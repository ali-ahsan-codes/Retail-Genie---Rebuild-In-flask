
'use client';

import { useState, useEffect, useMemo } from 'react';
import { useApp } from '@/context/AppContext';
import type { Order, OrderStatus, User, AttendanceLog, BreakLog, Product, CommissionSetting, PaymentDetail } from '@/types';
import {
  Download, Filter, Calendar as CalendarIconOriginal, ShieldAlert, FileText, ListChecks,
  ShoppingCart as ShoppingCartIcon,
  Package as PackageIcon,
  Users as UsersIconLucide,
  UserRound,
  CalendarDays as CalendarDaysIcon,
  Coffee as CoffeeIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { useToast } from '@/hooks/use-toast';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { format, parseISO, startOfDay, endOfDay, isWithinInterval, intervalToDuration, isValid } from 'date-fns';
import { cn } from '@/lib/utils';

const ALL_DATA_SECTIONS = [
  { id: 'sales', label: 'Sales & Order Details', icon: ShoppingCartIcon },
  { id: 'attendance', label: 'Attendance Logs', icon: CalendarDaysIcon },
  { id: 'breaks', label: 'Break Logs', icon: CoffeeIcon },
  { id: 'performance', label: 'Salesperson Performance', icon: UsersIconLucide },
  { id: 'products', label: 'Product List', icon: PackageIcon },
  { id: 'users', label: 'User List', icon: UserRound },
] as const;

type DataSectionId = typeof ALL_DATA_SECTIONS[number]['id'];

const AdminAccountsPage: React.FC = () => {
  const { orders, products, users, attendanceLogs, breakLogs, commissionSetting, hasPermission, isDataLoaded } = useApp();
  const { toast } = useToast();

  const [startDateFilter, setStartDateFilter] = useState<Date | undefined>(undefined);
  const [endDateFilter, setEndDateFilter] = useState<Date | undefined>(undefined);
  const [selectedDataSections, setSelectedDataSections] = useState<DataSectionId[]>(ALL_DATA_SECTIONS.map(s => s.id));

  const canViewReports = hasPermission('view_reports');

  const handleDataSectionChange = (sectionId: DataSectionId) => {
    setSelectedDataSections(prev =>
      prev.includes(sectionId) ? prev.filter(s => s !== sectionId) : [...prev, sectionId]
    );
  };

  const handleSelectAllDataSectionsChange = (checked: boolean) => {
    setSelectedDataSections(checked ? ALL_DATA_SECTIONS.map(s => s.id) : []);
  };

  const formatValidDuration = (duration: Duration | null | undefined): string => {
    if (!duration || Object.keys(duration).length === 0) return '00:00:00';
    const { hours = 0, minutes = 0, seconds = 0 } = duration;
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  };
  
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

  const handleExportCSV = () => {
    if (!canViewReports) {
      toast({ title: "Permission Denied", description: "You cannot export data.", variant: "destructive" });
      return;
    }
    if (selectedDataSections.length === 0) {
      toast({ title: "No Data Selected", description: "Please select at least one data section to export.", variant: "default" });
      return;
    }

    let csvContentParts: string[] = [];
    const dateRangeString = (startDateFilter && endDateFilter)
        ? `_(${format(startDateFilter, 'yyyyMMdd')}_to_${format(endDateFilter, 'yyyyMMdd')})`
        : (startDateFilter ? `_from_${format(startDateFilter, 'yyyyMMdd')}` : (endDateFilter ? `_until_${format(endDateFilter, 'yyyyMMdd')}` : '_all_dates'));

    const escapeCsvCell = (value: any): string => {
        if (value === null || value === undefined) {
            return '""';
        }
        const strValue = String(value).replace(/"/g, '""'); // Escape double quotes
        return `"${strValue}"`;
    };

    // --- Sales Data Section ---
    if (selectedDataSections.includes('sales')) {
      const salesCsvHeader = [
        'OrderID', 'OrderDate', 'OrderTime', 'OrderStatus', 'DeliveryStatus',
        'CustomerName', 'CustomerPhone', 'DeliveryAddress',
        'PrimarySalespersonName', 'SecondarySalespersonName', 'CashierName',
        'Subtotal_OMR', 'DiscountAmount_OMR', 'AppliedDiscountPercentage', 'TotalTax_OMR', 'TotalAmount_OMR',
        'TotalPaid_OMR', 'RemainingBalance_OMR', 'PaymentMethods',
        'PaidBy_Cash_OMR', 'PaidBy_Card_OMR', 'PaidBy_BankTransfer_OMR', 'PaidBy_AdvanceOnDN_OMR',
        'ItemCount', 'ItemSummary'
      ];
      
      const filteredOrders = orders.filter((order) => {
        if (!order || !order.createdAt || !isValid(parseISO(order.createdAt))) return false;
        if (startDateFilter && endDateFilter) {
          return isWithinInterval(parseISO(order.createdAt), { start: startOfDay(startDateFilter), end: endOfDay(endDateFilter) });
        } else if (startDateFilter) {
          return parseISO(order.createdAt) >= startOfDay(startDateFilter);
        } else if (endDateFilter) {
          return parseISO(order.createdAt) <= endOfDay(endDateFilter);
        }
        return true;
      });

      if (filteredOrders.length > 0) {
        const salesData = filteredOrders.map(order => {
            const primarySalesperson = users.find(u => u.id === order.primarySalespersonId);
            const secondarySalesperson = users.find(u => u.id === order.secondarySalespersonId);
            
            const orderPaymentSummary = {
                methodsUsed: new Set<string>(), cash: 0, card: 0, bank_transfer: 0, advance_on_dn: 0, totalPaid: 0,
            };
            (order.payments || []).forEach(payment => {
                orderPaymentSummary.methodsUsed.add(payment.method);
                if (payment.method === 'cash') orderPaymentSummary.cash += payment.amount;
                else if (payment.method === 'card') orderPaymentSummary.card += payment.amount;
                else if (payment.method === 'bank_transfer') orderPaymentSummary.bank_transfer += payment.amount;
                else if (payment.method === 'advance_on_dn') orderPaymentSummary.advance_on_dn += payment.amount;
                orderPaymentSummary.totalPaid += payment.amount;
            });
            const paymentMethodsString = Array.from(orderPaymentSummary.methodsUsed).join('; ');
            
            // Get cashier from the most recent payment on the order
            const lastPayment = (order.payments && order.payments.length > 0)
              ? [...order.payments].sort((a,b) => {
                  if (!a.paymentDate || !b.paymentDate) return 0;
                  return parseISO(b.paymentDate).getTime() - parseISO(a.paymentDate).getTime();
                })[0]
              : null;
            const cashierName = lastPayment?.cashierName || 'N/A';

            const remainingBalance = (order.totalAmount || 0) - orderPaymentSummary.totalPaid;
            const itemCount = order.items?.reduce((sum, item) => sum + item.quantity, 0) || 0;
            const itemSummary = order.items?.map(item => `${item.name} (x${item.quantity})`).join('; ') || 'N/A';

            return salesCsvHeader.map(header => {
                switch(header) {
                    case 'OrderID': return escapeCsvCell(order.id || 'N/A');
                    case 'OrderDate': return escapeCsvCell(order.createdAt ? format(parseISO(order.createdAt), 'MM/dd/yyyy') : 'N/A');
                    case 'OrderTime': return escapeCsvCell(order.createdAt ? format(parseISO(order.createdAt), 'HH:mm:ss') : 'N/A');
                    case 'OrderStatus': return escapeCsvCell(order.status.replace(/_/g, ' '));
                    case 'DeliveryStatus': return escapeCsvCell(order.deliveryStatus ? order.deliveryStatus.replace(/_/g, ' ') : 'N/A');
                    case 'CustomerName': return escapeCsvCell(order.customerName || 'N/A');
                    case 'CustomerPhone': return escapeCsvCell(order.customerPhone || 'N/A');
                    case 'DeliveryAddress': return escapeCsvCell(order.deliveryAddress || '');
                    case 'PrimarySalespersonName': return escapeCsvCell(primarySalesperson?.username || 'N/A');
                    case 'SecondarySalespersonName': return escapeCsvCell(secondarySalesperson?.username || 'N/A');
                    case 'CashierName': return escapeCsvCell(cashierName);
                    case 'Subtotal_OMR': return escapeCsvCell((order.subtotal || 0).toFixed(2));
                    case 'DiscountAmount_OMR': return escapeCsvCell((order.discountAmount || 0).toFixed(2));
                    case 'AppliedDiscountPercentage': return escapeCsvCell(`${(order.appliedDiscountPercentage || order.appliedGlobalDiscountPercentage || 0).toFixed(2)}%`);
                    case 'TotalTax_OMR': return escapeCsvCell((Array.isArray(order.taxes) ? order.taxes.reduce((sum, tax) => sum + tax.amount, 0) : 0).toFixed(2));
                    case 'TotalAmount_OMR': return escapeCsvCell((order.totalAmount || 0).toFixed(2));
                    case 'TotalPaid_OMR': return escapeCsvCell(orderPaymentSummary.totalPaid.toFixed(2));
                    case 'RemainingBalance_OMR': return escapeCsvCell(remainingBalance.toFixed(2));
                    case 'PaymentMethods': return escapeCsvCell(paymentMethodsString);
                    case 'PaidBy_Cash_OMR': return escapeCsvCell(orderPaymentSummary.cash.toFixed(2));
                    case 'PaidBy_Card_OMR': return escapeCsvCell(orderPaymentSummary.card.toFixed(2));
                    case 'PaidBy_BankTransfer_OMR': return escapeCsvCell(orderPaymentSummary.bank_transfer.toFixed(2));
                    case 'PaidBy_AdvanceOnDN_OMR': return escapeCsvCell(orderPaymentSummary.advance_on_dn.toFixed(2));
                    case 'ItemCount': return escapeCsvCell(itemCount);
                    case 'ItemSummary': return escapeCsvCell(itemSummary);
                    default: return '""';
                }
            }).join(',');
        });
        csvContentParts.push([salesCsvHeader.join(','), ...salesData].join('\n'));
      }
    }

    // --- Attendance Logs Section ---
    if (selectedDataSections.includes('attendance')) {
      const attendanceCsvHeader = ['LogID', 'UserID', 'Username', 'Date', 'Time', 'Method', 'SelfieImagePath'];
      const filteredAttendance = attendanceLogs.filter(log => {
        if (!log || !log.timestamp || !isValid(parseISO(log.timestamp))) return false;
        if (startDateFilter && endDateFilter) { return isWithinInterval(parseISO(log.timestamp), { start: startOfDay(startDateFilter), end: endOfDay(endDateFilter) }); }
        else if (startDateFilter) { return parseISO(log.timestamp) >= startOfDay(startDateFilter); }
        else if (endDateFilter) { return parseISO(log.timestamp) <= endOfDay(endDateFilter); }
        return true;
      });
      if(filteredAttendance.length > 0) {
        const attendanceData = filteredAttendance.map(log => {
            const user = users.find(u => u.id === log.userId);
            return [
                escapeCsvCell(log.id), escapeCsvCell(log.userId), escapeCsvCell(user?.username || 'N/A'),
                escapeCsvCell(format(parseISO(log.timestamp), 'MM/dd/yyyy')), escapeCsvCell(format(parseISO(log.timestamp), 'HH:mm:ss')),
                escapeCsvCell(log.method || 'N/A'), escapeCsvCell(log.selfieImagePath || 'N/A')
            ].join(',');
        });
        csvContentParts.push([attendanceCsvHeader.join(','), ...attendanceData].join('\n'));
      }
    }

    // --- Break Logs Section ---
    if (selectedDataSections.includes('breaks')) {
      const breakCsvHeader = ['LogID', 'UserID', 'Username', 'StartDate', 'StartTime', 'EndDate', 'EndTime', 'DurationFormatted'];
      const filteredBreaks = breakLogs.filter(log => {
         if (!log || !log.startTime || !isValid(parseISO(log.startTime))) return false;
         const startTime = parseISO(log.startTime);
        if (startDateFilter && endDateFilter) { return isWithinInterval(startTime, { start: startOfDay(startDateFilter), end: endOfDay(endDateFilter) }); }
        else if (startDateFilter) { return startTime >= startOfDay(startDateFilter); }
        else if (endDateFilter) { return startTime <= endOfDay(endDateFilter); }
        return true;
      });
      if(filteredBreaks.length > 0) {
        const breakData = filteredBreaks.map(log => {
            const user = users.find(u => u.id === log.userId);
            const durationStr = log.durationMs ? formatValidDuration(intervalToDuration({ start: 0, end: log.durationMs })) : (log.endTime ? 'N/A' : 'Ongoing');
            return [
                escapeCsvCell(log.id), escapeCsvCell(log.userId), escapeCsvCell(user?.username || 'N/A'),
                escapeCsvCell(format(parseISO(log.startTime), 'MM/dd/yyyy')), escapeCsvCell(format(parseISO(log.startTime), 'HH:mm:ss')),
                escapeCsvCell(log.endTime ? format(parseISO(log.endTime), 'MM/dd/yyyy') : 'N/A'),
                escapeCsvCell(log.endTime ? format(parseISO(log.endTime), 'HH:mm:ss') : 'N/A'),
                escapeCsvCell(durationStr)
            ].join(',');
        });
        csvContentParts.push([breakCsvHeader.join(','), ...breakData].join('\n'));
      }
    }

    // --- Salesperson Performance Section ---
    if (selectedDataSections.includes('performance')) {
        const performanceHeader = ['SalespersonID', 'SalespersonName', 'TotalOrdersContributed', 'TotalAttributedSalesValue_OMR', 'PotentialCommission_OMR'];
        const salespersons = users.filter(u => u.role === 'salesperson');
        if (salespersons.length > 0) {
            const performanceData = salespersons.map(sp => {
                let totalAttributedSales = 0;
                let ordersContributed = 0;
                orders.filter(order => { 
                    if (!order || !order.createdAt || !isValid(parseISO(order.createdAt))) return false;
                    if (startDateFilter && endDateFilter) { return isWithinInterval(parseISO(order.createdAt), { start: startOfDay(startDateFilter), end: endOfDay(endDateFilter) }); }
                    else if (startDateFilter) { return parseISO(order.createdAt) >= startOfDay(startDateFilter); }
                    else if (endDateFilter) { return parseISO(order.createdAt) <= endOfDay(endDateFilter); }
                    return true;
                }).forEach(order => {
                    if (order.primarySalespersonId === sp.id) {
                        ordersContributed++;
                        totalAttributedSales += (order.totalAmount || 0) * (order.primarySalespersonCommission ?? 1);
                    } else if (order.secondarySalespersonId === sp.id) {
                        if ((order.secondarySalespersonCommission ?? 0) > 0) ordersContributed++;
                        totalAttributedSales += (order.totalAmount || 0) * (order.secondarySalespersonCommission ?? 0);
                    }
                });
                const commission = calculateCommission(totalAttributedSales, commissionSetting);
                return [
                    escapeCsvCell(sp.id), escapeCsvCell(sp.username), escapeCsvCell(ordersContributed),
                    escapeCsvCell(totalAttributedSales.toFixed(2)), escapeCsvCell(commission.toFixed(2))
                ].join(',');
            });
             csvContentParts.push([performanceHeader.join(','), ...performanceData].join('\n'));
        }
    }

    // --- Product List Section ---
    if (selectedDataSections.includes('products')) {
        const productHeader = ['ProductID', 'ProductName', 'SKU', 'Price_OMR', 'QuantityInStock', 'Category', 'ExpiryDate', 'LowStockThreshold', 'LowStockPrice_OMR', 'IsDemandNoticeProduct'];
        if (products.length > 0) {
            const productData = products.map(p => {
                return [
                    escapeCsvCell(p.id), escapeCsvCell(p.name), escapeCsvCell(p.sku), escapeCsvCell((p.price || 0).toFixed(2)), escapeCsvCell(p.quantityInStock),
                    escapeCsvCell(p.category || 'N/A'), escapeCsvCell(p.expiryDate || 'N/A'), escapeCsvCell(p.lowStockThreshold ?? 'N/A'),
                    escapeCsvCell(p.lowStockPrice?.toFixed(2) ?? 'N/A'), escapeCsvCell(p.isDemandNoticeProduct ? 'Yes' : 'No')
                ].join(',');
            });
            csvContentParts.push([productHeader.join(','), ...productData].join('\n'));
        }
    }
    
    // --- User List Section ---
    if (selectedDataSections.includes('users')) {
        const userHeader = ['UserID', 'Username', 'Role', 'Permissions'];
        if (users.length > 0) {
            const userData = users.map(u => {
                return [
                    escapeCsvCell(u.id), escapeCsvCell(u.username), escapeCsvCell(u.role), escapeCsvCell((u.permissions || []).join('; '))
                ].join(',');
            });
            csvContentParts.push([userHeader.join(','), ...userData].join('\n'));
        }
    }

    if (csvContentParts.length === 0) {
        toast({ title: "No Data", description: "No data available for the selected sections and date range.", variant: "default" });
        return;
    }

    const finalCsvString = csvContentParts.join('\n\n'); // Separate sections with double newlines
    const blob = new Blob([finalCsvString], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    if (link.download !== undefined) {
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.download = `comprehensive_data_export${dateRangeString}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast({ title: "Export Successful", description: "Comprehensive data CSV download initiated." });
    } else {
      toast({ title: "Export Failed", description: "CSV export is not fully supported in this browser.", variant: "destructive" });
    }
  };

  if (!isDataLoaded && canViewReports) {
    return <div className="p-6 text-center">Loading data for export page...</div>;
  }

  if (!canViewReports && !hasPermission('view_admin_dashboard')) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to access data export.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <Download className="mr-2 h-7 w-7 text-primary" /> Comprehensive Data Export
          </CardTitle>
          <CardDescription>
            Select date range (for time-sensitive data) and data sections to export.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-6 p-4 border rounded-lg bg-muted/20 space-y-6">
            <div>
              <Label className="text-lg font-semibold mb-2 block">Filter by Date Range (for Sales, Attendance, Breaks):</Label>
              <div className="flex flex-col sm:flex-row gap-4">
                <div className="flex-1">
                  <Label htmlFor="start-date-filter" className="text-sm">Start Date</Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        id="start-date-filter"
                        variant={"outline"}
                        className={cn("w-full justify-start text-left font-normal h-10", !startDateFilter && "text-muted-foreground")}
                        disabled={!canViewReports}
                      >
                        <CalendarIconOriginal className="mr-2 h-4 w-4" />
                        {startDateFilter ? format(startDateFilter, "MM/dd/yyyy") : <span>Pick a start date</span>}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0">
                      <Calendar mode="single" selected={startDateFilter} onSelect={setStartDateFilter} disabled={(date) => endDateFilter ? date > endDateFilter : false} initialFocus />
                    </PopoverContent>
                  </Popover>
                </div>
                <div className="flex-1">
                  <Label htmlFor="end-date-filter" className="text-sm">End Date</Label>
                  <Popover>
                    <PopoverTrigger asChild>
                      <Button
                        id="end-date-filter"
                        variant={"outline"}
                        className={cn("w-full justify-start text-left font-normal h-10", !endDateFilter && "text-muted-foreground")}
                        disabled={!canViewReports}
                      >
                        <CalendarIconOriginal className="mr-2 h-4 w-4" />
                        {endDateFilter ? format(endDateFilter, "MM/dd/yyyy") : <span>Pick an end date</span>}
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-auto p-0">
                      <Calendar mode="single" selected={endDateFilter} onSelect={setEndDateFilter} disabled={(date) => startDateFilter ? date < startDateFilter : false} initialFocus />
                    </PopoverContent>
                  </Popover>
                </div>
              </div>
            </div>
            
            <div>
                <Label className="text-lg font-semibold mb-2 block flex items-center">
                    <ListChecks className="mr-2 h-5 w-5 text-muted-foreground" /> Data Sections to Export:
                </Label>
                <div className="flex items-center mb-3">
                    <Checkbox
                        id="selectAllDataSections"
                        checked={selectedDataSections.length === ALL_DATA_SECTIONS.length}
                        onCheckedChange={(checked) => handleSelectAllDataSectionsChange(Boolean(checked))}
                        className="mr-2"
                        disabled={!canViewReports}
                    />
                    <Label htmlFor="selectAllDataSections" className="font-medium">Select/Deselect All Data Types</Label>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-3">
                    {ALL_DATA_SECTIONS.map((section) => (
                    <div key={section.id} className="flex items-center">
                        <Checkbox
                        id={section.id}
                        checked={selectedDataSections.includes(section.id)}
                        onCheckedChange={() => handleDataSectionChange(section.id)}
                        className="mr-2"
                        disabled={!canViewReports}
                        />
                        <Label htmlFor={section.id} className="capitalize flex items-center text-sm">
                           {section.icon && <section.icon className="mr-2 h-4 w-4 text-muted-foreground" />}
                           {section.label}
                        </Label>
                    </div>
                    ))}
                </div>
            </div>
          </div>

          <Button
            onClick={handleExportCSV}
            className="w-full sm:w-auto h-11 text-base"
            disabled={!canViewReports || selectedDataSections.length === 0}
          >
            <Filter className="mr-2 h-5 w-5" /> Export Selected Data as CSV
          </Button>
        </CardContent>
      </Card>
    </div>
  );
};

export default AdminAccountsPage;
