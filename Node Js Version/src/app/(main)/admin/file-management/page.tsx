
// src/app/(main)/admin/file-management/page.tsx
'use client';

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useApp } from '@/context/AppContext';
import type { Product, AttendanceLog, CloudFileMetadata, User, UserRole } from '@/types';
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
import { Search, Trash2, Download, FileImage, UserCheck, FileText, UploadCloud, ShieldAlert, CalendarIcon as CalendarLucideIcon, Cloud, Filter, Loader2, RefreshCw, Users as UsersFilterIcon } from 'lucide-react';
import NotesEditor from '@/components/cloud/NotesEditor';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';

type ManagedFileType = 'product_image' | 'attendance_selfie' | 'audit_selfie' | 'audit_item_media' | 'cloud_document' | 'cloud_image';

interface ManagedFile {
  id: string; // Original ID of the entity (product, log, file_id, audit_id, audit_item_id)
  name: string; // Display name or filename
  type: ManagedFileType;
  previewUrl?: string; // Path relative to 'uploads' for API serving (e.g., "products/image.jpg")
  downloadUrl: string; // Path relative to 'uploads' for API serving
  uploadDate: string; // ISO string
  size?: number; // bytes
  notes?: string; // For cloud files
  associatedEntity?: string; // e.g., "Product SKU: XYZ", "User: username", "Audit: AUD-001"
  userIdForCloudFile?: string; 
  rawFileObject?: Product | AttendanceLog | CloudFileMetadata | Audit; // Use Audit for audit_selfie, AuditItem for audit_item_media
  ownerUsername?: string;
  auditItemId?: string; // For audit_item_media
  auditCountEventId?: string; // For audit_item_media
}

