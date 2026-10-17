
// src/app/api/quotations/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseQuotationJSONFields, parseQuotationItemJSONFields, getNextSeriesNumber } from '@/lib/server/database';
import type { Quotation, QuotationItem, User } from '@/types';

// Placeholder for your actual authentication mechanism
// In a real app, this would involve session/token validation
async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
  // This is a mock. Replace with your actual auth logic.
  // For now, let's assume salespersonId is passed in headers for protected routes
  // or derivable from a session cookie parsed by middleware.
  const userId = req.headers.get('x-user-id');
  if (userId) {
    const db = await getDb();
    if (!db) return null;
    const user = await db.get<User>('SELECT id, username, role, permissions FROM users WHERE id = ?', userId); // Added permissions
    return user || null;
  }
  return null;
}

function generateQuotationItemId() {
  return `QI-${Date.now().toString().slice(-4)}-${Math.random().toString(36).substring(2, 9).toUpperCase()}`;
}

export async function POST(req: NextRequest) {
  let db;
  try {
    // Replace with actual authentication
    const salespersonUser = await getAuthenticatedUser(req); 
    if (!salespersonUser || (salespersonUser.role !== 'salesperson' && salespersonUser.role !== 'admin' && salespersonUser.role !== 'manager')) {
      return NextResponse.json({ error: 'Unauthorized or invalid role for creating quotations' }, { status: 401 });
    }

    const body = await req.json();
    db = await getDb();
    if (!db) {
      return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
    }
    
    const {
      customerName, customerPhone, customerEmail, customerAddress,
      preparationDays, validUntil, status = 'draft', totalAmount, notes,
      items
    } = body;

    if (!items || !Array.isArray(items) || items.length === 0) {
      return NextResponse.json({ error: 'Quotation must include at least one item.' }, { status: 400 });
    }
    if (preparationDays == null || validUntil == null || totalAmount == null) {
      return NextResponse.json({ error: 'Missing required fields: preparationDays, validUntil, totalAmount.' }, { status: 400 });
    }

    await db.run('BEGIN TRANSACTION');
    const quotationId = await getNextSeriesNumber('quotation', db);
    const now = new Date().toISOString();

    const quotation: Quotation = {
      id: quotationId,
      salespersonId: salespersonUser.id,
      customerName,
      customerPhone,
      customerEmail,
      customerAddress,
      preparationDays: parseInt(preparationDays, 10),
      validUntil,
      status,
      createdAt: now,
      updatedAt: now,
      totalAmount: parseFloat(totalAmount),
      notes
    };

    await db.run(
      `INSERT INTO quotations (id, salespersonId, customerName, customerPhone, customerEmail, customerAddress, preparationDays, validUntil, status, createdAt, updatedAt, totalAmount, notes)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        quotation.id, quotation.salespersonId, quotation.customerName, quotation.customerPhone, quotation.customerEmail,
        quotation.customerAddress, quotation.preparationDays, quotation.validUntil, quotation.status,
        quotation.createdAt, quotation.updatedAt, quotation.totalAmount, quotation.notes
      ]
    );

    for (const item of items) {
      const itemId = generateQuotationItemId();
      const quotationItem: QuotationItem = {
        id: itemId,
        quotationId,
        productId: item.productId || null,
        productName: item.productName,
        productSku: item.productSku || null,
        price: parseFloat(item.price),
        quantity: parseInt(item.quantity, 10),
        isExternal: !!item.isExternal,
        converted: false,
      };
      await db.run(
        `INSERT INTO quotation_items (id, quotationId, productId, productName, productSku, price, quantity, isExternal, converted)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          quotationItem.id, quotationItem.quotationId, quotationItem.productId, quotationItem.productName, quotationItem.productSku,
          quotationItem.price, quotationItem.quantity, quotationItem.isExternal ? 1 : 0, quotationItem.converted ? 1 : 0
        ]
      );
    }

    await db.run('COMMIT');
    return NextResponse.json({ success: true, data: quotation }, { status: 201 });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error('Error creating quotation:', error);
    return NextResponse.json({ error: 'Internal Server Error', details: error.message }, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  let db;
  try {
    const authenticatedUser = await getAuthenticatedUser(req);
    if (!authenticatedUser) {
      return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 });
    }
    db = await getDb();
    if (!db) {
      return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
    }

    let query = 'SELECT * FROM quotations';
    const params: any[] = [];

    if (authenticatedUser.role === 'salesperson') {
      query += ' WHERE salespersonId = ?';
      params.push(authenticatedUser.id);
    } else if (authenticatedUser.role === 'admin' || authenticatedUser.role === 'manager') {
      // Admins and Managers see all quotations, no additional WHERE clause needed for filtering by user.
    } else {
      // Should not happen if initial role check in POST is correct, but as a fallback.
      return NextResponse.json({ success: false, error: 'Forbidden: Insufficient role for viewing quotations.' }, { status: 403 });
    }
    
    query += ' ORDER BY createdAt DESC';

    const quotationsRaw = await db.all(query, params);
    const quotations = quotationsRaw.map(parseQuotationJSONFields);
    
    return NextResponse.json({ success: true, data: quotations });

  } catch (error: any) {
    console.error('Error fetching quotations:', error);
    return NextResponse.json({ success: false, error: 'Internal Server Error', details: error.message }, { status: 500 });
  }
}
