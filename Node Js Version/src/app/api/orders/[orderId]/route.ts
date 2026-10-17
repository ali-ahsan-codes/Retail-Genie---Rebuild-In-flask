
// src/app/api/orders/[orderId]/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseOrderJSONFields, parseDemandNoticeJSONFields } from '@/lib/server/database';
import type { Order, OrderStatus, OrderItem, DemandNotice } from '@/types';

interface Params {
  params: { orderId: string };
}

export async function GET(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    const orderRaw = await db.get('SELECT * FROM orders WHERE id = ?', params.orderId);
    if (!orderRaw) {
      return NextResponse.json({ message: 'Order not found' }, { status: 404 });
    }
    const order = parseOrderJSONFields(orderRaw);
    return NextResponse.json(order);
  } catch (error) {
    console.error(`Failed to fetch order ${params.orderId}:`, error);
    return NextResponse.json({ message: 'Failed to fetch order' }, { status: 500 });
  }
}

export async function PUT(request: Request, { params }: Params) {
  let db;
  try {
    const orderDataFromClient = await request.json() as Order;
    db = await getDb();
    await db.run('BEGIN TRANSACTION');

    if (orderDataFromClient.id !== params.orderId) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Order ID mismatch' }, { status: 400 });
    }
    
    const existingOrderRaw = await db.get('SELECT status, payments, totalAmount FROM orders WHERE id = ?', params.orderId);
    if (!existingOrderRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Order not found for update' }, { status: 404 });
    }
    const existingOrder = parseOrderJSONFields(existingOrderRaw);
    const currentTotalPaidOnExistingOrder = (existingOrder.payments || []).reduce((sum, p) => sum + p.amount, 0);

    let clientSentStatus = orderDataFromClient.status;
    let finalStatusToSet = clientSentStatus;


    // Stricter validation for transitioning to preparation/ready states
    if (clientSentStatus === 'preparing' || clientSentStatus === 'ready_for_pickup') {
        const orderTotalAmountForCheck = orderDataFromClient.totalAmount || existingOrder.totalAmount; // Use client's total amount if provided, else existing

        if (currentTotalPaidOnExistingOrder <= 0 && clientSentStatus === 'preparing') { // No payment at all
             await db.run('ROLLBACK');
             return NextResponse.json({ message: `Cannot set order to 'preparing'. Order has no payment recorded. Payment is required.` }, { status: 400 });
        }
        if (clientSentStatus === 'ready_for_pickup' && currentTotalPaidOnExistingOrder < (orderTotalAmountForCheck - 0.005)) { // Not fully paid
             await db.run('ROLLBACK');
             return NextResponse.json({ message: `Cannot set order to 'ready_for_pickup'. Order is not fully paid. Current paid: OMR ${currentTotalPaidOnExistingOrder.toFixed(2)}, Total: OMR ${orderTotalAmountForCheck.toFixed(2)}.` }, { status: 400 });
        }
    }
    
    // If client is updating payments (e.g., cashier action)
    if (orderDataFromClient.payments && JSON.stringify(orderDataFromClient.payments) !== JSON.stringify(existingOrder.payments)) {
        const totalPaidFromClientUpdate = (orderDataFromClient.payments || []).reduce((sum, p) => sum + p.amount, 0);
        const totalAmountDue = orderDataFromClient.totalAmount;

        if (totalPaidFromClientUpdate >= totalAmountDue - 0.005) {
            // If fully paid, and current status implies it wasn't ready for pickup, set to 'paid'.
            // If it was already 'preparing' or 'ready_for_pickup', it means payment finalized an already progressing order, keep that status.
            if (existingOrder.status === 'pending_payment' || existingOrder.status === 'partial_payment') {
                finalStatusToSet = 'paid';
            } else {
                finalStatusToSet = existingOrder.status; // Keep advanced status
            }
        } else if (totalPaidFromClientUpdate > 0) {
            finalStatusToSet = 'partial_payment';
        } else { // No payment
            finalStatusToSet = 'pending_payment';
        }
    } 
    // If client sent a status that implies payment but isn't updating payment array, validate with DB payment state
    else if (clientSentStatus === 'paid' && currentTotalPaidOnExistingOrder < (existingOrder.totalAmount - 0.005)) {
        finalStatusToSet = currentTotalPaidOnExistingOrder > 0 ? 'partial_payment' : 'pending_payment';
    } else if (clientSentStatus === 'partial_payment' && currentTotalPaidOnExistingOrder <= 0) {
        finalStatusToSet = 'pending_payment';
    } else if (clientSentStatus === 'partial_payment' && currentTotalPaidOnExistingOrder >= (existingOrder.totalAmount - 0.005)) {
        finalStatusToSet = 'paid';
    }
    // For other status changes not involving payment updates (e.g. storekeeper: paid -> preparing -> ready_for_pickup, or admin: cancelled)
    // finalStatusToSet remains clientSentStatus, assuming the initial validation for 'preparing'/'ready_for_pickup' passed.

    orderDataFromClient.status = finalStatusToSet;
    
    const result = await db.run(
      `UPDATE orders SET 
        primarySalespersonId = ?, primarySalespersonName = ?, secondarySalespersonId = ?, secondarySalespersonName = ?,
        primarySalespersonCommission = ?, secondarySalespersonCommission = ?, items = ?, subtotal = ?, discountAmount = ?,
        appliedDiscountPercentage = ?, appliedGlobalDiscountPercentage = ?, taxes = ?, totalAmount = ?, status = ?, deliveryStatus = ?,
        customerName = ?, customerPhone = ?, deliveryAddress = ?, updatedAt = ?, payments = ?, 
        reminderDate = ?, reminderNotes = ?, returnTransactions = ?
       WHERE id = ?`,
      orderDataFromClient.primarySalespersonId || existingOrder.primarySalespersonId, 
      orderDataFromClient.primarySalespersonName || existingOrder.primarySalespersonName, 
      orderDataFromClient.secondarySalespersonId, 
      orderDataFromClient.secondarySalespersonName,
      orderDataFromClient.primarySalespersonCommission, 
      orderDataFromClient.secondarySalespersonCommission, 
      orderDataFromClient.items ? JSON.stringify(orderDataFromClient.items) : JSON.stringify(existingOrder.items), 
      orderDataFromClient.subtotal != null ? orderDataFromClient.subtotal : existingOrder.subtotal, 
      orderDataFromClient.discountAmount != null ? orderDataFromClient.discountAmount : existingOrder.discountAmount,
      orderDataFromClient.appliedDiscountPercentage, 
      orderDataFromClient.appliedGlobalDiscountPercentage, 
      orderDataFromClient.taxes ? JSON.stringify(orderDataFromClient.taxes) : JSON.stringify(existingOrder.taxes), 
      orderDataFromClient.totalAmount != null ? orderDataFromClient.totalAmount : existingOrder.totalAmount, 
      orderDataFromClient.status, // Use the final determined status
      orderDataFromClient.deliveryStatus,
      orderDataFromClient.customerName, 
      orderDataFromClient.customerPhone, 
      orderDataFromClient.deliveryAddress, 
      new Date().toISOString(), 
      orderDataFromClient.payments ? JSON.stringify(orderDataFromClient.payments) : JSON.stringify(existingOrder.payments),
      orderDataFromClient.reminderDate, 
      orderDataFromClient.reminderNotes, 
      orderDataFromClient.returnTransactions ? JSON.stringify(orderDataFromClient.returnTransactions) : JSON.stringify(existingOrder.returnTransactions),
      params.orderId
    );

    if (result.changes === 0) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Order not found or no changes made' }, { status: 404 });
    }

    if (orderDataFromClient.status === 'paid' && orderDataFromClient.linkedDemandNoticeId) {
      const linkedDN = await db.get('SELECT * FROM demand_notices WHERE id = ?', orderDataFromClient.linkedDemandNoticeId);
      if (linkedDN && linkedDN.status !== 'fulfilled' && linkedDN.status !== 'cancelled') {
        await db.run(
          'UPDATE demand_notices SET status = ?, updatedAt = ? WHERE id = ?',
          'fulfilled',
          new Date().toISOString(),
          orderDataFromClient.linkedDemandNoticeId
        );
      }
    }
    
    await db.run('COMMIT');
    const updatedOrderRaw = await db.get('SELECT * FROM orders WHERE id = ?', params.orderId);
    const updatedOrder = parseOrderJSONFields(updatedOrderRaw);
    return NextResponse.json(updatedOrder);

  } catch (error) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in PUT order:", e));
    console.error(`Failed to update order ${params.orderId}:`, error);
    return NextResponse.json({ message: 'Failed to update order', error: (error as Error).message }, { status: 500 });
  }
}

