// src/app/api/uploads/[...path]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { stat } from 'fs/promises'; // Use fs.promises.stat

// Define allowed base directories for security
const ALLOWED_BASE_DIRECTORIES = [
  path.join(process.cwd(), 'uploads'),
  // Add other base directories if needed, e.g., for special system files not in 'uploads'
];

function getMimeType(extension: string): string {
  const types: Record<string, string> = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    gif: 'image/gif',
    webp: 'image/webp',
    svg: 'image/svg+xml',
    mp4: 'video/mp4',
    webm: 'video/webm',
    ogg: 'video/ogg',
    csv: 'text/csv',
    pdf: 'application/pdf',
    txt: 'text/plain',
    json: 'application/json',
    // Add more as needed
  };
  return types[extension.toLowerCase()] || 'application/octet-stream';
}

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  try {
    // Construct the relative path from the params
    const relativePath = params.path.join('/');
    const filePath = path.join(process.cwd(), 'uploads', relativePath);

    // Security Check: Ensure the resolved path is within an allowed directory
    const resolvedFilePath = path.resolve(filePath);
    const isAllowed = ALLOWED_BASE_DIRECTORIES.some(allowedBase => 
      resolvedFilePath.startsWith(path.resolve(allowedBase) + path.sep) || 
      resolvedFilePath === path.resolve(allowedBase)
    );

    if (!isAllowed) {
      console.warn(`[API Uploads GET] Forbidden access attempt to path: ${resolvedFilePath} (resolved from ${relativePath})`);
      return new NextResponse('Forbidden', { status: 403 });
    }
    
    // Check if the file exists using fs.promises.stat
    try {
      const fileStat = await stat(resolvedFilePath);
      if (!fileStat.isFile()) {
        console.warn(`[API Uploads GET] Path is not a file: ${resolvedFilePath}`);
        return new NextResponse('File not found', { status: 404 });
      }
    } catch (err: any) {
      if (err.code === 'ENOENT') {
        console.warn(`[API Uploads GET] File does not exist: ${resolvedFilePath}`);
        return new NextResponse('File not found', { status: 404 });
      }
      console.error(`[API Uploads GET] Error checking file ${resolvedFilePath}:`, err);
      return new NextResponse('Internal Server Error', { status: 500 });
    }

    // Read the file stream
    const fileStream = fs.createReadStream(resolvedFilePath);
    const extension = path.extname(resolvedFilePath).slice(1);
    const contentType = getMimeType(extension);

    // The 'Cache-Control' header is good for production.
    // Consider if you need more granular control for specific file types (e.g., CSVs might change more often).
    return new NextResponse(fileStream as any, { // Type assertion for ReadableStream
      headers: {
        'Content-Type': contentType,
        'Cache-Control': 'public, max-age=31536000, immutable' 
      },
    });

  } catch (error) {
    console.error('[API Uploads GET] Unexpected error:', error);
    return new NextResponse('Internal Server Error', { status: 500 });
  }
}
