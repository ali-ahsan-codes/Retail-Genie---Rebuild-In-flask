
// src/app/api/audits/[auditId]/complete/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseAuditJSONFields, parseUserJSONFields, parseAuditItemJSONFields } from '@/lib/server/database';
import type { Audit, User } from '@/types';

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
  const userId = req.headers.get('x-user-id');
  if (!userId) return null;
  const db = await getDb();
  if (!db) return null;
  const userRaw = await db.get<User>('SELECT id, username, role, permissions FROM users WHERE id = ?', userId);
  return userRaw ? parseUserJSONFields(userRaw) : null;
}

interface Params {
  params: { auditId: string };
}

export async function POST(req: NextRequest, { params }: Params) {
  let db;
  try {
    const { auditId } = params;
    const authenticatedUser = await getAuthenticatedUser(req);

    if (!authenticatedUser || authenticatedUser.role !== 'auditor') {
      return NextResponse.json({ success: false, error: 'Unauthorized: Only assigned auditors can complete an audit.' }, { status: 403 });
    }

    db = await getDb();
    if (!db) {
      return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
    }

    await db.run('BEGIN TRANSACTION');

    const auditRaw = await db.get('SELECT * FROM audits WHERE id = ?', auditId);
    if (!auditRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: 'Audit not found' }, { status: 404 });
    }
    let audit = parseAuditJSONFields(auditRaw);

    if (audit.auditorId !== authenticatedUser.id) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: 'Forbidden: You are not assigned to this audit.' }, { status: 403 });
    }

    if (audit.status !== 'in_progress') {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: `Audit cannot be completed. Current status: ${audit.status}.` }, { status: 400 });
    }

    const now = new Date().toISOString();
    
    // Optional: Calculate finalAuditedQty for each item
    const auditItemsRaw = await db.all('SELECT * FROM audit_items WHERE auditId = ?', auditId);
    for (const itemRaw of auditItemsRaw) {
        const item = parseAuditItemJSONFields(itemRaw);
        const countsResult = await db.get('SELECT SUM(count) as totalCount FROM audit_item_counts WHERE auditItemId = ?', item.id);
        const finalAuditedQty = countsResult?.totalCount || 0;
        await db.run('UPDATE audit_items SET finalAuditedQty = ?, updatedAt = ? WHERE id = ?', finalAuditedQty, now, item.id);
    }
    
    await db.run(
      'UPDATE audits SET status = ?, completedAt = ?, updatedAt = ? WHERE id = ?',
      'completed',
      now,
      now,
      auditId
    );

    await db.run('COMMIT');

    const updatedAuditRaw = await db.get('SELECT * FROM audits WHERE id = ?', auditId);
    if (!updatedAuditRaw) {
        console.error(`[API Audit Complete] CRITICAL: Audit ${auditId} not found after supposedly successful completion and commit.`);
        return NextResponse.json({ success: false, error: 'Failed to retrieve updated audit after completion. Audit may have been completed.' }, { status: 500 });
    }
    const updatedAudit = parseAuditJSONFields(updatedAuditRaw);
    const itemsRaw = await db.all('SELECT * FROM audit_items WHERE auditId = ? ORDER BY createdAt ASC', auditId);
    updatedAudit.items = itemsRaw.map(parseAuditItemJSONFields);
    
    // Re-fetch items with their counts for the response
    for (const item of updatedAudit.items || []) {
        const countsRaw = await db.all('SELECT * FROM audit_item_counts WHERE auditItemId = ? ORDER BY createdAt DESC', item.id);
        item.counts = countsRaw.map(c => ({...c, images: []})); // Simplified for now
    }

    return NextResponse.json({ success: true, data: updatedAudit });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in audit complete:", e));
    console.error(`[API Audit Complete CATCH_BLOCK] Error completing audit ${params.auditId}:`, error);
    const detailMessage = (error && typeof error.message === 'string') ? error.message : 'An internal server error occurred during audit completion.';
    return NextResponse.json({ success: false, error: 'Audit Complete API Error', details: detailMessage }, { status: 500 });
  }
}

    