// src/app/lcd-display/layout.tsx
import type { ReactNode } from 'react';
import type { Metadata, Viewport } from 'next';

export const metadata: Metadata = {
  title: 'NetPOS - Order Display',
  description: 'Live Order Status Display',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false, // Prevent pinch zoom on touch devices
};

export default function LCDLayout({ children }: { children: ReactNode }) {
  // Apply the full-screen and background styles to this div
  return (
    <div className="h-screen w-screen bg-background text-foreground m-0 p-0 overflow-hidden">
      {children}
    </div>
  );
}
