
// src/app/(main)/admin/activity-logs/page.tsx
'use client';

import { useState, useMemo, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import type { Order, User, AttendanceLog, BreakLog } from '@/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { format, isSameDay, startOfDay, endOfDay, intervalToDuration, parseISO, isValid } from 'date-fns';
import { CalendarIcon, User as UserIcon, Activity, ShoppingCart, Briefcase, Clock, Coffee, ShieldAlert, PackageCheck, TruckIcon, AlertCircle, Camera } from 'lucide-react';
import SelfieImageDisplay from '@/components/shared/SelfieImageDisplay'; 
import { cn } from '@/lib/utils';
import { Label } from '@/components/ui/label'; 

interface DailyUserActivity {
  userId: string;
  username: string;
  role: User['role'];
  ordersCreated?: number;
  totalSalesValue?: number;
  ordersProcessed?: number; 
  ordersPrepared?: number; 
  deliveriesManaged?: number; 
  attendance?: AttendanceLog;
  breaks?: BreakLog[];
  totalBreakDuration?: string;
}

const formatValidDuration = (duration: Duration | null | undefined): string => {
  if (!duration || Object.keys(duration).length === 0) return '00:00:00'; 
  const { hours = 0, minutes = 0, seconds = 0 } = duration;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
};


export default function AdminActivityLogsPage() {
  const { orders, users, attendanceLogs, breakLogs, hasPermission, currentUser, isDataLoaded } = useApp();
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(new Date());

  const canViewLogs = hasPermission('view_activity_logs');

  const dailyActivityData = useMemo(() => {
    if (!selectedDate || !canViewLogs || !isDataLoaded || !users || !attendanceLogs || !breakLogs) return []; 

    const activity: Record<string, DailyUserActivity> = {};

    users.forEach(user => {
      if (!user || !user.id) return; 
      
      const userAttendanceLogs = attendanceLogs.filter(log => log.userId === user.id && isValid(parseISO(log.timestamp)));
      const userBreakLogs = breakLogs.filter(log => log.userId === user.id && isValid(parseISO(log.startTime)));
      
      activity[user.id] = {
        userId: user.id,
        username: user.username,
        role: user.role,
        ordersCreated: 0,
        totalSalesValue: 0,
        ordersProcessed: 0,
        ordersPrepared: 0,
        deliveriesManaged: 0,
        attendance: userAttendanceLogs.find(log => isValid(parseISO(log.timestamp)) && isSameDay(parseISO(log.timestamp), selectedDate)),
        breaks: userBreakLogs.filter(log => isValid(parseISO(log.startTime)) && isSameDay(parseISO(log.startTime), selectedDate)),
      };

      const totalBreakMs = activity[user.id].breaks?.reduce((sum, brk) => sum + (brk.durationMs || 0), 0) || 0;
      activity[user.id].totalBreakDuration = totalBreakMs > 0 ? 
        formatValidDuration(intervalToDuration({ start: 0, end: totalBreakMs }))
        : '00:00:00';
    });

    if (orders && orders.length > 0) {
      orders.forEach(order => {
        if (!order || !isValid(parseISO(order.createdAt)) || !isValid(parseISO(order.updatedAt))) return;

        if (isValid(parseISO(order.createdAt)) && isSameDay(parseISO(order.createdAt), selectedDate)) {
          if (activity[order.primarySalespersonId]) {
            activity[order.primarySalespersonId].ordersCreated = (activity[order.primarySalespersonId].ordersCreated || 0) + 1;
            activity[order.primarySalespersonId].totalSalesValue = (activity[order.primarySalespersonId].totalSalesValue || 0) + order.totalAmount;
          }
        }
      });
    }
    return Object.values(activity).sort((a,b) => a.username.localeCompare(b.username));
  }, [selectedDate, orders, users, attendanceLogs, breakLogs, canViewLogs, isDataLoaded]); 


  if (!canViewLogs) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to view activity logs.</p>
      </div>
    );
  }
  
  if (!isDataLoaded) { 
     return <div className="p-6 text-center">Initializing database and loading logs...</div>;
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <Activity className="mr-2 h-7 w-7 text-primary" /> Daily Activity Logs
          </CardTitle>
          <CardDescription>Monitor daily operations, user attendance, and productivity.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 mb-6">
            <Label htmlFor="activity-date" className="text-sm font-medium">Select Date:</Label>
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  id="activity-date"
                  variant={"outline"}
                  className={cn(
                    "w-[280px] justify-start text-left font-normal h-10",
                    !selectedDate && "text-muted-foreground"
                  )}
                >
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {selectedDate ? format(selectedDate, "MM/dd/yyyy") : <span>Pick a date</span>}
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

          <Tabs defaultValue="attendance_breaks" className="w-full">
            <TabsList className="grid w-full grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
              <TabsTrigger value="attendance_breaks">Attendance & Breaks</TabsTrigger>
              <TabsTrigger value="sales_activity">Sales Activity</TabsTrigger>
              <TabsTrigger value="order_status_changes">Order Status Changes</TabsTrigger>
            </TabsList>

            <TabsContent value="attendance_breaks" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center"><Clock className="mr-2 h-5 w-5 text-muted-foreground"/>User Attendance & Breaks</CardTitle>
                  <CardDescription>Summary of user clock-ins and break durations for {selectedDate ? format(selectedDate, "MM/dd/yyyy") : 'the selected date'}.</CardDescription>
                </CardHeader>
                <CardContent>
                  {dailyActivityData.length === 0 ? (
                    <p className="text-muted-foreground text-center py-4">No activity data for this date or users not loaded.</p>
                  ) : (
                  <ScrollArea className="h-[calc(100vh-26rem)]">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>User</TableHead>
                          <TableHead>Role</TableHead>
                          <TableHead>Clock-in Time</TableHead>
                          <TableHead>Method</TableHead>
                          <TableHead>Clock-in Selfie</TableHead>
                          <TableHead className="text-right">Total Break Time</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {dailyActivityData.map(userActivity => (
                          <TableRow key={userActivity.userId}>
                            <TableCell className="font-medium">{userActivity.username}</TableCell>
                            <TableCell className="capitalize">{userActivity.role}</TableCell>
                            <TableCell>
                              {userActivity.attendance && userActivity.attendance.timestamp && isValid(parseISO(userActivity.attendance.timestamp)) ? format(parseISO(userActivity.attendance.timestamp), 'p') : <span className="text-muted-foreground">Not clocked in</span>}
                            </TableCell>
                            <TableCell className="capitalize">
                              {userActivity.attendance?.method || '-'}
                            </TableCell>
                            <TableCell>
                              {userActivity.attendance?.method === 'selfie' ? (
                                <SelfieImageDisplay 
                                  src={userActivity.attendance.selfieImagePath || userActivity.attendance.selfieDataUri}
                                  alt={`Selfie for ${userActivity.username}`}
                                  width={40}
                                  height={40}
                                  className="rounded-sm object-cover aspect-square"
                                />
                              ) : (
                                '-'
                              )}
                            </TableCell>
                            <TableCell className="text-right">{userActivity.totalBreakDuration}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </ScrollArea>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
            
            <TabsContent value="sales_activity" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center"><ShoppingCart className="mr-2 h-5 w-5 text-muted-foreground"/>Salesperson Productivity</CardTitle>
                   <CardDescription>Orders created and total sales value by salespersons on {selectedDate ? format(selectedDate, "MM/dd/yyyy") : 'the selected date'}.</CardDescription>
                </CardHeader>
                <CardContent>
                   {dailyActivityData.filter(u => u.role === 'salesperson' && u.ordersCreated && u.ordersCreated > 0).length === 0 ? (
                     <p className="text-muted-foreground text-center py-4">No sales activity recorded for this date.</p>
                   ) : (
                  <ScrollArea className="h-[calc(100vh-26rem)]">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Salesperson</TableHead>
                          <TableHead className="text-center">Orders Created</TableHead>
                          <TableHead className="text-right">Total Sales Value</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {dailyActivityData.filter(u => u.role === 'salesperson' && u.ordersCreated && u.ordersCreated > 0).map(userActivity => (
                          <TableRow key={userActivity.userId}>
                            <TableCell className="font-medium">{userActivity.username}</TableCell>
                            <TableCell className="text-center">{userActivity.ordersCreated}</TableCell>
                            <TableCell className="text-right">OMR {userActivity.totalSalesValue?.toFixed(2)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </ScrollArea>
                   )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="order_status_changes" className="mt-4">
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center"><Briefcase className="mr-2 h-5 w-5 text-muted-foreground"/>Order Status Changes</CardTitle>
                        <CardDescription>Orders that had their status changed on {selectedDate ? format(selectedDate, "MM/dd/yyyy") : 'the selected date'}.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        {orders.filter(order => order && isValid(parseISO(order.updatedAt)) && isSameDay(parseISO(order.updatedAt), selectedDate || new Date())).length === 0 ? (
                             <p className="text-muted-foreground text-center py-4">No orders had their status changed on this date.</p>
                        ) : (
                        <ScrollArea className="h-[calc(100vh-26rem)]">
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Order ID</TableHead>
                                        <TableHead>New Status</TableHead>
                                        <TableHead>New Delivery Status</TableHead>
                                        <TableHead>Updated By</TableHead>
                                        <TableHead className="text-right">Updated At</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {orders.filter(order => order && isValid(parseISO(order.updatedAt)) && isSameDay(parseISO(order.updatedAt), selectedDate || new Date()))
                                        .sort((a,b) => parseISO(b.updatedAt).getTime() - parseISO(a.updatedAt).getTime())
                                        .map(order => (
                                        <TableRow key={order.id}>
                                            <TableCell className="font-medium">{order.id}</TableCell>
                                            <TableCell className="capitalize">{order.status.replace(/_/g, ' ')}</TableCell>
                                            <TableCell className="capitalize">{order.deliveryStatus ? order.deliveryStatus.replace(/_/g, ' ') : '-'}</TableCell>
                                            <TableCell className="text-muted-foreground">
                                              System/User
                                            </TableCell>
                                            <TableCell className="text-right">{isValid(parseISO(order.updatedAt)) ? format(parseISO(order.updatedAt), 'p') : 'Invalid Date'}</TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </ScrollArea>
                        )}
                    </CardContent>
                </Card>
            </TabsContent>

          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
