// src/app/(main)/express/page.tsx
'use client';
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Separator } from '@/components/ui/separator';
import { Barcode, ShoppingCart, Trash2, DollarSign, XCircle, PlusCircle, MinusCircle, Loader2, AlertTriangle, Package, Check, Banknote, CreditCard, Landmark, Printer, Plus, Calculator, Search as SearchIcon } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import type { Product, CartItem, Order, PaymentDetail, PaymentMethod as PaymentMethodType } from '@/types';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import Image from 'next/image';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { brandingConfig } from '@/config/branding';
import { format, parseISO, isValid } from 'date-fns';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import ProductCard from '@/components/ProductCard';


type ExpressCartItem = CartItem & { basePrice: number };

export default function ExpressCheckoutPage() {
  const { currentUser, getProductBySku, getEffectiveProductPrice, isDataLoaded, products: contextProducts } = useApp();
  const { toast } = useToast();
  
  const [barcodeInput, setBarcodeInput] = useState('');
  const [manualSearchTerm, setManualSearchTerm] = useState('');
  const [cart, setCart] = useState<ExpressCartItem[]>([]);
  const [lastScannedProduct, setLastScannedProduct] = useState<Product | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [payments, setPayments] = useState<PaymentDetail[]>([{ method: 'cash', amount: 0 }]);
  const [cashReceived, setCashReceived] = useState('');

  const skuInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    skuInputRef.current?.focus();
  }, [cart]);


  const handleAddToCart = useCallback((product: Product) => {
    const effectivePrice = getEffectiveProductPrice(product);

    setCart(prevCart => {
      const existingItem = prevCart.find(item => item.id === product.id);
      if (existingItem) {
        if (existingItem.cartQuantity >= product.quantityInStock) {
          toast({ title: "Stock Limit", description: `No more stock available for ${product.name}.`, variant: "destructive" });
          return prevCart;
        }
        return prevCart.map(item =>
          item.id === product.id ? { ...item, cartQuantity: item.cartQuantity + 1 } : item
        );
      }
      return [...prevCart, { ...product, basePrice: product.price, customPrice: effectivePrice, cartQuantity: 1 }];
    });
    setLastScannedProduct(product);
  }, [toast, getEffectiveProductPrice]);
  
  const handleManualAddToCart = useCallback((product: Product, quantity: number) => {
     handleAddToCart(product); // Manual add is just adding 1 at a time from card
  }, [handleAddToCart]);


  const handleSearch = useCallback(async () => {
    if (!barcodeInput.trim()) return;

    setIsLoading(true);
    setLastScannedProduct(null);
    try {
        const product = await getProductBySku(barcodeInput.trim());
        if (product) {
            if (product.quantityInStock <= 0) {
                toast({ title: "Out of Stock", description: `${product.name} is currently out of stock.`, variant: "destructive" });
            } else {
                handleAddToCart(product);
            }
        } else {
            toast({ title: "Not Found", description: `Product with SKU "${barcodeInput.trim()}" not found.`, variant: "destructive" });
        }
    } catch (error) {
        toast({ title: "Error", description: "Failed to fetch product details.", variant: "destructive" });
    } finally {
        setIsLoading(false);
        setBarcodeInput(''); // Clear input after processing
        skuInputRef.current?.focus();
    }
  }, [barcodeInput, getProductBySku, handleAddToCart, toast]);

  useEffect(() => {
    if (currentUser?.autoEnterAfterScan && barcodeInput.trim()) {
        handleSearch();
    }
  }, [barcodeInput, currentUser?.autoEnterAfterScan, handleSearch]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault(); // Prevent form submission if it's inside a form
      handleSearch();
    }
  };
  
  const updateQuantity = (productId: string, newQuantity: number) => {
    setCart(prevCart => {
        const itemToUpdate = prevCart.find(item => item.id === productId);
        if (!itemToUpdate) return prevCart;

        if(newQuantity > itemToUpdate.quantityInStock) {
            toast({ title: "Stock Limit", description: `Only ${itemToUpdate.quantityInStock} units of ${itemToUpdate.name} are available.`, variant: "destructive" });
            return prevCart.map(item => item.id === productId ? { ...item, cartQuantity: itemToUpdate.quantityInStock } : item);
        }

        if (newQuantity <= 0) {
            return prevCart.filter(item => item.id !== productId);
        }
        return prevCart.map(item => item.id === productId ? { ...item, cartQuantity: newQuantity } : item);
    });
  };

  const cartTotal = useMemo(() => cart.reduce((sum, item) => sum + (item.customPrice ?? item.basePrice) * item.cartQuantity, 0), [cart]);

  const totalPaid = useMemo(() => payments.reduce((sum, p) => sum + p.amount, 0), [payments]);
  const remainingBalance = useMemo(() => cartTotal - totalPaid, [cartTotal, totalPaid]);

  useEffect(() => {
    if (cart.length > 0) {
        if (payments.length === 1 && payments[0].amount !== cartTotal) {
             setPayments([{ method: payments[0].method, amount: cartTotal }]);
        }
    } else {
        setPayments([{ method: 'cash', amount: 0 }]);
        setCashReceived('');
    }
  }, [cartTotal, cart.length]);


  const handleAddPaymentMethod = () => {
    setPayments([...payments, { method: 'cash', amount: Math.max(0, remainingBalance) }]);
  };

  const handleRemovePaymentMethod = (index: number) => {
    if (payments.length > 1) {
      setPayments(payments.filter((_, i) => i !== index));
    }
  };

  const handlePaymentChange = (index: number, field: 'method' | 'amount', value: string | number) => {
    const newPayments = [...payments];
    if (field === 'amount') {
      newPayments[index][field] = Math.max(0, Number(value) || 0);
    } else {
      newPayments[index].method = value as PaymentMethodType;
    }
    setPayments(newPayments);
  };
  
  const handleDirectPrint = (order: Order | null) => {
    if (!order) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      toast({ title: "Print Error", description: "Please allow popups for this site to print the invoice.", variant: "destructive" });
      return;
    }

    const invoiceDate = isValid(parseISO(order.createdAt)) ? format(parseISO(order.createdAt), "dd/MM/yyyy HH:mm") : 'N/A';
    const directOrderStatusText = order.status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const logoUrl = `${baseUrl}${brandingConfig.logoPath}`;

    const paymentMethodTranslations: Record<PaymentMethodType, string> = {
      cash: 'نقدي',
      card: 'بطاقة',
      bank_transfer: 'تحويل بنكي',
      advance_on_dn: 'دفعة مقدمة'
    };

    const getPaymentMethodLabel = (method: PaymentMethodType, context: 'paid' | 'refund') => {
        const englishLabel = method.replace(/_/g, ' ');
        const paidText = context === 'paid' ? 'Paid' : 'Refund via';
        const arabicText = context === 'paid' ? 'دفع' : 'استرداد عبر';
        const arabicLabel = paymentMethodTranslations[method] || '';
        return `<span class="capitalize">${paidText} ${englishLabel}</span>${arabicLabel ? ` / ${arabicText} ${arabicLabel}` : ''}`;
    };

    const generatePageHeaderHtml = () => `
      <div class="receipt-header">
          ${brandingConfig.logoPath ? `<img src="${logoUrl}" alt="Company Logo" class="logo" data-ai-hint="logo company"/>` : ''}
          <div class="company-name">${brandingConfig.companyNameForInvoice}</div>
          <div class="company-details">
              ${brandingConfig.companyAddressForInvoice}<br/>
              Tel: ${brandingConfig.companyPhoneForInvoice}
              ${brandingConfig.companyWebsiteForInvoice ? `<br/>${brandingConfig.companyWebsiteForInvoice}` : ''}
          </div>
      </div>
    `;

    const totalPaidOnOrder = (order.payments || []).reduce((sum, p) => sum + p.amount, 0);
    const remainingBalanceOnOrder = order.totalAmount - totalPaidOnOrder;
    
    const pageContent = `
        <div class="section">
          ${generatePageHeaderHtml()}
        </div>
        <div class="section">
          <div class="section-title">Invoice / فاتورة</div>
          <div class="info-grid">
              <p><span class="label">Invoice #:</span> ${order.id}</p>
              <p><span class="label">Date:</span> ${invoiceDate}</p>
              <p><span class="label">Sales Rep:</span> ${order.primarySalespersonName}</p>
              <p><span class="label">Status:</span> ${directOrderStatusText}</p>
          </div>
          <div style="border-top: 1px dashed #ccc; margin: 2mm 0;"></div>
          <div class="bill-to">
              <p><span class="label">Bill To: / فاتورة إلى:</span></p>
              <p>${order.customerName || 'N/A'}</p>
              <p>${order.customerPhone || ''}</p>
              <p>${order.deliveryAddress || ''}</p>
          </div>
        </div>

        <div class="section">
          <div class="section-title">Items / العناصر</div>
          <div class="items-container">
            ${(order.items || []).map(item => `
              <div class="item-box">
                <div class="item-details">
                  <span class="item-name">${item.name}</span>
                  <span class="item-sku">SKU: ${item.sku}</span>
                </div>
                <div class="item-qty">Qty: ${item.quantity}</div>
                <div class="item-total">OMR ${item.totalPrice.toFixed(2)}</div>
              </div>
            `).join('')}
          </div>
        </div>

        <div class="section totals-section">
          <div class="section-title">Summary / ملخص</div>
          <div class="total-row"><span>Subtotal: / المجموع الفرعي:</span><span>OMR ${order.subtotal.toFixed(2)}</span></div>
          ${order.discountAmount > 0 ? `<div class="total-row"><span>Discount: / الخصم:</span><span>-OMR ${order.discountAmount.toFixed(2)}</span></div>` : ''}
          ${order.taxes && order.taxes.length > 0 ? `<div class="total-row"><span>Tax: / الضريبة:</span><span>OMR ${(order.taxes.reduce((s, t) => s + t.amount, 0)).toFixed(2)}</span></div>` : ''}
          <div class="total-row grand-total"><span>Total Due: / المبلغ الإجمالي:</span><span>OMR ${order.totalAmount.toFixed(2)}</span></div>
          <div style="border-top: 1px dashed #ccc; margin: 1.5mm 0;"></div>
          ${(order.payments || []).map(p => `<div class="total-row">${getPaymentMethodLabel(p.method, 'paid')}:</span><span>OMR ${p.amount.toFixed(2)}</span></div>`).join('')}
          <div class="total-row balance-due"><span>Balance Due: / الرصيد المتبقي:</span><span>OMR ${remainingBalanceOnOrder.toFixed(2)}</span></div>
        </div>
        
        <div class="section notes-section">
          <div class="section-title">Notes & Terms</div>
          <ul class="notes-list">${(brandingConfig.returnPolicyNotes || []).map(note => `<li>${note.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</li>`).join('')}</ul>
        </div>
        <div class="footer"><p>Thank you for your business!</p></div>
    `;
    
    const printStyles = `
      <style>
          @page { size: 80mm; margin: 3mm; }
          * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'monospace', 'Courier New', Courier; color: #000; }
          body { width: 74mm; font-size: 8pt; line-height: 1.3; }
          .receipt-header { text-align: center; margin-bottom: 4mm; }
          .logo { max-height: 40px; max-width: 100%; margin-bottom: 2mm; }
          .company-name { font-size: 11pt; font-weight: bold; }
          .company-details { font-size: 7pt; line-height: 1.2; }
          
          .section { margin-bottom: -1px; border: 1px solid #000; padding: 1.5mm; }
          .section-title { font-weight: bold; text-transform: uppercase; margin-bottom: 1.5mm; font-size: 9pt; text-align: center; border-bottom: 1px dashed #000; padding-bottom: 1mm; }
          
          .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1mm 3mm; font-size: 7.5pt; }
          .info-grid p, .bill-to p { margin: 0; }
          .label { font-weight: bold; }
          .bill-to { font-size: 8pt; margin-top: 2mm; }

          .items-container { display: flex; flex-direction: column; gap: 0; margin-top: 1mm; }
          .item-box { display: flex; justify-content: space-between; align-items: center; padding: 1.5mm; border-bottom: 1px solid #000; }
          .item-box:last-child { border-bottom: none; }
          .item-box .item-details { flex-grow: 1; display: flex; flex-direction: column; padding-right: 1mm; }
          .item-box .item-name { font-weight: bold; font-size: 8pt; }
          .item-box .item-sku { font-size: 7pt; color: #555; }
          .item-box .item-qty { width: 15%; text-align: center; font-size: 8pt; flex-shrink: 0; }
          .item-box .item-total { width: 25%; text-align: right; font-weight: bold; font-size: 8pt; flex-shrink: 0; }

          .totals-section .section-title { margin-bottom: 2mm; }
          .total-row { display: flex; justify-content: space-between; padding: 0.5mm 0; font-size: 8.5pt; }
          .total-row.grand-total { font-weight: bold; font-size: 11pt; border-top: 1px solid #000; padding-top: 1mm; margin-top: 1mm; }
          .total-row.balance-due { font-weight: bold; font-size: 10pt; border-top: 1px dashed #000; padding-top: 1mm; margin-top: 1mm; }

          .notes-section .section-title { text-align: left; border-bottom: none; padding-bottom: 0; }
          .notes-list { list-style-position: inside; padding-left: 1mm; margin-top: 1mm; font-size: 7pt;}
          .footer { text-align: center; margin-top: 4mm; font-size: 8pt; }
      </style>
    `;
    
    printWindow.document.write(`<html><head><title>Invoice ${order.id}</title>${printStyles}</head><body>${pageContent}</body></html>`);
    printWindow.document.close();
    setTimeout(() => {
      printWindow.print();
    }, 250);
  };

  const handleCheckout = async () => {
    if (cart.length === 0 || !currentUser) {
        toast({ title: "Error", description: "Cart is empty or user is not logged in.", variant: "destructive" });
        return;
    }
    if (Math.abs(remainingBalance) > 0.005) {
        toast({ title: "Payment Mismatch", description: `Total paid (OMR ${totalPaid.toFixed(2)}) does not match cart total (OMR ${cartTotal.toFixed(2)}).`, variant: "destructive"});
        return;
    }

    setIsProcessing(true);
    try {
        const payload = {
            items: cart.map(item => ({ sku: item.sku, quantity: item.cartQuantity })),
            payments: payments,
            cashierId: currentUser.id,
        };

        const response = await fetch('/api/express/checkout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || 'Checkout failed on the server.');
        }

        const result = await response.json();
        if (result.success && result.data) {
            toast({ title: "Checkout Successful!", description: `Transaction ID: ${result.data.id}`, className: 'bg-green-100 text-green-800'});
            handleDirectPrint(result.data);
            setCart([]);
        } else {
            throw new Error(result.error || 'Failed to complete checkout.');
        }
    } catch (error) {
        toast({ title: "Checkout Error", description: (error as Error).message, variant: "destructive" });
    } finally {
        setIsProcessing(false);
    }
  };

  const cashPaymentAmount = useMemo(() => {
    return payments.filter(p => p.method === 'cash').reduce((sum, p) => sum + p.amount, 0);
  }, [payments]);

  const changeDue = useMemo(() => {
    const cashReceivedNum = parseFloat(cashReceived) || 0;
    if (cashReceivedNum <= 0 || cashPaymentAmount <= 0) return 0;
    return cashReceivedNum - cashPaymentAmount;
  }, [cashReceived, cashPaymentAmount]);
  
  const filteredProducts = useMemo(() => {
    if (!manualSearchTerm.trim()) return contextProducts;
    const term = manualSearchTerm.toLowerCase();
    return contextProducts.filter(p => p.name.toLowerCase().includes(term) || p.sku.toLowerCase().includes(term));
  },[manualSearchTerm, contextProducts]);

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 h-[calc(100vh-theme(spacing.24)-2rem)]">
        {/* Left Panel: Scanner and Cart */}
        <div className="flex flex-col gap-4">
          <Card>
             <CardHeader>
                <CardTitle className="text-xl">Product Input</CardTitle>
             </CardHeader>
             <CardContent>
                <Tabs defaultValue="scan">
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="scan"><Barcode className="mr-2 h-4 w-4"/>Barcode Scan</TabsTrigger>
                        <TabsTrigger value="search"><SearchIcon className="mr-2 h-4 w-4"/>Manual Search</TabsTrigger>
                    </TabsList>
                    <TabsContent value="scan" className="pt-4">
                        <Input
                            ref={skuInputRef}
                            value={barcodeInput}
                            onChange={(e) => setBarcodeInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Scan product barcode..."
                            className="h-12 text-lg"
                            disabled={isLoading}
                            autoFocus
                        />
                         {lastScannedProduct && (
                            <Card className="bg-blue-50/50 border-blue-200 mt-4">
                                <CardContent className="p-4 flex gap-4 items-center">
                                    {lastScannedProduct.imageUrl ? (
                                        <Image src={`/api/uploads/${lastScannedProduct.imageUrl}`} alt={lastScannedProduct.name} width={64} height={64} className="rounded-md object-cover" unoptimized={true} onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/64x64.png'; }} />
                                    ) : (
                                        <div className="w-16 h-16 bg-muted rounded-md flex items-center justify-center"><Package className="w-8 h-8 text-muted-foreground"/></div>
                                    )}
                                    <div>
                                        <p className="font-semibold">{lastScannedProduct.name}</p>
                                        <p className="text-sm text-muted-foreground">Price: OMR {getEffectiveProductPrice(lastScannedProduct).toFixed(2)}</p>
                                    </div>
                                </CardContent>
                            </Card>
                         )}
                    </TabsContent>
                    <TabsContent value="search" className="pt-4">
                       <Input
                            placeholder="Search by name or SKU..."
                            value={manualSearchTerm}
                            onChange={(e) => setManualSearchTerm(e.target.value)}
                            className="h-10 text-base"
                        />
                        <ScrollArea className="h-48 mt-2 border rounded-md">
                          <div className="p-2 space-y-2">
                            {filteredProducts.map(p => (
                              <ProductCard key={p.id} product={p} onAddToCart={handleManualAddToCart} />
                            ))}
                          </div>
                        </ScrollArea>
                    </TabsContent>
                </Tabs>
             </CardContent>
          </Card>

          <Card className="flex-grow flex flex-col">
            <CardHeader>
              <CardTitle className="flex items-center"><ShoppingCart className="mr-2 h-6 w-6 text-primary"/> Cart</CardTitle>
            </CardHeader>
            <CardContent className="flex-grow p-0">
              <ScrollArea className="h-[calc(100vh-32rem)]">
                {cart.length === 0 ? (
                  <div className="text-center p-8 text-muted-foreground">Scan or add items to begin...</div>
                ) : (
                  <Table>
                    <TableHeader><TableRow><TableHead>Item</TableHead><TableHead className="text-center">Qty</TableHead><TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {cart.map(item => (
                        <TableRow key={item.id}>
                          <TableCell>
                            <div className="font-medium">{item.name}</div>
                            <div className="text-xs text-muted-foreground">@ OMR {(item.customPrice ?? item.basePrice).toFixed(2)}</div>
                          </TableCell>
                          <TableCell className="text-center">
                              <div className="flex items-center justify-center gap-1">
                                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => updateQuantity(item.id, item.cartQuantity - 1)}><MinusCircle className="h-4 w-4"/></Button>
                                  <span>{item.cartQuantity}</span>
                                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => updateQuantity(item.id, item.cartQuantity + 1)}><PlusCircle className="h-4 w-4"/></Button>
                              </div>
                          </TableCell>
                          <TableCell className="text-right font-semibold">OMR {((item.customPrice ?? item.basePrice) * item.cartQuantity).toFixed(2)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Right Panel: Payment */}
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle className="text-2xl">Payment</CardTitle>
            <CardDescription>Total amount must be paid in full.</CardDescription>
          </CardHeader>
          <CardContent className="flex-grow flex flex-col justify-between">
              <div className="space-y-4">
                  <div className="text-center p-6 border-dashed border-2 rounded-lg">
                      <p className="text-muted-foreground">Total Amount</p>
                      <p className="text-5xl font-bold tracking-tighter">OMR {cartTotal.toFixed(3)}</p>
                  </div>
                  
                  <div className="space-y-2">
                      <Label className="font-medium">Payment Methods</Label>
                      {payments.map((payment, index) => (
                          <div key={index} className="grid grid-cols-[1fr_auto_auto] gap-2 items-center p-2 border rounded-md">
                             <Select value={payment.method} onValueChange={(value) => handlePaymentChange(index, 'method', value as PaymentMethodType)}>
                               <SelectTrigger><SelectValue/></SelectTrigger>
                               <SelectContent>
                                  <SelectItem value="cash"><Banknote className="inline mr-2 h-4 w-4"/>Cash</SelectItem>
                                  <SelectItem value="card"><CreditCard className="inline mr-2 h-4 w-4"/>Card</SelectItem>
                                  <SelectItem value="bank_transfer"><Landmark className="inline mr-2 h-4 w-4"/>Bank Transfer</SelectItem>
                               </SelectContent>
                             </Select>
                             <Input type="number" value={payment.amount} onChange={(e) => handlePaymentChange(index, 'amount', e.target.value)} className="w-28 text-right" placeholder="0.00"/>
                             {payments.length > 1 && <Button variant="ghost" size="icon" className="text-destructive h-8 w-8" onClick={() => handleRemovePaymentMethod(index)}><Trash2 className="h-4 w-4"/></Button>}
                          </div>
                      ))}
                      <Button variant="outline" size="sm" className="w-full" onClick={handleAddPaymentMethod} disabled={remainingBalance <= 0}><PlusCircle className="mr-2 h-4 w-4"/>Add Payment Method</Button>
                  </div>
                  
                  {cashPaymentAmount > 0 && (
                     <Card className="p-3 bg-muted/30">
                      <CardTitle className="text-sm font-semibold mb-2 flex items-center"><Calculator className="h-4 w-4 mr-2 text-muted-foreground"/>Cash Calculator</CardTitle>
                      <div className="space-y-2">
                        <div>
                          <Label htmlFor="cash-received" className="text-xs">Cash Received (OMR)</Label>
                          <Input id="cash-received" type="number" value={cashReceived} onChange={e => setCashReceived(e.target.value)} className="h-8 w-full text-right" placeholder="e.g. 50"/>
                        </div>
                        <div className="flex justify-between text-xs">
                          <span>Amount Due (Cash):</span>
                          <span>OMR {cashPaymentAmount.toFixed(2)}</span>
                        </div>
                        {parseFloat(cashReceived) > 0 && (
                          <div className={cn("flex justify-between text-lg font-bold", changeDue < 0 ? 'text-destructive' : 'text-green-600')}>
                            <span>Change Due:</span>
                            <span>OMR {changeDue >= 0 ? changeDue.toFixed(2) : `Short by ${Math.abs(changeDue).toFixed(2)}` }</span>
                          </div>
                        )}
                      </div>
                    </Card>
                  )}

                  <Separator/>
                  <div className="space-y-1 text-sm">
                      <div className="flex justify-between font-semibold"><span>Total Paid:</span><span>OMR {totalPaid.toFixed(2)}</span></div>
                      <div className={cn("flex justify-between font-bold", remainingBalance === 0 ? "text-green-600" : "text-destructive")}>
                          <span>Remaining:</span>
                          <span>OMR {remainingBalance.toFixed(2)}</span>
                      </div>
                  </div>

              </div>
              <Button className="w-full h-16 text-xl mt-6" onClick={handleCheckout} disabled={cart.length === 0 || isProcessing || Math.abs(remainingBalance) > 0.005}>
                {isProcessing ? <Loader2 className="mr-2 h-6 w-6 animate-spin"/> : <DollarSign className="mr-2 h-6 w-6"/>}
                Complete Sale
              </Button>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
