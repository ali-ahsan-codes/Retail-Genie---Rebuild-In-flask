
'use client';
import React, { useState, useMemo, useCallback, useEffect } from 'react';
import type { Order, OrderStatus, User, DeliveryStatus } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { MoreHorizontal, Eye, Edit, Trash2, Filter, Archive, Search, Users as UsersIcon, Percent, RotateCw, Tag, ShieldAlert, Undo2, Truck } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { format, parseISO, isValid } from 'date-fns';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator, DropdownMenuLabel } from '@/components/ui/dropdown-menu';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Dialog, DialogClose, DialogContent as FormDialogContent, DialogDescription as FormDialogDescription, DialogFooter as FormDialogFooter, DialogHeader as FormDialogHeader, DialogTitle as FormDialogTitle, DialogTrigger as DialogFormTrigger } from "@/components/ui/dialog";
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { deleteOrderFromDb, updateOrderInDb, getOrderByIdFromDb } from '@/lib/database'; 
import Link from 'next/link'; 
import { ALL_ORDER_STATUSES_FOR_FILTERING } from '@/lib/constants';

const ALL_DELIVERY_STATUSES: DeliveryStatus[] = ['pending_dispatch', 'out_for_delivery', 'delivered', 'delivery_failed', 'pickup_ready'];
const NONE_SALESPERSON_VALUE = "--NONE--"; 

interface MemoizedOrderRowProps {
  order: Order;
  isSubmitting: boolean;
  canManageOrders: boolean;
  canManageReturns: boolean;
  canManageLogistics: boolean;
  salespeople: User[];
  onUpdateStatus: (orderId: string, newStatus: OrderStatus) => void;
  onUpdateDeliveryStatus: (orderId: string, newStatus: DeliveryStatus) => void;
  onDeleteOrder: (orderId: string) => void;
  onOpenAttributionModal: (order: Order) => void;
  onOpenDiscountModal: (order: Order) => void;
  onOpenTransferModal: (order: Order) => void;
  getOrderStatusBadge: (status: Order['status']) => JSX.Element;
  getDeliveryStatusBadge: (status?: DeliveryStatus) => JSX.Element;
}

