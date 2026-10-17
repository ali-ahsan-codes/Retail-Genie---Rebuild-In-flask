// src/app/(main)/admin/scm/po/[poId]/page.tsx
'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ArrowLeft, Edit, FileText, Truck, Banknote, Calendar, CheckCircle, Package, Loader2, Paperclip, ThumbsUp, UserSquare, Warehouse, ListChecks, Printer, Ship, Save, Phone, Car, Edit2 as EditIcon } from 'lucide-react';
import { format, isValid, parseISO } from 'date-fns';
import type { PurchaseOrder, User, POAttachment, Supplier } from '@/types';
import { useToast } from '@/hooks/use-toast';
import Link from 'next/link';
import { brandingConfig } from '@/config/branding';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { useDropzone } from 'react-dropzone';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';


function LogisticsManagementCard({ po, onUpdate }: { po: PurchaseOrder; onUpdate: () => void }) {
  const { currentUser } = useApp();
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  
  const [formData, setFormData] = useState({
    status: po.status,
    vehicle_number: po.transportationDetails?.vehicle_number || '',
    driver_contact: po.transportationDetails?.driver_contact || '',
    notes: po.transportationDetails?.notes || '',
    expected_delivery: po.expected_delivery && isValid(parseISO(po.expected_delivery)) ? format(parseISO(po.expected_delivery), 'yyyy-MM-dd') : ''
  });

  useEffect(() => {
    setFormData({
      status: po.status,
      vehicle_number: po.transportationDetails?.vehicle_number || '',
      driver_contact: po.transportationDetails?.driver_contact || '',
      notes: po.transportationDetails?.notes || '',
      expected_delivery: po.expected_delivery && isValid(parseISO(po.expected_delivery)) ? format(parseISO(po.expected_delivery), 'yyyy-MM-dd') : ''
    });
  }, [po]);


  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData(prev => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleStatusChange = (value: PurchaseOrder['status']) => {
    setFormData(prev => ({ ...prev, status: value }));
  };

  const handleSaveChanges = async () => {
    if (!currentUser) return;
    setIsLoading(true);
    try {
        const updatePayload = {
            id: po.id,
            status: formData.status,
            expected_delivery: formData.expected_delivery ? new Date(formData.expected_delivery).toISOString() : po.expected_delivery,
            transportationDetails: { // Use camelCase to match database
                vehicle_number: formData.vehicle_number,
                driver_contact: formData.driver_contact,
                notes: formData.notes,
            },
        };

        const response = await fetch(`/api/purchase-orders/${po.id}`, {
            method: 'PUT',
            headers: { 
              'Content-Type': 'application/json',
              'x-user-id': currentUser.id
            },
            body: JSON.stringify(updatePayload),
        });

        if (!response.ok) {
           const errorData = await response.json();
           throw new Error(errorData.details || 'Failed to save logistics details.');
        }

        toast({ title: 'Success', description: 'Logistics details updated successfully.' });
        onUpdate();
    } catch (error) {
        toast({ title: 'Error', description: (error as Error).message, variant: "destructive" });
    } finally {
        setIsLoading(false);
    }
  };


  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl flex items-center"><Truck className="mr-2 h-5 w-5 text-muted-foreground" />Logistics Management</CardTitle>
        <CardDescription>Assign vehicle and driver, and track the shipment.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="status">Shipment Status</Label>
              <Select value={formData.status} onValueChange={handleStatusChange}>
                  <SelectTrigger id="status"><SelectValue /></SelectTrigger>
                  <SelectContent>
                      <SelectItem value="Confirmed">Confirmed</SelectItem>
                      <SelectItem value="Shipped">Shipped</SelectItem>
                      <SelectItem value="Delivered">Delivered</SelectItem>
                      <SelectItem value="Delayed">Delayed</SelectItem>
                      <SelectItem value="Rescheduled">Rescheduled</SelectItem>
                  </SelectContent>
              </Select>
            </div>
            <div>
                <Label htmlFor="expected_delivery">Expected Delivery</Label>
                <Input id="expected_delivery" name="expected_delivery" type="date" value={formData.expected_delivery} onChange={handleInputChange} />
            </div>
            <div>
                <Label htmlFor="vehicle_number">Vehicle Number</Label>
                <Input id="vehicle_number" name="vehicle_number" value={formData.vehicle_number} onChange={handleInputChange} />
            </div>
             <div>
                <Label htmlFor="driver_contact">Driver Contact</Label>
                <Input id="driver_contact" name="driver_contact" value={formData.driver_contact} onChange={handleInputChange} />
            </div>
             <div className="md:col-span-2">
                <Label htmlFor="notes">Transportation Notes</Label>
                <Textarea id="notes" name="notes" value={formData.notes} onChange={handleInputChange} placeholder="e.g., Gate number, specific instructions..."/>
            </div>
        </div>
      </CardContent>
       <CardFooter>
            <Button onClick={handleSaveChanges} disabled={isLoading}>
                {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : <Save className="mr-2 h-4 w-4"/>}
                Update Logistics Info
            </Button>
       </CardFooter>
    </Card>
  );
}

