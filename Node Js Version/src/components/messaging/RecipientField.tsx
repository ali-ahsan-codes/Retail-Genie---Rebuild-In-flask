// src/components/messaging/RecipientField.tsx
'use client';
import React, { useState, useRef, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import type { User } from '@/types';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { X } from 'lucide-react';

interface RecipientFieldProps {
  label: string;
  onRecipientsChange: (recipients: string[]) => void;
}

export default function RecipientField({ label, onRecipientsChange }: RecipientFieldProps) {
  const { users, currentUser } = useApp();
  const [searchTerm, setSearchTerm] = useState('');
  const [selected, setSelected] = useState<User[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const availableUsers = users.filter(u => u.id !== currentUser?.id);

  const suggestions = searchTerm
    ? availableUsers.filter(user =>
        !selected.some(s => s.id === user.id) &&
        user.username.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : [];

  useEffect(() => {
    onRecipientsChange(selected.map(u => u.id));
  }, [selected, onRecipientsChange]);

  const handleSelect = (user: User) => {
    setSelected(prev => [...prev, user]);
    setSearchTerm('');
    setShowSuggestions(false);
  };

  const handleRemove = (userId: string) => {
    setSelected(prev => prev.filter(u => u.id !== userId));
  };
  
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="flex items-start gap-2" ref={wrapperRef}>
      <label className="w-12 text-sm font-medium text-muted-foreground pt-2 text-right">{label}</label>
      <div className="flex-1 border rounded-md p-1 min-h-[40px] flex flex-wrap items-center gap-1 relative">
        {selected.map(user => (
          <Badge key={user.id} variant="secondary" className="flex items-center gap-1">
            {user.username}
            <button type="button" onClick={() => handleRemove(user.id)} className="rounded-full hover:bg-destructive/20">
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <div className="relative flex-grow">
          <Input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onFocus={() => setShowSuggestions(true)}
            className="border-none shadow-none focus-visible:ring-0 h-8 p-1 w-full min-w-[100px]"
            placeholder={selected.length === 0 ? "Select users..." : ""}
          />
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute top-full left-0 mt-1 w-full max-w-sm bg-card border rounded-md shadow-lg z-50">
              <ScrollArea className="max-h-40">
                {suggestions.map(user => (
                  <div
                    key={user.id}
                    className="p-2 hover:bg-accent cursor-pointer text-sm"
                    onClick={() => handleSelect(user)}
                  >
                    {user.username}
                  </div>
                ))}
              </ScrollArea>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
