
'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import type { Order, ReturnItemDetail, PaymentDetail, Product } from '@/types';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Undo2, ShieldAlert } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import ReturnForm from '@/components/admin/ReturnForm';
import { ScrollArea } from '@/components/ui/scroll-area';

export default function ProcessReturnPage() {
  const router = useRouter();
  const params = useParams();
  const { getOrderById, processDetailedReturn, products, currentUser, hasPermission } = useApp();
  const { toast } = useToast();

  const [order, setOrder] = useState<Order | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const orderId = typeof params.orderId === 'string' ? params.orderId : '';

  const canManageReturns = hasPermission('manage_returns');

  useEffect(() => {
    if (orderId) {
      const foundOrder = getOrderById(orderId);
      if (foundOrder) {
        setOrder(foundOrder);
      } else {
        toast({
          title: 'Order Not Found',
          description: `Order with ID ${orderId} could not be found.`,
          variant: 'destructive',
        });
        router.replace('/admin/orders');
      }
      setIsLoading(false);
    } else {
        router.replace('/admin/orders'); // Redirect if no orderId
    }
  }, [orderId, getOrderById, router, toast]);

  const handleSubmitReturn = async (
    itemsToReturn: ReturnItemDetail[],
    refundPaymentDetails: PaymentDetail[],
    returnReason?: string,
    exchangeNotes?: string
  ) => {
    if (!order || !currentUser) {
      toast({ title: 'Error', description: 'Order or user context missing.', variant: 'destructive' });
      return false;
    }
    if (!canManageReturns) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to process returns.', variant: 'destructive' });
      return false;
    }

    try {
      const success = await processDetailedReturn(
        order.id,
        itemsToReturn,
        refundPaymentDetails,
        returnReason,
        exchangeNotes
      );

      if (success) {
        toast({
          title: 'Return Processed Successfully',
          description: `Order ${order.id} has been updated.`,
          className: 'bg-accent text-accent-foreground border-accent'
        });
        router.push('/admin/orders');
        return true;
      } else {
        toast({ title: 'Return Processing Failed', description: 'Please check the details and try again.', variant: 'destructive' });
        return false;
      }
    } catch (error) {
      console.error('Error processing return:', error);
      toast({ title: 'Error', description: 'An unexpected error occurred.', variant: 'destructive' });
      return false;
    }
  };

  if (isLoading) {
    return <div className="p-6">Loading order details...</div>;
  }

  if (!canManageReturns) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to manage returns.</p>
        <Button onClick={() => router.back()} className="mt-4">
          <ArrowLeft className="mr-2 h-4 w-4" /> Go Back
        </Button>
      </div>
    );
  }

  if (!order) {
    return (
        <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
            <h1 className="text-2xl font-bold">Order Not Found</h1>
            <p className="text-muted-foreground">The requested order could not be loaded.</p>
             <Button onClick={() => router.push('/admin/orders')} className="mt-4">
                <ArrowLeft className="mr-2 h-4 w-4" /> Back to Orders
            </Button>
        </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="outline" onClick={() => router.back()} className="mb-4">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to Orders
      </Button>
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <Undo2 className="mr-2 h-7 w-7 text-primary" /> Process Return/Exchange for Order: {order.id}
          </CardTitle>
          <CardDescription>
            Manage returned items, process refunds, and note exchanges for this order.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[calc(100vh-20rem)] p-1">
            <div className="pr-4"> {/* Padding for scrollbar */}
              <ReturnForm 
                order={order} 
                onSubmit={handleSubmitReturn} 
                allProducts={products} 
                currentUser={currentUser}
              />
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
