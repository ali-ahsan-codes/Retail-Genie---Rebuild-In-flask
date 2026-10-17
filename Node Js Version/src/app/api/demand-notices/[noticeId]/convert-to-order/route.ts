
// src/app/api/demand-notices/[noticeId]/convert-to-order/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseDemandNoticeJSONFields, parseOrderJSONFields, getNextSeriesNumber } from '@/lib/server/database';
import type { DemandNotice, Order, OrderItem, Product, User } from '@/types';

interface Params {
  params: { noticeId: string };
}

export async function POST(request: Request, { params }: Params) {
  const { noticeId } = params;
  let db;

  try {
    db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    await db.run('BEGIN TRANSACTION');

    // 1. Fetch and validate Demand Notice
    const noticeRaw = await db.get('SELECT * FROM demand_notices WHERE id = ?', noticeId);
    if (!noticeRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Demand Notice not found' }, { status: 404 });
    }
    const notice = parseDemandNoticeJSONFields(noticeRaw);

    if (notice.status !== 'full_stock_available' && notice.status !== 'customer_notified_stock') {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: `Cannot convert Demand Notice. Status is '${notice.status}'. Expected 'full_stock_available' or 'customer_notified_stock'.` }, { status: 400 });
    }
    if (!notice.productId) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Demand Notice is not linked to a valid product.' }, { status: 400 });
    }
     if (notice.linkedOrderId) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: `Demand Notice ${noticeId} is already linked to Order ${notice.linkedOrderId}.` }, { status: 409 });
    }


    // 2. Fetch associated Product and Salesperson
    const product = await db.get<Product>('SELECT * FROM products WHERE id = ?', notice.productId);
    if (!product) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: `Product with ID ${notice.productId} not found.` }, { status: 404 });
    }

    const salesperson = await db.get<User>('SELECT * FROM users WHERE id = ?', notice.salespersonId);
    if (!salesperson) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: `Salesperson with ID ${notice.salespersonId} not found.` }, { status: 404 });
    }

    // --- BEGIN STOCK DEDUCTION ---
    if (product.quantityInStock < notice.quantityRequested) {
        await db.run('ROLLBACK');
        return NextResponse.json({ message: `Insufficient stock for product ${product.name} (SKU: ${product.sku}). Available: ${product.quantityInStock}, Requested: ${notice.quantityRequested}. Demand Notice status might be outdated or stock count is incorrect.` }, { status: 409 });
    }
    const newStockQuantity = product.quantityInStock - notice.quantityRequested;
    await db.run(
        'UPDATE products SET quantityInStock = ? WHERE id = ?',
        newStockQuantity,
        product.id
    );
    // --- END STOCK DEDUCTION ---
    
    // 3. Generate new unique Order ID (Invoice ID) using getNextSeriesNumber
    const newOrderId = await getNextSeriesNumber('invoice', db);
    
    // 4. Construct new Order object
    const now = new Date().toISOString();
    const orderItems: OrderItem[] = [{
      productId: notice.productId,
      name: notice.productName,
      sku: notice.productSku,
      quantity: notice.quantityRequested,
      pricePerUnit: notice.agreedPrice,
      totalPrice: notice.quantityRequested * notice.agreedPrice,
    }];
    const subtotal = orderItems.reduce((sum, item) => sum + item.totalPrice, 0);
    const newOrder: Order = {
      id: newOrderId,
      primarySalespersonId: notice.salespersonId,
      primarySalespersonName: salesperson.username,
      items: orderItems,
      subtotal: subtotal,
      discountAmount: 0, 
      taxes: [],         
      totalAmount: subtotal, 
      status: 'pending_payment', 
      deliveryStatus: 'pending_dispatch',
      customerName: `DN: ${notice.id}`, 
      customerPhone: notice.customerContactNumber,
      createdAt: now,
      updatedAt: now,
      payments: notice.payments || [], 
      returnTransactions: [],
      linkedDemandNoticeId: notice.id,
      // Initialize other optional fields to undefined if they are not applicable here
      secondarySalespersonId: undefined,
      secondarySalespersonName: undefined,
      primarySalespersonCommission: 1.0, // Default to 100% for primary salesperson
      secondarySalespersonCommission: undefined,
      appliedDiscountPercentage: undefined,
      appliedGlobalDiscountPercentage: undefined,
      storekeeperNotes: undefined,
      cashierNotes: undefined,
      reminderDate: undefined,
      reminderNotes: undefined,
      deliveryAddress: undefined, // If customerAddress from DN should be used, map it here
    };

    // 5. Insert the new Order
    await db.run(
      `INSERT INTO orders (
        id, primarySalespersonId, primarySalespersonName, items, subtotal, discountAmount, taxes, totalAmount, 
        status, deliveryStatus, customerName, customerPhone, createdAt, updatedAt, payments, 
        returnTransactions, linkedDemandNoticeId, secondarySalespersonId, secondarySalespersonName,
        primarySalespersonCommission, secondarySalespersonCommission, appliedDiscountPercentage,
        appliedGlobalDiscountPercentage, deliveryAddress, storekeeperNotes, cashierNotes, reminderDate, reminderNotes
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        newOrder.id, newOrder.primarySalespersonId, newOrder.primarySalespersonName, JSON.stringify(newOrder.items), 
        newOrder.subtotal, newOrder.discountAmount, JSON.stringify(newOrder.taxes), newOrder.totalAmount,
        newOrder.status, newOrder.deliveryStatus, newOrder.customerName, newOrder.customerPhone,
        newOrder.createdAt, newOrder.updatedAt, JSON.stringify(newOrder.payments),
        JSON.stringify(newOrder.returnTransactions), newOrder.linkedDemandNoticeId,
        newOrder.secondarySalespersonId, newOrder.secondarySalespersonName,
        newOrder.primarySalespersonCommission, newOrder.secondarySalespersonCommission,
        newOrder.appliedDiscountPercentage, newOrder.appliedGlobalDiscountPercentage,
        newOrder.deliveryAddress, newOrder.storekeeperNotes, newOrder.cashierNotes,
        newOrder.reminderDate, newOrder.reminderNotes
      ]
    );

    // 6. Update Demand Notice (Removed manual invoice number setting update)
    await db.run(
      'UPDATE demand_notices SET linkedOrderId = ?, status = ?, updatedAt = ? WHERE id = ?',
      newOrder.id,
      'order_processing',
      now,
      noticeId
    );

    await db.run('COMMIT');
    
    const createdOrderRaw = await db.get('SELECT * FROM orders WHERE id = ?', newOrder.id);
    const createdOrder = parseOrderJSONFields(createdOrderRaw);

    return NextResponse.json(createdOrder, { status: 201 });

  } catch (error) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in convert-to-order:", e));
    console.error(`Failed to convert Demand Notice ${noticeId} to order:`, error);
    return NextResponse.json({ message: 'Failed to convert Demand Notice to order', error: (error as Error).message }, { status: 500 });
  }
}
    
