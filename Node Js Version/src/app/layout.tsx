
// src/app/layout.tsx
import type { Metadata, Viewport } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import { Toaster } from '@/components/ui/toaster';
import { AppProvider } from '@/context/AppContext';
import ClientOnly from '@/components/layout/ClientOnly';
import { brandingConfig } from '@/config/branding';
import ErrorBoundary from '@/components/ErrorBoundary';
import AppInitializer from '@/components/layout/AppInitializer';
import { NetworkStatusBar } from '@/components/network/NetworkStatusBar';
import RootErrorFallbackComponent from '@/components/layout/RootErrorFallback'; // Import the new component

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: brandingConfig.appName,
    description: `Point of Sale Application by ${brandingConfig.appName}`,
    icons: {
      icon: brandingConfig.faviconPath,
    },
  }
}

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: 'white' },
    { media: '(prefers-color-scheme: dark)', color: 'black' },
  ],
}

// The RootErrorFallback JSX has been moved to its own component

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased bg-gradient-to-br from-blue-50/50 to-indigo-100/50 dark:from-slate-900 dark:to-slate-950`}>
        <AppInitializer />
        <ErrorBoundary fallback={<RootErrorFallbackComponent />}> {/* Use the imported component here */}
          <AppProvider>
            {children}
            <ClientOnly>
              <Toaster />
              <NetworkStatusBar />
            </ClientOnly>
          </AppProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
