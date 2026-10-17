
// src/app/api/messaging/messages/[messageId]/read/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { User } from '@/types';

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
    const userId = req.headers.get('x-user-id');
    if (!userId) return null;
    const db = await getDb();
    if (!db) return null;
    return db.get<User>('SELECT * FROM users WHERE id = ?', userId);
}

// PUT to mark a message as read
export async function PUT(req: NextRequest, { params }: { params: { messageId: string } }) {
    try {
        const currentUser = await getAuthenticatedUser(req);
        if (!currentUser) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }
        
        const db = await getDb();
        if (!db) {
            return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
        }

        const { messageId } = params;
        
        // Update the read_at timestamp for the current user for this specific message
        const result = await db.run(`
            UPDATE message_recipients
            SET read_at = ?
            WHERE message_id = ? AND recipient_id = ? AND read_at IS NULL
        `, [new Date().toISOString(), messageId, currentUser.id]);

        if (result.changes === 0) {
            // This isn't necessarily an error. It could mean the message was already read,
            // or the user isn't a recipient. We can return a specific message for clarity.
            return NextResponse.json({ success: true, message: 'Message was already marked as read or user is not a recipient.' });
        }

        return NextResponse.json({ success: true, message: 'Message marked as read.' });

    } catch (error: any) {
        console.error(`Error marking message ${params.messageId} as read:`, error);
        return NextResponse.json({ error: 'Failed to mark message as read', details: error.message }, { status: 500 });
    }
}
