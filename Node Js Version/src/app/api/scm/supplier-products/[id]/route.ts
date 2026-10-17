// src/app/api/scm/supplier-products/[id]/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';

interface Params {
  params: { id: string };
}

export async function DELETE(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }

    const { id } = params;
    
    const result = await db.run('DELETE FROM supplier_products WHERE id = ?', id);

    if (result.changes === 0) {
      return NextResponse.json({ message: 'Supplier product link not found' }, { status: 404 });
    }

    return NextResponse.json({ message: 'Supplier product link deleted successfully' }, { status: 200 });
  } catch (error) {
    console.error(`Failed to delete supplier product link ${params.id}:`, error);
    return NextResponse.json({ message: 'Failed to delete supplier product link', error: (error as Error).message }, { status: 500 });
  }
}
