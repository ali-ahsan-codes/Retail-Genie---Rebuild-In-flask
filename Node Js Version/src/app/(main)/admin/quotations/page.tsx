
// src/app/(main)/admin/quotations/page.tsx
'use client';
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { useApp } from '@/context/AppContext';
import type { Quotation, QuotationStatus, User } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { PlusCircle, Search, FileSignature, Edit, Eye, Trash2, Filter, Loader2, Settings2, Send, CheckCircle, XCircle, Edit3 as RevisionIcon, PauseCircle, Users } from 'lucide-react';
import { format, parseISO } from 'date-fns';
import { Input } from '@/components/ui/input';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';

const QUOTATION_STATUSES_FILTER_ADMIN: (QuotationStatus | 'all')[] = ['all', 'draft', 'sent', 'accepted', 'rejected', 'revision', 'hold', 'converted'];

const ADMIN_VALID_STATUS_TRANSITIONS: Partial<Record<QuotationStatus, { newStatus: QuotationStatus; label: string; icon?: React.ElementType }[]>> = {
  draft: [{ newStatus: 'sent', label: 'Mark as Sent', icon: Send }],
  sent: [
    { newStatus: 'accepted', label: 'Mark as Accepted', icon: CheckCircle },
    { newStatus: 'rejected', label: 'Mark as Rejected', icon: XCircle },
    { newStatus: 'revision', label: 'Request Revision', icon: RevisionIcon },
    { newStatus: 'hold', label: 'Put on Hold', icon: PauseCircle },
  ],
  accepted: [
    { newStatus: 'hold', label: 'Put on Hold', icon: PauseCircle },
    { newStatus: 'sent', label: 'Revert to Sent', icon: Send },
    // Admins might also have an option to directly mark as converted if all items processed
    // For now, conversion happens via specific buttons on view page.
  ],
  revision: [
    { newStatus: 'sent', label: 'Resend Quotation', icon: Send },
    { newStatus: 'draft', label: 'Revert to Draft', icon: Edit },
  ],
  hold: [
    { newStatus: 'sent', label: 'Resume (Mark as Sent)', icon: Send },
    { newStatus: 'accepted', label: 'Mark as Accepted', icon: CheckCircle },
    { newStatus: 'rejected', label: 'Mark as Rejected', icon: XCircle },
  ],
  // No transitions from 'rejected' or 'converted' by default from list view
};

