// src/app/api/audits/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, getNextSeriesNumber, parseAuditJSONFields, parseAuditItemJSONFields, parseProductJSONFields, parseUserJSONFields } from '@/lib/server/database';
import type { Audit, AuditItem, AuditItemFormData, User, Product, SeriesId } from '@/types';

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
  const userId = req.headers.get('x-user-id'); 
  if (!userId) return null;
  const db = await getDb();
  if (!db) return null;
  const userRaw = await db.get<User>('SELECT id, username, role, permissions FROM users WHERE id = ?', userId);
  return userRaw ? parseUserJSONFields(userRaw) : null; // Ensure permissions are parsed
}

export async function POST(req: NextRequest) {
  let db;
  try {
    const adminUser = await getAuthenticatedUser(req);
    if (!adminUser || !(adminUser.role === 'admin' || (adminUser.role === 'manager' && (adminUser.permissions || []).includes('manage_audits')))) {
      return NextResponse.json({ error: 'Unauthorized: Only admins or managers with permission can create audits.' }, { status: 403 });
    }

    const body = await req.json();
    const { title, auditorId, storeLocation, items } = body as {
      title: string;
      auditorId: string;
      storeLocation: string;
      items: AuditItemFormData[];
    };

    if (!title || !auditorId || !storeLocation || !items || items.length === 0) {
      return NextResponse.json({ error: 'Missing required fields: title, auditorId, storeLocation, and at least one item are required.' }, { status: 400 });
    }

    db = await getDb();
    if (!db) {
      return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
    }

    await db.run('BEGIN TRANSACTION');

    const newAuditId = await getNextSeriesNumber('audit' as SeriesId, db);
    const now = new Date().toISOString();

    const newAuditData: Omit<Audit, 'items'> = {
      id: newAuditId,
      title,
      adminId: adminUser.id,
      auditorId,
      storeLocation,
      status: 'pending', 
      createdAt: now,
      updatedAt: now,
    };

    await db.run(
      `INSERT INTO audits (id, title, adminId, auditorId, storeLocation, status, createdAt, updatedAt)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        newAuditData.id, newAuditData.title, newAuditData.adminId, newAuditData.auditorId,
        newAuditData.storeLocation, newAuditData.status, newAuditData.createdAt, newAuditData.updatedAt
      ]
    );

    const createdAuditItems: AuditItem[] = [];
    for (const itemData of items) {
      const newAuditItemId = `ai_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
      let currentStock = 0;
      let productIdToStore: string | undefined = itemData.productId;
      let productSkuToStore: string | undefined = itemData.productSku;

      if (itemData.productId && !itemData.isManual) {
        const product = await db.get<Product>('SELECT quantityInStock, sku FROM products WHERE id = ?', itemData.productId);
        if (product) {
          currentStock = product.quantityInStock;
          productSkuToStore = product.sku; 
        } else {
          console.warn(`[API Audit POST] Product ID ${itemData.productId} provided for existing item not found. Defaulting stock to 0.`);
        }
      } else if (itemData.isManual) {
        productIdToStore = undefined; 
      }

      const auditItem: AuditItem = {
        id: newAuditItemId,
        auditId: newAuditId,
        productId: productIdToStore,
        productName: itemData.productName,
        productSku: productSkuToStore,
        currentStock: currentStock,
        createdAt: now,
        updatedAt: now,
      };

      await db.run(
        `INSERT INTO audit_items (id, auditId, productId, productName, productSku, currentStock, createdAt, updatedAt)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          auditItem.id, auditItem.auditId, auditItem.productId, auditItem.productName,
          auditItem.productSku, auditItem.currentStock, auditItem.createdAt, auditItem.updatedAt
        ]
      );
      createdAuditItems.push(auditItem);
    }

    await db.run('COMMIT');

    const createdAudit: Audit = { ...newAuditData, items: createdAuditItems };
    return NextResponse.json({ success: true, data: parseAuditJSONFields(createdAudit) }, { status: 201 });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error('Error creating audit:', error);
    return NextResponse.json({ error: 'Failed to create audit', details: error.message }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  let db;
  try {
    const authenticatedUser = await getAuthenticatedUser(req);
    if (!authenticatedUser) {
        return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 });
    }

    db = await getDb();
    if (!db) {
      return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
    }

    let auditsRaw: any[];
    if (authenticatedUser.role === 'admin' || (authenticatedUser.role === 'manager' && (authenticatedUser.permissions || []).includes('manage_audits'))) {
      auditsRaw = await db.all('SELECT * FROM audits ORDER BY createdAt DESC');
    } else if (authenticatedUser.role === 'auditor') {
      auditsRaw = await db.all('SELECT * FROM audits WHERE auditorId = ? ORDER BY createdAt DESC', authenticatedUser.id);
    } else {
      return NextResponse.json({ success: false, error: 'Forbidden: Insufficient permissions to view audits.' }, { status: 403 });
    }
    
    const audits = auditsRaw.map(parseAuditJSONFields);
    
    // Optionally, fetch and attach items if needed for list view (might be too heavy for just a list)
    // For now, items are fetched when getting a single audit.

    return NextResponse.json({ success: true, data: audits });

  } catch (error: any) {
    console.error('Error fetching audits:', error);
    return NextResponse.json({ success: false, error: 'Failed to fetch audits', details: error.message }, { status: 500 });
  }
}