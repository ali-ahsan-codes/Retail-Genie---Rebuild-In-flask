
// src/app/api/cloud/files/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { readCloudMetadata, getAllCloudFilesMetadataForAdmin } from '@/lib/server/cloudStorageUtils';
import { getDb } from '@/lib/server/database';
import type { CloudFileMetadata, User } from '@/types';

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const requestingUserId = searchParams.get('userId');
    const isAdminRequest = searchParams.get('adminView') === 'true'; // Check for admin view flag

    if (!requestingUserId) {
      return NextResponse.json({ success: false, error: 'User ID is required.' }, { status: 400 });
    }

    const db = await getDb();
    if (!db) {
      console.error("[API Cloud Files GET] Database is unavailable.");
      return NextResponse.json({ success: false, error: 'Database service temporarily unavailable.' }, { status: 503 });
    }

    const requestingUser = await db.get<User>('SELECT id, username, role, permissions FROM users WHERE id = ?', requestingUserId);
    if (!requestingUser) {
        return NextResponse.json({ success: false, error: 'Requesting user not found.' }, { status: 403 });
    }
    
    let filesToReturn: (CloudFileMetadata & { ownerUsername?: string })[] = [];

    if (isAdminRequest && (requestingUser.role === 'admin' || (requestingUser.role === 'manager' && (requestingUser.permissions || []).includes('manage_cloud_files')))) {
      // Admin/Manager with permission fetching all files
      const allFiles = await getAllCloudFilesMetadataForAdmin();
      const allUsernames = new Map<string, string>();
      const usersFromDb = await db.all<{id: string, username: string}>('SELECT id, username FROM users');
      usersFromDb.forEach(u => allUsernames.set(u.id, u.username));

      filesToReturn = allFiles.map(file => ({
        ...file,
        ownerUsername: allUsernames.get(file.userId) || 'Unknown Owner'
      }));
      console.log(`[API Cloud Files GET] Admin request for user ${requestingUserId}. Returning ${filesToReturn.length} total files.`);

    } else {
      // Regular user fetching their own files
      const ownedFiles = await readCloudMetadata(requestingUserId);
      filesToReturn = ownedFiles.map(file => ({
        ...file,
        ownerUsername: requestingUser.username // They are the owner
      }));
      console.log(`[API Cloud Files GET] Regular request for user ${requestingUserId}. Returning ${filesToReturn.length} owned files.`);
    }
    
    filesToReturn.sort((a, b) => new Date(b.upload_timestamp).getTime() - new Date(a.upload_timestamp).getTime());

    return NextResponse.json({ success: true, files: filesToReturn });

  } catch (error: any) {
    console.error('[API Cloud Files GET] Error processing request:', error);
    return NextResponse.json({ success: false, error: 'Failed to retrieve cloud file list.', details: error.message }, { status: 500 });
  }
}
