
'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import type { DemandNotice, DemandNoticeStatus, Product } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogClose } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { PlusCircle, BellRing, AlertTriangle, Search, Edit3, Trash2, CheckCircle, PackagePlus, Loader2, UserCheck } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { format, isPast, isToday, differenceInDays } from 'date-fns';
import DemandNoticeForm from '@/components/salesperson/DemandNoticeForm';
import { Input } from '@/components/ui/input';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { DEMAND_NOTICE_STATUSES } from '@/lib/constants';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import Link from 'next/link';
import { Alert, AlertDescription as UIDescription, AlertTitle as UITitle } from '@/components/ui/alert';


interface MemoizedSalespersonDemandNoticeRowProps {
  notice: DemandNotice;
  product?: Product;
  isSubmitting: boolean;
  onUpdateStatus: (noticeId: string, newStatus: DemandNoticeStatus) => void;
  onDelete: (noticeId: string) => void;
  onPrepareOrder: (noticeId: string) => void;
  getStatusBadge: (status: DemandNoticeStatus, quantityFulfilled?: number, quantityRequested?: number) => JSX.Element;
  getReminderHighlight: (notice: DemandNotice, product?: Product) => string;
  disabled: boolean; 
}

const MemoizedSalespersonDemandNoticeRow = React.memo(function MemoizedSalespersonDemandNoticeRow({
  notice, product, isSubmitting, onUpdateStatus, onDelete, onPrepareOrder, getStatusBadge, getReminderHighlight, disabled
}: MemoizedSalespersonDemandNoticeRowProps) {
  const reminderClass = getReminderHighlight(notice, product);
  const canPrepareOrder = notice.status === 'full_stock_available' || notice.status === 'customer_notified_stock';

  return (
    <TableRow key={`${notice.id}-row`} className={cn(reminderClass)}>
      <TableCell>
        <div className="font-medium">{notice.productName}</div>
        <div className="text-xs text-muted-foreground">Product Code: {notice.productSku}</div>
      </TableCell>
      <TableCell>{notice.customerContactNumber}</TableCell>
      <TableCell className="text-center">{notice.quantityRequested}</TableCell>
      <TableCell className="text-right">OMR {notice.agreedPrice.toFixed(2)}</TableCell>
      <TableCell>{format(new Date(notice.expectedAvailabilityDate), 'MM/dd/yyyy')}</TableCell>
      <TableCell>{getStatusBadge(notice.status, notice.quantityFulfilled, notice.quantityRequested)}</TableCell>
      <TableCell className="text-center">{product?.quantityInStock ?? 'N/A'}</TableCell>
      <TableCell className="text-right">
        <div className="flex gap-1 justify-end items-center">
          {notice.status === 'full_stock_available' && (
            <Button variant="ghost" size="sm" onClick={() => onUpdateStatus(notice.id, 'customer_notified_stock')} disabled={isSubmitting || disabled} className="text-green-600 hover:text-green-700 hover:bg-green-100">
              <CheckCircle className="h-4 w-4 mr-1" /> Notified
            </Button>
          )}
          {canPrepareOrder && (
            <Button variant="default" size="sm" onClick={() => onPrepareOrder(notice.id)} disabled={isSubmitting || disabled} className="bg-blue-500 hover:bg-blue-600 text-white">
              <PackagePlus className="h-4 w-4 mr-1" /> Prepare Order
            </Button>
          )}
            {(notice.status === 'pending_review' || notice.status === 'awaiting_stock' || notice.status === 'full_stock_available' || notice.status === 'partial_stock_available') && (
            <AlertDialog>
                <AlertDialogTrigger asChild>
                    <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive hover:bg-destructive/10" disabled={isSubmitting || disabled}>
                        <Trash2 className="h-4 w-4"/>
                    </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                    <AlertDialogHeader>
                    <AlertDialogTitle>Cancel Demand Notice?</AlertDialogTitle>
                    <AlertDialogDescription>
                        Are you sure you want to cancel this demand notice for {notice.productName}? This action cannot be undone.
                    </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                    <AlertDialogCancel disabled={isSubmitting}>Keep Notice</AlertDialogCancel>
                    <AlertDialogAction onClick={() => onUpdateStatus(notice.id, 'cancelled')} className="bg-destructive hover:bg-destructive/90" disabled={isSubmitting}>
                        {isSubmitting ? "Cancelling..." : "Confirm Cancel"}
                    </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
            )}
        </div>
      </TableCell>
    </TableRow>
  );
});
MemoizedSalespersonDemandNoticeRow.displayName = 'MemoizedSalespersonDemandNoticeRow';

