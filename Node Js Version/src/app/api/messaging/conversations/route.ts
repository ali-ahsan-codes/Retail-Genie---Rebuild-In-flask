// src/app/api/messaging/conversations/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { User, Conversation } from '@/types';
import fs from 'fs/promises';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';

const MESSAGING_UPLOADS_DIR = path.join(process.cwd(), 'uploads', 'messaging');
const UPLOADS_BASE_DIR = path.join(process.cwd(), 'uploads');
const MAX_MESSAGE_LENGTH = 3500;


async function getAuthenticatedUser(req: NextRequest): Promise<User | null> {
    const userId = req.headers.get('x-user-id');
    if (!userId) return null;
    const db = await getDb();
    if (!db) return null;
    return db.get<User>('SELECT * FROM users WHERE id = ?', userId);
}

// POST to start a new conversation
export async function POST(req: NextRequest) {
    let db;
    try {
        const sender = await getAuthenticatedUser(req);
        if (!sender) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }

        const formData = await req.formData();
        const subject = formData.get('subject') as string;
        const content = formData.get('content') as string;
        const toRecipients = formData.getAll('to[]') as string[];
        const ccRecipients = formData.getAll('cc[]') as string[];
        const bccRecipients = formData.getAll('bcc[]') as string[];
        const attachments = formData.getAll('attachments') as File[];
        const forwardedAttachmentIds = formData.getAll('forwardedAttachmentIds[]') as string[];


        if (!subject || !content || toRecipients.length === 0) {
            return NextResponse.json({ error: 'Subject, content, and at least one "To" recipient are required.' }, { status: 400 });
        }

        if (content.length > MAX_MESSAGE_LENGTH) {
            return NextResponse.json({ error: `Message content exceeds the maximum length of ${MAX_MESSAGE_LENGTH} characters.` }, { status: 400 });
        }


        db = await getDb();
        if (!db) {
            return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
        }

        await db.run('BEGIN TRANSACTION');

        // 1. Create Conversation
        const conversationId = uuidv4();
        const now = new Date().toISOString();
        await db.run('INSERT INTO conversations (id, subject, created_at, creator_id) VALUES (?, ?, ?, ?)', [conversationId, subject, now, sender.id]);

        // 2. Create Message
        const messageId = uuidv4();
        await db.run('INSERT INTO messages (id, conversation_id, sender_id, content, sent_at) VALUES (?, ?, ?, ?, ?)', [messageId, conversationId, sender.id, content, now]);

        // 3. Add Recipients
        const allRecipients = new Map<string, 'to' | 'cc' | 'bcc'>();
        toRecipients.forEach(id => allRecipients.set(id, 'to'));
        ccRecipients.forEach(id => allRecipients.set(id, 'cc'));
        bccRecipients.forEach(id => allRecipients.set(id, 'bcc'));

        for (const [recipientId, type] of allRecipients.entries()) {
            await db.run('INSERT INTO message_recipients (id, message_id, recipient_id, recipient_type) VALUES (?, ?, ?, ?)', [uuidv4(), messageId, recipientId, type]);
        }

        const conversationDir = path.join(MESSAGING_UPLOADS_DIR, conversationId);
        const messageDir = path.join(conversationDir, messageId);
        
        // Ensure directory exists for any type of attachment
        if(attachments.length > 0 || forwardedAttachmentIds.length > 0) {
            await fs.mkdir(messageDir, { recursive: true });
        }

        // 4. Handle Attachments (newly uploaded)
        for (const file of attachments) {
            const attachmentId = uuidv4();
            const fileExtension = path.extname(file.name) || '';
            const savedFileName = `${attachmentId}${fileExtension}`;
            const filePathOnDisk = path.join(messageDir, savedFileName);
            
            const buffer = Buffer.from(await file.arrayBuffer());
            await fs.writeFile(filePathOnDisk, buffer);

            const relativeDbPath = `messaging/${conversationId}/${messageId}/${savedFileName}`;

            await db.run('INSERT INTO attachments (id, message_id, file_path, original_name, mime_type) VALUES (?, ?, ?, ?, ?)', [attachmentId, messageId, relativeDbPath, file.name, file.type]);
        }
        

        // 5. Handle Forwarded Attachments
        if (forwardedAttachmentIds.length > 0) {
            const placeholders = forwardedAttachmentIds.map(() => '?').join(',');
            const originalAttachments = await db.all(`SELECT * FROM attachments WHERE id IN (${placeholders})`, forwardedAttachmentIds);
            
            for (const origAtt of originalAttachments) {
                const newForwardedAttachmentId = uuidv4();
                const originalFilePathOnDisk = path.join(UPLOADS_BASE_DIR, origAtt.file_path);
                const fileExtension = path.extname(origAtt.original_name) || '';
                const newSavedFileName = `${newForwardedAttachmentId}${fileExtension}`;
                const newFilePathOnDisk = path.join(messageDir, newSavedFileName);
                const newRelativeDbPath = `messaging/${conversationId}/${messageId}/${newSavedFileName}`;

                try {
                    await fs.copyFile(originalFilePathOnDisk, newFilePathOnDisk);
                    await db.run('INSERT INTO attachments (id, message_id, file_path, original_name, mime_type) VALUES (?, ?, ?, ?, ?)', 
                        [newForwardedAttachmentId, messageId, newRelativeDbPath, origAtt.original_name, origAtt.mime_type]
                    );
                } catch(copyError) {
                    console.error(`Failed to copy forwarded attachment from ${originalFilePathOnDisk} to ${newFilePathOnDisk}`, copyError);
                    // Decide if you should rollback or just skip this attachment
                }
            }
        }


        await db.run('COMMIT');

        const newConversationRaw = await db.get('SELECT * FROM conversations WHERE id = ?', conversationId);
        
        if (newConversationRaw) {
            return NextResponse.json({ success: true, data: { ...newConversationRaw, id: newConversationRaw.id, conversation_id: newConversationRaw.id } }, { status: 201 });
        } else {
            return NextResponse.json({ success: false, error: 'Failed to retrieve conversation after creation.' }, { status: 500 });
        }

    } catch (error: any) {
        if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
        console.error('Error creating conversation:', error);
        return NextResponse.json({ error: 'Failed to create conversation', details: error.message }, { status: 500 });
    }
}


