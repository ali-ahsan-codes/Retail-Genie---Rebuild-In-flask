
import { NextResponse } from 'next/server';
import { getDb, parseDemandNoticeJSONFields } from '@/lib/server/database'; 
import type { Product, DemandNotice } from '@/types';
import fs from 'fs/promises';
import path from 'path';

// Base directory for all uploads
const UPLOADS_BASE_DIR = path.join(process.cwd(), 'uploads'); 

interface Params {
  params: { productId: string };
}

export async function GET(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    if (!db) {
        console.error(`[API Product GET ${params.productId}] Database not available.`);
        return NextResponse.json({ success: false, error: 'Database service temporarily unavailable.' }, { status: 503 });
    }
    const product = await db.get<Product>('SELECT * FROM products WHERE id = ?', params.productId);
    if (!product) {
      return NextResponse.json({ success: false, error: 'Product not found' }, { status: 404 });
    }
    return NextResponse.json({ success: true, data: product });
  } catch (error) {
    console.error(`Failed to fetch product ${params.productId}:`, error);
    return NextResponse.json({ success: false, error: (error as Error).message || 'Failed to fetch product' }, { status: 500 });
  }
}

export async function PUT(request: Request, { params }: Params) {
  let db;
  let productData: Product;
  let oldDbImageUrl: string | undefined | null = null;

  try {
    productData = await request.json() as Product;
    db = await getDb();
    if (!db) {
        console.error(`[API Product PUT ${params.productId}] Database not available.`);
        return NextResponse.json({ success: false, error: 'Database service temporarily unavailable.' }, { status: 503 });
    }
    
    await db.run('BEGIN TRANSACTION');
    if (productData.id !== params.productId) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: 'Product ID mismatch' }, { status: 400 });
    }
     if (!productData.name || !productData.sku || productData.price == null || productData.quantityInStock == null) {
        await db.run('ROLLBACK');
        return NextResponse.json({ success: false, error: 'Missing required product fields' }, { status: 400 });
    }

    const existingProduct = await db.get<Product>('SELECT imageUrl FROM products WHERE id = ?', params.productId);
    if (existingProduct) {
      oldDbImageUrl = existingProduct.imageUrl; // This path is relative to 'uploads', e.g., "products/image.jpg"
    }

    // If productData.imageUrl comes from client as empty string, it means "remove image".
    // If it's "PENDING_UPLOAD", it means a new file was selected on client, but actual path is not yet known.
    // If it's an existing path (e.g. "products/someimage.jpg"), it means client wants to keep it or it's unchanged.
    let imageUrlToStoreInDb = productData.imageUrl;
    if (productData.imageUrl === '') {
        imageUrlToStoreInDb = null; // Store NULL in DB if image is removed.
    }
    // If imageUrl is 'PENDING_UPLOAD', we don't change DB path yet; image route will update it.
    // So, if PENDING_UPLOAD, we use the oldDbImageUrl for this PUT operation to avoid clearing it prematurely.
    else if (productData.imageUrl === 'PENDING_UPLOAD') {
        imageUrlToStoreInDb = oldDbImageUrl;
    }
    // Otherwise, imageUrlToStoreInDb is what client sent (an existing path or new path if already uploaded separately, though current flow is via image route)


    const result = await db.run(
      'UPDATE products SET name = ?, price = ?, quantityInStock = ?, sku = ?, expiryDate = ?, imageUrl = ?, category = ?, isDemandNoticeProduct = ?, lowStockThreshold = ?, lowStockPrice = ? WHERE id = ?',
      productData.name, productData.price, productData.quantityInStock, productData.sku,
      productData.expiryDate, imageUrlToStoreInDb, productData.category, productData.isDemandNoticeProduct ? 1 : 0,
      productData.lowStockThreshold, productData.lowStockPrice,
      params.productId
    );

    if (result.changes === 0) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: 'Product not found or no changes made' }, { status: 404 });
    }

    // Delete old physical image file if imageUrl in DB changed and was not null
    if (oldDbImageUrl && oldDbImageUrl !== imageUrlToStoreInDb && imageUrlToStoreInDb !== 'PENDING_UPLOAD') {
      const oldImageFullPath = path.join(UPLOADS_BASE_DIR, oldDbImageUrl); // Construct full path
      try {
        await fs.access(oldImageFullPath); // Check if file exists
        await fs.unlink(oldImageFullPath);
        console.log(`[API Product PUT] Deleted old image file: ${oldImageFullPath}`);
      } catch (unlinkError: any) {
        if (unlinkError.code === 'ENOENT') {
          console.warn(`[API Product PUT] Old image file not found for deletion: ${oldImageFullPath}`);
        } else {
          console.error(`[API Product PUT] Error deleting old image file ${oldImageFullPath}:`, unlinkError);
        }
      }
    }

    await db.run('COMMIT'); 

    const updatedProductAfterCommit = await db.get<Product>('SELECT * FROM products WHERE id = ?', params.productId);
    if (updatedProductAfterCommit) {
        const relatedNoticesRaw = await db.all(
            'SELECT * FROM demand_notices WHERE productId = ? AND status IN (?, ?, ?, ?, ?)',
            updatedProductAfterCommit.id,
            'awaiting_stock',
            'pending_review', 
            'partial_stock_available',
            'full_stock_available', 
            'customer_notified_stock' 
        );
        const relatedNotices: DemandNotice[] = relatedNoticesRaw.map(parseDemandNoticeJSONFields);

        for (const notice of relatedNotices) {
            let newCalculatedStatus: DemandNotice['status'] = notice.status;
            if (updatedProductAfterCommit.quantityInStock >= notice.quantityRequested) {
                newCalculatedStatus = 'full_stock_available';
            } else if (updatedProductAfterCommit.quantityInStock > 0 && updatedProductAfterCommit.quantityInStock < notice.quantityRequested) {
                newCalculatedStatus = 'partial_stock_available';
            } else { 
                newCalculatedStatus = 'awaiting_stock';
            }
            
            if (newCalculatedStatus !== notice.status || 
                (notice.status === 'pending_review' && (newCalculatedStatus === 'full_stock_available' || newCalculatedStatus === 'partial_stock_available'))) {
                try {
                    await db.run(
                        'UPDATE demand_notices SET status = ?, updatedAt = ? WHERE id = ?',
                        newCalculatedStatus,
                        new Date().toISOString(),
                        notice.id
                    );
                } catch (dnUpdateError) {
                    console.error(`[DB Product Update] Failed to update DN ${notice.id} status:`, dnUpdateError);
                }
            }
        }
    }
    
    const finalProductState = await db.get<Product>('SELECT * FROM products WHERE id = ?', params.productId);
    return NextResponse.json({ success: true, data: finalProductState });

  } catch (error: any) {
    if (db) {
      try { await db.run('ROLLBACK'); } catch (e) { console.error("Product update rollback failed:", e); }
    }
    console.error(`Failed to update product ${params.productId}:`, error);
    let errorMessage = 'Failed to update product';
    if (error.message && error.message.includes('UNIQUE constraint failed: products.sku')) {
      errorMessage = `Product with Product Code ${productData!.sku} already exists.`;
      return NextResponse.json({ success: false, error: errorMessage }, { status: 409 });
    } else if (error.message) {
        errorMessage = error.message;
    }
    return NextResponse.json({ success: false, error: errorMessage }, { status: 500 });
  }
}

