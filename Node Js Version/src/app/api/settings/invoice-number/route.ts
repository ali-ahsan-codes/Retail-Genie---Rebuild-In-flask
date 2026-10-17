
// src/app/api/settings/invoice-number/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { SeriesNumberSetting, SeriesId } from '@/types';
import { INITIAL_INVOICE_NUMBER_SETTING, INITIAL_QUOTATION_NUMBER_SETTING, INITIAL_DEMAND_NOTICE_NUMBER_SETTING } from '@/lib/constants';

export async function GET() {
  try {
    const dbInstance = await getDb();
    if (!dbInstance) {
      console.error("[API GET /api/settings/invoice-number] Database is unavailable. Returning default settings for all series.");
      return NextResponse.json({
        invoice: INITIAL_INVOICE_NUMBER_SETTING,
        quotation: INITIAL_QUOTATION_NUMBER_SETTING,
        demand_notice: INITIAL_DEMAND_NOTICE_NUMBER_SETTING
      }, { status: 200 });
    }

    const settingsRaw = await dbInstance.all<SeriesNumberSetting[]>('SELECT * FROM invoice_number_settings');
    
    const settingsMap: Record<SeriesId, SeriesNumberSetting> = {
      invoice: INITIAL_INVOICE_NUMBER_SETTING,
      quotation: INITIAL_QUOTATION_NUMBER_SETTING,
      demand_notice: INITIAL_DEMAND_NOTICE_NUMBER_SETTING,
    };

    settingsRaw.forEach(s => {
      if (s.id === 'invoice' || s.id === 'quotation' || s.id === 'demand_notice') {
        settingsMap[s.id] = s;
      }
    });
    
    return NextResponse.json(settingsMap);
  } catch (error) {
    console.error('[API GET /api/settings/invoice-number] Error during DB operation. Error:', error);
    console.warn('[API GET /api/settings/invoice-number] Returning default settings for all series due to DB error.');
    return NextResponse.json({
        invoice: INITIAL_INVOICE_NUMBER_SETTING,
        quotation: INITIAL_QUOTATION_NUMBER_SETTING,
        demand_notice: INITIAL_DEMAND_NOTICE_NUMBER_SETTING
      }, { status: 200 });
  }
}

export async function PUT(request: Request) {
  try {
    const settingDataFromClient = await request.json() as Partial<SeriesNumberSetting> & { id: SeriesId } | null;
    const dbInstance = await getDb();

    if (!dbInstance) {
      console.error("[API PUT /api/settings/invoice-number] Database is unavailable. Cannot update settings.");
      return NextResponse.json({ message: 'Database unavailable, cannot update series number settings.' }, { status: 503 });
    }

    if (!settingDataFromClient || !settingDataFromClient.id || !['invoice', 'quotation', 'demand_notice'].includes(settingDataFromClient.id) || settingDataFromClient.nextNumber == null || settingDataFromClient.nextNumber < 1) {
      return NextResponse.json({ message: 'Invalid series number setting data. "id" must be "invoice", "quotation", or "demand_notice" and "nextNumber" must be a positive integer.' }, { status: 400 });
    }
    
    await dbInstance.run(
      'INSERT OR REPLACE INTO invoice_number_settings (id, nextNumber) VALUES (?, ?)',
      settingDataFromClient.id, 
      settingDataFromClient.nextNumber
    );

    const newSettingRaw = await dbInstance.get<SeriesNumberSetting>('SELECT * FROM invoice_number_settings WHERE id = ?', settingDataFromClient.id);
    return NextResponse.json(newSettingRaw);
  } catch (error) {
    console.error('Failed to update series number setting:', error);
    return NextResponse.json({ message: 'Failed to update series number setting', error: (error as Error).message }, { status: 500 });
  }
}
