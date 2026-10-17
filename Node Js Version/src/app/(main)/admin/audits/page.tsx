// src/app/(main)/admin/audits/page.tsx
'use client';

import React, { useEffect, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PlusCircle, ShieldAlert, ClipboardCheck, Eye, Edit, Trash2, Loader2, RotateCcw } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import Link from 'next/link';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { format, parseISO, isValid } from 'date-fns';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import type { Audit, AuditStatus } from '@/types';

export default function AdminAuditsPage() {
  const { currentUser, hasPermission, isDataLoaded, audits, users } = useApp();

  const getAuditorUsername = (auditorId?: string): string => {
    if (!auditorId) return 'Not Assigned';
    const auditor = users.find(u => u.id === auditorId);
    return auditor?.username || 'Unknown Auditor';
  };

  const getStatusBadgeVariant = (status: AuditStatus) => {
    switch (status) {
      case 'pending': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'in_progress': return 'bg-blue-100 text-blue-700 border-blue-300';
      case 'completed': return 'bg-green-100 text-green-700 border-green-300';
      case 'cancelled': return 'bg-red-100 text-red-700 border-red-300';
      default: return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  const sortedAudits = useMemo(() => {
    return [...audits].sort((a, b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime());
  }, [audits]);

  if (!isDataLoaded) {
    return (
        <div className="flex flex-col items-center justify-center h-full p-8">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading audit management...</p>
        </div>
    );
  }

  if (!currentUser || !(currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('manage_audits')))) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to manage audits.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader className="flex flex-row justify-between items-center">
          <div>
            <CardTitle className="text-2xl flex items-center">
              <ClipboardCheck className="mr-2 h-7 w-7 text-primary" /> Audit Management
            </CardTitle>
            <CardDescription>
              Oversee, launch, and review stock audits.
            </CardDescription>
          </div>
          <Button asChild>
            <Link href="/admin/audits/create"> 
              <PlusCircle className="mr-2 h-4 w-4" /> Launch New Audit
            </Link>
          </Button>
        </CardHeader>
        <CardContent>
          {sortedAudits.length === 0 ? (
            <div className="text-center py-10">
              <ClipboardCheck className="mx-auto h-12 w-12 text-muted-foreground mb-3" />
              <p className="text-lg font-medium">No Audits Found</p>
              <p className="text-muted-foreground text-sm">
                No audits have been launched yet. Click "Launch New Audit" to get started.
              </p>
            </div>
          ) : (
            <ScrollArea className="h-[calc(100vh-20rem)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead>Auditor</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Completed</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedAudits.map((audit) => (
                    <TableRow key={audit.id}>
                      <TableCell className="font-medium text-primary">{audit.id}</TableCell>
                      <TableCell>{audit.title}</TableCell>
                      <TableCell>{audit.storeLocation}</TableCell>
                      <TableCell>{getAuditorUsername(audit.auditorId)}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn("capitalize", getStatusBadgeVariant(audit.status))}>
                          {audit.status.replace(/_/g, ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell>{isValid(parseISO(audit.createdAt)) ? format(parseISO(audit.createdAt), 'PP p') : 'N/A'}</TableCell>
                      <TableCell>{audit.completedAt && isValid(parseISO(audit.completedAt)) ? format(parseISO(audit.completedAt), 'PP p') : '-'}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="icon" asChild className="h-8 w-8">
                           <Link href={`/admin/audits/${audit.id}/report`} title="View Report">
                             <Eye className="h-4 w-4" />
                           </Link>
                        </Button>
                         {audit.status === 'completed' && (
                           <Button variant="ghost" size="icon" asChild className="h-8 w-8">
                             <Link href={`/admin/audits/create?relaunchFrom=${audit.id}`} title="Relaunch Audit">
                               <RotateCcw className="h-4 w-4 text-orange-500" />
                             </Link>
                           </Button>
                         )}
                         {/* Add Edit/Delete if applicable for 'pending' audits */}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
