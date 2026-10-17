// src/app/(main)/admin/scm/po/[poId]/edit/page.tsx
'use client';
import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import { PurchaseOrder, POAttachment } from '@/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { Loader2, ArrowLeft, Save, Edit, UploadCloud, File, Trash2, DollarSign } from 'lucide-react';
import { Textarea } from '@/components/ui/textarea';
import { format, parseISO } from 'date-fns';
import { useDropzone } from 'react-dropzone';

type UploadFile = File & { preview: string; };

export default function EditPurchaseOrderPage() {
  const router = useRouter();
  const params = useParams();
  const poId = params.poId as string;
  const { isDataLoaded, currentUser } = useApp();
  const { toast } = useToast();

  const [po, setPo] = useState<PurchaseOrder | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [attachments, setAttachments] = useState<POAttachment[]>([]);
  const [newFiles, setNewFiles] = useState<UploadFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const fetchPo = useCallback(async () => {
    if (!poId || !isDataLoaded) return;
    setIsLoading(true);
    try {
      const response = await fetch(`/api/purchase-orders/${poId}`);
      if (!response.ok) throw new Error('Failed to fetch PO');
      const data = await response.json();
      setPo(data);
      setAttachments(data.attachments || []);
    } catch (error) {
      toast({ title: 'Error', description: (error as Error).message, variant: 'destructive' });
      router.push('/admin/scm');
    } finally {
      setIsLoading(false);
    }
  }, [poId, isDataLoaded, router, toast]);

  useEffect(() => {
    fetchPo();
  }, [fetchPo]);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setNewFiles(prev => [
      ...prev,
      ...acceptedFiles.map(file => Object.assign(file, {
        preview: URL.createObjectURL(file),
      }))
    ]);
  }, []);

  const { getRootProps, getInputProps } = useDropzone({
    onDrop,
    accept: { 'image/*': [], 'application/pdf': [], 'application/vnd.ms-excel': [], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': [] }
  });
  
  const handleRemoveNewFile = (index: number) => {
    setNewFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleUploadAttachments = async () => {
    if (newFiles.length === 0) return;
    setIsUploading(true);
    const formData = new FormData();
    newFiles.forEach(file => {
      formData.append('files', file);
    });

    try {
      const response = await fetch(`/api/purchase-orders/${poId}/attachments`, {
        method: 'POST',
        headers: { 'x-user-id': currentUser?.id || '' },
        body: formData,
      });
      if (!response.ok) throw new Error('Failed to upload attachments');
      toast({ title: 'Success', description: 'Attachments uploaded.' });
      setNewFiles([]);
      fetchPo(); // Refresh data
    } catch (error) {
      toast({ title: 'Upload Error', description: (error as Error).message, variant: 'destructive' });
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteAttachment = async (attachmentId: string) => {
    try {
        const response = await fetch(`/api/purchase-orders/${poId}/attachments?id=${attachmentId}`, {
            method: 'DELETE',
            headers: { 'x-user-id': currentUser?.id || '' }
        });
        if (!response.ok) throw new Error('Failed to delete attachment.');
        toast({title: 'Success', description: 'Attachment deleted.'});
        fetchPo(); // Refresh
    } catch (error) {
        toast({title: 'Error', description: (error as Error).message, variant: 'destructive'});
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!po) return;
    const { name, value } = e.target;
    setPo({ ...po, [name]: value });
  };
  
  const handleStatusChange = (value: string) => {
    if (!po) return;
    setPo({ ...po, status: value as PurchaseOrder['status'] });
  };

  const handleSaveChanges = async () => {
    if (!po) return;
    setIsSaving(true);
    try {
      const response = await fetch(`/api/purchase-orders/${po.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'x-user-id': currentUser?.id || '' },
        body: JSON.stringify(po)
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.details || errorData.message || 'Failed to save changes');
      }
      
      if (newFiles.length > 0) {
        await handleUploadAttachments();
      } 
      toast({ title: 'Success', description: 'Purchase Order updated successfully' });
      router.push(`/admin/scm/po/${po.id}`);
      
    } catch (error) {
      console.error('PO Update Error:', error);
      toast({ title: 'Error', description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading || !isDataLoaded) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="animate-spin h-8 w-8 text-primary" /></div>;
  }

  if (!po) {
    return <div>Purchase Order not found.</div>;
  }

  return (
    <div className="space-y-6">
       <div className="flex justify-between items-center">
        <Button variant="outline" onClick={() => router.push(`/admin/scm/po/${poId}`)}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to PO Details
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-2xl flex items-center"><Edit className="mr-2 h-6 w-6"/>Edit Purchase Order</CardTitle>
          <CardDescription>PO Number: <span className="font-semibold text-primary">{po.id}</span></CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
             <div>
                <Label htmlFor="status">Status</Label>
                <Select value={po.status} onValueChange={handleStatusChange}>
                    <SelectTrigger id="status">
                        <SelectValue placeholder="Select status" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="Draft">Draft</SelectItem>
                        <SelectItem value="Pending">Pending</SelectItem>
                        <SelectItem value="Confirmed">Confirmed</SelectItem>
                        <SelectItem value="Shipped">Shipped</SelectItem>
                        <SelectItem value="Received">Received</SelectItem>
                        <SelectItem value="Cancelled">Cancelled</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <div>
              <Label htmlFor="expected_delivery">Expected Delivery Date</Label>
              <Input type="date" id="expected_delivery" name="expected_delivery" value={po.expected_delivery ? po.expected_delivery.split('T')[0] : ''} onChange={handleInputChange} />
            </div>
             <div>
              <Label htmlFor="deadline">Payment Deadline</Label>
              <Input type="date" id="deadline" name="deadline" value={po.deadline ? po.deadline.split('T')[0] : ''} onChange={handleInputChange} />
            </div>
            <div>
                <Label htmlFor="advance_paid">Advance Paid (OMR)</Label>
                <Input type="number" id="advance_paid" name="advance_paid" value={po.advance_paid || ''} onChange={handleInputChange} />
            </div>
             <div>
                <Label htmlFor="total_amount" className="flex items-center"><DollarSign className="w-4 h-4 mr-1 text-muted-foreground"/>Total Amount (OMR)</Label>
                <Input type="number" id="total_amount" name="total_amount" value={po.total_amount || ''} onChange={handleInputChange} />
            </div>
          </div>
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader>
            <CardTitle>Attachments</CardTitle>
            <CardDescription>Upload invoices, contracts, or other relevant documents.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
            <div {...getRootProps({className: 'p-6 border-2 border-dashed rounded-lg text-center cursor-pointer hover:border-primary'})}>
                <input {...getInputProps()} />
                <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <UploadCloud className="h-8 w-8" />
                    <p>Drag 'n' drop some files here, or click to select files</p>
                </div>
            </div>

            {newFiles.length > 0 && (
                <div className="space-y-3">
                    <h4 className="font-semibold">New Attachments</h4>
                    {newFiles.map((file, index) => (
                        <div key={index} className="flex flex-col gap-2 p-3 border rounded-md">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <File className="h-5 w-5 text-muted-foreground" />
                                    <span className="text-sm font-medium">{file.name}</span>
                                </div>
                                <Button variant="ghost" size="sm" className="text-destructive" onClick={() => handleRemoveNewFile(index)}>Remove</Button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
            
            {attachments.length > 0 && (
                <div className="space-y-3">
                    <h4 className="font-semibold">Existing Attachments</h4>
                     {attachments.map((att) => (
                        <div key={att.id} className="flex items-center justify-between p-2 border rounded-md">
                            <a href={`/api/uploads/${att.file_path}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-primary hover:underline">
                                <File className="h-5 w-5" />
                                <div>
                                    <p className="text-sm font-medium">{att.original_name}</p>
                                    <p className="text-xs text-muted-foreground">Uploaded: {format(parseISO(att.uploaded_at), 'PPP')}</p>
                                </div>
                            </a>
                            <Button variant="ghost" size="icon" className="text-destructive h-8 w-8" onClick={() => handleDeleteAttachment(att.id)}>
                                <Trash2 className="h-4 w-4" />
                            </Button>
                        </div>
                    ))}
                </div>
            )}
        </CardContent>
      </Card>

      <div className="flex justify-end mt-6">
        <Button onClick={handleSaveChanges} disabled={isSaving || isUploading}>
            {isSaving || isUploading ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : <Save className="mr-2 h-4 w-4"/>}
            {isSaving || isUploading ? 'Saving...' : 'Save All Changes'}
        </Button>
      </div>
    </div>
  );
}
