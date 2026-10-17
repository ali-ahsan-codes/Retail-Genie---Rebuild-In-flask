// src/components/layout/AppSidebarContent.tsx
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Image from 'next/image';
import {
  LayoutDashboard,
  ShoppingCart,
  PackageCheck,
  Receipt,
  Users,
  Archive,
  Boxes,
  UserCog,
  FileText,
  UserCircle,
  BarChart3,
  Truck,
  BellRing,
  SlidersHorizontal,
  Percent,
  Undo2,
  Activity,
  UsersRound,
  Target,
  Store as StoreIcon,
  PackageSearch as StorekeeperIcon,
  Tags, 
  Coffee, 
  Cloud,
  FileSignature,
  ClipboardCheck, // Icon for Audits
  Mail, // Icon for Messaging
  Ship, // Icon for SCM
  Zap // Icon for Express
} from 'lucide-react';
import { useApp } from '@/context/AppContext';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import { brandingConfig } from '@/config/branding';
import type { Permission, UserRole } from '@/types'; 
import {
  SidebarHeader,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarFooter,
  SidebarMenuBadge,
} from '@/components/ui/sidebar';


interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  roles: UserRole[]; 
  requiredPermission?: Permission;
  group?: 'main' | 'management' | 'reports' | 'settings' | 'personal_tools' | 'auditing' | 'operational_dashboards'; 
  badgeId?: 'messaging';
}

const navItems: NavItem[] = [
  // Main Dashboards for Specific Roles
  { href: '/salesperson/dashboard', label: 'Sales Dashboard', icon: ShoppingCart, roles: ['salesperson'], group: 'main' },
  { href: '/storekeeper/dashboard', label: 'Store Dashboard', icon: PackageCheck, roles: ['storekeeper'], group: 'main' },
  { href: '/cashier/dashboard', label: 'Cashier Dashboard', icon: Receipt, roles: ['cashier'], group: 'main' },
  { href: '/logistics/dashboard', label: 'Logistics Dashboard', icon: Truck, roles: ['logistics'], group: 'main' },
  { href: '/auditor/audits', label: 'My Audits', icon: ClipboardCheck, roles: ['auditor'], group: 'main' },
  { href: '/express', label: 'Express Checkout', icon: Zap, roles: ['express'], group: 'main' },
  
  // Salesperson Specific Tools
  { href: '/salesperson/reports', label: 'Sales Report', icon: BarChart3, roles: ['salesperson'], group: 'main' },
  { href: '/salesperson/demand-notices', label: 'Demand Notices', icon: BellRing, roles: ['salesperson'], group: 'main' },
  { href: '/salesperson/stores', label: 'External Stores', icon: StoreIcon, roles: ['salesperson'], group: 'main' },
  { href: '/salesperson/quotations', label: 'My Quotations', icon: FileSignature, roles: ['salesperson'], group: 'main' }, 

  // Storekeeper Specific Tools
  { href: '/storekeeper/demand-notices', label: 'Demand Notices', icon: StorekeeperIcon, roles: ['storekeeper'], group: 'main' },
  { href: '/storekeeper/stock-receiving', label: 'Stock Receiving', icon: Ship, roles: ['storekeeper'], group: 'main' },
  
  // Logistics Specific Tools
  { href: '/logistics/po-tracking', label: 'PO Tracking', icon: Ship, roles: ['logistics'], group: 'main' },


  // General User Profile
  { href: '/profile', label: 'Profile Management', icon: UserCircle, roles: ['salesperson', 'storekeeper', 'cashier', 'admin', 'logistics', 'manager', 'auditor', 'express'], group: 'personal_tools' },
  { href: '/my-cloud', label: 'My Cloud Files', icon: Cloud, roles: ['salesperson', 'storekeeper', 'cashier', 'admin', 'logistics', 'manager', 'auditor', 'express'], group: 'personal_tools' },
  { href: '/messaging', label: 'Messaging', icon: Mail, roles: ['salesperson', 'storekeeper', 'cashier', 'admin', 'logistics', 'manager', 'auditor', 'express'], group: 'personal_tools', badgeId: 'messaging' },


  // Admin & Manager Section: Main
  { href: '/admin/dashboard', label: 'Overview', icon: LayoutDashboard, roles: ['admin', 'manager'], requiredPermission: 'view_admin_dashboard', group: 'main' },

  // Admin & Manager Section: Management
  { href: '/admin/products', label: 'Products & Stores', icon: Boxes, roles: ['admin', 'manager'], requiredPermission: 'manage_products', group: 'management' },
  { href: '/admin/scm', label: 'SCM Dashboard', icon: Ship, roles: ['admin', 'manager'], requiredPermission: 'manage_products', group: 'management' },
  { href: '/admin/orders', label: 'All Orders', icon: Archive, roles: ['admin', 'manager'], requiredPermission: 'manage_orders', group: 'management' },
  { href: '/admin/users', label: 'Users', icon: UserCog, roles: ['admin', 'manager'], requiredPermission: 'manage_users', group: 'management' },
  { href: '/admin/demand-notices', label: 'All Demand Notices', icon: BellRing, roles: ['admin', 'manager'], requiredPermission: 'manage_demand_notices', group: 'management' },
  { href: '/admin/quotations', label: 'All Quotations', icon: FileSignature, roles: ['admin', 'manager'], requiredPermission: 'manage_orders', group: 'management' }, 
  { href: '/admin/label-printing', label: 'Label Printing', icon: Tags, roles: ['admin', 'manager'], requiredPermission: 'manage_labels', group: 'management' },
  { href: '/admin/file-management', label: 'System File Mgmt', icon: Cloud, roles: ['admin', 'manager'], requiredPermission: 'manage_cloud_files', group: 'management'}, 

  // Admin & Manager Section: Auditing
  { href: '/admin/audits', label: 'Manage Audits', icon: ClipboardCheck, roles: ['admin', 'manager'], requiredPermission: 'manage_audits', group: 'auditing' },

  // Manager Operational Dashboards (New Group)
  { href: '/salesperson/dashboard', label: 'Sales Ops', icon: ShoppingCart, roles: ['manager'], group: 'operational_dashboards'},
  { href: '/salesperson/quotations', label: 'Quotations Ops', icon: FileSignature, roles: ['manager'], group: 'operational_dashboards'},
  { href: '/salesperson/demand-notices', label: 'Demand Notices Ops', icon: BellRing, roles: ['manager'], group: 'operational_dashboards'},
  { href: '/cashier/dashboard', label: 'Cashier Ops', icon: Receipt, roles: ['manager'], group: 'operational_dashboards'},
  { href: '/storekeeper/dashboard', label: 'Store Ops', icon: PackageCheck, roles: ['manager'], group: 'operational_dashboards'},
  { href: '/logistics/dashboard', label: 'Logistics Ops', icon: Truck, roles: ['manager'], group: 'operational_dashboards'},
  { href: '/logistics/po-tracking', label: 'PO Tracking Ops', icon: Ship, roles: ['manager'], group: 'operational_dashboards'},


  // Admin & Manager Section: Reports
  { href: '/admin/accounts', label: 'Sales Export', icon: FileText, roles: ['admin', 'manager'], requiredPermission: 'view_reports', group: 'reports' },
  { href: '/admin/activity-logs', label: 'Activity Logs', icon: Activity, roles: ['admin', 'manager'], requiredPermission: 'view_activity_logs', group: 'reports' },
  { href: '/admin/salesperson-reports', label: 'Salesperson Reports', icon: UsersRound, roles: ['admin', 'manager'], requiredPermission: 'view_salesperson_reports', group: 'reports' },
  { href: '/admin/breaks-dashboard', label: 'Active Breaks', icon: Coffee, roles: ['admin', 'manager'], requiredPermission: 'view_activity_logs', group: 'reports' },

  // Admin & Manager Section: Settings
  { href: '/admin/settings', label: 'System Settings', icon: SlidersHorizontal, roles: ['admin', 'manager'], requiredPermission: 'manage_settings', group: 'settings' }, 
  { href: '/admin/global-discount', label: 'Global Discount', icon: Percent, roles: ['admin', 'manager'], requiredPermission: 'manage_settings', group: 'settings' },
  { href: '/admin/commission-settings', label: 'Commission Settings', icon: Target, roles: ['admin', 'manager'], requiredPermission: 'manage_settings', group: 'settings'},
];

