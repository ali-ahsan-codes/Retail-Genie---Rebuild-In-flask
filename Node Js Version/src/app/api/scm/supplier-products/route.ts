
// src/app/api/scm/supplier-products/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { SupplierProduct } from '@/types';
import { v4 as uuidv4 } from 'uuid';

export async function POST(request: Request) {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }

    const { supplier_id, product_id, unit_price } = await request.json();

    if (!supplier_id || !product_id || unit_price === undefined) {
      return NextResponse.json({ message: 'Missing required fields: supplier_id, product_id, unit_price' }, { status: 400 });
    }

    const newLink: SupplierProduct = {
      id: uuidv4(),
      supplier_id,
      product_id,
      unit_price: parseFloat(unit_price),
      document_path: '', // Placeholder for now
    };

    await db.run(
      'INSERT INTO supplier_products (id, supplier_id, product_id, unit_price, document_path) VALUES (?, ?, ?, ?, ?)',
      [newLink.id, newLink.supplier_id, newLink.product_id, newLink.unit_price, newLink.document_path]
    );

    return NextResponse.json(newLink, { status: 201 });
  } catch (error) {
    console.error('Failed to link supplier product:', error);
    return NextResponse.json({ message: 'Failed to link supplier product', error: (error as Error).message }, { status: 500 });
  }
}

export async function GET() {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    const linkedProducts = await db.all<SupplierProduct[]>('SELECT * FROM supplier_products');
    return NextResponse.json(linkedProducts, { status: 200 });
  } catch (error) {
    console.error('Failed to fetch supplier products:', error);
    return NextResponse.json({ message: 'Failed to fetch supplier products', error: (error as Error).message }, { status: 500 });
  }
}
