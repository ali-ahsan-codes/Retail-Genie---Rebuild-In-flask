// src/app/api/audits/[auditId]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseAuditJSONFields, parseAuditItemJSONFields, parseAuditItemCountJSONFields, parseAuditImageJSONFields, parseUserJSONFields } from '@/lib/server/database';
import type { Audit, AuditItem, AuditItemCount, AuditImage, User } from '@/types';

interface Params {
  params: { auditId: string };
}

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
  const userId = req.headers.get('x-user-id');
  if (!userId) return null;
  const db = await getDb();
  if (!db) return null;
  const userRaw = await db.get<User>('SELECT id, username, role, permissions FROM users WHERE id = ?', userId);
  return userRaw ? parseUserJSONFields(userRaw) : null;
}

export async function GET(req: NextRequest, { params }: Params) {
  let db;
  try {
    const { auditId } = params;
    const authenticatedUser = await getAuthenticatedUser(req);
    if (!authenticatedUser) {
      return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 });
    }

    db = await getDb();
    if (!db) {
      return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
    }

    const auditRaw = await db.get('SELECT * FROM audits WHERE id = ?', auditId);
    if (!auditRaw) {
      return NextResponse.json({ success: false, error: 'Audit not found' }, { status: 404 });
    }

    const canView = authenticatedUser.role === 'admin' ||
                    (authenticatedUser.role === 'manager' && (authenticatedUser.permissions || []).includes('manage_audits')) ||
                    (authenticatedUser.role === 'auditor' && auditRaw.auditorId === authenticatedUser.id);

    if (!canView) {
      return NextResponse.json({ success: false, error: 'Forbidden: You do not have permission to view this audit.' }, { status: 403 });
    }
    
    const audit = parseAuditJSONFields(auditRaw);

    const itemsRaw = await db.all<any[]>('SELECT * FROM audit_items WHERE auditId = ? ORDER BY createdAt ASC', auditId);
    const auditItems: AuditItem[] = [];

    for (const itemRaw of itemsRaw) {
      const item = parseAuditItemJSONFields(itemRaw);
      const countsRaw = await db.all<any[]>('SELECT * FROM audit_item_counts WHERE auditItemId = ? ORDER BY createdAt DESC', item.id);
      
      const itemCounts: AuditItemCount[] = [];
      for (const countRaw of countsRaw) {
        const count = parseAuditItemCountJSONFields(countRaw);
        const imagesRaw = await db.all<AuditImage>('SELECT * FROM audit_images WHERE countEventId = ? ORDER BY createdAt ASC', count.id);
        count.images = imagesRaw.map(parseAuditImageJSONFields);
        itemCounts.push(count);
      }
      item.counts = itemCounts;
      auditItems.push(item);
    }
    audit.items = auditItems;

    return NextResponse.json({ success: true, data: audit });

  } catch (error: any) {
    console.error(`Error fetching audit ${params.auditId}:`, error);
    return NextResponse.json({ success: false, error: 'Failed to fetch audit details', details: error.message }, { status: 500 });
  }
}

export async function PUT(req: NextRequest, { params }: Params) {
  return NextResponse.json({ error: 'Method Not Allowed' }, { status: 405 });
}

export async function DELETE(req: NextRequest, { params }: Params) {
  return NextResponse.json({ error: 'Method Not Allowed' }, { status: 405 });
}