export async function DELETE(request: Request, { params }: Params) {
  let db;
  try {
    db = await getDb();
    
    await db.run('BEGIN TRANSACTION');

    const orderToDeleteRaw = await db.get('SELECT items, status, linkedDemandNoticeId FROM orders WHERE id = ?', params.orderId);
    
    if (!orderToDeleteRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Order not found' }, { status: 404 });
    }
    const orderToDelete = parseOrderJSONFields(orderToDeleteRaw);

    if (!orderToDelete.linkedDemandNoticeId && 
        orderToDelete.status !== 'completed' && 
        orderToDelete.status !== 'returned' && 
        orderToDelete.status !== 'cancelled') {
      
      const items: OrderItem[] = orderToDelete.items; 
      for (const item of items) {
        const productCheck = await db.get('SELECT id FROM products WHERE id = ?', item.productId);
        if (productCheck) {
          await db.run('UPDATE products SET quantityInStock = quantityInStock + ? WHERE id = ?', item.quantity, item.productId);
        } else {
          console.warn(`Product ID ${item.productId} not found during stock restoration for deleted order ${params.orderId}.`);
        }
      }
    }

    const result = await db.run('DELETE FROM orders WHERE id = ?', params.orderId);
    
    if (orderToDelete.linkedDemandNoticeId) {
      const dnToUpdate = await db.get('SELECT status FROM demand_notices WHERE id = ?', orderToDelete.linkedDemandNoticeId);
      if (dnToUpdate && dnToUpdate.status !== 'fulfilled' && dnToUpdate.status !== 'cancelled') {
        await db.run(
          'UPDATE demand_notices SET linkedOrderId = NULL, status = ?, updatedAt = ? WHERE id = ?',
          'full_stock_available', 
          new Date().toISOString(),
          orderToDelete.linkedDemandNoticeId
        );
      }
    }

    await db.run('COMMIT');

    if (result.changes === 0) { 
      return NextResponse.json({ message: 'Order not found, no deletion occurred' }, { status: 404 });
    }

    return NextResponse.json({ message: 'Order deleted successfully and stock restored if applicable' });
  } catch (error) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in DELETE order:", e));
    console.error(`Failed to delete order ${params.orderId}:`, error);
    return NextResponse.json({ message: 'Failed to delete order', error: (error as Error).message }, { status: 500 });
  }
}

    