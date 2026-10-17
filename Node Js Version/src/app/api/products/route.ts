
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { Product } from '@/types';

export async function GET() {
  try {
    const db = await getDb();
    if (!db) {
        console.error("[API Products GET] Database not available.");
        return NextResponse.json({ success: false, error: 'Database service temporarily unavailable.' }, { status: 503 });
    }
    const products = await db.all<Product[]>('SELECT * FROM products');
    return NextResponse.json(products); // Default success is true, data is products
  } catch (error) {
    console.error('Failed to fetch products:', error);
    return NextResponse.json({ success: false, error: (error as Error).message || 'Failed to fetch products' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  let db;
  let productData: Omit<Product, 'id'>;
  try {
    productData = await request.json() as Omit<Product, 'id'>;
    db = await getDb();
    if (!db) {
        console.error("[API Products POST] Database not available.");
        return NextResponse.json({ success: false, error: 'Database service temporarily unavailable.' }, { status: 503 });
    }
    await db.run('BEGIN TRANSACTION');

    if (!productData.name || !productData.sku || productData.price == null || productData.quantityInStock == null) {
        await db.run('ROLLBACK');
        return NextResponse.json({ success: false, error: 'Missing required product fields' }, { status: 400 });
    }

    const newProductId = 'prod_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7);
    const newProduct: Product = { 
        ...productData, 
        id: newProductId, 
        isDemandNoticeProduct: productData.isDemandNoticeProduct || false,
        lowStockThreshold: productData.lowStockThreshold,
        lowStockPrice: productData.lowStockPrice 
    };

    await db.run(
      'INSERT INTO products (id, name, price, quantityInStock, sku, expiryDate, imageUrl, category, isDemandNoticeProduct, lowStockThreshold, lowStockPrice) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      newProduct.id, newProduct.name, newProduct.price, newProduct.quantityInStock, newProduct.sku,
      newProduct.expiryDate, newProduct.imageUrl, newProduct.category, newProduct.isDemandNoticeProduct ? 1 : 0,
      newProduct.lowStockThreshold, newProduct.lowStockPrice
    );

    // Check for demand notices related to this new product's SKU
    if (newProduct.quantityInStock > 0) {
      const relatedNoticesRaw = await db.all('SELECT * FROM demand_notices WHERE productSku = ? AND status IN (?, ?, ?)',
        newProduct.sku, 'awaiting_stock', 'pending_review', 'partial_stock_available'
      );
      
      type LocalDemandNotice = {
        id: string;
        productSku: string;
        quantityRequested: number;
        quantityFulfilled?: number;
        status: string;
        payments: any[]; 
        isNewProduct: boolean;
      };

      const relatedNotices: LocalDemandNotice[] = relatedNoticesRaw.map((noticeRaw: any) => ({
        ...noticeRaw,
        payments: noticeRaw.payments ? JSON.parse(noticeRaw.payments) : [],
        isNewProduct: !!noticeRaw.isNewProduct, 
      }));


      for (const notice of relatedNotices) {
        const newQuantityFulfilled = Math.min(notice.quantityRequested, (notice.quantityFulfilled || 0) + newProduct.quantityInStock);
        const newStatus: string = newQuantityFulfilled >= notice.quantityRequested ? 'full_stock_available' : 'partial_stock_available';

        await db.run(
          'UPDATE demand_notices SET status = ?, quantityFulfilled = ?, productId = ?, updatedAt = ? WHERE id = ?',
          newStatus, newQuantityFulfilled, newProduct.id, new Date().toISOString(), notice.id
        );
      }
    }

    await db.run('COMMIT');
    return NextResponse.json({ success: true, data: newProduct }, { status: 201 });
  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Product add rollback failed:", e));
    console.error('Failed to add product:', error);
    let errorMessage = 'Failed to add product';
    if (error.message && error.message.includes('UNIQUE constraint failed: products.sku')) {
      errorMessage = `Product with Product Code ${productData!.sku} already exists`;
      return NextResponse.json({ success: false, error: errorMessage }, { status: 409 });
    } else if (error.message) {
      errorMessage = error.message;
    }
    return NextResponse.json({ success: false, error: errorMessage }, { status: 500 });
  }
}

