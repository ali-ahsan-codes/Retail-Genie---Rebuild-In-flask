// src/app/api/purchase-orders/[poId]/confirm/route.ts
import { NextResponse } from 'next/server';
import { getDb, parsePurchaseOrderJSONFields } from '@/lib/server/database';
import type { PurchaseOrder } from '@/types';

interface Params {
  params: { poId: string };
}

export async function POST(request: Request, { params }: Params) {
    try {
        const db = await getDb();
        if (!db) {
            return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
        }

        const po = await db.get<PurchaseOrder>('SELECT * FROM purchase_orders WHERE id = ?', params.poId);

        if (!po) {
            return NextResponse.json({ message: 'Purchase Order not found' }, { status: 404 });
        }
        if (po.status !== 'Draft') {
            return NextResponse.json({ message: `Cannot confirm a PO with status '${po.status}'.` }, { status: 400 });
        }

        const result = await db.run(
            'UPDATE purchase_orders SET status = ?, updatedAt = ? WHERE id = ?',
            ['Confirmed', new Date().toISOString(), params.poId]
        );

        if (result.changes === 0) {
            return NextResponse.json({ message: 'No changes made' }, { status: 404 });
        }

        const updatedPoRaw = await db.get('SELECT * FROM purchase_orders WHERE id = ?', params.poId);
        const updatedPo = parsePurchaseOrderJSONFields(updatedPoRaw);
        
        return NextResponse.json(updatedPo);
    } catch (error) {
        console.error(`Failed to confirm PO ${params.poId}:`, error);
        return NextResponse.json({ message: 'Failed to confirm PO', error: (error as Error).message }, { status: 500 });
    }
}
