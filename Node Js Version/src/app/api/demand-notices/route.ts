
import { NextResponse } from 'next/server';
import { getDb, parseDemandNoticeJSONFields, getNextSeriesNumber } from '@/lib/server/database';
import type { DemandNotice } from '@/types';
import { format } from 'date-fns';

export async function GET() {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    const noticesRaw = await db.all('SELECT * FROM demand_notices ORDER BY createdAt DESC');
    const notices = noticesRaw.map(parseDemandNoticeJSONFields);
    return NextResponse.json(notices);
  } catch (error) {
    console.error('Failed to fetch demand notices:', error);
    return NextResponse.json(
      { message: 'Failed to fetch demand notices' },
      { status: 500 }
    );
  }
}

export async function POST(request: Request) {
  let db;
  // Variables to hold data for potential use in the catch block, initialized to be safe.
  let requestBody: any = null; 
  let determinedProductSku: string | undefined = undefined;

  try {
    requestBody = await request.json();
    
    const noticeData = requestBody as Omit<DemandNotice, 'id' | 'createdAt' | 'updatedAt' | 'status' | 'quantityFulfilled' | 'payments'>;
    determinedProductSku = noticeData.productSku; // Initial assumption

    db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    await db.run('BEGIN TRANSACTION');

    // Validate required fields
    const requiredFields = [
      'salespersonId',
      'salespersonName',
      'productName',
      'customerContactNumber',
      'quantityRequested',
      'agreedPrice',
      'expectedAvailabilityDate'
    ];
    
    const missingFields = requiredFields.filter(field => !(noticeData as any)[field]);
    if (missingFields.length > 0) {
      await db.run('ROLLBACK');
      return NextResponse.json(
        { message: `Missing required fields: ${missingFields.join(', ')}` },
        { status: 400 }
      );
    }

    const newNoticeId = await getNextSeriesNumber('demand_notice', db);

    let resolvedProductId: string | undefined = noticeData.productId;

    if (noticeData.isNewProduct) {
        resolvedProductId = undefined;
        if (noticeData.productSku && noticeData.productSku.trim() !== "") {
            determinedProductSku = noticeData.productSku.trim();
            const existingProductWithSku = await db.get('SELECT id FROM products WHERE sku = ?', determinedProductSku);
            if (existingProductWithSku) {
                await db.run('ROLLBACK');
                return NextResponse.json(
                    { message: `A product with Product Code '${determinedProductSku}' already exists. Please use a different Product Code or select the existing product if it's the same item.` },
                    { status: 409 }
                );
            }
        } else {
            let attempts = 0;
            const MAX_SKU_ATTEMPTS = 5;
            let uniqueSkuFound = false;
            let tempSku = '';
            do {
                tempSku = `NEW-${Date.now().toString(36)}-${Math.random().toString(36).substring(2, 7).toUpperCase()}`;
                const existingProductWithGeneratedSku = await db.get('SELECT id FROM products WHERE sku = ?', tempSku);
                if (!existingProductWithGeneratedSku) {
                    uniqueSkuFound = true;
                }
                attempts++;
            } while (!uniqueSkuFound && attempts < MAX_SKU_ATTEMPTS);

            if (!uniqueSkuFound) {
                await db.run('ROLLBACK');
                return NextResponse.json({ message: 'Failed to generate a unique Product Code for the new item. Please try again or enter one manually.' }, { status: 500 });
            }
            determinedProductSku = tempSku;
        }
    } else { 
        if (!resolvedProductId) { 
            await db.run('ROLLBACK');
            return NextResponse.json({ message: 'Product ID is required when creating a demand notice for an existing product.' }, { status: 400 });
        }
        const existingProduct = await db.get<{ sku: string }>('SELECT sku FROM products WHERE id = ?', resolvedProductId);
        if (!existingProduct) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: `The selected existing product (ID: ${resolvedProductId}) was not found.` }, { status: 404 });
        }
        determinedProductSku = existingProduct.sku;
    }

    if (!determinedProductSku) { 
        await db.run('ROLLBACK');
        return NextResponse.json({ message: 'Failed to determine Product Code for the demand notice. Ensure a product is selected or details for a new product are complete.' }, { status: 500 });
    }

    const now = new Date().toISOString();
    const newNotice: DemandNotice = {
      ...noticeData,
      id: newNoticeId,
      productId: resolvedProductId, 
      productSku: determinedProductSku, // Use the definitively determined SKU
      status: noticeData.isNewProduct ? 'pending_review' : 'awaiting_stock',
      quantityFulfilled: 0,
      createdAt: now,
      updatedAt: now,
      payments: [],
    };

    await db.run(
      `INSERT INTO demand_notices (
        id, salespersonId, salespersonName, customerContactNumber, productId, 
        productName, productSku, quantityRequested, quantityFulfilled, 
        agreedPrice, expectedAvailabilityDate, status, isNewProduct, 
        createdAt, updatedAt, notes, payments, linkedOrderId
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        newNotice.id, newNotice.salespersonId, newNotice.salespersonName,
        newNotice.customerContactNumber, newNotice.productId, newNotice.productName,
        newNotice.productSku, newNotice.quantityRequested, newNotice.quantityFulfilled,
        newNotice.agreedPrice, newNotice.expectedAvailabilityDate, newNotice.status,
        newNotice.isNewProduct ? 1 : 0, newNotice.createdAt, newNotice.updatedAt,
        newNotice.notes, JSON.stringify(newNotice.payments), newNotice.linkedOrderId
      ]
    );

    if (newNotice.isNewProduct) {
      const generatedNewProductId = `dnp_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      await db.run(
        `INSERT INTO products (
          id, name, price, quantityInStock, sku, category, isDemandNoticeProduct
        ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
        [
          generatedNewProductId, newNotice.productName, newNotice.agreedPrice,
          0, newNotice.productSku, // Use the SKU from newNotice (which is determinedProductSku)
          'Demand Notice Item', 1
        ]
      );
      await db.run(
        'UPDATE demand_notices SET productId = ? WHERE id = ?',
        [generatedNewProductId, newNotice.id]
      );
      newNotice.productId = generatedNewProductId;
    }

    await db.run('COMMIT');
    return NextResponse.json(parseDemandNoticeJSONFields(newNotice), { status: 201 });

  } catch (error: any) {
    if (db) {
      await db.run('ROLLBACK').catch(e => console.error('Rollback failed:', e));
    }
    
    // Log the detailed error on the server for debugging
    console.error('Failed to add demand notice API error:', error);
    
    let clientErrorMessage = 'Failed to add demand notice due to an unexpected server error. Please check server logs for details.';
    let statusCode = 500;

    if (error && typeof error.message === 'string') {
        const actualErrorMessageFromServer = error.message;
        
        if (actualErrorMessageFromServer.includes('UNIQUE constraint failed: products.sku')) {
            // Safely access SKU for the error message
            const conflictingSku = determinedProductSku || (requestBody && requestBody.productSku) || 'the specified Product Code';
            clientErrorMessage = `A product with Product Code '${conflictingSku}' already exists. Please use a unique code or select the existing product.`;
            statusCode = 409;
        } else if (actualErrorMessageFromServer.includes('NOT NULL constraint failed')) {
             clientErrorMessage = `A required field was missing or invalid when creating the demand notice. Specific error: ${actualErrorMessageFromServer}`;
             statusCode = 400;
        }
        // If it's another type of error but has a message, use that.
        else if (actualErrorMessageFromServer) {
             clientErrorMessage = `Server error: ${actualErrorMessageFromServer}`;
        }
    } else if (error && error.type === 'SyntaxError') { // Specifically for JSON parsing errors
        clientErrorMessage = "Invalid data format sent to server. Please check your input.";
        statusCode = 400;
    }
    
    return NextResponse.json(
      { message: clientErrorMessage },
      { status: statusCode }
    );
  }
}
