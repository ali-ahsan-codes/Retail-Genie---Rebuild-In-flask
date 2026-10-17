
'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import type { DemandNotice, DemandNoticeStatus, Product, User } from '@/types';
import { useApp } from '@/context/AppContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { BellRing, AlertTriangle, Search, PackageCheck, PackageSearch as StorekeeperIcon, Edit3, Truck, PackagePlus, Loader2, UserCheck } from 'lucide-react';
import { format, isPast, isToday } from 'date-fns';
import { Input } from '@/components/ui/input';
import { DEMAND_NOTICE_STATUSES_WORKFLOW } from '@/lib/constants';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import Link from 'next/link';
import { Alert, AlertDescription as UIDescription, AlertTitle as UITitle } from '@/components/ui/alert';


const STOREKEEPER_RELEVANT_STATUSES: DemandNoticeStatus[] = [
    'awaiting_stock',
    'partial_stock_available',
    'full_stock_available',
    'order_processing',
    'preparing_stock',
    'ready_for_collection'
];

const STOREKEEPER_ACTIONS_MAP: Partial<Record<DemandNoticeStatus, { actionLabel: string; nextStatus: DemandNoticeStatus; icon?: React.ElementType }[]>> = {
    order_processing: [{ actionLabel: "Start Preparing Stock", nextStatus: 'preparing_stock', icon: PackagePlus }],
    preparing_stock: [{ actionLabel: "Mark as Ready for Collection", nextStatus: 'ready_for_collection', icon: PackageCheck }],
};

