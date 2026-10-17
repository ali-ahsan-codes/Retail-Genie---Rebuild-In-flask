// src/app/api/purchase-orders/[poId]/route.ts
import { NextResponse, NextRequest } from 'next/server';
import { getDb, parsePurchaseOrderJSONFields, parsePOItemJSONFields, parseUserJSONFields } from '@/lib/server/database';
import type { PurchaseOrder, POAttachment, User } from '@/types';

interface Params {
  params: { poId: string };
}

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
    const userId = req.headers.get('x-user-id');
    if (!userId) return null;
    const db = await getDb();
    if (!db) return null;
    return parseUserJSONFields(await db.get<User>('SELECT * FROM users WHERE id = ?', userId));
}

export async function GET(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    const poRaw = await db.get('SELECT * FROM purchase_orders WHERE id = ?', params.poId);
    if (!poRaw) {
      return NextResponse.json({ message: 'Purchase Order not found' }, { status: 404 });
    }
    
    const po = parsePurchaseOrderJSONFields(poRaw);
    const itemsRaw = await db.all('SELECT * FROM po_items WHERE po_id = ?', params.poId);
    const attachmentsRaw = await db.all<POAttachment[]>('SELECT * FROM po_attachments WHERE po_id = ? ORDER BY uploaded_at DESC', params.poId);

    po.items = itemsRaw.map(parsePOItemJSONFields);
    po.attachments = attachmentsRaw;

    return NextResponse.json(po);
  } catch (error) {
    console.error(`Failed to fetch PO ${params.poId}:`, error);
    return NextResponse.json({ message: 'Failed to fetch PO', error: (error as Error).message }, { status: 500 });
  }
}

export async function PUT(request: NextRequest, { params }: Params) {
    let db;
    try {
        const user = await getAuthenticatedUser(request);
        if (!user) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }
        
        db = await getDb();
        if (!db) {
            return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
        }
        
        await db.run('BEGIN TRANSACTION');

        const poDataFromClient = await request.json();
        const { id, ...updateData } = poDataFromClient;

        if (id !== params.poId) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: 'ID mismatch' }, { status: 400 });
        }
        
        const existingPo = await db.get('SELECT * from purchase_orders WHERE id = ?', params.poId);
        if (!existingPo) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: 'Purchase Order not found.'}, { status: 404 });
        }

        // Authorization logic
        const canAdmin = user.role === 'admin' || (user.role === 'manager' && user.permissions?.includes('manage_suppliers'));
        const canLogistics = user.role === 'logistics';
        
        const allowedUpdates: Record<string, any> = {
            updatedAt: new Date().toISOString(),
        };
        const allowedKeys = new Set<string>(['updatedAt']);

        if (canAdmin) {
            ['status', 'expected_delivery', 'deadline', 'advance_paid', 'total_amount'].forEach(k => allowedKeys.add(k));
        }
        if (canLogistics || canAdmin) {
            ['status', 'expected_delivery', 'transportationDetails'].forEach(k => allowedKeys.add(k));
        }

        let hasValidUpdate = false;
        for (const key of Object.keys(updateData)) {
            if (allowedKeys.has(key)) {
                hasValidUpdate = true;
                if (key === 'transportationDetails') {
                    allowedUpdates[key] = (updateData[key] && typeof updateData[key] === 'object')
                        ? JSON.stringify(updateData[key])
                        : null;
                } else {
                    allowedUpdates[key] = updateData[key];
                }
            } else {
                console.warn(`[API PO PUT] User ${user.id} (${user.role}) tried to update unauthorized field '${key}' on PO ${params.poId}.`);
            }
        }
        
        if (!hasValidUpdate) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: "No valid fields provided for update or permission denied for all fields."}, { status: 400 });
        }

        const setClauses = Object.keys(allowedUpdates).map(key => `${key} = ?`).join(', ');
        const queryParams = [...Object.values(allowedUpdates), params.poId];

        const result = await db.run(
            `UPDATE purchase_orders SET ${setClauses} WHERE id = ?`,
            queryParams
        );

        if (result.changes === 0) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: 'Purchase Order not found or no changes made' }, { status: 404 });
        }
        
        await db.run('COMMIT');

        const updatedPoRaw = await db.get('SELECT * FROM purchase_orders WHERE id = ?', params.poId);
        
        const updatedPo = parsePurchaseOrderJSONFields(updatedPoRaw);
        const itemsRaw = await db.all('SELECT * FROM po_items WHERE po_id = ?', params.poId);
        const attachmentsRaw = await db.all<POAttachment[]>('SELECT * FROM po_attachments WHERE po_id = ? ORDER BY uploaded_at DESC', params.poId);
        updatedPo.items = itemsRaw.map(parsePOItemJSONFields);
        updatedPo.attachments = attachmentsRaw;
        
        return NextResponse.json(updatedPo);
    } catch (error) {
        if(db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
        console.error(`Failed to update PO ${params.poId}:`, error);
        return NextResponse.json({ 
            message: 'Failed to update PO', 
            details: (error as Error).message 
        }, { status: 500 });
    }
}
