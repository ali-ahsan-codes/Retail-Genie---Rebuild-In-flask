
"use client"; // This hook uses browser APIs and useEffect, so it's a client component

import { useState, useEffect, useCallback } from 'react';

export function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(typeof navigator !== 'undefined' ? navigator.onLine : true);
  // For 'isSlow', we'll keep it simple. A more robust solution would involve actual speed tests.
  // This version simply flags if a fetch takes too long or if connection type suggests slowness.
  const [isSlow, setIsSlow] = useState(false);
  const [lastSuccessfulRequestTime, setLastSuccessfulRequestTime] = useState(Date.now());
  const [requestInProgress, setRequestInProgress] = useState(false);

  const updateOnlineStatus = useCallback(() => {
    setIsOnline(typeof navigator !== 'undefined' ? navigator.onLine : true);
  }, []);

  // More sophisticated slow network detection would require observing actual request times
  // or using navigator.connection API if widely supported and reliable for this use case.
  // For this implementation, 'isSlow' is a placeholder and would need enhancement.
  // For example, you could expose a function from this hook that components can call
  // before/after making important fetch requests to help gauge network responsiveness.
  // For now, it's a simplified version.
  const checkSlowNetwork = useCallback(() => {
    if (typeof navigator !== 'undefined' && 'connection' in navigator) {
      const connection = (navigator as any).connection;
      if (connection && (connection.saveData || connection.effectiveType === 'slow-2g' || connection.effectiveType === '2g')) {
        setIsSlow(true);
        return;
      }
    }
    // If a request has been in progress for a while, consider it slow
    if (requestInProgress && (Date.now() - lastSuccessfulRequestTime > 5000)) { // 5 seconds threshold
        setIsSlow(true);
    } else {
        setIsSlow(false);
    }
  }, [requestInProgress, lastSuccessfulRequestTime]);


  useEffect(() => {
    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);
    
    // Periodically check for slow network if a request seems to be taking time
    const intervalId = setInterval(checkSlowNetwork, 3000); // Check every 3 seconds

    return () => {
      window.removeEventListener('online', updateOnlineStatus);
      window.removeEventListener('offline', updateOnlineStatus);
      clearInterval(intervalId);
    };
  }, [updateOnlineStatus, checkSlowNetwork]);

  // Functions to be called by API client or other parts of the app
  const onRequestStart = useCallback(() => {
    setRequestInProgress(true);
    // Reset lastSuccessfulRequestTime to now to start a new timing window
    // Or, keep the old one to see if the *current* request makes it slow relative to last success
  }, []);

  const onRequestEnd = useCallback((success: boolean) => {
    setRequestInProgress(false);
    if (success) {
      setLastSuccessfulRequestTime(Date.now());
      setIsSlow(false); // If a request just succeeded, network might not be "slow" in that instant
    } else {
      // If request failed, it might be due to slow network or offline.
      // isOnline state will handle offline. isSlow might be set by timeout logic.
      checkSlowNetwork(); // Re-evaluate slow status
    }
  }, [checkSlowNetwork]);

  return { isOnline, isSlow, onRequestStart, onRequestEnd };
}
