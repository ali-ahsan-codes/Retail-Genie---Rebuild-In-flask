
// src/app/api/audits/[auditId]/items/[auditItemId]/evidence/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { promises as fs } from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

// New upload directory structure
const AUDITS_UPLOADS_BASE_DIR = path.join(process.cwd(), 'uploads', 'audits');
const AUDIT_EVIDENCE_UPLOAD_DIR = path.join(AUDITS_UPLOADS_BASE_DIR, 'item_images');

async function ensureUploadDirExists() {
  try {
    await fs.access(AUDIT_EVIDENCE_UPLOAD_DIR);
  } catch (error) {
    try {
      await fs.mkdir(AUDIT_EVIDENCE_UPLOAD_DIR, { recursive: true });
      console.log(`[API Audit Evidence] Created directory: ${AUDIT_EVIDENCE_UPLOAD_DIR}`);
    } catch (mkdirError: any) {
      console.error(`[API Audit Evidence] Critical error creating upload directory ${AUDIT_EVIDENCE_UPLOAD_DIR}:`, mkdirError);
      throw new Error(`Failed to create required upload directory for audit evidence: ${mkdirError.message}`);
    }
  }
}

export async function POST(
  request: NextRequest, 
  { params }: { params: { auditId: string; auditItemId: string } }
) {
  try {
    await ensureUploadDirExists();

    const formData = await request.formData();
    const fileType = formData.get('type') as 'image' | 'video' | null; 
    const file = formData.get('file') as File | null;
    
    if (!fileType || !file) {
      return NextResponse.json(
        { success: false, error: 'Missing required fields: type and file are required.' },
        { status: 400 }
      );
    }
    if (fileType !== 'image' && fileType !== 'video') {
         return NextResponse.json(
        { success: false, error: 'Invalid file type. Must be "image" or "video".' },
        { status: 400 }
      );
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    const originalFilename = file.name;
    const fileExtension = (path.extname(originalFilename) || (fileType === 'image' ? '.jpg' : '.mp4')).toLowerCase();
    
    const filenamePrefix = fileType === 'image' ? 'audit_item_img' : 'audit_item_vid';
    const uniqueFileName = `${filenamePrefix}_${params.auditId.substring(0,4)}_${params.auditItemId.substring(0,4)}_${Date.now()}${fileExtension}`;
    
    const filePathOnDisk = path.join(AUDIT_EVIDENCE_UPLOAD_DIR, uniqueFileName);
    
    await fs.writeFile(filePathOnDisk, buffer);
    
    // This path is relative to the 'uploads' directory root for storage/API use.
    const relativeDbPath = `audits/item_images/${uniqueFileName}`; 
    
    console.log(`[API Audit Evidence] Uploaded evidence file for audit ${params.auditId}, item ${params.auditItemId}: ${relativeDbPath}`);

    return NextResponse.json({ 
      success: true, 
      message: 'Evidence file uploaded. Path will be associated when count is saved.',
      filePath: relativeDbPath, 
      type: fileType
    });

  } catch (error: any) {
    console.error(`[API Audit Evidence] Error uploading evidence for audit ${params.auditId}, item ${params.auditItemId}:`, error);
    return NextResponse.json(
      { success: false, error: 'Internal server error during evidence upload.', details: error.message },
      { status: 500 }
    );
  }
}

