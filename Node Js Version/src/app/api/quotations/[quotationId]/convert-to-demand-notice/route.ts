
// src/app/api/quotations/[quotationId]/convert-to-demand-notice/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseQuotationJSONFields, parseQuotationItemJSONFields, getNextSeriesNumber, parseProductJSONFields } from '@/lib/server/database';
import type { Quotation, QuotationItem, DemandNotice, User, Product } from '@/types';
import { format, addDays } from 'date-fns';

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
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    db = await getDb();
    if (!db) {
      return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
    }

    await db.run('BEGIN TRANSACTION');

    const quotationRaw = await db.get('SELECT * FROM quotations WHERE id = ?', quotationId);
    if (!quotationRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ error: 'Quotation not found' }, { status: 404 });
    }
    const quotation = parseQuotationJSONFields(quotationRaw);

    if (quotation.salespersonId !== salespersonUser.id && salespersonUser.role !== 'admin' && salespersonUser.role !== 'manager') {
      await db.run('ROLLBACK');
      return NextResponse.json({ error: 'Forbidden: You can only convert your own quotations.' }, { status: 403 });
    }

    if (quotation.status !== 'accepted') {
      await db.run('ROLLBACK');
      return NextResponse.json({ error: `Quotation must be 'accepted' to convert to Demand Notice. Current status: ${quotation.status}` }, { status: 400 });
    }

    const itemsRaw = await db.all('SELECT * FROM quotation_items WHERE quotationId = ?', quotationId);
    const quotationItems = itemsRaw.map(parseQuotationItemJSONFields);

    const externalUnconvertedItems = quotationItems.filter(item => item.isExternal && !item.converted);

    if (externalUnconvertedItems.length === 0) {
      // No explicit rollback needed if we haven't made changes yet, but good practice if we had.
      return NextResponse.json({ success: true, message: 'No external, unconverted items found to process into demand notices.', createdDemandNoticeIds: [] }, { status: 200 });
    }

    const createdDemandNoticeIds: string[] = [];
    const now = new Date().toISOString();

    for (const item of externalUnconvertedItems) {
      let productIdForDn: string;
      let isNewProductForDn: boolean = false;
      let productSkuForDn = item.productSku?.trim() || '';

      // Product handling logic - similar to POST /api/demand-notices
      const existingProductBySku = productSkuForDn ? await db.get<Product>('SELECT * FROM products WHERE sku = ?', productSkuForDn) : null;

      if (existingProductBySku) {
        productIdForDn = existingProductBySku.id;
        productSkuForDn = existingProductBySku.sku; // Use the SKU from the existing product
        isNewProductForDn = false;
      } else {
        // Create new placeholder product
        isNewProductForDn = true;
        productIdForDn = `dnp_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
        
        if (!productSkuForDn) {
            // Generate a unique SKU if not provided by quotation item for this new product
            let attempts = 0;
            const MAX_SKU_ATTEMPTS = 5;
            let uniqueSkuFound = false;
            let tempSku = '';
            do {
                tempSku = `EXT-${item.productName.substring(0,3).toUpperCase()}${Date.now().toString().slice(-3)}${Math.random().toString(36).substring(2,4).toUpperCase()}`;
                const checkExisting = await db.get('SELECT id FROM products WHERE sku = ?', tempSku);
                if (!checkExisting) uniqueSkuFound = true;
                attempts++;
            } while (!uniqueSkuFound && attempts < MAX_SKU_ATTEMPTS);
            if (!uniqueSkuFound) {
                 await db.run('ROLLBACK');
                 return NextResponse.json({ error: `Failed to generate a unique SKU for new product from quotation item "${item.productName}". Please ensure unique SKUs or try again.` }, { status: 500 });
            }
            productSkuForDn = tempSku;
        }
        
        await db.run(
          `INSERT INTO products (id, name, price, quantityInStock, sku, category, isDemandNoticeProduct) 
           VALUES (?, ?, ?, ?, ?, ?, ?)`,
          [
            productIdForDn,
            item.productName,
            item.price, // Use price from quotation item as initial product price
            0, // Initial stock is 0
            productSkuForDn,
            'External Quotation Item', // Default category
            1 // Mark as originated from DN process
          ]
        );
      }

      // Create Demand Notice
      const newDnId = await getNextSeriesNumber('demand_notice', db);
      
      const newDemandNotice: Omit<DemandNotice, 'payments' | 'quantityFulfilled' | 'linkedOrderId'> = {
        id: newDnId,
        salespersonId: quotation.salespersonId,
        salespersonName: salespersonUser.username,
        customerContactNumber: quotation.customerPhone || 'N/A',
        productId: productIdForDn,
        productName: item.productName, // Store name from quotation
        productSku: productSkuForDn, // Store SKU from quotation/generated
        quantityRequested: item.quantity,
        agreedPrice: item.price, // Store price from quotation
        expectedAvailabilityDate: format(addDays(new Date(), 7), "yyyy-MM-dd'T'HH:mm:ss.SSSxxx"), // Default to 7 days
        status: 'awaiting_stock', // Placeholder created, now awaiting stock
        isNewProduct: isNewProductForDn,
        createdAt: now,
        updatedAt: now,
        notes: `Created from Quotation: ${quotation.id}. Item: ${item.productName}. Customer: ${quotation.customerName || 'N/A'} (${quotation.customerPhone || 'N/A'}). Original Quote Notes: ${quotation.notes || ''}`.substring(0, 250),
      };

      await db.run(
        `INSERT INTO demand_notices (
          id, salespersonId, salespersonName, customerContactNumber, productId, 
          productName, productSku, quantityRequested, quantityFulfilled, 
          agreedPrice, expectedAvailabilityDate, status, isNewProduct, 
          createdAt, updatedAt, notes, payments, linkedOrderId
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          newDemandNotice.id, newDemandNotice.salespersonId, newDemandNotice.salespersonName,
          newDemandNotice.customerContactNumber, newDemandNotice.productId,
          newDemandNotice.productName, newDemandNotice.productSku, newDemandNotice.quantityRequested, 0, 
          newDemandNotice.agreedPrice, newDemandNotice.expectedAvailabilityDate, newDemandNotice.status,
          newDemandNotice.isNewProduct ? 1 : 0, newDemandNotice.createdAt, newDemandNotice.updatedAt,
          newDemandNotice.notes, JSON.stringify([]), null
        ]
      );
      createdDemandNoticeIds.push(newDnId);

      await db.run('UPDATE quotation_items SET converted = 1 WHERE id = ?', item.id);
    }

    const allItemsAfterUpdateRaw = await db.all('SELECT converted FROM quotation_items WHERE quotationId = ?', quotationId);
    const allItemsConverted = allItemsAfterUpdateRaw.every(item => item.converted === 1);

    if (allItemsConverted) {
      await db.run('UPDATE quotations SET status = ?, updatedAt = ? WHERE id = ?', 'converted', now, quotationId);
    }

    await db.run('COMMIT');
    return NextResponse.json({ 
      success: true, 
      message: `Successfully created ${createdDemandNoticeIds.length} demand notice(s) for external items.`, 
      createdDemandNoticeIds 
    });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error(`Error converting quotation ${params.quotationId} to demand notice(s):`, error);
    let detailMessage = "An internal server error occurred during conversion.";
    if(error.message) {
        detailMessage = error.message;
        if (error.message.includes('UNIQUE constraint failed: products.sku')) {
            detailMessage = "A product SKU conflict occurred. One of the external items might already exist or has a duplicate SKU.";
        }
    }
    return NextResponse.json({ error: 'Conversion to Demand Notice Failed', details: detailMessage }, { status: 500 });
  }
}

