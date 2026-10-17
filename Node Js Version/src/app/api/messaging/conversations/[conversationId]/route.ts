// src/app/api/messaging/conversations/[conversationId]/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { User, Conversation, Message, MessageRecipient, Attachment } from '@/types';
import fs from 'fs/promises';
import path from 'path';

const MESSAGING_UPLOADS_DIR = path.join(process.cwd(), 'uploads', 'messaging');

async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
    const userId = req.headers.get('x-user-id');
    if (!userId) return null;
    const db = await getDb();
    if (!db) return null;
    return db.get<User>('SELECT * FROM users WHERE id = ?', userId);
}

// GET details for a single conversation, including all messages and their recipients
export async function GET(req: NextRequest, { params }: { params: { conversationId: string } }) {
    let db;
    try {
        const currentUser = await getAuthenticatedUser(req);
        if (!currentUser) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }

        db = await getDb();
        if (!db) {
            return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
        }
        
        const { conversationId } = params;
        await db.run('BEGIN TRANSACTION');

        const participantCheck = await db.get(`
            SELECT 1 FROM messages m
            LEFT JOIN message_recipients mr ON mr.message_id = m.id
            WHERE m.conversation_id = ? AND (m.sender_id = ? OR mr.recipient_id = ?)
            LIMIT 1
        `, [conversationId, currentUser.id, currentUser.id]);

        if (!participantCheck) {
            await db.run('ROLLBACK');
            return NextResponse.json({ error: 'Forbidden: You are not a participant of this conversation.' }, { status: 403 });
        }
        
        const conversationRaw = await db.get('SELECT * FROM conversations WHERE id = ?', conversationId);
        if (!conversationRaw) {
            await db.run('ROLLBACK');
            return NextResponse.json({ error: 'Conversation not found' }, { status: 404 });
        }
        
        // Mark messages in this conversation as read for the current user
        await db.run(`
            UPDATE message_recipients
            SET read_at = ?
            WHERE read_at IS NULL AND recipient_id = ? AND message_id IN (
                SELECT id FROM messages WHERE conversation_id = ?
            )
        `, [new Date().toISOString(), currentUser.id, conversationId]);


        const messagesRaw = await db.all<any[]>(`
            SELECT m.*, u.username as senderUsername 
            FROM messages m
            JOIN users u ON u.id = m.sender_id
            WHERE m.conversation_id = ? 
            ORDER BY m.sent_at ASC
        `, conversationId);

        const messages: FullConversation['messages'] = [];
        const participantIds = new Set<string>();

        for (const msgRaw of messagesRaw) {
            const attachments = await db.all<Attachment[]>('SELECT * FROM attachments WHERE message_id = ?', msgRaw.id);
            const recipientsRaw = await db.all<any[]>(`
                SELECT mr.recipient_type, u.id as recipientId, u.username as recipientUsername
                FROM message_recipients mr
                JOIN users u ON u.id = mr.recipient_id
                WHERE mr.message_id = ?
            `, msgRaw.id);
            
            const recipients = recipientsRaw.map(r => ({
                recipient_type: r.recipient_type,
                recipient: {
                    id: r.recipientId,
                    username: r.recipientUsername,
                }
            }));


            messages.push({
                ...msgRaw,
                sender: { id: msgRaw.sender_id, username: msgRaw.senderUsername },
                recipients, // Add detailed recipients here
                attachments,
            });
            participantIds.add(msgRaw.sender_id);
            recipientsRaw.forEach(r => participantIds.add(r.recipientId));
        }

        const participantsList = await db.all<Pick<User, 'id' | 'username'>>(`
            SELECT id, username FROM users WHERE id IN (${Array.from(participantIds).map(() => '?').join(',')})
        `, Array.from(participantIds));

        const conversation: FullConversation = { 
            ...conversationRaw, 
            messages,
            participantsList,
        };
        
        await db.run('COMMIT');

        return NextResponse.json({ success: true, data: conversation });

    } catch (error: any) {
        if(db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
        console.error(`Error fetching conversation ${params.conversationId}:`, error);
        return NextResponse.json({ error: 'Failed to fetch conversation', details: error.message }, { status: 500 });
    }
}


export async function DELETE(req: NextRequest, { params }: { params: { conversationId: string } }) {
    let db;
    try {
        const currentUser = await getAuthenticatedUser(req);
        if (!currentUser) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }

        const { conversationId } = params;
        db = await getDb();
        if (!db) {
            return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
        }

        await db.run('BEGIN TRANSACTION');

        const participantCheck = await db.get(`
            SELECT 1 FROM messages m
            LEFT JOIN message_recipients mr ON mr.message_id = m.id
            WHERE m.conversation_id = ? AND (m.sender_id = ? OR mr.recipient_id = ?)
            LIMIT 1
        `, [conversationId, currentUser.id, currentUser.id]);

        if (!participantCheck) {
            await db.run('ROLLBACK');
            return NextResponse.json({ error: 'Forbidden: You are not a participant of this conversation.' }, { status: 403 });
        }
        
        const messageIdsResult = await db.all<{ id: string }>('SELECT id FROM messages WHERE conversation_id = ?', conversationId);
        const messageIds = messageIdsResult.map(m => m.id);

        if (messageIds.length > 0) {
            const placeholders = messageIds.map(() => '?').join(',');
            await db.run(`DELETE FROM attachments WHERE message_id IN (${placeholders})`, messageIds);
            await db.run(`DELETE FROM message_recipients WHERE message_id IN (${placeholders})`, messageIds);
            await db.run(`DELETE FROM messages WHERE conversation_id = ?`, conversationId);
        }

        await db.run('DELETE FROM conversations WHERE id = ?', conversationId);

        const conversationUploadDir = path.join(MESSAGING_UPLOADS_DIR, conversationId);
        try {
            await fs.rm(conversationUploadDir, { recursive: true, force: true });
        } catch (fileError) {
            console.warn(`Could not delete attachment directory ${conversationUploadDir}:`, fileError);
        }

        await db.run('COMMIT');

        return NextResponse.json({ success: true, message: 'Conversation deleted successfully.' });

    } catch (error: any) {
        if(db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
        console.error(`Error deleting conversation ${params.conversationId}:`, error);
        return NextResponse.json({ error: 'Failed to delete conversation', details: error.message }, { status: 500 });
    }
}

interface FullConversation extends Conversation {
    messages: (Message & { 
        sender?: Pick<User, 'id' | 'username'>;
        recipients?: Partial<MessageRecipient>[];
        attachments?: Attachment[];
    })[];
    participantsList?: Pick<User, 'id' | 'username'>[];
}
