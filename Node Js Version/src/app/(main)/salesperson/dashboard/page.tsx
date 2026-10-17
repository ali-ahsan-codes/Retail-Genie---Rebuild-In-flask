
// src/app/(main)/salesperson/dashboard/page.tsx
'use client';
import { useState, useEffect, useCallback } from 'react';
import type { Product, CartItem, Order, OrderItem, User } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Trash2, PlusCircle, MinusCircle, Search, ShoppingBag, FileText, User as UserIcon, Phone, Home, Percent, Users as UsersIcon, Loader2, Package, AlertTriangle, UserCheck } from 'lucide-react';
import ProductCard from '@/components/ProductCard';
import { useToast } from '@/hooks/use-toast';
import { format, isWithinInterval, parseISO, isValid } from 'date-fns';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogClose } from '@/components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import Image from 'next/image';
import Link from 'next/link';
import { Alert, AlertDescription as UIDescription, AlertTitle as UITitle } from '@/components/ui/alert';

const NONE_SALESPERSON_VALUE = "--NONE--";

export default function SalespersonDashboard() {
  const {
    products,
    users,
    cart,
    addToCart: contextAddToCart,
    removeFromCart,
    updateCartItemQuantity,
    updateCartItemPrice,
    clearCart,
    addOrder,
    currentUser,
    getProductById,
    globalDiscountSetting,
    getTodayAttendanceForUser,
    isDataLoaded,
    isAttendanceCurrentlyRequired, 
  } = useApp();
  const { toast } = useToast();
  const [searchTerm, setSearchTerm] = useState('');
  const [isOrderSubmitModalOpen, setIsOrderSubmitModalOpen] = useState(false);
  const [isSubmittingOrder, setIsSubmittingOrder] = useState(false);

  const [customerName, setCustomerName] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [deliveryAddress, setDeliveryAddress] = useState('');

  const [secondarySalespersonId, setSecondarySalespersonId] = useState<string>(NONE_SALESPERSON_VALUE);
  const [primaryCommissionPercentage, setPrimaryCommissionPercentage] = useState<number>(100);
  const [secondaryCommissionPercentage, setSecondaryCommissionPercentage] = useState<number>(0);

  const [hasClockedInToday, setHasClockedInToday] = useState<boolean | null>(null);
  const [mustClockIn, setMustClockIn] = useState(false); 

  const availableSalespeople = users.filter(u => u.role === 'salesperson' && u.id !== currentUser?.id);

  useEffect(() => {
    if (currentUser && isDataLoaded) {
      const attendanceLog = getTodayAttendanceForUser(currentUser.id);
      setHasClockedInToday(!!attendanceLog);
      setMustClockIn(isAttendanceCurrentlyRequired(currentUser.role) && !attendanceLog);
    }
  }, [currentUser, getTodayAttendanceForUser, isDataLoaded, isAttendanceCurrentlyRequired]);


  useEffect(() => {
    if (secondarySalespersonId === NONE_SALESPERSON_VALUE) {
      if (primaryCommissionPercentage !== 100 || secondaryCommissionPercentage !== 0) {
        setPrimaryCommissionPercentage(100);
        setSecondaryCommissionPercentage(0);
      }
    }
  }, [secondarySalespersonId, primaryCommissionPercentage, secondaryCommissionPercentage]);


  const handlePrimaryCommissionChange = useCallback((value: string) => {
    const newPrimary = parseInt(value, 10);
    if (!isNaN(newPrimary) && newPrimary >= 0 && newPrimary <= 100) {
      setPrimaryCommissionPercentage(newPrimary);
      if (secondarySalespersonId !== NONE_SALESPERSON_VALUE) {
        setSecondaryCommissionPercentage(100 - newPrimary);
      } else {
        setSecondaryCommissionPercentage(0);
      }
    }
  }, [secondarySalespersonId]);

  const handleSecondaryCommissionChange = useCallback((value: string) => {
    const newSecondary = parseInt(value, 10);
    if (!isNaN(newSecondary) && newSecondary >= 0 && newSecondary <= 100) {
      setSecondaryCommissionPercentage(newSecondary);
      if (secondarySalespersonId !== NONE_SALESPERSON_VALUE) {
        setPrimaryCommissionPercentage(100 - newSecondary);
      }
    }
  }, [secondarySalespersonId]);


  const handleAddToCart = useCallback((product: Product, quantity: number) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in from your profile page. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    const cartItem = cart.find(item => item.id === product.id);
    const newQuantity = (cartItem?.cartQuantity || 0) + quantity;

    const stockProduct = getProductById(product.id);
    if (!stockProduct) {
      toast({ title: 'Error', description: 'Product not found.', variant: 'destructive' });
      return;
    }

    if (newQuantity > stockProduct.quantityInStock) {
      toast({
        title: 'Stock Limit Reached',
        description: `Cannot add more ${product.name}. Only ${stockProduct.quantityInStock - (cartItem?.cartQuantity || 0)} more available.`,
        variant: 'destructive',
      });
      return;
    }
    contextAddToCart(product, quantity);
    toast({
      title: `${product.name} added`,
      description: `${quantity} unit(s) added to cart.`,
    });
  }, [cart, getProductById, contextAddToCart, toast, mustClockIn]);

  const handleUpdateQuantity = useCallback((productId: string, newQuantity: number) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in from your profile page. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    const product = getProductById(productId);
    if (product && newQuantity > product.quantityInStock) {
       toast({
        title: 'Stock Limit Reached',
        description: `Cannot set quantity for ${product.name} to ${newQuantity}. Only ${product.quantityInStock} available.`,
        variant: 'destructive',
      });
      updateCartItemQuantity(productId, product.quantityInStock);
      return;
    }
    if (newQuantity <= 0) {
      removeFromCart(productId);
    } else {
      updateCartItemQuantity(productId, newQuantity);
    }
  }, [getProductById, toast, updateCartItemQuantity, removeFromCart, mustClockIn]);

  const handlePriceChange = useCallback((productId: string, newPrice: number) => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in from your profile page. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    updateCartItemPrice(productId, newPrice);
     toast({
      title: `Price Updated`,
      description: `Price for item ${getProductById(productId)?.name} set to OMR ${newPrice.toFixed(2)}.`,
    });
  }, [updateCartItemPrice, toast, getProductById, mustClockIn]);

  const filteredProducts = products.filter(product =>
    product.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    product.sku.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const cartSubtotal = cart.reduce((sum, item) => sum + (item.customPrice ?? item.price) * item.cartQuantity, 0);

  let activeGlobalDiscountAmount = 0;
  let activeGlobalDiscountPercentage = 0;
  let isGlobalDiscountActiveNow = false;

  if (globalDiscountSetting && globalDiscountSetting.isActive) {
    const today = new Date();
    const startDateString = globalDiscountSetting.startDate;
    const endDateString = globalDiscountSetting.endDate;

    const startDate = startDateString && isValid(parseISO(startDateString)) ? parseISO(startDateString) : null;
    const endDate = endDateString && isValid(parseISO(endDateString)) ? parseISO(endDateString) : null;

    isGlobalDiscountActiveNow =
      (!startDate || today >= startDate) &&
      (!endDate || today <= endDate);

    if (isGlobalDiscountActiveNow) {
      activeGlobalDiscountPercentage = globalDiscountSetting.percentage;
      activeGlobalDiscountAmount = cartSubtotal * (activeGlobalDiscountPercentage / 100);
    }
  }

  const cartTotal = cartSubtotal - activeGlobalDiscountAmount;

  const prepareOrderSubmission = useCallback(() => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in from your profile page. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    if (cart.length === 0) {
        toast({title: "Cart Empty", description: "Please add items to the cart before submitting.", variant: "destructive"});
        return;
    }
    setSecondarySalespersonId(NONE_SALESPERSON_VALUE);
    setPrimaryCommissionPercentage(100);
    setSecondaryCommissionPercentage(0);
    setIsOrderSubmitModalOpen(true);
  }, [cart.length, toast, mustClockIn]);


  const handleSubmitOrder = useCallback(async () => {
    if (mustClockIn) {
        toast({ title: "Attendance Required", description: "Please clock in from your profile page. Mandatory attendance time has passed.", variant: "destructive"});
        return;
    }
    if (!currentUser || cart.length === 0) {
      toast({
        title: 'Cannot submit order',
        description: !currentUser ? 'No user logged in.' : 'Cart is empty.',
        variant: 'destructive',
      });
      return;
    }
     if (!customerName.trim() || !customerPhone.trim()) {
      toast({
        title: "Missing Customer Details",
        description: "Please enter customer name and phone number.",
        variant: 'destructive',
      });
      return;
    }

    if (secondarySalespersonId !== NONE_SALESPERSON_VALUE && (primaryCommissionPercentage + secondaryCommissionPercentage !== 100)) {
        toast({
            title: "Commission Split Error",
            description: "Primary and Secondary commission percentages must sum to 100%.",
            variant: "destructive"
        });
        return;
    }

    setIsSubmittingOrder(true);

    const orderItems: OrderItem[] = cart.map(item => ({
      productId: item.id,
      name: item.name,
      sku: item.sku,
      quantity: item.cartQuantity,
      pricePerUnit: item.customPrice ?? item.price,
      totalPrice: (item.customPrice ?? item.price) * item.cartQuantity,
    }));

    const orderDataPayload = {
      items: orderItems,
      subtotal: cartSubtotal,
      discountAmount: 0,
      taxes: [],
      totalAmount: cartTotal,
      customerName: customerName.trim(),
      customerPhone: customerPhone.trim(),
      deliveryAddress: deliveryAddress.trim() || undefined,
      secondarySalespersonId: secondarySalespersonId === NONE_SALESPERSON_VALUE ? undefined : secondarySalespersonId,
      primarySalespersonCommission: primaryCommissionPercentage / 100,
      secondarySalespersonCommission: secondarySalespersonId === NONE_SALESPERSON_VALUE ? undefined : secondaryCommissionPercentage / 100,
    };


    try {
      const createdOrder = await addOrder(orderDataPayload as any);

      if (createdOrder) {
          clearCart();
          setCustomerName('');
          setCustomerPhone('');
          setDeliveryAddress('');
          setSecondarySalespersonId(NONE_SALESPERSON_VALUE);
          setPrimaryCommissionPercentage(100);
          setSecondaryCommissionPercentage(0);
          setIsOrderSubmitModalOpen(false);
          toast({
            title: 'Order Submitted!',
            description: `Invoice ${createdOrder.id} created. Pending payment and processing.`,
            className: 'bg-accent text-accent-foreground border-accent'
          });
      } else {
           toast({
              title: 'Order Submission Failed',
              description: 'Could not create the order. Please try again.',
              variant: 'destructive'
          });
      }
    } catch (error) {
       toast({
          title: 'Order Submission Error',
          description: 'An unexpected error occurred.',
          variant: 'destructive'
      });
    } finally {
      setIsSubmittingOrder(false);
    }
  }, [currentUser, cart, customerName, customerPhone, deliveryAddress, secondarySalespersonId, primaryCommissionPercentage, secondaryCommissionPercentage, cartSubtotal, cartTotal, addOrder, clearCart, toast, mustClockIn]);

  if (!isDataLoaded || hasClockedInToday === null) {
    return (
        <div className="flex flex-col items-center justify-center h-full p-8">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">Loading dashboard and checking attendance...</p>
        </div>
    );
  }

  if (currentUser?.role !== 'salesperson' && currentUser?.role !== 'admin' && currentUser?.role !== 'manager') {
    return <div className="p-4">Access Denied. This dashboard is for Salespersons, Admins, and Managers.</div>;
  }


  if (mustClockIn) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <Alert variant="destructive" className="max-w-md text-left">
          <AlertTriangle className="h-5 w-5" />
          <UITitle>Mandatory Attendance Required</UITitle>
          <UIDescription>
            The mandatory attendance time has passed. You must clock in before you can access the sales dashboard.
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
    <div className="flex flex-col lg:flex-row gap-6 h-[calc(100vh-theme(spacing.24))] ">
      {/* Product Selection Area */}
      <div className="lg:w-2/3 flex flex-col">
        <Card className="shadow-md flex-shrink-0">
          <CardHeader>
            <CardTitle className="text-2xl flex items-center">
              <ShoppingBag className="mr-2 h-6 w-6 text-primary" /> Product Catalog
            </CardTitle>
            <div className="flex items-center gap-2 mt-2">
              <div className="relative flex-grow">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                  type="search"
                  placeholder="Search products by name or Product Code..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10 h-10"
                  disabled={mustClockIn}
                />
              </div>
            </div>
          </CardHeader>
        </Card>
        <ScrollArea className="flex-grow mt-4 rounded-lg border bg-card p-1">
            {filteredProducts.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 p-3">
              {filteredProducts.map((product) => (
                <ProductCard
                  key={product.id}
                  product={product}
                  onAddToCart={handleAddToCart}
                  allowPriceEdit={true}
                  currentPrice={cart.find(ci => ci.id === product.id)?.customPrice}
                  onPriceChange={(newPrice) => handlePriceChange(product.id, newPrice)}
                />
              ))}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full p-8 text-center">
                <Search className="w-16 h-16 text-muted-foreground mb-4" />
                <p className="text-xl font-semibold">No products found</p>
                <p className="text-muted-foreground">Try adjusting your search term or adding new products.</p>
              </div>
            )}
        </ScrollArea>
      </div>

      {/* Digital Cart Area */}
      <div className="lg:w-1/3 flex flex-col">
        <Card className="shadow-md flex-grow flex flex-col">
          <CardHeader>
            <CardTitle className="text-2xl flex items-center">
              <FileText className="mr-2 h-6 w-6 text-primary" /> Digital Cart
            </CardTitle>
          </CardHeader>
          <ScrollArea className="flex-grow">
            <CardContent className="space-y-3 p-4">
              {cart.length === 0 ? (
                <p className="text-muted-foreground text-center py-8">Your cart is empty. Add products to get started.</p>
              ) : (
                cart.map((item) => (
                  <div key={item.id} className="flex items-start gap-3 p-3 border rounded-md bg-background/50">
                    {item.imageUrl ? (
                      <Image
                        src={item.imageUrl}
                        alt={item.name}
                        width={64}
                        height={64}
                        className="w-16 h-16 object-cover rounded-md"
                        data-ai-hint="product item"
                      />
                    ) : (
                      <div className="w-16 h-16 flex items-center justify-center bg-muted rounded-md">
                        <Package className="w-8 h-8 text-muted-foreground" />
                      </div>
                    )}
                    <div className="flex-grow">
                      <h4 className="font-semibold text-sm">{item.name}</h4>
                      <p className="text-xs text-muted-foreground">Product Code: {item.sku}</p>
                      <div className="flex items-center mt-1">
                        <span className="text-xs mr-1">Price: OMR</span>
                        <Input
                          type="number"
                          value={item.customPrice ?? item.price}
                          onChange={(e) => handlePriceChange(item.id, parseFloat(e.target.value))}
                          className="h-7 w-20 text-xs"
                          min="0"
                          step="0.01"
                          disabled={mustClockIn}
                        />
                      </div>
                      <div className="flex items-center gap-1 mt-1">
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleUpdateQuantity(item.id, item.cartQuantity - 1)} disabled={mustClockIn}>
                          <MinusCircle className="h-4 w-4" />
                        </Button>
                        <Input
                            type="number"
                            value={item.cartQuantity}
                            onChange={(e) => handleUpdateQuantity(item.id, parseInt(e.target.value))}
                            className="h-7 w-12 text-center text-xs"
                            min="1"
                            max={getProductById(item.id)?.quantityInStock || 0}
                            disabled={mustClockIn}
                        />
                        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleUpdateQuantity(item.id, item.cartQuantity + 1)}
                          disabled={item.cartQuantity >= (getProductById(item.id)?.quantityInStock || 0) || mustClockIn}>
                          <PlusCircle className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <div className="text-right">
                       <p className="font-semibold text-sm">OMR {((item.customPrice ?? item.price) * item.cartQuantity).toFixed(2)}</p>
                       <Button variant="ghost" size="icon" className="h-7 w-7 mt-2 text-destructive hover:text-destructive" onClick={() => removeFromCart(item.id)} disabled={mustClockIn}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </CardContent>
          </ScrollArea>
          {cart.length > 0 && (
            <CardFooter className="flex flex-col gap-2 border-t p-4">
              <div className="w-full flex justify-between text-sm">
                <span>Subtotal:</span>
                <span className="font-semibold">OMR {cartSubtotal.toFixed(2)}</span>
              </div>
              {isGlobalDiscountActiveNow && activeGlobalDiscountAmount > 0 && (
                <div className="w-full flex justify-between text-sm text-destructive">
                    <span className="flex items-center"><Percent className="h-4 w-4 mr-1"/> Global Discount ({activeGlobalDiscountPercentage}%):</span>
                    <span className="font-semibold">- OMR {activeGlobalDiscountAmount.toFixed(2)}</span>
                </div>
              )}
              <Separator className="my-1" />
              <div className="w-full flex justify-between text-lg font-bold text-primary">
                <span>Total:</span>
                <span>OMR {cartTotal.toFixed(2)}</span>
              </div>
              {isGlobalDiscountActiveNow && globalDiscountSetting?.description && (
                 <p className="text-xs text-center text-green-600 font-medium w-full">
                    🎉 {globalDiscountSetting.description} applied! 🎉
                </p>
              )}
              <div className="flex gap-2 w-full mt-2">
                <Button variant="outline" onClick={clearCart} className="flex-1" disabled={isSubmittingOrder || mustClockIn}>
                  Clear Cart
                </Button>
                <Button
                  onClick={prepareOrderSubmission}
                  className="flex-1 bg-accent hover:bg-accent/90 text-accent-foreground"
                  disabled={isSubmittingOrder || mustClockIn}
                >
                  {isSubmittingOrder ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Submitting...</>
                  ) : (
                    "Submit Order"
                  )}
                </Button>
              </div>
            </CardFooter>
          )}
        </Card>
      </div>
      <Dialog open={isOrderSubmitModalOpen} onOpenChange={(isOpen) => { if (!isSubmittingOrder) setIsOrderSubmitModalOpen(isOpen); }}>
        <DialogContent className="sm:max-w-lg">
            <DialogHeader>
                <DialogTitle>Customer &amp; Commission Details</DialogTitle>
                <DialogDescription>Provide customer information and optionally split commission with another salesperson.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
                <div className="space-y-1">
                    <Label htmlFor="customer-name" className="flex items-center"><UserIcon className="mr-2 h-4 w-4 text-muted-foreground" />Customer Name</Label>
                    <Input id="customer-name" value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Full Name" />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="customer-phone" className="flex items-center"><Phone className="mr-2 h-4 w-4 text-muted-foreground" />Customer Phone</Label>
                    <Input id="customer-phone" type="tel" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} placeholder="e.g., 9xxxxxxx" />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="delivery-address" className="flex items-center"><Home className="mr-2 h-4 w-4 text-muted-foreground" />Delivery Address (Optional)</Label>
                    <Input id="delivery-address" value={deliveryAddress} onChange={(e) => setDeliveryAddress(e.target.value)} placeholder="Street, City, Area" />
                </div>
                <Separator className="my-2" />
                <h3 className="text-md font-semibold flex items-center"><UsersIcon className="mr-2 h-4 w-4 text-muted-foreground" />Sales Commission Split (Optional)</h3>
                 <div className="space-y-1">
                    <Label htmlFor="secondary-salesperson">Secondary Salesperson</Label>
                     <Select value={secondarySalespersonId} onValueChange={setSecondarySalespersonId}>
                        <SelectTrigger id="secondary-salesperson">
                            <SelectValue placeholder="Select secondary salesperson" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value={NONE_SALESPERSON_VALUE}>None</SelectItem>
                            {availableSalespeople.map(sp => (
                                <SelectItem key={sp.id} value={sp.id}>{sp.username}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                {secondarySalespersonId !== NONE_SALESPERSON_VALUE && (
                    <div className="grid grid-cols-2 gap-4">
                         <div className="space-y-1">
                            <Label htmlFor="primary-commission" className="flex items-center"><Percent className="mr-1 h-3 w-3" />Your Commission (%)</Label>
                            <Input id="primary-commission" type="number" value={primaryCommissionPercentage} onChange={(e) => handlePrimaryCommissionChange(e.target.value)} min="0" max="100" />
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="secondary-commission" className="flex items-center"><Percent className="mr-1 h-3 w-3" />Secondary's Commission (%)</Label>
                            <Input id="secondary-commission" type="number" value={secondaryCommissionPercentage} onChange={(e) => handleSecondaryCommissionChange(e.target.value)} min="0" max="100" />
                        </div>
                    </div>
                )}
                 {secondarySalespersonId !== NONE_SALESPERSON_VALUE && (primaryCommissionPercentage + secondaryCommissionPercentage !== 100) && (
                    <p className="text-xs text-destructive">Total commission must be 100%.</p>
                )}

            </div>
            <DialogFooter>
                <DialogClose asChild><Button variant="outline" disabled={isSubmittingOrder}>Cancel</Button></DialogClose>
                <Button
                    onClick={handleSubmitOrder}
                    disabled={
                        isSubmittingOrder ||
                        !customerName.trim() ||
                        !customerPhone.trim() ||
                        (secondarySalespersonId !== NONE_SALESPERSON_VALUE && primaryCommissionPercentage + secondaryCommissionPercentage !== 100)
                    }
                >
                 {isSubmittingOrder ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Submitting...</>
                  ) : (
                    "Confirm & Submit Order"
                  )}
                </Button>
            </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
    