export default function SalespersonDemandNoticesPage() {
  const app = useApp();
  const {
    currentUser,
    products,
    demandNotices,
    addDemandNotice,
    updateDemandNoticeStatus,
    deleteDemandNotice,
    getProductById,
    getDemandNoticesForSalesperson,
    prepareOrderFromDemandNotice,
    getTodayAttendanceForUser,
    isDataLoaded,
    isAttendanceCurrentlyRequired, 
  } = app;
  const { toast } = useToast();

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<DemandNoticeStatus | 'all'>('all');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hasClockedInToday, setHasClockedInToday] = useState<boolean | null>(null);
  const [mustClockIn, setMustClockIn] = useState(false); 

  useEffect(() => {
    if (currentUser && isDataLoaded) {
      const attendanceLog = getTodayAttendanceForUser(currentUser.id);
      setHasClockedInToday(!!attendanceLog);
      setMustClockIn(isAttendanceCurrentlyRequired(currentUser.role) && !attendanceLog);
    }
  }, [currentUser, getTodayAttendanceForUser, isDataLoaded, isAttendanceCurrentlyRequired]);

  const salespersonNoticesFromContext = useMemo(() => {
    if (!currentUser) return [];
    return getDemandNoticesForSalesperson(currentUser.id);
  }, [currentUser, getDemandNoticesForSalesperson, demandNotices]);

  const filteredNotices = useMemo(() => {
    return salespersonNoticesFromContext.filter(notice => {
        const searchMatch = notice.productName.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            notice.productSku.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            notice.customerContactNumber.includes(searchTerm);
        const statusMatch = statusFilter === 'all' || notice.status === statusFilter;
        return searchMatch && statusMatch;
    }).sort((a,b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [salespersonNoticesFromContext, searchTerm, statusFilter]);


  const handleSubmitForm = useCallback(async (data: Omit<DemandNotice, 'id' | 'createdAt' | 'updatedAt' | 'salespersonId' | 'salespersonName' | 'status' | 'payments' | 'quantityFulfilled' | 'linkedOrderId'> & { expectedAvailabilityDate: string }) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before creating demand notices. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    setIsSubmitting(true);
    try {
      const newNotice = await addDemandNotice(data);
      if (newNotice) {
        toast({ title: 'Demand Notice Created', description: `Notice for ${data.productName} has been created.` });
        setIsFormOpen(false);
      } else {
        toast({ title: 'Error', description: 'Could not create demand notice.', variant: 'destructive' });
      }
    } catch (error) {
      toast({ title: 'Error', description: 'An unexpected error occurred.', variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  }, [addDemandNotice, toast, mustClockIn]);

  const handleUpdateStatus = useCallback(async (noticeId: string, newStatus: DemandNoticeStatus) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before updating demand notices. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    setIsSubmitting(true);
    try {
        await updateDemandNoticeStatus(noticeId, newStatus);
        toast({ title: 'Status Updated', description: `Demand notice status changed to ${newStatus.replace(/_/g, ' ')}.` });
    } catch (error) {
        toast({ title: 'Error updating status', variant: 'destructive' });
    } finally {
        setIsSubmitting(false);
    }
  }, [updateDemandNoticeStatus, toast, mustClockIn]);

  const handleCancelNotice = useCallback(async (noticeId: string) => {
    handleUpdateStatus(noticeId, 'cancelled');
  }, [handleUpdateStatus]);

  const handlePrepareOrder = useCallback(async (noticeId: string) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before preparing orders. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    setIsSubmitting(true);
    try {
        await prepareOrderFromDemandNotice(noticeId);
    } catch (error) {
        toast({ title: 'Error Preparing Order', description: (error as Error).message, variant: 'destructive'});
    } finally {
        setIsSubmitting(false);
    }
  }, [prepareOrderFromDemandNotice, toast, mustClockIn]);

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

  const getReminderHighlight = useCallback((notice: DemandNotice, product: Product | undefined) => {
    const isDue = isPast(new Date(notice.expectedAvailabilityDate)) || isToday(new Date(notice.expectedAvailabilityDate));
    if (notice.status === 'full_stock_available' && isDue) return 'bg-green-50/70 border-l-4 border-green-400';
    if ((notice.status === 'awaiting_stock' || notice.status === 'pending_review') && isDue && (!product || product.quantityInStock < notice.quantityRequested)) return 'bg-orange-50/70 border-l-4 border-orange-400';
    return '';
  }, []);

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
        <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="text-2xl flex items-center"><BellRing className="mr-2 h-7 w-7 text-primary" /> My Demand Notices</CardTitle>
            <CardDescription>Track products requested by customers that are currently out of stock.</CardDescription>
          </div>
          <Dialog open={isFormOpen} onOpenChange={setIsFormOpen}>
            <DialogTrigger asChild>
              <Button onClick={() => setIsFormOpen(true)} disabled={isSubmitting || mustClockIn}>
                <PlusCircle className="mr-2 h-4 w-4" /> Create New Notice
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Create Demand Notice</DialogTitle>
              </DialogHeader>
              <DemandNoticeForm
                onSubmit={handleSubmitForm}
                onCancel={() => setIsFormOpen(false)}
                isLoading={isSubmitting}
              />
            </DialogContent>
          </Dialog>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-4 mb-4">
            <div className="relative flex-grow">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                    type="search"
                    placeholder="Search by Product Name, Product Code, or Customer Contact..."
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
                    <SelectItem value="all">All Statuses</SelectItem>
                    {DEMAND_NOTICE_STATUSES.map(status => (
                    <SelectItem key={status} value={status} className="capitalize">{status.replace(/_/g, ' ')}</SelectItem>
                    ))}
                </SelectContent>
            </Select>
          </div>

          {filteredNotices.length === 0 ? (
            <div className="py-10 text-center">
              <AlertTriangle className="mx-auto h-12 w-12 text-muted-foreground mb-3" />
              <p className="text-lg font-medium">No demand notices found.</p>
              <p className="text-muted-foreground text-sm">
                {searchTerm || statusFilter !== 'all' ? "Try adjusting your search/filter." : "Create a new demand notice for out-of-stock products."}
              </p>
            </div>
          ) : (
            <ScrollArea className="h-[calc(100vh-24rem)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Product (Product Code)</TableHead>
                    <TableHead>Customer Contact</TableHead>
                    <TableHead className="text-center">Qty</TableHead>
                    <TableHead className="text-right">Agreed Price</TableHead>
                    <TableHead>Expected Date</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-center">Current Stock</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredNotices.map((notice) => (
                    <MemoizedSalespersonDemandNoticeRow
                      key={`${notice.id}-memoized`}
                      notice={notice}
                      product={getProductById(notice.productId)}
                      isSubmitting={isSubmitting}
                      onUpdateStatus={handleUpdateStatus}
                      onDelete={handleCancelNotice}
                      onPrepareOrder={handlePrepareOrder}
                      getStatusBadge={getStatusBadge}
                      getReminderHighlight={getReminderHighlight}
                      disabled={mustClockIn}
                    />
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
