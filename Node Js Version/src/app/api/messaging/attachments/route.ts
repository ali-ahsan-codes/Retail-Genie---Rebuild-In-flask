
// src/app/api/messaging/attachments/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb, parseUserJSONFields } from '@/lib/server/database';
import type { User, Attachment } from '@/types';

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
    const userId = req.headers.get('x-user-id');
    if (!userId) return null;
    const db = await getDb();
    if (!db) return null;
    const userRaw = await db.get<User>('SELECT id, username, role, permissions FROM users WHERE id = ?', userId);
    return userRaw ? parseUserJSONFields(userRaw) : null;
}

// GET to fetch metadata for a list of attachment IDs
export async function GET(req: NextRequest) {
    try {
        const currentUser = await getAuthenticatedUser(req);
        if (!currentUser) {
            return NextResponse.json({ success: false, error: 'Unauthorized' }, { status: 401 });
        }
        
        const { searchParams } = new URL(req.url);
        const idsParam = searchParams.get('ids');
        if (!idsParam) {
            return NextResponse.json({ success: false, error: 'Attachment IDs are required.' }, { status: 400 });
        }

        const attachmentIds = idsParam.split(',').filter(id => id.trim() !== '');
        if (attachmentIds.length === 0) {
            return NextResponse.json({ success: true, data: [] });
        }

        const db = await getDb();
        if (!db) {
            return NextResponse.json({ success: false, error: 'Database service unavailable' }, { status: 503 });
        }

        // This query fetches attachments if they exist in a conversation the current user is part of.
        // It's a security measure to prevent fetching arbitrary attachments.
        // The join ensures we only get attachments from relevant conversations.
        const query = `
            SELECT DISTINCT a.*
            FROM attachments a
            JOIN messages m ON a.message_id = m.id
            WHERE a.id IN (${attachmentIds.map(() => '?').join(',')})
              AND EXISTS (
                SELECT 1
                FROM messages AS sub_m
                LEFT JOIN message_recipients AS sub_mr ON sub_mr.message_id = sub_m.id
                WHERE sub_m.conversation_id = m.conversation_id
                  AND (sub_m.sender_id = ? OR sub_mr.recipient_id = ?)
            );
        `;
        
        const attachments = await db.all<Attachment[]>(query, [...attachmentIds, currentUser.id, currentUser.id]);

        if (attachments.length < attachmentIds.length) {
            console.warn(`[API Attachments GET] User ${currentUser.id} requested ${attachmentIds.length} attachments but was only authorized for/found ${attachments.length}.`);
        }
        
        return NextResponse.json({ success: true, data: attachments });

    } catch (error: any) {
        console.error('[API Attachments GET] Error fetching attachment details:', error);
        return NextResponse.json({ success: false, error: 'Failed to fetch attachment details', details: error.message }, { status: 500 });
    }
}