export default function StorekeeperDemandNoticesPage() {
  const {
    demandNotices: allDemandNoticesFromContext,
    getProductById,
    updateDemandNoticeStatus,
    currentUser,
    getTodayAttendanceForUser,
    isDataLoaded,
    isAttendanceCurrentlyRequired, 
  } = useApp();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<DemandNoticeStatus | 'all'>('all');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { toast } = useToast();
  const [hasClockedInToday, setHasClockedInToday] = useState<boolean | null>(null);
  const [mustClockIn, setMustClockIn] = useState(false); 

  useEffect(() => {
    if (currentUser && isDataLoaded) {
      const attendanceLog = getTodayAttendanceForUser(currentUser.id);
      setHasClockedInToday(!!attendanceLog);
      setMustClockIn(isAttendanceCurrentlyRequired(currentUser.role) && !attendanceLog);
    }
  }, [currentUser, getTodayAttendanceForUser, isDataLoaded, isAttendanceCurrentlyRequired]);

  const storekeeperNotices = useMemo(() => {
    if (!Array.isArray(allDemandNoticesFromContext)) {
      return [];
    }
    return allDemandNoticesFromContext.filter(notice => {
        const searchMatch = notice.productName.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            notice.productSku.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            (notice.customerContactNumber && notice.customerContactNumber.includes(searchTerm)) ||
                            notice.salespersonName.toLowerCase().includes(searchTerm.toLowerCase());
        const statusMatch = statusFilter === 'all' || notice.status === statusFilter;
        const relevantForStorekeeper = STOREKEEPER_RELEVANT_STATUSES.includes(notice.status);
        return searchMatch && statusMatch && relevantForStorekeeper;
    }).sort((a,b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [allDemandNoticesFromContext, searchTerm, statusFilter]);

  const getStatusBadge = useCallback((status: DemandNoticeStatus, quantityFulfilled?: number, quantityRequested?: number) => {
    let text = status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
    let variantClass = "bg-gray-100 text-gray-700 border-gray-300";

    switch (status) {
      case 'pending_review': variantClass = "bg-yellow-100 text-yellow-700 border-yellow-300"; break;
      case 'awaiting_stock': variantClass = "bg-red-100 text-red-700 border-red-300"; break;
      case 'partial_stock_available':
        variantClass = "bg-yellow-100 text-yellow-700 border-yellow-300";
        text = `Partial Stock (${quantityFulfilled || 0}/${quantityRequested || '?'})`;
        break;
      case 'full_stock_available': variantClass = "bg-green-100 text-green-700 border-green-300"; break;
      case 'customer_notified_stock': variantClass = "bg-blue-100 text-blue-700 border-blue-300"; break;
      case 'awaiting_customer_action': variantClass = "bg-purple-100 text-purple-700 border-purple-300"; break;
      case 'order_processing': variantClass = "bg-indigo-100 text-indigo-700 border-indigo-300"; text="Order Processing"; break;
      case 'preparing_stock': variantClass = "bg-cyan-100 text-cyan-700 border-cyan-300"; text="Preparing Stock"; break;
      case 'ready_for_collection': variantClass = "bg-teal-100 text-teal-700 border-teal-300"; text="Ready for Collection"; break;
      case 'fulfilled': variantClass = "bg-emerald-200 text-emerald-800 border-emerald-400"; break;
      case 'cancelled': return <Badge variant="destructive">Cancelled</Badge>;
      default: break;
    }
    return <Badge variant="outline" className={variantClass}>{text}</Badge>;
  }, []);


  const handleUpdateStatus = useCallback(async (noticeId: string, newStatus: DemandNoticeStatus) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before processing demand notices. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    const notice = storekeeperNotices.find(n => n.id === noticeId);
    if (!notice) {
        toast({ title: 'Error', description: 'Demand notice not found.', variant: 'destructive' });
        return;
    }

    const requiresLinkedOrder =
        (newStatus === 'preparing_stock' && notice.status === 'order_processing') ||
        (newStatus === 'ready_for_collection' && notice.status === 'preparing_stock');

    if (requiresLinkedOrder && !notice.linkedOrderId) {
        toast({
            title: 'Cannot Proceed',
            description: 'This demand notice is not yet linked to a sales order. The salesperson needs to "Prepare the Order" first.',
            variant: 'destructive',
            duration: 8000,
        });
        return;
    }

    setIsSubmitting(true);
    try {
        await updateDemandNoticeStatus(noticeId, newStatus, currentUser);
        toast({ title: 'Status Updated', description: `Demand notice status changed to ${newStatus.replace(/_/g, ' ')}.` });
    } catch (error) {
        toast({ title: 'Error updating status', variant: 'destructive' });
    } finally {
        setIsSubmitting(false);
    }
  }, [storekeeperNotices, updateDemandNoticeStatus, currentUser, toast, mustClockIn]);

  if (!isDataLoaded || hasClockedInToday === null) {
    return (
        <div className="flex flex-col items-center justify-center h-full p-8">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading page and checking attendance...</p>
        </div>
    );
  }

  if (mustClockIn) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <Alert variant="destructive" className="max-w-md text-left">
          <AlertTriangle className="h-5 w-5" />
          <UITitle>Mandatory Attendance Required</UITitle>
          <UIDescription>
            The mandatory attendance time has passed. You must clock in before you can manage demand notices.
            Please go to your profile to complete your attendance.
          </UIDescription>
        </Alert>
        <Button asChild className="mt-6">
          <Link href="/profile">
            <UserCheck className="mr-2 h-4 w-4" /> Go to Profile to Clock In
          </Link>
        </Button>
      </div>
    );
  }


  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
            <CardTitle className="text-2xl flex items-center"><StorekeeperIcon className="mr-2 h-7 w-7 text-primary" /> Demand Notices for Storekeeper</CardTitle>
            <CardDescription>Monitor and process product demand notices that require stock preparation.</CardDescription>
        </CardHeader>
        <CardContent>
        <div className="flex flex-col md:flex-row gap-4 mb-4">
            <div className="relative flex-grow">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                    type="search"
                    placeholder="Search by Product, Product Code, Salesperson..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10 h-10 w-full"
                    disabled={mustClockIn}
                />
            </div>
            <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as DemandNoticeStatus | 'all')} disabled={mustClockIn}>
                <SelectTrigger className="w-full md:w-[200px] h-10">
                    <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="all">All Relevant Statuses</SelectItem>
                    {STOREKEEPER_RELEVANT_STATUSES.map(status => (
                       <SelectItem key={status} value={status} className="capitalize">{status.replace(/_/g, ' ')}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
          </div>

          {storekeeperNotices.length === 0 ? (
            <div className="py-10 text-center">
              <AlertTriangle className="mx-auto h-12 w-12 text-muted-foreground mb-3" />
              <p className="text-lg font-medium">No demand notices found for processing.</p>
              <p className="text-muted-foreground text-sm">
                 {searchTerm || statusFilter !== 'all' ? "Try adjusting your search/filter." : "There are currently no demand notices requiring your attention."}
              </p>
            </div>
          ) : (
            <ScrollArea className="h-[calc(100vh-22rem)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product (Product Code)</TableHead>
                    <TableHead>Salesperson</TableHead>
                    <TableHead className="text-center">Qty Req.</TableHead>
                    <TableHead className="text-center">Stock Avail.</TableHead>
                    <TableHead>Expected Date</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {storekeeperNotices.map((notice) => {
                    const product = notice.productId ? getProductById(notice.productId) : undefined;
                    const availableActions = STOREKEEPER_ACTIONS_MAP[notice.status] || [];
                    return (
                    <TableRow key={notice.id}>
                      <TableCell>
                        <div className="font-medium">{notice.productName}</div>
                        <div className="text-xs text-muted-foreground">Product Code: {notice.productSku}</div>
                      </TableCell>
                      <TableCell>{notice.salespersonName}</TableCell>
                      <TableCell className="text-center">{notice.quantityRequested}</TableCell>
                      <TableCell className={cn("text-center", (product?.quantityInStock ?? 0) < notice.quantityRequested ? "text-red-600 font-semibold" : "text-green-600")}>
                        {product?.quantityInStock ?? (notice.isNewProduct ? 'New' : 'N/A')}
                      </TableCell>
                      <TableCell>{format(new Date(notice.expectedAvailabilityDate), 'MMM d, yyyy')}</TableCell>
                      <TableCell>{getStatusBadge(notice.status, notice.quantityFulfilled, notice.quantityRequested)}</TableCell>
                      <TableCell className="text-right">
                        {availableActions.map(action => {
                          const Icon = action.icon;
                          return (
                            <Button
                                key={action.nextStatus}
                                variant="outline"
                                size="sm"
                                onClick={() => handleUpdateStatus(notice.id, action.nextStatus)}
                                disabled={isSubmitting || mustClockIn}
                                className="ml-2"
                            >
                                {Icon && <Icon className="h-4 w-4 mr-1.5" />}
                                {action.actionLabel}
                            </Button>
                        )})}
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
    
