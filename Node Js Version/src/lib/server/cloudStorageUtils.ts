// src/lib/server/cloudStorageUtils.ts
import { promises as fs } from 'fs';
import path from 'path';
import type { CloudFileMetadata } from '@/types';
import { v4 as uuidv4 } from 'uuid';

// --- User-specific Cloud Storage ---
const CLOUD_STORAGE_BASE_DIR = path.join(process.cwd(), 'uploads', 'cloud');

function getUserCloudDir(userId: string): string {
  if (!userId || typeof userId !== 'string' || userId.trim() === '') {
    throw new Error('Valid userId is required for user-specific cloud path.');
  }
  const sanitizedUserId = userId.replace(/[^a-zA-Z0-9_-]/g, '');
  if (sanitizedUserId !== userId) {
    console.warn(`[CloudStorageUtils] userId '${userId}' was sanitized to '${sanitizedUserId}' for path safety.`);
  }
  if (!sanitizedUserId) {
    throw new Error('Sanitized userId is empty, cannot create user cloud path.');
  }
  return path.join(CLOUD_STORAGE_BASE_DIR, sanitizedUserId);
}

function getUserMetadataFilePath(userId: string): string {
  return path.join(getUserCloudDir(userId), 'cloud_files_metadata.ndjson');
}

export function getUserDocumentsDir(userId: string): string {
  return path.join(getUserCloudDir(userId), 'documents');
}

export function getUserImagesDir(userId: string): string {
  return path.join(getUserCloudDir(userId), 'images');
}

async function ensureUserMetadataFileExists(userId: string): Promise<void> {
  const userMetadataFilePath = getUserMetadataFilePath(userId);
  const userDir = path.dirname(userMetadataFilePath);
  try {
    await fs.access(userDir);
  } catch (error) {
    await fs.mkdir(userDir, { recursive: true });
  }
  try {
    await fs.access(userMetadataFilePath);
  } catch (error) {
    await fs.writeFile(userMetadataFilePath, '');
    console.log(`[CloudStorageUtils] Created metadata file for user ${userId}: ${userMetadataFilePath}`);
  }
}

export async function readCloudMetadata(userId: string): Promise<CloudFileMetadata[]> {
  await ensureUserMetadataFileExists(userId);
  const userMetadataFilePath = getUserMetadataFilePath(userId);
  try {
    const fileContent = await fs.readFile(userMetadataFilePath, 'utf-8');
    if (!fileContent.trim()) {
      return [];
    }
    return fileContent
      .trim()
      .split('\n')
      .map(line => {
        try {
          const entry = JSON.parse(line) as CloudFileMetadata;
          if (!entry.userId) { 
            entry.userId = userId;
          }
          if (entry.public_url && !entry.public_url.startsWith('cloud/')) {
            entry.public_url = `cloud/${userId}/${entry.path}`;
          }
          return entry;
        } catch(e) {
          console.error(`[CloudStorageUtils] Failed to parse line in metadata for user ${userId}: "${line.substring(0,100)}..."`, e);
          return null;
        }
      })
      .filter(entry => entry !== null) as CloudFileMetadata[];
  } catch (error) {
    console.error(`[CloudStorageUtils] Error reading metadata file for user ${userId}:`, error);
    return [];
  }
}

export async function appendCloudMetadataEntry(userId: string, entry: Omit<CloudFileMetadata, 'file_id' | 'userId'> & {file_id?: string}): Promise<CloudFileMetadata> {
  await ensureUserMetadataFileExists(userId);
  const userMetadataFilePath = getUserMetadataFilePath(userId);
  
  const publicUrlForDb = `cloud/${userId}/${entry.path}`;

  const newEntry: CloudFileMetadata = {
    ...entry,
    file_id: entry.file_id || uuidv4(),
    userId: userId,
    public_url: publicUrlForDb,
  };
  const entryString = JSON.stringify(newEntry) + '\n';
  try {
    await fs.appendFile(userMetadataFilePath, entryString);
    return newEntry;
  } catch (error) {
    console.error(`[CloudStorageUtils] Error appending to metadata file for user ${userId}:`, error);
    throw error;
  }
}

async function writeCloudMetadata(userId: string, metadataArray: CloudFileMetadata[]): Promise<void> {
  await ensureUserMetadataFileExists(userId);
  const userMetadataFilePath = getUserMetadataFilePath(userId);
  const ndjsonString = metadataArray.map(entry => JSON.stringify(entry)).join('\n') + (metadataArray.length > 0 ? '\n' : '');
  try {
    await fs.writeFile(userMetadataFilePath, ndjsonString, 'utf-8');
  } catch (error) {
    console.error(`[CloudStorageUtils] Error writing metadata file for user ${userId}:`, error);
    throw error;
  }
}

export async function updateCloudMetadataEntry(ownerUserId: string, fileId: string, newNotes: string): Promise<CloudFileMetadata | null> {
  const allMetadata = await readCloudMetadata(ownerUserId);
  let updatedEntry: CloudFileMetadata | null = null;
  const updatedMetadata = allMetadata.map(entry => {
    if (entry.file_id === fileId && entry.userId === ownerUserId) {
      updatedEntry = { ...entry, notes: newNotes, upload_timestamp: new Date().toISOString() };
      return updatedEntry;
    }
    return entry;
  });

  if (updatedEntry) {
    await writeCloudMetadata(ownerUserId, updatedMetadata);
    return updatedEntry;
  }
  console.warn(`[CloudStorageUtils] updateCloudMetadataEntry: File ${fileId} not found for owner ${ownerUserId}.`);
  return null;
}