function LogisticsInfoCard({ po }: { po: PurchaseOrder }) {
  const hasDetails = po.transportationDetails && (po.transportationDetails.vehicle_number || po.transportationDetails.driver_contact || po.transportationDetails.notes);
  const hasDeliveryDate = po.expected_delivery && isValid(parseISO(po.expected_delivery));
  
  if (!hasDetails && !hasDeliveryDate) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl flex items-center">
            <Truck className="mr-2 h-5 w-5 text-muted-foreground" />
            Logistics Details
        </CardTitle>
        <CardDescription>Saved transportation and delivery information.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <InfoItem icon={Calendar} label="Expected Delivery" value={hasDeliveryDate ? format(parseISO(po.expected_delivery!), 'PPP') : 'Not set'} />
        {hasDetails && (
            <>
                <InfoItem icon={Car} label="Vehicle Number" value={po.transportationDetails?.vehicle_number || 'Not set'} />
                <InfoItem icon={Phone} label="Driver Contact" value={po.transportationDetails?.driver_contact || 'Not set'} />
                <InfoItem icon={FileText} label="Transportation Notes" value={po.transportationDetails?.notes || 'No notes'} isBlock={true} />
            </>
        )}
      </CardContent>
    </Card>
  );
}



export default function PurchaseOrderDetailPage() {
  const router = useRouter();
  const params = useParams();
  const poId = params.poId as string;
  const { getProductById, suppliers, users, isDataLoaded, currentUser, hasPermission } = useApp();
  const { toast } = useToast();

  const [poDetails, setPoDetails] = useState<PurchaseOrder | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isPrintDialogOpen, setIsPrintDialogOpen] = useState(false);

  const fetchPoDetails = useCallback(async () => {
    if (!poId || !isDataLoaded) return;
    setIsLoading(true);
    try {
      const response = await fetch(`/api/purchase-orders/${poId}`);
      if (!response.ok) {
        throw new Error('Failed to fetch purchase order details');
      }
      let data = await response.json();
      
      setPoDetails(data);
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
      router.push('/admin/scm');
    } finally {
      setIsLoading(false);
    }
  }, [poId, isDataLoaded, router, toast]);

  useEffect(() => {
    fetchPoDetails();
  }, [fetchPoDetails]);

  const handleConfirmPO = async () => {
    if (!poDetails) return;
    setIsConfirming(true);
    try {
      const response = await fetch(`/api/purchase-orders/${poId}/confirm`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Failed to confirm Purchase Order');
      }
      const updatedPO = await response.json();
      setPoDetails(updatedPO);
      toast({ title: 'Success', description: `PO ${poId} has been confirmed.` });
    } catch (error) {
      toast({ title: 'Error', description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsConfirming(false);
    }
  };
  
  const getStatusVariant = (status: string) => {
    switch (status) {
        case 'Draft': return 'secondary';
        case 'Pending': return 'outline';
        case 'Confirmed': return 'default';
        case 'Received': return 'default'; // A success variant would be better
        default: return 'secondary';
    }
  }
   const getStatusClass = (status: string) => {
    switch (status) {
        case 'Received': return 'bg-green-100 text-green-700 border-green-300';
        case 'Shipped': return 'bg-cyan-100 text-cyan-700 border-cyan-300';
        case 'Confirmed': return 'bg-blue-100 text-blue-700 border-blue-300';
        default: return '';
    }
  }

  const handlePrint = () => {
    if (!poDetails || !suppliers || suppliers.length === 0) {
        toast({ title: "Error", description: "Cannot print, PO or supplier data is not ready.", variant: "destructive"});
        return;
    }
    
    const supplierDetails = suppliers.find(s => s.id === poDetails.supplier_id);

    if (!supplierDetails) {
        toast({ title: "Error", description: "Supplier details could not be found for this PO.", variant: "destructive"});
        return;
    }

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      toast({ title: "Print Error", description: "Please allow popups for this site to print.", variant: "destructive" });
      return;
    }
    
    setIsPrintDialogOpen(false);

    const poDate = isValid(parseISO(poDetails.createdAt)) ? format(parseISO(poDetails.createdAt), "MMMM dd, yyyy") : 'N/A';
    const deliveryDate = poDetails.expected_delivery && isValid(parseISO(poDetails.expected_delivery)) ? format(parseISO(poDetails.expected_delivery), "MMMM dd, yyyy") : 'Not Specified';

    const pageContent = `
      <div class="print-container">
        <div class="header">
          <div class="header-left">
            <h1 class="po-title">PURCHASE ORDER</h1>
            <p><strong>PO Number:</strong> ${poDetails.id}</p>
            <p><strong>Date:</strong> ${poDate}</p>
            <p><strong>Status:</strong> ${poDetails.status}</p>
          </div>
          <div class="header-right">
            <h2>${brandingConfig.companyNameForInvoice}</h2>
            <p>${brandingConfig.companyAddressForInvoice.replace(/\\n/g, '<br/>')}</p>
            <p>Phone: ${brandingConfig.companyPhoneForInvoice}</p>
            ${brandingConfig.companyWebsiteForInvoice ? `<p>Web: ${brandingConfig.companyWebsiteForInvoice}</p>` : ''}
          </div>
        </div>

        <div class="details-grid">
          <div>
            <h3>Supplier:</h3>
            <p><strong>${supplierDetails?.name || 'N/A'}</strong></p>
            <p>${supplierDetails?.contact_email || ''}</p>
            <p>${supplierDetails?.phone || ''}</p>
          </div>
          <div>
            <h3>Shipping To:</h3>
            <p><strong>${brandingConfig.companyNameForInvoice}</strong></p>
            <p>${brandingConfig.companyAddressForInvoice.replace(/\\n/g, '<br/>')}</p>
          </div>
        </div>

        <table class="items-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Item Description</th>
              <th>SKU</th>
              <th class="text-center">Qty Ordered</th>
            </tr>
          </thead>
          <tbody>
            ${(poDetails.items || []).map((item, index) => {
              const product = getProductById(item.product_id);
              return `
                <tr>
                  <td>${index + 1}</td>
                  <td>${product?.name || 'Unknown Item'}</td>
                  <td>${product?.sku || 'N/A'}</td>
                  <td class="text-center">${item.quantity_ordered}</td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
        
        <div class="notes-section">
          <h4>Delivery Information:</h4>
          <p>Please deliver by: <strong>${deliveryDate}</strong></p>
          <p>Payment Deadline: <strong>${poDetails.deadline && isValid(parseISO(poDetails.deadline)) ? format(parseISO(poDetails.deadline), 'MMMM dd, yyyy') : 'Not Specified'}</strong></p>
        </div>

        <div class="footer">
          <p>Thank you for your business!</p>
        </div>
      </div>
    `;

    const printStyles = `
      <style>
        @page { size: A4; margin: 0.75in; }
        body { font-family: Arial, sans-serif; color: #333; font-size: 10pt; }
        .print-container { width: 100%; }
        .header { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 1rem; border-bottom: 2px solid #333; }
        .header-left { text-align: left; }
        .header-right { text-align: right; font-size: 0.9em; }
        .po-title { font-size: 2.2em; font-weight: bold; color: #000; margin-bottom: 0.5rem; }
        .details-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.5rem; padding: 1rem; border: 1px solid #eee; background-color: #fcfcfc; border-radius: 8px;}
        .details-grid h3 { font-size: 1em; font-weight: bold; color: #555; margin-bottom: 0.5rem; border-bottom: 1px solid #eee; padding-bottom: 0.25rem; }
        .details-grid p { margin: 0 0 0.25rem 0; }
        .items-table { width: 100%; border-collapse: collapse; margin-top: 1.5rem; font-size: 0.95em; }
        .items-table th, .items-table td { border: 1px solid #ddd; padding: 0.6rem; text-align: left; }
        .items-table th { background-color: #f2f2f2 !important; font-weight: bold; }
        .items-table .text-right { text-align: right; }
        .items-table .text-center { text-align: center; }
        .notes-section { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #eee; }
        .notes-section h4 { font-weight: bold; margin-bottom: 0.5rem; color: #444; }
        .footer { text-align: center; margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #ddd; font-size: 0.8em; color: #777; }
      </style>
    `;

    printWindow.document.write(`<html><head><title>Purchase Order - ${poDetails.id}</title>${printStyles}</head><body>${pageContent}</body></html>`);
    printWindow.document.close();
    setTimeout(() => {
        printWindow.print();
    }, 250);
  };
  

  if (isLoading || !isDataLoaded) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="animate-spin h-8 w-8 text-primary" /></div>;
  }

  if (!poDetails) {
    return <div>Purchase Order not found.</div>;
  }
  
  const supplier = suppliers.find(s => s.id === poDetails.supplier_id);
  const canManageLogistics = currentUser?.role === 'logistics';
  const canManageAdminTasks = currentUser?.role === 'admin' || hasPermission('manage_suppliers');


  const storekeeperAttachments = (poDetails.attachments || []).filter(att => {
      const uploader = users.find(u => u.id === att.uploaded_by_id);
      return uploader?.role === 'storekeeper';
  });

  return (
    <div className="space-y-6">
       <div className="flex justify-between items-center">
        <Button variant="outline" onClick={() => router.back()}>
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to Dashboard
        </Button>
        {canManageAdminTasks && (
            <div className="flex gap-2">
                <Button variant="outline" asChild>
                    <Link href={`/admin/scm/po/${poId}/edit`}><Edit className="mr-2 h-4 w-4" /> Edit PO</Link>
                </Button>
                <Dialog open={isPrintDialogOpen} onOpenChange={setIsPrintDialogOpen}>
                    <DialogTrigger asChild>
                        <Button><Printer className="mr-2 h-4 w-4" /> Print PO</Button>
                    </DialogTrigger>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Print Purchase Order</DialogTitle>
                            <DialogDescription>
                                This will open a new window with a print-friendly version of the PO.
                            </DialogDescription>
                        </DialogHeader>
                        <Button onClick={handlePrint} className="w-full">Proceed to Print</Button>
                    </DialogContent>
                </Dialog>
            </div>
        )}
      </div>
      
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Purchase Order Details</CardTitle>
          <div className="flex justify-between items-start">
            <CardDescription>PO Number: <span className="font-semibold text-primary">{poDetails.id}</span></CardDescription>
            <Badge variant={getStatusVariant(poDetails.status)} className={getStatusClass(poDetails.status)}>{poDetails.status}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 text-sm">
            <InfoItem icon={Package} label="Supplier" value={supplier?.name || 'N/A'} />
            <InfoItem icon={Calendar} label="Created On" value={isValid(parseISO(poDetails.createdAt)) ? format(new Date(poDetails.createdAt), 'PPP') : 'N/A'} />
            
            {canManageAdminTasks && (
                <>
                    <InfoItem icon={Banknote} label="Total Amount" value={`OMR ${(poDetails.total_amount || 0).toFixed(2)}`} />
                    <InfoItem icon={CheckCircle} label="Advance Paid" value={`OMR ${(poDetails.advance_paid || 0).toFixed(2)}`} />
                    <InfoItem icon={Calendar} label="Payment Deadline" value={poDetails.deadline && isValid(parseISO(poDetails.deadline)) ? format(new Date(poDetails.deadline), 'PPP') : 'Not set'} />
                </>
            )}
          </div>
          
          <Separator className="my-6" />

          <h3 className="text-lg font-semibold mb-4">Items in this Order</h3>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>Qty Ordered</TableHead>
                <TableHead>Qty Received</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {poDetails.items.map(item => {
                const product = getProductById(item.product_id);
                return (
                <TableRow key={item.product_id}>
                  <TableCell className="font-medium">{product?.name || 'Unknown Product'}</TableCell>
                  <TableCell>{item.quantity_ordered}</TableCell>
                  <TableCell>{item.quantity_received}</TableCell>
                </TableRow>
              )})}
            </TableBody>
          </Table>

        </CardContent>
         {canManageAdminTasks && poDetails.status === 'Draft' && (
             <CardFooter className="border-t pt-4">
                <Button onClick={handleConfirmPO} disabled={isConfirming}>
                    {isConfirming ? <Loader2 className="animate-spin mr-2" /> : <ThumbsUp className="mr-2 h-4 w-4" />}
                    Confirm PO with Supplier
                </Button>
            </CardFooter>
         )}
         {canManageAdminTasks && poDetails.status === 'Confirmed' && (
             <CardFooter className="border-t pt-4">
                <p className="text-sm text-blue-600 font-medium">This PO is confirmed and awaiting stock arrival.</p>
            </CardFooter>
         )}
      </Card>
      
      <LogisticsInfoCard po={poDetails} />

      {(canManageAdminTasks && !canManageLogistics) && (
        <ProcessChecklist po={poDetails} attachments={poDetails.attachments || []} />
      )}
      
       {(canManageLogistics || (canManageAdminTasks && (poDetails.status !== 'Draft' && poDetails.status !== 'Received'))) && (
         <LogisticsManagementCard po={poDetails} onUpdate={fetchPoDetails} />
       )}

      
        {(canManageAdminTasks && !canManageLogistics) && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                 <RoleActivityCard po={poDetails} users={users} title="Logistics Activity" icon={UserSquare} role="logistics" />
                 <RoleActivityCard po={poDetails} users={users} title="Storekeeper Activity" icon={Warehouse} role="storekeeper" />
            </div>
        )}
    </div>
  );
}

const InfoItem = ({ icon: Icon, label, value, isBlock = false }: { icon: React.ElementType, label: string, value: string | null | undefined, isBlock?: boolean }) => {
    if (!value) return null;
    return (
      <div className={`flex gap-3 ${isBlock ? 'items-start' : 'items-center'}`}>
        <Icon className="h-5 w-5 text-muted-foreground mt-1 flex-shrink-0" />
        <div>
          <p className="text-muted-foreground text-xs">{label}</p>
          <p className={`font-medium ${isBlock ? 'whitespace-pre-wrap' : ''}`}>{value}</p>
        </div>
      </div>
    );
};


const RoleActivityCard = ({ po, users, title, icon: Icon, role }: { po: PurchaseOrder, users: User[], title: string, icon: React.ElementType, role: 'logistics' | 'storekeeper' }) => {
    const attachments = (po.attachments || []).filter(att => {
        const uploader = users.find(u => u.id === att.uploaded_by_id);
        return uploader?.role === role;
    });

    const hasLogisticsDetails = role === 'logistics' && po.transportationDetails && (po.transportationDetails.vehicle_number || po.transportationDetails.driver_contact);
    
    const wasShipped = role === 'logistics' && po.status === 'Shipped';
    
    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-xl flex items-center"><Icon className="mr-2 h-5 w-5 text-muted-foreground"/>{title}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
                {role === 'logistics' && (
                    <>
                        {wasShipped && <InfoItem icon={Ship} label="Status Updated" value="Marked as Shipped" />}
                        {hasLogisticsDetails && <InfoItem icon={Car} label="Vehicle Assigned" value={po.transportationDetails?.vehicle_number || 'N/A'} />}
                        {hasLogisticsDetails && <InfoItem icon={Phone} label="Driver Contact" value={po.transportationDetails?.driver_contact || 'N/A'} />}
                        {attachments.length > 0 && hasLogisticsDetails && <Separator className="my-2"/>}
                    </>
                )}

                {attachments && attachments.length > 0 && (
                    <div className="space-y-2">
                        <h4 className="text-sm font-semibold">Uploaded Documents:</h4>
                        {attachments.map(att => {
                            const uploader = users.find(u => u.id === att.uploaded_by_id);
                            return (
                                <a key={att.id} href={`/api/uploads/${att.file_path}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 p-2 border rounded-md hover:bg-muted">
                                    <Paperclip className="h-5 w-5 text-muted-foreground" />
                                    <div>
                                        <p className="text-sm font-medium text-primary">{att.original_name}</p>
                                        <p className="text-xs text-muted-foreground">
                                            Uploaded by: {uploader?.username || 'Unknown'} on {format(parseISO(att.uploaded_at), 'PPP')}
                                        </p>
                                    </div>
                                </a>
                            )
                        })}
                    </div>
                )}
                
                {!wasShipped && !hasLogisticsDetails && attachments.length === 0 && (
                     <p className="text-sm text-muted-foreground">No activity recorded by this role for this PO yet.</p>
                )}
            </CardContent>
        </Card>
    )
}

function ProcessChecklist({ po, attachments }: { po: PurchaseOrder, attachments: POAttachment[]}) {
    const isConfirmed = po.status === 'Confirmed' || po.status === 'Shipped' || po.status === 'Received';
    const isPaid = po.advance_paid && po.advance_paid > 0;
    const hasGrnDocs = attachments.some(att => att.type === 'grn');
    const isGoodsReceived = po.status === 'Received';
    const isShipped = po.status === 'Shipped' || po.status === 'Received';


    const [manualOverrides, setManualOverrides] = useState<Record<string, boolean>>({});

    const handleCheckChange = (item: string, checked: boolean) => {
        setManualOverrides(prev => ({...prev, [item]: checked}));
    };
    
    const checklistItems = [
        { id: 'confirmed', label: 'PO Confirmed with Supplier', checked: isConfirmed },
        { id: 'paid', label: 'Advance/Full Payment Processed', checked: !!isPaid },
        { id: 'shipped', label: 'Goods Shipped by Supplier', checked: isShipped},
        { id: 'grn', label: 'GRN Documents Uploaded', checked: hasGrnDocs },
        { id: 'received', label: 'Goods Received by Storekeeper', checked: isGoodsReceived },
    ];

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-xl flex items-center"><ListChecks className="mr-2 h-5 w-5 text-muted-foreground"/>Process Checklist</CardTitle>
                <CardDescription>Track the procurement process. Admins can manually mark items as complete if handled offline.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
                {checklistItems.map(item => (
                    <div key={item.id} className="flex items-center space-x-3 p-2 border rounded-md">
                        <Checkbox
                            id={`checklist-${item.id}`}
                            checked={manualOverrides[item.id] ?? item.checked}
                            onCheckedChange={(checked) => handleCheckChange(item.id, Boolean(checked))}
                        />
                        <Label htmlFor={`checklist-${item.id}`} className="text-sm font-medium">
                            {item.label}
                        </Label>
                        {(manualOverrides[item.id] === undefined && !item.checked) && <Badge variant="outline">Pending</Badge>}
                        {(manualOverrides[item.id] === undefined && item.checked) && <Badge className="bg-green-100 text-green-700">Auto-Verified</Badge>}
                        {manualOverrides[item.id] === true && <Badge className="bg-blue-100 text-blue-700">Manually Marked</Badge>}
                    </div>
                ))}
            </CardContent>
        </Card>
    );
}
