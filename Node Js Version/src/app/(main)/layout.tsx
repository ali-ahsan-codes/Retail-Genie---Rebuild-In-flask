// This component is now a Server Component by default, which is correct for a layout.
// 'use client' has been removed.

import type { ReactNode } from 'react';
import AppHeader from '@/components/layout/AppHeader';
import AppSidebar from '@/components/layout/AppSidebar';
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import MainLayoutClientWrapper from './MainLayoutClientWrapper'; // Import the new client wrapper

export default function MainAppLayout({ children }: { children: ReactNode }) {
  
  // This layout now wraps the children with a client component that handles
  // the dynamic logic (like checking auth status and showing loaders).
  // The structural parts (Sidebar, Header) remain here.
  return (
    <SidebarProvider defaultOpen={true}>
      <AppSidebar />
      <div className="flex flex-col flex-1 min-h-screen">
        <AppHeader />
        <SidebarInset>
          <main className="flex-1 p-4 sm:p-6 bg-background overflow-auto">
            <MainLayoutClientWrapper>
              {children}
            </MainLayoutClientWrapper>
          </main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}
