
'use client';
import { useMemo } from 'react';
import { useApp } from '@/context/AppContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  LayoutDashboard,
  DollarSign,
  ShoppingCart,
  Package,
  Users as UsersIcon,
  ShieldAlert,
  Activity,
  BarChart3,
  PieChart as PieChartIcon, // Renamed to avoid conflict with Recharts' PieChart
} from 'lucide-react';
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { cn } from '@/lib/utils';
import type { OrderStatus, UserRole } from '@/types';

const ORDER_STATUS_DISPLAY_ORDER: OrderStatus[] = [
  'pending_payment',
  'preparing',
  'ready_for_pickup',
  'paid',
  'completed',
  'cancelled',
  'returned',
];

const USER_ROLE_COLORS: Record<UserRole, string> = {
  admin: 'hsl(var(--chart-1))',
  manager: 'hsl(var(--chart-2))',
  salesperson: 'hsl(var(--chart-3))',
  storekeeper: 'hsl(var(--chart-4))',
  cashier: 'hsl(var(--chart-5))',
  logistics: 'hsl(var(--destructive))', // Using destructive for logistics for variety
};


export default function AdminDashboard() {
  const { orders, products, users, currentUser, hasPermission, isDataLoaded } = useApp();

  const dashboardData = useMemo(() => {
    if (!isDataLoaded) return null;

    const totalRevenue = orders
      .filter(order => order.status === 'paid' || order.status === 'completed')
      .reduce((sum, order) => sum + order.totalAmount, 0);

    const totalOrders = orders.length;
    const totalProducts = products.length;
    const totalUsers = users.length;

    const orderStatusCounts = ORDER_STATUS_DISPLAY_ORDER.reduce((acc, status) => {
        acc[status] = 0;
        return acc;
    }, {} as Record<OrderStatus, number>);

    orders.forEach(order => {
      if (orderStatusCounts.hasOwnProperty(order.status)) {
        orderStatusCounts[order.status]++;
      }
    });

    const orderStatusChartData = ORDER_STATUS_DISPLAY_ORDER.map(status => ({
      name: status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      count: orderStatusCounts[status],
    }));

    const userRoleCounts = users.reduce((acc, user) => {
      acc[user.role] = (acc[user.role] || 0) + 1;
      return acc;
    }, {} as Record<UserRole, number>);

    const userRoleChartData = Object.entries(userRoleCounts).map(([role, count]) => ({
      name: role.charAt(0).toUpperCase() + role.slice(1),
      value: count,
      fill: USER_ROLE_COLORS[role as UserRole] || 'hsl(var(--muted))',
    }));
    
    const recentActivity = orders.slice(0, 5).map(order => ({ // Simplified recent activity
        id: order.id,
        description: `Order ${order.id} status updated to ${order.status.replace(/_/g, ' ')}.`,
        time: new Date(order.updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        type: order.status,
    }));


    return {
      totalRevenue,
      totalOrders,
      totalProducts,
      totalUsers,
      orderStatusChartData,
      userRoleChartData,
      recentActivity,
    };
  }, [orders, products, users, isDataLoaded]);

  if (!isDataLoaded) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
        <p className="ml-4 text-muted-foreground">Loading dashboard data...</p>
      </div>
    );
  }
  
  const canViewPage = currentUser && (currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('view_admin_dashboard')));

  if (!canViewPage) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">
          {currentUser?.role === 'manager' 
            ? "You do not have the 'view_admin_dashboard' permission." 
            : "You do not have permission to view this page."}
        </p>
      </div>
    );
  }

  if (!dashboardData) {
    return <div className="p-6">Error loading dashboard data. Please try again later.</div>;
  }

  return (
    <ScrollArea className="h-full p-1">
      <div className="space-y-6 p-2 md:p-4 lg:p-6">
        <CardHeader className="p-0 mb-4">
          <CardTitle className="text-3xl font-bold flex items-center">
            <LayoutDashboard className="mr-3 h-8 w-8 text-primary" />
            Admin Overview
          </CardTitle>
          <CardDescription>
            Welcome, {currentUser?.username}! Here's a snapshot of your retail operations.
          </CardDescription>
        </CardHeader>

        {/* Key Metrics */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <StatCard title="Total Revenue" value={`OMR ${dashboardData.totalRevenue.toFixed(2)}`} />
          <StatCard title="Total Orders" value={dashboardData.totalOrders.toString()} icon={ShoppingCart} />
          <StatCard title="Total Products" value={dashboardData.totalProducts.toString()} icon={Package} />
          <StatCard title="Total Users" value={dashboardData.totalUsers.toString()} icon={UsersIcon} />
        </div>

        {/* Charts Section */}
        <div className="grid gap-6 md:grid-cols-2">
          <Card className="shadow-lg">
            <CardHeader>
              <CardTitle className="text-xl flex items-center"><BarChart3 className="mr-2 h-5 w-5 text-primary" /> Order Status Distribution</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={dashboardData.orderStatusChartData} margin={{ top: 5, right: 0, left: -20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="name" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} angle={-30} textAnchor="end" height={60} interval={0}/>
                  <YAxis tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 12 }} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))' }} />
                  <Legend wrapperStyle={{ fontSize: '12px' }}/>
                  <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} name="Order Count" />
                </ComposedChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card className="shadow-lg">
            <CardHeader>
              <CardTitle className="text-xl flex items-center"><PieChartIcon className="mr-2 h-5 w-5 text-primary" /> User Role Distribution</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={dashboardData.userRoleChartData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name} (${(percent * 100).toFixed(0)}%)`}
                    outerRadius={100}
                    dataKey="value"
                    nameKey="name"
                    stroke="hsl(var(--border))"
                  >
                    {dashboardData.userRoleChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))' }}/>
                  <Legend wrapperStyle={{ fontSize: '12px' }}/>
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
        
        {/* Recent Activity - Placeholder */}
        <Card className="shadow-lg">
          <CardHeader>
            <CardTitle className="text-xl flex items-center"><Activity className="mr-2 h-5 w-5 text-primary"/> Recent Activity</CardTitle>
             <CardDescription>Latest updates and changes in the system.</CardDescription>
          </CardHeader>
          <CardContent>
            {dashboardData.recentActivity.length > 0 ? (
                <ul className="space-y-3">
                {dashboardData.recentActivity.map((activity) => (
                    <li key={activity.id} className="flex items-center justify-between p-3 bg-muted/30 rounded-md">
                    <span className="text-sm text-muted-foreground">{activity.description}</span>
                    <span className="text-xs text-foreground bg-background px-2 py-1 rounded-full border">{activity.time}</span>
                    </li>
                ))}
                </ul>
            ) : (
                <p className="text-muted-foreground text-center py-4">No recent activity to display.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </ScrollArea>
  );
}

interface StatCardProps {
  title: string;
  value: string;
  icon?: React.ElementType;
  className?: string;
}

const StatCard: React.FC<StatCardProps> = ({ title, value, icon: Icon, className }) => (
  <Card className={cn("shadow-lg hover:shadow-xl transition-shadow", className)}>
    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
      <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      {Icon && <Icon className="h-5 w-5 text-primary" />}
    </CardHeader>
    <CardContent>
      <div className="text-3xl font-bold text-foreground">{value}</div>
    </CardContent>
  </Card>
);


    
