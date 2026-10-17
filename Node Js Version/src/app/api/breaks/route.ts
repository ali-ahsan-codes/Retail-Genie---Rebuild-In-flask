
// src/app/api/breaks/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseAttendanceSettingJSONFields } from '@/lib/server/database';
import type { BreakLog, AttendanceSetting } from '@/types';
import { INITIAL_ATTENDANCE_SETTING } from '@/lib/constants';

export async function GET() {
  try {
    const db = await getDb();
    if (!db) {
      console.error("[API GET /api/breaks] Database is unavailable.");
      return NextResponse.json({ message: 'Database unavailable' }, { status: 503 });
    }
    const logs = await db.all<BreakLog[]>('SELECT * FROM break_logs ORDER BY startTime DESC');
    return NextResponse.json(logs);
  } catch (error) {
    console.error('Failed to fetch break logs:', error);
    return NextResponse.json({ message: 'Failed to fetch break logs' }, { status: 500 });
  }
}

export async function POST(request: Request) { // This is for starting a break
  let db;
  try {
    const { userId } = await request.json() as { userId: string };
    db = await getDb();
    if (!db) {
      console.error("[API POST /api/breaks] Database is unavailable.");
      return NextResponse.json({ message: 'Database unavailable' }, { status: 503 });
    }
    await db.run('BEGIN TRANSACTION');

    if (!userId) {
        await db.run('ROLLBACK');
        return NextResponse.json({ message: 'User ID is required to start a break' }, { status: 400 });
    }

    // REMOVED: Concurrent break limit check
    // const attendanceSettingRaw = await db.get('SELECT * FROM attendance_settings WHERE id = ?', INITIAL_ATTENDANCE_SETTING.id);
    // const attendanceSetting = attendanceSettingRaw
    //     ? parseAttendanceSettingJSONFields(attendanceSettingRaw)
    //     : parseAttendanceSettingJSONFields(INITIAL_ATTENDANCE_SETTING);

    // if (attendanceSetting && attendanceSetting.max_concurrent_breaks !== null && attendanceSetting.max_concurrent_breaks >= 0) {
    //     const activeBreaksCountResult = await db.get('SELECT COUNT(*) as count FROM break_logs WHERE endTime IS NULL');
    //     const activeBreaksCount = activeBreaksCountResult?.count || 0;
    //     if (activeBreaksCount >= attendanceSetting.max_concurrent_breaks) {
    //         await db.run('ROLLBACK');
    //         return NextResponse.json({ message: `Concurrent break limit of ${attendanceSetting.max_concurrent_breaks} reached. Please try again later.` }, { status: 409 }); // 409 Conflict
    //     }
    // }

    const activeBreakForUser = await db.get('SELECT id FROM break_logs WHERE userId = ? AND endTime IS NULL', userId);
    if (activeBreakForUser) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'User is already on an active break' }, { status: 409 });
    }
    
    const newLogId = `brk_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const startTime = new Date().toISOString();
    const newBreak: BreakLog = { id: newLogId, userId, startTime };

    await db.run(
      'INSERT INTO break_logs (id, userId, startTime) VALUES (?, ?, ?)',
      newBreak.id, newBreak.userId, newBreak.startTime
    );
    // Update user's activeBreakId
    await db.run('UPDATE users SET activeBreakId = ? WHERE id = ?', newBreak.id, userId);
    
    await db.run('COMMIT');
    return NextResponse.json(newBreak, { status: 201 });
  } catch (error) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed in POST /api/breaks:", e));
    console.error('Failed to start break log:', error);
    return NextResponse.json({ message: 'Failed to start break log', error: (error as Error).message }, { status: 500 });
  }
}

