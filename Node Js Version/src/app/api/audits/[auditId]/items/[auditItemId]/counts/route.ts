
// src/app/api/audits/[auditId]/items/[auditItemId]/counts/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseAuditItemCountJSONFields, parseAuditImageJSONFields, parseUserJSONFields } from '@/lib/server/database';
import type { AuditItemCount, AuditImage, User } from '@/types';
import fs from 'fs/promises';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

// New upload directory structure
const AUDITS_UPLOADS_BASE_DIR = path.join(process.cwd(), 'uploads', 'audits');
const AUDIT_ITEM_IMAGES_DIR = path.join(AUDITS_UPLOADS_BASE_DIR, 'item_images');

async function ensureUploadDirExists() {
  try {
    await fs.access(AUDIT_ITEM_IMAGES_DIR);
  } catch (error) {
    try {
      await fs.mkdir(AUDIT_ITEM_IMAGES_DIR, { recursive: true });
      console.log(`[API Audit Item Count] Created directory: ${AUDIT_ITEM_IMAGES_DIR}`);
    } catch (mkdirError: any) {
      console.error(`[API Audit Item Count] Critical error creating upload directory ${AUDIT_ITEM_IMAGES_DIR}:`, mkdirError);
      throw new Error(`Failed to create required upload directory for audit item images: ${mkdirError.message}`);
    }
  }
}

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
  const userId = req.headers.get('x-user-id');
  if (!userId) return null;
  const db = await getDb();
  if (!db) return null;
  const userRaw = await db.get<User>('SELECT id, username, role, permissions FROM users WHERE id = ?', userId);
  return userRaw ? parseUserJSONFields(userRaw) : null;
}

interface Params {
  params: { auditId: string; auditItemId: string };
}

export async function POST(req: NextRequest, { params }: Params) {
  let db;
  try {
    const { auditId, auditItemId } = params;
    const authenticatedUser = await getAuthenticatedUser(req);

    if (!authenticatedUser || authenticatedUser.role !== 'auditor') {
      return NextResponse.json({ success: false, error: 'Unauthorized: Only auditors can record counts.' }, { status: 403 });
    }

    const formData = await req.formData();
    const countStr = formData.get('count') as string | null;
    const notes = formData.get('notes') as string | null;
    const imageFile = formData.get('image') as File | null;

    if (!countStr || isNaN(parseInt(countStr, 10))) {
      return NextResponse.json({ success: false, error: 'Count quantity is required and must be a number.' }, { status: 400 });
    }
    const count = parseInt(countStr, 10);

    db = await getDb();
    if (!db) {
      return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
    }

    await db.run('BEGIN TRANSACTION');

    // Verify audit and item exist and auditor is assigned
    const audit = await db.get('SELECT id, auditorId, status FROM audits WHERE id = ?', auditId);
    if (!audit) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: 'Audit not found.' }, { status: 404 });
    }
    if (audit.auditorId !== authenticatedUser.id) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: 'Forbidden: You are not assigned to this audit.' }, { status: 403 });
    }
    if (audit.status !== 'in_progress') {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: `Cannot record count. Audit status is ${audit.status}.` }, { status: 400 });
    }
    const auditItem = await db.get('SELECT id FROM audit_items WHERE id = ? AND auditId = ?', auditItemId, auditId);
    if (!auditItem) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: 'Audit item not found for this audit.' }, { status: 404 });
    }

    const now = new Date().toISOString();
    const newCountId = `aic_${Date.now()}_${uuidv4().substring(0, 7)}`;

    await db.run(
      'INSERT INTO audit_item_counts (id, auditItemId, count, notes, createdAt) VALUES (?, ?, ?, ?, ?)',
      newCountId,
      auditItemId,
      count,
      notes || null,
      now
    );

    let relativeDbImagePath: string | undefined = undefined;
    let createdAuditImageRecord: AuditImage | undefined = undefined;

    if (imageFile) {
      await ensureUploadDirExists();
      const fileExtension = (path.extname(imageFile.name) || '.jpg').toLowerCase();
      const imageFilename = `audit_item_img_${newCountId}_${Date.now()}${fileExtension}`;
      const imageFilePathOnDisk = path.join(AUDIT_ITEM_IMAGES_DIR, imageFilename);
      
      const buffer = Buffer.from(await imageFile.arrayBuffer());
      await fs.writeFile(imageFilePathOnDisk, buffer);
      relativeDbImagePath = `audits/item_images/${imageFilename}`; // Relative path for DB
      console.log(`[API Audit Item Count] Image saved to: ${imageFilePathOnDisk}, DB path will be: ${relativeDbImagePath}`);

      const newImageId = `aimg_${Date.now()}_${uuidv4().substring(0, 7)}`;
      await db.run(
        'INSERT INTO audit_images (id, countEventId, imagePath, createdAt) VALUES (?, ?, ?, ?)',
        newImageId, newCountId, relativeDbImagePath, now
      );
      createdAuditImageRecord = { id: newImageId, countEventId: newCountId, imagePath: relativeDbImagePath, createdAt: now };
    }

    await db.run('COMMIT');

    const createdCount: AuditItemCount = {
      id: newCountId,
      auditItemId: auditItemId,
      count: count,
      notes: notes || undefined,
      createdAt: now,
      images: createdAuditImageRecord ? [createdAuditImageRecord] : [],
    };

    return NextResponse.json({ success: true, data: createdCount });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in audit item count POST:", e));
    console.error(`[API Audit Item Count POST CATCH_BLOCK] Error recording count for item ${params.auditItemId} in audit ${params.auditId}:`, error);
    const detailMessage = (error && typeof error.message === 'string') ? error.message : 'An internal server error occurred while recording count.';
    return NextResponse.json({ success: false, error: 'Count Record API Error', details: detailMessage }, { status: 500 });
  }
}

export async function GET(req: NextRequest, { params }: Params) {
    return NextResponse.json({ success: false, error: 'Method not implemented yet for listing counts individually.' }, { status: 501 });
}
