
'use client';

import { useState, useMemo, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import type { Order, User, ReturnTransactionInfo, CommissionSetting } from '@/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { UsersRound, CalendarDays, AlertCircle, ShoppingCart, Package, Undo2, XCircle, ShieldAlert, BarChart3, ListFilter, Target as TargetIcon, Coins, TrendingUp } from 'lucide-react';
import { format, startOfDay, endOfDay, startOfWeek, endOfWeek, startOfMonth, endOfMonth, isWithinInterval, parseISO } from 'date-fns';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { cn } from '@/lib/utils';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';

type ReportRangePreset = 'today' | 'thisWeek' | 'thisMonth' | 'allTime' | 'custom';

interface ReportSummary {
  totalAttributedSalesValue: number;
  totalOrdersCreatedAsPrimary: number;
  totalItemsSoldByPrimary: number;
  totalReturnsProcessedByPrimary: number;
  totalValueReturnedFromPrimaryOrders: number;
  totalCancelledOrdersByPrimary: number;
  totalCommissionEarned: number;
}

export default function SalespersonReportsPage() {
  const { orders, users, hasPermission, commissionSetting } = useApp();
  const [selectedSalespersonId, setSelectedSalespersonId] = useState<string | null>(null);
  const [dateRangePreset, setDateRangePreset] = useState<ReportRangePreset>('thisMonth');
  const [customStartDate, setCustomStartDate] = useState<Date | undefined>(undefined);
  const [customEndDate, setCustomEndDate] = useState<Date | undefined>(undefined);

  const canViewPage = hasPermission('view_salesperson_reports');

  const salespeople = useMemo(() => users.filter(u => u.role === 'salesperson'), [users]);

  const { filteredOrders, reportDateRange } = useMemo(() => {
    if (!selectedSalespersonId) return { filteredOrders: [], reportDateRange: { start: new Date(), end: new Date() } };

    let startDate: Date, endDate: Date;
    const now = new Date();

    if (dateRangePreset === 'custom' && customStartDate && customEndDate) {
      startDate = startOfDay(customStartDate);
      endDate = endOfDay(customEndDate);
    } else if (dateRangePreset === 'custom') { // Default custom to this month if dates not set
      startDate = startOfMonth(now);
      endDate = endOfMonth(now);
    } else {
      switch (dateRangePreset) {
        case 'today':
          startDate = startOfDay(now);
          endDate = endOfDay(now);
          break;
        case 'thisWeek':
          startDate = startOfWeek(now, { weekStartsOn: 1 });
          endDate = endOfWeek(now, { weekStartsOn: 1 });
          break;
        case 'thisMonth':
          startDate = startOfMonth(now);
          endDate = endOfMonth(now);
          break;
        case 'allTime':
        default:
          startDate = new Date(0); // Earliest possible date
          endDate = endOfDay(now); // Ensure current day is fully included
          break;
      }
    }
    
    const filtered = orders.filter(order => {
      const isSalespersonMatch = order.primarySalespersonId === selectedSalespersonId || order.secondarySalespersonId === selectedSalespersonId;
      if (!isSalespersonMatch) return false;
      const orderDate = parseISO(order.createdAt);
      return isWithinInterval(orderDate, { start: startDate, end: endDate });
    }).sort((a, b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime());
    
    return { filteredOrders: filtered, reportDateRange: { start: startDate, end: endDate } };

  }, [selectedSalespersonId, orders, dateRangePreset, customStartDate, customEndDate]);

  const calculateCommission = (attributedSales: number, setting: CommissionSetting | null): number => {
    if (!setting || !setting.isActive || attributedSales <= setting.salesTarget) {
      return 0;
    }
    const salesAboveTarget = attributedSales - setting.salesTarget;
    if (salesAboveTarget <= 0 || setting.commissionInterval <= 0) {
      return 0;
    }

    const numberOfIntervals = Math.floor(salesAboveTarget / setting.commissionInterval);
    if (numberOfIntervals <= 0) {
      return 0;
    }

    const commissionPerInterval = setting.commissionInterval * (setting.commissionPercentage / 100);
    return numberOfIntervals * commissionPerInterval;
  };

  const reportSummary = useMemo((): ReportSummary => {
    let totalAttributedSalesValue = 0;
    let totalOrdersCreatedAsPrimary = 0;
    let totalItemsSoldByPrimary = 0;
    let totalReturnsProcessedByPrimary = 0;
    let totalValueReturnedFromPrimaryOrders = 0;
    let totalCancelledOrdersByPrimary = 0;

    filteredOrders.forEach(order => {
      let salespersonShareOfOrderValue = 0;
      if (order.primarySalespersonId === selectedSalespersonId) {
        salespersonShareOfOrderValue = order.totalAmount * (order.primarySalespersonCommission ?? 1);
      } else if (order.secondarySalespersonId === selectedSalespersonId) {
        salespersonShareOfOrderValue = order.totalAmount * (order.secondarySalespersonCommission ?? 0);
      }

      // Only count towards sales value if order is paid or completed
      if (order.status === 'paid' || order.status === 'completed') {
        totalAttributedSalesValue += salespersonShareOfOrderValue;
      }
      
      // Metrics specific to when the selected salesperson was PRIMARY on the order
      if (order.primarySalespersonId === selectedSalespersonId) {
        totalOrdersCreatedAsPrimary++;
        if (order.status === 'paid' || order.status === 'completed') {
          order.items.forEach(item => totalItemsSoldByPrimary += item.quantity);
        }
        if (order.status === 'cancelled') {
          totalCancelledOrdersByPrimary++;
        }
        // If returns happened on an order where this salesperson was primary
        if (order.returnTransactions && order.returnTransactions.length > 0) {
          totalReturnsProcessedByPrimary++; // Count of orders with returns
          order.returnTransactions.forEach(rt => {
            // Value returned from orders where this SP was primary
            totalValueReturnedFromPrimaryOrders += rt.totalValueOfReturnedItems;
          });
        }
      }
    });
    
    // Commission is calculated on the total attributed sales value (after splits)
    const totalCommissionEarned = calculateCommission(totalAttributedSalesValue, commissionSetting);

    return {
      totalAttributedSalesValue,
      totalOrdersCreatedAsPrimary,
      totalItemsSoldByPrimary,
      totalReturnsProcessedByPrimary,
      totalValueReturnedFromPrimaryOrders,
      totalCancelledOrdersByPrimary,
      totalCommissionEarned
    };
  }, [filteredOrders, selectedSalespersonId, commissionSetting]);

  if (!canViewPage) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to view this page.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <UsersRound className="mr-2 h-7 w-7 text-primary" /> Salesperson Performance Report
          </CardTitle>
          <CardDescription>Analyze sales data, returns, cancellations, and commissions for individual salespersons.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-end p-4 border rounded-lg bg-muted/20">
            <div>
              <Label htmlFor="salesperson-select" className="text-sm font-medium">Select Salesperson</Label>
              <Select value={selectedSalespersonId || ''} onValueChange={setSelectedSalespersonId}>
                <SelectTrigger id="salesperson-select" className="w-full h-10">
                  <SelectValue placeholder="Choose a salesperson" />
                </SelectTrigger>
                <SelectContent>
                  {salespeople.map(sp => (
                    <SelectItem key={sp.id} value={sp.id}>{sp.username}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="daterange-preset-select" className="text-sm font-medium">Date Range</Label>
              <Select value={dateRangePreset} onValueChange={(value) => { setDateRangePreset(value as ReportRangePreset); if(value !== 'custom') {setCustomStartDate(undefined); setCustomEndDate(undefined);}}}>
                <SelectTrigger id="daterange-preset-select" className="w-full h-10">
                  <SelectValue placeholder="Select period" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="today">Today</SelectItem>
                  <SelectItem value="thisWeek">This Week</SelectItem>
                  <SelectItem value="thisMonth">This Month</SelectItem>
                  <SelectItem value="allTime">All Time</SelectItem>
                  <SelectItem value="custom">Custom Range</SelectItem>
                </SelectContent>
              </Select>
            </div>
             {dateRangePreset === 'custom' && (
              <div className="grid grid-cols-2 gap-2 lg:col-span-1 items-end">
                 <div>
                    <Label htmlFor="custom-start-date" className="text-xs">Start Date</Label>
                    <Popover>
                      <PopoverTrigger asChild>
                        <Button id="custom-start-date" variant="outline" className={cn("w-full h-10 justify-start text-left font-normal", !customStartDate && "text-muted-foreground")}>
                          <CalendarDays className="mr-2 h-4 w-4" />
                          {customStartDate ? format(customStartDate, "PPP") : <span>Pick start</span>}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0"><Calendar mode="single" selected={customStartDate} onSelect={setCustomStartDate} /></PopoverContent>
                    </Popover>
                </div>
                <div>
                    <Label htmlFor="custom-end-date" className="text-xs">End Date</Label>
                     <Popover>
                      <PopoverTrigger asChild>
                        <Button id="custom-end-date" variant="outline" className={cn("w-full h-10 justify-start text-left font-normal", !customEndDate && "text-muted-foreground")}>
                          <CalendarDays className="mr-2 h-4 w-4" />
                          {customEndDate ? format(customEndDate, "PPP") : <span>Pick end</span>}
                        </Button>
                      </PopoverTrigger>
                      <PopoverContent className="w-auto p-0"><Calendar mode="single" selected={customEndDate} onSelect={setCustomEndDate} disabled={(date) => customStartDate ? date < customStartDate : false} /></PopoverContent>
                    </Popover>
                </div>
              </div>
            )}
          </div>

          {!selectedSalespersonId ? (
            <div className="text-center py-10">
              <ListFilter className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <p className="text-lg font-medium">Please select a salesperson to view their report.</p>
            </div>
          ) : (
            <>
              <div className="border-t pt-6">
                 <h3 className="text-lg font-semibold mb-3">
                    Report for {salespeople.find(s => s.id === selectedSalespersonId)?.username || 'Selected Salesperson'} ({format(reportDateRange.start, 'PP')} - {format(reportDateRange.end, 'PP')})
                </h3>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    <StatCard title="Total Attributed Sales" value={`OMR ${reportSummary.totalAttributedSalesValue.toFixed(2)}`} currencySymbol="OMR" />
                    <StatCard title="Commission Earned" value={`OMR ${reportSummary.totalCommissionEarned.toFixed(2)}`} currencySymbol="OMR" color={commissionSetting?.isActive ? "text-green-600" : "text-muted-foreground"} />
                    <StatCard title="Orders (Primary)" value={reportSummary.totalOrdersCreatedAsPrimary.toString()} icon={ShoppingCart} />
                    <StatCard title="Items Sold (Primary)" value={reportSummary.totalItemsSoldByPrimary.toString()} icon={Package} />
                    <StatCard title="Returns (Primary Orders)" value={reportSummary.totalReturnsProcessedByPrimary.toString()} icon={Undo2} color="text-orange-600" />
                    <StatCard title="Value Returned (Primary Orders)" value={`OMR ${reportSummary.totalValueReturnedFromPrimaryOrders.toFixed(2)}`} currencySymbol="OMR" color="text-orange-600" />
                    <StatCard title="Cancelled (Primary Orders)" value={reportSummary.totalCancelledOrdersByPrimary.toString()} icon={XCircle} color="text-red-600" />
                </div>
                {commissionSetting && (
                  <Card className="mt-4 bg-muted/30">
                    <CardHeader className="pb-2 pt-4">
                      <CardTitle className="text-md flex items-center"><TargetIcon className="mr-2 h-5 w-5 text-muted-foreground"/> Active Commission Rules</CardTitle>
                    </CardHeader>
                    <CardContent className="text-xs space-y-1 pt-0 pb-4">
                      <p>Status: <span className={cn("font-semibold", commissionSetting.isActive ? "text-green-600" : "text-red-600")}>{commissionSetting.isActive ? "Active" : "Inactive"}</span></p>
                      <p>Sales Target: <span className="font-semibold">OMR {commissionSetting.salesTarget.toFixed(2)}</span></p>
                      <p>Commission Interval: <span className="font-semibold">OMR {commissionSetting.commissionInterval.toFixed(2)}</span></p>
                      <p>Commission Rate: <span className="font-semibold">{commissionSetting.commissionPercentage}%</span> (on each full interval above target)</p>
                    </CardContent>
                  </Card>
                )}
              </div>
              
              {filteredOrders.length === 0 ? (
                <div className="text-center py-10">
                  <AlertCircle className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
                  <p className="text-lg font-medium">No data found for the selected salesperson and period.</p>
                </div>
              ) : (
                <div className="border-t pt-6">
                  <h3 className="text-lg font-semibold mb-3">Detailed Orders</h3>
                  <ScrollArea className="h-[calc(100vh-30rem)] md:h-[calc(100vh-25rem)]">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Order ID</TableHead>
                          <TableHead>Date</TableHead>
                          <TableHead>Customer</TableHead>
                          <TableHead className="text-center">Items</TableHead>
                          <TableHead className="text-right">Order Total (OMR)</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead>Your Role &amp; Share</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredOrders.map((order) => {
                          let roleText = "";
                          let shareText = "";
                          if (order.primarySalespersonId === selectedSalespersonId) {
                            roleText = "Primary";
                            shareText = `(${( (order.primarySalespersonCommission ?? 1) * 100).toFixed(0)}%)`;
                          } else if (order.secondarySalespersonId === selectedSalespersonId) {
                            roleText = "Secondary";
                            shareText = `(${( (order.secondarySalespersonCommission ?? 0) * 100).toFixed(0)}%)`;
                          }
                          return (
                          <TableRow key={order.id}>
                            <TableCell className="font-medium">{order.id}</TableCell>
                            <TableCell>{format(parseISO(order.createdAt), 'PPp')}</TableCell>
                            <TableCell>{order.customerName || 'N/A'}</TableCell>
                            <TableCell className="text-center">{order.items.reduce((sum, item) => sum + item.quantity, 0)}</TableCell>
                            <TableCell className="text-right">{order.totalAmount.toFixed(2)}</TableCell>
                            <TableCell>
                                <Badge variant={order.status === 'cancelled' ? 'destructive' : order.status === 'returned' ? 'outline' : 'default'} 
                                className={cn(order.status === 'returned' && 'bg-orange-100 text-orange-700 border-orange-300', 
                                             (order.status === 'paid' || order.status === 'completed') && 'bg-green-100 text-green-700 border-green-300',
                                             order.status === 'pending_payment' && 'bg-yellow-100 text-yellow-700 border-yellow-300'
                                             )}>
                                    {order.status.replace(/_/g, ' ')}
                                </Badge>
                            </TableCell>
                            <TableCell>
                                {roleText} {shareText}
                            </TableCell>
                          </TableRow>
                        );})}
                      </TableBody>
                    </Table>
                  </ScrollArea>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface StatCardProps {
    title: string;
    value: string;
    icon?: React.ElementType;
    currencySymbol?: string;
    color?: string;
}
const StatCard: React.FC<StatCardProps> = ({ title, value, icon: Icon, currencySymbol, color = "text-primary" }) => (
    <Card className="shadow">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {Icon && <Icon className={cn("h-5 w-5", color)} />}
        {currencySymbol && <span className={cn("font-semibold text-lg", color)}>{currencySymbol}</span>}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
);

