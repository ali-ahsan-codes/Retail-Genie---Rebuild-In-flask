
'use client'; // This component contains the client-side logic that was in the layout.

import type { ReactNode } from 'react';
import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import TowerLoader from '@/components/layout/TowerLoader';

export default function MainLayoutClientWrapper({ children }: { children: ReactNode }) {
  const { currentUser, isDataLoaded } = useApp();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isDataLoaded) {
      return;
    }
    if (!currentUser) {
      router.replace('/login');
    }
  }, [currentUser, router, pathname, isDataLoaded]);

  if (!isDataLoaded) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center">
          <TowerLoader />
          <p className="text-lg text-foreground mt-4">Loading Application...</p>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center">
          <TowerLoader />
          <p className="text-lg text-foreground mt-4">Authenticating...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
