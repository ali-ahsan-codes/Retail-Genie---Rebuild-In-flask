
// src/app/api/demand-notices/[noticeId]/payment/route.ts
import { NextResponse } from 'next/server';
import { getDb, parseDemandNoticeJSONFields } from '@/lib/server/database';
import type { DemandNotice, PaymentDetail } from '@/types';

interface Params {
  params: { noticeId: string };
}

interface PaymentRequestBody {
  payment: PaymentDetail;
}

export async function POST(request: Request, { params }: Params) {
  let db;
  try {
    const { payment } = await request.json() as PaymentRequestBody;
    db = await getDb();
    const noticeId = params.noticeId;

    if (!payment || typeof payment.amount !== 'number' || !payment.method) {
      return NextResponse.json({ message: 'Invalid payment data provided' }, { status: 400 });
    }

    await db.run('BEGIN TRANSACTION');

    const noticeRaw = await db.get('SELECT * FROM demand_notices WHERE id = ?', noticeId);
    if (!noticeRaw) {
      await db.run('ROLLBACK');
      return NextResponse.json({ message: 'Demand notice not found' }, { status: 404 });
    }
    const notice = parseDemandNoticeJSONFields(noticeRaw);

    const newPayment: PaymentDetail = {
      ...payment,
      paymentDate: new Date().toISOString(),
      transactionId: payment.method !== 'cash' ? payment.transactionId || `DN_PMT_${Date.now()}` : undefined,
    };

    const updatedPayments = [...(notice.payments || []), newPayment];

    await db.run(
      'UPDATE demand_notices SET payments = ?, updatedAt = ? WHERE id = ?',
      JSON.stringify(updatedPayments),
      new Date().toISOString(),
      noticeId
    );
    
    await db.run('COMMIT');

    const updatedNoticeRaw = await db.get('SELECT * FROM demand_notices WHERE id = ?', noticeId);
    const updatedNotice = parseDemandNoticeJSONFields(updatedNoticeRaw);
    
    return NextResponse.json(updatedNotice, { status: 200 });

  } catch (error) {
    if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
    console.error(`Failed to add payment to demand notice ${params.noticeId}:`, error);
    return NextResponse.json({ message: 'Failed to add payment', error: (error as Error).message }, { status: 500 });
  }
}

    