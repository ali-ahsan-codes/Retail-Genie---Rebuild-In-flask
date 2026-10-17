
// src/app/api/suppliers/[supplierId]/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { Supplier, SupplierAttachment } from '@/types';

interface Params {
  params: { supplierId: string };
}

// GET a single supplier
export async function GET(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    const supplier = await db.get<Supplier>('SELECT * FROM suppliers WHERE id = ?', params.supplierId);
    if (!supplier) {
      return NextResponse.json({ message: 'Supplier not found' }, { status: 404 });
    }
    const attachments = await db.all<SupplierAttachment[]>('SELECT * FROM supplier_attachments WHERE supplier_id = ? ORDER BY uploaded_at DESC', params.supplierId);
    supplier.attachments = attachments;

    return NextResponse.json(supplier);
  } catch (error) {
    console.error(`Failed to fetch supplier ${params.supplierId}:`, error);
    return NextResponse.json({ message: 'Failed to fetch supplier' }, { status: 500 });
  }
}

// UPDATE a supplier
export async function PUT(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    const { name, contact_email, phone, lead_time, notes } = await request.json();
    if (!name) {
      return NextResponse.json({ message: 'Supplier name is required' }, { status: 400 });
    }

    const result = await db.run(
      'UPDATE suppliers SET name = ?, contact_email = ?, phone = ?, lead_time = ?, notes = ? WHERE id = ?',
      [name, contact_email, phone, lead_time, notes, params.supplierId]
    );

    if (result.changes === 0) {
      return NextResponse.json({ message: 'Supplier not found or no changes made' }, { status: 404 });
    }
    const updatedSupplier = await db.get('SELECT * FROM suppliers WHERE id = ?', params.supplierId);
    return NextResponse.json(updatedSupplier);
  } catch (error) {
    console.error(`Failed to update supplier ${params.supplierId}:`, error);
    return NextResponse.json({ message: 'Failed to update supplier' }, { status: 500 });
  }
}

// DELETE a supplier
export async function DELETE(request: Request, { params }: Params) {
    let db;
    try {
        db = await getDb();
        if (!db) {
            return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
        }
        
        await db.run('BEGIN TRANSACTION');
        
        // Before deleting the supplier, delete their linked products
        await db.run('DELETE FROM supplier_products WHERE supplier_id = ?', params.supplierId);
        
        const result = await db.run('DELETE FROM suppliers WHERE id = ?', params.supplierId);
        
        if (result.changes === 0) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: 'Supplier not found' }, { status: 404 });
        }
        
        await db.run('COMMIT');
        return NextResponse.json({ message: 'Supplier deleted successfully' });

    } catch (error) {
        if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in DELETE supplier:", e));
        console.error(`Failed to delete supplier ${params.supplierId}:`, error);
        return NextResponse.json({ message: 'Failed to delete supplier', error: (error as Error).message }, { status: 500 });
    }
}
