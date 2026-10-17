
// src/app/api/settings/commission/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { CommissionSetting } from '@/types';
import { INITIAL_COMMISSION_SETTING } from '@/lib/constants';

export async function GET() {
  try {
    const dbInstance = await getDb();
    if (!dbInstance) {
      console.error("[API GET /api/settings/commission] Database is unavailable. Returning default settings.");
      const defaultResponse = INITIAL_COMMISSION_SETTING 
        ? { ...INITIAL_COMMISSION_SETTING, isActive: !!INITIAL_COMMISSION_SETTING.isActive } 
        : null;
      return NextResponse.json(defaultResponse, { status: 200 });
    }

    const settingRaw = await dbInstance.get('SELECT * FROM commission_settings LIMIT 1');
    if (!settingRaw) {
      console.warn("[API GET /api/settings/commission] No commission setting in DB, returning initial default from constants.");
      const defaultResponse = INITIAL_COMMISSION_SETTING 
        ? { ...INITIAL_COMMISSION_SETTING, isActive: !!INITIAL_COMMISSION_SETTING.isActive } 
        : null;
      return NextResponse.json(defaultResponse, { status: 200 });
    }
    const setting = {...settingRaw, isActive: !!settingRaw.isActive};
    return NextResponse.json(setting);
  } catch (error) {
    console.error('[API GET /api/settings/commission] Error during DB operation for commission setting. Error:', error);
    console.warn('[API GET /api/settings/commission] Returning default commission setting (from constants) due to DB operation error.');
    const defaultResponseOnError = INITIAL_COMMISSION_SETTING 
      ? { ...INITIAL_COMMISSION_SETTING, isActive: !!INITIAL_COMMISSION_SETTING.isActive } 
      : null;
    return NextResponse.json(defaultResponseOnError, { status: 200 });
  }
}

export async function PUT(request: Request) {
  try {
    const settingData = await request.json() as CommissionSetting | null;
    const dbInstance = await getDb();

    if (!dbInstance) {
      console.error("[API PUT /api/settings/commission] Database is unavailable. Cannot update settings.");
      return NextResponse.json({ message: 'Database unavailable, cannot update commission settings.' }, { status: 503 });
    }

    await dbInstance.run('DELETE FROM commission_settings'); 

    if (settingData) {
      if (settingData.id == null || settingData.salesTarget == null || settingData.commissionInterval == null || settingData.commissionPercentage == null || settingData.isActive == null) {
        return NextResponse.json({ message: 'Invalid commission setting object fields' }, { status: 400 });
      }
      await dbInstance.run(
        'INSERT INTO commission_settings (id, salesTarget, commissionInterval, commissionPercentage, isActive) VALUES (?, ?, ?, ?, ?)',
        settingData.id, settingData.salesTarget, settingData.commissionInterval, settingData.commissionPercentage, settingData.isActive ? 1 : 0
      );
      const newSettingRaw = await dbInstance.get('SELECT * FROM commission_settings WHERE id = ?', settingData.id);
      const newSetting = newSettingRaw ? {...newSettingRaw, isActive: !!newSettingRaw.isActive} : null;
      return NextResponse.json(newSetting);
    }
    
    return NextResponse.json(null, {status: 200 }); 
  } catch (error) {
    console.error('Failed to update commission setting:', error);
    return NextResponse.json({ message: 'Failed to update commission setting', error: (error as Error).message }, { status: 500 });
  }
}

