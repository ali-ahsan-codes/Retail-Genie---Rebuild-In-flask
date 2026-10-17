// src/app/(main)/storekeeper/dashboard/page.tsx
'use client';

import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import type { Order, OrderItem, Product, OrderStatus } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { PackageSearch, PackageCheck, Clock, Search, AlertCircle, AlertTriangle, Loader2, UserCheck } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { format, parseISO, isValid } from 'date-fns'; 
import Link from 'next/link';
import { Alert, AlertDescription as UIDescription, AlertTitle as UITitle } from '@/components/ui/alert';


interface ScannedItemsState {
  [orderId: string]: {
    [itemKey: string]: boolean;
  };
}

interface MemoizedStorekeeperOrderRowProps {
  order: Order;
  scannedItems: ScannedItemsState;
  onItemScannedToggle: (orderId: string, itemKey: string) => void;
  onMarkOrderAsReadyForPickup: (orderId: string) => void; 
  getProductById: (productId: string) => OrderItem | Product | undefined;
  getOrderStatusBadge: (status: Order['status']) => JSX.Element;
  disabled: boolean;
}

const MemoizedStorekeeperOrderRow = React.memo(function MemoizedStorekeeperOrderRow({
  order, scannedItems, onItemScannedToggle, onMarkOrderAsReadyForPickup, getProductById, getOrderStatusBadge, disabled
}: MemoizedStorekeeperOrderRowProps) {
  const totalItems = order.items.reduce((sum, item) => sum + item.quantity, 0);
  const itemsScannedCount = order.items.reduce((sum, item) => {
      const itemKey = `${item.productId}_${item.sku}`;
      return sum + ((scannedItems[order.id]?.[itemKey] && item.quantity > 0) ? item.quantity : 0);
  }, 0);

  const isOrderFullyScanned = order.items.every(item => {
      const itemKey = `${item.productId}_${item.sku}`;
      return !!scannedItems[order.id]?.[itemKey];
  });

  return (
    <AccordionItem value={order.id} className="border rounded-lg shadow-sm bg-card">
      <AccordionTrigger className="p-4 hover:no-underline" disabled={disabled}>
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center w-full gap-2">
          <div className="flex-1">
            <h3 className="font-semibold text-primary text-lg">{order.id}</h3>
            <p className="text-sm text-muted-foreground">
              Salesperson: {order.primarySalespersonName}
            </p>
          </div>
          <div className="flex items-center gap-4 text-sm">
              {getOrderStatusBadge(order.status)}
              <span className="text-muted-foreground">
              {order.createdAt && isValid(parseISO(order.createdAt)) ? format(parseISO(order.createdAt), "MMM d, yyyy HH:mm") : "Invalid Date"}
              </span>
            <span className="font-medium">
              {itemsScannedCount} / {totalItems} items
            </span>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="p-0">
        <div className="p-4 border-t">
          <h4 className="font-medium mb-2 text-base">Order Items:</h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[60px]"></TableHead>
                <TableHead>Product</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead className="text-center">Qty</TableHead>
                <TableHead className="text-center">In Stock</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {order.items.map((item, index) => {
                const productDetails = getProductById(item.productId) as Product | undefined;
                const itemKey = `${item.productId}_${item.sku}`;
                return (
                <TableRow key={`${item.productId}-${index}`}>
                  <TableCell>
                      <Checkbox
                          id={`scan-${order.id}-${itemKey}`}
                          checked={!!scannedItems[order.id]?.[itemKey]}
                          onCheckedChange={() => onItemScannedToggle(order.id, itemKey)}
                          aria-label={`Scan ${item.name}`}
                          disabled={disabled || order.status === 'ready_for_pickup' || order.status === 'completed' || order.status === 'cancelled'}
                      />
                  </TableCell>
                  <TableCell className="font-medium">{item.name}</TableCell>
                  <TableCell>{item.sku}</TableCell>
                  <TableCell className="text-center">{item.quantity}</TableCell>
                  <TableCell className="text-center">{productDetails?.quantityInStock ?? 'N/A'}</TableCell>
                </TableRow>
              );})}
            </TableBody>
          </Table>
        </div>
        {order.status === 'preparing' && (
          <CardFooter className="p-4 border-t">
            <Button
              onClick={() => onMarkOrderAsReadyForPickup(order.id)}
              disabled={!isOrderFullyScanned || disabled}
              className="w-full bg-green-500 hover:bg-green-600 text-white"
            >
              <PackageCheck className="h-5 w-5 mr-2"/> Mark Order as Ready for Pickup
            </Button>
          </CardFooter>
        )}
        {order.status === 'ready_for_pickup' && (
            <CardFooter className="p-4 border-t bg-green-50">
              <p className="text-sm text-green-700 font-medium flex items-center">
                  <PackageCheck className="h-5 w-5 mr-2"/> This order is fully prepared and awaiting cashier.
              </p>
          </CardFooter>
        )}
        {order.status !== 'preparing' && order.status !== 'ready_for_pickup' && !isOrderFullyScanned && itemsScannedCount > 0 && (
             <CardFooter className="p-4 border-t bg-blue-50">
              <p className="text-sm text-blue-700 font-medium flex items-center">
                  <Clock className="h-5 w-5 mr-2"/> Preparation in progress...
              </p>
          </CardFooter>
        )}
      </AccordionContent>
    </AccordionItem>
  );
});
MemoizedStorekeeperOrderRow.displayName = "MemoizedStorekeeperOrderRow";


