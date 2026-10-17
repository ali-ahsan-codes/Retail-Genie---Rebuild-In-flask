
// src/app/api/settings/tax/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { TaxSetting } from '@/types';
import { INITIAL_TAX_SETTINGS } from '@/lib/constants';

export async function GET() {
  try {
    const dbInstance = await getDb();
    if (!dbInstance) {
      console.error("[API GET /api/settings/tax] Database is unavailable. Returning default settings.");
      return NextResponse.json(INITIAL_TAX_SETTINGS.map(s => ({...s, enabled: !!s.enabled })), { status: 200 });
    }

    const settingsRaw = await dbInstance.all('SELECT id, name, rate, enabled FROM tax_settings');
    
    if (!settingsRaw || settingsRaw.length === 0) {
        const dbIsEmpty = (await dbInstance.get('SELECT COUNT(*) as count FROM tax_settings'))?.count === 0;
        if (dbIsEmpty) {
            console.warn("[API GET /api/settings/tax] Tax settings table is empty in DB, returning initial defaults from constants.");
            return NextResponse.json(INITIAL_TAX_SETTINGS.map(s => ({...s, enabled: !!s.enabled })), { status: 200 });
        }
    }
    const settings = settingsRaw.map(s => ({...s, enabled: !!s.enabled })); 
    return NextResponse.json(settings);
  } catch (error) {
    console.error('[API GET /api/settings/tax] Error during DB operation for tax settings. Error:', error);
    console.warn('[API GET /api/settings/tax] Returning default tax settings (from constants) due to DB operation error.');
    return NextResponse.json(INITIAL_TAX_SETTINGS.map(s => ({...s, enabled: !!s.enabled })), { status: 200 });
  }
}

export async function PUT(request: Request) { 
  let dbInstance;
  try {
    const newSettings = await request.json() as TaxSetting[];
    dbInstance = await getDb();

    if (!dbInstance) {
      console.error("[API PUT /api/settings/tax] Database is unavailable. Cannot update settings.");
      return NextResponse.json({ message: 'Database unavailable, cannot update tax settings.' }, { status: 503 });
    }

    if (!Array.isArray(newSettings)) {
        return NextResponse.json({ message: 'Invalid format for tax settings' }, { status: 400 });
    }

    await dbInstance.run('BEGIN TRANSACTION');
    await dbInstance.run('DELETE FROM tax_settings');
    for (const setting of newSettings) {
        if (!setting.id || !setting.name || setting.rate == null || setting.enabled == null) {
            await dbInstance.run('ROLLBACK');
            return NextResponse.json({ message: `Invalid tax setting object: ${JSON.stringify(setting)}` }, { status: 400 });
        }
      await dbInstance.run(
        'INSERT INTO tax_settings (id, name, rate, enabled) VALUES (?, ?, ?, ?)',
        setting.id, setting.name, setting.rate, setting.enabled ? 1 : 0
      );
    }
    await dbInstance.run('COMMIT');

    const updatedSettingsRaw = await dbInstance.all('SELECT id, name, rate, enabled FROM tax_settings');
    const updatedSettings = updatedSettingsRaw.map(s => ({...s, enabled: !!s.enabled }));
    return NextResponse.json(updatedSettings);
  } catch (error) {
    console.error('Failed to update tax settings:', error);
    if (dbInstance) {
      try { await dbInstance.run('ROLLBACK'); } catch (e) { console.error("Rollback failed or db not available", e); }
    }
    return NextResponse.json({ message: 'Failed to update tax settings', error: (error as Error).message }, { status: 500 });
  }
}

