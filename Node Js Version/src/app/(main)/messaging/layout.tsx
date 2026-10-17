
// src/app/(main)/messaging/layout.tsx
'use client';

import React, { useState, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import { Mail } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useRouter } from 'next/navigation';

export default function MessagingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { currentUser, totalUnreadCount } = useApp();
  const [previousUnreadCount, setPreviousUnreadCount] = useState<number | undefined>(undefined);
  const { toast } = useToast();
  const router = useRouter();

  useEffect(() => {
    // On initial load, set the count without showing a notification.
    if (previousUnreadCount === undefined) {
      setPreviousUnreadCount(totalUnreadCount);
      return;
    }
    
    // Do not show notifications for the 'display' user.
    if (currentUser?.role === 'display') {
      setPreviousUnreadCount(totalUnreadCount); // Keep count updated to prevent future notifications if role changes.
      return;
    }

    // If the new count is greater than the old one, a new message has arrived.
    if (totalUnreadCount > previousUnreadCount) {
      const newMessages = totalUnreadCount - previousUnreadCount;
      toast({
        title: "New Message Received",
        description: `You have ${newMessages} new message${newMessages > 1 ? 's' : ''}.`,
        action: (
           <button
             onClick={() => router.push('/messaging')}
             className="px-3 py-1.5 text-sm rounded-md bg-accent text-accent-foreground hover:bg-accent/90"
           >
             View
           </button>
        ),
      });
    }

    // Update the previous count for the next check.
    setPreviousUnreadCount(totalUnreadCount);
  }, [totalUnreadCount, previousUnreadCount, toast, router, currentUser]);

  return (
    <div className="h-full">
      {children}
    </div>
  );
}
