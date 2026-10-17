
'use client';

import { useState, useMemo, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import type { Order, User, CommissionSetting } from '@/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { BarChart3, CalendarDays, AlertCircle, ShoppingBag, Target, Coins, TrendingUp, Info } from 'lucide-react';
import { format, startOfDay, endOfDay, startOfWeek, endOfWeek, startOfMonth, endOfMonth, isWithinInterval, parseISO } from 'date-fns';
import { cn } from '@/lib/utils';

type ReportRange = 'today' | 'thisWeek' | 'thisMonth';

interface SalesReportSummary {
  totalAttributedSalesValue: number;
  totalOrdersContributed: number;
  commissionEarned: number;
  salesTowardsTarget: number;
}

export default function SalespersonOwnReportsPage() {
  const { orders, currentUser, commissionSetting, isDataLoaded } = useApp();
  const [selectedRange, setSelectedRange] = useState<ReportRange>('thisMonth');

  const filteredOrders = useMemo(() => {
    if (!currentUser || !isDataLoaded) return [];

    const now = new Date();
    let startDate: Date, endDate: Date;

    switch (selectedRange) {
      case 'today':
        startDate = startOfDay(now);
        endDate = endOfDay(now);
        break;
      case 'thisWeek':
        startDate = startOfWeek(now, { weekStartsOn: 1 });
        endDate = endOfWeek(now, { weekStartsOn: 1 });
        break;
      case 'thisMonth':
      default:
        startDate = startOfMonth(now);
        endDate = endOfMonth(now);
        break;
    }

    return orders.filter(order => {
      const isSalespersonInvolved = order.primarySalespersonId === currentUser.id || order.secondarySalespersonId === currentUser.id;
      if (!isSalespersonInvolved) return false;
      
      const orderDate = parseISO(order.createdAt);
      return isWithinInterval(orderDate, { start: startDate, end: endDate });
    }).sort((a, b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime());
  }, [selectedRange, orders, currentUser, isDataLoaded]);

  const calculateCommission = (attributedSales: number, setting: CommissionSetting | null): number => {
    if (!setting || !setting.isActive || attributedSales <= setting.salesTarget) {
      return 0;
    }
    const salesAboveTarget = attributedSales - setting.salesTarget;
    if (salesAboveTarget <= 0 || setting.commissionInterval <= 0) return 0;
    
    const numberOfIntervals = Math.floor(salesAboveTarget / setting.commissionInterval);
    if (numberOfIntervals <= 0) return 0;

    const commissionPerInterval = setting.commissionInterval * (setting.commissionPercentage / 100);
    return numberOfIntervals * commissionPerInterval;
  };

  const reportSummary = useMemo((): SalesReportSummary => {
    if (!currentUser || !isDataLoaded) return { totalAttributedSalesValue: 0, totalOrdersContributed: 0, commissionEarned: 0, salesTowardsTarget: 0 };

    let totalAttributedSalesValue = 0;
    let totalOrdersContributed = 0;

    filteredOrders.forEach(order => {
      if (order.status === 'paid' || order.status === 'completed') {
        let orderShare = 0;
        if (order.primarySalespersonId === currentUser.id) {
          orderShare = order.totalAmount * (order.primarySalespersonCommission ?? 1);
          totalOrdersContributed++;
        } else if (order.secondarySalespersonId === currentUser.id) {
          orderShare = order.totalAmount * (order.secondarySalespersonCommission ?? 0);
           // Only count as contributed if they have some commission or it's a primary contribution
           if (order.secondarySalespersonCommission && order.secondarySalespersonCommission > 0) {
               totalOrdersContributed++;
           }
        }
        totalAttributedSalesValue += orderShare;
      }
    });
    
    const commissionEarned = calculateCommission(totalAttributedSalesValue, commissionSetting);

    return {
      totalAttributedSalesValue,
      totalOrdersContributed,
      commissionEarned,
      salesTowardsTarget: totalAttributedSalesValue, // This represents total sales for the period, to compare against target
    };
  }, [filteredOrders, currentUser, commissionSetting, isDataLoaded]);
  
  if (!isDataLoaded) {
    return <div className="p-6 text-center">Loading report data...</div>;
  }

  if (!currentUser) {
    return <div className="p-6 text-center text-destructive">User not found. Please log in again.</div>;
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <BarChart3 className="mr-2 h-7 w-7 text-primary" />
            My Sales & Commission Report
          </CardTitle>
          <CardDescription>Review your sales performance, targets, and estimated commission.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 mb-6">
            <CalendarDays className="h-5 w-5 text-muted-foreground" />
            <Select value={selectedRange} onValueChange={(value) => setSelectedRange(value as ReportRange)}>
              <SelectTrigger className="w-full md:w-[200px] h-10">
                <SelectValue placeholder="Select period" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="today">Today</SelectItem>
                <SelectItem value="thisWeek">This Week</SelectItem>
                <SelectItem value="thisMonth">This Month</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 mb-6">
            <StatCard title="Attributed Sales Value" value={`OMR ${reportSummary.totalAttributedSalesValue.toFixed(2)}`} icon={TrendingUp} />
            <StatCard title="Orders Contributed" value={reportSummary.totalOrdersContributed.toString()} icon={ShoppingBag} />
            <StatCard title="Estimated Commission" value={`OMR ${reportSummary.commissionEarned.toFixed(2)}`} icon={Coins} color={commissionSetting?.isActive ? "text-green-600" : "text-muted-foreground"} />
          </div>

          {commissionSetting && (
            <Card className="mb-6 bg-muted/30">
              <CardHeader className="pb-3 pt-4">
                <CardTitle className="text-md flex items-center"><Target className="mr-2 h-5 w-5 text-muted-foreground"/> Current Commission Rules</CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-1.5 pt-0 pb-4">
                <p>Status: <span className={cn("font-semibold", commissionSetting.isActive ? "text-green-600" : "text-red-600")}>{commissionSetting.isActive ? "Active" : "Inactive"}</span></p>
                <p>Sales Target for Commission: <span className="font-semibold">OMR {commissionSetting.salesTarget.toFixed(2)}</span></p>
                <p>Commission Interval: <span className="font-semibold">OMR {commissionSetting.commissionInterval.toFixed(2)}</span></p>
                <p>Commission Rate: <span className="font-semibold">{commissionSetting.commissionPercentage}%</span> (on each full interval above target)</p>
                 {!commissionSetting.isActive && (
                  <p className="text-xs text-orange-600 mt-1">Note: Commission system is currently inactive. No commission will be calculated.</p>
                )}
              </CardContent>
              {commissionSetting.isActive && (
              <CardFooter className="text-xs text-muted-foreground border-t pt-3 pb-3">
                <Info className="h-4 w-4 mr-2 shrink-0" />
                You earn {commissionSetting.commissionPercentage}% on every OMR {commissionSetting.commissionInterval.toFixed(2)} of sales made *above* your OMR {commissionSetting.salesTarget.toFixed(2)} target for the period.
              </CardFooter>
              )}
            </Card>
          )}

          {filteredOrders.length === 0 && isDataLoaded ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <AlertCircle className="w-16 h-16 text-muted-foreground mb-4" />
              <p className="text-xl font-semibold">No sales data found for this period.</p>
              <p className="text-muted-foreground">Try selecting a different period.</p>
            </div>
          ) : isDataLoaded && (
            <ScrollArea className="h-[calc(100vh-36rem)] md:h-[calc(100vh-32rem)] border rounded-md">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Invoice ID</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Your Role</TableHead>
                    <TableHead className="text-right">Order Total</TableHead>
                    <TableHead className="text-right">Your Share</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredOrders.map((order) => {
                    let role = "";
                    let shareAmount = 0;
                    if (order.primarySalespersonId === currentUser.id) {
                      role = `Primary (${((order.primarySalespersonCommission ?? 1) * 100).toFixed(0)}%)`;
                      shareAmount = order.totalAmount * (order.primarySalespersonCommission ?? 1);
                    } else if (order.secondarySalespersonId === currentUser.id) {
                      role = `Secondary (${((order.secondarySalespersonCommission ?? 0) * 100).toFixed(0)}%)`;
                      shareAmount = order.totalAmount * (order.secondarySalespersonCommission ?? 0);
                    }
                    return (
                    <TableRow key={order.id}>
                      <TableCell className="font-medium">{order.id}</TableCell>
                      <TableCell>{format(parseISO(order.createdAt), 'PPp')}</TableCell>
                      <TableCell>{role}</TableCell>
                      <TableCell className="text-right">OMR {order.totalAmount.toFixed(2)}</TableCell>
                      <TableCell className="text-right font-semibold">OMR {shareAmount.toFixed(2)}</TableCell>
                      <TableCell className="capitalize">{order.status.replace(/_/g, ' ')}</TableCell>
                    </TableRow>
                  )})}
                </TableBody>
              </Table>
            </ScrollArea>
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
    color?: string;
}
const StatCard: React.FC<StatCardProps> = ({ title, value, icon: Icon, color = "text-primary" }) => (
    <Card className="shadow">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        {Icon && <Icon className={cn("h-4 w-4", color)} />}
      </CardHeader>
      <CardContent>
        <div className={cn("text-2xl font-bold", value.startsWith("OMR") ? color : "")}>{value}</div>
      </CardContent>
    </Card>
);
