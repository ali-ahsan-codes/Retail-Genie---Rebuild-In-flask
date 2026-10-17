
// src/app/api/products/image/route.ts
import { NextRequest, NextResponse } from 'next/server'
import path from 'path'
import { promises as fs } from 'fs' 
import { getDb } from '@/lib/server/database'

// Define directory paths relative to project root
const UPLOADS_BASE_DIR = path.join(process.cwd(), 'uploads');
const PRODUCTS_UPLOADS_DIR = path.join(UPLOADS_BASE_DIR, 'products');


async function ensureUploadDirExists() {
  try {
    await fs.access(PRODUCTS_UPLOADS_DIR);
  } catch (error) {
    try {
      await fs.mkdir(PRODUCTS_UPLOADS_DIR, { recursive: true });
      console.log(`[API Product Img Upload] Created directory: ${PRODUCTS_UPLOADS_DIR}`);
    } catch (mkdirError) {
      console.error(`[API Product Img Upload] Critical error creating upload directory ${PRODUCTS_UPLOADS_DIR}:`, mkdirError);
      throw new Error(`Failed to create required upload directory.`);
    }
  }
}


export async function POST(request: NextRequest) {
  try {
    await ensureUploadDirExists(); 

    const formData = await request.formData();
    const image = formData.get('image') as File | null;
    const productId = formData.get('product_id') as string | null;
    const sku = formData.get('sku') as string | null; 

    if (!image || !productId || !sku) {
      return NextResponse.json(
        { error: 'Missing required fields: image, product_id, and sku are required.' },
        { status: 400 }
      );
    }

    const timestamp = Date.now();
    const originalExt = image.name.split('.').pop() || 'bin';
    const safeExt = ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(originalExt.toLowerCase()) ? originalExt.toLowerCase() : 'bin';
    const filename = `${productId}_${timestamp}.${safeExt}`;
    const filePathOnDisk = path.join(PRODUCTS_UPLOADS_DIR, filename); // Full path for saving

    // Path to be stored in DB - relative to the 'uploads' directory
    const relativeDbPath = `products/${filename}`; 

    const buffer = Buffer.from(await image.arrayBuffer());
    await fs.writeFile(filePathOnDisk, buffer);
    console.log(`[API Product Img Upload] Image saved to disk: ${filePathOnDisk}`);

    const db = await getDb();
    await db.run(
      `UPDATE products SET imageUrl = ? WHERE id = ?`,
      relativeDbPath, // Store the new relative path
      productId
    );
    console.log(`[API Product Img Upload] Product ${productId} imageUrl updated in DB to ${relativeDbPath}`);

    // The public_url for client consumption will be via the /api/uploads route
    const apiUrlForImage = `/api/uploads/${relativeDbPath}`;

    return NextResponse.json({ success: true, public_url: apiUrlForImage, db_path: relativeDbPath, filename: filename });
  } catch (error: any) {
    console.error('[API Product Img Upload] Image upload failed:', error.message, error.stack);
    return NextResponse.json(
      { error: 'Internal server error during image upload.', details: error.message },
      { status: 500 }
    );
  }
}

export async function GET(request: NextRequest) {
  return NextResponse.json(
    { message: 'Direct image metadata querying is no longer supported. Image URLs are in product data and served via /api/uploads.' },
    { status: 404 }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      'Allow': 'POST, OPTIONS', // Only POST is primarily used now for upload
      'Access-Control-Allow-Origin': '*', 
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    },
  });
}
