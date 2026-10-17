// src/components/network/NetworkStatusBar.tsx
'use client';

import { useNetworkStatus } from '@/hooks/useNetworkStatus';
import { useEffect, useState } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { WifiOff, Wifi, AlertTriangle, ShieldAlert } from 'lucide-react';
import { cn } from '@/lib/utils';

export function NetworkStatusBar() {
  const { isOnline, isSlow } = useNetworkStatus();
  const [showOfflineBanner, setShowOfflineBanner] = useState(false);
  const [showSlowBanner, setShowSlowBanner] = useState(false);
  const [showOnlineBanner, setShowOnlineBanner] = useState(false);
  const [firstLoad, setFirstLoad] = useState(true);

  useEffect(() => {
    if (firstLoad) {
      if (!isOnline) {
        setShowOfflineBanner(true);
      }
      setFirstLoad(false);
      return;
    }

    if (!isOnline) {
      setShowOfflineBanner(true);
      setShowOnlineBanner(false); // Hide online banner if we go offline
      setShowSlowBanner(false); // Offline takes precedence over slow
    } else {
      // If we were showing offline, now show online briefly
      if (showOfflineBanner) {
        setShowOnlineBanner(true);
        const timer = setTimeout(() => setShowOnlineBanner(false), 3000); // Show for 3s
        // Don't clear showOfflineBanner immediately, let online banner take over
        const offlineTimer = setTimeout(() => setShowOfflineBanner(false), 2800); // Clear just before online banner
        return () => { clearTimeout(timer); clearTimeout(offlineTimer);};
      } else {
        // If we were not offline, ensure offline banner is hidden
        setShowOfflineBanner(false);
      }
    }
  }, [isOnline, firstLoad, showOfflineBanner]);

  useEffect(() => {
    if (isOnline && isSlow) {
      setShowSlowBanner(true);
      const timer = setTimeout(() => setShowSlowBanner(false), 5000); // Show for 5s
      return () => clearTimeout(timer);
    } else if (!isOnline) {
      setShowSlowBanner(false); // Don't show slow if offline
    }
    // If online and not slow, and we were showing slow, it will clear on its own timer.
  }, [isSlow, isOnline]);


  if (showOfflineBanner && !isOnline) { // Prioritize offline message
    return (
      <Alert
        variant="destructive"
        className={cn(
          "fixed bottom-4 right-4 w-auto max-w-sm z-[200] p-4 shadow-lg animate-in fade-in-0 slide-in-from-bottom-5",
          "bg-destructive text-destructive-foreground border-destructive/80"
        )}
      >
        <WifiOff className="h-5 w-5 text-destructive-foreground" />
        <AlertTitle className="font-semibold">You are Offline</AlertTitle>
        <AlertDescription className="text-xs">
          Your internet connection is lost. Changes will be synced when you reconnect.
        </AlertDescription>
      </Alert>
    );
  }

  if (showOnlineBanner && isOnline) {
    return (
      <Alert
        className={cn(
          "fixed bottom-4 right-4 w-auto max-w-sm z-[200] p-4 shadow-lg animate-in fade-in-0 slide-in-from-bottom-5",
          "bg-accent text-accent-foreground border-accent/80"
        )}
      >
        <Wifi className="h-5 w-5 text-accent-foreground" />
        <AlertTitle className="font-semibold">Back Online!</AlertTitle>
        <AlertDescription className="text-xs">
          Your internet connection has been restored.
        </AlertDescription>
      </Alert>
    );
  }

  if (showSlowBanner && isOnline && isSlow && !showOnlineBanner) { // Only show slow if online and not showing "Back Online"
    return (
      <Alert
        className={cn(
          "fixed bottom-4 right-4 w-auto max-w-sm z-[200] p-4 shadow-lg animate-in fade-in-0 slide-in-from-bottom-5",
          "bg-yellow-100 text-yellow-700 border-yellow-400"
        )}
      >
        <AlertTriangle className="h-5 w-5 text-yellow-700" />
        <AlertTitle className="font-semibold text-yellow-800">Slow Connection</AlertTitle>
        <AlertDescription className="text-xs text-yellow-700">
          Your network connection appears to be slow. Some features might be limited.
        </AlertDescription>
      </Alert>
    );
  }

  return null;
}