export async function deleteCloudMetadataEntry(userId: string, fileId: string): Promise<boolean> {
  const allMetadata = await readCloudMetadata(userId);
  const initialLength = allMetadata.length;
  const filteredMetadata = allMetadata.filter(entry => !(entry.file_id === fileId && entry.userId === userId));

  if (initialLength === filteredMetadata.length) {
    console.warn(`[CloudStorageUtils] deleteCloudMetadataEntry: File ${fileId} not found in metadata for user ${userId}. No deletion performed.`);
    return false;
  }

  await writeCloudMetadata(userId, filteredMetadata);
  console.log(`[CloudStorageUtils] Successfully deleted metadata for file ${fileId} for user ${userId}.`);
  return true;
}

export async function ensureUserCloudUploadDirsExist(userId: string) {
  const userDocsDir = getUserDocumentsDir(userId);
  const userImgsDir = getUserImagesDir(userId);
  try {
    await fs.access(userDocsDir);
  } catch {
    await fs.mkdir(userDocsDir, { recursive: true });
    console.log(`[CloudStorageUtils] Created documents directory for user ${userId}: ${userDocsDir}`);
  }
  try {
    await fs.access(userImgsDir);
  } catch {
    await fs.mkdir(userImgsDir, { recursive: true });
    console.log(`[CloudStorageUtils] Created images directory for user ${userId}: ${userImgsDir}`);
  }
}

export async function getAllCloudFilesMetadataForAdmin(): Promise<CloudFileMetadata[]> {
  const allFiles: CloudFileMetadata[] = [];
  console.log(`[CloudStorageUtils ADM] Starting to scan for all user cloud files in: ${CLOUD_STORAGE_BASE_DIR}`);
  try {
    const userDirEntries = await fs.readdir(CLOUD_STORAGE_BASE_DIR, { withFileTypes: true });
    console.log(`[CloudStorageUtils ADM] Found ${userDirEntries.length} entries in CLOUD_STORAGE_BASE_DIR.`);

    for (const userDirEnt of userDirEntries) {
      if (userDirEnt.isDirectory()) {
        const userId = userDirEnt.name; 
        console.log(`[CloudStorageUtils ADM] Processing directory for user: ${userId}`);
        try {
          const userMetadata = await readCloudMetadata(userId);
          console.log(`[CloudStorageUtils ADM] Read ${userMetadata.length} metadata entries for user ${userId}.`);
          const filesWithCorrectedUserId = userMetadata.map(file => ({
            ...file,
            userId: userId 
          }));
          allFiles.push(...filesWithCorrectedUserId);
        } catch (userMetaError) {
          console.error(`[CloudStorageUtils ADM] Error reading metadata for user ${userId}:`, userMetaError);
        }
      } else {
        console.log(`[CloudStorageUtils ADM] Skipping non-directory entry: ${userDirEnt.name}`);
      }
    }
  } catch (error) {
    console.error(`[CloudStorageUtils ADM] Error reading CLOUD_STORAGE_BASE_DIR for admin fetch:`, error);
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') {
        try {
            await fs.mkdir(CLOUD_STORAGE_BASE_DIR, { recursive: true });
            console.log(`[CloudStorageUtils ADM] Created CLOUD_STORAGE_BASE_DIR as it was missing: ${CLOUD_STORAGE_BASE_DIR}`);
        } catch (mkdirError) {
            console.error(`[CloudStorageUtils ADM] Critical error creating CLOUD_STORAGE_BASE_DIR ${CLOUD_STORAGE_BASE_DIR}:`, mkdirError);
        }
    }
  }
  console.log(`[CloudStorageUtils ADM] Finished scan. Total files found for admin view: ${allFiles.length}`);
  return allFiles;
}

// --- SCM Document Management ---
const SCM_UPLOADS_BASE_DIR = path.join(process.cwd(), 'uploads', 'scm');

async function ensureScmUploadsDirExists(subDir: string): Promise<void> {
  try {
    await fs.access(subDir);
  } catch (error) {
    await fs.mkdir(subDir, { recursive: true });
    console.log(`[SCM StorageUtils] Created SCM directory: ${subDir}`);
  }
}

/**
 * Uploads a document related to a Supplier or Purchase Order.
 * @param entityType 'supplier' or 'po'
 * @param entityId The ID of the supplier or purchase order.
 * @param file The file object to upload.
 * @param subfolder 'contracts' or 'invoices' etc.
 * @returns The relative path to the stored file, suitable for DB storage.
 */
export async function uploadScmDocument(
  entityType: 'supplier' | 'po' | 'storage',
  entityId: string,
  subfolder: 'documents' | 'po_invoices' | 'storage_evidence',
  file: File
): Promise<string> {
  const dirPath = path.join(SCM_UPLOADS_BASE_DIR, subfolder, entityId);
  await ensureScmUploadsDirExists(dirPath);
  
  const fileExtension = path.extname(file.name) || '.bin';
  const savedFileName = `${Date.now()}_${uuidv4().substring(0, 8)}${fileExtension}`;
  const filePathOnDisk = path.join(dirPath, savedFileName);
  
  const buffer = Buffer.from(await file.arrayBuffer());
  await fs.writeFile(filePathOnDisk, buffer);
  
  // Return the path relative to the 'uploads' directory
  const relativeDbPath = `scm/${subfolder}/${entityId}/${savedFileName}`;
  console.log(`[SCM StorageUtils] Document saved to ${filePathOnDisk}, DB path: ${relativeDbPath}`);
  return relativeDbPath;
}
