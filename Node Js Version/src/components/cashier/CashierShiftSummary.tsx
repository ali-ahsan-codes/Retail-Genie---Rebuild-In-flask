
// src/components/cashier/CashierShiftSummary.tsx
'use client';

import { useMemo, useState, useEffect } from 'react';
import type { Order, PaymentDetail, User, OrderStatus, DemandNotice } from '@/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DollarSign, Wallet, CheckCircle, History, Calendar as CalendarIcon, ListChecks, ShoppingBag, BellRing, ClockIcon, InputIcon } from 'lucide-react'; 
import { format, isSameDay, parseISO, isValid, setHours as dateFnsSetHours, setMinutes as dateFnsSetMinutes, setSeconds as dateFnsSetSeconds, setMilliseconds as dateFnsSetMilliseconds, parse } from 'date-fns';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { useApp } from '@/context/AppContext';

interface CashierShiftSummaryProps {
  currentUser: User | null;
  context?: 'dashboard' | 'profile';
}

interface ShiftSummary {
  totalOrdersFullyPaidOnDate: number;
  totalPaymentsOnDateByMethod: Record<string, number>;
  grandTotalPaymentsOnDate: number;
  ordersWithPaymentsOnDateDetails: {
    id: string;
    orderTotalAmount: number;
    amountPaidOnDate: number;
    orderStatus: OrderStatus;
    paymentMethodsOnDate: string[];
    closedOnThisDate: boolean;
    lastActivityTimeOnDate?: string;
  }[];
  demandNoticesWithAdvancePaymentsOnDateDetails: {
    id: string;
    productName: string;
    customerContactNumber: string;
    amountPaidOnDate: number;
    paymentMethodsOnDate: string[];
    dnTotalAgreedAmount: number;
    dnTotalAdvancePaid: number;
    lastActivityTimeOnDate?: string;
  }[];
}

