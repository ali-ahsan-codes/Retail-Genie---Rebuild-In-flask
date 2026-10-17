// src/components/layout/RootErrorFallback.tsx
"use client";

import { Button } from '@/components/ui/button';
import { AlertTriangle } from 'lucide-react';

export default function RootErrorFallbackComponent() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-background p-6 text-center">
      <AlertTriangle className="w-20 h-20 text-destructive mb-6" />
      <h1 className="text-4xl font-bold text-foreground mb-3">Application Error</h1>
      <p className="text-lg text-muted-foreground mb-8 max-w-lg">
        We&apos;re sorry for the inconvenience. Please try refreshing the application.
        If the issue persists, contact support.
      </p>
      <button
        onClick={() => window.location.reload()}
        className="px-6 py-3 bg-destructive text-destructive-foreground rounded-md font-semibold text-lg hover:bg-destructive/90 transition-colors"
      >
        Refresh Application
      </button>
    </div>
  );
}
