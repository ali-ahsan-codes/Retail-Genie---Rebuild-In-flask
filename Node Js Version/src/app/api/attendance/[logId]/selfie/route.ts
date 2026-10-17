
// src/app/api/attendance/[logId]/selfie/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { AttendanceLog } from '@/types';
import fs from 'fs/promises';
import path from 'path';

interface Params {
  params: { logId: string };
}

// Base directory for all uploads
const UPLOADS_BASE_DIR = path.join(process.cwd(), 'uploads');

export async function DELETE(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    const logId = params.logId;

    const log = await db.get<AttendanceLog>('SELECT id, selfieImagePath FROM attendance_logs WHERE id = ?', logId);

    if (!log) {
      return NextResponse.json({ success: false, error: 'Attendance log not found' }, { status: 404 });
    }

    if (log.selfieImagePath) {
      // selfieImagePath is stored relative to 'uploads' directory, e.g., "attendance/filename.jpg"
      const fullImagePath = path.join(UPLOADS_BASE_DIR, log.selfieImagePath);
      try {
        await fs.access(fullImagePath); // Check if file exists
        await fs.unlink(fullImagePath);
        console.log(`[API Selfie Delete] Deleted selfie image file: ${fullImagePath}`);
      } catch (unlinkError: any) {
        if (unlinkError.code === 'ENOENT') {
          console.warn(`[API Selfie Delete] Selfie image file not found for deletion: ${fullImagePath}`);
        } else {
          console.error(`[API Selfie Delete] Error deleting selfie image file ${fullImagePath}:`, unlinkError);
        }
      }
    }

    // Clear selfie path from DB
    await db.run('UPDATE attendance_logs SET selfieImagePath = NULL, selfieDataUri = NULL WHERE id = ?', logId);

    return NextResponse.json({ success: true, message: 'Attendance selfie deleted successfully.' });

  } catch (error) {
    console.error(`Failed to delete attendance selfie for log ${params.logId}:`, error);
    return NextResponse.json({ success: false, error: (error as Error).message || 'Failed to delete attendance selfie' }, { status: 500 });
  }
}