export default function CashierShiftSummary({ currentUser, context = 'dashboard' }: CashierShiftSummaryProps) {
  const { orders, demandNotices: allDemandNotices } = useApp();
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(new Date());
  const [startTime, setStartTime] = useState(''); // e.g., "13:00"
  const [endTime, setEndTime] = useState('');   // e.g., "20:00"


  const datePickerButtonId = context === 'profile' ? 'shift-summary-date-profile-trigger' : 'shift-summary-date-dashboard-trigger';

  const shiftSummary = useMemo((): ShiftSummary => {
    if (!currentUser || !selectedDate) {
      return {
        totalOrdersFullyPaidOnDate: 0,
        totalPaymentsOnDateByMethod: {},
        grandTotalPaymentsOnDate: 0,
        ordersWithPaymentsOnDateDetails: [],
        demandNoticesWithAdvancePaymentsOnDateDetails: []
      };
    }

    let reportStartDate = new Date(selectedDate);
    reportStartDate = dateFnsSetHours(reportStartDate, 0);
    reportStartDate = dateFnsSetMinutes(reportStartDate, 0);
    reportStartDate = dateFnsSetSeconds(reportStartDate, 0);
    reportStartDate = dateFnsSetMilliseconds(reportStartDate, 0);

    let reportEndDate = new Date(selectedDate);
    reportEndDate = dateFnsSetHours(reportEndDate, 23);
    reportEndDate = dateFnsSetMinutes(reportEndDate, 59);
    reportEndDate = dateFnsSetSeconds(reportEndDate, 59);
    reportEndDate = dateFnsSetMilliseconds(reportEndDate, 999);


    if (startTime && /^\d{2}:\d{2}$/.test(startTime)) {
        const parsedTime = parse(startTime, 'HH:mm', new Date());
        if (isValid(parsedTime)) {
            let tempStartDate = new Date(selectedDate);
            tempStartDate = dateFnsSetHours(tempStartDate, parsedTime.getHours());
            tempStartDate = dateFnsSetMinutes(tempStartDate, parsedTime.getMinutes());
            tempStartDate = dateFnsSetSeconds(tempStartDate, 0);
            reportStartDate = dateFnsSetMilliseconds(tempStartDate, 0);
        }
    }
    if (endTime && /^\d{2}:\d{2}$/.test(endTime)) {
        const parsedTime = parse(endTime, 'HH:mm', new Date());
        if (isValid(parsedTime)) {
            let tempEndDate = new Date(selectedDate);
            tempEndDate = dateFnsSetHours(tempEndDate, parsedTime.getHours());
            tempEndDate = dateFnsSetMinutes(tempEndDate, parsedTime.getMinutes());
            tempEndDate = dateFnsSetSeconds(tempEndDate, 59);
            reportEndDate = dateFnsSetMilliseconds(tempEndDate, 999);
        }
    }
    
    // If user accidentally set end time before start time for the same day, adjust reportEndDate to end of day.
    if (reportEndDate < reportStartDate && isSameDay(reportStartDate, reportEndDate)) {
        let tempEndSameDay = new Date(selectedDate);
        tempEndSameDay = dateFnsSetHours(tempEndSameDay, 23);
        tempEndSameDay = dateFnsSetMinutes(tempEndSameDay, 59);
        tempEndSameDay = dateFnsSetSeconds(tempEndSameDay, 59);
        reportEndDate = dateFnsSetMilliseconds(tempEndSameDay, 999);
    }


    let totalOrdersFullyPaidOnDate = 0;
    const totalPaymentsOnDateByMethod: Record<string, number> = { cash: 0, card: 0, bank_transfer: 0, advance_on_dn: 0 };
    let grandTotalPaymentsOnDate = 0;
    const ordersWithPaymentsOnDateDetails: ShiftSummary['ordersWithPaymentsOnDateDetails'] = [];
    const demandNoticesWithAdvancePaymentsOnDateDetails: ShiftSummary['demandNoticesWithAdvancePaymentsOnDateDetails'] = [];
    
    orders.forEach(order => {
      let amountPaidForThisOrderOnDateByNewTender = 0;
      const methodsUsedForThisOrderOnDate: Set<string> = new Set();
      let latestPaymentTimeOnDateForOrder: string | undefined = undefined;

      const paymentsOnSelectedDateTimeRange = (order.payments || []).filter(payment =>
        payment.paymentDate && 
        isValid(parseISO(payment.paymentDate)) && 
        payment.cashierId === currentUser.id && // Filter by the current cashier/express user
        isSameDay(parseISO(payment.paymentDate), selectedDate) &&
        parseISO(payment.paymentDate) >= reportStartDate &&
        parseISO(payment.paymentDate) <= reportEndDate
      );

      if (paymentsOnSelectedDateTimeRange.length > 0) {
        paymentsOnSelectedDateTimeRange.forEach(payment => {
          if (payment.method !== 'advance_on_dn') {
            totalPaymentsOnDateByMethod[payment.method] = (totalPaymentsOnDateByMethod[payment.method] || 0) + payment.amount;
            grandTotalPaymentsOnDate += payment.amount;
            amountPaidForThisOrderOnDateByNewTender += payment.amount;
          }
          methodsUsedForThisOrderOnDate.add(payment.method);
        });
        const latestPayment = paymentsOnSelectedDateTimeRange.sort((a, b) => {
            if (!a.paymentDate || !b.paymentDate) return 0; // Should not happen if filtered correctly
            return parseISO(b.paymentDate).getTime() - parseISO(a.paymentDate).getTime();
        })[0];
        if (latestPayment && latestPayment.paymentDate) {
          latestPaymentTimeOnDateForOrder = format(parseISO(latestPayment.paymentDate), 'p');
        }
      }

      // Determine if order was closed on this date BY THIS USER
      const orderUpdatedAtDate = parseISO(order.updatedAt);
      const isOrderClosed = order.status === 'paid' || order.status === 'completed';
      const isUpdatedOnDate = isValid(orderUpdatedAtDate) && isSameDay(orderUpdatedAtDate, selectedDate) && orderUpdatedAtDate >= reportStartDate && orderUpdatedAtDate <= reportEndDate;
      const lastPayment = (order.payments && order.payments.length > 0) 
                            ? [...order.payments].sort((a,b) => parseISO(b.paymentDate || '1970').getTime() - parseISO(a.paymentDate || '1970').getTime())[0] 
                            : null;
      const lastPaymentCashierId = lastPayment?.cashierId;

      const orderClosedOnThisDateByCurrentUser = isOrderClosed && isUpdatedOnDate && lastPaymentCashierId === currentUser.id;

      // The order should appear in the list if either a payment was made by this user on this date, OR the order was closed by this user on this date.
      if (paymentsOnSelectedDateTimeRange.length > 0 || orderClosedOnThisDateByCurrentUser) {
         let totalPaidOnOrderToday = amountPaidForThisOrderOnDateByNewTender;
         paymentsOnSelectedDateTimeRange.forEach(p => {
            if (p.method === 'advance_on_dn') {
                totalPaidOnOrderToday += p.amount;
            }
        });

        if (!latestPaymentTimeOnDateForOrder && orderClosedOnThisDateByCurrentUser) {
           latestPaymentTimeOnDateForOrder = format(orderUpdatedAtDate, 'p');
        }

        ordersWithPaymentsOnDateDetails.push({
          id: order.id,
          orderTotalAmount: order.totalAmount,
          amountPaidOnDate: totalPaidOnOrderToday,
          orderStatus: order.status,
          paymentMethodsOnDate: Array.from(methodsUsedForThisOrderOnDate).map(m => m.replace('_',' ').replace(/\b\w/g, char => char.toUpperCase())),
          closedOnThisDate: orderClosedOnThisDateByCurrentUser,
          lastActivityTimeOnDate: latestPaymentTimeOnDateForOrder,
        });

        if (orderClosedOnThisDateByCurrentUser) {
             totalOrdersFullyPaidOnDate++;
        }
      }
    });

    allDemandNotices.forEach(dn => {
      let amountPaidForThisDnOnDate = 0;
      const methodsUsedForThisDnOnDate: Set<string> = new Set();
      let relevantDnPaymentExists = false;
      let latestPaymentTimeOnDateForDN: string | undefined = undefined;

      const paymentsOnSelectedDateTimeRangeForDN = (dn.payments || []).filter(payment =>
        payment.paymentDate && 
        isValid(parseISO(payment.paymentDate)) && 
        payment.cashierId === currentUser.id && // Filter by the current cashier/express user
        isSameDay(parseISO(payment.paymentDate), selectedDate) &&
        parseISO(payment.paymentDate) >= reportStartDate &&
        parseISO(payment.paymentDate) <= reportEndDate
      );

      if (paymentsOnSelectedDateTimeRangeForDN.length > 0) {
          relevantDnPaymentExists = true;
          paymentsOnSelectedDateTimeRangeForDN.forEach(payment => {
            totalPaymentsOnDateByMethod[payment.method] = (totalPaymentsOnDateByMethod[payment.method] || 0) + payment.amount;
            grandTotalPaymentsOnDate += payment.amount;
            amountPaidForThisDnOnDate += payment.amount;
            methodsUsedForThisDnOnDate.add(payment.method);
          });
          const latestPaymentDN = paymentsOnSelectedDateTimeRangeForDN.sort((a, b) => {
            if (!a.paymentDate || !b.paymentDate) return 0;
            return parseISO(b.paymentDate).getTime() - parseISO(a.paymentDate).getTime();
          })[0];
          if (latestPaymentDN && latestPaymentDN.paymentDate) {
            latestPaymentTimeOnDateForDN = format(parseISO(latestPaymentDN.paymentDate), 'p');
          }
      }


      if (relevantDnPaymentExists) {
        demandNoticesWithAdvancePaymentsOnDateDetails.push({
          id: dn.id,
          productName: dn.productName,
          customerContactNumber: dn.customerContactNumber,
          amountPaidOnDate: amountPaidForThisDnOnDate,
          paymentMethodsOnDate: Array.from(methodsUsedForThisDnOnDate).map(m => m.replace('_',' ').replace(/\b\w/g, char => char.toUpperCase())),
          dnTotalAgreedAmount: dn.agreedPrice * dn.quantityRequested,
          dnTotalAdvancePaid: (dn.payments || []).reduce((sum,p) => sum + p.amount, 0),
          lastActivityTimeOnDate: latestPaymentTimeOnDateForDN,
        });
      }
    });
    
    ordersWithPaymentsOnDateDetails.sort((a, b) => {
        const orderA = orders.find(o => o.id === a.id);
        const orderB = orders.find(o => o.id === b.id);
        const paymentsA = (orderA?.payments || []).filter(p => p.paymentDate && isValid(parseISO(p.paymentDate)) && p.cashierId === currentUser.id && isSameDay(parseISO(p.paymentDate), selectedDate) && parseISO(p.paymentDate) >= reportStartDate && parseISO(p.paymentDate) <= reportEndDate);
        const paymentsB = (orderB?.payments || []).filter(p => p.paymentDate && isValid(parseISO(p.paymentDate)) && p.cashierId === currentUser.id && isSameDay(parseISO(p.paymentDate), selectedDate) && parseISO(p.paymentDate) >= reportStartDate && parseISO(p.paymentDate) <= reportEndDate);
        const latestPaymentA = paymentsA.sort((x,y) => {
            if(!x.paymentDate || !y.paymentDate) return 0;
            return parseISO(y.paymentDate).getTime() - parseISO(x.paymentDate).getTime();
        })[0]?.paymentDate;
        const latestPaymentB = paymentsB.sort((x,y) => {
            if(!x.paymentDate || !y.paymentDate) return 0;
            return parseISO(y.paymentDate).getTime() - parseISO(x.paymentDate).getTime();
        })[0]?.paymentDate;

        const dateA = latestPaymentA || orderA?.updatedAt || orderA?.createdAt || '';
        const dateB = latestPaymentB || orderB?.updatedAt || orderB?.createdAt || '';
        
        if (!dateA || !dateB || !isValid(parseISO(dateA)) || !isValid(parseISO(dateB))) return 0;
        return parseISO(dateB).getTime() - parseISO(dateA).getTime();
    });

    demandNoticesWithAdvancePaymentsOnDateDetails.sort((a, b) => {
        const dnA = allDemandNotices.find(dn => dn.id === a.id);
        const dnB = allDemandNotices.find(dn => dn.id === b.id);
        const paymentsA_DN = (dnA?.payments || []).filter(p => p.paymentDate && isValid(parseISO(p.paymentDate)) && p.cashierId === currentUser.id && isSameDay(parseISO(p.paymentDate), selectedDate) && parseISO(p.paymentDate) >= reportStartDate && parseISO(p.paymentDate) <= reportEndDate);
        const paymentsB_DN = (dnB?.payments || []).filter(p => p.paymentDate && isValid(parseISO(p.paymentDate)) && p.cashierId === currentUser.id && isSameDay(parseISO(p.paymentDate), selectedDate) && parseISO(p.paymentDate) >= reportStartDate && parseISO(p.paymentDate) <= reportEndDate);
        const latestPaymentA_DN = paymentsA_DN.sort((x,y) => {
            if(!x.paymentDate || !y.paymentDate) return 0;
            return parseISO(y.paymentDate).getTime() - parseISO(x.paymentDate).getTime();
        })[0]?.paymentDate;
        const latestPaymentB_DN = paymentsB_DN.sort((x,y) => {
            if(!x.paymentDate || !y.paymentDate) return 0;
            return parseISO(y.paymentDate).getTime() - parseISO(x.paymentDate).getTime();
        })[0]?.paymentDate;

        const dateA_DN = latestPaymentA_DN || dnA?.updatedAt || dnA?.createdAt || '';
        const dateB_DN = latestPaymentB_DN || dnB?.updatedAt || dnB?.createdAt || '';

        if (!dateA_DN || !dateB_DN || !isValid(parseISO(dateA_DN)) || !isValid(parseISO(dateB_DN))) return 0;
        return parseISO(dateB_DN).getTime() - parseISO(dateA_DN).getTime();
    });


    return {
        totalOrdersFullyPaidOnDate,
        totalPaymentsOnDateByMethod,
        grandTotalPaymentsOnDate,
        ordersWithPaymentsOnDateDetails,
        demandNoticesWithAdvancePaymentsOnDateDetails
    };
  }, [currentUser, orders, allDemandNotices, selectedDate, startTime, endTime]);

  if (!currentUser || (currentUser.role !== 'cashier' && currentUser.role !== 'express')) {
    return null;
  }

  const titleDatePart = selectedDate ? format(selectedDate, 'PPP') : 'No date selected';
  let titleTimePart = "";

  if (startTime && /^\d{2}:\d{2}$/.test(startTime)) {
    const parsedStartTimeInstance = parse(startTime, 'HH:mm', new Date());
    if (isValid(parsedStartTimeInstance)) {
      titleTimePart += ` from ${format(parsedStartTimeInstance, 'p')}`;
    }
  }
  if (endTime && /^\d{2}:\d{2}$/.test(endTime)) {
    const parsedEndTimeInstance = parse(endTime, 'HH:mm', new Date());
    if (isValid(parsedEndTimeInstance)) {
      if (titleTimePart.includes('from')) { // If start time was also added
        titleTimePart += ` to ${format(parsedEndTimeInstance, 'p')}`;
      } else { // Only end time is specified
        titleTimePart = ` until ${format(parsedEndTimeInstance, 'p')}`;
      }
    }
  }

  return (
    <Card className="shadow-lg w-full">
      <CardHeader className="p-6">
        <div className={cn(
          "flex flex-col gap-3", // Main container for title and filters
          context === 'profile' ? 'no-print' : '', 'date-picker-container'
        )}>
           <h3 className="text-xl flex items-center report-title-data">
            <History className="mr-2 h-6 w-6 text-primary" />
            Shift Summary for: {titleDatePart}{titleTimePart}
          </h3>
          {/* Filter controls grouped together */}
          <div className="flex flex-col sm:flex-row gap-3 items-center sm:items-end">
            <div className="w-full sm:w-auto">
              <Label htmlFor={datePickerButtonId} className="text-xs mb-1 block">Select Date</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    id={datePickerButtonId}
                    variant={"outline"}
                    className={cn("w-full justify-start text-left font-normal h-9")}
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {selectedDate ? format(selectedDate, "PPP") : <span>Pick a date</span>}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0">
                  <Calendar
                    mode="single"
                    selected={selectedDate}
                    onSelect={setSelectedDate}
                    initialFocus
                    disabled={(date) => date > new Date() || date < new Date("2000-01-01")}
                  />
                </PopoverContent>
              </Popover>
            </div>
            {/* Time Inputs */}
            <div className="w-full sm:w-auto">
              <Label htmlFor={`${datePickerButtonId}-start-time`} className="text-xs mb-1 block">Start Time</Label>
              <Input
                id={`${datePickerButtonId}-start-time`}
                type="time"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="h-9 w-full"
              />
            </div>
            <div className="w-full sm:w-auto">
              <Label htmlFor={`${datePickerButtonId}-end-time`} className="text-xs mb-1 block">End Time</Label>
              <Input
                id={`${datePickerButtonId}-end-time`}
                type="time"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="h-9 w-full"
              />
            </div>
          </div>
        </div>
        <CardDescription className="text-sm text-muted-foreground pt-2">Summary of payments processed on the selected date and time range.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6 p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-muted/30 summary-card-data">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center text-muted-foreground title-data">
                <CheckCircle className="mr-2 h-4 w-4" /> Orders Fully Paid
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold value-data">{shiftSummary.totalOrdersFullyPaidOnDate}</p>
            </CardContent>
          </Card>
          <Card className="bg-muted/30 col-span-1 md:col-span-2 summary-card-data">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium flex items-center text-muted-foreground title-data">
                <Wallet className="mr-2 h-4 w-4" /> Payments Received by Method
              </CardTitle>
            </CardHeader>
            <CardContent className="payment-method-summary value-data">
              {Object.entries(shiftSummary.totalPaymentsOnDateByMethod)
                .filter(([method]) => method !== 'advance_on_dn') 
                .map(([method, amount]) => (
                amount > 0 &&
                <div key={method} className="flex justify-between text-sm">
                  <span className="capitalize">{method.replace('_',' ')}:</span>
                  <span className="font-medium">OMR {amount.toFixed(2)}</span>
                </div>
              ))}
               {Object.entries(shiftSummary.totalPaymentsOnDateByMethod)
                .filter(([method]) => method !== 'advance_on_dn')
                .every(([,amount]) => amount === 0) && (
                 <p className="text-xs text-muted-foreground">No new tender payments recorded for this period.</p>
               )}
            </CardContent>
          </Card>
        </div>
        <div className="text-right grand-total-line">
          <p className="text-lg font-bold flex items-center justify-end grand-total-value-data">
            <DollarSign className="mr-1 h-5 w-5 text-green-600" />
            Grand Total New Tender:
            <span className="ml-2 text-green-600">OMR {shiftSummary.grandTotalPaymentsOnDate.toFixed(2)}</span>
          </p>
        </div>

        {shiftSummary.ordersWithPaymentsOnDateDetails.length > 0 && (
            <div>
                <h4 className="text-md font-semibold mb-2 flex items-center section-title">
                    <ListChecks className="mr-2 h-5 w-5 text-muted-foreground" />
                    Orders with Activity:
                </h4>
                 <ScrollArea className="h-[150px] border rounded-md">
                    <Table className="orders-table-data">
                        <TableHeader>
                            <TableRow>
                                <TableHead>Order ID</TableHead>
                                <TableHead>Time</TableHead>
                                <TableHead className="text-right">Paid/Applied</TableHead>
                                <TableHead className="text-right">Order Total</TableHead>
                                <TableHead>Methods</TableHead>
                                <TableHead>Current Status</TableHead>
                                <TableHead className="text-center">Closed Today?</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {shiftSummary.ordersWithPaymentsOnDateDetails.map(detail => (
                                <TableRow key={detail.id}>
                                    <TableCell className="font-medium">{detail.id}</TableCell>
                                    <TableCell className="text-xs text-muted-foreground">{detail.lastActivityTimeOnDate || '-'}</TableCell>
                                    <TableCell className="text-right">OMR {detail.amountPaidOnDate.toFixed(2)}</TableCell>
                                    <TableCell className="text-right">OMR {detail.orderTotalAmount.toFixed(2)}</TableCell>
                                    <TableCell>{detail.paymentMethodsOnDate.join(', ')}</TableCell>
                                    <TableCell>
                                        <Badge variant={detail.orderStatus === 'paid' || detail.orderStatus === 'completed' ? 'default' : detail.orderStatus === 'partial_payment' ? 'outline' : 'secondary'}
                                            className={cn(
                                                (detail.orderStatus === 'paid' || detail.orderStatus === 'completed') && 'bg-green-100 text-green-700 border-green-300',
                                                detail.orderStatus === 'partial_payment' && 'bg-orange-100 text-orange-700 border-orange-300'
                                            )}
                                        >
                                            {detail.orderStatus.replace(/_/g, ' ')}
                                        </Badge>
                                    </TableCell>
                                    <TableCell className="text-center">
                                        {detail.closedOnThisDate ?
                                            <CheckCircle className="h-5 w-5 text-green-600 mx-auto" /> :
                                            <span className="text-muted-foreground">-</span>
                                        }
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                 </ScrollArea>
            </div>
        )}

        {shiftSummary.demandNoticesWithAdvancePaymentsOnDateDetails.length > 0 && (
            <div className="mt-6">
                <h4 className="text-md font-semibold mb-2 flex items-center section-title">
                    <BellRing className="mr-2 h-5 w-5 text-muted-foreground" />
                    Demand Notices with Advance Payments:
                </h4>
                 <ScrollArea className="h-[150px] border rounded-md">
                    <Table className="dn-table-data">
                        <TableHeader>
                            <TableRow>
                                <TableHead>DN ID</TableHead>
                                <TableHead>Time</TableHead>
                                <TableHead>Product</TableHead>
                                <TableHead>Customer</TableHead>
                                <TableHead className="text-right">Amount Paid</TableHead>
                                <TableHead>Methods</TableHead>
                                <TableHead className="text-right">Total Agreed</TableHead>
                                <TableHead className="text-right">Total DN Advance</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {shiftSummary.demandNoticesWithAdvancePaymentsOnDateDetails.map(detail => (
                                <TableRow key={`dn-${detail.id}`}>
                                    <TableCell className="font-medium">{detail.id}</TableCell>
                                     <TableCell className="text-xs text-muted-foreground">{detail.lastActivityTimeOnDate || '-'}</TableCell>
                                    <TableCell>{detail.productName}</TableCell>
                                    <TableCell>{detail.customerContactNumber}</TableCell>
                                    <TableCell className="text-right">OMR {detail.amountPaidOnDate.toFixed(2)}</TableCell>
                                    <TableCell>{detail.paymentMethodsOnDate.join(', ')}</TableCell>
                                    <TableCell className="text-right">OMR {detail.dnTotalAgreedAmount.toFixed(2)}</TableCell>
                                    <TableCell className="text-right">OMR {detail.dnTotalAdvancePaid.toFixed(2)}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                 </ScrollArea>
            </div>
        )}

        {(shiftSummary.ordersWithPaymentsOnDateDetails.length === 0 && shiftSummary.demandNoticesWithAdvancePaymentsOnDateDetails.length === 0) && (
          <p className="text-center text-muted-foreground py-4 flex items-center justify-center gap-2">
            <ShoppingBag className="h-5 w-5" /> No payments recorded for the selected period.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

