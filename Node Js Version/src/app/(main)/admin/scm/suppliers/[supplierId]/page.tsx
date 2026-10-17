
// src/app/(main)/admin/scm/suppliers/[supplierId]/page.tsx
'use client';
import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Edit, Globe, Mail, Phone, Clock, FileText, Loader2, Paperclip } from 'lucide-react';
import { Supplier } from '@/types';
import { useToast } from '@/hooks/use-toast';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter, DialogTrigger, DialogClose } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { format } from 'date-fns';

export default function SupplierDetailPage() {
  const router = useRouter();
  const params = useParams();
  const supplierId = params.supplierId as string;
  
  const [supplier, setSupplier] = useState<Supplier | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  // State for the edit form
  const [editFormState, setEditFormState] = useState<Partial<Supplier>>({});

  const { toast } = useToast();
  const { hasPermission, isDataLoaded } = useApp();
  const canEdit = hasPermission('manage_products'); // Using this as a proxy

  const fetchSupplier = async () => {
    if (!supplierId || !isDataLoaded) return;
    setIsLoading(true);
    try {
      const response = await fetch(`/api/suppliers/${supplierId}`);
      if (!response.ok) {
        throw new Error('Failed to fetch supplier details.');
      }
      const data = await response.json();
      setSupplier(data);
      setEditFormState(data); // Initialize form state when data is fetched
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
      router.push('/admin/scm');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSupplier();
  }, [supplierId, isDataLoaded]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setEditFormState(prev => ({
      ...prev,
      [name]: name === 'lead_time' ? (value ? parseInt(value, 10) : undefined) : value,
    }));
  };

  const handleSaveChanges = async () => {
    if (!canEdit || !editFormState.name) {
      toast({ title: "Validation Error", description: "Supplier name cannot be empty.", variant: "destructive"});
      return;
    }
    setIsSaving(true);
    try {
      const response = await fetch(`/api/suppliers/${supplierId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editFormState),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || 'Failed to update supplier.');
      }
      
      const updatedSupplier = await response.json();
      setSupplier(updatedSupplier);
      toast({ title: "Success", description: "Supplier details updated successfully." });
      setIsEditing(false); // Close the dialog
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsSaving(false);
    }
  };


  if (isLoading || !isDataLoaded) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="animate-spin h-8 w-8 text-primary" /></div>;
  }

  if (!supplier) {
    return <div>Supplier not found.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <Button variant="outline" onClick={() => router.push('/admin/scm')}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to SCM Dashboard
        </Button>
        {canEdit && (
          <Dialog open={isEditing} onOpenChange={setIsEditing}>
            <DialogTrigger asChild>
              <Button onClick={() => setEditFormState(supplier)}><Edit className="mr-2 h-4 w-4" /> Edit Supplier</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Edit Supplier: {supplier.name}</DialogTitle>
                <DialogDescription>Update the details for this supplier.</DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-1">
                  <Label htmlFor="edit-name">Company Name</Label>
                  <Input id="edit-name" name="name" value={editFormState.name || ''} onChange={handleInputChange} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="edit-email">Contact Email</Label>
                  <Input id="edit-email" name="contact_email" type="email" value={editFormState.contact_email || ''} onChange={handleInputChange} />
                </div>
                 <div className="space-y-1">
                  <Label htmlFor="edit-phone">Phone</Label>
                  <Input id="edit-phone" name="phone" type="tel" value={editFormState.phone || ''} onChange={handleInputChange} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="edit-lead_time">Lead Time (Days)</Label>
                  <Input id="edit-lead_time" name="lead_time" type="number" value={editFormState.lead_time || ''} onChange={handleInputChange} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="edit-notes">Notes</Label>
                  <Textarea id="edit-notes" name="notes" value={editFormState.notes || ''} onChange={handleInputChange} />
                </div>
              </div>
              <DialogFooter>
                <DialogClose asChild><Button variant="outline" disabled={isSaving}>Cancel</Button></DialogClose>
                <Button onClick={handleSaveChanges} disabled={isSaving}>
                  {isSaving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving...</> : 'Save Changes'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl flex items-center gap-3">
            <Globe className="h-7 w-7 text-primary" />
            {supplier.name}
          </CardTitle>
          <CardDescription>Supplier ID: {supplier.id}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <InfoRow icon={Mail} label="Email" value={supplier.contact_email} />
          <InfoRow icon={Phone} label="Phone" value={supplier.phone} />
          <InfoRow icon={Clock} label="Lead Time" value={supplier.lead_time ? `${supplier.lead_time} days` : 'Not set'} />
          <InfoRow icon={FileText} label="Notes" value={supplier.notes} isBlock={true} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl flex items-center gap-3">
            <Paperclip className="h-6 w-6 text-primary" />
            Attachments
          </CardTitle>
        </CardHeader>
        <CardContent>
          {supplier.attachments && supplier.attachments.length > 0 ? (
            <ul className="space-y-2">
              {supplier.attachments.map(att => (
                <li key={att.id}>
                   <a href={`/api/uploads/${att.file_path}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 p-2 border rounded-md hover:bg-muted">
                      <FileText className="h-5 w-5 text-muted-foreground" />
                      <div>
                        <p className="text-sm font-medium text-primary">{att.original_name}</p>
                        <p className="text-xs text-muted-foreground">Uploaded on: {format(new Date(att.uploaded_at), 'PPP')}</p>
                      </div>
                    </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No attachments for this supplier.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const InfoRow = ({ icon: Icon, label, value, isBlock = false }: { icon: React.ElementType, label: string, value?: string | null, isBlock?: boolean }) => {
  if (!value) return null;
  return (
    <div className={`flex gap-3 ${isBlock ? 'flex-col items-start' : 'items-center'}`}>
      <div className="flex items-center gap-2 text-muted-foreground">
        <Icon className="h-5 w-5" />
        <span className="font-semibold text-sm">{label}:</span>
      </div>
      <p className={`text-sm ${isBlock ? 'mt-1 pl-7 whitespace-pre-wrap' : ''}`}>{value}</p>
    </div>
  );
};
