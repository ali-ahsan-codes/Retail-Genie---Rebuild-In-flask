// src/app/(main)/admin/layout.tsx
'use client';
import type { ReactNode } from 'react';
import { useApp } from '@/context/AppContext';
import { useRouter, usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { ShieldAlert, Loader2 } from 'lucide-react';

export default function AdminLayout({ children }: { children: ReactNode }) {
  const { currentUser, isDataLoaded } = useApp();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isDataLoaded) {
      return; 
    }
    if (!currentUser) {
      console.log('AdminLayout: No current user, redirecting to login.');
      router.replace('/login');
      return;
    }
    
    // Allow logistics role to access only specific SCM PO detail pages
    if (currentUser.role === 'logistics') {
      if (pathname.startsWith('/admin/scm/po/')) {
        // This is an allowed path for logistics, so we let them stay.
        return; 
      } else {
        // If a logistics user is anywhere else in /admin, redirect them home.
        console.log(`AdminLayout: Logistics user on unauthorized admin path '${pathname}'. Redirecting to logistics dashboard.`);
        router.replace('/logistics/dashboard');
        return;
      }
    }

    // For any other role, if they are not admin or manager, redirect them.
    if (currentUser.role !== 'admin' && currentUser.role !== 'manager') {
      console.log(`AdminLayout: User role '${currentUser.role}' not authorized for /admin, redirecting.`);
      if (currentUser.role === 'auditor') {
        router.replace('/auditor/audits');
      } else if (currentUser.role === 'express'){
        router.replace('/express');
      } else {
        router.replace(`/${currentUser.role}/dashboard`);
      }
      return;
    }
    // If user is admin or manager, they can proceed.
    // Individual pages within /admin/* should handle specific permission checks.
  }, [currentUser, router, isDataLoaded, pathname]);

  if (!isDataLoaded) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex flex-col items-center text-center">
          <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
          <p className="text-lg text-muted-foreground">Loading admin section...</p>
        </div>
      </div>
    );
  }

  // Allow logistics to render if they are on a PO detail page while waiting for redirect/auth logic to run
  if (currentUser?.role === 'logistics' && pathname.startsWith('/admin/scm/po/')) {
    return <>{children}</>;
  }

  // If user is not admin or manager (and not a logistics user on an allowed page), show a loading/redirecting screen.
  if (!currentUser || (currentUser.role !== 'admin' && currentUser.role !== 'manager')) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex flex-col items-center text-center">
          <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
          <h1 className="text-2xl font-bold">Redirecting</h1>
          <p className="text-muted-foreground">Authorizing...</p>
        </div>
      </div>
    );
  }
  
  // If user is admin or manager, render children.
  return <>{children}</>;
}
