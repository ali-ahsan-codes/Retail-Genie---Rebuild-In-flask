
// src/app/api/purchase-orders/route.ts
import { NextResponse } from 'next/server';
import { getDb, getNextSeriesNumber, parsePurchaseOrderJSONFields, parsePOItemJSONFields } from '@/lib/server/database';
import type { PurchaseOrder, POItem, SeriesId } from '@/types';
import { v4 as uuidv4 } from 'uuid';

export async function POST(request: Request) {
  let db;
  try {
    const { supplier_id, items, expected_delivery, deadline } = await request.json();
    db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }

    if (!supplier_id || !items || !Array.isArray(items) || items.length === 0) {
      return NextResponse.json({ message: 'Missing required fields: supplier_id and at least one item are required.' }, { status: 400 });
    }

    await db.run('BEGIN TRANSACTION');

    const poId = await getNextSeriesNumber('po' as SeriesId, db);
    const now = new Date().toISOString();

    const newPOData: Omit<PurchaseOrder, 'items'> = {
      id: poId,
      supplier_id,
      status: 'Draft',
      total_amount: 0, // Will calculate this later
      advance_paid: 0,
      deadline: deadline || undefined,
      expected_delivery: expected_delivery || undefined,
      invoice_path: undefined,
      createdAt: now,
      updatedAt: now,
    };

    await db.run(
      'INSERT INTO purchase_orders (id, supplier_id, status, total_amount, advance_paid, deadline, expected_delivery, invoice_path, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      [newPOData.id, newPOData.supplier_id, newPOData.status, newPOData.total_amount, newPOData.advance_paid, newPOData.deadline, newPOData.expected_delivery, newPOData.invoice_path, newPOData.createdAt, newPOData.updatedAt]
    );

    for (const item of items) {
      let productId = item.productId;
      // Handle manual products by creating them if they don't exist by SKU
      if (item.isManual) {
        let existingProduct = item.sku ? await db.get('SELECT id FROM products WHERE sku = ?', item.sku) : null;
        if (existingProduct) {
          productId = existingProduct.id;
        } else {
          const newProductId = `prod_${Date.now()}`;
          await db.run('INSERT INTO products (id, name, sku, price, quantityInStock) VALUES (?, ?, ?, ?, ?)',
            [newProductId, item.name, item.sku || `NEW-${Date.now()}`, 0, 0] // Default price/qty
          );
          productId = newProductId;
        }
      }

      if (!productId) {
        throw new Error(`Could not determine product ID for item ${item.name}`);
      }
      
      const poItem: POItem = {
        id: uuidv4(),
        po_id: poId,
        product_id: productId,
        quantity_ordered: item.quantity,
        quantity_received: 0,
      };
      await db.run(
        'INSERT INTO po_items (id, po_id, product_id, quantity_ordered, quantity_received) VALUES (?, ?, ?, ?, ?)',
        [poItem.id, poItem.po_id, poItem.product_id, poItem.quantity_ordered, poItem.quantity_received]
      );
    }
    
    await db.run('COMMIT');

    const createdPoRaw = await db.get('SELECT * FROM purchase_orders WHERE id = ?', poId);
    if (!createdPoRaw) throw new Error("Could not retrieve PO after creation.");
    
    const createdPo = parsePurchaseOrderJSONFields(createdPoRaw);
    return NextResponse.json(createdPo, { status: 201 });
  } catch (error) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error('Failed to create purchase order:', error);
    return NextResponse.json({ message: 'Failed to create purchase order', error: (error as Error).message }, { status: 500 });
  }
}

export async function GET() {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    const purchaseOrdersRaw = await db.all<any[]>('SELECT * FROM purchase_orders');
    const purchaseOrders: PurchaseOrder[] = [];
    for (const poRaw of purchaseOrdersRaw) {
        const po = parsePurchaseOrderJSONFields(poRaw);
        const itemsRaw = await db.all('SELECT * FROM po_items WHERE po_id = ?', po.id);
        po.items = itemsRaw.map(parsePOItemJSONFields);
        const attachmentsRaw = await db.all('SELECT * FROM po_attachments WHERE po_id = ?', po.id);
        po.attachments = attachmentsRaw;
        purchaseOrders.push(po);
    }
    return NextResponse.json(purchaseOrders, { status: 200 });
  } catch (error) {
    console.error('Failed to fetch purchase orders:', error);
    return NextResponse.json({ message: 'Failed to fetch purchase orders', error: (error as Error).message }, { status: 500 });
  }
}
