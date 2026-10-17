'use client';

import { Sidebar } from '@/components/ui/sidebar';
import AppSidebarContent from './AppSidebarContent';

export default function AppSidebar() {
  return (
    <Sidebar collapsible="icon" variant="sidebar" side="left" className="border-r">
      <AppSidebarContent />
    </Sidebar>
  );
}
