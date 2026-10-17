
'use client';

import { useState, useEffect, useMemo } from 'react';
import type { Order, OrderItem, ReturnItemDetail, PaymentDetail, Product, User, ReturnTransactionInfo } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { MinusCircle, PlusCircle, DollarSign, CreditCard, Banknote, Landmark, Package, FileText, CheckCircle2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { format, parseISO, isValid } from 'date-fns';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface ReturnFormProps {
  order: Order;
  onSubmit: (
    itemsToReturn: ReturnItemDetail[],
    refundPaymentDetails: PaymentDetail[],
    returnReason?: string,
    exchangeNotes?: string
  ) => Promise<boolean>;
  allProducts: Product[];
  currentUser: User | null;
}

export default function ReturnForm({ order, onSubmit, allProducts, currentUser }: ReturnFormProps) {
  const { toast } = useToast();

  // Calculate previously returned quantities for each item
  const previouslyReturnedQuantities = useMemo(() => {
    const returnedMap: Record<string, number> = {}; // Key: productId_sku
    if (order.returnTransactions) {
      for (const rt of order.returnTransactions) {
        for (const item of rt.itemsReturned) {
          const key = `${item.productId}_${item.sku}`;
          returnedMap[key] = (returnedMap[key] || 0) + item.quantityToReturn;
        }
      }
    }
    return returnedMap;
  }, [order.returnTransactions]);

  const [itemsToReturn, setItemsToReturn] = useState<ReturnItemDetail[]>(
    order.items.map(item => {
      const key = `${item.productId}_${item.sku}`;
      const alreadyReturned = previouslyReturnedQuantities[key] || 0;
      const maxReturnableNow = Math.max(0, item.quantity - alreadyReturned);
      return {
        ...item,
        quantityToReturn: 0, // Start with 0 for current return transaction
        returnReason: '',
        originalOrderQuantity: item.quantity, // Store original quantity for reference
        previouslyReturnedQuantity: alreadyReturned,
        maxReturnableThisTx: maxReturnableNow,
      };
    })
  );

  const [refundPayments, setRefundPayments] = useState<PaymentDetail[]>([{ method: 'cash', amount: 0 }]);
  const [overallReturnReason, setOverallReturnReason] = useState('');
  const [exchangeNotes, setExchangeNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const totalValueOfReturnedItems = useMemo(() => {
    return itemsToReturn.reduce((sum, item) => {
      const price = typeof item.pricePerUnit === 'number' ? item.pricePerUnit : 0;
      return sum + price * item.quantityToReturn;
    }, 0);
  }, [itemsToReturn]);

  const netRefundAmount = totalValueOfReturnedItems;
  const totalRefundPaid = useMemo(() => refundPayments.reduce((sum, p) => sum + p.amount, 0), [refundPayments]);
  const remainingRefundBalance = useMemo(() => netRefundAmount - totalRefundPaid, [netRefundAmount, totalRefundPaid]);

  const handleQuantityToReturnChange = (productId: string, sku: string, newQuantity: number) => {
    setItemsToReturn(prevItems =>
      prevItems.map(item => {
        if (item.productId === productId && item.sku === sku) {
          const maxCanReturn = item.maxReturnableThisTx || 0;
          const clampedQuantity = Math.max(0, Math.min(newQuantity, maxCanReturn));
          return { ...item, quantityToReturn: clampedQuantity };
        }
        return item;
      })
    );
  };

  const handleAddRefundPaymentMethod = () => {
    setRefundPayments([...refundPayments, { method: 'cash', amount: Math.max(0, remainingRefundBalance) }]);
  };

  const handleRemoveRefundPaymentMethod = (index: number) => {
    if (refundPayments.length > 1) {
      setRefundPayments(refundPayments.filter((_, i) => i !== index));
    }
  };

  const handleRefundPaymentChange = (index: number, field: keyof PaymentDetail, value: string | number) => {
    const newPayments = [...refundPayments];
    if (field === 'amount') {
      newPayments[index][field] = Math.max(0, Number(value) || 0);
    } else {
      newPayments[index].method = value as PaymentDetail['method'];
    }
    setRefundPayments(newPayments);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    const actualItemsToReturn = itemsToReturn.filter(item => item.quantityToReturn > 0);
    if (actualItemsToReturn.length === 0) {
      toast({ title: 'No Items Selected', description: 'Please select items and quantities to return.', variant: 'destructive' });
      setIsSubmitting(false);
      return;
    }

    if (remainingRefundBalance < -0.005) {
      toast({ title: 'Refund Error', description: `Refund amount processed (OMR ${totalRefundPaid.toFixed(2)}) exceeds value of returned items (OMR ${netRefundAmount.toFixed(2)}). Adjust refund payments.`, variant: 'destructive' });
      setIsSubmitting(false);
      return;
    }
    if (remainingRefundBalance > 0.005) {
      toast({ title: 'Refund Error', description: `OMR ${remainingRefundBalance.toFixed(2)} still needs to be refunded. Adjust refund payments.`, variant: 'destructive' });
      setIsSubmitting(false);
      return;
    }

    const success = await onSubmit(actualItemsToReturn, refundPayments, overallReturnReason, exchangeNotes);
    setIsSubmitting(false);
    // Navigation or state reset handled by parent
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center"><FileText className="mr-2 h-5 w-5 text-muted-foreground" />Original Order Details</CardTitle>
          <CardDescription>
            Invoice ID: {order.id} | Date: {format(new Date(order.createdAt), 'MM/dd/yyyy p')} | Total: OMR {order.totalAmount.toFixed(2)}
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Items Being Returned</CardTitle>
          <CardDescription>Select items and specify quantities to return from the original order.</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[300px] border rounded-md">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[50px]">Return</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead className="text-center">Orig. Qty</TableHead>
                  <TableHead className="text-center">Prev. Ret.</TableHead>
                  <TableHead className="w-[120px] text-center">Qty to Return</TableHead>
                  <TableHead className="text-right">Unit Price</TableHead>
                  <TableHead className="text-right">Value Returned</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {itemsToReturn.map(item => {
                  const isFullyReturned = (item.maxReturnableThisTx || 0) <= 0;
                  return (
                    <TableRow 
                        key={item.productId + item.sku} 
                        className={cn(isFullyReturned ? "bg-green-50/50" : "")}
                    >
                      <TableCell>
                        <Checkbox
                          checked={item.quantityToReturn > 0}
                          onCheckedChange={(checked) =>
                            handleQuantityToReturnChange(
                              item.productId,
                              item.sku,
                              checked ? (item.maxReturnableThisTx || 1) : 0
                            )
                          }
                          disabled={isFullyReturned}
                        />
                      </TableCell>
                      <TableCell>
                        <div className={cn("font-medium", isFullyReturned && "text-green-700 line-through")}>{item.name}</div>
                        <div className="text-xs text-muted-foreground">SKU: {item.sku}</div>
                        {isFullyReturned && (
                          <Badge variant="outline" className="mt-1 border-green-300 text-green-600 bg-green-50 text-xs">
                            <CheckCircle2 className="w-3 h-3 mr-1" />
                            Fully Returned
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-center">{item.originalOrderQuantity}</TableCell>
                      <TableCell className="text-center">{item.previouslyReturnedQuantity}</TableCell>
                      <TableCell className="text-center">
                        <Input
                          type="number"
                          value={item.quantityToReturn}
                          onChange={(e) => handleQuantityToReturnChange(item.productId, item.sku, parseInt(e.target.value) || 0)}
                          min="0"
                          max={item.maxReturnableThisTx || 0}
                          className={cn("h-8 w-full text-center", isFullyReturned && "bg-muted/50 cursor-not-allowed")}
                          disabled={isFullyReturned}
                        />
                         {item.maxReturnableThisTx && item.maxReturnableThisTx > 0 && !isFullyReturned ? (
                            <p className="text-xs text-muted-foreground mt-1">Max: {item.maxReturnableThisTx}</p>
                         ) : null}
                      </TableCell>
                      <TableCell className="text-right">OMR {item.pricePerUnit.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-semibold">OMR {(item.pricePerUnit * item.quantityToReturn).toFixed(2)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </ScrollArea>
          <div className="mt-4 text-right">
            <span className="font-semibold text-lg">Total Value of Items in This Return: OMR {totalValueOfReturnedItems.toFixed(2)}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-lg">Return Details</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="overallReturnReason">Overall Reason for Return (Optional)</Label>
            <Textarea
              id="overallReturnReason"
              value={overallReturnReason}
              onChange={(e) => setOverallReturnReason(e.target.value)}
              placeholder="e.g., Customer changed mind, defective item..."
            />
          </div>
          <div>
            <Label htmlFor="exchangeNotes">Notes on Exchange (If any)</Label>
            <Textarea
              id="exchangeNotes"
              value={exchangeNotes}
              onChange={(e) => setExchangeNotes(e.target.value)}
              placeholder="e.g., Exchanged for Product X (SKU: YYY), size L."
            />
            <p className="text-xs text-muted-foreground mt-1">
              Note: For actual exchanges involving new products, process this return, then create a new order for exchanged items.
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Refund Processing</CardTitle>
          <CardDescription>Specify how the refund will be issued to the customer.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {refundPayments.map((payment, index) => (
            <div key={index} className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-3 items-end p-3 border rounded-md">
              <div className="space-y-1">
                <Label htmlFor={`refundMethod-${index}`}>Refund Method #{index + 1}</Label>
                <Select
                  value={payment.method}
                  onValueChange={(value) => handleRefundPaymentChange(index, 'method', value as PaymentDetail['method'])}
                >
                  <SelectTrigger id={`refundMethod-${index}`} className="h-10">
                    <SelectValue placeholder="Select method" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash"><Banknote className="inline mr-2 h-4 w-4" />Refund as Cash</SelectItem>
                    <SelectItem value="card"><CreditCard className="inline mr-2 h-4 w-4" />Refund to Card</SelectItem>
                    <SelectItem value="bank_transfer"><Landmark className="inline mr-2 h-4 w-4" />Refund via Bank Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor={`refundAmount-${index}`}>Amount to Refund</Label>
                <Input
                  id={`refundAmount-${index}`}
                  type="number"
                  value={payment.amount}
                  onChange={(e) => handleRefundPaymentChange(index, 'amount', e.target.value)}
                  className="h-10 text-right"
                  placeholder="0.00"
                  min="0"
                  step="0.01"
                />
              </div>
              {refundPayments.length > 1 && (
                <Button variant="ghost" size="icon" onClick={() => handleRemoveRefundPaymentMethod(index)} className="self-end text-destructive hover:text-destructive" aria-label="Remove refund method">
                  <MinusCircle className="h-5 w-5" />
                </Button>
              )}
            </div>
          ))}
          <Button variant="outline" onClick={handleAddRefundPaymentMethod} className="w-full mt-2" disabled={remainingRefundBalance <= 0}>
            <PlusCircle className="mr-2 h-4 w-4" /> Add Refund Method
          </Button>
          
          <Separator className="my-4" />
          <div className="space-y-2 text-sm">
            <div className="flex justify-between font-semibold text-lg">
              <span>Total Refund Due to Customer:</span>
              <span>OMR {netRefundAmount.toFixed(2)}</span>
            </div>
            <div className="flex justify-between font-semibold">
              <span>Total Refund Processed:</span>
              <span>OMR {totalRefundPaid.toFixed(2)}</span>
            </div>
            <div className="flex justify-between font-bold text-lg mt-1">
              <span>
                {remainingRefundBalance < -0.005 ? "Over-refunded by:" : (remainingRefundBalance > 0.005 ? "Remaining Refund Due:" : "Refund Balance:")}
              </span>
              <span className={remainingRefundBalance < -0.005 ? 'text-destructive' : (remainingRefundBalance > 0.005 ? 'text-orange-600' : 'text-green-600')}>
                OMR {Math.abs(remainingRefundBalance).toFixed(2)}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2 pt-4">
        <Button type="button" variant="outline" onClick={() => history.back()} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button 
          type="submit" 
          disabled={
            isSubmitting || 
            itemsToReturn.every(item => item.quantityToReturn === 0) || 
            (remainingRefundBalance > 0.005 || remainingRefundBalance < -0.005)
          } 
          className="bg-orange-500 hover:bg-orange-600 text-white"
        >
          {isSubmitting ? 'Processing...' : 'Confirm Return & Process Refund'}
        </Button>
      </div>
    </form>
  );
}
