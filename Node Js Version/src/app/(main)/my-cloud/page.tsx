// src/app/(main)/my-cloud/page.tsx
'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useApp } from '@/context/AppContext';
import type { CloudFileMetadata, User } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger, DialogClose } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { useToast } from '@/hooks/use-toast';
import Image from 'next/image';
import { format, parseISO, isValid, startOfDay, endOfDay } from 'date-fns';
import { Search, Trash2, Download, FileImage, FileText, UploadCloud, Cloud, Filter, Loader2, Edit3, CalendarIcon as CalendarLucideIcon, RefreshCw } from 'lucide-react';
import NotesEditor from '@/components/cloud/NotesEditor';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';

type UserCloudFileType = 'cloud_document' | 'cloud_image';

export default function MyCloudFilesPage() {
  const { currentUser } = useApp();
  const { toast } = useToast();

  const [myCloudFiles, setMyCloudFiles] = useState<CloudFileMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [fileToUpload, setFileToUpload] = useState<File | null>(null);
  const [fileNotes, setFileNotes] = useState('');

  const [filterType, setFilterType] = useState<UserCloudFileType | 'all'>('all');
  const [filterSearchTerm, setFilterSearchTerm] = useState('');
  const [filterStartDate, setFilterStartDate] = useState<Date | undefined>(undefined);
  const [filterEndDate, setFilterEndDate] = useState<Date | undefined>(undefined);

  const [showUploadModal, setShowUploadModal] = useState(false);

  const fetchMyCloudFiles = useCallback(async (isManualRefresh = false) => {
    if (!currentUser?.id) {
      setMyCloudFiles([]);
      if(isManualRefresh) setIsRefreshing(false); else setIsLoading(false);
      return;
    }
    if(isManualRefresh) setIsRefreshing(true); else setIsLoading(true);
    try {
      const response = await fetch(`/api/cloud/files?userId=${currentUser.id}`);
      if (!response.ok) throw new Error('Failed to fetch your cloud files.');
      const data = await response.json();
      setMyCloudFiles(data.files || []);
      if (isManualRefresh) toast({title: "My Files Refreshed", description: "Your cloud file list has been updated.", duration: 2000});
    } catch (error) {
      console.error("Error fetching user's cloud files:", error);
      toast({ title: "Error", description: "Could not load your cloud files.", variant: "destructive" });
      setMyCloudFiles([]);
    } finally {
      if(isManualRefresh) setIsRefreshing(false); else setIsLoading(false);
    }
  }, [currentUser?.id, toast]);

  useEffect(() => {
    if (currentUser?.id) {
        fetchMyCloudFiles(false);
    } else {
        setIsLoading(false);
    }
  }, [currentUser?.id, fetchMyCloudFiles]);

  const displayedFiles = useMemo(() => {
    return myCloudFiles
      .filter(file => {
        const typeMatch = filterType === 'all' ||
                          (filterType === 'cloud_image' && file.file_type.startsWith('image/')) ||
                          (filterType === 'cloud_document' && !file.file_type.startsWith('image/'));

        const searchMatch = filterSearchTerm === '' ||
          file.original_filename.toLowerCase().includes(filterSearchTerm.toLowerCase()) ||
          (file.notes && file.notes.toLowerCase().includes(filterSearchTerm.toLowerCase()));

        let dateMatch = true;
        if (filterStartDate || filterEndDate) {
          const uploadDateObj = parseISO(file.upload_timestamp);
          if (!isValid(uploadDateObj)) dateMatch = false;
          else {
            if (filterStartDate && uploadDateObj < startOfDay(filterStartDate)) dateMatch = false;
            if (filterEndDate && uploadDateObj > endOfDay(filterEndDate)) dateMatch = false;
          }
        }
        return typeMatch && searchMatch && dateMatch;
      })
      .sort((a, b) => parseISO(b.upload_timestamp).getTime() - parseISO(a.upload_timestamp).getTime());
  }, [myCloudFiles, filterType, filterSearchTerm, filterStartDate, filterEndDate]);

  const formatFileSize = (bytes?: number): string => {
    if (bytes === undefined || bytes === null) return 'N/A';
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleDeleteFile = async (fileId: string) => {
    if (!currentUser) return;
    try {
      const response = await fetch(`/api/cloud/file/${fileId}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId: currentUser.id })
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({error: "Server error during deletion."}));
        throw new Error(errorData.error);
      }
      toast({ title: "File Deleted", description: "Your cloud file has been deleted. Click Refresh to see changes." });
    } catch (error: any) {
      toast({ title: "Delete Failed", description: error.message, variant: "destructive" });
    }
  };

  const handleFileUpload = async () => {
    if (!fileToUpload || !currentUser) {
      toast({ title: "Error", description: "No file selected or user not identified.", variant: "destructive" });
      return;
    }
    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', fileToUpload);
    formData.append('notes', fileNotes);
    formData.append('userId', currentUser.id);

    try {
      const response = await fetch('/api/cloud/upload', { method: 'POST', body: formData });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Server error during upload." }));
        throw new Error(errorData.error);
      }
      toast({ title: "File Uploaded", description: `${fileToUpload.name} uploaded. Click Refresh to see changes.` });
      setShowUploadModal(false); setFileToUpload(null); setFileNotes('');
    } catch (error: any) {
      toast({ title: "Upload Failed", description: error.message, variant: "destructive" });
    } finally {
      setIsUploading(false);
    }
  };

  const handleNotesUpdated = async (updatedCloudFile: CloudFileMetadata) => {
    toast({ title: 'Notes Updated', description: `Notes for ${updatedCloudFile.original_filename} saved. Click Refresh to see changes.`});
  };

  if (!currentUser) {
    return <div className="p-6 text-center text-muted-foreground">Please log in to access your cloud files.</div>;
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="text-2xl flex items-center"><Cloud className="mr-2 h-7 w-7 text-primary"/> My Cloud Files</CardTitle>
            <CardDescription>Manage your personal documents and images.</CardDescription>
          </div>
          <div className="flex gap-2 mt-4 md:mt-0">
            <Button onClick={() => fetchMyCloudFiles(true)} variant="outline" disabled={isRefreshing || isLoading}>
              <RefreshCw className={`mr-2 h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              Refresh My Files
            </Button>
            <Dialog open={showUploadModal} onOpenChange={setShowUploadModal}>
              <DialogTrigger asChild>
                <Button onClick={() => setShowUploadModal(true)}>
                  <UploadCloud className="mr-2 h-4 w-4" /> Upload New File
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Upload File to Your Cloud</DialogTitle>
                  <DialogDescription>Select a document or image to upload.</DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <div> <Label htmlFor="my-cloud-file-input">File</Label> <Input id="my-cloud-file-input" type="file" onChange={(e) => setFileToUpload(e.target.files ? e.target.files[0] : null)} /> </div>
                  <div> <Label htmlFor="my-cloud-file-notes">Notes (Optional)</Label> <Textarea id="my-cloud-file-notes" value={fileNotes} onChange={(e) => setFileNotes(e.target.value)} placeholder="Add notes..." /> </div>
                </div>
                <DialogFooter>
                  <DialogClose asChild><Button variant="outline" onClick={() => setShowUploadModal(false)} disabled={isUploading}>Cancel</Button></DialogClose>
                  <Button onClick={handleFileUpload} disabled={isUploading || !fileToUpload}>
                    {isUploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Upload
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>
        </CardHeader>
        <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6 items-end p-4 border rounded-lg bg-muted/20">
                <div className="lg:col-span-2">
                <Label htmlFor="my-cloud-search-term" className="text-sm">Search My Files</Label>
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input id="my-cloud-search-term" placeholder="By name, notes..." value={filterSearchTerm} onChange={e => setFilterSearchTerm(e.target.value)} className="pl-9 h-9" />
                </div>
                </div>
                <div>
                <Label htmlFor="my-cloud-type-filter" className="text-sm">File Type</Label>
                <Select value={filterType} onValueChange={(v) => setFilterType(v as UserCloudFileType | 'all')}>
                    <SelectTrigger id="my-cloud-type-filter" className="h-9"><SelectValue placeholder="Filter by type" /></SelectTrigger>
                    <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    <SelectItem value="cloud_document">Documents</SelectItem>
                    <SelectItem value="cloud_image">Images</SelectItem>
                    </SelectContent>
                </Select>
                </div>
                <div className="grid grid-cols-2 gap-2">
                <div><Label htmlFor="my-cloud-start-date" className="text-xs">Start Date</Label><Popover><PopoverTrigger asChild><Button id="my-cloud-start-date" variant="outline" className="w-full h-9 justify-start text-left font-normal text-xs p-2"><CalendarLucideIcon className="mr-1 h-3 w-3" />{filterStartDate ? format(filterStartDate, "PP") : "Pick"}</Button></PopoverTrigger><PopoverContent className="w-auto p-0"><Calendar mode="single" selected={filterStartDate} onSelect={setFilterStartDate} /></PopoverContent></Popover></div>
                <div><Label htmlFor="my-cloud-end-date" className="text-xs">End Date</Label><Popover><PopoverTrigger asChild><Button id="my-cloud-end-date" variant="outline" className="w-full h-9 justify-start text-left font-normal text-xs p-2"><CalendarLucideIcon className="mr-1 h-3 w-3" />{filterEndDate ? format(filterEndDate, "PP") : "Pick"}</Button></PopoverTrigger><PopoverContent className="w-auto p-0"><Calendar mode="single" selected={filterEndDate} onSelect={setFilterEndDate} disabled={(date) => filterStartDate ? date < filterStartDate : false} /></PopoverContent></Popover></div>
                </div>
            </div>

            {isLoading ? (
                <div className="flex justify-center items-center h-64"><Loader2 className="h-8 w-8 animate-spin text-primary" /> <span className="ml-2">Loading your cloud files...</span></div>
            ) : displayedFiles.length === 0 ? (
                <div className="text-center py-10 text-muted-foreground"><Filter className="mx-auto h-12 w-12 mb-4" /><p>No files found matching your filters.</p></div>
            ) : (
                <ScrollArea className="h-[calc(100vh-32rem)] border rounded-md">
                <Table>
                    <TableHeader><TableRow><TableHead className="w-[80px]">Preview</TableHead><TableHead>Name</TableHead><TableHead>Type</TableHead><TableHead>Upload Date</TableHead><TableHead>Size</TableHead><TableHead className="w-[200px]">Notes</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                    <TableBody>
                    {displayedFiles.map(file => (
                        <TableRow key={file.file_id}>
                        <TableCell>
                            {file.file_type.startsWith('image/') ? (
                            <Image 
                                src={`/api/uploads/${file.public_url}`} // Use API route
                                alt={file.original_filename} 
                                width={48} height={48} 
                                className="rounded object-cover aspect-square" 
                                data-ai-hint="file preview" 
                                unoptimized={true}
                                onError={(e) => { e.currentTarget.style.display = 'none'; e.currentTarget.parentElement!.innerHTML = '<div class=\"w-12 h-12 flex items-center justify-center bg-muted rounded\"><FileImage class=\"w-6 h-6 text-muted-foreground\" /></div>';}} />
                            ) : (
                            <div className="w-12 h-12 flex items-center justify-center bg-muted rounded"><FileText className="w-6 h-6 text-muted-foreground" /></div>
                            )}
                        </TableCell>
                        <TableCell>
                            <div className="font-medium truncate max-w-xs" title={file.original_filename}>{file.original_filename}</div>
                        </TableCell>
                        <TableCell><Badge variant="outline" className="capitalize text-xs">{file.file_type.startsWith('image/') ? 'Image' : 'Document'}</Badge></TableCell>
                        <TableCell className="text-xs">{isValid(parseISO(file.upload_timestamp)) ? format(parseISO(file.upload_timestamp), 'PPp') : 'Invalid Date'}</TableCell>
                        <TableCell className="text-xs">{formatFileSize(file.file_size)}</TableCell>
                        <TableCell>
                            <NotesEditor file={file} onNotesUpdated={handleNotesUpdated} />
                        </TableCell>
                        <TableCell className="text-right">
                            <Button variant="ghost" size="icon" asChild className="h-8 w-8" title="Download">
                            <a href={`/api/uploads/${file.public_url}`} target="_blank" download={file.original_filename} rel="noopener noreferrer">
                                <Download className="h-4 w-4" />
                            </a>
                            </Button>
                            <AlertDialog>
                            <AlertDialogTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" title="Delete"><Trash2 className="h-4 w-4" /></Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                                <AlertDialogHeader><AlertDialogTitle>Confirm Deletion</AlertDialogTitle></AlertDialogHeader>
                                <AlertDialogDescription>Are you sure you want to delete your cloud file "{file.original_filename}"? This action cannot be undone.</AlertDialogDescription>
                                <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => handleDeleteFile(file.file_id)} className="bg-destructive hover:bg-destructive/90">Delete</AlertDialogAction></AlertDialogFooter>
                            </AlertDialogContent>
                            </AlertDialog>
                        </TableCell>
                        </TableRow>
                    ))}
                    </TableBody>
                </Table>
                </ScrollArea>
            )}
        </CardContent>
      </Card>
    </div>
  );
}
