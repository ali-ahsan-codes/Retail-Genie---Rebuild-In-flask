
'use client';
import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import type { Order, PaymentDetail, PaymentMethod, AppliedTax, TaxSetting, DemandNotice, OrderStatus, Product, DemandNoticeStatus } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Search, Info, DollarSign, CreditCard, Banknote, Landmark, XCircle, PlusCircle, Receipt, ListChecks, Percent as PercentIcon, Tag, BellRing, Calculator, Eye, WalletCards, CheckCircle as CheckCircleIcon, Loader2, ShoppingBag, Printer } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/hooks/use-toast';
import InvoiceModal from '@/components/InvoiceModal';
import { format, parseISO, isValid, isSameDay, setHours, setMinutes, setSeconds, setMilliseconds, parse } from 'date-fns';
import { Alert, AlertDescription as UIDescription, AlertTitle as UITitle } from '@/components/ui/alert';
import CashierShiftSummary from '@/components/cashier/CashierShiftSummary';
import DemandNoticeReceiptModal from '@/components/cashier/DemandNoticeReceiptModal';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface SuggestionItem {
  id: string;
  type: 'order' | 'demand_notice';
  matchScore: number;
  statusText?: string;
  statusColorClass?: string;
  createdAt: string;
  customerName?: string;
  customerPhone?: string;
  productName?: string; // for DN
  productSku?: string; // for DN
}