export async function DELETE(request: Request, { params }: Params) {
  try {
    const db = await getDb();
     if (!db) {
        console.error(`[API Product DELETE ${params.productId}] Database not available.`);
        return NextResponse.json({ success: false, error: 'Database service temporarily unavailable.' }, { status: 503 });
    }
    const productToDelete = await db.get<Product>('SELECT imageUrl FROM products WHERE id = ?', params.productId);

    if (!productToDelete) {
      return NextResponse.json({ success: false, error: 'Product not found' }, { status: 404 });
    }

    const result = await db.run('DELETE FROM products WHERE id = ?', params.productId);

    if (result.changes === 0) {
      return NextResponse.json({ success: false, error: 'Product not found, no deletion occurred' }, { status: 404 });
    }

    if (productToDelete.imageUrl) {
      // productToDelete.imageUrl is relative to 'uploads', e.g., "products/image.jpg"
      const imageFullPath = path.join(UPLOADS_BASE_DIR, productToDelete.imageUrl);
      try {
        await fs.access(imageFullPath); // Check if file exists
        await fs.unlink(imageFullPath);
        console.log(`[API Product DELETE] Deleted image file: ${imageFullPath}`);
      } catch (unlinkError: any) {
        if (unlinkError.code === 'ENOENT') {
          console.warn(`[API Product DELETE] Image file not found for deletion: ${imageFullPath}`);
        } else {
          console.error(`[API Product DELETE] Error deleting image file ${imageFullPath}:`, unlinkError);
        }
      }
    }

    return NextResponse.json({ success: true, message: 'Product deleted successfully' }, { status: 200 });
  } catch (error) {
    console.error(`Failed to delete product ${params.productId}:`, error);
    return NextResponse.json({ success: false, error: (error as Error).message || 'Failed to delete product' }, { status: 500 });
  }
}
    
