
// src/app/api/breaks/[breakId]/route.ts
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { BreakLog } from '@/types';
import { parseISO } from 'date-fns';

interface Params {
  params: { breakId: string };
}

// This route is primarily for ending a break (PUT operation)
export async function PUT(request: Request, { params }: Params) {
  try {
    const { userId } = await request.json() as { userId: string }; // Expect userId to confirm who is ending break
    const db = await getDb();
    const breakId = params.breakId;

    if (!userId) {
        return NextResponse.json({ message: 'User ID is required to end a break' }, { status: 400 });
    }

    const activeBreak = await db.get<BreakLog>('SELECT * FROM break_logs WHERE id = ? AND userId = ? AND endTime IS NULL', breakId, userId);

    if (!activeBreak) {
      return NextResponse.json({ message: 'Active break not found for this user and break ID, or break already ended.' }, { status: 404 });
    }
    
    const endTime = new Date().toISOString();
    const durationMs = parseISO(endTime).getTime() - parseISO(activeBreak.startTime).getTime();
    
    const result = await db.run(
      'UPDATE break_logs SET endTime = ?, durationMs = ? WHERE id = ?',
      endTime,
      durationMs,
      breakId
    );

    if (result.changes === 0) {
      // This case should ideally be caught by the activeBreak check, but as a safeguard
      return NextResponse.json({ message: 'Break not found or no changes made' }, { status: 404 });
    }

    // Clear user's activeBreakId
    await db.run('UPDATE users SET activeBreakId = NULL WHERE id = ? AND activeBreakId = ?', userId, breakId);

    const updatedBreak = await db.get<BreakLog>('SELECT * FROM break_logs WHERE id = ?', breakId);
    return NextResponse.json(updatedBreak);

  } catch (error) {
    console.error(`Failed to update break log ${params.breakId}:`, error);
    return NextResponse.json({ message: 'Failed to update break log', error: (error as Error).message }, { status: 500 });
  }
}
