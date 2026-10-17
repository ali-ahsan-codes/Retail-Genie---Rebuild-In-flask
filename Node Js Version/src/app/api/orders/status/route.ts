// src/app/api/orders/status/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { OrderStatus } from '@/types';

// Define the specific Order type for this LCD endpoint's response
type LcdOrder = {
  id: string;
  status: OrderStatus;
  createdAt: string;
  customerName?: string;
  totalAmount: number;
};

export async function GET() {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
    }

    const statusesToFetch: OrderStatus[] = ['pending_payment', 'paid', 'preparing', 'ready_for_pickup'];
    const placeholders = statusesToFetch.map(() => '?').join(',');

    // Fetch only necessary fields and limit to recent orders
    const ordersRaw = await db.all<LcdOrder[]>(
      `SELECT id, status, createdAt, customerName, totalAmount 
       FROM orders 
       WHERE status IN (${placeholders}) 
       ORDER BY createdAt DESC 
       LIMIT 50`, // Limit to last 50 relevant orders for performance
      statusesToFetch
    );
    
    const orders = ordersRaw.map(order => ({
        ...order,
        customerName: order.customerName || 'N/A', // Ensure customerName is a string for display
    }));

    return NextResponse.json(orders);
  } catch (error) {
    console.error('Failed to fetch orders for LCD:', error);
    return NextResponse.json({ error: 'Failed to fetch orders for LCD', details: (error as Error).message }, { status: 500 });
  }
}
