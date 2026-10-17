
// src/app/api/quotations/[quotationId]/convert-to-order/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseQuotationJSONFields, parseQuotationItemJSONFields, parseOrderJSONFields, parseProductJSONFields, getNextSeriesNumber } from '@/lib/server/database';
import type { Quotation, QuotationItem, Order, OrderItem, Product, User, SeriesNumberSetting } from '@/types';

interface RouteParams {
  params: { quotationId: string };
}

// Placeholder for actual authentication
async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
  const userId = req.headers.get('x-user-id');
  if (userId) {
    const db = await getDb();
    if (!db) return null;
    const user = await db.get<User>('SELECT id, username, role FROM users WHERE id = ?', userId);
    return user || null;
  }
  return null;
}

export async function POST(req: NextRequest, { params }: RouteParams) {
  let db;
  try {
    const { quotationId } = params;
    const salespersonUser = await getAuthenticatedUser(req);
    if (!salespersonUser) {
      return NextResponse.json({ error: 'Unauthorized', details: 'User authentication failed.' }, { status: 401 });
    }

    db = await getDb();
    if (!db) {
      console.error("[Convert To Order API] Database service unavailable at start of POST.");
      return NextResponse.json({ error: 'Database service unavailable', details: 'The database connection could not be established.' }, { status: 503 });
    }

    await db.run('BEGIN TRANSACTION');

    const quotationRaw = await db.get('SELECT * FROM quotations WHERE id = ?', quotationId);
    if (!quotationRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ error: 'Quotation not found', details: `Quotation with ID ${quotationId} was not found.` }, { status: 404 });
    }
    const quotation = parseQuotationJSONFields(quotationRaw);

    if (quotation.salespersonId !== salespersonUser.id && salespersonUser.role !== 'admin' && salespersonUser.role !== 'manager') {
      await db.run('ROLLBACK');
      return NextResponse.json({ error: 'Forbidden', details: 'You can only convert your own quotations.' }, { status: 403 });
    }
    if (quotation.status !== 'accepted') {
      await db.run('ROLLBACK');
      return NextResponse.json({ error: `Quotation must be 'accepted' to convert. Current status: ${quotation.status}` }, { status: 400 });
    }

    const itemsRaw = await db.all('SELECT * FROM quotation_items WHERE quotationId = ?', quotationId);
    if (!Array.isArray(itemsRaw)) {
        await db.run('ROLLBACK');
        console.error(`[Convert To Order API] itemsRaw for quotation ${quotationId} is not an array:`, itemsRaw);
        return NextResponse.json({ error: 'Data Error', details: 'Could not retrieve quotation items correctly.' }, { status: 500 });
    }
    const quotationItems = itemsRaw.map(parseQuotationItemJSONFields);

    const internalUnconvertedItems = quotationItems.filter(item => !item.isExternal && !item.converted && item.productId);
    if (internalUnconvertedItems.length === 0) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: true, message: 'No internal, unconverted items found in this quotation.', createdOrder: null }, { status: 200 });
    }

    // Stock Check and Order Item Creation
    const orderItemsForNewOrder: OrderItem[] = [];
    for (const qi of internalUnconvertedItems) {
      if (!qi.productId) {
        await db.run('ROLLBACK');
        return NextResponse.json({ error: `Data Integrity Issue`, details: `Internal item ${qi.productName} is missing a product ID.` }, { status: 400 });
      }
      const product = await db.get<Product>('SELECT * FROM products WHERE id = ?', qi.productId);
      if (!product) {
        await db.run('ROLLBACK');
        return NextResponse.json({ error: `Product Not Found`, details: `Product ${qi.productName} (ID: ${qi.productId}) not found.` }, { status: 404 });
      }
      if (product.quantityInStock < qi.quantity) {
        await db.run('ROLLBACK');
        return NextResponse.json({ error: `Insufficient Stock`, details: `Insufficient stock for ${product.name}. Available: ${product.quantityInStock}, Requested: ${qi.quantity}.` }, { status: 409 });
      }
      orderItemsForNewOrder.push({
        productId: qi.productId,
        name: qi.productName,
        sku: qi.productSku || product.sku,
        quantity: qi.quantity,
        pricePerUnit: qi.price,
        totalPrice: qi.price * qi.quantity,
      });
    }

    const newOrderId = await getNextSeriesNumber('invoice', db);
    
    const now = new Date().toISOString();
    const subtotal = orderItemsForNewOrder.reduce((sum, item) => sum + item.totalPrice, 0);

    const newOrderData: Order = {
      id: newOrderId,
      primarySalespersonId: quotation.salespersonId,
      primarySalespersonName: salespersonUser.username,
      items: orderItemsForNewOrder,
      subtotal: subtotal,
      discountAmount: 0, 
      taxes: [], 
      totalAmount: subtotal, 
      status: 'pending_payment',
      deliveryStatus: 'pending_dispatch',
      customerName: quotation.customerName,
      customerPhone: quotation.customerPhone,
      deliveryAddress: quotation.customerAddress,
      createdAt: now,
      updatedAt: now,
      payments: [],
      returnTransactions: [],
      linkedDemandNoticeId: undefined, 
      // Ensure all nullable fields not explicitly set here will default to NULL in DB
      secondarySalespersonId: undefined,
      secondarySalespersonName: undefined,
      primarySalespersonCommission: 1.0, // Default primary gets 100%
      secondarySalespersonCommission: undefined,
      appliedDiscountPercentage: undefined,
      appliedGlobalDiscountPercentage: undefined,
      storekeeperNotes: undefined,
      cashierNotes: undefined,
      reminderDate: undefined,
      reminderNotes: undefined,
    };

    await db.run(
      `INSERT INTO orders (
        id, primarySalespersonId, primarySalespersonName, items, subtotal, discountAmount, taxes, totalAmount, 
        status, deliveryStatus, customerName, customerPhone, deliveryAddress, createdAt, updatedAt, payments, 
        returnTransactions, secondarySalespersonId, secondarySalespersonName, primarySalespersonCommission, 
        secondarySalespersonCommission, appliedDiscountPercentage, appliedGlobalDiscountPercentage, 
        storekeeperNotes, cashierNotes, reminderDate, reminderNotes, linkedDemandNoticeId
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        newOrderData.id, newOrderData.primarySalespersonId, newOrderData.primarySalespersonName, JSON.stringify(newOrderData.items), 
        newOrderData.subtotal, newOrderData.discountAmount, JSON.stringify(newOrderData.taxes), newOrderData.totalAmount,
        newOrderData.status, newOrderData.deliveryStatus, newOrderData.customerName, newOrderData.customerPhone, newOrderData.deliveryAddress,
        newOrderData.createdAt, newOrderData.updatedAt, JSON.stringify(newOrderData.payments), JSON.stringify(newOrderData.returnTransactions),
        newOrderData.secondarySalespersonId, newOrderData.secondarySalespersonName, newOrderData.primarySalespersonCommission,
        newOrderData.secondarySalespersonCommission, newOrderData.appliedDiscountPercentage, newOrderData.appliedGlobalDiscountPercentage,
        newOrderData.storekeeperNotes, newOrderData.cashierNotes, newOrderData.reminderDate, newOrderData.reminderNotes, newOrderData.linkedDemandNoticeId
      ]
    );
    
    for (const item of internalUnconvertedItems) {
      await db.run('UPDATE products SET quantityInStock = quantityInStock - ? WHERE id = ?', item.quantity, item.productId);
      await db.run('UPDATE quotation_items SET converted = 1 WHERE id = ?', item.id);
    }

    const remainingUnconvertedItems = await db.get<{ count: number }>('SELECT COUNT(*) as count FROM quotation_items WHERE quotationId = ? AND converted = 0', quotationId);
    if (remainingUnconvertedItems && remainingUnconvertedItems.count === 0) {
      await db.run('UPDATE quotations SET status = ?, updatedAt = ? WHERE id = ?', 'converted', now, quotationId);
    }

    await db.run('COMMIT');
    
    const createdOrderRaw = await db.get('SELECT * FROM orders WHERE id = ?', newOrderId);
    if (!createdOrderRaw) {
        // This state should be highly unlikely if COMMIT succeeded.
        console.error(`[Convert To Order API] CRITICAL: Order ${newOrderId} not found after supposedly successful insert and commit.`);
        // Attempt a more graceful signal than another DB operation that might fail if DB is troubled.
        return NextResponse.json({ error: 'Server Integrity Issue', details: `Failed to confirm order creation (ID: ${newOrderId}). Order might have been created. Please check system or contact support.` }, { status: 500 });
    }
    const createdOrder = parseOrderJSONFields(createdOrderRaw);

    return NextResponse.json({ success: true, message: `Order ${newOrderId} created successfully.`, createdOrder });

  } catch (error: any) {
    if (db) {
      try {
        await db.run('ROLLBACK');
      } catch (rollbackError) {
        console.error("Rollback failed in convert-to-order:", rollbackError);
      }
    }
    
    let clientFriendlyDetail = "An unexpected server error occurred during order conversion. Please try again later.";
    let logMessage = `Error converting quotation ${params.quotationId} to order.`;

    if (error instanceof Error) {
        logMessage += ` Message: ${error.message}.`;
        // Try to make client message a bit more specific without exposing too much detail
        if (error.message.toLowerCase().includes("unique constraint failed")) {
            clientFriendlyDetail = "A data conflict occurred (e.g., trying to create a duplicate entry). Please review your data or contact support.";
        } else if (error.message.toLowerCase().includes("not null constraint failed")) {
            clientFriendlyDetail = "Some required information was missing for the order creation process.";
        } else if (error.message.toLowerCase().includes("no such column")) {
            clientFriendlyDetail = "There's a data configuration issue on the server. Please contact support.";
        } else if (error.message.length > 0 && error.message.length < 150) { // If it's a reasonably short message
            clientFriendlyDetail = `Server error: ${error.message}`;
        }
        // For very long or generic error messages, stick to the default clientFriendlyDetail.
    } else if (typeof error === 'string') {
        logMessage += ` Error: ${error}`;
        if (error.length > 0 && error.length < 150) clientFriendlyDetail = `Server error: ${error}`;
    } else {
        try {
            logMessage += ` Error object: ${JSON.stringify(error)}`;
        } catch (stringifyError) {
            logMessage += ` Non-serializable error object.`;
        }
    }
    
    console.error(logMessage, error); // Log the full error object too for server-side debugging
    
    return NextResponse.json({ 
        error: "Internal Server Error", // Generic main error type for client handleApiError
        details: clientFriendlyDetail   // More specific detail for the client
    }, { status: 500 });
  }
}
