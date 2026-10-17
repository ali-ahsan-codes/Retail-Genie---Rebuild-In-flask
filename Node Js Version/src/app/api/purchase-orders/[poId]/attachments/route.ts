// src/app/api/purchase-orders/[poId]/attachments/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import { promises as fs } from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import type { User, POAttachment } from '@/types';

const PO_ATTACHMENTS_DIR = path.join(process.cwd(), 'uploads', 'scm', 'po_attachments');

async function ensureUploadsDirExists(poId: string): Promise<string> {
  const dir = path.join(PO_ATTACHMENTS_DIR, poId);
  try {
    await fs.access(dir);
  } catch {
    await fs.mkdir(dir, { recursive: true });
  }
  return dir;
}

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
    const userId = req.headers.get('x-user-id');
    if (!userId) return null;
    const db = await getDb();
    if (!db) return null;
    return db.get<User>('SELECT * FROM users WHERE id = ?', userId);
}

export async function POST(req: NextRequest, { params }: { params: { poId: string } }) {
  const { poId } = params;
  let db;

  try {
    const user = await getAuthenticatedUser(req);
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const formData = await req.formData();
    const files = formData.getAll('files') as File[];

    if (!files || files.length === 0) {
      return NextResponse.json({ error: 'No files provided.' }, { status: 400 });
    }

    db = await getDb();
    if (!db) {
      return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
    }

    const poDir = await ensureUploadsDirExists(poId);
    const createdAttachments: POAttachment[] = [];
    
    await db.run('BEGIN TRANSACTION');

    for (let i = 0; i < files.length; i++) {
        const file = files[i];

        const attachmentId = uuidv4();
        const fileExtension = path.extname(file.name) || '.bin';
        const savedFileName = `${attachmentId}${fileExtension}`;
        const filePathOnDisk = path.join(poDir, savedFileName);

        const buffer = Buffer.from(await file.arrayBuffer());
        await fs.writeFile(filePathOnDisk, buffer);

        const relativeDbPath = `scm/po_attachments/${poId}/${savedFileName}`;

        const newAttachment: POAttachment = {
            id: attachmentId,
            po_id: poId,
            file_path: relativeDbPath,
            original_name: file.name,
            notes: '', // Notes field removed from UI
            uploaded_at: new Date().toISOString(),
            uploaded_by_id: user.id,
            type: 'other' // General attachments are 'other'
        };

        await db.run(
            'INSERT INTO po_attachments (id, po_id, file_path, original_name, notes, type, uploaded_at, uploaded_by_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            [newAttachment.id, newAttachment.po_id, newAttachment.file_path, newAttachment.original_name, newAttachment.notes, newAttachment.type, newAttachment.uploaded_at, newAttachment.uploaded_by_id]
        );
        
        createdAttachments.push(newAttachment);
    }
    
    // Also update the main PO's updatedAt timestamp
    await db.run('UPDATE purchase_orders SET updatedAt = ? WHERE id = ?', [new Date().toISOString(), poId]);

    await db.run('COMMIT');

    return NextResponse.json({ success: true, data: createdAttachments }, { status: 201 });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error(`Error uploading attachments for PO ${poId}:`, error);
    return NextResponse.json({ error: 'Failed to upload attachments', details: error.message }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
    let db;
    try {
        const user = await getAuthenticatedUser(req);
        if (!user) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }

        const { searchParams } = new URL(req.url);
        const attachmentId = searchParams.get('id');

        if (!attachmentId) {
            return NextResponse.json({ error: 'Attachment ID is required.' }, { status: 400 });
        }
        
        db = await getDb();
        if (!db) {
            return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
        }

        const attachment = await db.get<POAttachment>('SELECT * FROM po_attachments WHERE id = ?', attachmentId);

        if (!attachment) {
            return NextResponse.json({ error: 'Attachment not found' }, { status: 404 });
        }
        
        const filePathOnDisk = path.join(process.cwd(), 'uploads', attachment.file_path);
        
        await fs.unlink(filePathOnDisk).catch(err => {
            if (err.code !== 'ENOENT') { // Don't throw if file is already gone
                throw err;
            }
            console.warn(`File not found for deletion, but proceeding to delete DB record: ${filePathOnDisk}`);
        });

        await db.run('DELETE FROM po_attachments WHERE id = ?', attachmentId);
        
        return NextResponse.json({ success: true, message: 'Attachment deleted successfully.' });

    } catch (error: any) {
        console.error('Error deleting attachment:', error);
        return NextResponse.json({ error: 'Failed to delete attachment', details: error.message }, { status: 500 });
    }
}
