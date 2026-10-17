
import { NextResponse } from 'next/server';
import { getDb, parseOrderJSONFields, getNextSeriesNumber } from '@/lib/server/database';
import type { Order, PaymentDetail } from '@/types'; // Added PaymentDetail

export async function GET() {
  try {
    const db = await getDb();
    const ordersRaw = await db.all('SELECT * FROM orders ORDER BY createdAt DESC');
    const orders = ordersRaw.map(parseOrderJSONFields);
    return NextResponse.json(orders);
  } catch (error) {
    console.error('Failed to fetch orders:', error);
    return NextResponse.json({ message: 'Failed to fetch orders' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  let db;
  try {
    const orderData = await request.json() as Omit<Order, 'id' | 'createdAt' | 'updatedAt' | 'status' | 'deliveryStatus' | 'returnTransactions'> & {
        primarySalespersonId: string;
        primarySalespersonName?: string; 
        linkedDemandNoticeId?: string;
        payments?: PaymentDetail[]; 
    };
    db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    await db.run('BEGIN TRANSACTION');

    if (!orderData.primarySalespersonId || !orderData.items || orderData.items.length === 0 || orderData.subtotal == null || orderData.totalAmount == null) {
        await db.run('ROLLBACK');
        return NextResponse.json({ message: 'Missing required order fields (primarySalespersonId, items, subtotal, totalAmount)' }, { status: 400 });
    }

    const invoiceId = await getNextSeriesNumber('invoice', db);

    const primarySalespersonFromDb = await db.get('SELECT username FROM users WHERE id = ?', orderData.primarySalespersonId);
    if (!primarySalespersonFromDb) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: `Primary salesperson with ID ${orderData.primarySalespersonId} not found` }, { status: 400 });
    }
    const primarySalespersonNameToUse = orderData.primarySalespersonName || primarySalespersonFromDb.username;

    let secondarySalespersonName;
    if (orderData.secondarySalespersonId) {
        const secondarySp = await db.get('SELECT username FROM users WHERE id = ?', orderData.secondarySalespersonId);
        secondarySalespersonName = secondarySp?.username;
    }

    const now = new Date().toISOString();

    const newOrder: Order = {
      id: invoiceId, 
      primarySalespersonId: orderData.primarySalespersonId,
      primarySalespersonName: primarySalespersonNameToUse,
      secondarySalespersonId: orderData.secondarySalespersonId,
      secondarySalespersonName: secondarySalespersonName,
      primarySalespersonCommission: orderData.primarySalespersonCommission,
      secondarySalespersonCommission: orderData.secondarySalespersonCommission,
      items: orderData.items,
      subtotal: orderData.subtotal,
      discountAmount: orderData.discountAmount || 0,
      appliedDiscountPercentage: orderData.appliedDiscountPercentage,
      appliedGlobalDiscountPercentage: orderData.appliedGlobalDiscountPercentage,
      taxes: orderData.taxes || [],
      totalAmount: orderData.totalAmount,
      status: orderData.linkedDemandNoticeId ? 'pending_payment' : 'pending_payment',
      deliveryStatus: 'pending_dispatch',
      customerName: orderData.customerName,
      customerPhone: orderData.customerPhone,
      deliveryAddress: orderData.deliveryAddress,
      createdAt: now,
      updatedAt: now,
      payments: orderData.payments || [], 
      returnTransactions: [],
      reminderDate: orderData.reminderDate,
      reminderNotes: orderData.reminderNotes,
      linkedDemandNoticeId: orderData.linkedDemandNoticeId,
    };

    await db.run(
      `INSERT INTO orders (
        id, primarySalespersonId, primarySalespersonName, secondarySalespersonId, secondarySalespersonName,
        primarySalespersonCommission, secondarySalespersonCommission, items, subtotal, discountAmount,
        appliedDiscountPercentage, appliedGlobalDiscountPercentage, taxes, totalAmount, status, deliveryStatus,
        customerName, customerPhone, deliveryAddress, createdAt, updatedAt, payments, reminderDate, reminderNotes, returnTransactions, linkedDemandNoticeId
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      newOrder.id, newOrder.primarySalespersonId, newOrder.primarySalespersonName, newOrder.secondarySalespersonId, newOrder.secondarySalespersonName,
      newOrder.primarySalespersonCommission, newOrder.secondarySalespersonCommission, JSON.stringify(newOrder.items), newOrder.subtotal, newOrder.discountAmount,
      newOrder.appliedDiscountPercentage, newOrder.appliedGlobalDiscountPercentage, JSON.stringify(newOrder.taxes), newOrder.totalAmount, newOrder.status, newOrder.deliveryStatus,
      newOrder.customerName, newOrder.customerPhone, newOrder.deliveryAddress, newOrder.createdAt, newOrder.updatedAt,
      JSON.stringify(newOrder.payments), newOrder.reminderDate, newOrder.reminderNotes, JSON.stringify(newOrder.returnTransactions), newOrder.linkedDemandNoticeId
    );
    

    if (!newOrder.linkedDemandNoticeId) {
        for (const item of newOrder.items) {
          const productCheck = await db.get('SELECT id FROM products WHERE id = ?', item.productId);
          if (!productCheck) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: `Product with ID ${item.productId} for item '${item.name}' not found during stock update.` }, { status: 400 });
          }
          await db.run('UPDATE products SET quantityInStock = quantityInStock - ? WHERE id = ?', item.quantity, item.productId);
        }
    } else {
        const dnCheck = await db.get('SELECT id FROM demand_notices WHERE id = ?', newOrder.linkedDemandNoticeId);
        if (!dnCheck) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: `Linked Demand Notice with ID ${newOrder.linkedDemandNoticeId} not found.` }, { status: 400 });
        }
        await db.run('UPDATE demand_notices SET linkedOrderId = ?, status = ? WHERE id = ?', newOrder.id, 'order_processing', newOrder.linkedDemandNoticeId);
    }

    await db.run('COMMIT');
    return NextResponse.json(newOrder, { status: 201 });
  } catch (error) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    const errorMessage = (error instanceof Error && error.message) ? error.message : 'An unknown error occurred during order creation on the server.';
    console.error('Failed to add order (API POST):', errorMessage, error); 
    return NextResponse.json({ message: `Order creation failed on server. Details: ${errorMessage}` }, { status: 500 });
  }
}