export default function AdminAllQuotationsPage() {
  const { currentUser, quotations, deleteQuotation, updateQuotation: appUpdateQuotation, isDataLoaded, users } = useApp();
  const { toast } = useToast();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<QuotationStatus | 'all'>('all');
  const [salespersonFilter, setSalespersonFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(false);

  const filteredQuotations = useMemo(() => {
    return quotations // AppContext now provides all quotations for admin/manager
      .filter(q => {
        const searchMatch =
          q.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
          (q.customerName && q.customerName.toLowerCase().includes(searchTerm.toLowerCase())) ||
          (q.customerPhone && q.customerPhone.includes(searchTerm)) ||
          (q.salespersonId && users.find(u => u.id === q.salespersonId)?.username.toLowerCase().includes(searchTerm.toLowerCase()));
        const statusMatch = statusFilter === 'all' || q.status === statusFilter;
        const salespersonMatch = salespersonFilter === 'all' || q.salespersonId === salespersonFilter;
        return searchMatch && statusMatch && salespersonMatch;
      })
      .sort((a, b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime());
  }, [quotations, searchTerm, statusFilter, salespersonFilter, users]);

  const handleDelete = async (quotationId: string) => {
    setIsLoading(true);
    try {
      await deleteQuotation(quotationId); // AppContext deleteQuotation will use current admin's ID for auth
      toast({ title: "Quotation Deleted", description: `Quotation ${quotationId} has been removed.` });
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to delete quotation.", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };

  const handleStatusChange = async (quotationId: string, newStatus: QuotationStatus) => {
    setIsLoading(true);
    try {
      const updatedQuotation = await appUpdateQuotation({ id: quotationId, status: newStatus });
      if (updatedQuotation) {
        toast({ title: "Status Updated", description: `Quotation ${quotationId} status changed to ${newStatus.replace(/_/g, ' ')}.` });
      } else {
        toast({ title: "Update Failed", description: "Could not update quotation status.", variant: "destructive" });
      }
    } catch (error: any) {
      toast({ title: "Error", description: error.message || "Failed to update status.", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };
  
  const getStatusBadgeVariant = (status: QuotationStatus) => {
    switch (status) {
      case 'draft': return 'bg-gray-200 text-gray-700 border-gray-300';
      case 'sent': return 'bg-blue-100 text-blue-700 border-blue-300';
      case 'accepted': return 'bg-green-100 text-green-700 border-green-300';
      case 'rejected': return 'bg-red-100 text-red-700 border-red-300';
      case 'revision': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'hold': return 'bg-purple-100 text-purple-700 border-purple-300';
      case 'converted': return 'bg-teal-100 text-teal-700 border-teal-300';
      default: return 'bg-muted text-muted-foreground';
    }
  };
  
  const salespersons = useMemo(() => users.filter(u => u.role === 'salesperson'), [users]);

  if (!isDataLoaded) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="h-8 w-8 animate-spin text-primary" /> <span className="ml-2">Loading all quotations...</span></div>;
  }
  if (currentUser?.role !== 'admin' && currentUser?.role !== 'manager') {
    return <div className="p-4">Access Denied. Only Admins/Managers can view all quotations.</div>
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader className="flex flex-col md:flex-row items-start md:items-center justify-between">
          <div>
            <CardTitle className="text-2xl flex items-center"><FileSignature className="mr-2 h-7 w-7 text-primary" /> All Quotations</CardTitle>
            <CardDescription>View, manage, and track all customer quotations in the system.</CardDescription>
          </div>
          <Button asChild className="mt-4 md:mt-0">
            <Link href="/salesperson/quotations/create">
              <PlusCircle className="mr-2 h-4 w-4" /> Create New Quotation
            </Link>
          </Button>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-4 mb-4">
            <div className="relative flex-grow">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <Input
                type="search"
                placeholder="Search by ID, Customer, Salesperson..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 h-10 w-full"
              />
            </div>
            <div className="flex items-center gap-2">
              <Filter className="h-5 w-5 text-muted-foreground" />
              <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as QuotationStatus | 'all')}>
                <SelectTrigger className="w-full md:w-[180px] h-10">
                  <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                  {QUOTATION_STATUSES_FILTER_ADMIN.map(status => (
                    <SelectItem key={status} value={status} className="capitalize">
                      {status.replace(/_/g, ' ')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-muted-foreground" />
              <Select value={salespersonFilter} onValueChange={setSalespersonFilter}>
                <SelectTrigger className="w-full md:w-[180px] h-10">
                  <SelectValue placeholder="Filter by Salesperson" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Salespersons</SelectItem>
                  {salespersons.map(sp => (
                    <SelectItem key={sp.id} value={sp.id}>{sp.username}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {filteredQuotations.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground">
              <FileSignature className="mx-auto h-12 w-12 mb-4" />
              <p>No quotations found matching your criteria.</p>
            </div>
          ) : (
            <ScrollArea className="h-[calc(100vh-28rem)] border rounded-md">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead>Salesperson</TableHead>
                    <TableHead className="text-right">Total (OMR)</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Valid Until</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredQuotations.map((q) => {
                    const possibleActions = ADMIN_VALID_STATUS_TRANSITIONS[q.status] || [];
                    const quoteSalesperson = users.find(u => u.id === q.salespersonId)?.username || 'N/A';
                    return (
                    <TableRow key={q.id}>
                      <TableCell className="font-medium text-primary">{q.id}</TableCell>
                      <TableCell>
                        <div>{q.customerName || 'N/A'}</div>
                        <div className="text-xs text-muted-foreground">{q.customerPhone || ''}</div>
                      </TableCell>
                      <TableCell>{quoteSalesperson}</TableCell>
                      <TableCell className="text-right">{q.totalAmount.toFixed(2)}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={`capitalize ${getStatusBadgeVariant(q.status)}`}>
                          {q.status.replace(/_/g, ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell>{format(parseISO(q.createdAt), 'PP')}</TableCell>
                      <TableCell>{format(parseISO(q.validUntil), 'PP')}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-0.5">
                            <Button variant="ghost" size="icon" asChild className="h-8 w-8">
                               <Link href={`/salesperson/quotations/${q.id}/view`}><Eye className="h-4 w-4"/></Link>
                            </Button>
                            {(q.status === 'draft' || q.status === 'revision' || currentUser?.role === 'admin' || currentUser?.role === 'manager') && (
                              <Button variant="ghost" size="icon" asChild className="h-8 w-8">
                                <Link href={`/salesperson/quotations/${q.id}/edit`}><Edit className="h-4 w-4"/></Link>
                              </Button>
                            )}
                            {possibleActions.length > 0 && (
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button variant="ghost" size="icon" className="h-8 w-8" disabled={isLoading}>
                                    <Settings2 className="h-4 w-4" />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end">
                                  <DropdownMenuLabel>Change Status</DropdownMenuLabel>
                                  <DropdownMenuSeparator />
                                  {possibleActions.map(action => (
                                    <DropdownMenuItem key={action.newStatus} onClick={() => handleStatusChange(q.id, action.newStatus)} disabled={isLoading}>
                                      {action.icon && <action.icon className="mr-2 h-4 w-4" />}
                                      {action.label}
                                    </DropdownMenuItem>
                                  ))}
                                </DropdownMenuContent>
                              </DropdownMenu>
                            )}
                            <AlertDialog>
                                <AlertDialogTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive">
                                    <Trash2 className="h-4 w-4"/>
                                </Button>
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                <AlertDialogHeader><AlertDialogTitle>Confirm Deletion</AlertDialogTitle></AlertDialogHeader>
                                <AlertDialogDescription>Are you sure you want to delete quotation {q.id}?</AlertDialogDescription>
                                <AlertDialogFooter>
                                    <AlertDialogCancel disabled={isLoading}>Cancel</AlertDialogCancel>
                                    <AlertDialogAction onClick={() => handleDelete(q.id)} className="bg-destructive hover:bg-destructive/90" disabled={isLoading}>
                                      {isLoading ? "Deleting..." : "Delete"}
                                    </AlertDialogAction>
                                </AlertDialogFooter>
                                </AlertDialogContent>
                            </AlertDialog>
                        </div>
                      </TableCell>
                    </TableRow>
                  );})}
                </TableBody>
              </Table>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
