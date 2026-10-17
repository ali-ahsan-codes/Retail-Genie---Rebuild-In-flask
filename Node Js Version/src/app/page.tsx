// This page will redirect to the login page or dashboard if already logged in.
"use client";
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext'; 
import ClientOnly from '@/components/layout/ClientOnly';
import TowerLoader from '@/components/layout/TowerLoader'; // Import the new loader

export default function HomePage() {
  const router = useRouter();
  const { currentUser, isDataLoaded } = useApp(); 

  useEffect(() => {
    if (!isDataLoaded) { 
      return; // Wait for data to be loaded
    }
    if (currentUser && currentUser.role) {
      if (currentUser.role === 'admin' || currentUser.role === 'manager') {
        router.replace('/admin/dashboard');
      } else if (currentUser.role === 'auditor') {
        router.replace('/auditor/audits'); // Corrected redirection for auditor
      } else {
        router.replace(`/${currentUser.role}/dashboard`);
      }
    } else {
      router.replace('/login');
    }
  }, [currentUser, router, isDataLoaded]); 

  return (
    <ClientOnly>
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center">
          <TowerLoader /> {/* Use the new TowerLoader component */}
          <p className="text-lg text-foreground mt-4"> {/* Added margin-top for spacing */}
            {isDataLoaded ? "Redirecting..." : "Loading Retail Genie..."}
          </p>
        </div>
      </div>
    </ClientOnly>
  );
}
