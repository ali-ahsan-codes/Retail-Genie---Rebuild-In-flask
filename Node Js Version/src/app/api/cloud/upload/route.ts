
// src/app/api/cloud/upload/route.ts
import { NextRequest, NextResponse } from 'next/server';
import path from 'path';
import { promises as fs } from 'fs';
import { v4 as uuidv4 } from 'uuid';
import { 
  appendCloudMetadataEntry, 
  ensureUserCloudUploadDirsExist, 
  getUserDocumentsDir, 
  getUserImagesDir 
} from '@/lib/server/cloudStorageUtils';
import type { CloudFileMetadata } from '@/types';

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get('file') as File | null;
    const notes = formData.get('notes') as string | null;
    const userId = formData.get('userId') as string | null;

    if (!file) {
      return NextResponse.json({ error: 'No file provided.' }, { status: 400 });
    }
    if (!userId) {
      return NextResponse.json({ error: 'User ID is required for cloud upload.' }, { status: 400 });
    }

    await ensureUserCloudUploadDirsExist(userId); 

    const fileBuffer = Buffer.from(await file.arrayBuffer());
    const originalFilename = file.name;
    const fileType = file.type;
    const fileSize = file.size;

    const isImageFile = fileType.startsWith('image/');
    const userTypeSpecificDir = isImageFile ? getUserImagesDir(userId) : getUserDocumentsDir(userId);
    
    const fileExtension = path.extname(originalFilename) || '';
    const baseFilename = path.basename(originalFilename, fileExtension);
    
    const sanitizedBaseFilename = baseFilename.replace(/[^a-zA-Z0-9_.-]/g, '_');
    const uniqueSavedFilename = `${sanitizedBaseFilename}_${Date.now()}_${uuidv4().substring(0, 6)}${fileExtension}`;
    
    const filePathOnDisk = path.join(userTypeSpecificDir, uniqueSavedFilename);
    
    // Path relative to the user's cloud type directory (documents or images)
    const pathWithinUserTypeDir = uniqueSavedFilename; 
    // Path relative to the 'uploads' directory root, used for API serving and DB storage
    const publicUrlForDb = `cloud/${userId}/${isImageFile ? 'images' : 'documents'}/${uniqueSavedFilename}`;

    await fs.writeFile(filePathOnDisk, fileBuffer);

    const metadataEntry: Omit<CloudFileMetadata, 'file_id' | 'userId'> = {
      original_filename: originalFilename,
      saved_filename: uniqueSavedFilename,
      path: `${isImageFile ? 'images' : 'documents'}/${uniqueSavedFilename}`, // Path relative to user's specific cloud dir (e.g. images/myphoto.jpg)
      public_url: publicUrlForDb, // Path relative to 'uploads' dir, e.g. cloud/userid/images/myphoto.jpg
      file_type: fileType,
      file_size: fileSize,
      upload_timestamp: new Date().toISOString(),
      notes: notes || '',
    };

    const savedMetadata = await appendCloudMetadataEntry(userId, metadataEntry);

    return NextResponse.json({ success: true, metadata: savedMetadata }, { status: 201 });

  } catch (error: any) {
    console.error('[API Cloud Upload] Error uploading file:', error);
    return NextResponse.json({ error: 'File upload failed.', details: error.message }, { status: 500 });
  }
}