export default function StorekeeperDashboard() {
  const { orders, updateOrderStatus, getProductById, currentUser, getTodayAttendanceForUser, isDataLoaded, isAttendanceCurrentlyRequired } = useApp();
  const { toast } = useToast();
  const [searchTerm, setSearchTerm] = useState('');
  const [scannedItems, setScannedItems] = useState<ScannedItemsState>({});
  const [lastInteractedOrderId, setLastInteractedOrderId] = useState<string | null>(null);
  const prevOrdersRef = useRef<Order[]>(orders);
  const [hasClockedInToday, setHasClockedInToday] = useState<boolean | null>(null);
  const [mustClockIn, setMustClockIn] = useState(false);

  useEffect(() => {
    if (currentUser && isDataLoaded) {
      const attendanceLog = getTodayAttendanceForUser(currentUser.id);
      setHasClockedInToday(!!attendanceLog);
      setMustClockIn(isAttendanceCurrentlyRequired(currentUser.role) && !attendanceLog);
    }
  }, [currentUser, getTodayAttendanceForUser, isDataLoaded, isAttendanceCurrentlyRequired]);

  const pendingOrders = useMemo(() => {
    const relevantStatuses: OrderStatus[] = ['pending_payment', 'partial_payment', 'paid', 'preparing', 'ready_for_pickup'];
    return orders
      .filter(order => relevantStatuses.includes(order.status))
      .filter(order => order.id.toLowerCase().includes(searchTerm.toLowerCase()))
      .sort((a, b) => {
        if (a.status === 'preparing' && b.status !== 'preparing') return -1;
        if (a.status !== 'preparing' && b.status === 'preparing') return 1;
        return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()
      });
  }, [orders, searchTerm]);

  const handleItemScannedToggle = useCallback((orderId: string, itemKey: string) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before preparing orders. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    setScannedItems(prev => {
      const updatedOrderScans = { ...(prev[orderId] || {}), [itemKey]: !prev[orderId]?.[itemKey] };
      return { ...prev, [orderId]: updatedOrderScans };
    });
    setLastInteractedOrderId(orderId);
  }, [mustClockIn, toast]);

  useEffect(() => {
    if (!lastInteractedOrderId || mustClockIn) return;

    const order = orders.find(o => o.id === lastInteractedOrderId);
    if (!order) {
      setLastInteractedOrderId(null);
      return;
    }

    const orderScans = scannedItems[order.id] || {};
    const allScanned = order.items.every(item => {
        const itemKey = `${item.productId}_${item.sku}`;
        return !!orderScans[itemKey];
    });
    const anyScanned = order.items.some(item => {
        const itemKey = `${item.productId}_${item.sku}`;
        return !!orderScans[itemKey];
    });

    if (!allScanned && order.status === 'ready_for_pickup') {
      updateOrderStatus(lastInteractedOrderId, 'preparing');
    } else if (anyScanned && (order.status === 'pending_payment' || order.status === 'partial_payment' || order.status === 'paid')) {
      updateOrderStatus(lastInteractedOrderId, 'preparing');
    }
    setLastInteractedOrderId(null);
  }, [lastInteractedOrderId, scannedItems, orders, updateOrderStatus, mustClockIn]);

  const handleMarkOrderAsReadyForPickup = useCallback(async (orderId: string) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in before marking orders ready. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    const order = orders.find(o => o.id === orderId);
    if (!order) {
      toast({ title: "Error", description: "Order not found.", variant: "destructive" });
      return;
    }
    const orderScans = scannedItems[order.id] || {};
    const allScanned = order.items.every(item => {
        const itemKey = `${item.productId}_${item.sku}`;
        return !!orderScans[itemKey];
    });

    if (allScanned && order.status === 'preparing') {
        await updateOrderStatus(orderId, 'ready_for_pickup');
    } else if (!allScanned) {
        toast({ title: "Not Ready", description: "Not all items are scanned for this order.", variant: "default" });
    } else if (order.status !== 'preparing') {
        toast({ title: "Invalid Action", description: `Order status is ${order.status}, cannot mark as ready for pickup directly.`, variant: "default" });
    }
  }, [orders, scannedItems, updateOrderStatus, toast, mustClockIn]);


  useEffect(() => {
    orders.forEach(currentOrder => {
      const prevOrder = prevOrdersRef.current.find(po => po.id === currentOrder.id);
      if (prevOrder && prevOrder.status !== 'ready_for_pickup' && currentOrder.status === 'ready_for_pickup') {
        toast({
          title: 'Order Ready!',
          description: `Order ${currentOrder.id} is now fully prepared and ready for the cashier.`,
          className: 'bg-accent text-accent-foreground border-accent'
        });
      }
    });
    prevOrdersRef.current = [...orders];
  }, [orders, toast]);


  const getOrderStatusBadge = useCallback((status: Order['status']) => {
    switch (status) {
      case 'pending_payment': return <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">Pending Payment</Badge>;
      case 'partial_payment': return <Badge variant="outline" className="bg-orange-100 text-orange-700 border-orange-300">Partial Payment</Badge>;
      case 'paid': return <Badge variant="default" className="bg-green-100 text-green-700 border-green-300">Paid (Needs Prep)</Badge>;
      case 'preparing': return <Badge variant="outline" className="bg-blue-100 text-blue-700 border-blue-300">Preparing</Badge>;
      case 'ready_for_pickup': return <Badge variant="default" className="bg-accent text-accent-foreground">Ready for Pickup</Badge>;
      default: return <Badge variant="secondary">{status}</Badge>;
    }
  }, []);

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
            The mandatory attendance time has passed. You must clock in before you can access the storekeeper dashboard.
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
          <CardTitle className="text-2xl flex items-center">
            <PackageSearch className="mr-2 h-7 w-7 text-primary" /> Sales Order Preparation
          </CardTitle>
          <CardDescription>View and prepare customer orders. Check items to mark them as ready.</CardDescription>
          <div className="relative mt-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
            <Input
              type="search"
              placeholder="Search by Invoice ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 h-10"
              disabled={mustClockIn}
            />
          </div>
        </CardHeader>
      </Card>

      {pendingOrders.length === 0 ? (
         <Card>
          <CardContent className="p-8 text-center">
            <AlertCircle className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-xl font-semibold">No pending orders found.</p>
            <p className="text-muted-foreground">All orders are processed or there are no orders matching your search.</p>
          </CardContent>
        </Card>
      ) : (
      <ScrollArea className="h-[calc(100vh-theme(spacing.56))]">
        <Accordion type="multiple" className="w-full space-y-4">
          {pendingOrders.map((order) => (
            <MemoizedStorekeeperOrderRow
              key={order.id}
              order={order}
              scannedItems={scannedItems}
              onItemScannedToggle={handleItemScannedToggle}
              onMarkOrderAsReadyForPickup={handleMarkOrderAsReadyForPickup}
              getProductById={getProductById}
              getOrderStatusBadge={getOrderStatusBadge}
              disabled={mustClockIn}
            />
          ))}
        </Accordion>
      </ScrollArea>
      )}
    </div>
  );
}

    
