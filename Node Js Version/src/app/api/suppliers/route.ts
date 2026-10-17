
// src/app/api/suppliers/route.ts
import { NextResponse, NextRequest } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { Supplier, User } from '@/types';
import { v4 as uuidv4 } from 'uuid';
import fs from 'fs/promises';
import path from 'path';

const SUPPLIER_ATTACHMENTS_DIR = path.join(process.cwd(), 'uploads', 'scm', 'documents');

async function ensureUploadsDirExists(): Promise<void> {
  try {
    await fs.access(SUPPLIER_ATTACHMENTS_DIR);
  } catch {
    await fs.mkdir(SUPPLIER_ATTACHMENTS_DIR, { recursive: true });
  }
}

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
    const userId = req.headers.get('x-user-id');
    if (!userId) return null;
    const db = await getDb();
    if (!db) return null;
    return db.get<User>('SELECT * FROM users WHERE id = ?', userId);
}


// GET all suppliers
export async function GET() {
  try {
    const db = await getDb();
    if (!db) {
      return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    const suppliers = await db.all<Supplier[]>('SELECT * FROM suppliers ORDER BY name');
    return NextResponse.json(suppliers, { status: 200 });
  } catch (error) {
    console.error('Failed to fetch suppliers:', error);
    return NextResponse.json({ message: 'Failed to fetch suppliers', error: (error as Error).message }, { status: 500 });
  }
}

// POST a new supplier
export async function POST(request: NextRequest) {
  let db;
  try {
    await ensureUploadsDirExists();
    const user = await getAuthenticatedUser(request);
    
    db = await getDb();
    if (!db) {
        return NextResponse.json({ message: 'Database service unavailable' }, { status: 503 });
    }
    
    const formData = await request.formData();
    const id = formData.get('id') as string | null;
    const name = formData.get('name') as string;
    const contact_email = formData.get('contact_email') as string | null;
    const phone = formData.get('phone') as string | null;
    const lead_time = formData.get('lead_time') as string | null;
    const notes = formData.get('notes') as string | null;
    const documents = formData.getAll('documents') as File[];

    if (!name) {
      return NextResponse.json({ message: 'Supplier name is required' }, { status: 400 });
    }

    await db.run('BEGIN TRANSACTION');

    const newSupplierId = id || `sup_${Date.now()}`;
    
    if (id) {
        const existing = await db.get('SELECT id FROM suppliers WHERE id = ?', id);
        if (existing) {
            await db.run('ROLLBACK');
            return NextResponse.json({ message: 'Supplier ID already exists.' }, { status: 409 });
        }
    }
    
    const newSupplier: Supplier = {
      id: newSupplierId,
      name,
      contact_email,
      phone,
      lead_time: lead_time ? parseInt(lead_time, 10) : 0,
      notes,
    };

    await db.run(
      'INSERT INTO suppliers (id, name, contact_email, phone, lead_time, notes) VALUES (?, ?, ?, ?, ?, ?)',
      [newSupplier.id, newSupplier.name, newSupplier.contact_email, newSupplier.phone, newSupplier.lead_time, newSupplier.notes]
    );

    // Handle file uploads
    for (const file of documents) {
        const attachmentId = uuidv4();
        const fileExtension = path.extname(file.name) || '.bin';
        const savedFileName = `${newSupplierId}_${attachmentId}${fileExtension}`;
        const filePathOnDisk = path.join(SUPPLIER_ATTACHMENTS_DIR, savedFileName);

        const buffer = Buffer.from(await file.arrayBuffer());
        await fs.writeFile(filePathOnDisk, buffer);

        const relativeDbPath = `scm/documents/${savedFileName}`;
        await db.run(
            'INSERT INTO supplier_attachments (id, supplier_id, file_path, original_name, uploaded_at, uploaded_by_id) VALUES (?, ?, ?, ?, ?, ?)',
            [attachmentId, newSupplierId, relativeDbPath, file.name, new Date().toISOString(), user?.id || null]
        );
    }

    await db.run('COMMIT');

    // Fetch the full supplier object to return
    const createdSupplier = await db.get('SELECT * FROM suppliers WHERE id = ?', newSupplierId);
    
    return NextResponse.json(createdSupplier, { status: 201 });
  } catch (error) {
    if(db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error('Failed to create supplier:', error);
    return NextResponse.json({ message: 'Failed to create supplier', error: (error as Error).message }, { status: 500 });
  }
}
