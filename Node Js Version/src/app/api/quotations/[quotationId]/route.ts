
// src/app/api/quotations/[quotationId]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseQuotationJSONFields, parseQuotationItemJSONFields } from '@/lib/server/database';
import type { Quotation, QuotationItem, User, QuotationStatus } from '@/types';

interface RouteParams {
  params: { quotationId: string };
}

// Helper function to generate unique ID for quotation items
function generateQuotationItemId() {
  return `QI-${Date.now().toString().slice(-4)}-${Math.random().toString(36).substring(2, 9).toUpperCase()}`;
}

// Placeholder for actual authentication
async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
  const userId = req.headers.get('x-user-id');
  if (userId) {
    const db = await getDb();
    if (!db) return null;
    const user = await db.get<User>('SELECT id, username, role, permissions FROM users WHERE id = ?', userId); // Ensure permissions are fetched
    return user || null;
  }
  return null;
}

async function checkPermission(authenticatedUser: User | null, quotation: Quotation | null, action: 'view' | 'edit' | 'delete'): Promise<boolean> {
  if (!authenticatedUser) return false;
  if (authenticatedUser.role === 'admin') return true;
  if (authenticatedUser.role === 'manager') {
    // For now, managers can perform all these actions on any quotation.
    // This could be refined with specific manager permissions later.
    return true; 
  }
  // Salesperson checks
  if (authenticatedUser.role === 'salesperson' && quotation && quotation.salespersonId === authenticatedUser.id) {
    if (action === 'delete') {
      // Salespersons can only delete their own quotations if they are in 'draft' or 'rejected' status.
      return ['draft', 'rejected'].includes(quotation.status);
    }
    return true; // Salespersons can view and edit (PUT) their own quotations.
  }
  return false;
}

export async function GET(req: NextRequest, { params }: RouteParams) {
  let db;
  try {
    const { quotationId } = params;
    const authenticatedUser = await getAuthenticatedUser(req);
    
    db = await getDb();
    if (!db) {
      return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
    }

    const quotationRaw = await db.get('SELECT * FROM quotations WHERE id = ?', quotationId);
    if (!quotationRaw) {
      return NextResponse.json({ success: false, error: 'Quotation not found' }, { status: 404 });
    }
    const quotation = parseQuotationJSONFields(quotationRaw);

    if (!await checkPermission(authenticatedUser, quotation, 'view')) {
        return NextResponse.json({ success: false, error: 'Forbidden' }, { status: 403 });
    }

    const itemsRaw = await db.all('SELECT * FROM quotation_items WHERE quotationId = ?', quotationId);
    quotation.items = itemsRaw.map(parseQuotationItemJSONFields);

    return NextResponse.json({ success: true, data: quotation });
  } catch (error: any) {
    console.error(`Error fetching quotation ${params.quotationId}:`, error);
    return NextResponse.json({ success: false, error: 'Internal Server Error', details: error.message }, { status: 500 });
  }
}

export async function PUT(req: NextRequest, { params }: RouteParams) {
  let db;
  try {
    const { quotationId } = params;
    const authenticatedUser = await getAuthenticatedUser(req);
    
    const body = await req.json();
    db = await getDb();
    if (!db) {
      return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
    }

    await db.run('BEGIN TRANSACTION');

    const existingQuotationRaw = await db.get('SELECT * FROM quotations WHERE id = ?', quotationId);
    if (!existingQuotationRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ success: false, error: 'Quotation not found' }, { status: 404 });
    }
    const existingQuotation = parseQuotationJSONFields(existingQuotationRaw);

    if (!await checkPermission(authenticatedUser, existingQuotation, 'edit')) {
        await db.run('ROLLBACK');
        return NextResponse.json({ success: false, error: 'Forbidden' }, { status: 403 });
    }
    
    const { 
        status, notes, customerName, customerPhone, customerEmail, customerAddress, 
        preparationDays, validUntil, totalAmount, items 
    } = body;
    
    const updateFields: Partial<Quotation> = {};
    if (status !== undefined) updateFields.status = status as QuotationStatus;
    if (notes !== undefined) updateFields.notes = notes;
    if (customerName !== undefined) updateFields.customerName = customerName;
    if (customerPhone !== undefined) updateFields.customerPhone = customerPhone;
    if (customerEmail !== undefined) updateFields.customerEmail = customerEmail;
    if (customerAddress !== undefined) updateFields.customerAddress = customerAddress;
    if (preparationDays !== undefined) updateFields.preparationDays = parseInt(preparationDays, 10);
    if (validUntil !== undefined) updateFields.validUntil = validUntil; 
    if (totalAmount !== undefined) updateFields.totalAmount = parseFloat(totalAmount); 

    if (Object.keys(updateFields).length === 0 && (!items || items.length === 0)) {
      await db.run('ROLLBACK');
      return NextResponse.json({ error: 'No valid fields or items provided for update.' }, { status: 400 });
    }

    updateFields.updatedAt = new Date().toISOString();

    // Update main quotation table
    const updateQueryParts: string[] = [];
    const queryParams: any[] = [];

    for (const [key, value] of Object.entries(updateFields)) {
      updateQueryParts.push(`${key} = ?`);
      queryParams.push(value);
    }
    
    if (updateQueryParts.length > 0) {
        queryParams.push(quotationId);
        await db.run(
          `UPDATE quotations SET ${updateQueryParts.join(', ')} WHERE id = ?`,
          queryParams
        );
    }

    // Update quotation items if provided
    if (items && Array.isArray(items)) {
      // Delete existing items for this quotation
      await db.run('DELETE FROM quotation_items WHERE quotationId = ?', quotationId);

      // Insert new items
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
          converted: false, // New items start as unconverted
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
    }
    
    await db.run('COMMIT');

    const updatedQuotationRaw = await db.get('SELECT * FROM quotations WHERE id = ?', quotationId);
    const updatedQuotation = parseQuotationJSONFields(updatedQuotationRaw);
    
    const finalItemsRaw = await db.all('SELECT * FROM quotation_items WHERE quotationId = ?', quotationId);
    updatedQuotation.items = finalItemsRaw.map(parseQuotationItemJSONFields);


    return NextResponse.json({ success: true, data: updatedQuotation });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error(`Error updating quotation ${params.quotationId}:`, error);
    return NextResponse.json({ success: false, error: 'Internal Server Error', details: error.message }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest, { params }: RouteParams) {
  let db;
  try {
    const { quotationId } = params;
    const authenticatedUser = await getAuthenticatedUser(req);
    
    db = await getDb();
    if (!db) {
      return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
    }

    const quotationRaw = await db.get('SELECT * FROM quotations WHERE id = ?', quotationId);
    if (!quotationRaw) {
      return NextResponse.json({ success: false, error: 'Quotation not found' }, { status: 404 });
    }
    const quotation = parseQuotationJSONFields(quotationRaw);
    
    if (!await checkPermission(authenticatedUser, quotation, 'delete')) {
        return NextResponse.json({ success: false, error: 'Forbidden' }, { status: 403 });
    }
    
    await db.run('BEGIN TRANSACTION');
    await db.run('DELETE FROM quotation_items WHERE quotationId = ?', quotationId);
    await db.run('DELETE FROM quotations WHERE id = ?', quotationId);
    await db.run('COMMIT');

    return NextResponse.json({ success: true, message: 'Quotation deleted successfully.' });

  } catch (error: any) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error(`Error deleting quotation ${params.quotationId}:`, error);
    return NextResponse.json({ success: false, error: 'Internal Server Error', details: error.message }, { status: 500 });
  }
}

    