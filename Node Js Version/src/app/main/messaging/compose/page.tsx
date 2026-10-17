// src/app/(main)/messaging/compose/page.tsx
'use client';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { PenSquare } from 'lucide-react';
import React from 'react';
import MessageComposer from '@/components/messaging/MessageComposer';
import { useRouter, useSearchParams } from 'next/navigation';
import { useApp } from '@/context/AppContext';

export default function ComposeMessagePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { sendNewMessage, replyToConversation } = useApp();

  const handleSend = async (data: any) => {
    const { to, cc, bcc, subject, content, attachments, forwardedAttachmentIds } = data;
    let result = null;

    if (data.conversationId) { // Replying doesn't involve forwarding in this flow
      result = await replyToConversation(
        data.conversationId,
        content,
        to,
        cc,
        bcc,
        attachments
      );
    } else { // New or Forwarded message
      result = await sendNewMessage(
        subject,
        content,
        to,
        cc,
        bcc,
        attachments,
        forwardedAttachmentIds // Pass the IDs here
      );
    }
    
    if (result) {
      router.push(`/messaging/conversations/${result.conversation_id}`);
    }
  };

  const initialSubject = searchParams.get('subject') || undefined;
  const initialContent = searchParams.get('content') || undefined;
  const forwardedAttachmentIdsParam = searchParams.get('forwardAttachments');

  return (
    <div className="space-y-6">
       <Card className="shadow-md">
        <CardHeader>
            <CardTitle className="text-2xl flex items-center"><PenSquare className="mr-2 h-7 w-7 text-primary" /> Compose Message</CardTitle>
            <CardDescription>Create and send a new message to other users.</CardDescription>
        </CardHeader>
        <CardContent>
          <MessageComposer 
            onSend={handleSend}
            onCancel={() => router.back()}
            initialSubject={initialSubject}
            initialContent={initialContent}
            initialForwardedAttachmentIdsParam={forwardedAttachmentIdsParam}
          />
        </CardContent>
      </Card>
    </div>
  );
}