export default function CashierDashboard() {
  const {
    orders,
    currentUser,
    getOrderById: getOrderByIdFromContext,
    taxSettings,
    demandNotices: allDemandNotices,
    addAdvancePaymentToDemandNotice,
    updateOrderAndRefreshContext,
    getProductById,
  } = useApp();
  const { toast } = useToast();

  const [globalSearchTerm, setGlobalSearchTerm] = useState('');
  const [suggestions, setSuggestions] = useState<SuggestionItem[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchBarRef = useRef<HTMLInputElement>(null);
  const suggestionListRef = useRef<HTMLDivElement>(null);
  const searchButtonRef = useRef<HTMLButtonElement>(null);
  const processedOrderIdRef = useRef<string | null>(null);


  const [currentOrder, setCurrentOrder] = useState<Order | null>(null);
  const [manualDiscountAmountInput, setManualDiscountAmountInput] = useState('0');
  const [manualDiscountPercentageInput, setManualDiscountPercentageInput] = useState('0');
  const [payments, setPayments] = useState<PaymentDetail[]>([{ method: 'cash', amount: 0 }]);
  const [showInvoiceModal, setShowInvoiceModal] = useState(false);
  const [processedOrder, setProcessedOrder] = useState<Order | null>(null);
  const [selectedTaxes, setSelectedTaxes] = useState<Record<string, boolean>>({});
  const [orderCashReceived, setOrderCashReceived] = useState('');
  const [viewingInvoice, setViewingInvoice] = useState<Order | null>(null);
  const [isProcessingPayment, setIsProcessingPayment] = useState(false);

  const [currentDemandNotice, setCurrentDemandNotice] = useState<DemandNotice | null>(null);
  const [advancePaymentAmount, setAdvancePaymentAmount] = useState('0');
  const [advancePaymentMethod, setAdvancePaymentMethod] = useState<PaymentMethod>('cash');
  const [advancePaymentTransactionId, setAdvancePaymentTransactionId] = useState('');
  const [isProcessingDnPayment, setIsProcessingDnPayment] = useState(false);
  const [dnCashReceived, setDnCashReceived] = useState('');
  const [viewingDnReceipt, setViewingDnReceipt] = useState<DemandNotice | null>(null);
  const [showDnReceiptModal, setShowDnReceiptModal] = useState(false);

  const resetOrderPaymentForm = useCallback((keepSearchTerm = false) => {
    setCurrentOrder(null);
    setManualDiscountAmountInput('0');
    setManualDiscountPercentageInput('0');
    setPayments([{ method: 'cash', amount: 0 }]);
    setSelectedTaxes({});
    setOrderCashReceived('');
    if (!keepSearchTerm) setGlobalSearchTerm('');
  }, []);

  const resetDnAdvanceForm = useCallback((keepSearchTerm = false) => {
    setCurrentDemandNotice(null);
    setAdvancePaymentAmount('0');
    setAdvancePaymentMethod('cash');
    setAdvancePaymentTransactionId('');
    setDnCashReceived('');
    if (!keepSearchTerm) setGlobalSearchTerm('');
  }, []);
  
  const resetAllFormsExceptSearch = useCallback(() => {
    setCurrentOrder(null);
    setManualDiscountAmountInput('0');
    setManualDiscountPercentageInput('0');
    setPayments([{ method: 'cash', amount: 0 }]);
    setSelectedTaxes({});
    setOrderCashReceived('');
    
    setCurrentDemandNotice(null);
    setAdvancePaymentAmount('0');
    setAdvancePaymentMethod('cash');
    setAdvancePaymentTransactionId('');
    setDnCashReceived('');
  }, []);


  const resetAllForms = useCallback(() => {
    setGlobalSearchTerm('');
    resetOrderPaymentForm();
    resetDnAdvanceForm();
    setSuggestions([]);
    setShowSuggestions(false);
  }, [resetOrderPaymentForm, resetDnAdvanceForm]);

  const generateSuggestions = useCallback((searchTerm: string): SuggestionItem[] => {
    if (!searchTerm.trim()) return [];
    const term = searchTerm.toLowerCase();
    const isNumericTerm = /^\d+$/.test(term);
    const isShortNumeric = isNumericTerm && term.length >= 2 && term.length <= 4;

    const getOrderPaymentStatusInfo = (order: Order): { text: string; colorClass: string } => {
        const totalPaid = (order.payments || []).reduce((sum, p) => sum + p.amount, 0);
        if (order.status === 'paid' || order.status === 'completed' || totalPaid >= (order.totalAmount - 0.005)) {
            return { text: 'Paid', colorClass: 'bg-green-100 text-green-800' };
        }
        if (totalPaid > 0) {
            return { text: 'Advance Paid', colorClass: 'bg-yellow-100 text-yellow-800' };
        }
        return { text: 'Not Paid', colorClass: 'bg-red-100 text-red-800' };
    };

    const orderSuggestions = orders
      .map(order => {
        let matchScore = Infinity;
        if (order.id.toLowerCase().includes(term) || (isShortNumeric && order.id.endsWith(term))) matchScore = Math.min(matchScore, 1);
        if (order.customerName && order.customerName.toLowerCase().includes(term)) matchScore = Math.min(matchScore, 2);
        if (order.customerPhone && order.customerPhone.includes(term)) matchScore = Math.min(matchScore, 3);
        if (matchScore === Infinity) return null;

        const paymentStatus = getOrderPaymentStatusInfo(order);
        return { 
            id: order.id, type: 'order' as const, matchScore,
            statusText: paymentStatus.text, statusColorClass: paymentStatus.colorClass,
            createdAt: order.createdAt, customerName: order.customerName, customerPhone: order.customerPhone,
        };
      })
      .filter((item): item is SuggestionItem => item !== null);

    const dnSuggestions = allDemandNotices
      .map(dn => {
        let matchScore = Infinity;
        if (dn.id.toLowerCase().includes(term) || (isShortNumeric && dn.id.endsWith(term))) matchScore = Math.min(matchScore, 1.5);
        if (dn.customerContactNumber && dn.customerContactNumber.includes(term)) matchScore = Math.min(matchScore, 3.5);
        if (dn.productName.toLowerCase().includes(term)) matchScore = Math.min(matchScore, 4);
        if (matchScore === Infinity) return null;

        const totalPaid = (dn.payments || []).reduce((sum, p) => sum + p.amount, 0);
        const totalAgreed = dn.agreedPrice * dn.quantityRequested;
        let statusInfo = { text: 'No Advance', colorClass: 'bg-gray-100 text-gray-800' };
        if (totalPaid >= totalAgreed) {
            statusInfo = { text: 'Fully Paid Advance', colorClass: 'bg-green-100 text-green-800'};
        } else if (totalPaid > 0) {
            statusInfo = { text: 'Partial Advance', colorClass: 'bg-yellow-100 text-yellow-800'};
        }

        return {
            id: dn.id, type: 'demand_notice' as const, matchScore,
            statusText: statusInfo.text, statusColorClass: statusInfo.colorClass,
            createdAt: dn.createdAt, customerName: dn.productName, customerPhone: dn.customerContactNumber, productName: dn.productName, productSku: dn.productSku,
        };
      })
      .filter((item): item is SuggestionItem => item !== null);

    return [...orderSuggestions, ...dnSuggestions]
      .sort((a, b) => a.matchScore - b.matchScore || a.id.localeCompare(b.id))
      .slice(0, 10);
  }, [orders, allDemandNotices]);


  useEffect(() => {
    const newSearchTerm = globalSearchTerm.trim();
    if (newSearchTerm) {
      const newSuggestions = generateSuggestions(newSearchTerm);
      setSuggestions(newSuggestions);
      setShowSuggestions(newSuggestions.length > 0);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, [globalSearchTerm, generateSuggestions]);


  const handleSelectSuggestion = useCallback((suggestion: SuggestionItem) => {
    setGlobalSearchTerm(suggestion.id); 
    setShowSuggestions(false);
    setTimeout(() => {
        if (searchButtonRef.current) {
           searchButtonRef.current.click(); 
        }
    }, 0);
  }, []);


  const handleGlobalSearch = useCallback(async () => {
    const searchTerm = globalSearchTerm.trim();
    if (!searchTerm) {
      resetAllForms();
      return;
    }

    resetAllFormsExceptSearch(); 
    
    let foundOrder = getOrderByIdFromContext(searchTerm);
    if (foundOrder) {
      setCurrentOrder(foundOrder);
      setShowSuggestions(false);
      if (['pending_payment', 'partial_payment', 'ready_for_pickup', 'paid'].includes(foundOrder.status)) {
        toast({ title: "Order Found", description: `Order ${foundOrder.id} loaded for payment processing.` });
      } else {
        toast({ title: "Order Found", description: `Order ${foundOrder.id} loaded. Current status: ${foundOrder.status.replace(/_/g, ' ')}. You can view the invoice.` });
      }
      return;
    }

    let foundNotice = allDemandNotices.find(dn => dn.id.toLowerCase() === searchTerm.toLowerCase());
    if (foundNotice) {
      setShowSuggestions(false);
      if (foundNotice.status === 'ready_for_collection' && foundNotice.linkedOrderId) {
        toast({ title: "DN Ready for Final Payment", description: `Demand Notice ${foundNotice.id} is ready. Linked Sales Order ${foundNotice.linkedOrderId} loaded.`, variant: "default", duration: 7000 });
        const linkedOrder = getOrderByIdFromContext(foundNotice.linkedOrderId);
        if (linkedOrder) setCurrentOrder(linkedOrder);
        else toast({ title: "Error", description: `Linked order ${foundNotice.linkedOrderId} not found.`, variant: "destructive" });
      } else {
        // For all other DN states (including fulfilled, cancelled etc.) just load it.
        setCurrentDemandNotice(foundNotice);
        toast({ title: "Demand Notice Found", description: `DN ${foundNotice.id} (Status: ${foundNotice.status.replace(/_/g, ' ')}) loaded.` });
      }
      return;
    }
    
    const currentSuggestions = generateSuggestions(searchTerm);
    setSuggestions(currentSuggestions);

    if (currentSuggestions.length > 0) {
      setShowSuggestions(true); 
      if (currentSuggestions.length > 1) {
        toast({ title: "Multiple Matches", description: `Multiple items match '${searchTerm}'. Please select from the list or be more specific.`, variant: "default" });
      } else { 
        toast({ title: "Suggestion Found", description: `One item matches '${searchTerm}'. Please review and select if correct.`, variant: "default" });
      }
      searchBarRef.current?.focus();
    } else {
      toast({ title: "Not Found", description: `No matching Order or Demand Notice found for "${searchTerm}".`, variant: "destructive" });
      setShowSuggestions(false);
    }
  }, [globalSearchTerm, getOrderByIdFromContext, allDemandNotices, toast, resetAllForms, resetAllFormsExceptSearch, generateSuggestions]);

  useEffect(() => {
    // Only reset the form if a new order is loaded
    if (currentOrder && currentOrder.id !== processedOrderIdRef.current) {
      setManualDiscountAmountInput((currentOrder.discountAmount || 0).toFixed(2));
      const initialPercentage = currentOrder.appliedDiscountPercentage && currentOrder.appliedDiscountPercentage > 0
                                ? currentOrder.appliedDiscountPercentage
                                : (currentOrder.appliedGlobalDiscountPercentage && currentOrder.appliedGlobalDiscountPercentage > 0
                                  ? currentOrder.appliedGlobalDiscountPercentage
                                  : 0);
      setManualDiscountPercentageInput(initialPercentage.toString());

      const initialSelectedTaxesState: Record<string, boolean> = {};
      const activeSystemTaxes = taxSettings.filter(ts => ts.enabled);

      if (currentOrder.taxes && currentOrder.taxes.length > 0) {
        activeSystemTaxes.forEach(definedTax => {
          initialSelectedTaxesState[definedTax.id] = !!currentOrder.taxes.find(appliedTax => appliedTax.name === definedTax.name && appliedTax.amount > 0);
        });
      } else {
        activeSystemTaxes.forEach(tax => initialSelectedTaxesState[tax.id] = true);
      }
      setSelectedTaxes(initialSelectedTaxesState);

      const subtotal = currentOrder.subtotal || currentOrder.items.reduce((sum, item) => sum + item.totalPrice, 0);
      const orderDiscount = currentOrder.discountAmount || 0;
      const subtotalAfterOrderDiscount = subtotal - orderDiscount;

      const taxesForInitial = activeSystemTaxes.reduce((sum, tax) => {
        return sum + (initialSelectedTaxesState[tax.id] ? (subtotalAfterOrderDiscount * tax.rate) : 0);
      }, 0);

      const initialTotalDueForOrder = subtotalAfterOrderDiscount + taxesForInitial;
      const alreadyPaidOnOrder = currentOrder.payments?.reduce((sum, p) => sum + p.amount, 0) || 0;
      const amountStillToPay = initialTotalDueForOrder - alreadyPaidOnOrder;

      setPayments([{ method: 'cash', amount: Math.max(0, parseFloat(amountStillToPay.toFixed(2))) }]);
      setOrderCashReceived('');
      processedOrderIdRef.current = currentOrder.id; // Store the ID of the processed order
    } else if (!currentOrder) {
      processedOrderIdRef.current = null; // Reset when no order is selected
    }
  }, [currentOrder, taxSettings]); // Dependencies are correct, but the logic inside is now conditional

  useEffect(() => {
    if (currentOrder && parseFloat(manualDiscountPercentageInput) >= 0) {
      const percentage = parseFloat(manualDiscountPercentageInput) || 0;
      const subtotal = currentOrder.subtotal || currentOrder.items.reduce((sum, item) => sum + item.totalPrice, 0);
      const newDiscountAmount = subtotal * (percentage / 100);
      setManualDiscountAmountInput(newDiscountAmount.toFixed(2));
    }
  }, [manualDiscountPercentageInput, currentOrder]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        searchBarRef.current && !searchBarRef.current.contains(event.target as Node) &&
        suggestionListRef.current && !suggestionListRef.current.contains(event.target as Node) &&
        searchButtonRef.current && !searchButtonRef.current.contains(event.target as Node)
      ) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const { orderSubtotal, finalDiscountAmount, finalAppliedDiscountPercentage, calculatedTaxes, totalTaxAmount, finalTotal, totalPaidThisTransaction, overallTotalPaid, remainingBalance, advancePaymentsTotalOnCurrentOrder } = useMemo(() => {
    if (!currentOrder) {
      return { orderSubtotal: 0, finalDiscountAmount: 0, finalAppliedDiscountPercentage: 0, calculatedTaxes: [], totalTaxAmount: 0, finalTotal: 0, totalPaidThisTransaction: 0, overallTotalPaid: 0, remainingBalance: 0, advancePaymentsTotalOnCurrentOrder: 0 };
    }
    const subtotal = currentOrder.subtotal || currentOrder.items.reduce((sum, item) => sum + item.totalPrice, 0);
    const currentManualDiscountAmount = parseFloat(manualDiscountAmountInput) || 0;
    let effectiveDiscountAmount = 0;
    let effectiveDiscountPercentage = 0;
    const manualPercentage = parseFloat(manualDiscountPercentageInput) || 0;

    if (manualPercentage > 0) {
        effectiveDiscountPercentage = manualPercentage;
        effectiveDiscountAmount = subtotal * (manualPercentage / 100);
    } else if (currentManualDiscountAmount > 0 && currentManualDiscountAmount !== currentOrder.discountAmount) {
        effectiveDiscountAmount = currentManualDiscountAmount;
        effectiveDiscountPercentage = subtotal > 0 ? (currentManualDiscountAmount / subtotal) * 100 : 0;
    } else {
        effectiveDiscountAmount = currentOrder.discountAmount || 0;
        effectiveDiscountPercentage = currentOrder.appliedDiscountPercentage || currentOrder.appliedGlobalDiscountPercentage || 0;
    }

    const subtotalAfterDiscount = subtotal - effectiveDiscountAmount;
    const activeSystemTaxes = taxSettings.filter(ts => ts.enabled);
    const activeTaxes: AppliedTax[] = activeSystemTaxes
        .filter(tax => selectedTaxes[tax.id])
        .map(tax => ({
            name: tax.name,
            rate: tax.rate,
            amount: subtotalAfterDiscount * tax.rate,
        }));
    const taxSum = activeTaxes.reduce((sum, tax) => sum + tax.amount, 0);
    const grandTotal = subtotalAfterDiscount + taxSum;
    const paymentsMadeBeforeThisTransaction = currentOrder.payments?.reduce((sum, p) => sum + p.amount, 0) || 0;
    const formPaymentsTotal = payments.reduce((sum, p) => sum + p.amount, 0);
    const totalActuallyPaidNow = paymentsMadeBeforeThisTransaction + formPaymentsTotal;
    const balance = grandTotal - totalActuallyPaidNow;

    return {
      orderSubtotal: subtotal,
      finalDiscountAmount: effectiveDiscountAmount,
      finalAppliedDiscountPercentage: effectiveDiscountPercentage,
      calculatedTaxes: activeTaxes,
      totalTaxAmount: taxSum,
      finalTotal: grandTotal,
      totalPaidThisTransaction: formPaymentsTotal,
      overallTotalPaid: totalActuallyPaidNow,
      remainingBalance: balance,
      advancePaymentsTotalOnCurrentOrder: paymentsMadeBeforeThisTransaction,
    };
  }, [currentOrder, manualDiscountAmountInput, manualDiscountPercentageInput, payments, selectedTaxes, taxSettings]);

  const amountToPayNowForOrder = useMemo(() => {
    if (!currentOrder) return 0;
    return Math.max(0, finalTotal - advancePaymentsTotalOnCurrentOrder);
  }, [finalTotal, advancePaymentsTotalOnCurrentOrder, currentOrder]);

  const orderChangeDue = useMemo(() => {
    const cashReceivedNum = parseFloat(orderCashReceived) || 0;
    if (cashReceivedNum <= 0 || amountToPayNowForOrder <=0) return 0;
    const currentCashTransactionAmount = payments.filter(p => p.method === 'cash').reduce((sum, p) => sum + p.amount, 0);
    const change = cashReceivedNum - currentCashTransactionAmount;
    return change;
  }, [orderCashReceived, amountToPayNowForOrder, payments]);

  const advanceAmountToPayNow = useMemo(() => parseFloat(advancePaymentAmount) || 0, [advancePaymentAmount]);

  const dnChangeDue = useMemo(() => {
    const cashReceivedNum = parseFloat(dnCashReceived) || 0;
    if (cashReceivedNum <=0 || advanceAmountToPayNow <=0) return 0;
    const change = cashReceivedNum - advanceAmountToPayNow;
    return change;
  }, [dnCashReceived, advanceAmountToPayNow]);

  const recentOrdersForCashier = useMemo(() => {
    return orders
      .filter(order => order.status === 'pending_payment' || order.status === 'partial_payment' || order.status === 'ready_for_pickup')
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
      .slice(0, 10);
  }, [orders]);

  const handleAddPaymentMethod = () => {
    setPayments([...payments, { method: 'cash', amount: Math.max(0, remainingBalance) }]);
  };

  const handleRemovePaymentMethod = (index: number) => {
    if (payments.length > 1) {
      setPayments(payments.filter((_, i) => i !== index));
    }
  };

  const handlePaymentChange = (index: number, field: keyof PaymentDetail, value: string | number) => {
    const newPayments = [...payments];
    if (field === 'amount') {
      newPayments[index][field] = Math.max(0, Number(value) || 0);
    } else {
      newPayments[index][field] = value as PaymentMethod;
    }
    setPayments(newPayments);
  };

  const handleManualDiscountAmountChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setManualDiscountAmountInput(value);
    if (currentOrder) {
      const subtotal = currentOrder.subtotal || currentOrder.items.reduce((sum, item) => sum + item.totalPrice, 0);
      if (subtotal > 0 && (parseFloat(value) / subtotal * 100).toFixed(2) !== parseFloat(manualDiscountPercentageInput).toFixed(2)) {
        setManualDiscountPercentageInput('');
      }
    }
  };

  const handleManualDiscountPercentageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
     setManualDiscountPercentageInput(value);
  };

  const handleProcessOrderPayment = async () => {
    if (!currentOrder || !currentUser) {
      toast({ title: 'Error', description: 'No order or user selected.', variant: 'destructive' });
      return;
    }

    const isFullPayment = remainingBalance <= 0.005;

    if (totalPaidThisTransaction <= 0) {
      toast({ title: "Payment Required", description: "No payment amount entered.", variant: "destructive" });
      return;
    }

    if (remainingBalance < -0.01 && !payments.some(p => p.method === 'cash')) {
      toast({ title: 'Overpayment Issue', description: `Order overpaid by OMR ${Math.abs(remainingBalance).toFixed(2)}, but no cash payment recorded to provide change.`, variant: 'destructive' });
      return;
    }

    setIsProcessingPayment(true);
    
    const newPaymentsFromForm = payments.map(p => ({
      ...p,
      transactionId: p.method !== 'cash' ? `TXN-${Date.now()}-${Math.random().toString(36).substring(7)}` : undefined,
      paymentDate: new Date().toISOString(),
      cashierId: currentUser?.id,
      cashierName: currentUser?.username,
    })).filter(p => p.amount > 0);

    const allPaymentsForOrder = [...(currentOrder.payments || []), ...newPaymentsFromForm];
    
    const orderPayloadToSave: Order = {
      ...currentOrder,
      subtotal: orderSubtotal,
      discountAmount: finalDiscountAmount,
      appliedDiscountPercentage: finalAppliedDiscountPercentage > 0 ? finalAppliedDiscountPercentage : undefined,
      appliedGlobalDiscountPercentage: (finalAppliedDiscountPercentage > 0 && finalAppliedDiscountPercentage !== currentOrder.appliedGlobalDiscountPercentage) ? undefined : currentOrder.appliedGlobalDiscountPercentage,
      taxes: calculatedTaxes,
      totalAmount: finalTotal,
      payments: allPaymentsForOrder,
      updatedAt: new Date().toISOString(),
    };

    try {
      const serverConfirmedOrder = await updateOrderAndRefreshContext(orderPayloadToSave);
      if (serverConfirmedOrder) {
        if (isFullPayment) {
          setProcessedOrder(serverConfirmedOrder);
          setViewingInvoice(serverConfirmedOrder);
          setShowInvoiceModal(true);
          toast({ title: 'Payment Complete & Order Closed!', description: `Order ${currentOrder.id} marked as paid. Invoice generated.`, className: 'bg-accent text-accent-foreground border-accent' });
          resetAllForms();
        } else {
          setCurrentOrder(serverConfirmedOrder);
          const remainingOnServer = serverConfirmedOrder.totalAmount - (serverConfirmedOrder.payments?.reduce((s, p) => s + p.amount, 0) || 0);
          toast({ title: 'Partial Payment Recorded', description: `OMR ${totalPaidThisTransaction.toFixed(2)} recorded for order ${currentOrder.id}. Remaining: OMR ${remainingOnServer.toFixed(2)}.` });
          setPayments([{ method: 'cash', amount: Math.max(0, parseFloat(remainingOnServer.toFixed(2))) }]);
          setOrderCashReceived('');
        }
      } else {
        const latestVersionOfCurrentOrder = getOrderByIdFromContext(currentOrder.id);
        if (latestVersionOfCurrentOrder) setCurrentOrder(latestVersionOfCurrentOrder);
      }
    } catch (error) {
      toast({ title: "Payment Processing Failed", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsProcessingPayment(false);
    }
  };

  const handleProcessAdvancePayment = async () => {
    if (!currentDemandNotice || !currentUser) {
      toast({ title: "Error", description: "No demand notice or user selected.", variant: "destructive" });
      return;
    }
    const amount = parseFloat(advancePaymentAmount);
    if (isNaN(amount) || amount <= 0) {
      toast({ title: "Invalid Amount", description: "Please enter a valid positive amount.", variant: "destructive" });
      return;
    }
    const totalAlreadyPaidOnDN = currentDemandNotice.payments?.reduce((sum, p) => sum + p.amount, 0) || 0;
    const totalAgreedPrice = currentDemandNotice.agreedPrice * currentDemandNotice.quantityRequested;
    if (totalAlreadyPaidOnDN + amount > totalAgreedPrice + 0.001) {
      toast({ title: "Amount Exceeds", description: `Total payments (OMR ${(totalAlreadyPaidOnDN + amount).toFixed(2)}) cannot exceed total agreed price (OMR ${totalAgreedPrice.toFixed(2)}). Current paid: OMR ${totalAlreadyPaidOnDN.toFixed(2)}.`, variant: "destructive" });
      return;
    }
    setIsProcessingDnPayment(true);
    const paymentDetail: PaymentDetail = {
      method: advancePaymentMethod,
      amount: amount,
      transactionId: advancePaymentMethod !== 'cash' && advancePaymentTransactionId ? advancePaymentTransactionId : undefined,
      paymentDate: new Date().toISOString(),
      notes: "Advance payment for Demand Notice",
      cashierId: currentUser?.id,
      cashierName: currentUser?.username,
    };
    const updatedNotice = await addAdvancePaymentToDemandNotice(currentDemandNotice.id, paymentDetail);
    setIsProcessingDnPayment(false);
    if (updatedNotice) {
      toast({ title: "Advance Payment Recorded", description: `OMR ${amount.toFixed(2)} recorded for DN ${currentDemandNotice.id}.`, className: "bg-accent text-accent-foreground border-accent" });
      setViewingDnReceipt(updatedNotice);
      setShowDnReceiptModal(true);
      resetDnAdvanceForm();
      setCurrentDemandNotice(updatedNotice);
    } else {
      toast({ title: "Payment Failed", description: "Could not record advance payment.", variant: "destructive" });
    }
  };

  const payableStatuses: OrderStatus[] = ['pending_payment', 'partial_payment', 'ready_for_pickup'];
  const isOrderPayable = currentOrder ? payableStatuses.includes(currentOrder.status) : false;

  const canAcceptAdvancePayment = currentDemandNotice && 
                                  currentDemandNotice.status !== 'fulfilled' && 
                                  currentDemandNotice.status !== 'cancelled' &&
                                  currentDemandNotice.status !== 'order_processing' &&
                                  currentDemandNotice.status !== 'ready_for_collection';


  const getDNStatusBadge = useCallback((status?: DemandNoticeStatus) => {
    if (!status) return <Badge variant="secondary">Unknown</Badge>;
    let text = status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
    let variantClass = "bg-gray-100 text-gray-700 border-gray-300"; // Default

    switch (status) {
      case 'pending_review': variantClass = "bg-yellow-100 text-yellow-700 border-yellow-300"; break;
      case 'awaiting_stock': variantClass = "bg-red-100 text-red-700 border-red-300"; break;
      case 'partial_stock_available': variantClass = "bg-yellow-100 text-yellow-700 border-yellow-300"; break;
      case 'full_stock_available': variantClass = "bg-green-100 text-green-700 border-green-300"; break;
      case 'customer_notified_stock': variantClass = "bg-blue-100 text-blue-700 border-blue-300"; break;
      case 'awaiting_customer_action': variantClass = "bg-purple-100 text-purple-700 border-purple-300"; break;
      case 'order_processing': variantClass = "bg-indigo-100 text-indigo-700 border-indigo-300"; break;
      case 'preparing_stock': variantClass = "bg-cyan-100 text-cyan-700 border-cyan-300"; break;
      case 'ready_for_collection': variantClass = "bg-teal-100 text-teal-700 border-teal-300"; break;
      case 'fulfilled': variantClass = "bg-emerald-200 text-emerald-800 border-emerald-400"; break;
      case 'cancelled': return <Badge variant="destructive">Cancelled</Badge>;
      default: break;
    }
    return <Badge variant="outline" className={cn("text-xs", variantClass)}>{text}</Badge>;
  }, []);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-theme(spacing.24)-2rem)] lg:h-[calc(100vh-theme(spacing.24))]">
      <div className="flex flex-col space-y-4 lg:h-full">
        <Card className="shadow-md flex-shrink-0">
          <CardHeader>
            <CardTitle className="text-2xl flex items-center"><Search className="mr-2 h-6 w-6 text-primary" /> Transaction Search</CardTitle>
            <CardDescription>Enter Order Invoice ID, Demand Notice ID, or Customer Phone.</CardDescription>
            <div className="flex gap-2 mt-2 items-start relative">
              <Input
                ref={searchBarRef}
                type="text"
                placeholder="Search..."
                value={globalSearchTerm}
                onChange={(e) => setGlobalSearchTerm(e.target.value)}
                onFocus={() => globalSearchTerm.trim() && suggestions.length > 0 && setShowSuggestions(true)}
                className="h-10 text-base flex-grow"
              />
              <Button ref={searchButtonRef} onClick={handleGlobalSearch} className="h-10">Search</Button>
              {showSuggestions && suggestions.length > 0 && (
                <div ref={suggestionListRef} className="absolute top-full left-0 right-0 mt-1 w-full bg-card border rounded-md shadow-lg z-50 max-h-60 overflow-y-auto">
                  {suggestions.map((suggestion) => (
                    <div
                      key={`${suggestion.type}-${suggestion.id}`}
                      className="p-3 border-b last:border-b-0 hover:bg-accent cursor-pointer"
                      onClick={() => handleSelectSuggestion(suggestion)}
                    >
                      <div className="flex justify-between items-center">
                        <div>
                          <span className="font-medium text-primary">#{suggestion.id}</span>
                          <span className="text-muted-foreground ml-2 text-xs">
                            ({isValid(parseISO(suggestion.createdAt)) ? format(parseISO(suggestion.createdAt), 'dd MMM yyyy') : 'Invalid Date'})
                          </span>
                        </div>
                        {suggestion.statusText && (
                          <span className={cn('px-2 py-0.5 rounded-full text-xs', suggestion.statusColorClass)}>
                            {suggestion.statusText}
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        {suggestion.type === 'order' 
                         ? `${suggestion.customerName} • ${suggestion.customerPhone}`
                         : `${suggestion.productName} (DN) • ${suggestion.customerPhone}`
                        }
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardHeader>
        </Card>

        {currentOrder && ( <Card className="shadow-md flex-grow flex flex-col"> <CardHeader> <CardTitle className="text-xl">Order Details: {currentOrder.id}</CardTitle> <CardDescription> Salesperson: {currentOrder.primarySalespersonName} | Created: {parseISO(currentOrder.createdAt).toLocaleString()} </CardDescription> </CardHeader> <CardContent className="flex-grow overflow-hidden"> <ScrollArea className="h-full max-h-[calc(100vh-40rem)] lg:max-h-[calc(100vh-32rem)]"> <div className="pr-3 space-y-4"> 
        <Table>
          <TableHeader><TableRow><TableHead>Item</TableHead><TableHead className="text-center">Qty</TableHead><TableHead className="text-right">Price</TableHead><TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
          <TableBody>
            {(currentOrder.items || []).map((item) => (
              <TableRow key={item.productId}><TableCell>{item.name}</TableCell><TableCell className="text-center">{item.quantity}</TableCell><TableCell className="text-right">OMR {item.pricePerUnit.toFixed(2)}</TableCell><TableCell className="text-right">OMR {item.totalPrice.toFixed(2)}</TableCell></TableRow>
            ))}
          </TableBody>
        </Table>
        <Separator className="my-4" /> <div className="space-y-2 text-sm"> <div className="flex justify-between"><span>Subtotal:</span> <span>OMR {orderSubtotal.toFixed(2)}</span></div> {currentOrder.discountAmount > 0 && (<div className="flex justify-between text-blue-600"><span>Initial Discount {currentOrder.appliedGlobalDiscountPercentage ? `(${currentOrder.appliedGlobalDiscountPercentage}% Global)` : currentOrder.appliedDiscountPercentage ? `(${currentOrder.appliedDiscountPercentage}% Manual)` : ''}:</span><span>-OMR {currentOrder.discountAmount.toFixed(2)}</span></div>)} {isOrderPayable && ( <div className="p-3 border rounded-md mt-2 space-y-2 bg-muted/30"> <Label className="font-semibold flex items-center"><Tag className="mr-2 h-4 w-4 text-muted-foreground"/>Cashier Discount (Overrides Initial):</Label> <div className="grid grid-cols-2 gap-x-4 gap-y-2 items-end"> <div><Label htmlFor="manual-discount-percentage" className="flex items-center text-xs"><PercentIcon className="mr-1 h-3 w-3" /> Discount (%)</Label><Input id="manual-discount-percentage" type="number" value={manualDiscountPercentageInput} onChange={handleManualDiscountPercentageChange} className="h-8 w-full text-right" placeholder="e.g. 10" min="0" max="100" step="0.01"/></div> <div><Label htmlFor="manual-discount-amount" className="flex items-center text-xs"><DollarSign className="mr-1 h-3 w-3" /> Discount Amount (OMR)</Label><Input id="manual-discount-amount" type="number" value={manualDiscountAmountInput} onChange={handleManualDiscountAmountChange} className="h-8 w-full text-right" placeholder="0.00" min="0" step="0.01" max={orderSubtotal.toString()}/></div> </div> </div> )} <Separator className="my-2" /> <div className="space-y-2"><Label className="font-semibold flex items-center"><PercentIcon className="mr-2 h-4 w-4 text-muted-foreground" />Apply Taxes:</Label> {taxSettings.filter(t => t.enabled).map(tax => (<div key={tax.id} className="flex items-center justify-between pl-2"><Label htmlFor={`tax-${tax.id}`} className="flex items-center text-sm font-normal cursor-pointer"><Checkbox id={`tax-${tax.id}`} checked={!!selectedTaxes[tax.id]} onCheckedChange={(checked) => { isOrderPayable && setSelectedTaxes(prev => ({ ...prev, [tax.id]: !!checked }));}} className="mr-2" disabled={!isOrderPayable}/>{tax.name} ({(tax.rate * 100).toFixed(0)}%)</Label><span className="text-muted-foreground">OMR {( (orderSubtotal - finalDiscountAmount) * tax.rate * (selectedTaxes[tax.id] ? 1 : 0) ).toFixed(2)}</span></div>))} </div> <Separator className="my-2" /> {advancePaymentsTotalOnCurrentOrder > 0 && ( <div className="space-y-1"> <Label className="font-semibold text-blue-600">Advance Payments Made:</Label> {currentOrder.payments?.filter(p=>p.notes === "Advance payment for Demand Notice").map((p, idx) => ( <div key={`adv-${idx}`} className="flex justify-between text-xs text-blue-500"> <span>{p.method.replace('_',' ')} {p.paymentDate ? `(on ${format(parseISO(p.paymentDate), 'PP')})` : ''}</span> <span>OMR {p.amount.toFixed(2)}</span> </div> ))} <div className="flex justify-between text-xs font-semibold text-blue-600 pt-1 border-t border-blue-200"> <span>Total Advance Paid:</span> <span>OMR {advancePaymentsTotalOnCurrentOrder.toFixed(2)}</span> </div> </div> )} <Separator className="my-2" /> <div className="flex justify-between font-bold text-lg text-primary"><span>Total Order Value:</span> <span>OMR {finalTotal.toFixed(2)}</span></div> <div className="flex justify-between font-semibold"><span>Amount To Pay Now:</span> <span>OMR {amountToPayNowForOrder.toFixed(2)}</span></div> </div> </div> </ScrollArea> </CardContent> </Card> )}

        {currentDemandNotice && (
          <Card className="shadow-md mt-4 flex-shrink-0">
            <CardHeader>
              <CardTitle className="text-xl flex items-center">
                <BellRing className="mr-2 h-6 w-6 text-primary" /> Demand Notice: {currentDemandNotice.id}
              </CardTitle>
              <CardDescription>
                Product: {currentDemandNotice.productName} | Customer: {currentDemandNotice.customerContactNumber}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h4 className="font-semibold mb-1">DN Details:</h4>
                <p className="text-sm">Status: {getDNStatusBadge(currentDemandNotice.status)}</p>
                <p className="text-sm">Total Agreed Price: OMR {(currentDemandNotice.agreedPrice * currentDemandNotice.quantityRequested).toFixed(2)}</p>
                <p className="text-sm">Total Advance Paid: OMR {(currentDemandNotice.payments?.reduce((sum, p) => sum + p.amount, 0) || 0).toFixed(2)}</p>
              </div>
              
              <Button
                variant="outline"
                className="w-full"
                onClick={() => {
                  if (currentDemandNotice) {
                    setViewingDnReceipt(currentDemandNotice);
                    setShowDnReceiptModal(true);
                  }
                }}
              >
                <Printer className="mr-2 h-4 w-4" /> View/Reprint DN Receipt
              </Button>
              
              {canAcceptAdvancePayment && (
                <>
                  <Separator />
                  <Label className="font-semibold text-md block pt-2">Record New Advance Payment:</Label>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-end">
                    <div>
                      <Label htmlFor="advancePaymentAmount">Advance Amount (OMR)</Label>
                      <Input id="advancePaymentAmount" type="number" value={advancePaymentAmount} onChange={e => setAdvancePaymentAmount(e.target.value)} className="h-10" min="0.01" step="0.01"/>
                    </div>
                    <div>
                      <Label htmlFor="advancePaymentMethod">Payment Method</Label>
                      <Select value={advancePaymentMethod} onValueChange={value => setAdvancePaymentMethod(value as PaymentMethod)}>
                        <SelectTrigger id="advancePaymentMethod" className="h-10"><SelectValue /></SelectTrigger>
                        <SelectContent> <SelectItem value="cash">Cash</SelectItem><SelectItem value="card">Card</SelectItem><SelectItem value="bank_transfer">Bank Transfer</SelectItem> </SelectContent>
                      </Select>
                    </div>
                  </div>
                  {advancePaymentMethod !== 'cash' && (
                    <div>
                      <Label htmlFor="advancePaymentTransactionId">Transaction ID (Optional)</Label>
                      <Input id="advancePaymentTransactionId" value={advancePaymentTransactionId} onChange={e => setAdvancePaymentTransactionId(e.target.value)} className="h-10" />
                    </div>
                  )}
                  {advancePaymentMethod === 'cash' && advanceAmountToPayNow > 0 && (
                    <Card className="p-3 bg-muted/30">
                      <CardTitle className="text-sm font-semibold mb-2 flex items-center"><Calculator className="h-4 w-4 mr-2 text-muted-foreground"/>Cash Calculator</CardTitle>
                      <div className="space-y-2">
                        <div><Label htmlFor="dn-cash-received" className="text-xs">Cash Received (OMR)</Label><Input id="dn-cash-received" type="number" value={dnCashReceived} onChange={e => setDnCashReceived(e.target.value)} className="h-8 w-full text-right" placeholder="e.g. 50"/></div>
                        <div className="flex justify-between text-xs"><span>Advance Amount Due:</span><span>OMR {advanceAmountToPayNow.toFixed(2)}</span></div>
                        {parseFloat(dnCashReceived) > 0 && (
                          <div className={`flex justify-between text-xs font-semibold ${dnChangeDue < 0 ? 'text-destructive' : 'text-green-600'}`}><span>Change to Return:</span><span>OMR {dnChangeDue >= 0 ? dnChangeDue.toFixed(2) : 'Short by ' + Math.abs(dnChangeDue).toFixed(2) }</span></div>
                        )}
                      </div>
                    </Card>
                  )}
                  <Button onClick={handleProcessAdvancePayment} className="w-full" disabled={isProcessingDnPayment}>
                    {isProcessingDnPayment ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processing...</> : 'Record Advance Payment'}
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {!currentOrder && !currentDemandNotice && globalSearchTerm !== '' && ( <Card className="shadow-md flex-grow flex items-center justify-center"> <div className="text-center text-muted-foreground p-8"> <Info className="mx-auto h-12 w-12 mb-4" /> <p className="text-lg">No Order or Demand Notice loaded.</p> <p className="text-sm">Please use the search above.</p> </div> </Card> )}
        {!currentOrder && !currentDemandNotice && globalSearchTerm === '' && ( <Card className="shadow-md flex-grow"><CardHeader><CardTitle className="text-xl flex items-center"><ListChecks className="mr-2 h-6 w-6 text-primary" /> Recent Orders for Payment</CardTitle></CardHeader> <CardContent> {recentOrdersForCashier.length > 0 ? ( <ScrollArea className="h-[calc(50vh-10rem)]"> <div className="space-y-3"> {recentOrdersForCashier.map(order => (<Button key={order.id} variant="outline" className="w-full justify-start h-auto p-3 group hover:bg-accent hover:text-accent-foreground" onClick={() => setGlobalSearchTerm(order.id)}><div className="flex flex-col items-start text-left w-full"><div className="flex justify-between w-full items-center"><span className="font-semibold text-primary group-hover:text-accent-foreground">ID: {order.id}</span><Badge variant="outline" className="text-xs group-hover:bg-background/20 group-hover:text-white">{order.status.replace(/_/g, ' ')}</Badge></div><span className="text-xs text-muted-foreground group-hover:text-accent-foreground">Salesperson: {order.primarySalespersonName} | Total: OMR {order.totalAmount.toFixed(2)}</span><span className="text-xs text-muted-foreground group-hover:text-accent-foreground">Created: {format(parseISO(order.createdAt), 'PPp')}</span></div></Button>))}</div></ScrollArea> ) : (<div className="text-center text-muted-foreground p-8"><Info className="mx-auto h-12 w-12 mb-4" /><p className="text-lg">No recent orders awaiting payment or pickup.</p><p className="text-sm">Use the search bar above if you have an Invoice ID or DN details.</p></div>)} </CardContent> </Card> )}
      </div>

      <div className="flex flex-col space-y-4 lg:h-full">
        <Card className="shadow-md flex-grow flex flex-col">
          <CardHeader> <CardTitle className="text-2xl flex items-center"> <DollarSign className="mr-2 h-6 w-6 text-primary" /> Payment Input </CardTitle> <CardDescription>Enter customer payment details for the selected final order.</CardDescription> </CardHeader>
          <CardContent className="flex-grow overflow-hidden">
            <ScrollArea className="h-full max-h-[calc(100vh-30rem)] lg:max-h-[calc(100vh-20rem)]">
              <div className="space-y-4 pr-3">
                {payments.map((payment, index) => ( <div key={index} className="grid grid-cols-1 md:grid-cols-[1fr_auto_auto] gap-3 items-end p-3 border rounded-md"> <div className="space-y-1"> <Label htmlFor={`paymentMethod-${index}`}>Payment Method #{index + 1}</Label> <Select value={payment.method} onValueChange={(value) => handlePaymentChange(index, 'method', value as PaymentMethod)} disabled={!isOrderPayable}> <SelectTrigger id={`paymentMethod-${index}`} className="h-10"><SelectValue placeholder="Select method" /></SelectTrigger> <SelectContent> <SelectItem value="cash"><Banknote className="inline mr-2 h-4 w-4" />Cash</SelectItem> <SelectItem value="card"><CreditCard className="inline mr-2 h-4 w-4" />Card</SelectItem> <SelectItem value="bank_transfer"><Landmark className="inline mr-2 h-4 w-4" />Bank Transfer</SelectItem> </SelectContent> </Select> </div> <div className="space-y-1"> <Label htmlFor={`amount-${index}`}>Amount Paid</Label> <Input id={`amount-${index}`} type="number" value={payment.amount} onChange={(e) => handlePaymentChange(index, 'amount', e.target.value)} className="h-10 text-right" placeholder="0.00" disabled={!isOrderPayable} min="0" step="0.01"/> </div> {payments.length > 1 && (<Button variant="ghost" size="icon" onClick={() => handleRemovePaymentMethod(index)} className="self-end text-destructive hover:text-destructive" aria-label="Remove payment method" disabled={!isOrderPayable}><XCircle className="h-5 w-5" /></Button>)} </div> ))}
                <Button variant="outline" onClick={handleAddPaymentMethod} className="w-full mt-2" disabled={!isOrderPayable || remainingBalance <=0}><PlusCircle className="mr-2 h-4 w-4" /> Add Payment Method</Button>
                {currentOrder && isOrderPayable && amountToPayNowForOrder > 0 && payments.some(p => p.method === 'cash' && p.amount > 0) && ( <Card className="mt-4 p-3 bg-muted/30"> <CardTitle className="text-sm font-semibold mb-2 flex items-center"><Calculator className="h-4 w-4 mr-2 text-muted-foreground"/>Cash Payment Calculator</CardTitle> <div className="space-y-2"> <div><Label htmlFor="order-cash-received" className="text-xs">Cash Received (OMR)</Label><Input id="order-cash-received" type="number" value={orderCashReceived} onChange={e => setOrderCashReceived(e.target.value)} className="h-8 w-full text-right" placeholder="e.g. 50"/></div> <div className="flex justify-between text-xs"><span>Amount Due (Current Cash Transaction):</span><span>OMR {payments.filter(p=>p.method === 'cash').reduce((s,p)=>s+p.amount,0).toFixed(2)}</span></div> {parseFloat(orderCashReceived) > 0 && ( <div className={`flex justify-between text-xs font-semibold ${orderChangeDue < 0 ? 'text-destructive' : 'text-green-600'}`}><span>Change to Return:</span><span>OMR {orderChangeDue >= 0 ? orderChangeDue.toFixed(2) : 'Short by ' + Math.abs(orderChangeDue).toFixed(2) }</span></div> )} </div> </Card> )}
                {currentOrder && ( <> <Separator className="my-4" /> <div className="space-y-2 text-sm"> <div className="flex justify-between font-semibold"><span>Total Order Value:</span> <span>OMR {finalTotal.toFixed(2)}</span></div> {advancePaymentsTotalOnCurrentOrder > 0 && ( <div className="flex justify-between text-blue-600"><span>Advance Paid on DN:</span> <span>- OMR {advancePaymentsTotalOnCurrentOrder.toFixed(2)}</span></div> )} <div className="flex justify-between font-semibold"><span>Amount Being Paid Now:</span> <span>OMR {totalPaidThisTransaction.toFixed(2)}</span></div> <div className="flex justify-between font-bold text-lg mt-1"><span>{remainingBalance < -0.01 ? "Change Due:" : (remainingBalance > 0.01 ? "Amount Remaining:" : "Balance:")}</span><span className={remainingBalance < -0.01 ? 'text-green-600' : (remainingBalance > 0.01 ? 'text-destructive' : '')}>OMR {Math.abs(remainingBalance).toFixed(2)}</span></div> </div> </> )}
                {currentOrder && !isOrderPayable && ( <Alert className="mt-4 border-blue-500 bg-blue-50"> <Info className="h-5 w-5 text-blue-600" /> <UITitle className="text-blue-700">Order Status: {currentOrder.status.replace(/_/g, ' ')}</UITitle> <UIDescription className="text-blue-600"> This order is currently not eligible for payment processing. You can view the invoice. </UIDescription> </Alert> )}
              </div>
            </ScrollArea>
          </CardContent>
          <CardFooter className="border-t p-4 flex flex-col gap-3">
             <div className="flex flex-col sm:flex-row gap-3 w-full">
                <Button variant="outline" className="flex-1 h-12 text-lg" onClick={() => { setViewingInvoice(currentOrder); setShowInvoiceModal(true);}} disabled={!currentOrder} >
                    <Eye className="mr-2 h-5 w-5" /> View Full Invoice
                </Button>
                <Button
                    onClick={handleProcessOrderPayment}
                    disabled={!isOrderPayable || isProcessingPayment || totalPaidThisTransaction <= 0}
                    className="flex-1 bg-accent hover:bg-accent/90 text-accent-foreground h-12 text-lg"
                >
                    {isProcessingPayment ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <WalletCards className="mr-2 h-4 w-4" />}
                    Pay
                </Button>
            </div>
          </CardFooter>
        </Card>
        <div className="mt-auto pt-4 flex-shrink-0"> <CashierShiftSummary currentUser={currentUser} context="profile" /> </div>
      </div>
      <InvoiceModal order={viewingInvoice || processedOrder} isOpen={showInvoiceModal} onClose={() => { setShowInvoiceModal(false); setViewingInvoice(null); if(processedOrder && ['paid', 'completed'].includes(processedOrder.status)) setProcessedOrder(null); }} />
      <DemandNoticeReceiptModal demandNotice={viewingDnReceipt} isOpen={showDnReceiptModal} onClose={() => { setShowDnReceiptModal(false); setViewingDnReceipt(null); }} />
    </div>
  );
}

