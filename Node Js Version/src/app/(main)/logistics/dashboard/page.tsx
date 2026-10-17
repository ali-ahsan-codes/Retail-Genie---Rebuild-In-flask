
'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import type { Order, DeliveryStatus } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Truck, Search, Package, Phone, MessageSquare, CalendarClock, Edit3, AlertTriangle, Loader2, UserCheck } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { format } from 'date-fns';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogClose } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import Link from 'next/link';
import { Alert, AlertDescription as UIDescription, AlertTitle as UITitle } from '@/components/ui/alert';


const ALL_DELIVERY_STATUSES: DeliveryStatus[] = ['pending_dispatch', 'out_for_delivery', 'delivered', 'delivery_failed', 'pickup_ready'];

interface MemoizedLogisticsOrderRowProps {
  order: Order;
  onUpdateDeliveryStatus: (orderId: string, newStatus: DeliveryStatus) => void;
  onOpenReminderModal: (order: Order) => void;
  getDeliveryStatusBadge: (status?: DeliveryStatus) => JSX.Element;
  disabled: boolean; 
}

const MemoizedLogisticsOrderRow = React.memo(function MemoizedLogisticsOrderRow({
  order, onUpdateDeliveryStatus, onOpenReminderModal, getDeliveryStatusBadge, disabled
}: MemoizedLogisticsOrderRowProps) {
  return (
    <AccordionItem value={order.id} className="border rounded-lg shadow-sm bg-card">
      <AccordionTrigger className="p-4 hover:no-underline" disabled={disabled}>
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center w-full gap-2">
            <div className="flex-1">
              <h3 className="font-semibold text-primary text-lg">{order.id}</h3>
              <p className="text-sm text-muted-foreground">
                Customer: {order.customerName || 'N/A'} ({order.customerPhone || 'N/A'})
              </p>
                <p className="text-xs text-muted-foreground">Order Placed: {format(new Date(order.createdAt), "MMM d, yyyy HH:mm")}</p>
            </div>
            <div className="flex items-center gap-2 md:gap-4 text-sm flex-wrap">
              {getDeliveryStatusBadge(order.deliveryStatus)}
              <span className="font-bold text-base">OMR {order.totalAmount.toFixed(2)}</span>
            </div>
          </div>
      </AccordionTrigger>
      <AccordionContent className="p-0">
        <div className="p-4 space-y-4">
            <div>
                <h4 className="font-medium mb-1 text-sm">Delivery Address:</h4>
                <p className="text-sm text-muted-foreground">{order.deliveryAddress || 'Not specified'}</p>
            </div>
              <div>
                <h4 className="font-medium mb-1 text-sm">Items:</h4>
                <ul className="list-disc pl-5 text-sm text-muted-foreground">
                    {order.items.map(item => <li key={item.productId}>{item.name} (Qty: {item.quantity})</li>)}
                </ul>
            </div>
            <div className="flex flex-col sm:flex-row gap-2 items-start sm:items-center">
                <h4 className="font-medium text-sm whitespace-nowrap">Update Delivery Status:</h4>
                <Select
                    value={order.deliveryStatus || ''}
                    onValueChange={(newStatus) => onUpdateDeliveryStatus(order.id, newStatus as DeliveryStatus)}
                    disabled={disabled}
                >
                    <SelectTrigger className="w-full sm:w-[200px] h-9 text-sm">
                        <SelectValue placeholder="Set status" />
                    </SelectTrigger>
                    <SelectContent>
                        {ALL_DELIVERY_STATUSES.map(status => (
                        <SelectItem key={status} value={status} className="capitalize text-sm">{status.replace(/_/g, ' ')}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>
            <div className="flex flex-col sm:flex-row gap-2 items-start sm:items-center">
                <h4 className="font-medium text-sm whitespace-nowrap">Reminder:</h4>
                {order.reminderDate ? (
                      <Badge variant="outline" className="text-sm">
                        <CalendarClock className="h-4 w-4 mr-1.5" />
                        {format(new Date(order.reminderDate), "MMM d, yyyy HH:mm")} - {order.reminderNotes || "No notes"}
                    </Badge>
                ) : (
                    <span className="text-sm text-muted-foreground">Not set</span>
                )}
                <Button variant="outline" size="sm" onClick={() => onOpenReminderModal(order)} disabled={disabled}>
                    <Edit3 className="h-4 w-4 mr-1.5" /> {order.reminderDate ? 'Edit' : 'Set'} Reminder
                </Button>
            </div>
              <Button variant="outline" size="sm" onClick={() => window.open(`tel:${order.customerPhone || ''}`)} disabled={!order.customerPhone || disabled}>
                <Phone className="h-4 w-4 mr-1.5" /> Call Customer
              </Button>
        </div>
      </AccordionContent>
    </AccordionItem>
  );
});
MemoizedLogisticsOrderRow.displayName = "MemoizedLogisticsOrderRow";


export default function LogisticsDashboardPage() {
  const { orders, users, updateOrderDeliveryStatus, setOrderReminder, loadDataFromDb, currentUser, getTodayAttendanceForUser, isDataLoaded, isAttendanceCurrentlyRequired } = useApp();
  const { toast } = useToast();

  const [searchTerm, setSearchTerm] = useState('');
  const [deliveryFilter, setDeliveryFilter] = useState<DeliveryStatus | 'all'>('all');

  const [isReminderModalOpen, setIsReminderModalOpen] = useState(false);
  const [selectedOrderForReminder, setSelectedOrderForReminder] = useState<Order | null>(null);
  const [reminderDate, setReminderDate] = useState('');
  const [reminderNotes, setReminderNotes] = useState('');
  const [hasClockedInToday, setHasClockedInToday] = useState<boolean | null>(null);
  const [mustClockIn, setMustClockIn] = useState(false);

  useEffect(() => {
    if (currentUser && isDataLoaded) {
      const attendanceLog = getTodayAttendanceForUser(currentUser.id);
      setHasClockedInToday(!!attendanceLog);
      setMustClockIn(isAttendanceCurrentlyRequired(currentUser.role) && !attendanceLog);
    }
  }, [currentUser, getTodayAttendanceForUser, isDataLoaded, isAttendanceCurrentlyRequired]);

  const filteredOrders = useMemo(() => {
    return orders
      .filter(order => {
        const searchMatch = order.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
                             (order.customerName && order.customerName.toLowerCase().includes(searchTerm.toLowerCase())) ||
                             (order.customerPhone && order.customerPhone.includes(searchTerm));
        const statusMatch = deliveryFilter === 'all' || order.deliveryStatus === deliveryFilter;
        const relevantOrderStatus = ['paid', 'ready_for_pickup', 'completed'].includes(order.status) || order.deliveryStatus;
        return searchMatch && statusMatch && relevantOrderStatus;
      })
      .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
  }, [orders, searchTerm, deliveryFilter]);

  const getDeliveryStatusBadge = useCallback((status?: DeliveryStatus) => {
    if (!status) return <Badge variant="secondary">Unknown</Badge>;
    switch (status) {
      case 'pending_dispatch': return <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">Pending Dispatch</Badge>;
      case 'out_for_delivery': return <Badge variant="outline" className="bg-blue-100 text-blue-700 border-blue-300">Out for Delivery</Badge>;
      case 'delivered': return <Badge variant="default" className="bg-green-200 text-green-800 border-green-400">Delivered</Badge>;
      case 'delivery_failed': return <Badge variant="destructive">Delivery Failed</Badge>;
      case 'pickup_ready': return <Badge variant="default" className="bg-purple-200 text-purple-800 border-purple-400">Ready for Pickup</Badge>;
      default: return <Badge variant="secondary">{status.replace(/_/g, ' ')}</Badge>;
    }
  }, []);

  const handleUpdateDeliveryStatus = useCallback(async (orderId: string, newStatus: DeliveryStatus) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before updating delivery statuses. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    try {
      await updateOrderDeliveryStatus(orderId, newStatus);
      toast({ title: 'Delivery Status Updated', description: `Order ${orderId} is now ${newStatus.replace(/_/g, ' ')}.` });
    } catch (error) {
      console.error("Error updating delivery status:", error);
      toast({ title: 'Error', description: 'Could not update delivery status.', variant: 'destructive' });
    }
  }, [updateOrderDeliveryStatus, toast, mustClockIn]);

  const openReminderModal = useCallback((order: Order) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before setting reminders. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    setSelectedOrderForReminder(order);
    setReminderDate(order.reminderDate ? format(new Date(order.reminderDate), "yyyy-MM-dd'T'HH:mm") : '');
    setReminderNotes(order.reminderNotes || '');
    setIsReminderModalOpen(true);
  }, [mustClockIn, toast]);

  const handleSetReminder = useCallback(async () => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before setting reminders. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    if (!selectedOrderForReminder || !reminderDate) {
        toast({title: "Error", description: "Please select a date for the reminder.", variant: "destructive"});
        return;
    }
    try {
        await setOrderReminder(selectedOrderForReminder.id, new Date(reminderDate).toISOString(), reminderNotes);
        toast({title: "Reminder Set", description: `Reminder set for order ${selectedOrderForReminder.id}.`});
        setIsReminderModalOpen(false);
        setSelectedOrderForReminder(null);
    } catch (error) {
        console.error("Error setting reminder:", error);
        toast({title: "Error", description: "Could not set reminder.", variant: "destructive"});
    }
  }, [selectedOrderForReminder, reminderDate, reminderNotes, setOrderReminder, toast, mustClockIn]);

  if (!isDataLoaded || hasClockedInToday === null) {
    return (
        <div className="flex flex-col items-center justify-center h-full p-8">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading dashboard and checking attendance...</p>
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
            The mandatory attendance time has passed. You must clock in before you can access the logistics dashboard.
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
          <CardTitle className="text-2xl flex items-center"><Truck className="mr-2 h-7 w-7 text-primary" /> Order Logistics & Follow-up</CardTitle>
          <CardDescription>Track orders, update delivery statuses, and manage customer follow-ups.</CardDescription>
          <div className="flex flex-col md:flex-row gap-4 mt-4">
            <div className="relative flex-grow">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <Input
                type="search"
                placeholder="Search by Invoice ID, Customer Name/Phone..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 h-10 w-full"
                disabled={mustClockIn}
              />
            </div>
            <div className="flex items-center gap-2">
                <Truck className="h-5 w-5 text-muted-foreground" />
                <Select value={deliveryFilter} onValueChange={(value) => setDeliveryFilter(value as DeliveryStatus | 'all')} disabled={mustClockIn}>
                    <SelectTrigger className="w-full md:w-[220px] h-10">
                        <SelectValue placeholder="Filter by delivery status" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">All Delivery Statuses</SelectItem>
                        {ALL_DELIVERY_STATUSES.map(status => (
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
            <Package className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-xl font-semibold">No orders found.</p>
            <p className="text-muted-foreground">
                {searchTerm || deliveryFilter !== 'all' ? "Try adjusting your search or filter." : "There are no orders requiring logistics action currently."}
            </p>
            </CardContent>
        </Card>
      ) : (
        <ScrollArea className="h-[calc(100vh-theme(spacing.64))]">
        <Accordion type="multiple" className="w-full space-y-4">
          {filteredOrders.map((order) => (
            <MemoizedLogisticsOrderRow
              key={order.id}
              order={order}
              onUpdateDeliveryStatus={handleUpdateDeliveryStatus}
              onOpenReminderModal={openReminderModal}
              getDeliveryStatusBadge={getDeliveryStatusBadge}
              disabled={mustClockIn}
            />
          ))}
        </Accordion>
        </ScrollArea>
      )}

        <Dialog open={isReminderModalOpen} onOpenChange={(isOpen) => {
          if (!isOpen) {
            setSelectedOrderForReminder(null);
          }
          setIsReminderModalOpen(isOpen);
        }}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>Set/Edit Reminder for Order {selectedOrderForReminder?.id}</DialogTitle>
                </DialogHeader>
                <div className="grid gap-4 py-4">
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="reminder-date" className="text-right">Date & Time</Label>
                        <Input
                            id="reminder-date"
                            type="datetime-local"
                            value={reminderDate}
                            onChange={(e) => setReminderDate(e.target.value)}
                            className="col-span-3"
                            disabled={mustClockIn}
                        />
                    </div>
                    <div className="grid grid-cols-4 items-center gap-4">
                        <Label htmlFor="reminder-notes" className="text-right">Notes</Label>
                        <Textarea
                            id="reminder-notes"
                            value={reminderNotes}
                            onChange={(e) => setReminderNotes(e.target.value)}
                            className="col-span-3"
                            placeholder="E.g., Follow up about delivery feedback"
                            disabled={mustClockIn}
                        />
                    </div>
                </div>
                <DialogFooter>
                    <DialogClose asChild><Button variant="outline" disabled={mustClockIn}>Cancel</Button></DialogClose>
                    <Button onClick={handleSetReminder} disabled={mustClockIn}>Save Reminder</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>

    </div>
  );
}
    
