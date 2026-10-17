
// src/app/main/messaging/conversations/[conversationId]/page.tsx
'use client';

import React, { useEffect, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { ArrowLeft, Loader2, AlertCircle, Paperclip, Send, CornerDownLeft, Forward, FileText, Type, Check, XIcon } from 'lucide-react';
import type { Conversation, Message, User, Attachment, MessageRecipient } from '@/types';
import { format, formatDistanceToNow, parseISO, isValid } from 'date-fns';
import { useToast } from '@/hooks/use-toast';
import AttachmentManager from '@/components/messaging/AttachmentManager';
import { Separator } from '@/components/ui/separator';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";


interface FullConversation extends Conversation {
  messages: (Message & { 
      sender?: Pick<User, 'id' | 'username'>;
      recipients?: Partial<MessageRecipient & { recipient: Pick<User, 'id'|'username'> }>[];
      attachments?: Attachment[];
  })[];
  participantsList?: Pick<User, 'id' | 'username'>[];
}

export default function ConversationViewPage() {
  const params = useParams();
  const router = useRouter();
  const { currentUser, replyToConversation } = useApp();
  const { toast } = useToast();
  const conversationId = params.conversationId as string;

  const [conversation, setConversation] = useState<FullConversation | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [replyContent, setReplyContent] = useState('');
  const [replyAttachments, setReplyAttachments] = useState<File[]>([]);
  const [isReplying, setIsReplying] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const replyTextareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    async function fetchConversation() {
      if (!currentUser || !conversationId) return;
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/messaging/conversations/${conversationId}`, {
          headers: { 'x-user-id': currentUser.id }
        });
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.error || `Failed to fetch conversation. Status: ${response.status}`);
        }
        const result = await response.json();
        if (result.success) {
          setConversation(result.data);
        } else {
          throw new Error(result.error || "An unknown error occurred.");
        }
      } catch (err: any) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    }
    fetchConversation();
  }, [currentUser, conversationId]);

  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollViewport = scrollAreaRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (scrollViewport) {
          setTimeout(() => {
            scrollViewport.scrollTop = scrollViewport.scrollHeight;
          }, 100);
      }
    }
  }, [conversation]);

  const handleReplyToMessage = (message: Message) => {
    const senderName = message.sender?.username || 'user';
    const sentDate = isValid(parseISO(message.sent_at)) ? format(parseISO(message.sent_at), 'MMM d, yyyy p') : 'a while ago';
    const quotedText = `\n\n--- On ${sentDate}, ${senderName} wrote: ---\n> ${message.content.replace(/\n/g, '\n> ')}\n`;
    setReplyContent(quotedText);
    replyTextareaRef.current?.focus();
    replyTextareaRef.current?.setSelectionRange(0, 0); 
  };
  
  const handleForwardMessage = (message: Message, includeAttachments: boolean) => {
    const forwardedSubject = `Fwd: ${conversation?.subject}`;
    const senderName = message.sender?.username || 'user';
    const sentDate = isValid(parseISO(message.sent_at)) ? format(parseISO(message.sent_at), 'MMM d, yyyy p') : 'a while ago';

    const quotedContent = `\n\n--- Forwarded message ---\nFrom: ${senderName}\nDate: ${sentDate}\nSubject: ${conversation?.subject}\n\n${message.content}`;
    
    const query = new URLSearchParams({
      subject: forwardedSubject,
      content: quotedContent,
    });
    
    if (includeAttachments && message.attachments && message.attachments.length > 0) {
        // Instead of passing IDs, pass the full attachment metadata as a JSON string
        // This avoids the extra failing API call from the compose page.
        const attachmentData = message.attachments.map(att => ({
            id: att.id,
            original_name: att.original_name,
        }));
        query.set('forwardAttachments', JSON.stringify(attachmentData));
    }
    
    router.push(`/messaging/compose?${query.toString()}`);
  };


  const handleSendReply = async () => {
    if (!replyContent.trim() || !conversation) {
        toast({ title: "Error", description: "Reply content cannot be empty.", variant: "destructive"});
        return;
    }
    setIsReplying(true);
    
    const lastMessage = conversation.messages[conversation.messages.length - 1];
    let toRecipients: string[] = [];
    
    if (lastMessage.sender?.id === currentUser?.id) {
        const otherParticipantIds = (conversation.participantsList || [])
            .map(p => p.id)
            .filter(id => id !== currentUser?.id);

        if (otherParticipantIds.length > 0) {
            toRecipients = [...new Set(otherParticipantIds)];
        } else {
            toRecipients = [currentUser.id];
        }
    } else {
        if (lastMessage.sender?.id) {
            toRecipients = [lastMessage.sender.id];
        }
    }

    if (toRecipients.length === 0) {
        toast({ title: "Error", description: "Could not determine a recipient for the reply.", variant: "destructive"});
        setIsReplying(false);
        return;
    }

    const result = await replyToConversation(
        conversationId,
        replyContent,
        toRecipients,
        [], 
        [], 
        replyAttachments
    );
    if(result) {
        setReplyContent('');
        setReplyAttachments([]);
        const response = await fetch(`/api/messaging/conversations/${conversationId}`, { headers: { 'x-user-id': currentUser!.id } });
        const updatedResult = await response.json();
        if(updatedResult.success) setConversation(updatedResult.data);
    }
    setIsReplying(false);
  };


  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="ml-3 text-muted-foreground">Loading conversation...</p>
      </div>
    );
  }

  if (error) {
    return (
      <Card className="shadow-md">
        <CardHeader><CardTitle className="text-destructive">Error</CardTitle></CardHeader>
        <CardContent className="text-center py-12 text-destructive">
          <AlertCircle className="h-8 w-8 mx-auto mb-2" />
          <p>Could not load conversation: {error}</p>
          <Button variant="outline" className="mt-4" onClick={() => router.push('/messaging')}>
            <ArrowLeft className="mr-2 h-4 w-4" /> Back to Inbox
          </Button>
        </CardContent>
      </Card>
    );
  }
  
  if (!conversation) {
     return (
      <Card className="shadow-md">
        <CardHeader><CardTitle>Not Found</CardTitle></CardHeader>
        <CardContent className="text-center py-12 text-muted-foreground">
          <p>The requested conversation could not be found.</p>
          <Button variant="outline" className="mt-4" onClick={() => router.push('/messaging')}>
             <ArrowLeft className="mr-2 h-4 w-4" /> Back to Inbox
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <Card className="shadow-md flex-1 flex flex-col">
        <CardHeader className="border-b">
          <div className="flex items-center gap-3">
             <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => router.push('/messaging')}>
                <ArrowLeft className="h-4 w-4" />
             </Button>
             <div>
                <CardTitle className="text-xl">{conversation.subject}</CardTitle>
                <CardDescription className="text-xs">
                    Participants: {conversation.participantsList?.map(p => p.username).join(', ') || '...'}
                </CardDescription>
             </div>
          </div>
        </CardHeader>
        <CardContent className="p-0 flex-1 overflow-hidden">
          <ScrollArea className="h-full" ref={scrollAreaRef}>
            <div className="p-4 space-y-6">
              {conversation.messages.map(message => {
                 const toRecipients = message.recipients?.filter(r => r.recipient_type === 'to').map(r => r.recipient?.username).join(', ');
                 const ccRecipients = message.recipients?.filter(r => r.recipient_type === 'cc').map(r => r.recipient?.username).join(', ');
                 return (
                  <div key={message.id} className="flex gap-4">
                    <Avatar className="mt-1">
                      <AvatarFallback>{message.sender?.username?.charAt(0).toUpperCase() || '?'}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 border rounded-lg overflow-hidden shadow-sm">
                      <div className="bg-muted/30 px-4 py-2 border-b text-xs text-muted-foreground">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4">
                           <p><strong>From:</strong> {message.sender?.username}</p>
                           <p><strong>Date:</strong> {isValid(parseISO(message.sent_at)) ? format(parseISO(message.sent_at), 'PPpp') : '...'}</p>
                           {toRecipients && <p className="col-span-full"><strong>To:</strong> {toRecipients}</p>}
                           {ccRecipients && <p className="col-span-full"><strong>Cc:</strong> {ccRecipients}</p>}
                        </div>
                      </div>
                      <div className="p-4 space-y-4">
                         <div className="flex items-start gap-2">
                             <h3 className="text-sm font-semibold text-muted-foreground">Subject:</h3>
                             <h3 className="text-sm font-semibold">{conversation.subject}</h3>
                         </div>
                         <Separator />
                        <div className="text-sm whitespace-pre-wrap">
                          {message.content}
                        </div>
                        {message.attachments && message.attachments.length > 0 && (
                            <div className="mt-4 pt-3 border-t space-y-2">
                                {message.attachments.map(att => (
                                    <a key={att.id} href={`/api/uploads/${att.file_path}`} target="_blank" rel="noopener noreferrer" className="text-xs inline-flex items-center gap-1.5 p-1.5 border rounded-md hover:bg-accent transition-colors">
                                        <Paperclip className="h-3 w-3" />
                                        {att.original_name}
                                    </a>
                                ))}
                            </div>
                        )}
                        <div className="text-right mt-3 flex justify-end gap-1">
                          {(message.attachments && message.attachments.length > 0) ? (
                              <AlertDialog>
                                <AlertDialogTrigger asChild>
                                  <Button variant="ghost" size="sm" className="h-7 text-xs"><Forward className="mr-1 h-3 w-3" />Forward</Button>
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                  <AlertDialogHeader>
                                    <AlertDialogTitle>Forward with attachments?</AlertDialogTitle>
                                    <AlertDialogDescription>
                                      Do you want to include the attachments from this message in your forward?
                                    </AlertDialogDescription>
                                  </AlertDialogHeader>
                                  <AlertDialogFooter>
                                    <AlertDialogAction onClick={() => handleForwardMessage(message, false)} variant="outline">
                                        No
                                    </AlertDialogAction>
                                    <AlertDialogAction onClick={() => handleForwardMessage(message, true)}>
                                        Yes
                                    </AlertDialogAction>
                                  </AlertDialogFooter>
                                </AlertDialogContent>
                              </AlertDialog>
                          ) : (
                            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => handleForwardMessage(message, false)}>
                                <Forward className="mr-1 h-3 w-3" />
                                Forward
                            </Button>
                          )}
                            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => handleReplyToMessage(message)}>
                                <CornerDownLeft className="mr-1 h-3 w-3" />
                                Reply
                            </Button>
                        </div>
                      </div>
                    </div>
                  </div>
              )})}
            </div>
          </ScrollArea>
        </CardContent>
        <CardFooter className="p-4 border-t bg-background">
          <div className="w-full space-y-3">
              <Textarea
                ref={replyTextareaRef}
                placeholder="Type your reply here..."
                value={replyContent}
                onChange={(e) => setReplyContent(e.target.value)}
                rows={4}
                disabled={isReplying}
              />
              <AttachmentManager files={replyAttachments} onFilesChange={setReplyAttachments} />
              <div className="flex justify-end">
                <Button onClick={handleSendReply} disabled={!replyContent.trim() || isReplying}>
                    {isReplying ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : <Send className="mr-2 h-4 w-4" />}
                    {isReplying ? "Replying..." : "Send Reply"}
                </Button>
              </div>
          </div>
        </CardFooter>
      </Card>
    </div>
  );
}
