
// src/app/api/orders/[orderId]/return/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseOrderJSONFields, parseDemandNoticeJSONFields, parseUserJSONFields } from '@/lib/server/database';
import type { Order, ReturnItemDetail, PaymentDetail, ReturnTransactionInfo, Product, DemandNotice, User } from '@/types';
import { v4 as uuidv4 } from 'uuid';

interface Params {
  params: { orderId: string };
}

interface ReturnRequestBody {
  itemsToReturn: ReturnItemDetail[];
  refundPaymentDetails: PaymentDetail[];
  returnReason?: string;
  exchangeNotes?: string;
  processedByUserId: string;
  // processedByUsername will be fetched from DB
}

export async function POST(request: Request, { params }: Params) {
  let db;
  try {
    const { 
        itemsToReturn, 
        refundPaymentDetails, 
        returnReason, 
        exchangeNotes,
        processedByUserId
    } = await request.json() as ReturnRequestBody;
    
    db = await getDb();
    const orderId = params.orderId;

    if (!itemsToReturn || itemsToReturn.length === 0 || !refundPaymentDetails || !processedByUserId) {
        return NextResponse.json({ message: 'Missing required fields for return processing' }, { status: 400 });
    }
    
    const processedByUser = await db.get<User>('SELECT * FROM users WHERE id = ?', processedByUserId);
    if (!processedByUser) {
        return NextResponse.json({ message: 'Processing user not found' }, { status: 404 });
    }
    const processedByUsername = processedByUser.username;


    await db.run('BEGIN TRANSACTION');
    
    const orderRaw = await db.get('SELECT * FROM orders WHERE id = ?', orderId);
    if (!orderRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Order not found' }, { status: 404 });
    }
    let order = parseOrderJSONFields(orderRaw);

    if (order.status !== 'paid' && order.status !== 'completed' && order.status !== 'partial_payment') {
        await db.run('ROLLBACK');
        return NextResponse.json({ message: `Order status is ${order.status}. Only paid, completed, or partially paid orders can be returned.` }, { status: 400 });
    }

    let totalValueOfReturnedItems = 0;

    for (const returnedItem of itemsToReturn) {
        const originalOrderItem = order.items.find(oi => oi.productId === returnedItem.productId && oi.sku === returnedItem.sku);
        if (!originalOrderItem) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: `Item ${returnedItem.name} (SKU: ${returnedItem.sku}) not found in original order.` }, { status: 400 });
        }
        if (returnedItem.quantityToReturn <= 0) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: `Quantity to return for ${returnedItem.name} must be positive.` }, { status: 400 });
        }
        
        // Calculate sum of quantities already returned for this item from previous transactions
        let previouslyReturnedQuantity = 0;
        if (order.returnTransactions && order.returnTransactions.length > 0) {
            order.returnTransactions.forEach(rt => {
                rt.itemsReturned.forEach(prevRetItem => {
                    if (prevRetItem.productId === returnedItem.productId && prevRetItem.sku === returnedItem.sku) {
                        previouslyReturnedQuantity += prevRetItem.quantityToReturn;
                    }
                });
            });
        }

        if (previouslyReturnedQuantity + returnedItem.quantityToReturn > originalOrderItem.quantity) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: `Cannot return more ${returnedItem.name} than originally purchased (${originalOrderItem.quantity} ordered, ${previouslyReturnedQuantity} already returned).` }, { status: 400 });
        }
        
        totalValueOfReturnedItems += originalOrderItem.pricePerUnit * returnedItem.quantityToReturn;
        
        const product = await db.get<Product>('SELECT * FROM products WHERE id = ?', returnedItem.productId);
        if (product) {
            const newQuantityInStock = product.quantityInStock + returnedItem.quantityToReturn;
            let newCategory = product.category;
            if (product.isDemandNoticeProduct) {
                newCategory = product.category ? (product.category.includes('Return DN') ? product.category : `${product.category}, Return DN`) : 'Return DN';
            }
            await db.run(
                'UPDATE products SET quantityInStock = ?, category = ? WHERE id = ?',
                newQuantityInStock,
                newCategory,
                returnedItem.productId
            );
        } else {
            console.warn(`Product ${returnedItem.productId} not found for stock update during return of order ${orderId}.`);
        }
    }

    const netRefundAmount = totalValueOfReturnedItems; // Assuming full value refund for now
    const totalRefundedViaPayments = refundPaymentDetails.reduce((sum, p) => sum + p.amount, 0);

    if (Math.abs(totalRefundedViaPayments - netRefundAmount) > 0.01) { // Allow for minor float discrepancies
        await db.run('ROLLBACK');
        return NextResponse.json({ message: `Refund amount processed (OMR ${totalRefundedViaPayments.toFixed(2)}) does not match value of returned items (OMR ${netRefundAmount.toFixed(2)}). Please adjust.` }, { status: 400 });
    }

    const returnTransaction: ReturnTransactionInfo = {
        id: `RET-${uuidv4()}`,
        returnedAt: new Date().toISOString(),
        processedByUserId,
        processedByUsername,
        originalOrderItemsSnapshot: [...order.items], // Snapshot of order items at time of this return
        itemsReturned: itemsToReturn,
        notesOnExchange: exchangeNotes,
        returnReasonGeneral: returnReason,
        totalValueOfReturnedItems,
        netRefundAmount,
        refundPaymentDetails: refundPaymentDetails.map(p => ({...p, paymentDate: new Date().toISOString()})),
    };

    const updatedReturnTransactions = [...(order.returnTransactions || []), returnTransaction];
    
    // Determine new order status
    let allItemsFullyReturned = true;
    for (const originalItem of order.items) {
        let totalReturnedForThisItem = 0;
        updatedReturnTransactions.forEach(rt => {
            rt.itemsReturned.forEach(rItem => {
                if (rItem.productId === originalItem.productId && rItem.sku === originalItem.sku) {
                    totalReturnedForThisItem += rItem.quantityToReturn;
                }
            });
        });
        if (totalReturnedForThisItem < originalItem.quantity) {
            allItemsFullyReturned = false;
            break;
        }
    }
    const newOrderStatus = allItemsFullyReturned ? 'returned' : order.status; // Or 'partial_return' etc. For now, keeps original if not all returned.

    await db.run(
        'UPDATE orders SET status = ?, returnTransactions = ?, updatedAt = ? WHERE id = ?',
        newOrderStatus,
        JSON.stringify(updatedReturnTransactions),
        new Date().toISOString(),
        orderId
    );

    if (order.linkedDemandNoticeId && newOrderStatus === 'returned') {
        const dn = await db.get<DemandNotice>('SELECT * FROM demand_notices WHERE id = ?', order.linkedDemandNoticeId);
        if (dn && dn.status !== 'fulfilled' && dn.status !== 'cancelled') {
            await db.run(
                'UPDATE demand_notices SET status = ?, updatedAt = ? WHERE id = ?',
                'awaiting_customer_action', // Or 'cancelled' depending on business rule
                new Date().toISOString(),
                order.linkedDemandNoticeId
            );
        }
    }

    await db.run('COMMIT');
    
    const updatedOrderRaw = await db.get('SELECT * FROM orders WHERE id = ?', orderId);
    const updatedOrder = parseOrderJSONFields(updatedOrderRaw);

    return NextResponse.json(updatedOrder);

  } catch (error) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in return API:", e));
    console.error(`Failed to process return for order ${params.orderId}:`, error);
    return NextResponse.json({ message: 'Failed to process return', error: (error as Error).message }, { status: 500 });
  }
}
