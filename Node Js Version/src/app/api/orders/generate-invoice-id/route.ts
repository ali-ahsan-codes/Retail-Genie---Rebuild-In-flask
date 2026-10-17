
// src/app/api/orders/generate-invoice-id/route.ts
// This route is deprecated and its functionality is now integrated into POST /api/orders.
// It can be removed. If kept for any legacy reason, it should be updated,
// but the primary invoice generation logic is in /api/orders/route.ts.

import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { InvoiceNumberSetting } from '@/types';

export async function GET(request: Request) {
  console.warn("[DEPRECATED API] /api/orders/generate-invoice-id called. This endpoint is deprecated. Invoice ID generation is handled by POST /api/orders.");
  
  // For safety, return an error or a placeholder if somehow called.
  // Or, implement the new numerical logic here too if there's a hidden dependency.
  // Given the file_structure and api_endpoints docs, this should not be the primary path.

  // Implementing new numerical logic here as a fallback, though ideally it's unused.
  try {
    const db = await getDb();
    await db.run('BEGIN TRANSACTION');

    let setting = await db.get<InvoiceNumberSetting>('SELECT * FROM invoice_number_settings WHERE id = ?', 'main_invoice_config');
    if (!setting) {
      setting = { id: 'main_invoice_config', nextInvoiceNumber: 1 };
      await db.run('INSERT INTO invoice_number_settings (id, nextInvoiceNumber) VALUES (?, ?)', setting.id, setting.nextInvoiceNumber);
    }

    let currentNextInvoiceNumber = setting.nextInvoiceNumber;
    let newId = '';
    let attempts = 0;
    const MAX_ATTEMPTS = 50;

    do {
      newId = String(currentNextInvoiceNumber).padStart(6, '0');
      const existingOrder = await db.get('SELECT id FROM orders WHERE id = ?', newId);
      if (!existingOrder) break;
      currentNextInvoiceNumber++;
      attempts++;
    } while (attempts < MAX_ATTEMPTS);

    if (attempts >= MAX_ATTEMPTS) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Failed to generate unique invoice ID (fallback). Please try again.' }, { status: 500 });
    }

    await db.run('UPDATE invoice_number_settings SET nextInvoiceNumber = ? WHERE id = ?', currentNextInvoiceNumber + 1, setting.id);
    await db.run('COMMIT');
    
    return NextResponse.json({ invoiceId: newId });

  } catch (error) {
    const dbInstance = await getDb().catch(() => null);
    if (dbInstance) await dbInstance.run('ROLLBACK').catch(e => console.error("Rollback failed in deprecated generate-invoice-id:", e));
    console.error('Failed to generate invoice ID (fallback):', error);
    return NextResponse.json({ message: 'Failed to generate invoice ID (fallback)', error: (error as Error).message }, { status: 500 });
  }
}
