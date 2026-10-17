
// src/app/api/attendance/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { AttendanceLog } from '@/types';
import { format, parseISO, startOfDay } from 'date-fns';
import fs from 'fs/promises';
import path from 'path';

// New upload directory structure
const ATTENDANCE_UPLOADS_DIR = path.join(process.cwd(), 'uploads', 'attendance');
console.log(`[API Attendance Init] Resolved ATTENDANCE_UPLOADS_DIR to: ${ATTENDANCE_UPLOADS_DIR}`);

async function ensureUploadDirExists() {
  try {
    await fs.access(ATTENDANCE_UPLOADS_DIR);
    console.log(`[API Attendance] Upload directory already exists: ${ATTENDANCE_UPLOADS_DIR}`);
  } catch (error) {
    try {
      await fs.mkdir(ATTENDANCE_UPLOADS_DIR, { recursive: true });
      console.log(`[API Attendance] Created directory: ${ATTENDANCE_UPLOADS_DIR}`);
    } catch (mkdirError) {
      console.error(`[API Attendance] Critical error creating upload directory ${ATTENDANCE_UPLOADS_DIR}:`, mkdirError);
      throw new Error(`Failed to create required upload directory.`);
    }
  }
}


export async function GET() {
  try {
    const db = await getDb();
    const logs = await db.all<AttendanceLog[]>('SELECT * FROM attendance_logs ORDER BY timestamp DESC');
    return NextResponse.json(logs);
  } catch (error) {
    console.error('Failed to fetch attendance logs:', error);
    return NextResponse.json({ message: 'Failed to fetch attendance logs' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const logData = await request.json() as Omit<AttendanceLog, 'id'>;
    const db = await getDb();

    if (!logData.userId || !logData.timestamp) {
        return NextResponse.json({ message: 'Missing required attendance log fields' }, { status: 400 });
    }
    
    const todayStr = format(startOfDay(parseISO(logData.timestamp)), 'yyyy-MM-dd');
    const existingLog = await db.get(
      "SELECT id FROM attendance_logs WHERE userId = ? AND strftime('%Y-%m-%d', timestamp) = ?",
      logData.userId,
      todayStr
    );

    if (existingLog) {
      return NextResponse.json({ message: 'User already clocked in today' }, { status: 409 });
    }

    const newLogId = `att_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    let relativeDbSelfiePath: string | undefined = undefined;
    let finalSelfieDataUri: string | undefined = logData.selfieDataUri;

    if (logData.method === 'selfie' && logData.selfieDataUri) {
      await ensureUploadDirExists();
      const matches = logData.selfieDataUri.match(/^data:(.+?);base64,(.+)$/);
      if (matches && matches.length === 3) {
        const mimeType = matches[1];
        const base64Data = matches[2];
        const extension = mimeType.split('/')[1] || 'jpg';
        const filename = `${newLogId}_${logData.userId}.${extension}`;
        const filePathOnDisk = path.join(ATTENDANCE_UPLOADS_DIR, filename); // Absolute path for server-side write
        
        await fs.writeFile(filePathOnDisk, base64Data, 'base64');
        relativeDbSelfiePath = `attendance/${filename}`; // Relative path for DB (to be served via /api/uploads)
        finalSelfieDataUri = undefined; // Clear DataURI as we have saved the file
        console.log(`[API Attendance] Selfie saved to: ${filePathOnDisk}, stored DB path: ${relativeDbSelfiePath}. DataURI cleared.`);
      } else {
        console.warn(`[API Attendance] Invalid Data URI format for selfie for log ID ${newLogId}. Not saving image file. DataURI will be stored if present.`);
      }
    }

    const newLog: AttendanceLog = {
      ...logData,
      id: newLogId,
      selfieDataUri: finalSelfieDataUri,
      selfieImagePath: relativeDbSelfiePath,
    };

    await db.run(
      'INSERT INTO attendance_logs (id, userId, timestamp, method, selfieDataUri, selfieImagePath) VALUES (?, ?, ?, ?, ?, ?)',
      newLog.id, newLog.userId, newLog.timestamp, newLog.method, newLog.selfieDataUri, newLog.selfieImagePath
    );
    return NextResponse.json(newLog, { status: 201 });
  } catch (error) {
    console.error('Failed to add attendance log:', error);
    return NextResponse.json({ message: 'Failed to add attendance log', error: (error as Error).message }, { status: 500 });
  }
}
