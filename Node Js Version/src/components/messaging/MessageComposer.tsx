// src/components/messaging/MessageComposer.tsx
'use client';
import React, { useState, useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Send, Paperclip, X, Loader2, File as FileIcon } from 'lucide-react';
import RecipientField from './RecipientField';
import AttachmentManager from './AttachmentManager';
import { useRouter } from 'next/navigation';
import { Attachment } from '@/types';
import { useToast } from '@/hooks/use-toast';

const MAX_MESSAGE_LENGTH = 3500;

const messageSchema = z.object({
  to: z.array(z.string()).min(1, 'At least one "To" recipient is required.'),
  cc: z.array(z.string()).optional(),
  bcc: z.array(z.string()).optional(),
  subject: z.string().min(1, 'Subject is required.'),
  content: z.string().min(1, 'Message content cannot be empty.').max(MAX_MESSAGE_LENGTH, `Message cannot exceed ${MAX_MESSAGE_LENGTH} characters.`),
  attachments: z.array(z.instanceof(File)).optional(),
  conversationId: z.string().optional(),
});

type MessageFormValues = z.infer<typeof messageSchema>;

type ForwardedAttachmentInfo = {
  id: string;
  original_name: string;
};

interface MessageComposerProps {
  onSend: (data: MessageFormValues & { forwardedAttachmentIds?: string[] }) => Promise<void>;
  onCancel: () => void;
  initialSubject?: string | null;
  initialContent?: string | null;
  initialForwardedAttachmentIdsParam?: string | null;
}

export default function MessageComposer({ onSend, onCancel, initialSubject, initialContent, initialForwardedAttachmentIdsParam }: MessageComposerProps) {
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();
  
  const [forwardedAttachments, setForwardedAttachments] = useState<ForwardedAttachmentInfo[]>([]);
  const { currentUser } = useApp();

  useEffect(() => {
    async function fetchForwardedAttachmentDetails() {
      if (!initialForwardedAttachmentIdsParam) {
        setForwardedAttachments([]);
        return;
      }
      try {
        const response = await fetch(`/api/messaging/attachments?ids=${initialForwardedAttachmentIdsParam}`, {
          headers: {
            'x-user-id': currentUser?.id || '',
          }
        });

        if (!response.ok) {
          throw new Error("Failed to fetch attachment details.");
        }
        const data = await response.json();
        if (data.success) {
          setForwardedAttachments(data.data.map((att: Attachment) => ({ id: att.id, original_name: att.original_name })));
        } else {
            throw new Error(data.error || "Could not load forwarded attachments.");
        }
        
      } catch (e: any) {
        console.error("Failed to parse or fetch forwarded attachments:", e);
        toast({
          title: "Attachment Error",
          description: e.message,
          variant: "destructive"
        });
        setForwardedAttachments([]);
      }
    }
    if(currentUser?.id) {
        fetchForwardedAttachmentDetails();
    }
  }, [initialForwardedAttachmentIdsParam, toast, currentUser]);


  const form = useForm<MessageFormValues>({
    resolver: zodResolver(messageSchema),
    defaultValues: {
      to: [],
      cc: [],
      bcc: [],
      subject: initialSubject || '',
      content: initialContent || '',
      attachments: [],
    },
  });

  const { control, handleSubmit, setValue, watch, reset } = form;
  const attachments = watch('attachments') || [];
  const contentValue = watch('content') || '';

  useEffect(() => {
    reset({
      to: [],
      cc: [],
      bcc: [],
      subject: initialSubject || '',
      content: initialContent || '',
      attachments: [],
    });
  }, [initialSubject, initialContent, reset]);

  const handleAttachmentsChange = (files: File[]) => {
    setValue('attachments', files);
  };

  const processSubmit = async (data: MessageFormValues) => {
    setIsLoading(true);
    const forwardedAttachmentIds = forwardedAttachments.map(att => att.id);
    await onSend({ ...data, forwardedAttachmentIds });
    setIsLoading(false);
  };
  
  const removeForwardedAttachment = (idToRemove: string) => {
    setForwardedAttachments(prev => prev.filter(att => att.id !== idToRemove));
  };


  return (
    <form onSubmit={handleSubmit(processSubmit)} className="space-y-4">
      <Controller
        name="to"
        control={control}
        render={({ field, fieldState }) => (
          <div>
            <RecipientField label="To:" onRecipientsChange={field.onChange} />
            {fieldState.error && <p className="text-sm text-destructive mt-1">{fieldState.error.message}</p>}
          </div>
        )}
      />
      <Controller
        name="cc"
        control={control}
        render={({ field }) => <RecipientField label="Cc:" onRecipientsChange={field.onChange} />}
      />
      <Controller
        name="bcc"
        control={control}
        render={({ field }) => <RecipientField label="Bcc:" onRecipientsChange={field.onChange} />}
      />

      <div className="space-y-1">
        <Label htmlFor="subject">Subject</Label>
        <Input id="subject" {...form.register('subject')} placeholder="Message subject" />
        {form.formState.errors.subject && <p className="text-sm text-destructive mt-1">{form.formState.errors.subject.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="content">Message</Label>
        <Textarea 
            id="content" 
            {...form.register('content')} 
            placeholder="Compose your message..." 
            rows={10} 
            maxLength={MAX_MESSAGE_LENGTH}
        />
        <div className="flex justify-between text-xs text-muted-foreground">
            {form.formState.errors.content && <p className="text-destructive">{form.formState.errors.content.message}</p>}
            <p className="ml-auto">{contentValue.length} / {MAX_MESSAGE_LENGTH}</p>
        </div>
      </div>
      
      {forwardedAttachments.length > 0 && (
        <div className="space-y-2">
            <h4 className="text-sm font-medium">Forwarded Attachments:</h4>
            {forwardedAttachments.map(att => (
              <div key={att.id} className="flex items-center justify-between p-2 border rounded-md bg-blue-50/50">
                <div className="flex items-center gap-2 overflow-hidden">
                  <FileIcon className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-sm truncate" title={att.original_name}>{att.original_name}</span>
                </div>
                <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeForwardedAttachment(att.id)}>
                  <X className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            ))}
        </div>
      )}

      <AttachmentManager files={attachments} onFilesChange={handleAttachmentsChange} />

      <div className="flex justify-end gap-3 pt-4">
        <Button type="button" variant="outline" onClick={onCancel} disabled={isLoading}>
          <X className="mr-2 h-4 w-4" /> Cancel
        </Button>
        <Button type="submit" disabled={isLoading}>
          {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
          {isLoading ? 'Sending...' : 'Send Message'}
        </Button>
      </div>
    </form>
  );
}
