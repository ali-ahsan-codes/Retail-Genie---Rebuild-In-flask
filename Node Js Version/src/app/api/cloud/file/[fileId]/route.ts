
// src/app/api/cloud/file/[fileId]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import path from 'path';
import { promises as fs } from 'fs';
import { 
  readCloudMetadata, 
  updateCloudMetadataEntry, 
  deleteCloudMetadataEntry, 
  getUserDocumentsDir, 
  getUserImagesDir 
} from '@/lib/server/cloudStorageUtils';

interface Params {
  params: { fileId: string };
}

// Helper to get user ID from request
async function getUserIdFromRequest(req: NextRequest): Promise<string | null> {
    if (req.method === 'PUT' || req.method === 'DELETE') {
        try {
            const body = await req.json();
            return body.userId || null;
        } catch (e) {
            // Fallback to query params if body parsing fails or userId not in body
        }
    }
    const { searchParams } = new URL(req.url);
    return searchParams.get('userId');
}


export async function GET(req: NextRequest, { params }: Params) {
  try {
    const { fileId } = params;
    const userId = await getUserIdFromRequest(req);

    if (!userId) {
      return NextResponse.json({ error: 'User ID is required to get file metadata.' }, { status: 400 });
    }

    const userMetadata = await readCloudMetadata(userId);
    // The metadata file now only contains files for that userId, so we only need to match fileId.
    const fileMeta = userMetadata.find(f => f.file_id === fileId); 

    if (!fileMeta) {
      return NextResponse.json({ error: 'File not found for this user.' }, { status: 404 });
    }
    return NextResponse.json({ success: true, data: fileMeta });
  } catch (error: any) {
    console.error(`[API Cloud File GET ${params.fileId}] Error:`, error);
    return NextResponse.json({ error: 'Failed to retrieve file metadata.', details: error.message }, { status: 500 });
  }
}

export async function PUT(req: NextRequest, { params }: Params) { // For updating notes
  let requestBody;
  try {
    requestBody = await req.json() as { notes: string; userId: string };
  } catch (e) {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }
  
  const { fileId } = params;
  const { notes, userId } = requestBody;

  if (!userId) {
    return NextResponse.json({ error: 'User ID is required in the request body to update notes.' }, { status: 400 });
  }
  if (typeof notes !== 'string') {
    return NextResponse.json({ error: 'Invalid notes data.' }, { status: 400 });
  }

  try {
    // updateCloudMetadataEntry now implies ownerUserId through its first param.
    const updatedMetadata = await updateCloudMetadataEntry(userId, fileId, notes);

    if (!updatedMetadata) {
      return NextResponse.json({ error: 'File not found for this user or failed to update notes.' }, { status: 404 });
    }
    return NextResponse.json({ success: true, data: updatedMetadata });
  } catch (error: any) {
    console.error(`[API Cloud File PUT ${fileId}] Error updating notes for user ${userId}:`, error);
    return NextResponse.json({ error: 'Failed to update notes.', details: error.message }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest, { params }: Params) {
  let requestBody;
   try {
    const contentType = req.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
        try {
            requestBody = await req.json() as { userId?: string };
        } catch (e) {
            console.warn("[API Cloud File DELETE] Could not parse JSON body, relying on query param.");
        }
    }
  } catch (e) { /* Ignore if req.json() fails */ }

  const { fileId } = params;
  const { searchParams } = new URL(req.url);
  const userIdFromQuery = searchParams.get('userId');
  const userId = requestBody?.userId || userIdFromQuery;


  if (!userId) {
    return NextResponse.json({ error: 'User ID is required to delete a file.' }, { status: 400 });
  }

  try {
    const allUserMetadata = await readCloudMetadata(userId);
    const fileMetaToDelete = allUserMetadata.find(f => f.file_id === fileId); // userId check is implicit in readCloudMetadata

    if (!fileMetaToDelete) {
      return NextResponse.json({ error: 'File metadata not found for this user, cannot delete.' }, { status: 404 });
    }

    // fileMetaToDelete.path is relative to the user's specific type directory (documents or images)
    // e.g., "documents/report.pdf" or "images/photo.jpg"
    const baseUserTypeDir = fileMetaToDelete.file_type.startsWith('image/') ? getUserImagesDir(userId) : getUserDocumentsDir(userId);
    const physicalFilePath = path.join(baseUserTypeDir, fileMetaToDelete.saved_filename);

    try {
      await fs.unlink(physicalFilePath);
      console.log(`[API Cloud File DELETE] Deleted physical file for user ${userId}: ${physicalFilePath}`);
    } catch (fileError: any) {
      if (fileError.code === 'ENOENT') {
        console.warn(`[API Cloud File DELETE] Physical file not found for user ${userId}, but proceeding to delete metadata: ${physicalFilePath}`);
      } else {
        console.error(`[API Cloud File DELETE] Error deleting physical file ${physicalFilePath} for user ${userId}:`, fileError);
        // Depending on policy, you might want to stop here and not delete metadata if physical file deletion fails
      }
    }

    const metadataDeleted = await deleteCloudMetadataEntry(userId, fileId);
    if (!metadataDeleted) {
      // This means the fileId wasn't found for the userId in the metadata, which should have been caught by fileMetaToDelete check.
      // However, if writeCloudMetadata failed internally, this might be reached.
      return NextResponse.json({ error: 'File metadata found but failed to delete from store for this user.' }, { status: 500 });
    }

    return NextResponse.json({ success: true, message: `File ${fileMetaToDelete.original_filename} and its metadata deleted for user ${userId}.` });
  } catch (error: any) {
    console.error(`[API Cloud File DELETE ${fileId}] Error for user ${userId}:`, error);
    return NextResponse.json({ error: 'Failed to delete file.', details: error.message }, { status: 500 });
  }
}