const MemoizedOrderRow = React.memo(function MemoizedOrderRow({
  order, isSubmitting, canManageOrders, canManageReturns, canManageLogistics, salespeople,
  onUpdateStatus, onUpdateDeliveryStatus, onDeleteOrder, onOpenAttributionModal, onOpenDiscountModal, onOpenTransferModal,
  getOrderStatusBadge, getDeliveryStatusBadge
}: MemoizedOrderRowProps) {
  
  const formattedCreatedAt = useMemo(() => {
    try {
      const date = parseISO(order.createdAt);
      return isValid(date) ? format(date, "MM/dd/yyyy HH:mm") : "Invalid Date";
    } catch (e) {
      return "Invalid Date";
    }
  }, [order.createdAt]);

  const formattedUpdatedAt = useMemo(() => {
    try {
      const date = parseISO(order.updatedAt);
      return isValid(date) ? format(date, "MM/dd/yyyy p") : "Invalid Date";
    } catch (e) {
      return "Invalid Date";
    }
  }, [order.updatedAt]);

  return (
    <AccordionItem value={order.id} className="border rounded-lg shadow-sm bg-card">
      <div className="flex items-center p-4 data-[state=open]:border-b">
        <AccordionTrigger className="flex-1 p-0 hover:no-underline data-[state=open]:border-0 rounded-none">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center w-full gap-2">
            <div className="flex-1">
              <h3 className="font-semibold text-primary text-lg">{order.id}</h3>
              <p className="text-sm text-muted-foreground">
                By: {order.primarySalespersonName} 
                {order.secondarySalespersonName && ` & ${order.secondarySalespersonName}`}
                {' '} on {formattedCreatedAt}
              </p>
            </div>
            <div className="flex items-center gap-2 md:gap-4 text-sm flex-wrap">
              {getOrderStatusBadge(order.status)}
              {getDeliveryStatusBadge(order.deliveryStatus)}
              <span className="font-bold text-base">OMR {order.totalAmount.toFixed(2)}</span>
            </div>
          </div>
        </AccordionTrigger>

        <div className="flex-shrink-0 pl-3">
            <AlertDialog> 
                <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8 p-0" disabled={isSubmitting || (!canManageOrders && !canManageReturns && !canManageLogistics)}>
                    <MoreHorizontal className="h-5 w-5" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    <DropdownMenuLabel>Actions</DropdownMenuLabel><ScrollArea className="h-48 overflow-y-auto">
                    {canManageOrders && (
                        <>
                            <DropdownMenuSeparator />
                            <DropdownMenuLabel>Change Order Status</DropdownMenuLabel>
                            {ALL_ORDER_STATUSES_FOR_FILTERING.filter(s => s !== order.status && s !== 'returned').map(newStatus => (
                            <DropdownMenuItem key={`order-${order.id}-${newStatus}`} onClick={() => onUpdateStatus(order.id, newStatus)} disabled={isSubmitting}>
                                Set to {newStatus.replace(/_/g, ' ')}
                            </DropdownMenuItem>
                            ))}
                            <DropdownMenuSeparator />
                            <DialogFormTrigger asChild>
                                <DropdownMenuItem onClick={() => onOpenAttributionModal(order)} disabled={isSubmitting}>
                                <UsersIcon className="mr-2 h-4 w-4" /> Edit Sales Attribution
                                </DropdownMenuItem>
                            </DialogFormTrigger>
                             <DialogFormTrigger asChild>
                                <DropdownMenuItem onClick={() => onOpenTransferModal(order)} disabled={isSubmitting}>
                                <RotateCw className="mr-2 h-4 w-4" /> Transfer Order
                                </DropdownMenuItem>
                            </DialogFormTrigger>
                            <DialogFormTrigger asChild>
                                <DropdownMenuItem onClick={() => onOpenDiscountModal(order)} disabled={isSubmitting}>
                                <Tag className="mr-2 h-4 w-4" /> Set/Edit Discount
                                </DropdownMenuItem>
                            </DialogFormTrigger>
                            <DropdownMenuSeparator />
                            <AlertDialogTrigger asChild>
                            <DropdownMenuItem className="text-destructive focus:text-destructive focus:bg-destructive/10" disabled={isSubmitting}>
                                <Trash2 className="mr-2 h-4 w-4" /> Delete Order
                            </DropdownMenuItem>
                            </AlertDialogTrigger>
                        </>
                    )}
                    {canManageLogistics && (
                       <>
                        <DropdownMenuSeparator />
                        <DropdownMenuLabel>Change Delivery Status</DropdownMenuLabel>
                         {ALL_DELIVERY_STATUSES.filter(s => s !== order.deliveryStatus).map(newStatus => (
                            <DropdownMenuItem key={`delivery-${order.id}-${newStatus}`} onClick={() => onUpdateDeliveryStatus(order.id, newStatus)} disabled={isSubmitting}>
                                Set to {newStatus.replace(/_/g, ' ')}
                            </DropdownMenuItem>
                            ))}
                       </>
                    )}
                      {canManageReturns && (order.status === 'paid' || order.status === 'completed' || order.status === 'partial_payment') && (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem asChild disabled={isSubmitting} className="text-orange-600 focus:text-orange-700 focus:bg-orange-100">
                            <Link href={`/admin/returns/${order.id}`}>
                                <Undo2 className="mr-2 h-4 w-4" /> Process Return/Exchange
                            </Link>
                          </DropdownMenuItem>
                        </>
                    )}
                    {!canManageOrders && !canManageReturns && !canManageLogistics && <DropdownMenuItem disabled>No actions available</DropdownMenuItem>}
                    </ScrollArea>
                </DropdownMenuContent>
                </DropdownMenu>

                  <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                        <AlertDialogDescription>
                        This action cannot be undone. This will permanently delete order {order.id}.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel disabled={isSubmitting}>Cancel</AlertDialogCancel>
                        <AlertDialogAction onClick={() => onDeleteOrder(order.id)} className="bg-destructive hover:bg-destructive/90" disabled={isSubmitting}>
                        {isSubmitting ? "Deleting..." : "Delete"}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
      </div>
      <AccordionContent className="p-0">
        <div className="p-4">
          <h4 className="font-medium mb-2">Order Items:</h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead className="text-center">Qty</TableHead>
                <TableHead className="text-right">Unit Price</TableHead>
                <TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(Array.isArray(order.items) ? order.items : []).map((item, index) => (
                <TableRow key={`${order.id}-item-${item.productId}-${index}`}>
                  <TableCell className="font-medium">{item.name}</TableCell>
                  <TableCell>{item.sku}</TableCell>
                  <TableCell className="text-center">{item.quantity}</TableCell>
                  <TableCell className="text-right">OMR {item.pricePerUnit.toFixed(2)}</TableCell>
                  <TableCell className="text-right">OMR {item.totalPrice.toFixed(2)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Separator className="my-4" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
                <h5 className="font-semibold mb-1">Summary:</h5>
                <p>Subtotal: OMR {order.subtotal.toFixed(2)}</p>
                {order.discountAmount > 0 && (
                    <p>Discount: -OMR {order.discountAmount.toFixed(2)} 
                        {order.appliedDiscountPercentage ? ` (${order.appliedDiscountPercentage}%)` 
                        : order.appliedGlobalDiscountPercentage ? ` (${order.appliedGlobalDiscountPercentage}% Global)` 
                        : ''}
                    </p>
                )}
                {(Array.isArray(order.taxes) ? order.taxes : []).map(tax => <p key={`${order.id}-tax-${tax.name}`}>{tax.name} ({(tax.rate*100).toFixed(0)}%): OMR {tax.amount.toFixed(2)}</p>)}
                <p className="font-bold mt-1">Total: OMR {order.totalAmount.toFixed(2)}</p>
            </div>
            <div>
                <h5 className="font-semibold mb-1">Payments:</h5>
                {(Array.isArray(order.payments) && order.payments.length > 0) ? order.payments.map((p, idx) => (
                    <p key={`${order.id}-payment-${idx}`} className="capitalize">{p.method.replace(/_/g, ' ')}: OMR {p.amount.toFixed(2)}</p>
                )) : <p className="text-muted-foreground">No payments recorded.</p>}
            </div>
            <div>
                <h5 className="font-semibold mb-1">Sales Attribution:</h5>
                <p>{order.primarySalespersonName}: {((order.primarySalespersonCommission ?? 1) * 100).toFixed(0)}%</p>
                {order.secondarySalespersonId && order.secondarySalespersonName && 
                    <p>{order.secondarySalespersonName}: {((order.secondarySalespersonCommission ?? 0) * 100).toFixed(0)}%</p>
                }
            </div>
             {order.deliveryAddress && (
                <div>
                    <h5 className="font-semibold mb-1">Delivery:</h5>
                    <p>To: {order.customerName} ({order.customerPhone})</p>
                    <p>Address: {order.deliveryAddress}</p>
                </div>
            )}
            {(Array.isArray(order.returnTransactions) && order.returnTransactions.length > 0) && (
              <div className="md:col-span-2 mt-2">
                <h5 className="font-semibold mb-1 text-orange-600">Return/Exchange History:</h5>
                {order.returnTransactions.map(rt => {
                    const formattedReturnedAt = isValid(parseISO(rt.returnedAt)) ? format(parseISO(rt.returnedAt), 'MM/dd/yyyy p') : "Invalid Date";
                    return (
                        <div key={`${order.id}-return-${rt.id}`} className="text-xs border-l-2 border-orange-400 pl-2 mb-2">
                            <p>Processed: {formattedReturnedAt} by {rt.processedByUsername}</p>
                            <p>Returned Items Value: OMR {rt.totalValueOfReturnedItems.toFixed(2)}</p>
                            <p>Net Refund/Payment: OMR {rt.netRefundAmount.toFixed(2)} via {(Array.isArray(rt.refundPaymentDetails) ? rt.refundPaymentDetails : []).map(p => p.method).join(', ')}</p>
                            {rt.notesOnExchange && <p>Exchange Notes: {rt.notesOnExchange}</p>}
                            {rt.returnReasonGeneral && <p>Reason: {rt.returnReasonGeneral}</p>}
                        </div>
                    )
                })}
              </div>
            )}
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
MemoizedOrderRow.displayName = 'MemoizedOrderRow';


export default function AdminOrdersPage() {
  const { 
    orders: contextOrders, 
    users, 
    updateOrderStatus, 
    loadDataFromDb, 
    transferOrder, 
    getOrderById, 
    hasPermission, 
    updateProductStock,
    updateOrderDeliveryStatus
  } = useApp();
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<OrderStatus | 'all'>('all');
  const [localOrders, setLocalOrders] = useState<Order[]>([]);

  const [isAttributionModalOpen, setIsAttributionModalOpen] = useState(false);
  const [selectedOrderForAttribution, setSelectedOrderForAttribution] = useState<Order | null>(null);
  const [primarySalesperson, setPrimarySalesperson] = useState<string>(NONE_SALESPERSON_VALUE);
  const [secondarySalesperson, setSecondarySalesperson] = useState<string>(NONE_SALESPERSON_VALUE); 
  const [primaryCommission, setPrimaryCommission] = useState<number>(100);
  const [secondaryCommission, setSecondaryCommission] = useState<number>(0);

  const [isDiscountModalOpen, setIsDiscountModalOpen] = useState(false);
  const [selectedOrderForDiscount, setSelectedOrderForDiscount] = useState<Order | null>(null);
  const [adminDiscountPercentageInput, setAdminDiscountPercentageInput] = useState('0');
  
  const [isTransferModalOpen, setIsTransferModalOpen] = useState(false);
  const [selectedOrderForTransfer, setSelectedOrderForTransfer] = useState<Order | null>(null);
  const [newPrimarySalespersonForTransfer, setNewPrimarySalespersonForTransfer] = useState<string>(NONE_SALESPERSON_VALUE);
  const [newSecondarySalespersonForTransfer, setNewSecondarySalespersonForTransfer] = useState<string>(NONE_SALESPERSON_VALUE);
  const [transferPrimaryCommission, setTransferPrimaryCommission] = useState<number>(100);
  const [transferSecondaryCommission, setTransferSecondaryCommission] = useState<number>(0);


  const canManageOrders = hasPermission('manage_orders');
  const canManageReturns = hasPermission('manage_returns');
  const canManageLogistics = hasPermission('manage_logistics'); 

  useEffect(() => {
    setLocalOrders(contextOrders.sort((a,b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()));
  }, [contextOrders]);

  const salespeople = useMemo(() => users.filter(u => u.role === 'salesperson'), [users]);

  const filteredOrders = useMemo(() => {
    return localOrders
      .filter(order => {
        const itemsArray = Array.isArray(order.items) ? order.items : [];
        const trimmedSearchTerm = searchTerm.trim();
        const termIsShortNumeric = /^\d{2,4}$/.test(trimmedSearchTerm);

        const idMatch = order.id.toLowerCase().includes(trimmedSearchTerm.toLowerCase()) ||
                        (termIsShortNumeric && order.id.endsWith(trimmedSearchTerm));
        
        const searchMatch = idMatch ||
                             order.primarySalespersonName.toLowerCase().includes(trimmedSearchTerm.toLowerCase()) ||
                             (order.secondarySalespersonName && order.secondarySalespersonName.toLowerCase().includes(trimmedSearchTerm.toLowerCase())) ||
                             (order.customerName && order.customerName.toLowerCase().includes(trimmedSearchTerm.toLowerCase())) ||
                             itemsArray.some(item => item.name.toLowerCase().includes(trimmedSearchTerm.toLowerCase()));
        const statusMatch = statusFilter === 'all' || order.status === statusFilter;
        return searchMatch && statusMatch;
      });
  }, [localOrders, searchTerm, statusFilter]);

  const getOrderStatusBadge = useCallback((status: Order['status']) => {
    switch (status) {
      case 'pending_payment': return <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">Pending Payment</Badge>;
      case 'partial_payment': return <Badge variant="outline" className="bg-orange-100 text-orange-700 border-orange-300">Partial Payment</Badge>;
      case 'preparing': return <Badge variant="outline" className="bg-blue-100 text-blue-700 border-blue-300">Preparing</Badge>;
      case 'ready_for_pickup': return <Badge variant="default" className="bg-purple-100 text-purple-700 border-purple-300">Ready for Pickup</Badge>;
      case 'paid': return <Badge variant="default" className="bg-green-100 text-green-700 border-green-300">Paid</Badge>;
      case 'completed': return <Badge variant="default" className="bg-emerald-500 text-white">Completed</Badge>;
      case 'cancelled': return <Badge variant="destructive">Cancelled</Badge>;
      case 'returned': return <Badge variant="outline" className="bg-orange-100 text-orange-700 border-orange-300">Returned</Badge>;
      default: return <Badge variant="secondary">{status.replace(/_/g, ' ')}</Badge>;
    }
  }, []);

  const getDeliveryStatusBadge = useCallback((status?: DeliveryStatus) => {
    if (!status) return null;
    switch (status) {
      case 'pending_dispatch': return <Badge variant="outline" className="bg-gray-200 text-gray-700 border-gray-300">Pending Dispatch</Badge>;
      case 'out_for_delivery': return <Badge variant="outline" className="bg-sky-100 text-sky-700 border-sky-300">Out for Delivery</Badge>;
      case 'delivered': return <Badge variant="default" className="bg-teal-100 text-teal-700 border-teal-300">Delivered</Badge>;
      case 'delivery_failed': return <Badge variant="destructive" className="bg-red-200 text-red-700 border-red-300">Delivery Failed</Badge>;
      case 'pickup_ready': return <Badge variant="default" className="bg-indigo-100 text-indigo-700 border-indigo-300">Ready for Pickup (Logistics)</Badge>;
      default: return <Badge variant="secondary">{status.replace(/_/g, ' ')}</Badge>;
    }
  }, []);

  const handleUpdateStatus = useCallback(async (orderId: string, newStatus: OrderStatus) => {
    if (!canManageOrders) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to update order status.', variant: 'destructive' });
      return;
    }
    setIsSubmitting(true);
    try {
      await updateOrderStatus(orderId, newStatus); 
      toast({ title: 'Order Status Updated', description: `Order ${orderId} is now ${newStatus.replace(/_/g, ' ')}.` });
    } catch (error) {
      console.error("Error updating order status:", error);
      toast({ title: 'Error', description: 'Could not update order status.', variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  }, [canManageOrders, updateOrderStatus, toast]);

  const handleUpdateDeliveryStatus = useCallback(async (orderId: string, newStatus: DeliveryStatus) => {
    if (!canManageLogistics && !canManageOrders) { 
      toast({ title: 'Permission Denied', description: 'You do not have permission to update delivery status.', variant: 'destructive' });
      return;
    }
    setIsSubmitting(true);
    try {
      await updateOrderDeliveryStatus(orderId, newStatus);
      toast({ title: 'Delivery Status Updated', description: `Order ${orderId} delivery status is now ${newStatus.replace(/_/g, ' ')}.` });
    } catch (error) {
      console.error("Error updating delivery status:", error);
      toast({ title: 'Error', description: 'Could not update delivery status.', variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  }, [canManageLogistics, canManageOrders, updateOrderDeliveryStatus, toast]);

  const handleDeleteOrder = useCallback(async (orderId: string) => {
    if (!canManageOrders) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to delete orders.', variant: 'destructive' });
      return;
    }
    setIsSubmitting(true);
    try {
      await deleteOrderFromDb(orderId); 
      await loadDataFromDb(); 
      toast({ title: 'Order Deleted', description: `Order ${orderId} has been removed.`, variant: 'destructive' });
    } catch (error) {
      console.error("Error deleting order:", error);
      toast({ title: 'Error', description: 'Could not delete order.', variant: 'destructive' });
    } finally {
      setIsSubmitting(false);
    }
  }, [canManageOrders, loadDataFromDb, toast]);

  const openAttributionModal = useCallback((order: Order) => {
    if (!canManageOrders) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to edit sales attribution.', variant: 'destructive' });
      return;
    }
    setSelectedOrderForAttribution(order);
    setPrimarySalesperson(order.primarySalespersonId);
    setSecondarySalesperson(order.secondarySalespersonId || NONE_SALESPERSON_VALUE); 
    setPrimaryCommission(order.primarySalespersonCommission !== undefined ? order.primarySalespersonCommission * 100 : 100);
    setSecondaryCommission(order.secondarySalespersonCommission !== undefined ? order.secondarySalespersonCommission * 100 : 0);
    setIsTransferModalOpen(false); 
    setIsDiscountModalOpen(false);
    setIsAttributionModalOpen(true);
  }, [canManageOrders, toast]);
  
  const openDiscountModal = useCallback((order: Order) => {
    if (!canManageOrders) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to set discounts.', variant: 'destructive' });
      return;
    }
    setSelectedOrderForDiscount(order);
    setAdminDiscountPercentageInput((order.appliedDiscountPercentage || 0).toString());
    setIsTransferModalOpen(false); 
    setIsAttributionModalOpen(false);
    setIsDiscountModalOpen(true);
  }, [canManageOrders, toast]);

  const openTransferModal = useCallback((order: Order) => {
    if (!canManageOrders) {
        toast({ title: 'Permission Denied', description: 'You do not have permission to transfer orders.', variant: 'destructive'});
        return;
    }
    setSelectedOrderForTransfer(order);
    setNewPrimarySalespersonForTransfer(order.primarySalespersonId);
    setNewSecondarySalespersonForTransfer(order.secondarySalespersonId || NONE_SALESPERSON_VALUE);
    setTransferPrimaryCommission(order.primarySalespersonCommission !== undefined ? order.primarySalespersonCommission * 100 : 100);
    setTransferSecondaryCommission(order.secondarySalespersonCommission !== undefined ? order.secondarySalespersonCommission * 100 : 0);
    setIsAttributionModalOpen(false);
    setIsDiscountModalOpen(false);
    setIsTransferModalOpen(true);
  }, [canManageOrders, toast]);


  const handleAdminSetDiscount = useCallback(async () => {
    if (!canManageOrders || !selectedOrderForDiscount) {
      toast({ title: 'Error', description: 'Action not permitted or no order selected.', variant: 'destructive' });
      return;
    }
    const percentage = parseFloat(adminDiscountPercentageInput);
    if (isNaN(percentage) || percentage < 0 || percentage > 100) {
      toast({ title: "Error", description: "Please enter a valid discount percentage (0-100).", variant: "destructive" });
      return;
    }

    setIsSubmitting(true);
    try {
      const orderToUpdate = await getOrderByIdFromDb(selectedOrderForDiscount.id); 
      if (!orderToUpdate) throw new Error("Order not found for discount update.");

      const newDiscountAmount = orderToUpdate.subtotal * (percentage / 100);
      const taxesArray = Array.isArray(orderToUpdate.taxes) ? orderToUpdate.taxes : [];
      
      const updatedOrder: Order = {
        ...orderToUpdate,
        discountAmount: newDiscountAmount,
        appliedDiscountPercentage: percentage, 
        appliedGlobalDiscountPercentage: undefined, 
        totalAmount: orderToUpdate.subtotal - newDiscountAmount + taxesArray.reduce((sum, tax) => sum + tax.amount, 0), 
        updatedAt: new Date().toISOString(),
      };
      
      await updateOrderInDb(updatedOrder); 
      await loadDataFromDb(); 
      toast({ title: "Discount Updated", description: `Manual discount set to ${percentage}% for order ${selectedOrderForDiscount.id}.` });
      setIsDiscountModalOpen(false);
      setSelectedOrderForDiscount(null);
    } catch (error) {
      console.error("Error setting discount:", error);
      toast({ title: "Error", description: "Could not set discount.", variant: "destructive" });
    } finally {
      setIsSubmitting(false);
    }
  }, [canManageOrders, selectedOrderForDiscount, adminDiscountPercentageInput, loadDataFromDb, toast]);


  const handleUpdateSalesAttribution = useCallback(async () => {
    if (!canManageOrders || !selectedOrderForAttribution || primarySalesperson === NONE_SALESPERSON_VALUE) {
      toast({ title: "Error", description: "Primary salesperson must be selected or action not permitted.", variant: "destructive" });
      return;
    }
    if (primarySalesperson === secondarySalesperson && secondarySalesperson !== NONE_SALESPERSON_VALUE) {
        toast({ title: "Error", description: "Primary and secondary salesperson cannot be the same.", variant: "destructive"});
        return;
    }
    const totalCommission = primaryCommission + (secondarySalesperson !== NONE_SALESPERSON_VALUE ? secondaryCommission : 0);
    if (secondarySalesperson !== NONE_SALESPERSON_VALUE && totalCommission !== 100) { 
        toast({ title: "Error", description: "Total commission for primary and secondary salesperson must be 100%.", variant: "destructive"});
        return;
    }
    
    setIsSubmitting(true);
    try {
      await transferOrder( 
        selectedOrderForAttribution.id,
        primarySalesperson,
        secondarySalesperson === NONE_SALESPERSON_VALUE ? undefined : secondarySalesperson,
        { 
          primary: primaryCommission / 100, 
          secondary: secondarySalesperson !== NONE_SALESPERSON_VALUE ? secondaryCommission / 100 : 0 
        }
      );
      toast({ title: "Sales Attribution Updated", description: `Attribution for order ${selectedOrderForAttribution.id} has been updated.` });
      setIsAttributionModalOpen(false);
      setSelectedOrderForAttribution(null);
    } catch (error) {
      console.error("Error updating sales attribution:", error);
      toast({ title: "Error", description: "Could not update sales attribution.", variant: "destructive" });
    } finally {
      setIsSubmitting(false);
    }
  }, [canManageOrders, selectedOrderForAttribution, primarySalesperson, secondarySalesperson, primaryCommission, secondaryCommission, transferOrder, toast]);

  const handleTransferOrder = useCallback(async () => {
    if (!canManageOrders || !selectedOrderForTransfer || newPrimarySalespersonForTransfer === NONE_SALESPERSON_VALUE) {
      toast({ title: "Error", description: "Primary salesperson must be selected for transfer or action not permitted.", variant: "destructive" });
      return;
    }
     if (newPrimarySalespersonForTransfer === newSecondarySalespersonForTransfer && newSecondarySalespersonForTransfer !== NONE_SALESPERSON_VALUE) {
        toast({ title: "Error", description: "Primary and secondary salesperson cannot be the same.", variant: "destructive"});
        return;
    }
    const totalCommission = transferPrimaryCommission + (newSecondarySalespersonForTransfer !== NONE_SALESPERSON_VALUE ? transferSecondaryCommission : 0);
    if (newSecondarySalespersonForTransfer !== NONE_SALESPERSON_VALUE && totalCommission !== 100) { 
        toast({ title: "Error", description: "Total commission for primary and secondary salesperson must be 100%.", variant: "destructive"});
        return;
    }

    setIsSubmitting(true);
    try {
        await transferOrder(
            selectedOrderForTransfer.id,
            newPrimarySalespersonForTransfer,
            newSecondarySalespersonForTransfer === NONE_SALESPERSON_VALUE ? undefined : newSecondarySalespersonForTransfer,
            { 
                primary: transferPrimaryCommission / 100, 
                secondary: newSecondarySalespersonForTransfer !== NONE_SALESPERSON_VALUE ? transferSecondaryCommission / 100 : 0 
            }
        );
        toast({ title: "Order Transferred", description: `Order ${selectedOrderForTransfer.id} attribution has been updated.`});
        setIsTransferModalOpen(false);
        setSelectedOrderForTransfer(null);
    } catch (error) {
        console.error("Error transferring order:", error);
        toast({ title: "Transfer Error", description: "Could not transfer order.", variant: "destructive" });
    } finally {
        setIsSubmitting(false);
    }
  }, [canManageOrders, selectedOrderForTransfer, newPrimarySalespersonForTransfer, newSecondarySalespersonForTransfer, transferPrimaryCommission, transferSecondaryCommission, transferOrder, toast]);


  const closeModals = useCallback(() => {
    setIsAttributionModalOpen(false);
    setSelectedOrderForAttribution(null);
    setIsDiscountModalOpen(false);
    setSelectedOrderForDiscount(null);
    setIsTransferModalOpen(false);
    setSelectedOrderForTransfer(null);
  }, []);

  if (!canManageOrders && !hasPermission('view_admin_dashboard') && !canManageLogistics) { 
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to view or manage orders.</p>
      </div>
    );
  }


  return (
    <Dialog onOpenChange={(isOpen) => { if (!isOpen) closeModals(); }}>
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center"><Archive className="mr-2 h-7 w-7 text-primary" />All Orders</CardTitle>
          <CardDescription>View, manage, and track all customer orders.</CardDescription>
          <div className="flex flex-col md:flex-row gap-4 mt-4">
            <div className="relative flex-grow">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <Input
                type="search"
                placeholder="Search by Invoice ID, Salesperson, Customer, Product..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 h-10 w-full"
              />
            </div>
            <div className="flex items-center gap-2">
                <Filter className="h-5 w-5 text-muted-foreground" />
                <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as OrderStatus | 'all')}>
                    <SelectTrigger className="w-full md:w-[200px] h-10">
                        <SelectValue placeholder="Filter by status" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">All Order Statuses</SelectItem>
                        {ALL_ORDER_STATUSES_FOR_FILTERING.map(status => (
                        <SelectItem key={status} value={status} className="capitalize">{status.replace(/_/g, ' ')}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>
          </div>
        </CardHeader>
      </Card>

      {filteredOrders.length === 0 ? (
        <Card>
            <CardContent className="p-8 text-center">
            <Archive className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-xl font-semibold">No orders found.</p>
            <p className="text-muted-foreground">
                {searchTerm || statusFilter !== 'all' ? "Try adjusting your search or filter." : "There are no orders in the system yet."}
            </p>
            </CardContent>
        </Card>
      ) : (
        <ScrollArea className="h-[calc(100vh-theme(spacing.64))]"> 
        <Accordion type="multiple" className="w-full space-y-4">
          {filteredOrders.map((order) => (
            <MemoizedOrderRow
              key={order.id + "-admin-order-row"} 
              order={order}
              isSubmitting={isSubmitting}
              canManageOrders={canManageOrders}
              canManageReturns={canManageReturns}
              canManageLogistics={canManageLogistics}
              salespeople={salespeople}
              onUpdateStatus={handleUpdateStatus}
              onUpdateDeliveryStatus={handleUpdateDeliveryStatus}
              onDeleteOrder={handleDeleteOrder}
              onOpenAttributionModal={openAttributionModal}
              onOpenDiscountModal={openDiscountModal}
              onOpenTransferModal={openTransferModal}
              getOrderStatusBadge={getOrderStatusBadge}
              getDeliveryStatusBadge={getDeliveryStatusBadge}
            />
          ))}
        </Accordion>
        </ScrollArea>
      )}
      {isAttributionModalOpen && selectedOrderForAttribution && (
        <FormDialogContent className="sm:max-w-md">
          <FormDialogHeader>
            <FormDialogTitle>Edit Sales Attribution: {selectedOrderForAttribution.id}</FormDialogTitle>
            <FormDialogDescription>
              Assign this order to a primary salesperson and optionally a secondary salesperson with commission splits.
            </FormDialogDescription>
          </FormDialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="primary-salesperson" className="flex items-center mb-1">
                <UsersIcon className="mr-2 h-4 w-4 text-muted-foreground" /> Primary Salesperson
              </Label>
              <Select value={primarySalesperson} onValueChange={setPrimarySalesperson} disabled={!canManageOrders}>
                <SelectTrigger id="primary-salesperson">
                  <SelectValue placeholder="Select primary salesperson" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_SALESPERSON_VALUE} disabled>Select primary salesperson</SelectItem>
                  {salespeople.map(sp => (
                    <SelectItem key={`${sp.id}-primary-attr`} value={sp.id} disabled={sp.id === secondarySalesperson && secondarySalesperson !== NONE_SALESPERSON_VALUE}>{sp.username}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="primary-commission" className="flex items-center mb-1">
                  <Percent className="mr-2 h-4 w-4 text-muted-foreground" /> Primary Commission (%)
              </Label>
              <Input 
                  id="primary-commission" 
                  type="number" 
                  value={primaryCommission} 
                  onChange={(e) => setPrimaryCommission(Math.max(0, Math.min(100, Number(e.target.value))))} 
                  min="0" max="100"
                  disabled={secondarySalesperson === NONE_SALESPERSON_VALUE || !canManageOrders} 
              />
            </div>
            <div>
              <Label htmlFor="secondary-salesperson" className="flex items-center mb-1">
                <UsersIcon className="mr-2 h-4 w-4 text-muted-foreground" /> Secondary Salesperson (Optional)
              </Label>
              <Select 
                  value={secondarySalesperson} 
                  onValueChange={(value) => {
                      setSecondarySalesperson(value);
                      if (value === NONE_SALESPERSON_VALUE) { 
                          setPrimaryCommission(100);
                          setSecondaryCommission(0);
                      } else { 
                          if (primaryCommission === 100 || (primaryCommission + secondaryCommission !== 100)){
                              setPrimaryCommission(50); 
                              setSecondaryCommission(50);
                          }
                      }
                  }}
                  disabled={!canManageOrders}>
                <SelectTrigger id="secondary-salesperson">
                  <SelectValue placeholder="Select secondary salesperson" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE_SALESPERSON_VALUE}>None</SelectItem>
                  {salespeople.map(sp => (
                    <SelectItem key={`${sp.id}-secondary-attr`} value={sp.id} disabled={sp.id === primarySalesperson && primarySalesperson !== NONE_SALESPERSON_VALUE}>{sp.username}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {secondarySalesperson !== NONE_SALESPERSON_VALUE && (
              <div>
                  <Label htmlFor="secondary-commission" className="flex items-center mb-1">
                      <Percent className="mr-2 h-4 w-4 text-muted-foreground" /> Secondary Commission (%)
                  </Label>
                  <Input 
                      id="secondary-commission" 
                      type="number" 
                      value={secondaryCommission} 
                      onChange={(e) => setSecondaryCommission(Math.max(0, Math.min(100, Number(e.target.value))))} 
                      min="0" max="100"
                      disabled={!canManageOrders}
                  />
              </div>
            )}
          </div>
          <FormDialogFooter>
            <DialogClose asChild><Button type="button" variant="outline" disabled={isSubmitting}>Cancel</Button></DialogClose>
            <Button 
              type="button" 
              onClick={handleUpdateSalesAttribution} 
              disabled={isSubmitting || !canManageOrders || primarySalesperson === NONE_SALESPERSON_VALUE || (secondarySalesperson !== NONE_SALESPERSON_VALUE && (primaryCommission + secondaryCommission !== 100))}>
              {isSubmitting ? "Saving..." : "Confirm Attribution"}
            </Button>
          </FormDialogFooter>
        </FormDialogContent>
      )}
      {isDiscountModalOpen && selectedOrderForDiscount && (
        <FormDialogContent className="sm:max-w-xs">
            <FormDialogHeader>
                <FormDialogTitle>Set Discount for Order: {selectedOrderForDiscount.id}</FormDialogTitle>
                <FormDialogDescription>
                Apply a percentage-based discount to this order. This will update the order's discount amount and override any global discount.
                </FormDialogDescription>
            </FormDialogHeader>
            <div className="space-y-4 py-4">
                <div>
                    <Label htmlFor="admin-discount-percentage" className="flex items-center mb-1">
                        <Tag className="mr-2 h-4 w-4 text-muted-foreground" /> Discount Percentage (%)
                    </Label>
                    <Input 
                        id="admin-discount-percentage" 
                        type="number" 
                        value={adminDiscountPercentageInput} 
                        onChange={(e) => setAdminDiscountPercentageInput(e.target.value)} 
                        min="0" max="100" step="0.01"
                        placeholder="e.g. 10 for 10%"
                        disabled={!canManageOrders}
                    />
                </div>
                  <>
                    <p className="text-sm text-muted-foreground">
                        Order Subtotal: OMR {selectedOrderForDiscount.subtotal.toFixed(2)}
                    </p>
                    {selectedOrderForDiscount.appliedGlobalDiscountPercentage && (
                        <p className="text-xs text-blue-600">
                          Note: A global discount of {selectedOrderForDiscount.appliedGlobalDiscountPercentage}% was initially applied. Setting a manual discount here will override it for this order.
                        </p>
                    )}
                  </>
            </div>
            <FormDialogFooter>
                <DialogClose asChild><Button type="button" variant="outline" disabled={isSubmitting}>Cancel</Button></DialogClose>
                <Button 
                type="button" 
                onClick={handleAdminSetDiscount} 
                disabled={isSubmitting || !canManageOrders}
                >
                {isSubmitting ? "Saving..." : "Apply Discount"}
                </Button>
            </FormDialogFooter>
        </FormDialogContent>
      )}
       {isTransferModalOpen && selectedOrderForTransfer && (
                <FormDialogContent className="sm:max-w-md">
                  <FormDialogHeader>
                    <FormDialogTitle>Transfer Order: {selectedOrderForTransfer.id}</FormDialogTitle>
                    <FormDialogDescription>
                      Re-assign this order to a new primary salesperson and optionally a secondary salesperson with commission splits.
                    </FormDialogDescription>
                  </FormDialogHeader>
                  <div className="space-y-4 py-4">
                     <div>
                      <Label htmlFor="transfer-primary-salesperson">New Primary Salesperson</Label>
                      <Select value={newPrimarySalespersonForTransfer} onValueChange={setNewPrimarySalespersonForTransfer} disabled={!canManageOrders}>
                        <SelectTrigger id="transfer-primary-salesperson">
                          <SelectValue placeholder="Select primary salesperson" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NONE_SALESPERSON_VALUE} disabled>Select primary salesperson</SelectItem>
                          {salespeople.map(sp => (
                            <SelectItem key={`transfer-prim-${sp.id}-${selectedOrderForTransfer.id}`} value={sp.id} disabled={sp.id === newSecondarySalespersonForTransfer && newSecondarySalespersonForTransfer !== NONE_SALESPERSON_VALUE}>{sp.username}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label htmlFor="transfer-primary-commission">New Primary Commission (%)</Label>
                      <Input 
                        id="transfer-primary-commission" 
                        type="number" 
                        value={transferPrimaryCommission} 
                        onChange={(e) => setTransferPrimaryCommission(Math.max(0, Math.min(100, Number(e.target.value))))} 
                        min="0" max="100"
                        disabled={newSecondarySalespersonForTransfer === NONE_SALESPERSON_VALUE || !canManageOrders}
                      />
                    </div>
                    <div>
                      <Label htmlFor="transfer-secondary-salesperson">New Secondary Salesperson (Optional)</Label>
                      <Select 
                        value={newSecondarySalespersonForTransfer} 
                        onValueChange={(value) => {
                          setNewSecondarySalespersonForTransfer(value);
                          if (value === NONE_SALESPERSON_VALUE) {
                            setTransferPrimaryCommission(100);
                            setTransferSecondaryCommission(0);
                          } else {
                            if(transferPrimaryCommission === 100 || (transferPrimaryCommission + transferSecondaryCommission !== 100)){
                               setTransferPrimaryCommission(50);
                               setTransferSecondaryCommission(50);
                            }
                          }
                        }}
                        disabled={!canManageOrders}
                      >
                        <SelectTrigger id="transfer-secondary-salesperson">
                          <SelectValue placeholder="Select secondary salesperson" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NONE_SALESPERSON_VALUE}>None</SelectItem>
                          {salespeople.map(sp => (
                            <SelectItem key={`transfer-sec-${sp.id}-${selectedOrderForTransfer.id}`} value={sp.id} disabled={sp.id === newPrimarySalespersonForTransfer && newPrimarySalespersonForTransfer !== NONE_SALESPERSON_VALUE}>{sp.username}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    {newSecondarySalespersonForTransfer !== NONE_SALESPERSON_VALUE && (
                      <div>
                        <Label htmlFor="transfer-secondary-commission">New Secondary Commission (%)</Label>
                        <Input 
                          id="transfer-secondary-commission" 
                          type="number" 
                          value={transferSecondaryCommission} 
                          onChange={(e) => setTransferSecondaryCommission(Math.max(0, Math.min(100, Number(e.target.value))))} 
                          min="0" max="100"
                          disabled={!canManageOrders}
                        />
                      </div>
                    )}
                  </div>
                  <FormDialogFooter>
                    <DialogClose asChild><Button variant="outline" disabled={isSubmitting}>Cancel</Button></DialogClose>
                    <Button 
                      type="button" 
                      onClick={handleTransferOrder} 
                      disabled={isSubmitting || !canManageOrders || newPrimarySalespersonForTransfer === NONE_SALESPERSON_VALUE || (newSecondarySalespersonForTransfer !== NONE_SALESPERSON_VALUE && (transferPrimaryCommission + transferSecondaryCommission !== 100))}
                    >
                      {isSubmitting ? "Transferring..." : "Confirm Transfer"}
                    </Button>
                  </FormDialogFooter>
                </FormDialogContent>
            )}
    </div>
    </Dialog>
  );
}
