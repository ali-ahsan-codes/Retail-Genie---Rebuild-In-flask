
import { NextResponse } from 'next/server';
import { getDb, parseDemandNoticeJSONFields } from '@/lib/server/database';
import type { DemandNotice } from '@/types';

interface Params {
  params: { noticeId: string };
}

export async function GET(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    const noticeRaw = await db.get('SELECT * FROM demand_notices WHERE id = ?', params.noticeId);
    if (!noticeRaw) {
      return NextResponse.json({ message: 'Demand notice not found' }, { status: 404 });
    }
    const notice = parseDemandNoticeJSONFields(noticeRaw);
    return NextResponse.json(notice);
  } catch (error) {
    console.error(`Failed to fetch demand notice ${params.noticeId}:`, error);
    return NextResponse.json({ message: 'Failed to fetch demand notice' }, { status: 500 });
  }
}


export async function PUT(request: Request, { params }: Params) {
  let db;
  try {
    const noticeDataFromClient = await request.json() as Partial<DemandNotice> & { id: string };
    db = await getDb();
    const noticeId = params.noticeId;

    if (noticeDataFromClient.id !== noticeId) {
      return NextResponse.json({ message: "ID mismatch in path and body." }, { status: 400 });
    }

    await db.run('BEGIN TRANSACTION');
    const existingNoticeRaw = await db.get('SELECT * FROM demand_notices WHERE id = ?', noticeId);
    if (!existingNoticeRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Demand notice not found' }, { status: 404 });
    }
    const existingNotice = parseDemandNoticeJSONFields(existingNoticeRaw);

    const updatedNotice: DemandNotice = {
      ...existingNotice,
      ...noticeDataFromClient,
      productSku: noticeDataFromClient.productSku || existingNotice.productSku, 
      updatedAt: new Date().toISOString(),
    };
    
    const result = await db.run(
      `UPDATE demand_notices SET 
        salespersonId = ?, salespersonName = ?, customerContactNumber = ?, productId = ?, 
        productName = ?, productSku = ?, quantityRequested = ?, quantityFulfilled = ?, agreedPrice = ?, 
        expectedAvailabilityDate = ?, status = ?, isNewProduct = ?, updatedAt = ?, notes = ?, payments = ?, linkedOrderId = ?
       WHERE id = ?`,
      updatedNotice.salespersonId, updatedNotice.salespersonName, updatedNotice.customerContactNumber, updatedNotice.productId,
      updatedNotice.productName, updatedNotice.productSku, updatedNotice.quantityRequested, updatedNotice.quantityFulfilled, updatedNotice.agreedPrice,
      updatedNotice.expectedAvailabilityDate, updatedNotice.status, updatedNotice.isNewProduct ? 1 : 0, updatedNotice.updatedAt, 
      updatedNotice.notes, JSON.stringify(updatedNotice.payments || []), updatedNotice.linkedOrderId,
      noticeId
    );

    if (result.changes === 0) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Demand notice not found or no changes made' }, { status: 404 });
    }

    await db.run('COMMIT');
    const freshNoticeRaw = await db.get('SELECT * FROM demand_notices WHERE id = ?', noticeId);
    const freshNotice = parseDemandNoticeJSONFields(freshNoticeRaw);
    return NextResponse.json(freshNotice);

  } catch (error: any) {
    if (db) {
      await db.run('ROLLBACK').catch(e => console.error("Rollback failed in PUT /api/demand-notices/[noticeId]:", e));
    }
    
    let clientErrorMessage = 'Failed to update demand notice on the server.';
    let errorDetailsForLog = String(error); // Default to string representation of the error

    if (error && typeof error.message === 'string') {
      clientErrorMessage = `Server error: ${error.message}`;
      errorDetailsForLog = error.message; 
      if (error.message.includes('UNIQUE constraint failed')) {
         clientErrorMessage = `A unique constraint was violated: ${error.message}`;
      } else if (error.message.includes('NOT NULL constraint failed')) {
        clientErrorMessage = `A required field was missing or invalid: ${error.message}`;
      }
    } else if (typeof error === 'string') {
      clientErrorMessage = `Server error: ${error}`;
    }
    
    console.error(`API Error in PUT /api/demand-notices/${params.noticeId}: ${errorDetailsForLog}`, error); 
    
    return NextResponse.json({ message: clientErrorMessage, error: errorDetailsForLog }, { status: 500 });
  }
}

export async function DELETE(request: Request, { params }: Params) {
  try {
    const db = await getDb();
    const result = await db.run('DELETE FROM demand_notices WHERE id = ?', params.noticeId);
    if (result.changes === 0) {
      return NextResponse.json({ message: 'Demand notice not found' }, { status: 404 });
    }
    return NextResponse.json({ message: 'Demand notice deleted successfully' });
  } catch (error) {
    console.error(`Failed to delete demand notice ${params.noticeId}:`, error);
    return NextResponse.json({ message: 'Failed to delete demand notice' }, { status: 500 });
  }
}
    
