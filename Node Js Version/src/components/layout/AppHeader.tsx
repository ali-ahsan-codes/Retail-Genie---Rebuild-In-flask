
'use client';

import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { useApp } from '@/context/AppContext';
import { brandingConfig } from '@/config/branding'; // Import branding config
import { LogOut, UserCircle, Menu } from 'lucide-react';
import Image from 'next/image'; 
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger
} from "@/components/ui/sheet";
import AppSidebarContent from './AppSidebarContent';
import { useSidebar } from '../ui/sidebar';
import ClientOnly from './ClientOnly'; 
import { cn } from '@/lib/utils';

export default function AppHeader() {
  const router = useRouter();
  const { currentUser, setCurrentUser } = useApp();
  const { toggleSidebar, isMobile } = useSidebar();


  const handleLogout = () => {
    setCurrentUser(null);
    router.push('/login');
  };

  return (
    <header className={cn(
      "sticky top-0 z-30 flex h-16 items-center justify-between border-b px-4 sm:px-6",
      "border-white/20 bg-card/40 shadow-lg backdrop-blur-md" // Added glassmorphism classes
    )}>
      <div className="flex items-center gap-4">
         <ClientOnly> 
          {isMobile ? (
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="md:hidden">
                  <Menu className="h-6 w-6" />
                  <span className="sr-only">Toggle Menu</span>
                </Button>
              </SheetTrigger>
              <SheetContent side="left" className="w-[280px] p-0">
                <SheetTitle className="sr-only">{brandingConfig.appName} Navigation Menu</SheetTitle> 
                <AppSidebarContent />
              </SheetContent>
            </Sheet>
          ) : (
            <Button variant="ghost" size="icon" onClick={toggleSidebar} className="hidden md:flex">
              <Menu className="h-6 w-6" />
              <span className="sr-only">Toggle Menu</span>
            </Button>
          )}
        </ClientOnly>
        <div className="flex items-center gap-2">
          <Image src={brandingConfig.logoPath} alt={`${brandingConfig.appName} Logo`} width={32} height={32} data-ai-hint="logo company"/>
          <h1 className="text-xl font-semibold text-primary">{brandingConfig.appName}</h1>
        </div>
      </div>
      <div className="flex items-center gap-4">
        {currentUser && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <UserCircle className="h-5 w-5 text-primary" />
            <span>
              {currentUser.username} ({currentUser.role.charAt(0).toUpperCase() + currentUser.role.slice(1)})
            </span>
          </div>
        )}
        <Button variant="outline" size="sm" onClick={handleLogout}>
          <LogOut className="mr-2 h-4 w-4" />
          Logout
        </Button>
      </div>
    </header>
  );
}
