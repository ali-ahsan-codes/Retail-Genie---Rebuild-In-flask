// src/app/api/express/checkout/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseOrderJSONFields, getNextSeriesNumber } from '@/lib/server/database';
import type { OrderItem, PaymentDetail, Order, Product } from '@/types';

interface ExpressCheckoutItem {
  sku: string;
  quantity: number;
}

interface ExpressCheckoutRequest {
  items: ExpressCheckoutItem[];
  payments: PaymentDetail[];
  cashierId: string;
}

export async function POST(request: NextRequest) {
  let db;
  try {
    const { items, payments, cashierId } = await request.json() as ExpressCheckoutRequest;

    if (!items || items.length === 0 || !payments || payments.length === 0 || !cashierId) {
      return NextResponse.json({ message: 'Missing required checkout data' }, { status: 400 });
    }

    db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }

    await db.run('BEGIN TRANSACTION');

    const skus = items.map(item => item.sku);
    const placeholders = skus.map(() => '?').join(',');
    const productsFromDb = await db.all<Product[]>(`SELECT * FROM products WHERE sku IN (${placeholders})`, skus);

    const productMap = new Map(productsFromDb.map(p => [p.sku, p]));
    let subtotal = 0;
    const orderItems: OrderItem[] = [];

    for (const item of items) {
      const product = productMap.get(item.sku);
      if (!product) {
        throw new Error(`Product with SKU ${item.sku} not found.`);
      }
      if (product.quantityInStock < item.quantity) {
        throw new Error(`Insufficient stock for ${product.name} (SKU: ${item.sku}). Available: ${product.quantityInStock}, Requested: ${item.quantity}.`);
      }
      const itemTotalPrice = product.price * item.quantity;
      subtotal += itemTotalPrice;
      orderItems.push({
        productId: product.id,
        name: product.name,
        sku: product.sku,
        quantity: item.quantity,
        pricePerUnit: product.price,
        totalPrice: itemTotalPrice,
      });
    }

    const totalAmount = subtotal; // Assuming no taxes/discounts for express checkout
    const totalPaid = payments.reduce((sum, p) => sum + p.amount, 0);

    if (Math.abs(totalPaid - totalAmount) > 0.005) { // Check if total payments match order total
      throw new Error(`Total payment amount (OMR ${totalPaid.toFixed(2)}) does not match order total (OMR ${totalAmount.toFixed(2)}).`);
    }
    
    const transactionId = await getNextSeriesNumber('invoice', db); // Use the main invoice series
    const now = new Date().toISOString();

    const cashier = await db.get('SELECT username FROM users WHERE id = ?', cashierId);

    const newOrder: Order = {
      id: transactionId,
      primarySalespersonId: cashierId,
      primarySalespersonName: cashier?.username || 'Express Checkout',
      items: orderItems,
      subtotal,
      discountAmount: 0,
      taxes: [],
      totalAmount,
      status: 'completed',
      deliveryStatus: 'pickup_ready', // Assuming immediate pickup
      createdAt: now,
      updatedAt: now,
      payments: payments.map(p => ({ ...p, paymentDate: now, cashierId, cashierName: cashier?.username || 'Express' })),
      returnTransactions: [],
    };

    await db.run(
      'INSERT INTO orders (id, primarySalespersonId, primarySalespersonName, items, subtotal, totalAmount, status, deliveryStatus, createdAt, updatedAt, payments, discountAmount, taxes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      [newOrder.id, newOrder.primarySalespersonId, newOrder.primarySalespersonName, JSON.stringify(newOrder.items), newOrder.subtotal, newOrder.totalAmount, newOrder.status, newOrder.deliveryStatus, newOrder.createdAt, newOrder.updatedAt, JSON.stringify(newOrder.payments), newOrder.discountAmount, JSON.stringify(newOrder.taxes)]
    );

    for (const item of orderItems) {
      await db.run('UPDATE products SET quantityInStock = quantityInStock - ? WHERE id = ?', item.quantity, item.productId);
    }

    await db.run('COMMIT');

    const createdOrder = await db.get('SELECT * FROM orders WHERE id = ?', transactionId);
    return NextResponse.json({ success: true, data: parseOrderJSONFields(createdOrder) }, { status: 201 });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error('Express checkout failed:', error);
    return NextResponse.json({ message: 'Express checkout failed', error: error.message }, { status: 500 });
  }
}
