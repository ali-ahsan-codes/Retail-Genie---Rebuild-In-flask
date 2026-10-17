
'use client';

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import type { DemandNotice, DemandNoticeStatus, Product, User, PaymentDetail } from '@/types';
import { useApp } from '@/context/AppContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { BellRing, AlertTriangle, Search, PackageCheck, ShieldAlert, Edit3, Trash2, DollarSign, CheckCircle, ThumbsUp, PackagePlus, Truck, MoreHorizontal, Settings2 } from 'lucide-react';
import { format, isPast, isToday, parseISO } from 'date-fns';
import { Input } from '@/components/ui/input';
import { DEMAND_NOTICE_STATUSES_WORKFLOW } from '@/lib/constants';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogClose, DialogFooter } from '@/components/ui/dialog';
import DemandNoticeForm from '@/components/salesperson/DemandNoticeForm'; // Re-use for editing
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';


const ADMIN_FULFILLMENT_FILTERS: DemandNoticeStatus[] = [
    'pending_review', 'awaiting_stock', 'partial_stock_available',
    'full_stock_available', 'customer_notified_stock', 'awaiting_customer_action',
    'order_processing', 'preparing_stock', 'ready_for_collection',
    'fulfilled', 'cancelled'
];

export default function AdminDemandNoticesPage() {
  const {
    demandNotices: contextDemandNotices,
    getProductById,
    updateDemandNoticeStatus,
    deleteDemandNotice,
    currentUser,
    hasPermission,
    addDemandNotice,
    updateDemandNotice: contextUpdateDemandNotice,
    products,
    loadDataFromDb,
    getAllDemandNotices,
  } = useApp();

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<DemandNoticeStatus | 'all'>('all');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { toast } = useToast();

  const [localDemandNotices, setLocalDemandNotices] = useState<DemandNotice[]>([]);
  const [editingNotice, setEditingNotice] = useState<DemandNotice | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);

  const [isStatusChangeModalOpen, setIsStatusChangeModalOpen] = useState(false);
  const [selectedNoticeForStatusChange, setSelectedNoticeForStatusChange] = useState<DemandNotice | null>(null);
  const [newSelectedStatus, setNewSelectedStatus] = useState<DemandNoticeStatus | ''>('');


  const canManageDemandNotices = hasPermission('manage_demand_notices');

  useEffect(() => {
    let isMounted = true;
    const fetchNotices = async () => {
      const noticesFromDb = await getAllDemandNotices();
      if (isMounted) {
        const uniqueNotices = Array.from(new Map(noticesFromDb.map(item => [item.id, item])).values());
        setLocalDemandNotices(uniqueNotices.sort((a,b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()));
      }
    }
    fetchNotices();
    return () => { isMounted = false; };
  }, [contextDemandNotices, getAllDemandNotices]);


  const filteredNotices = useMemo(() => {
    return localDemandNotices
      .filter(notice => {
        const searchMatch =
            (notice.productName && notice.productName.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (notice.productSku && notice.productSku.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (notice.customerContactNumber && notice.customerContactNumber.includes(searchTerm)) ||
            (notice.salespersonName && notice.salespersonName.toLowerCase().includes(searchTerm.toLowerCase())) ||
            (notice.id.toLowerCase().includes(searchTerm.toLowerCase()));
        const statusMatch = statusFilter === 'all' || notice.status === statusFilter;
        return searchMatch && statusMatch;
    });
  }, [localDemandNotices, searchTerm, statusFilter]);

  const getStatusBadge = useCallback((status: DemandNoticeStatus, quantityFulfilled?: number, quantityRequested?: number) => {
    let text = status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
    let variantClass = "bg-gray-100 text-gray-700 border-gray-300"; // Default

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
    if (notice.status === 'awaiting_stock' && isDue && (!product || product.quantityInStock < notice.quantityRequested)) return 'bg-orange-50/70 border-l-4 border-orange-400';
    return '';
  }, []);

  const handleEditNotice = (notice: DemandNotice) => {
    setEditingNotice(notice);
    setIsFormOpen(true);
  };

  const handleSubmitForm = async (data: Omit<DemandNotice, 'id' | 'createdAt' | 'updatedAt' | 'salespersonId' | 'salespersonName' | 'status' | 'payments'> & {productName: string, productSku: string, expectedAvailabilityDate: string}) => {
    if (!currentUser) return;
    setIsSubmitting(true);
    try {
      if (editingNotice) {
        const payload: DemandNotice = {
            ...editingNotice,
            ...data,
            isNewProduct: !!data.productId,
            updatedAt: new Date().toISOString(),
        };
        await contextUpdateDemandNotice(payload);
        toast({ title: 'Notice Updated', description: `Demand notice ${editingNotice.id} updated.` });
      } else {
        const newNoticePayload = {
            ...data,
            salespersonId: currentUser.id,
            salespersonName: currentUser.username,
            isNewProduct: !data.productId,
        };
        await addDemandNotice(newNoticePayload as any);
        toast({ title: 'Notice Created', description: `New demand notice for ${data.productName} created.` });
      }
      setIsFormOpen(false);
      setEditingNotice(null);
      await loadDataFromDb(false);
    } catch (error) {
      toast({ title: 'Error', description: `Could not save notice. ${(error as Error).message}`, variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAdminInitiatedStatusChange = async (noticeId: string, newStatus: DemandNoticeStatus) => {
    if (!canManageDemandNotices) return;
    setIsSubmitting(true);
    try {
      await updateDemandNoticeStatus(noticeId, newStatus, currentUser);
      toast({ title: 'Status Updated', description: `Notice status changed to ${newStatus.replace(/_/g, ' ')}.` });
      setIsStatusChangeModalOpen(false);
      setSelectedNoticeForStatusChange(null);
      setNewSelectedStatus('');
    } catch (error) {
      toast({ title: 'Error', description: 'Could not update notice status.', variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const openStatusChangeModal = (notice: DemandNotice) => {
    setSelectedNoticeForStatusChange(notice);
    setNewSelectedStatus(notice.status); // Pre-fill with current status
    setIsStatusChangeModalOpen(true);
  };


  if (!canManageDemandNotices && !hasPermission('view_admin_dashboard')) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to view demand notices.</p>
      </div>
    );
  }


  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
            <CardTitle className="text-2xl flex items-center"><BellRing className="mr-2 h-7 w-7 text-primary" /> Demand Fulfillment Dashboard</CardTitle>
            <CardDescription>View, edit, and manage all product demand notices.</CardDescription>
        </CardHeader>
        <CardContent>
        <div className="flex flex-col md:flex-row gap-4 mb-4">
            <div className="relative flex-grow">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                    type="search"
                    placeholder="Search by ID, Product, Product Code, Customer, Salesperson..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10 h-10 w-full"
                />
            </div>
            <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as DemandNoticeStatus | 'all')}>
                <SelectTrigger className="w-full md:w-[220px] h-10">
                    <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    {ADMIN_FULFILLMENT_FILTERS.map(status => (
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
                 {searchTerm || statusFilter !== 'all' ? "Try adjusting your search/filter." : "There are currently no demand notices in the system."}
              </p>
            </div>
          ) : (
            <ScrollArea className="h-[calc(100vh-24rem)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID / Product (Product Code)</TableHead>
                    <TableHead>Salesperson</TableHead>
                    <TableHead>Customer</TableHead>
                    <TableHead className="text-center">Qty Req.</TableHead>
                    <TableHead className="text-center">Qty Avail.</TableHead>
                    <TableHead className="text-right">Agreed Price</TableHead>
                    <TableHead>Advance Paid</TableHead>
                    <TableHead>Expected</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredNotices.map((notice) => {
                    const product = notice.productId ? getProductById(notice.productId) : undefined;
                    const reminderClass = getReminderHighlight(notice, product);
                    const totalAdvancePaid = notice.payments?.reduce((sum, p) => sum + p.amount, 0) || 0;
                    return (
                    <TableRow key={notice.id} className={cn(reminderClass)}>
                      <TableCell>
                        <div className="font-medium text-primary">{notice.id}</div>
                        <div>{notice.productName}</div>
                        <div className="text-xs text-muted-foreground">Product Code: {notice.productSku}</div>
                      </TableCell>
                      <TableCell>{notice.salespersonName}</TableCell>
                      <TableCell>{notice.customerContactNumber}</TableCell>
                      <TableCell className="text-center">{notice.quantityRequested}</TableCell>
                      <TableCell className={cn("text-center font-semibold", (product?.quantityInStock ?? (notice.quantityFulfilled || 0)) < notice.quantityRequested ? "text-orange-600" : "text-green-600")}>
                        {product?.quantityInStock ?? (notice.quantityFulfilled || 0)}
                      </TableCell>
                      <TableCell className="text-right">OMR {notice.agreedPrice.toFixed(2)}</TableCell>
                      <TableCell>
                        {totalAdvancePaid > 0 ? (
                          <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
                            Yes - OMR {totalAdvancePaid.toFixed(2)}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">No</Badge>
                        )}
                      </TableCell>
                      <TableCell>{format(new Date(notice.expectedAvailabilityDate), 'PP')}</TableCell>
                      <TableCell>{getStatusBadge(notice.status, notice.quantityFulfilled, notice.quantityRequested)}</TableCell>
                      <TableCell>{format(new Date(notice.createdAt), 'PP HH:mm')}</TableCell>
                      <TableCell className="text-right">
                         <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                                <Button variant="ghost" size="icon-sm" className="h-8 w-8 p-0" disabled={isSubmitting || !canManageDemandNotices}>
                                    <MoreHorizontal className="h-4 w-4" />
                                </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                                <DropdownMenuLabel>Actions</DropdownMenuLabel>
                                {notice.status === 'pending_review' && (
                                    <DropdownMenuItem onClick={() => handleAdminInitiatedStatusChange(notice.id, 'awaiting_stock')} disabled={isSubmitting}>
                                        <ThumbsUp className="mr-2 h-4 w-4 text-green-600"/> Approve Notice
                                    </DropdownMenuItem>
                                )}
                                <DropdownMenuItem onClick={() => handleEditNotice(notice)} disabled={isSubmitting}>
                                    <Edit3 className="mr-2 h-4 w-4" /> Edit Details
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => openStatusChangeModal(notice)} disabled={isSubmitting}>
                                    <Settings2 className="mr-2 h-4 w-4" /> Change Status
                                </DropdownMenuItem>
                                {notice.status !== 'fulfilled' && notice.status !== 'cancelled' && (
                                    <>
                                        <DropdownMenuSeparator />
                                        <AlertDialog>
                                            <AlertDialogTrigger asChild>
                                                <DropdownMenuItem className="text-destructive focus:text-destructive focus:bg-destructive/10" onSelect={(e) => e.preventDefault()} disabled={isSubmitting}>
                                                    <Trash2 className="mr-2 h-4 w-4"/> Cancel Notice
                                                </DropdownMenuItem>
                                            </AlertDialogTrigger>
                                            <AlertDialogContent>
                                                <AlertDialogHeader><AlertDialogTitle>Cancel Demand Notice?</AlertDialogTitle></AlertDialogHeader>
                                                <AlertDialogDescription>Cancel notice {notice.id} for {notice.productName}?</AlertDialogDescription>
                                                <AlertDialogFooter>
                                                    <AlertDialogCancel disabled={isSubmitting}>Back</AlertDialogCancel>
                                                    <AlertDialogAction onClick={() => handleAdminInitiatedStatusChange(notice.id, 'cancelled')} disabled={isSubmitting} className="bg-destructive hover:bg-destructive/90">
                                                        {isSubmitting ? "Cancelling..." : "Confirm Cancel"}
                                                    </AlertDialogAction>
                                                </AlertDialogFooter>
                                            </AlertDialogContent>
                                        </AlertDialog>
                                    </>
                                )}
                            </DropdownMenuContent>
                         </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  );})}
                </TableBody>
              </Table>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

       <Dialog open={isFormOpen} onOpenChange={(isOpen) => { setIsFormOpen(isOpen); if (!isOpen) setEditingNotice(null); }}>
        <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingNotice ? `Edit Demand Notice: ${editingNotice.id}` : 'Create New Demand Notice'}</DialogTitle>
          </DialogHeader>
          <DemandNoticeForm
            notice={editingNotice}
            onSubmit={handleSubmitForm}
            onCancel={() => { setIsFormOpen(false); setEditingNotice(null); }}
            isLoading={isSubmitting}
          />
        </DialogContent>
      </Dialog>

      <Dialog open={isStatusChangeModalOpen} onOpenChange={(isOpen) => {
        if (!isOpen) {
          setSelectedNoticeForStatusChange(null);
          setNewSelectedStatus('');
        }
        setIsStatusChangeModalOpen(isOpen);
      }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Change Status for Notice: {selectedNoticeForStatusChange?.id}</DialogTitle>
          </DialogHeader>
          {selectedNoticeForStatusChange && (
            <div className="py-4 space-y-4">
              <div className="text-sm">Current Status: <Badge variant="outline">{selectedNoticeForStatusChange.status.replace(/_/g, ' ')}</Badge></div>
              <div>
                <Label htmlFor="new-status-select">New Status</Label>
                <Select
                  value={newSelectedStatus}
                  onValueChange={(value) => setNewSelectedStatus(value as DemandNoticeStatus)}
                >
                  <SelectTrigger id="new-status-select">
                    <SelectValue placeholder="Select new status" />
                  </SelectTrigger>
                  <SelectContent>
                    {DEMAND_NOTICE_STATUSES_WORKFLOW.map(status => (
                      <SelectItem key={status} value={status} className="capitalize">
                        {status.replace(/_/g, ' ')}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsStatusChangeModalOpen(false)} disabled={isSubmitting}>Cancel</Button>
            <Button
              onClick={() => selectedNoticeForStatusChange && newSelectedStatus && handleAdminInitiatedStatusChange(selectedNoticeForStatusChange.id, newSelectedStatus)}
              disabled={isSubmitting || !newSelectedStatus || newSelectedStatus === selectedNoticeForStatusChange?.status}
            >
              {isSubmitting ? "Updating..." : "Confirm Status Change"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  );
}

    