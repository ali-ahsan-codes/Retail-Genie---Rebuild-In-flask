
// src/app/api/settings/global-discount/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { GlobalDiscountSetting } from '@/types';
import { INITIAL_GLOBAL_DISCOUNT_SETTING } from '@/lib/constants';

export async function GET() {
  try {
    const dbInstance = await getDb();
    if (!dbInstance) {
      console.error("[API GET /api/settings/global-discount] Database is unavailable. Returning default settings.");
      const defaultResponse = INITIAL_GLOBAL_DISCOUNT_SETTING 
        ? { ...INITIAL_GLOBAL_DISCOUNT_SETTING, isActive: !!INITIAL_GLOBAL_DISCOUNT_SETTING.isActive } 
        : null;
      return NextResponse.json(defaultResponse, { status: 200 });
    }

    const settingRaw = await dbInstance.get('SELECT * FROM global_discount_settings LIMIT 1');
    if (!settingRaw) {
      console.warn("[API GET /api/settings/global-discount] No global discount setting in DB, returning initial default from constants.");
      const defaultResponse = INITIAL_GLOBAL_DISCOUNT_SETTING 
        ? { ...INITIAL_GLOBAL_DISCOUNT_SETTING, isActive: !!INITIAL_GLOBAL_DISCOUNT_SETTING.isActive } 
        : null;
      return NextResponse.json(defaultResponse, { status: 200 });
    }
    const setting = {...settingRaw, isActive: !!settingRaw.isActive};
    return NextResponse.json(setting);
  } catch (error) {
    console.error('[API GET /api/settings/global-discount] Error during DB operation for global discount. Error:', error);
    console.warn('[API GET /api/settings/global-discount] Returning default global discount setting (from constants) due to DB operation error.');
    const defaultResponseOnError = INITIAL_GLOBAL_DISCOUNT_SETTING 
      ? { ...INITIAL_GLOBAL_DISCOUNT_SETTING, isActive: !!INITIAL_GLOBAL_DISCOUNT_SETTING.isActive } 
      : null;
    return NextResponse.json(defaultResponseOnError, { status: 200 });
  }
}

export async function PUT(request: Request) {
  try {
    const settingData = await request.json() as GlobalDiscountSetting | null;
    const dbInstance = await getDb();

    if (!dbInstance) {
      console.error("[API PUT /api/settings/global-discount] Database is unavailable. Cannot update settings.");
      return NextResponse.json({ message: 'Database unavailable, cannot update global discount settings.' }, { status: 503 });
    }

    await dbInstance.run('DELETE FROM global_discount_settings');

    if (settingData) { 
      if (settingData.percentage == null || settingData.isActive == null || !settingData.id) {
         return NextResponse.json({ message: 'Invalid global discount setting object' }, { status: 400 });
      }
      await dbInstance.run(
        'INSERT INTO global_discount_settings (id, percentage, startDate, endDate, isActive, description) VALUES (?, ?, ?, ?, ?, ?)',
        settingData.id, settingData.percentage, settingData.startDate, settingData.endDate, settingData.isActive ? 1 : 0, settingData.description
      );
      const newSettingRaw = await dbInstance.get('SELECT * FROM global_discount_settings WHERE id = ?', settingData.id);
      const newSetting = newSettingRaw ? {...newSettingRaw, isActive: !!newSettingRaw.isActive} : null;
      return NextResponse.json(newSetting);
    }
    
    return NextResponse.json(null, {status: 200}); 
  } catch (error) {
    console.error('Failed to update global discount setting:', error);
    return NextResponse.json({ message: 'Failed to update global discount setting', error: (error as Error).message }, { status: 500 });
  }
}