export default function AppSidebarContent() {
  const { currentUser, totalUnreadCount } = useApp();
  const pathname = usePathname();

  if (!currentUser) return null;

  const hasPermissionCheck = (permission?: Permission): boolean => {
    if (!permission) return true;
    if (currentUser.role === 'admin') return true;
    if (currentUser.role === 'manager') {
      return currentUser.permissions?.includes(permission) ?? false;
    }
    // Auditor specific permissions
    if (currentUser.role === 'auditor' && permission === 'conduct_audits') {
        return true;
    }
    // Allow logistics to view reports (which includes POs now)
    if (currentUser.role === 'logistics' && permission === 'view_reports') {
        return true;
    }
    return false;
  };

  const getFilteredNavItems = (groupName: NavItem['group']) => {
    return navItems
      .filter(item => item.group === groupName)
      .filter(item => item.roles.includes(currentUser.role))
      .filter(item => hasPermissionCheck(item.requiredPermission))
      .sort((a, b) => a.label.localeCompare(b.label));
  };

  const mainNavItems = getFilteredNavItems('main');
  const personalToolsNavItems = getFilteredNavItems('personal_tools'); 
  const operationalDashboardsNavItems = getFilteredNavItems('operational_dashboards'); // New for manager
  const managementNavItems = getFilteredNavItems('management');
  const auditingNavItems = getFilteredNavItems('auditing');
  const reportsNavItems = getFilteredNavItems('reports');
  const settingsNavItems = getFilteredNavItems('settings');

  const getBadgeContent = (badgeId?: 'messaging') => {
    if (badgeId === 'messaging' && totalUnreadCount > 0) {
      return totalUnreadCount;
    }
    return null;
  };


  const renderNavItem = (item: NavItem, index: number) => {
    const isActive = pathname === item.href || (pathname.startsWith(item.href) && item.href !== '/' && item.href !== `/${currentUser.role}/dashboard` && pathname.split('/').length > item.href.split('/').length);
    const badgeContent = getBadgeContent(item.badgeId);

    return (
      <SidebarMenuItem key={`${item.href}-${index}`}>
        <SidebarMenuButton
          asChild
          isActive={isActive}
          className={cn(
            "justify-start w-full",
            isActive ? "bg-sidebar-primary/10 text-sidebar-primary" : "hover:bg-sidebar-accent/80 hover:text-sidebar-accent-foreground"
          )}
          tooltip={item.label}
        >
          <Link href={item.href}>
            <item.icon className={cn("h-5 w-5", isActive ? "text-sidebar-primary" : "")} />
            <span className="truncate">{item.label}</span>
          </Link>
        </SidebarMenuButton>
        {badgeContent !== null && (
          <SidebarMenuBadge>{badgeContent}</SidebarMenuBadge>
        )}
      </SidebarMenuItem>
    );
  };

  return (
    <>
      <SidebarHeader className="border-b">
        <Link href="/" className="flex items-center gap-2 font-semibold text-primary text-lg p-2">
          <Image src={brandingConfig.logoPath} alt={`${brandingConfig.appName} Logo`} width={28} height={28} data-ai-hint="logo company" />
          <span>{brandingConfig.appName}</span>
        </Link>
      </SidebarHeader>
      <SidebarContent className="flex-1 p-2">
        <ScrollArea className="h-full">
          {mainNavItems.length > 0 && (
            <SidebarMenu>
              {mainNavItems.map((item, index) => renderNavItem(item, index))}
            </SidebarMenu>
          )}

          {currentUser.role === 'manager' && operationalDashboardsNavItems.length > 0 && (
            <SidebarGroup className="mt-4 pt-0">
              <SidebarGroupLabel className="text-xs font-semibold text-muted-foreground px-2 py-1">
                Operational Dashboards
              </SidebarGroupLabel>
              <SidebarMenu>
                {operationalDashboardsNavItems.map((item, index) => renderNavItem(item, index))}
              </SidebarMenu>
            </SidebarGroup>
          )}
          
          {personalToolsNavItems.length > 0 && (
            <SidebarGroup className="mt-4 pt-0">
              <SidebarGroupLabel className="text-xs font-semibold text-muted-foreground px-2 py-1">
                My Tools
              </SidebarGroupLabel>
              <SidebarMenu>
                {personalToolsNavItems.map((item, index) => renderNavItem(item, index))}
              </SidebarMenu>
            </SidebarGroup>
          )}

          {(currentUser.role === 'admin' || currentUser.role === 'manager') && managementNavItems.length > 0 && (
            <SidebarGroup className="mt-4 pt-0">
              <SidebarGroupLabel className="text-xs font-semibold text-muted-foreground px-2 py-1">
                Management
              </SidebarGroupLabel>
              <SidebarMenu>
                {managementNavItems.map((item, index) => renderNavItem(item, index))}
              </SidebarMenu>
            </SidebarGroup>
          )}
          {(currentUser.role === 'admin' || currentUser.role === 'manager') && auditingNavItems.length > 0 && (
            <SidebarGroup className="mt-4 pt-0">
              <SidebarGroupLabel className="text-xs font-semibold text-muted-foreground px-2 py-1">
                Auditing
              </SidebarGroupLabel>
              <SidebarMenu>
                {auditingNavItems.map((item, index) => renderNavItem(item, index))}
              </SidebarMenu>
            </SidebarGroup>
          )}
           {(currentUser.role === 'admin' || currentUser.role === 'manager') && reportsNavItems.length > 0 && (
            <SidebarGroup className="mt-4 pt-0">
              <SidebarGroupLabel className="text-xs font-semibold text-muted-foreground px-2 py-1">
                Reports
              </SidebarGroupLabel>
              <SidebarMenu>
                {reportsNavItems.map((item, index) => renderNavItem(item, index))}
              </SidebarMenu>
            </SidebarGroup>
          )}

          {(currentUser.role === 'admin' || currentUser.role === 'manager') && settingsNavItems.length > 0 && (
            <SidebarGroup className="mt-4 pt-0">
              <SidebarGroupLabel className="text-xs font-semibold text-muted-foreground px-2 py-1">
                Settings
              </SidebarGroupLabel>
              <SidebarMenu>
                {settingsNavItems.map((item, index) => renderNavItem(item, index))}
              </SidebarMenu>
            </SidebarGroup>
          )}
        </ScrollArea>
      </SidebarContent>
      <SidebarFooter className="border-t p-2">
      </SidebarFooter>
    </>
  );
}
