// src/app/api/messaging/conversations/[conversationId]/messages/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/server/database';
import type { User, Message } from '@/types';
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


// POST to reply to a conversation
export async function POST(req: NextRequest, { params }: { params: { conversationId: string } }) {
    let db;
    try {
        const sender = await getAuthenticatedUser(req);
        if (!sender) {
            return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
        }

        db = await getDb();
        if (!db) {
            return NextResponse.json({ error: 'Database service unavailable' }, { status: 503 });
        }
        
        const { conversationId } = params;

        await db.run('BEGIN TRANSACTION');

        // Security Check: Ensure the current user is part of this conversation
        const participantCheck = await db.get(`
            SELECT 1 FROM messages m
            LEFT JOIN message_recipients mr ON mr.message_id = m.id
            WHERE m.conversation_id = ? AND (m.sender_id = ? OR mr.recipient_id = ?)
            LIMIT 1
        `, [conversationId, sender.id, sender.id]);
        
        if (!participantCheck) {
            await db.run('ROLLBACK');
            return NextResponse.json({ error: 'Forbidden: You cannot reply to a conversation you are not part of.' }, { status: 403 });
        }

        const formData = await req.formData();
        const content = formData.get('content') as string;
        const toRecipients = formData.getAll('to[]') as string[];
        const ccRecipients = formData.getAll('cc[]') as string[];
        const bccRecipients = formData.getAll('bcc[]') as string[];
        const attachments = formData.getAll('attachments') as File[];
        const forwardedAttachmentIds = formData.getAll('forwardedAttachments[]') as string[];

        if (!content || toRecipients.length === 0) {
            await db.run('ROLLBACK');
            return NextResponse.json({ error: 'Content and at least one "To" recipient are required.' }, { status: 400 });
        }

        if (content.length > MAX_MESSAGE_LENGTH) {
            return NextResponse.json({ error: `Message content exceeds the maximum length of ${MAX_MESSAGE_LENGTH} characters.` }, { status: 400 });
        }

        // 1. Create Message
        const messageId = uuidv4();
        const now = new Date().toISOString();
        await db.run('INSERT INTO messages (id, conversation_id, sender_id, content, sent_at) VALUES (?, ?, ?, ?, ?)', [messageId, conversationId, sender.id, content, now]);

        // 2. Add Recipients
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
        
        // 3. Handle Attachments (newly uploaded)
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

        // 4. Handle Forwarded Attachments (same logic as new conversation)
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
                }
            }
        }
        
        await db.run('COMMIT');

        const newMessageRaw = await db.get('SELECT * FROM messages WHERE id = ?', messageId);
        
        if (newMessageRaw) {
            return NextResponse.json({ success: true, data: newMessageRaw }, { status: 201 });
        } else {
            return NextResponse.json({ success: false, error: 'Failed to retrieve message after sending reply.' }, { status: 500 });
        }

    } catch (error: any) {
        if (db) await db.run('ROLLBACK').catch(e => console.error("Rollback failed:", e));
        console.error('Error replying to conversation:', error);
        return NextResponse.json({ error: 'Failed to send reply', details: error.message }, { status: 500 });
    }
}
