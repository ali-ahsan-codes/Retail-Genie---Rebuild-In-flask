
// src/app/api/settings/attendance/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseAttendanceSettingJSONFields } from '@/lib/server/database';
import type { AttendanceSetting } from '@/types';
import { INITIAL_ATTENDANCE_SETTING } from '@/lib/constants';

export async function GET() {
  try {
    const dbInstance = await getDb();
    if (!dbInstance) {
      console.error("[API GET /api/settings/attendance] Database is unavailable. Returning default settings.");
      return NextResponse.json(parseAttendanceSettingJSONFields(INITIAL_ATTENDANCE_SETTING), { status: 200 });
    }

    const settingRaw = await dbInstance.get<any>('SELECT * FROM attendance_settings WHERE id = ? LIMIT 1', INITIAL_ATTENDANCE_SETTING.id);
    
    if (!settingRaw) {
      console.warn("[API GET /api/settings/attendance] No attendance setting in DB, returning initial default.");
      return NextResponse.json(parseAttendanceSettingJSONFields(INITIAL_ATTENDANCE_SETTING), { status: 200 });
    }
    return NextResponse.json(parseAttendanceSettingJSONFields(settingRaw));
  } catch (error) {
    console.error('[API GET /api/settings/attendance] Error during DB operation for attendance setting. Error:', error);
    console.warn('[API GET /api/settings/attendance] Returning default attendance settings due to DB operation error.');
    return NextResponse.json(parseAttendanceSettingJSONFields(INITIAL_ATTENDANCE_SETTING), { status: 200 });
  }
}

export async function PUT(request: Request) {
  let dbInstance;
  try {
    const settingDataFromClient = await request.json() as Partial<AttendanceSetting> | null;
    dbInstance = await getDb();

    if (!dbInstance) {
      console.error("[API PUT /api/settings/attendance] Database is unavailable. Cannot update settings.");
      return NextResponse.json({ message: 'Database unavailable, cannot update attendance settings.' }, { status: 503 });
    }

    if (!settingDataFromClient || settingDataFromClient.id !== INITIAL_ATTENDANCE_SETTING.id) {
      console.log("[API VAL] Invalid settingDataFromClient or ID mismatch:", settingDataFromClient);
      return NextResponse.json({ message: `Invalid attendance setting data. ID must be '${INITIAL_ATTENDANCE_SETTING.id}'.` }, { status: 400 });
    }

    if (settingDataFromClient.is_mandatory_attendance_active && settingDataFromClient.mandatory_attendance_time) {
        if (!/^(0[0-9]|1[0-9]|2[0-3]):[0-5][0-9]$/.test(settingDataFromClient.mandatory_attendance_time)) {
            console.log("[API VAL] Invalid time format for mandatory_attendance_time:", settingDataFromClient.mandatory_attendance_time);
            return NextResponse.json({ message: 'Invalid time format for mandatory_attendance_time. Please use HH:MM.' }, { status: 400 });
        }
    }

    const maxBreaksFromClient = settingDataFromClient.max_concurrent_breaks;
    if (maxBreaksFromClient !== undefined && maxBreaksFromClient !== null) {
      if (typeof maxBreaksFromClient !== 'number' || !Number.isInteger(maxBreaksFromClient) || maxBreaksFromClient < 0) {
        console.log(`[API VAL] Invalid max_concurrent_breaks from client:`, maxBreaksFromClient, typeof maxBreaksFromClient);
        return NextResponse.json({ message: 'max_concurrent_breaks must be a non-negative integer or null (if not provided/cleared).' }, { status: 400 });
      }
    }
    
    let currentSetting: AttendanceSetting;
    const existingSettingRaw = await dbInstance.get<any>('SELECT * FROM attendance_settings WHERE id = ?', INITIAL_ATTENDANCE_SETTING.id);

    if (existingSettingRaw) {
      currentSetting = parseAttendanceSettingJSONFields(existingSettingRaw);
    } else {
      currentSetting = parseAttendanceSettingJSONFields(INITIAL_ATTENDANCE_SETTING);
    }
    
    const newIsMandatoryActive = typeof settingDataFromClient.is_mandatory_attendance_active === 'boolean'
                                ? settingDataFromClient.is_mandatory_attendance_active
                                : currentSetting.is_mandatory_attendance_active;

    const newMandatoryTime = newIsMandatoryActive
                              ? (settingDataFromClient.mandatory_attendance_time !== undefined
                                  ? settingDataFromClient.mandatory_attendance_time 
                                  : currentSetting.mandatory_attendance_time)
                              : null;
    
    let newMaxConcurrentBreaks: number | null;
    if (settingDataFromClient.max_concurrent_breaks === undefined) { 
        newMaxConcurrentBreaks = currentSetting.max_concurrent_breaks;
    } else { 
        newMaxConcurrentBreaks = settingDataFromClient.max_concurrent_breaks;
    }

    const finalSettingToSave: AttendanceSetting = {
      id: INITIAL_ATTENDANCE_SETTING.id,
      mandatory_attendance_time: newMandatoryTime,
      is_mandatory_attendance_active: newIsMandatoryActive,
      max_concurrent_breaks: newMaxConcurrentBreaks,
    };

    await dbInstance.run('BEGIN TRANSACTION');
    
    await dbInstance.run(
      'INSERT OR REPLACE INTO attendance_settings (id, mandatory_attendance_time, is_mandatory_attendance_active, max_concurrent_breaks) VALUES (?, ?, ?, ?)',
      finalSettingToSave.id,
      finalSettingToSave.mandatory_attendance_time, 
      finalSettingToSave.is_mandatory_attendance_active ? 1 : 0, 
      finalSettingToSave.max_concurrent_breaks 
    );
    
    await dbInstance.run('COMMIT'); 

    const updatedSettingRaw = await dbInstance.get<any>('SELECT * FROM attendance_settings WHERE id = ?', finalSettingToSave.id);
    
    if (!updatedSettingRaw) {
      console.error(`[API CRITICAL] Attendance setting with ID '${finalSettingToSave.id}' not found after successful commit.`);
      return NextResponse.json({ message: `Internal error: Failed to retrieve attendance setting post-update for ID ${finalSettingToSave.id}. Data may have been saved.` }, { status: 500 });
    }
    
    return NextResponse.json(parseAttendanceSettingJSONFields(updatedSettingRaw));

  } catch (error: any) {
    if (dbInstance) {
        try { await dbInstance.run('ROLLBACK'); } catch (rollbackError: any) { /* ignore */ }
    }
    let clientErrorMessage = 'Failed to update attendance setting on the server.';
    if (error.message) {
        clientErrorMessage += ` Server detail: ${error.message.substring(0, 150)}`; 
    }
    console.error('[API ERROR] Failed to update attendance setting:', error);
    return NextResponse.json({ message: clientErrorMessage, error: error.message || 'Unknown server error' }, { status: 500 });
  }
}

