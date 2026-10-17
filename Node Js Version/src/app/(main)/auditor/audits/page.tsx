// src/app/(main)/auditor/audits/page.tsx
'use client';

import React, { useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ClipboardCheck, ShieldAlert, Loader2, Eye, PlayCircle, AlertTriangle } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import Link from 'next/link';
import { format, parseISO, isValid } from 'date-fns';
import type { Audit, AuditStatus } from '@/types';
import { cn } from '@/lib/utils';

export default function AuditorAuditsPage() {
  const { currentUser, isDataLoaded, audits } = useApp();

  const assignedAudits = useMemo(() => {
    if (!currentUser || !audits) return [];
    // The API should already filter by auditorId, but this is a safe client-side double check.
    return audits.filter(audit => audit.auditorId === currentUser.id)
                 .sort((a, b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime());
  }, [currentUser, audits]);

  const getStatusBadgeVariant = (status: AuditStatus) => {
    switch (status) {
      case 'pending': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'in_progress': return 'bg-blue-100 text-blue-700 border-blue-300';
      case 'completed': return 'bg-green-100 text-green-700 border-green-300';
      case 'cancelled': return 'bg-red-100 text-red-700 border-red-300';
      default: return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  if (!isDataLoaded) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">Loading your assigned audits...</p>
      </div>
    );
  }

  if (!currentUser || currentUser.role !== 'auditor') {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to view this page.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader className="flex flex-row justify-between items-center">
          <div>
            <CardTitle className="text-2xl flex items-center">
              <ClipboardCheck className="mr-2 h-7 w-7 text-primary" /> My Assigned Audits
            </CardTitle>
            <CardDescription>
              View and conduct audits assigned to you.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {assignedAudits.length === 0 ? (
             <div className="text-center py-10">
              <AlertTriangle className="mx-auto h-12 w-12 text-muted-foreground mb-3" />
              <p className="text-lg font-medium">No Audits Assigned</p>
              <p className="text-muted-foreground text-sm">
                There are currently no audits assigned to you. Please check back later or contact an administrator.
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
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Assigned On</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {assignedAudits.map((audit) => (
                    <TableRow key={audit.id}>
                      <TableCell className="font-medium text-primary">{audit.id}</TableCell>
                      <TableCell>{audit.title}</TableCell>
                      <TableCell>{audit.storeLocation}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn("capitalize", getStatusBadgeVariant(audit.status))}>
                          {audit.status.replace(/_/g, ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell>{isValid(parseISO(audit.createdAt)) ? format(parseISO(audit.createdAt), 'PP p') : 'N/A'}</TableCell>
                      <TableCell>{isValid(parseISO(audit.updatedAt)) ? format(parseISO(audit.updatedAt), 'PP p') : 'N/A'}</TableCell>
                      <TableCell className="text-right">
                        {audit.status === 'pending' && (
                          <Button variant="outline" size="sm" asChild>
                            <Link href={`/auditor/audits/${audit.id}/conduct`}>
                              <PlayCircle className="mr-2 h-4 w-4 text-green-600" /> Start Audit
                            </Link>
                          </Button>
                        )}
                        {(audit.status === 'in_progress') && (
                          <Button variant="default" size="sm" asChild className="bg-blue-500 hover:bg-blue-600">
                            <Link href={`/auditor/audits/${audit.id}/conduct`}>
                              <ClipboardCheck className="mr-2 h-4 w-4" /> Continue Audit
                            </Link>
                          </Button>
                        )}
                        {(audit.status === 'completed' || audit.status === 'cancelled') && (
                           <Button variant="ghost" size="sm" asChild className="text-muted-foreground hover:text-primary">
                             <Link href={`/auditor/audits/${audit.id}/report`}>
                               <Eye className="mr-2 h-4 w-4" /> View Report
                             </Link>
                           </Button>
                        )}
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
