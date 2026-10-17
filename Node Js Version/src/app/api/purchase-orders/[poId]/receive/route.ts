// src/app/api/purchase-orders/[poId]/receive/route.ts
import { NextResponse, NextRequest } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { POItem, Product, PurchaseOrder, User, POAttachment } from '@/types';
import { v4 as uuidv4 } from 'uuid';
import { promises as fs } from 'fs';
import path from 'path';

const PO_ATTACHMENTS_DIR = path.join(process.cwd(), 'uploads', 'scm', 'po_attachments');

async function ensureUploadsDirExists(poId: string): Promise<string> {
  const dir = path.join(PO_ATTACHMENTS_DIR, poId);
  try {
    await fs.access(dir);
  } catch {
    await fs.mkdir(dir, { recursive: true });
  }
  return dir;
}


interface ReceiveItemPayload {
    poItemId: string;
    productId: string;
    receivedQuantity: number;
    notes?: string;
}

interface Params {
  params: { poId: string };
}

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
    const userId = req.headers.get('x-user-id');
    if (!userId) return null;
    const db = await getDb();
    if (!db) return null;
    return db.get<User>('SELECT * FROM users WHERE id = ?', userId);
}


export async function POST(request: NextRequest, { params }: Params) {
    let db;
    try {
        const { poId } = params;
        const formData = await request.formData();
        
        const itemsJson = formData.get('items') as string | null;
        if (!itemsJson) {
            return NextResponse.json({ message: 'Missing items data in form submission.'}, { status: 400 });
        }
        const itemsToReceive: ReceiveItemPayload[] = JSON.parse(itemsJson);
        
        const grnAttachments = formData.getAll('grnAttachments') as File[];
        const storageEvidenceFiles = formData.getAll('storageEvidence') as File[];
        const user = await getAuthenticatedUser(request);


        db = await getDb();
        if (!db) {
            return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
        }
        
        await db.run('BEGIN TRANSACTION');

        const po = await db.get<PurchaseOrder>('SELECT * FROM purchase_orders WHERE id = ?', poId);
        if (!po) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: 'Purchase Order not found' }, { status: 404 });
        }
        if (po.status !== 'Confirmed' && po.status !== 'Shipped') {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: `Cannot receive stock for a PO with status '${po.status}'.` }, { status: 400 });
        }

        const poItemsFromDb = await db.all<POItem[]>('SELECT * FROM po_items WHERE po_id = ?', poId);
        const now = new Date().toISOString();

        for (const receivedItem of itemsToReceive) {
            const poItemFromDb = poItemsFromDb.find(i => i.id === receivedItem.poItemId);
            if (!poItemFromDb) {
                throw new Error(`Item with ID ${receivedItem.poItemId} not found in this PO.`);
            }

            const quantityToReceive = Number(receivedItem.receivedQuantity);
            if (isNaN(quantityToReceive) || quantityToReceive < 0) {
                 throw new Error(`Invalid quantity received for item ${poItemFromDb.product_id}.`);
            }
            
            const remainingQty = poItemFromDb.quantity_ordered - (poItemFromDb.quantity_received || 0);
            if (quantityToReceive > remainingQty) {
                throw new Error(`Cannot receive more than remaining quantity (${remainingQty}) for item ${poItemFromDb.product_id}.`);
            }
            
            // Update PO Item received quantity
            if(quantityToReceive > 0) {
                await db.run(
                    'UPDATE po_items SET quantity_received = (quantity_received OR 0) + ?, notes = ?, updatedAt = ? WHERE id = ?',
                    [quantityToReceive, receivedItem.notes || poItemFromDb.notes || null, now, receivedItem.poItemId]
                );

                // Update Product Stock
                await db.run(
                    'UPDATE products SET quantityInStock = quantityInStock + ? WHERE id = ?',
                    [quantityToReceive, poItemFromDb.product_id]
                );
            }
        }

        // Handle file uploads
        if ((grnAttachments.length > 0 || storageEvidenceFiles.length > 0) && user) {
            const poDir = await ensureUploadsDirExists(poId);
            
            // Handle GRN attachments
            for (const file of grnAttachments) {
                const attachmentId = uuidv4();
                const fileExtension = path.extname(file.name) || '.bin';
                const savedFileName = `${attachmentId}${fileExtension}`;
                const filePathOnDisk = path.join(poDir, savedFileName);
                const buffer = Buffer.from(await file.arrayBuffer());
                await fs.writeFile(filePathOnDisk, buffer);

                const relativeDbPath = `scm/po_attachments/${poId}/${savedFileName}`;
                await db.run(
                    'INSERT INTO po_attachments (id, po_id, file_path, original_name, notes, type, uploaded_at, uploaded_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    [attachmentId, poId, relativeDbPath, file.name, 'GRN Attachment', 'grn', new Date().toISOString(), user.id]
                );
            }
            
            // Handle Storage Evidence attachments
            for (const file of storageEvidenceFiles) {
                const attachmentId = uuidv4();
                const fileExtension = path.extname(file.name) || '.bin';
                const savedFileName = `${attachmentId}_storage${fileExtension}`;
                const filePathOnDisk = path.join(poDir, savedFileName);
                const buffer = Buffer.from(await file.arrayBuffer());
                await fs.writeFile(filePathOnDisk, buffer);

                const relativeDbPath = `scm/po_attachments/${poId}/${savedFileName}`;
                await db.run(
                    'INSERT INTO po_attachments (id, po_id, file_path, original_name, notes, type, uploaded_at, uploaded_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    [attachmentId, poId, relativeDbPath, file.name, 'Storage Evidence', 'storage_evidence', new Date().toISOString(), user.id]
                );
            }
        }

        // Check if all items are fully received to update PO status
        const updatedPoItemsFromDb = await db.all<POItem[]>('SELECT * FROM po_items WHERE po_id = ?', poId);
        const allItemsReceived = updatedPoItemsFromDb.every(item => (item.quantity_received || 0) >= item.quantity_ordered);


        if (allItemsReceived) {
            await db.run('UPDATE purchase_orders SET status = ?, updatedAt = ? WHERE id = ?', ['Received', now, poId]);
        }
        
        await db.run('COMMIT');
        
        return NextResponse.json({ success: true, message: 'Stock received and updated successfully.' });

    } catch (error) {
        if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
        console.error('Failed to receive stock:', error);
        return NextResponse.json({ message: 'Failed to receive stock', error: (error as Error).message }, { status: 500 });
    }
}
