
// src/components/ErrorBoundary.tsx
'use client'; // Required for class components used as error boundaries in App Router

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Button } from '@/components/ui/button'; // Assuming you have a Button component
import { AlertTriangle } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode; // Optional custom fallback
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    // Update state so the next render will show the fallback UI.
    return { hasError: true, error, errorInfo: null }; // errorInfo will be set in componentDidCatch
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ error, errorInfo });
    // You can also log the error to an error reporting service here
    console.error("Uncaught error:", error, errorInfo);
  }

  private handleReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      // Default fallback UI
      return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-background p-6 text-center">
          <AlertTriangle className="w-16 h-16 text-destructive mb-4" />
          <h1 className="text-3xl font-bold text-foreground mb-2">Oops! Something went wrong.</h1>
          <p className="text-muted-foreground mb-6 max-w-md">
            We're sorry for the inconvenience. An unexpected error occurred.
            Please try refreshing the page.
          </p>
          <Button onClick={this.handleReload} variant="destructive" size="lg">
            Refresh Page
          </Button>
          {process.env.NODE_ENV === 'development' && this.state.error && (
            <details className="mt-6 text-left p-4 border rounded-md bg-destructive/10 max-w-2xl mx-auto overflow-auto">
              <summary className="text-destructive font-medium cursor-pointer">Error Details (Development Only)</summary>
              <pre className="mt-2 text-xs text-destructive whitespace-pre-wrap">
                {this.state.error.toString()}
                {this.state.errorInfo && this.state.errorInfo.componentStack && (
                  `\n\nComponent Stack:\n${this.state.errorInfo.componentStack}`
                )}
              </pre>
            </details>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
