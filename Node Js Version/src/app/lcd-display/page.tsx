// src/app/lcd-display/page.tsx
'use client';
import { useEffect, useState, useCallback } from 'react';
import { useApp } from '@/context/AppContext';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';
import type { OrderStatus as AppOrderStatus } from '@/types';

type LcdOrder = {
  id: string;
  status: AppOrderStatus;
  createdAt: string;
  customerName: string;
  totalAmount: number;
};

const STAGES_CONFIG = [
  { id: 1, name: 'Order Created', status: 'pending_payment' as AppOrderStatus, color: 'bg-primary text-primary-foreground', progressColor: 'bg-primary', progressWidth: 'w-1/4' },
  { id: 2, name: 'Payment Received', status: 'paid' as AppOrderStatus, color: 'bg-accent text-accent-foreground', progressColor: 'bg-accent', progressWidth: 'w-2/4' },
  { id: 3, name: 'Preparing Order', status: 'preparing' as AppOrderStatus, color: 'bg-secondary text-secondary-foreground', progressColor: 'bg-secondary', progressWidth: 'w-3/4' },
  { id: 4, name: 'Ready to Collect', status: 'ready_for_pickup' as AppOrderStatus, color: 'bg-primary text-primary-foreground', progressColor: 'bg-primary', progressWidth: 'w-full' },
];

export default function LCDDisplayPage() {
  const { currentUser, setCurrentUser, isDataLoaded } = useApp();
  const router = useRouter();
  const [orders, setOrders] = useState<LcdOrder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showLogoutButton, setShowLogoutButton] = useState(false);
  const [isAuthorized, setIsAuthorized] = useState(false);

  // Authorization effect
  useEffect(() => {
    if (!isDataLoaded) return;

    if (!currentUser) {
      router.replace('/login');
      return;
    }
    
    if (currentUser.role === 'display' || currentUser.role === 'admin' || currentUser.role === 'manager') {
      setIsAuthorized(true);
    } else {
      router.replace(`/${currentUser.role}/dashboard`);
    }
  }, [currentUser, router, isDataLoaded]);

  // Data fetching effect, depends on authorization
  useEffect(() => {
    if (!isAuthorized) return;

    const fetchOrdersLocal = async () => {
      try {
        setError(null);
        const res = await fetch('/api/orders/status');
        if (!res.ok) {
          const errorData = await res.json().catch(() => ({ error: `Failed to fetch: ${res.status}`}));
          throw new Error(errorData.error || `Failed to fetch orders: ${res.statusText}`);
        }
        const data = await res.json();
        setOrders(data);
      } catch (err) {
        console.error("Error fetching LCD orders:", err);
        setError((err as Error).message);
      }
    };

    fetchOrdersLocal();
    const interval = setInterval(fetchOrdersLocal, 5000);
    return () => clearInterval(interval);
  }, [isAuthorized]);

  const handleLogout = () => {
    setCurrentUser(null);
    router.push('/login');
  };

  if (!isDataLoaded || !isAuthorized) {
    return (
      <div className="flex h-screen items-center justify-center p-4">
        <p className="text-foreground">Loading display...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-screen items-center justify-center p-4">
        <div className="text-center p-8 bg-destructive text-destructive-foreground rounded-lg">
          <h2 className="text-2xl font-bold mb-4">Error Loading Orders</h2>
          <p>{error}</p>
          <p className="mt-4 text-sm">Attempting to refresh automatically...</p>
        </div>
      </div>
    );
  }

  const ordersByStatus = STAGES_CONFIG.map(stageConfig => ({
    ...stageConfig,
    orders: orders
      .filter(o => o.status === stageConfig.status)
      .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
  }));

  return (
    <div className="flex h-full p-2 sm:p-4 overflow-hidden relative">
      <div
        className="absolute top-0 left-0 w-12 h-12 z-40 cursor-default"
        onMouseEnter={() => setShowLogoutButton(true)}
      />
      {showLogoutButton && (
        <div
          className="absolute top-1 left-1 z-50"
          onMouseLeave={() => setShowLogoutButton(false)}
        >
          <Button
            variant="destructive"
            size="sm"
            onClick={handleLogout}
            className="opacity-80 hover:opacity-100 transition-opacity text-xs px-2 py-1 h-auto"
          >
            <LogOut className="mr-1 h-3 w-3" /> Logout
          </Button>
        </div>
      )}
      
      {ordersByStatus.map(stage => {
        const isReadyToCollectStage = stage.status === 'ready_for_pickup';
        return (
          <div key={stage.id} className="flex-1 flex flex-col mx-1 sm:mx-2">
            <div className={`text-center p-3 sm:p-4 rounded-t-lg ${stage.color} ${isReadyToCollectStage ? 'animate-pulse' : ''}`}>
              <h2 className="text-lg sm:text-2xl font-bold truncate">{stage.name}</h2>
            </div>
            
            <div className="flex-1 overflow-y-auto bg-muted rounded-b-lg p-2 sm:p-3 space-y-2 sm:space-y-3">
              {stage.orders.length === 0 && (
                <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
                  No orders in this stage.
                </div>
              )}
              {stage.orders.map(order => {
                const currentStageConfig = STAGES_CONFIG.find(s => s.status === order.status);
                return (
                  <div 
                    key={order.id} 
                    className="p-3 bg-card text-card-foreground rounded-lg shadow-md animate-fadeIn"
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-md sm:text-lg truncate">#{order.id.slice(-6)}</span>
                      <span className="text-xs sm:text-sm text-muted-foreground">{new Date(order.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>
                    <div className="mt-1 text-sm sm:text-base truncate" title={order.customerName}>{order.customerName || 'Walk-in Customer'}</div>
                    
                    <div className="mt-3 h-1.5 sm:h-2 bg-border rounded-full overflow-hidden">
                      <div 
                        className={`h-full rounded-full ${currentStageConfig?.progressColor || 'bg-muted'} ${currentStageConfig?.progressWidth || 'w-0'} ${order.status === 'ready_for_pickup' ? 'animate-pulse' : ''}`}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
