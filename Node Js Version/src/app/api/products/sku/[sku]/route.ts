// src/app/api/products/sku/[sku]/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { Product } from '@/types';

interface Params {
  params: { sku: string };
}

export async function GET(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    if (!db) {
        return NextResponse.json({ success: false, error: 'Database service temporarily unavailable.' }, { status: 503 });
    }
    const product = await db.get<Product>('SELECT * FROM products WHERE sku = ?', params.sku);
    if (!product) {
      return NextResponse.json({ success: false, error: 'Product not found' }, { status: 404 });
    }
    return NextResponse.json({ success: true, data: product });
  } catch (error) {
    console.error(`Failed to fetch product by SKU ${params.sku}:`, error);
    return NextResponse.json({ success: false, error: (error as Error).message || 'Failed to fetch product by SKU' }, { status: 500 });
  }
}
