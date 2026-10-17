
// src/app/api/audits/[auditId]/start/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseAuditJSONFields, parseUserJSONFields, parseAuditItemJSONFields } from '@/lib/server/database';
import type { Audit, User } from '@/types';
import fs from 'fs/promises';
import path from 'path';

// New upload directory structure
const AUDITS_UPLOADS_BASE_DIR = path.join(process.cwd(), 'uploads', 'audits');
const AUDIT_SELFIE_DIR_SPECIFIC = path.join(AUDITS_UPLOADS_BASE_DIR, 'selfies');

async function ensureUploadDirExists() {
  try {
    await fs.access(AUDIT_SELFIE_DIR_SPECIFIC);
    console.log(`[API Audit Start] Upload directory already exists: ${AUDIT_SELFIE_DIR_SPECIFIC}`);
  } catch (error) {
    try {
      await fs.mkdir(AUDIT_SELFIE_DIR_SPECIFIC, { recursive: true });
      console.log(`[API Audit Start] Created directory: ${AUDIT_SELFIE_DIR_SPECIFIC}`);
    } catch (mkdirError: any) {
      console.error(`[API Audit Start] Critical error creating upload directory ${AUDIT_SELFIE_DIR_SPECIFIC}:`, mkdirError);
      throw new Error(`Failed to create required upload directory for audit selfies: ${mkdirError.message}`);
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
  params: { auditId: string };
}

export async function POST(req: NextRequest, { params }: Params) {
  let db;
  try {
    const { auditId } = params;
    const authenticatedUser = await getAuthenticatedUser(req);

    if (!authenticatedUser || authenticatedUser.role !== 'auditor') {
      return NextResponse.json({ success: false, error: 'Unauthorized: Only assigned auditors can start an audit.' }, { status: 403 });
    }

    const formData = await req.formData();
    const selfieFile = formData.get('selfie') as File | null;


    if (!selfieFile) {
      return NextResponse.json({ success: false, error: 'Selfie image file is required to start the audit.' }, { status: 400 });
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

    if (audit.status !== 'pending') {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: `Audit cannot be started. Current status: ${audit.status}.` }, { status: 400 });
    }

    await ensureUploadDirExists();
    let relativeDbSelfiePath: string | undefined = undefined;

    const fileExtension = (path.extname(selfieFile.name) || '.jpg').toLowerCase(); 
    const filename = `audit_selfie_${auditId}_${authenticatedUser.id}_${Date.now()}${fileExtension}`;
    
    const filePathOnDisk = path.join(AUDIT_SELFIE_DIR_SPECIFIC, filename);

    const buffer = Buffer.from(await selfieFile.arrayBuffer());
    await fs.writeFile(filePathOnDisk, buffer);
    relativeDbSelfiePath = `audits/selfies/${filename}`; // Relative path for DB
    console.log(`[API Audit Start] Auditor selfie saved to: ${filePathOnDisk}, DB path will be: ${relativeDbSelfiePath}`);


    const now = new Date().toISOString();
    await db.run(
      'UPDATE audits SET status = ?, startedAt = ?, auditorSelfiePath = ?, updatedAt = ? WHERE id = ?',
      'in_progress',
      now,
      relativeDbSelfiePath,
      now,
      auditId
    );

    await db.run('COMMIT');

    const updatedAuditRaw = await db.get('SELECT * FROM audits WHERE id = ?', auditId);
    if (!updatedAuditRaw) {
        console.error(`[API Audit Start] CRITICAL: Audit ${auditId} not found after supposedly successful start and commit.`);
        return NextResponse.json({ success: false, error: 'Failed to retrieve updated audit after starting. Audit may have started.' }, { status: 500 });
    }
    const updatedAudit = parseAuditJSONFields(updatedAuditRaw);
    const itemsRaw = await db.all('SELECT * FROM audit_items WHERE auditId = ? ORDER BY createdAt ASC', auditId);
    updatedAudit.items = itemsRaw.map(parseAuditItemJSONFields);


    return NextResponse.json({ success: true, data: updatedAudit });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in audit start:", e));
    console.error(`[API Audit Start CATCH_BLOCK] Error starting audit ${params.auditId}:`, error);
    const detailMessage = (error && typeof error.message === 'string') ? error.message : 'An internal server error occurred during audit start.';
    return NextResponse.json({ success: false, error: 'Audit Start API Error', details: detailMessage }, { status: 500 });
  }
}
    