const FileManagementPage: React.FC = () => {
  const {
    products,
    attendanceLogs,
    audits, // Assuming audits are fetched and contain selfiePath and items with images
    users,
    currentUser,
    loadDataFromDb: appContextLoadDataFromDb,
    updateProduct,
    hasPermission, 
  } = useApp();
  const { toast } = useToast();

  const [allManagedFiles, setAllManagedFiles] = useState<ManagedFile[]>([]);
  const [cloudFilesForDisplay, setCloudFilesForDisplay] = useState<CloudFileMetadata[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isUploadingCloudFile, setIsUploadingCloudFile] = useState(false);
  const [cloudFileToUpload, setCloudFileToUpload] = useState<File | null>(null);
  const [cloudFileNotes, setCloudFileNotes] = useState('');

  const [filterType, setFilterType] = useState<ManagedFileType | 'all'>('all');
  const [filterSearchTerm, setFilterSearchTerm] = useState('');
  const [filterStartDate, setFilterStartDate] = useState<Date | undefined>(undefined);
  const [filterEndDate, setFilterEndDate] = useState<Date | undefined>(undefined);
  const [selectedOwnerFilterId, setSelectedOwnerFilterId] = useState<string>('all');

  const [showUploadModal, setShowUploadModal] = useState(false);
  const initialLoadDoneRef = useRef(false);

  const fetchAllCloudFilesForAdmin = useCallback(async (isManualRefresh = false) => {
    if (!currentUser?.id || !(currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('manage_cloud_files')))) {
      setCloudFilesForDisplay([]);
      if (isManualRefresh && setIsRefreshing) setIsRefreshing(false);
      return;
    }
    if (isManualRefresh && setIsRefreshing) setIsRefreshing(true);
    try {
      const response = await fetch(`/api/cloud/files?userId=${currentUser.id}&adminView=true`);
      if (!response.ok) throw new Error('Failed to fetch all cloud files for admin.');
      const data = await response.json();
      setCloudFilesForDisplay(data.files || []);
      if (isManualRefresh) toast({ title: "All Cloud Files Refreshed", description: "The list of all user cloud files has been updated.", duration: 2000 });
    } catch (error) {
      console.error("Error fetching all cloud files for admin:", error);
      toast({ title: "Error", description: "Could not load all cloud files.", variant: "destructive" });
      setCloudFilesForDisplay([]);
    } finally {
      if (isManualRefresh && setIsRefreshing) setIsRefreshing(false);
    }
  }, [currentUser, toast, hasPermission, setIsRefreshing]); 

  const loadAllPageData = useCallback(async (isManualRefresh = false) => {
    if(isManualRefresh) setIsRefreshing(true); else setIsLoading(true);
    await appContextLoadDataFromDb(false); 
    await fetchAllCloudFilesForAdmin(isManualRefresh); 
    if(isManualRefresh) setIsRefreshing(false); else setIsLoading(false);
    if(isManualRefresh) toast({ title: "All Files Refreshed", description: "File lists have been updated.", duration: 2000 });
  }, [appContextLoadDataFromDb, fetchAllCloudFilesForAdmin, toast, setIsRefreshing, setIsLoading]);


  useEffect(() => {
    const doInitialLoad = async () => {
      setIsLoading(true);
      await appContextLoadDataFromDb(false);
      await fetchAllCloudFilesForAdmin(false);
      setIsLoading(false);
    };

    if (currentUser?.id && !initialLoadDoneRef.current) {
      initialLoadDoneRef.current = true;
      doInitialLoad();
    } else if (!currentUser?.id) {
      setIsLoading(false);
      setAllManagedFiles([]);
      setCloudFilesForDisplay([]);
      initialLoadDoneRef.current = false; 
    }
  }, [currentUser?.id, appContextLoadDataFromDb, fetchAllCloudFilesForAdmin]);


  useEffect(() => {
    const productManagedFiles: ManagedFile[] = products
      .filter(p => p.imageUrl) // imageUrl is "products/filename.ext"
      .map(p => ({
        id: p.id, name: p.name, type: 'product_image',
        previewUrl: p.imageUrl, downloadUrl: p.imageUrl!,
        uploadDate: p.updatedAt || p.createdAt || new Date(0).toISOString(),
        associatedEntity: `Product SKU: ${p.sku}`, rawFileObject: p,
      }));

    const attendanceManagedFiles: ManagedFile[] = attendanceLogs
      .filter(log => log.selfieImagePath) // selfieImagePath is "attendance/filename.ext"
      .map(log => {
        const user = users.find(u => u.id === log.userId);
        return {
          id: log.id, name: `Attendance for ${user?.username || 'Unknown User'}`, type: 'attendance_selfie',
          previewUrl: log.selfieImagePath, downloadUrl: log.selfieImagePath!,
          uploadDate: log.timestamp, associatedEntity: `User: ${user?.username || log.userId}`, rawFileObject: log,
        };
      });

    const auditSelfieFiles: ManagedFile[] = audits
      .filter(audit => audit.auditorSelfiePath) // auditorSelfiePath is "audits/selfies/filename.ext"
      .map(audit => {
        const auditor = users.find(u => u.id === audit.auditorId);
        return {
          id: audit.id, name: `Audit Selfie for ${audit.title}`, type: 'audit_selfie',
          previewUrl: audit.auditorSelfiePath, downloadUrl: audit.auditorSelfiePath!,
          uploadDate: audit.startedAt || audit.createdAt,
          associatedEntity: `Audit ID: ${audit.id}, Auditor: ${auditor?.username || 'N/A'}`,
          rawFileObject: audit,
        };
      });

    const auditItemMediaFiles: ManagedFile[] = audits.flatMap(audit =>
      (audit.items || []).flatMap(item =>
        (item.counts || []).flatMap(count =>
          (count.images || []).map(img => ({
            id: img.id, name: `Evidence for ${item.productName} (Count ID: ${count.id.slice(-5)})`, type: 'audit_item_media',
            previewUrl: img.imagePath, // imagePath is "audits/item_images/filename.ext"
            downloadUrl: img.imagePath,
            uploadDate: img.createdAt,
            associatedEntity: `Audit: ${audit.id}, Item: ${item.productName}, Count: ${count.count}`,
            rawFileObject: item, // Could store item or count or img object
            auditItemId: item.id,
            auditCountEventId: count.id,
          }))
        )
      )
    );

    const allUserCloudManagedFiles: ManagedFile[] = cloudFilesForDisplay.map(cf => ({
      id: cf.file_id, name: cf.original_filename,
      // public_url is now like "cloud/userid/images/myphoto.jpg" or "cloud/userid/documents/mydoc.pdf"
      type: cf.file_type.startsWith('image/') ? 'cloud_image' : 'cloud_document',
      previewUrl: cf.file_type.startsWith('image/') ? cf.public_url : undefined,
      downloadUrl: cf.public_url, uploadDate: cf.upload_timestamp,
      size: cf.file_size, notes: cf.notes,
      userIdForCloudFile: cf.userId, 
      ownerUsername: cf.ownerUsername || users.find(u => u.id === cf.userId)?.username || 'Unknown Owner',
      rawFileObject: cf,
    }));

    setAllManagedFiles([
        ...productManagedFiles, 
        ...attendanceManagedFiles, 
        ...auditSelfieFiles, 
        ...auditItemMediaFiles, 
        ...allUserCloudManagedFiles
    ]);
  }, [products, attendanceLogs, audits, users, cloudFilesForDisplay]);


  const filteredAndSortedFiles = useMemo(() => {
    return allManagedFiles
      .filter(file => {
        const typeMatch = filterType === 'all' || file.type === filterType;

        const searchMatch = filterSearchTerm === '' ||
          file.name.toLowerCase().includes(filterSearchTerm.toLowerCase()) ||
          (file.associatedEntity && file.associatedEntity.toLowerCase().includes(filterSearchTerm.toLowerCase())) ||
          ((file.rawFileObject as CloudFileMetadata)?.original_filename?.toLowerCase().includes(filterSearchTerm.toLowerCase())) ||
          (file.notes && file.notes.toLowerCase().includes(filterSearchTerm.toLowerCase())) ||
          (file.ownerUsername && file.ownerUsername.toLowerCase().includes(filterSearchTerm.toLowerCase()));

        let dateMatch = true;
        if (filterStartDate || filterEndDate) {
          const uploadDateObj = parseISO(file.uploadDate);
          if (!isValid(uploadDateObj)) dateMatch = false;
          else {
            if (filterStartDate && uploadDateObj < startOfDay(filterStartDate)) dateMatch = false;
            if (filterEndDate && uploadDateObj > endOfDay(filterEndDate)) dateMatch = false;
          }
        }
        
        let ownerMatch = true;
        if (selectedOwnerFilterId !== 'all') {
          if (file.type === 'cloud_document' || file.type === 'cloud_image') {
            ownerMatch = file.userIdForCloudFile === selectedOwnerFilterId;
          } else if (file.type === 'attendance_selfie') {
            // Assuming rawFileObject for attendance_selfie is AttendanceLog
            const log = file.rawFileObject as AttendanceLog;
            ownerMatch = log.userId === selectedOwnerFilterId;
          } else if (file.type === 'audit_selfie'){
             const audit = file.rawFileObject as Audit;
             ownerMatch = audit.auditorId === selectedOwnerFilterId;
          }
           else { // For product_image, audit_item_media, they aren't directly "owned" by a single user in the same way
             ownerMatch = false;
          }
        }

        return typeMatch && searchMatch && dateMatch && ownerMatch;
      })
      .sort((a, b) => parseISO(b.uploadDate).getTime() - parseISO(a.uploadDate).getTime());
  }, [allManagedFiles, filterType, filterSearchTerm, filterStartDate, filterEndDate, selectedOwnerFilterId]);

  const formatFileSize = (bytes?: number): string => {
    if (bytes === undefined || bytes === null) return 'N/A';
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const handleDeleteFile = async (file: ManagedFile) => {
    if (!currentUser) return;
    let success = false;
    let toastMessage = '';

    try {
      // Path construction for deletion needs to be careful, as `file.downloadUrl` is already correct.
      // The API endpoint itself needs to know how to map its `[...path]` param to the actual file system path.
      // For now, we assume the API endpoint will handle the file.downloadUrl correctly.
      // The key is that the file.id and file.type guide the backend logic.
      
      let endpoint = '';
      let body: any = {};

      if (file.type === 'product_image') {
        if (!hasPermission('manage_products')) { toast({ title: "Permission Denied", variant: "destructive" }); return; }
        // Product image removal is handled by setting imageUrl to null/empty on the product itself.
        // The PUT /api/products/:productId route handles physical file deletion if imageUrl changes.
        const productToUpdate = file.rawFileObject as Product;
        await updateProduct({ ...productToUpdate, imageUrl: undefined }); 
        toastMessage = `Product image for ${file.name} removed.`;
        success = true;
      } else if (file.type === 'attendance_selfie') {
        if (!hasPermission('manage_users')) { toast({ title: "Permission Denied", variant: "destructive" }); return; }
        endpoint = `/api/attendance/${file.id}/selfie`; // file.id is the attendanceLogId
        const response = await fetch(endpoint, { method: 'DELETE' });
        if (!response.ok) throw new Error('Failed to delete selfie from server.');
        toastMessage = `Attendance selfie for ${file.name} deleted.`;
        success = true;
      } else if (file.type === 'audit_selfie' || file.type === 'audit_item_media') {
         if (!hasPermission('manage_audits')) { toast({ title: "Permission Denied", variant: "destructive" }); return; }
         // Deleting audit media needs a specific backend endpoint not detailed in the prompt.
         // For now, this will be a placeholder or assumed to be handled by audit management logic elsewhere.
         // Example: endpoint = `/api/audits/media/${file.id}`;
         // The current structure seems to imply audit media deletion is part of audit editing/deletion.
         toast({ title: "Not Implemented", description: `Deletion for ${file.type} requires a specific backend endpoint.`, variant: "default"});
         return; // For now, prevent actual attempt
      } else if ((file.type === 'cloud_document' || file.type === 'cloud_image')) {
        const ownerIdOfFileToDelete = file.userIdForCloudFile;
        if (!ownerIdOfFileToDelete) { toast({ title: "Error", description: "File owner ID missing.", variant: "destructive" }); return; }
        if (!(currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('manage_cloud_files')))) {
          toast({ title: "Permission Denied", description: "No permission to delete this cloud file.", variant: "destructive" }); return;
        }
        endpoint = `/api/cloud/file/${file.id}`; // file.id is file_id for cloud files
        body = { userId: ownerIdOfFileToDelete }; // API needs ownerId
        const response = await fetch(endpoint, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ error: "Server error during cloud file deletion." }));
          throw new Error(errorData.error);
        }
        const ownerUsername = users.find(u => u.id === ownerIdOfFileToDelete)?.username || ownerIdOfFileToDelete;
        toastMessage = `Cloud file ${file.name} (owned by ${ownerUsername}) deleted.`;
        success = true;
      }

      if (success) {
        toast({ title: "File Action Successful", description: `${toastMessage} Click Refresh to see changes.` });
      }
    } catch (error: any) {
      toast({ title: "Delete Failed", description: error.message, variant: "destructive" });
    }
  };

  const handleCloudFileUpload = async () => {
    if (!cloudFileToUpload || !currentUser) {
      toast({ title: "Error", description: "No file selected or user not identified.", variant: "destructive" });
      return;
    }
    if (!(currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('manage_cloud_files')))) {
      toast({ title: "Permission Denied", description: "No permission to upload to cloud via admin page.", variant: "destructive" });
      return;
    }
    setIsUploadingCloudFile(true);
    const formData = new FormData();
    formData.append('file', cloudFileToUpload);
    formData.append('notes', cloudFileNotes);
    formData.append('userId', currentUser.id); 

    try {
      const response = await fetch('/api/cloud/upload', { method: 'POST', body: formData });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Server error during upload." }));
        throw new Error(errorData.error);
      }
      toast({ title: "File Uploaded", description: `${cloudFileToUpload.name} uploaded to your (admin) cloud storage. Click Refresh to see changes.` });
      setShowUploadModal(false); setCloudFileToUpload(null); setCloudFileNotes('');
    } catch (error: any) {
      toast({ title: "Upload Failed", description: error.message, variant: "destructive" });
    } finally {
      setIsUploadingCloudFile(false);
    }
  };

  const handleNotesUpdated = async (updatedCloudFile: CloudFileMetadata) => {
    toast({ title: 'Notes Updated', description: `Notes for ${updatedCloudFile.original_filename} saved. Click Refresh to see changes.` });
  };

  if (!currentUser || !(currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('manage_cloud_files')))) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to view file management.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader className="flex flex-col md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle className="text-2xl flex items-center"><Cloud className="mr-2 h-7 w-7 text-primary" /> System & User File Management</CardTitle>
            <CardDescription>View system files (product images, attendance/audit selfies, audit item media) and all user cloud files.</CardDescription>
          </div>
          <div className="flex gap-2 mt-4 md:mt-0">
            <Button onClick={() => loadAllPageData(true)} variant="outline" disabled={isRefreshing || isLoading}>
              <RefreshCw className={`mr-2 h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              Refresh All Files
            </Button>
            {currentUser.role === 'admin' && (
              <Dialog open={showUploadModal} onOpenChange={setShowUploadModal}>
                <DialogTrigger asChild>
                  <Button onClick={() => setShowUploadModal(true)}>
                    <UploadCloud className="mr-2 h-4 w-4" /> Upload to My (Admin) Cloud
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Upload New File to Your Admin Cloud Storage</DialogTitle>
                    <DialogDescription>Select a document or image to upload.</DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div> <Label htmlFor="cloud-file-input-admin-page">File</Label> <Input id="cloud-file-input-admin-page" type="file" onChange={(e) => setCloudFileToUpload(e.target.files ? e.target.files[0] : null)} /> </div>
                    <div> <Label htmlFor="cloud-file-notes-admin-page">Notes (Optional)</Label> <Textarea id="cloud-file-notes-admin-page" value={cloudFileNotes} onChange={(e) => setCloudFileNotes(e.target.value)} placeholder="Add any notes about this file..." /> </div>
                  </div>
                  <DialogFooter>
                    <DialogClose asChild><Button variant="outline" onClick={() => setShowUploadModal(false)} disabled={isUploadingCloudFile}>Cancel</Button></DialogClose>
                    <Button onClick={handleCloudFileUpload} disabled={isUploadingCloudFile || !cloudFileToUpload}>
                      {isUploadingCloudFile ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null} Upload
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6 items-end p-4 border rounded-lg bg-muted/20">
            <div className="lg:col-span-2">
              <Label htmlFor="file-search-term-admin" className="text-sm">Search Files</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input id="file-search-term-admin" placeholder="By name, SKU, user, notes..." value={filterSearchTerm} onChange={e => setFilterSearchTerm(e.target.value)} className="pl-9 h-9" />
              </div>
            </div>
            <div>
              <Label htmlFor="file-type-filter-admin" className="text-sm">File Type</Label>
              <Select value={filterType} onValueChange={(v) => setFilterType(v as ManagedFileType | 'all')}>
                <SelectTrigger id="file-type-filter-admin" className="h-9"><SelectValue placeholder="Filter by type" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="product_image">Product Images</SelectItem>
                  <SelectItem value="attendance_selfie">Attendance Selfies</SelectItem>
                  <SelectItem value="audit_selfie">Audit Start Selfies</SelectItem>
                  <SelectItem value="audit_item_media">Audit Item Media</SelectItem>
                  <SelectItem value="cloud_document">User Cloud Docs</SelectItem>
                  <SelectItem value="cloud_image">User Cloud Images</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="owner-filter-admin" className="text-sm">Owner (Cloud/Attendance/Audit)</Label>
              <Select value={selectedOwnerFilterId} onValueChange={setSelectedOwnerFilterId}>
                <SelectTrigger id="owner-filter-admin" className="h-9">
                  <SelectValue placeholder="Filter by owner/user" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Users (for relevant types)</SelectItem>
                  {users.map(user => (
                    <SelectItem key={user.id} value={user.id}>{user.username}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label htmlFor="file-start-date-admin" className="text-xs">Start Date</Label><Popover><PopoverTrigger asChild><Button id="file-start-date-admin" variant="outline" className="w-full h-9 justify-start text-left font-normal text-xs p-2"><CalendarLucideIcon className="mr-1 h-3 w-3" />{filterStartDate ? format(filterStartDate, "PP") : "Pick"}</Button></PopoverTrigger><PopoverContent className="w-auto p-0"><Calendar mode="single" selected={filterStartDate} onSelect={setFilterStartDate} /></PopoverContent></Popover></div>
              <div><Label htmlFor="file-end-date-admin" className="text-xs">End Date</Label><Popover><PopoverTrigger asChild><Button id="file-end-date-admin" variant="outline" className="w-full h-9 justify-start text-left font-normal text-xs p-2"><CalendarLucideIcon className="mr-1 h-3 w-3" />{filterEndDate ? format(filterEndDate, "PP") : "Pick"}</Button></PopoverTrigger><PopoverContent className="w-auto p-0"><Calendar mode="single" selected={filterEndDate} onSelect={setFilterEndDate} disabled={(date) => filterStartDate ? date < filterStartDate : false} /></PopoverContent></Popover></div>
            </div>
          </div>

          {isLoading ? (
            <div className="flex justify-center items-center h-64"><Loader2 className="h-8 w-8 animate-spin text-primary" /> <span className="ml-2">Loading files...</span></div>
          ) : filteredAndSortedFiles.length === 0 ? (
            <div className="text-center py-10 text-muted-foreground"><Filter className="mx-auto h-12 w-12 mb-4" /><p>No files match your current filters.</p></div>
          ) : (
            <ScrollArea className="h-[calc(100vh-32rem)] border rounded-md"> 
              <Table>
                <TableHeader><TableRow><TableHead className="w-[80px]">Preview</TableHead><TableHead>Name / Details</TableHead><TableHead>Type</TableHead><TableHead>Owner/Context</TableHead><TableHead>Upload Date</TableHead><TableHead>Size</TableHead><TableHead className="w-[200px]">Notes</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                <TableBody>
                  {filteredAndSortedFiles.map(file => {
                    const isCloudFileType = file.type === 'cloud_document' || file.type === 'cloud_image';
                    // Admin can delete any product image if they can manage products, any attendance if manage users, any audit if manage_audits. Cloud specific permissions for cloud files.
                    const canAdminDeleteFile = 
                      (file.type === 'product_image' && hasPermission('manage_products')) ||
                      (file.type === 'attendance_selfie' && hasPermission('manage_users')) ||
                      ((file.type === 'audit_selfie' || file.type === 'audit_item_media') && hasPermission('manage_audits')) || // Placeholder, specific API needed
                      (isCloudFileType && file.userIdForCloudFile && (currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('manage_cloud_files'))));
                      
                    const canAdminEditNotesForFile = isCloudFileType && file.userIdForCloudFile && (currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('manage_cloud_files')));

                    return (
                      <TableRow key={`${file.id}-${file.type}-${file.userIdForCloudFile || ''}-${file.auditItemId || ''}-${file.auditCountEventId || ''}`}>
                        <TableCell>
                          {file.previewUrl ? (
                            <Image src={`/api/uploads/${file.previewUrl}`} alt={file.name} width={48} height={48} className="rounded object-cover aspect-square" data-ai-hint="file preview" unoptimized={true} onError={(e) => { e.currentTarget.style.display = 'none'; e.currentTarget.parentElement!.innerHTML = '<div class=\"w-12 h-12 flex items-center justify-center bg-muted rounded\"><FileImage class=\"w-6 h-6 text-muted-foreground\" /></div>'; }} />
                          ) : file.type === 'cloud_document' ? (
                            <div className="w-12 h-12 flex items-center justify-center bg-muted rounded"><FileText className="w-6 h-6 text-muted-foreground" /></div>
                          ) : (
                            <div className="w-12 h-12 flex items-center justify-center bg-muted rounded"><FileImage className="w-6 h-6 text-muted-foreground" /></div>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="font-medium truncate max-w-xs" title={file.name}>{file.name}</div>
                          {file.associatedEntity && <div className="text-xs text-muted-foreground">{file.associatedEntity}</div>}
                        </TableCell>
                        <TableCell><Badge variant="outline" className="capitalize text-xs">{file.type.replace(/_/g, ' ')}</Badge></TableCell>
                        <TableCell className="text-xs">
                          {file.ownerUsername ? (
                            <span className="flex items-center gap-1"><UsersFilterIcon className="h-3 w-3 text-muted-foreground" />{file.ownerUsername}</span>
                          ) : isCloudFileType && file.userIdForCloudFile ? (
                            <span className="text-xs text-muted-foreground italic">Owner ID: {file.userIdForCloudFile}</span>
                          ) : (
                            <span className="text-muted-foreground">- (System)</span>
                          )}
                        </TableCell>
                        <TableCell className="text-xs">{isValid(parseISO(file.uploadDate)) ? format(parseISO(file.uploadDate), 'PPp') : 'Invalid Date'}</TableCell>
                        <TableCell className="text-xs">{formatFileSize(file.size)}</TableCell>
                        <TableCell>
                          {isCloudFileType && file.rawFileObject && file.userIdForCloudFile ? (
                            <NotesEditor
                              file={file.rawFileObject as CloudFileMetadata}
                              onNotesUpdated={handleNotesUpdated}
                              ownerUserId={file.userIdForCloudFile} 
                              canEdit={canAdminEditNotesForFile}     
                            />
                          ) : file.notes ? (
                            <p className="text-xs text-muted-foreground truncate" title={file.notes}>{file.notes}</p>
                          ) : <span className="text-xs text-muted-foreground">-</span>}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" size="icon" asChild className="h-8 w-8"><a href={`/api/uploads/${file.downloadUrl}`} target="_blank" download={file.name} rel="noopener noreferrer" title="Download"><Download className="h-4 w-4" /></a></Button>
                          <AlertDialog>
                            <AlertDialogTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive" title="Delete"
                                disabled={!canAdminDeleteFile}>
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                              <AlertDialogHeader><AlertDialogTitle>Confirm Deletion</AlertDialogTitle></AlertDialogHeader>
                              <AlertDialogDescription>Are you sure you want to delete the file "{file.name}"? This action cannot be undone.</AlertDialogDescription>
                              <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => handleDeleteFile(file)} className="bg-destructive hover:bg-destructive/90">Delete</AlertDialogAction></AlertDialogFooter>
                            </AlertDialogContent>
                          </AlertDialog>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default FileManagementPage;
