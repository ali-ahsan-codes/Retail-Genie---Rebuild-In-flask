// src/components/layout/AppInitializer.tsx
"use client";

import { useEffect } from 'react';
// Removed direct import of registerServiceWorker as it will be handled based on NODE_ENV

export default function AppInitializer() {
  useEffect(() => {
    if (typeof window !== 'undefined' && 'serviceWorker' in navigator) {
      if (process.env.NODE_ENV === 'development') {
        // Unregister all service workers in development
        navigator.serviceWorker.getRegistrations().then(registrations => {
          for (let registration of registrations) {
            registration.unregister()
              .then(unregistered => {
                if (unregistered) {
                  console.log('[AppInitializer - Dev] Service Worker unregistered successfully.');
                } else {
                  console.log('[AppInitializer - Dev] Service Worker unregistration failed or no SW was registered.');
                }
              })
              .catch(error => {
                console.error('[AppInitializer - Dev] Error during service worker unregistration:', error);
              });
          }
          if (registrations.length === 0) {
            console.log('[AppInitializer - Dev] No active service workers found to unregister.');
          }
        }).catch(error => {
          console.error('[AppInitializer - Dev] Error getting service worker registrations:', error);
        });
      } else {
        // In production, register and update the service worker
        window.addEventListener('load', () => {
          navigator.serviceWorker.register('/sw.js')
            .then(registration => {
              console.log('[AppInitializer - Prod] ServiceWorker registration successful, scope is:', registration.scope);
              // Attempt to update the service worker if one is active
              // This is good practice to ensure the latest SW is installed.
              registration.update().catch(err => {
                console.error('[AppInitializer - Prod] ServiceWorker update check failed:', err);
              });
            })
            .catch(err => {
              console.error('[AppInitializer - Prod] ServiceWorker registration failed:', err);
            });
        });
      }
    } else if (typeof window !== 'undefined') {
      console.log('[AppInitializer] Service Worker not supported in this browser.');
    }
  }, []);

  return null; // This component doesn't render anything visible
}
