// src/components/salesperson/QuotationForm.tsx
'use client';
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import type { Product, Quotation, QuotationItem, QuotationStatus, CartItem as AppCartItem } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { useToast } from '@/hooks/use-toast';
import { format, addDays, parseISO, isValid } from 'date-fns';
import { cn } from '@/lib/utils';
import { Trash2, PlusCircle, MinusCircle, Search, CalendarIcon, Loader2, Package, DollarSign, Edit2, CheckSquare, Send, Save, Printer, X } from 'lucide-react';
import Image from 'next/image';
import { Badge } from '@/components/ui/badge';

interface QuotationCartItem extends AppCartItem {
  isExternal: boolean;
  externalStoreName?: string;
}

interface QuotationFormProps {
  initialQuotation?: Quotation;
}

export default function QuotationForm({ initialQuotation }: QuotationFormProps) {
  const { currentUser, products: availableProducts, addQuotation, updateQuotation, getProductById } = useApp();
  const router = useRouter();
  const { toast } = useToast();

  const [customerName, setCustomerName] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');
  const [customerAddress, setCustomerAddress] = useState('');
  const [preparationDays, setPreparationDays] = useState(3);
  const [validUntil, setValidUntil] = useState<Date | undefined>(addDays(new Date(), 7));
  const [status, setStatus] = useState<QuotationStatus>('draft');
  const [notes, setNotes] = useState('');
  const [quotationItems, setQuotationItems] = useState<QuotationCartItem[]>([]);

  const [productSearchTerm, setProductSearchTerm] = useState('');
  const [isAddingExternal, setIsAddingExternal] = useState(false);
  const [externalItemForm, setExternalItemForm] = useState({ name: '', sku: '', price: 0, quantity: 1 });

  const [isLoading, setIsLoading] = useState(false);
  const [prevInitialQuotationId, setPrevInitialQuotationId] = useState<string | null>(null);


  useEffect(() => {
    if (initialQuotation && initialQuotation.id !== prevInitialQuotationId) {
      setCustomerName(initialQuotation.customerName || '');
      setCustomerPhone(initialQuotation.customerPhone || '');
      setCustomerEmail(initialQuotation.customerEmail || '');
      setCustomerAddress(initialQuotation.customerAddress || '');
      setPreparationDays(initialQuotation.preparationDays || 3);
      setValidUntil(initialQuotation.validUntil ? parseISO(initialQuotation.validUntil) : addDays(new Date(), 7));
      setStatus(initialQuotation.status || 'draft');
      setNotes(initialQuotation.notes || '');

      const itemsToLoad: QuotationCartItem[] = (initialQuotation.items || []).map(item => {
        const productDetails = availableProducts.find(p => p.id === item.productId);
        return {
          id: item.productId || `ext-${item.productName.replace(/\s+/g, '-')}-${Math.random().toString(36).substr(2, 5)}`,
          name: item.productName,
          price: item.price,
          quantityInStock: productDetails?.quantityInStock ?? (item.isExternal ? Infinity : 0),
          sku: item.productSku || (productDetails?.sku ?? ''),
          imageUrl: productDetails?.imageUrl, // This will be "products/filename.ext"
          category: productDetails?.category,
          expiryDate: productDetails?.expiryDate,
          cartQuantity: item.quantity,
          customPrice: item.price,
          isExternal: item.isExternal,
        };
      });
      setQuotationItems(itemsToLoad);
      setPrevInitialQuotationId(initialQuotation.id);
    } else if (!initialQuotation && prevInitialQuotationId !== null) {
      setCustomerName(''); setCustomerPhone(''); setCustomerEmail(''); setCustomerAddress('');
      setPreparationDays(3); setValidUntil(addDays(new Date(), 7)); setStatus('draft');
      setNotes(''); setQuotationItems([]);
      setPrevInitialQuotationId(null);
    }
  }, [initialQuotation, availableProducts, prevInitialQuotationId]);

  useEffect(() => {
    if (!prevInitialQuotationId && !initialQuotation) return;

    setQuotationItems(currentCartItems =>
      currentCartItems.map(cartItem => {
        if (!cartItem.isExternal && cartItem.id) {
          const productDetails = availableProducts.find(p => p.id === cartItem.id);
          if (productDetails) {
            return {
              ...cartItem,
              quantityInStock: productDetails.quantityInStock,
              imageUrl: productDetails.imageUrl, // Correctly set here
            };
          }
        }
        return cartItem;
      })
    );
  }, [availableProducts, prevInitialQuotationId, initialQuotation]);


  const filteredProducts = useMemo(() => {
    if (!productSearchTerm.trim()) return [];
    return availableProducts.filter(
      p => p.name.toLowerCase().includes(productSearchTerm.toLowerCase()) ||
           p.sku.toLowerCase().includes(productSearchTerm.toLowerCase())
    ).slice(0, 5);
  }, [productSearchTerm, availableProducts]);

  const handleAddInternalProduct = (product: Product) => {
    setQuotationItems(prev => {
      const existing = prev.find(item => item.id === product.id && !item.isExternal);
      if (existing) {
        return prev.map(item => item.id === product.id && !item.isExternal ? { ...item, cartQuantity: item.cartQuantity + 1 } : item);
      }
      const newQuotationCartItem: QuotationCartItem = {
        id: product.id,
        name: product.name,
        price: product.price,
        quantityInStock: product.quantityInStock,
        sku: product.sku,
        imageUrl: product.imageUrl, // This is "products/filename.ext"
        category: product.category,
        expiryDate: product.expiryDate,
        cartQuantity: 1,
        customPrice: product.price,
        isExternal: false,
      };
      return [...prev, newQuotationCartItem];
    });
    setProductSearchTerm('');
  };

  const handleAddExternalItem = () => {
    if (!externalItemForm.name.trim() || externalItemForm.price <= 0 || externalItemForm.quantity <= 0) {
      toast({ title: "Invalid External Item", description: "Please provide name, positive price, and quantity.", variant: "destructive" });
      return;
    }
    const newItem: QuotationCartItem = {
      id: `ext-${Date.now()}-${externalItemForm.sku || externalItemForm.name.replace(/\s+/g, '-')}`,
      name: externalItemForm.name,
      price: externalItemForm.price,
      quantityInStock: Infinity,
      sku: externalItemForm.sku || `EXT-${externalItemForm.name.substring(0,3).toUpperCase()}`,
      cartQuantity: externalItemForm.quantity,
      customPrice: externalItemForm.price,
      isExternal: true,
      imageUrl: undefined, // External items won't have an imageUrl from our system
    };
    setQuotationItems(prev => [...prev, newItem]);
    setExternalItemForm({ name: '', sku: '', price: 0, quantity: 1 });
    setIsAddingExternal(false);
  };

  const updateItemQuantity = (itemId: string, isExternalItem: boolean, newQuantity: number) => {
    setQuotationItems(prev =>
      prev.map(item =>
        item.id === itemId && item.isExternal === isExternalItem
          ? { ...item, cartQuantity: Math.max(1, newQuantity) }
          : item
      )
    );
  };

  const updateItemPrice = (itemId: string, isExternalItem: boolean, newPrice: number) => {
    setQuotationItems(prev =>
      prev.map(item =>
        item.id === itemId && item.isExternal === isExternalItem
          ? { ...item, customPrice: Math.max(0, newPrice) }
          : item
      )
    );
  };

  const removeItem = (itemId: string, isExternalItem: boolean) => {
    setQuotationItems(prev => prev.filter(item => !(item.id === itemId && item.isExternal === isExternalItem)));
  };

  const totalAmount = useMemo(() => {
    return quotationItems.reduce((sum, item) => sum + (item.customPrice || item.price) * item.cartQuantity, 0);
  }, [quotationItems]);

  const handleSaveAndPrint = async () => {
    if (!currentUser) {
      toast({ title: "Error", description: "You must be logged in.", variant: "destructive" });
      return;
    }
    if (quotationItems.length === 0) {
      toast({ title: "Empty Quotation", description: "Please add items to the quotation.", variant: "destructive" });
      return;
    }
    if (!customerPhone.trim()) {
      toast({ title: "Missing Information", description: "Customer phone number is required.", variant: "destructive" });
      return;
    }
    if (!validUntil) {
      toast({ title: "Missing Information", description: "Quotation validity date is required.", variant: "destructive" });
      return;
    }

    setIsLoading(true);

    let targetStatusForSave: QuotationStatus = 'draft';
    if (initialQuotation) {
        if (initialQuotation.status === 'draft' || initialQuotation.status === 'revision') {
            targetStatusForSave = initialQuotation.status;
        } else {
            targetStatusForSave = 'draft';
        }
    }


    const quotationData = {
      salespersonId: currentUser.id,
      customerName, customerPhone, customerEmail, customerAddress,
      preparationDays: Number(preparationDays) || 0,
      validUntil: format(validUntil, "yyyy-MM-dd'T'HH:mm:ss.SSSxxx"),
      status: targetStatusForSave, 
      totalAmount,
      notes,
      items: quotationItems.map(item => ({
        productId: !item.isExternal ? item.id : undefined,
        productName: item.name,
        productSku: item.sku,
        price: item.customPrice || item.price,
        quantity: item.cartQuantity,
        isExternal: item.isExternal,
      })),
    };

    try {
      let result;
      if (initialQuotation?.id) {
        result = await updateQuotation({ ...quotationData, id: initialQuotation.id });
      } else {
        result = await addQuotation(quotationData);
      }

      if (result) {
        toast({ title: `Quotation ${initialQuotation ? 'Updated' : 'Saved'}`, description: `Quotation ${result.id} saved as ${result.status}. Redirecting to view/print.`, className:"bg-accent text-accent-foreground" });
        router.push(`/salesperson/quotations/${result.id}/view`); 
      }
    } catch (error:any) {
      toast({ title: "Save Failed", description: error.message || "An unexpected error occurred.", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Customer Information</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <InputWithLabel label="Customer Name" value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Enter customer name" />
          <InputWithLabel label="Customer Phone" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} placeholder="Enter customer phone (required)" required />
          <InputWithLabel label="Customer Email" type="email" value={customerEmail} onChange={(e) => setCustomerEmail(e.target.value)} placeholder="Enter customer email" />
          <InputWithLabel label="Customer Address" value={customerAddress} onChange={(e) => setCustomerAddress(e.target.value)} placeholder="Enter customer address" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Quotation Terms</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <InputWithLabel type="number" label="Preparation Days" value={preparationDays.toString()} onChange={(e) => setPreparationDays(Number(e.target.value))} min="0" />
          <div className="space-y-1">
            <Label>Valid Until</Label>
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" className={cn("w-full justify-start text-left font-normal h-10", !validUntil && "text-muted-foreground")}>
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {validUntil ? format(validUntil, 'PPP') : <span>Pick a date</span>}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0"><Calendar mode="single" selected={validUntil} onSelect={setValidUntil} initialFocus disabled={(date) => date < new Date(new Date().setHours(0,0,0,0))} /></PopoverContent>
            </Popover>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Items</CardTitle></CardHeader>
        <CardContent>
          <div className="mb-4 space-y-2">
            <Label>Add Internal Product</Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input placeholder="Search by name or SKU..." value={productSearchTerm} onChange={e => setProductSearchTerm(e.target.value)} className="pl-10" />
            </div>
            {productSearchTerm && filteredProducts.length > 0 && (
              <ScrollArea className="h-32 border rounded-md">
                {filteredProducts.map(p => (
                  <div key={p.id} className="p-2 hover:bg-accent cursor-pointer flex justify-between items-center" onClick={() => handleAddInternalProduct(p)}>
                    <span>{p.name} ({p.sku}) - OMR {p.price.toFixed(2)}</span>
                    <PlusCircle className="h-5 w-5 text-primary" />
                  </div>
                ))}
              </ScrollArea>
            )}
          </div>

          <Button variant="outline" onClick={() => setIsAddingExternal(!isAddingExternal)} className="mb-4 w-full">
            {isAddingExternal ? 'Cancel External Item' : '+ Add External/Custom Item'}
          </Button>
          {isAddingExternal && (
            <div className="p-4 border rounded-md space-y-3 mb-4 bg-muted/50">
              <InputWithLabel label="Item Name" value={externalItemForm.name} onChange={e => setExternalItemForm(prev => ({ ...prev, name: e.target.value }))} placeholder="External item name" />
              <InputWithLabel label="Item SKU/ID (Optional)" value={externalItemForm.sku} onChange={e => setExternalItemForm(prev => ({ ...prev, sku: e.target.value }))} placeholder="Identifier if any" />
              <InputWithLabel type="number" label="Price (OMR)" value={externalItemForm.price.toString()} onChange={e => setExternalItemForm(prev => ({ ...prev, price: parseFloat(e.target.value) || 0 }))} />
              <InputWithLabel type="number" label="Quantity" value={externalItemForm.quantity.toString()} onChange={e => setExternalItemForm(prev => ({ ...prev, quantity: parseInt(e.target.value) || 1 }))} min="1" />
              <Button onClick={handleAddExternalItem} className="w-full">Add External Item to Quotation</Button>
            </div>
          )}

          {quotationItems.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">No items in quotation yet.</p>
          ) : (
            <ScrollArea className="h-64 border rounded-md">
              {quotationItems.map(item => (
                <div key={`${item.id}-${item.isExternal}`} className="p-3 border-b flex items-start gap-3">
                  {item.imageUrl && !item.isExternal ? (
                    <Image src={`/api/uploads/${item.imageUrl}`} alt={item.name} width={48} height={48} className="w-12 h-12 object-cover rounded" data-ai-hint="product item" unoptimized={true} onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/48x48.png'; (e.target as HTMLImageElement).srcset = ''; }}/>
                  ) : (
                    <div className="w-12 h-12 flex items-center justify-center bg-muted rounded"><Package className="w-6 h-6 text-muted-foreground" /></div>
                  )}
                  <div className="flex-grow space-y-1">
                    <p className="font-semibold text-sm">{item.name} {item.isExternal && <Badge variant="outline" className="text-xs ml-1">External</Badge>}</p>
                    <p className="text-xs text-muted-foreground">SKU: {item.sku || 'N/A'}</p>
                     <div className="flex items-center gap-2">
                       <Label htmlFor={`price-${item.id}`} className="text-xs">Price:</Label>
                       <Input type="number" id={`price-${item.id}`} value={item.customPrice ?? item.price} onChange={e => updateItemPrice(item.id, item.isExternal, parseFloat(e.target.value))} className="h-7 w-20 text-xs" />
                     </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                     <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => updateItemQuantity(item.id, item.isExternal, item.cartQuantity - 1)}><MinusCircle className="h-4 w-4" /></Button>
                        <Input type="number" value={item.cartQuantity} onChange={e => updateItemQuantity(item.id, item.isExternal, parseInt(e.target.value))} className="h-7 w-12 text-center text-xs" />
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => updateItemQuantity(item.id, item.isExternal, item.cartQuantity + 1)}><PlusCircle className="h-4 w-4" /></Button>
                    </div>
                    <p className="text-sm font-medium">OMR {((item.customPrice || item.price) * item.cartQuantity).toFixed(2)}</p>
                    <Button variant="ghost" size="icon" className="h-6 w-6 text-destructive" onClick={() => removeItem(item.id, item.isExternal)}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                </div>
              ))}
            </ScrollArea>
          )}
        </CardContent>
         {quotationItems.length > 0 && (
            <CardFooter className="border-t pt-4">
                <div className="w-full flex justify-end items-center">
                    <span className="text-xl font-bold text-primary">Total: OMR {totalAmount.toFixed(2)}</span>
                </div>
            </CardFooter>
         )}
      </Card>

      <Card>
        <CardHeader><CardTitle>Notes</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <TextareaWithLabel label="Additional Notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Any specific terms, conditions, or comments..." />
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3 pt-4">
        <Button type="button" variant="outline" onClick={() => router.back()} disabled={isLoading}>
          <X className="mr-2 h-4 w-4" /> Cancel
        </Button>
        <Button onClick={handleSaveAndPrint} disabled={isLoading || quotationItems.length === 0} className="min-w-[150px]">
          {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Printer className="mr-2 h-4 w-4" />}
          Save and Print
        </Button>
      </div>
    </div>
  );
}

const InputWithLabel = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement> & { label: string }>(({ label, id, ...props }, ref) => {
  const inputId = id || `input-${label.toLowerCase().replace(/\s+/g, '-')}`;
  return (
    <div className="space-y-1">
      <Label htmlFor={inputId}>{label}</Label>
      <Input id={inputId} ref={ref} {...props} />
    </div>
  );
});
InputWithLabel.displayName = 'InputWithLabel';

const TextareaWithLabel = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string }>(({ label, id, ...props }, ref) => {
  const textareaId = id || `textarea-${label.toLowerCase().replace(/\s+/g, '-')}`;
  return (
    <div className="space-y-1">
      <Label htmlFor={textareaId}>{label}</Label>
      <Textarea id={textareaId} ref={ref} {...props} />
    </div>
  );
});
TextareaWithLabel.displayName = 'TextareaWithLabel';
