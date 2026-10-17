// src/app/main/messaging/page.tsx
// This file is now located at /src/app/(main)/messaging/page.tsx
'use client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Mail, PenSquare, Inbox, Send, Loader2, AlertCircle, Trash2, Search, CheckCheck } from 'lucide-react';
import Link from 'next/link';
import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useApp } from '@/context/AppContext';
import { Conversation } from '@/types';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { formatDistanceToNow, parseISO, isValid } from 'date-fns';
import { Badge } from '@/components/ui/badge';
import { useRouter } from 'next/navigation';
import { Input } from '@/components/ui/input';
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
import { useToast } from '@/hooks/use-toast';
import { useDebounce } from 'use-debounce';
import { cn } from '@/lib/utils';


export default function MessagingPage() {
    const { currentUser, deleteConversation: apiDeleteConversation, conversations: contextConversations, isDataLoaded } = useApp();
    const router = useRouter();
    const { toast } = useToast();
    const [isDeleting, setIsDeleting] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [debouncedSearchTerm] = useDebounce(searchTerm, 300);

    const filteredConversations = useMemo(() => {
        const conversations = contextConversations || [];
        if (!debouncedSearchTerm) {
            return conversations;
        }
        return conversations.filter(convo =>
            (convo.subject && convo.subject.toLowerCase().includes(debouncedSearchTerm.toLowerCase())) ||
            (convo.lastMessageContent && convo.lastMessageContent.toLowerCase().includes(debouncedSearchTerm.toLowerCase())) ||
            (convo.participants && convo.participants.toLowerCase().includes(debouncedSearchTerm.toLowerCase()))
        );
    }, [contextConversations, debouncedSearchTerm]);

    const handleDeleteConversation = async (conversationId: string) => {
        setIsDeleting(conversationId);
        try {
            await apiDeleteConversation(conversationId);
            toast({
                title: "Conversation Deleted",
                description: "The conversation has been permanently removed.",
                variant: 'destructive',
            });
        } catch (error: any) {
            toast({
                title: "Error Deleting Conversation",
                description: error.message || "Could not delete the conversation.",
                variant: "destructive",
            });
        } finally {
            setIsDeleting(null);
        }
    };


    const inboxConversations = useMemo(() => {
        const conversations = filteredConversations || [];
        return conversations.filter(c => c.folder === 'inbox');
    }, [filteredConversations]);

    const sentConversations = useMemo(() => {
        const conversations = filteredConversations || [];
        return conversations.filter(c => c.folder === 'sent');
    }, [filteredConversations]);


    const renderConversationList = (convos: Conversation[], emptyMessage: string) => {
        if (!convos || convos.length === 0) {
            return (
                <div className="text-center py-12 text-muted-foreground">
                    <p>{searchTerm ? 'No conversations match your search.' : emptyMessage}</p>
                </div>
            );
        }

        return (
            <div className="space-y-2">
                {convos.map(convo => (
                    <div
                        key={convo.id}
                        className="w-full text-left p-3 border rounded-lg hover:bg-blue-50/50 dark:hover:bg-slate-800/50 transition-colors flex items-start gap-3"
                    >
                        <button
                          className="flex-grow overflow-hidden text-left"
                          onClick={() => router.push(`/messaging/conversations/${convo.id}`)}
                        >
                            <div className="flex justify-between items-center">
                                <p className="text-sm font-semibold truncate" title={convo.subject}>{convo.subject}</p>
                                <div className="flex items-center gap-2">
                                    {convo.unreadCount && convo.unreadCount > 0 && (
                                        <Badge variant="destructive">{convo.unreadCount}</Badge>
                                    )}
                                    {convo.readStatus === 'read' && (
                                        <Badge variant="outline" className="text-xs text-green-600 border-green-300 bg-green-50">
                                            <CheckCheck className="h-3 w-3 mr-1" /> Read
                                        </Badge>
                                    )}
                                     {convo.readStatus === 'unread' && (
                                        <Badge variant="outline" className="text-xs">
                                            <Send className="h-3 w-3 mr-1" /> Sent
                                        </Badge>
                                    )}
                                </div>
                            </div>
                            <p className="text-xs text-muted-foreground truncate">
                                Participants: {convo.participants || '...'}
                            </p>
                            <p className="text-xs text-muted-foreground truncate">
                                <span className="font-medium">{convo.lastMessageSender}:</span> {convo.lastMessageContent}
                            </p>
                        </button>
                        <div className="flex flex-col items-end shrink-0">
                           <div className="text-xs text-muted-foreground text-right mb-2">
                                {convo.lastMessageAt && isValid(parseISO(convo.lastMessageAt)) ?
                                    formatDistanceToNow(parseISO(convo.lastMessageAt), { addSuffix: true }) : '...'}
                            </div>
                            <AlertDialog>
                                <AlertDialogTrigger asChild>
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive/70 hover:text-destructive hover:bg-destructive/10" disabled={isDeleting === convo.id}>
                                        {isDeleting === convo.id ? <Loader2 className="h-4 w-4 animate-spin"/> : <Trash2 className="h-4 w-4"/>}
                                    </Button>
                                </AlertDialogTrigger>
                                <AlertDialogContent>
                                    <AlertDialogHeader>
                                        <AlertDialogTitle>Delete Conversation?</AlertDialogTitle>
                                        <AlertDialogDescription>
                                            This will permanently delete the conversation "{convo.subject}" and all its messages. This action cannot be undone.
                                        </AlertDialogDescription>
                                    </AlertDialogHeader>
                                    <AlertDialogFooter>
                                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                                        <AlertDialogAction onClick={() => handleDeleteConversation(convo.id)} className="bg-destructive hover:bg-destructive/90">
                                            Delete
                                        </AlertDialogAction>
                                    </AlertDialogFooter>
                                </AlertDialogContent>
                            </AlertDialog>
                        </div>
                    </div>
                ))}
            </div>
        );
    }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
                <CardTitle className="text-2xl flex items-center"><Mail className="mr-2 h-7 w-7 text-primary" /> Messaging</CardTitle>
                <CardDescription>Your conversation inbox.</CardDescription>
            </div>
            <div className="w-full md:w-auto flex gap-2">
                <div className="relative flex-grow">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                        type="search"
                        placeholder="Search messages..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="pl-10 h-10 w-full"
                    />
                </div>
                <Button asChild className="h-10">
                    <Link href="/messaging/compose">
                        <PenSquare className="mr-2 h-4 w-4" /> Compose
                    </Link>
                </Button>
            </div>
        </CardHeader>
        <CardContent>
            {!isDataLoaded ? (
                <div className="flex justify-center items-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    <p className="ml-3 text-muted-foreground">Loading conversations...</p>
                </div>
            ) : (
                <Tabs defaultValue="inbox" className="w-full">
                    <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="inbox"><Inbox className="mr-2 h-4 w-4"/>Inbox</TabsTrigger>
                        <TabsTrigger value="sent"><Send className="mr-2 h-4 w-4"/>Sent</TabsTrigger>
                    </TabsList>
                    <TabsContent value="inbox" className="mt-4">
                        <ScrollArea className="h-[calc(100vh-25rem)]">
                            {renderConversationList(inboxConversations, 'Your inbox is empty.')}
                        </ScrollArea>
                    </TabsContent>
                    <TabsContent value="sent" className="mt-4">
                         <ScrollArea className="h-[calc(100vh-25rem)]">
                            {renderConversationList(sentConversations, 'You have not sent any messages.')}
                        </ScrollArea>
                    </TabsContent>
                </Tabs>
            )}
        </CardContent>
      </Card>
    </div>
  );
}
