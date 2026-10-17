
'use client';
import BreakDashboard from '@/components/admin/BreakDashboard';
import { useApp } from '@/context/AppContext';
import { ShieldAlert } from 'lucide-react';

export default function AdminBreaksDashboardPage() {
  const { hasPermission } = useApp();

  // Example: Only allow users with 'view_activity_logs' or 'manage_users' to see this.
  // Adjust permission as needed.
  const canViewPage = hasPermission('view_activity_logs') || hasPermission('manage_users');

  if (!canViewPage) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to view the breaks dashboard.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <BreakDashboard />
    </div>
  );
}

