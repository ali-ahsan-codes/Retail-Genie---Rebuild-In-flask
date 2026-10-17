
// src/components/cloud/NotesEditor.tsx
'use client';
import { useState, useEffect } from 'react';
import type { CloudFileMetadata } from '@/types';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { Loader2 } from 'lucide-react';
import { useApp } from '@/context/AppContext';

interface NotesEditorProps {
  file: CloudFileMetadata;
  onNotesUpdated: (updatedFile: CloudFileMetadata) => void;
  ownerUserId?: string; // ID of the user who owns the file (for admin editing)
  canEdit?: boolean;    // Explicit prop to control editability, useful for admin page
}

export default function NotesEditor({ file, onNotesUpdated, ownerUserId, canEdit: explicitCanEdit }: NotesEditorProps) {
  const { currentUser } = useApp();
  const [notes, setNotes] = useState(file.notes || '');
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    setNotes(file.notes || '');
  }, [file.notes, file.file_id]);

  // Determine if the current user can edit these notes.
  // If explicitCanEdit is passed (e.g., true from admin page), respect that.
  // Otherwise, default to checking if the current user is the file owner.
  const canActuallyEdit = explicitCanEdit !== undefined ? explicitCanEdit : (currentUser && file.userId === currentUser.id);

  const handleSaveNotes = async () => {
    if (!currentUser) {
      toast({ title: 'Error', description: 'User not authenticated.', variant: 'destructive' });
      return;
    }

    // The user ID to use for the API call: ownerUserId if provided (admin editing), else currentUser.id.
    const effectiveUserIdForApi = ownerUserId || file.userId;

    if (!effectiveUserIdForApi) {
        toast({ title: 'Error', description: 'File owner ID could not be determined for saving notes.', variant: 'destructive' });
        return;
    }
    
    // Check if the current user is authorized to save notes for this effectiveUserId
    // (Admin can edit any, regular user can only edit their own)
    if (!(currentUser.role === 'admin' || currentUser.role === 'manager' || effectiveUserIdForApi === currentUser.id)) {
        toast({ title: 'Permission Denied', description: 'You do not have permission to edit notes for this file.', variant: 'destructive'});
        return;
    }


    setIsLoading(true);
    try {
      const response = await fetch(`/api/cloud/file/${file.file_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes, userId: effectiveUserIdForApi }), // Send the actual owner's ID
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Failed to update notes.' }));
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }

      const result = await response.json();
      if (result.success && result.data) {
        toast({ title: 'Notes Saved', description: `Notes for ${file.original_filename} updated.` });
        onNotesUpdated(result.data);
      } else {
        throw new Error(result.error || 'Failed to save notes due to API error.');
      }
    } catch (error: any) {
      console.error('Error saving notes:', error);
      toast({
        title: 'Error Saving Notes',
        description: error.message || 'An unexpected error occurred.',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <Textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder={canActuallyEdit ? "Add/Edit notes for this file..." : (notes ? "Notes (view only)" : "No notes")}
        className="min-h-[60px] text-xs"
        disabled={isLoading || !canActuallyEdit}
        readOnly={!canActuallyEdit}
      />
      {canActuallyEdit && (
        <Button onClick={handleSaveNotes} size="sm" className="w-full sm:w-auto" disabled={isLoading || notes === (file.notes || '')}>
          {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          {isLoading ? 'Saving...' : 'Save Notes'}
        </Button>
      )}
    </div>
  );
}

    