// GET to list conversations for the current user
export async function GET(req: NextRequest) {
    try {
        const currentUser = await getAuthenticatedUser(req);
        if (!currentUser) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }
        
        const db = await getDb();
        if (!db) {
            return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
        }
        
        // Step 1: Get all conversation IDs the user is part of.
        const conversationIdsRaw = await db.all<{ conversation_id: string }>(`
            SELECT DISTINCT c.id as conversation_id
            FROM conversations c
            JOIN messages m ON m.conversation_id = c.id
            LEFT JOIN message_recipients mr ON mr.message_id = m.id
            WHERE m.sender_id = ? OR mr.recipient_id = ?
        `, [currentUser.id, currentUser.id]);
        
        const conversationIds = conversationIdsRaw.map(r => r.conversation_id);
        if (conversationIds.length === 0) {
            return NextResponse.json({ success: true, data: [] });
        }

        const enrichedConversations = [];

        // Step 2: Loop through each conversation ID to get its details.
        for (const convoId of conversationIds) {
            const convoRaw = await db.get('SELECT * FROM conversations WHERE id = ?', convoId);
            if (!convoRaw) continue;

            // Get last message details
            const lastMessage = await db.get(`
                SELECT m.id, m.sender_id, m.content, m.sent_at, u.username as senderUsername
                FROM messages m
                JOIN users u ON u.id = m.sender_id
                WHERE m.conversation_id = ?
                ORDER BY m.sent_at DESC
                LIMIT 1
            `, convoId);

            // Get all participants
            const participants = await db.all<{ username: string }>(`
                SELECT DISTINCT u.username FROM users u
                JOIN (
                    SELECT sender_id as user_id FROM messages WHERE conversation_id = ?
                    UNION
                    SELECT recipient_id as user_id FROM message_recipients mr JOIN messages m ON m.id = mr.message_id WHERE m.conversation_id = ?
                ) as participants_ids ON u.id = participants_ids.user_id
            `, [convoId, convoId]);

            // Get unread count for current user
            const unreadCountResult = await db.get<{ count: number }>(`
                SELECT COUNT(*) as count FROM message_recipients mr
                JOIN messages m ON m.id = mr.message_id
                WHERE m.conversation_id = ? AND mr.recipient_id = ? AND mr.read_at IS NULL
            `, [convoId, currentUser.id]);

            // Determine read status if sender is the current user
            let readStatus: 'read' | 'unread' | 'none' = 'none';
            if (lastMessage && lastMessage.sender_id === currentUser.id) {
                const recipients = await db.all<{ read_at: string | null }>(
                    'SELECT read_at FROM message_recipients WHERE message_id = ?',
                    lastMessage.id
                );
                if (recipients.length > 0 && recipients.every(r => r.read_at !== null)) {
                    readStatus = 'read';
                } else if (recipients.length > 0) {
                    readStatus = 'unread';
                }
            }

            enrichedConversations.push({
                ...convoRaw,
                folder: lastMessage?.sender_id === currentUser.id ? 'sent' : 'inbox',
                lastMessageContent: lastMessage?.content,
                lastMessageAt: lastMessage?.sent_at,
                lastMessageSender: lastMessage?.senderUsername,
                participants: participants.map((p: any) => p.username).join(', '),
                unreadCount: unreadCountResult?.count || 0,
                readStatus,
            });
        }

        enrichedConversations.sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime());

        return NextResponse.json({ success: true, data: enrichedConversations });

    } catch (error: any) {
        console.error('Error fetching conversations:', error);
        return NextResponse.json({ error: 'Failed to fetch conversations', details: error.message }, { status: 500 });
    }
}
