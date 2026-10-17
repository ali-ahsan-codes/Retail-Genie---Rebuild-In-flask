
// src/app/(main)/admin/scm/page.tsx
'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useApp } from '@/context/AppContext';
import { ShieldAlert, Users, Package, ShoppingCart, Truck, CreditCard, ClipboardCheck, ChevronsRight, FilePlus, FileUp, Trash2, Edit, Search, History } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Product, Supplier, SupplierProduct, PurchaseOrder, POAttachment, User } from '@/types'; 
import { useToast } from '@/hooks/use-toast';
import { addSupplierProduct, addSupplier, getSuppliers, deleteSupplierProduct, deleteSupplier as apiDeleteSupplier, createPurchaseOrder, getPurchaseOrders } from '@/lib/database';
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
import { Checkbox } from '@/components/ui/checkbox';
import Link from 'next/link'; 
import { ScrollArea } from '@/components/ui/scroll-area';
import { format, parseISO } from 'date-fns';
import { useDropzone } from 'react-dropzone';


type POItem = {
    productId?: string;
    name: string;
    sku: string;
    quantity: number;
    isManual: boolean;
};

type POActivity = {
    type: 'STATUS_CHANGE' | 'ATTACHMENT_UPLOAD' | 'STOCK_RECEIPT';
    poId: string;
    timestamp: string;
    description: string;
    user?: Pick<User, 'id' | 'username'>;
};


export default function ScmDashboardPage() {
  const { hasPermission, products, getProductById, users } = useApp();
  const canViewPage = hasPermission('manage_products'); // Using manage_products as a proxy for SCM for now
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [purchaseOrders, setPurchaseOrders] = useState<PurchaseOrder[]>([]);
  const { toast } = useToast();

  const fetchPageData = async () => {
      try {
          const [fetchedSuppliers, fetchedPOs] = await Promise.all([
              getSuppliers(),
              getPurchaseOrders() // Fetch POs
          ]);
          setSuppliers(fetchedSuppliers);
          // Correctly parse date string before sorting
          setPurchaseOrders(fetchedPOs.sort((a,b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime()));
      } catch (error) {
          toast({ title: "Error", description: "Could not load SCM data.", variant: "destructive"});
      }
  };

  useEffect(() => {
      fetchPageData();
  }, []);

  if (!canViewPage) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to access the SCM dashboard.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Supply Chain Management</CardTitle>
          <CardDescription>Manage suppliers, purchase orders, and inventory logistics.</CardDescription>
        </CardHeader>
      </Card>

      <Tabs defaultValue="suppliers" className="w-full">
        <TabsList className="grid w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-4">
          <TabsTrigger value="suppliers"><Users className="mr-2 h-4 w-4" />Suppliers</TabsTrigger>
          <TabsTrigger value="products"><Package className="mr-2 h-4 w-4" />Supplier Products</TabsTrigger>
          <TabsTrigger value="purchase_orders"><ShoppingCart className="mr-2 h-4 w-4" />Purchase Orders</TabsTrigger>
          <TabsTrigger value="logistics"><Truck className="mr-2 h-4 w-4" />Receiving & Storage</TabsTrigger>
        </TabsList>
        
        <TabsContent value="suppliers" className="mt-4">
          <SupplierManagementTab suppliers={suppliers} onSupplierChange={fetchPageData}/>
        </TabsContent>
        <TabsContent value="products" className="mt-4">
          <SupplierProductManagementTab suppliers={suppliers} />
        </TabsContent>
        <TabsContent value="purchase_orders" className="mt-4">
            <PurchaseOrderManagementTab suppliers={suppliers} products={products} getProductById={getProductById} pos={purchaseOrders} onPoChange={fetchPageData}/>
        </TabsContent>
        <TabsContent value="logistics" className="mt-4">
            <ReceivingStorageTab purchaseOrders={purchaseOrders} users={users} suppliers={suppliers} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function SupplierManagementTab({ suppliers, onSupplierChange }: { suppliers: Supplier[], onSupplierChange: () => void }) {
  const [id, setId] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [leadTime, setLeadTime] = useState('');
  const [notes, setNotes] = useState('');
  const [documents, setDocuments] = useState<File[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { toast } = useToast();

  const { getRootProps, getInputProps } = useDropzone({
    onDrop: (acceptedFiles) => {
        setDocuments(prev => [...prev, ...acceptedFiles]);
    }
  });

  const removeDocument = (index: number) => {
    setDocuments(prev => prev.filter((_, i) => i !== index));
  };

  const handleAddSupplier = async () => {
    if (!name) {
      toast({ title: "Error", description: "Supplier name is required.", variant: "destructive" });
      return;
    }
    setIsLoading(true);

    const formData = new FormData();
    if (id) formData.append('id', id);
    formData.append('name', name);
    if(email) formData.append('contact_email', email);
    if(phone) formData.append('phone', phone);
    if(leadTime) formData.append('lead_time', leadTime);
    if(notes) formData.append('notes', notes);
    documents.forEach(file => formData.append('documents', file));

    try {
      const newSupplier = await addSupplier(formData);
      if (newSupplier) {
        toast({ title: "Success", description: "Supplier added successfully." });
        // Reset form and refresh list
        setId('');
        setName('');
        setEmail('');
        setPhone('');
        setLeadTime('');
        setNotes('');
        setDocuments([]);
        onSupplierChange();
      }
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteSupplier = async (supplierId: string) => {
    setIsLoading(true);
    try {
        await apiDeleteSupplier(supplierId);
        toast({ title: "Success", description: "Supplier deleted successfully." });
        onSupplierChange();
    } catch (error) {
        toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
    } finally {
        setIsLoading(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2">
        <Card>
          <CardHeader><CardTitle>Supplier List</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Lead Time (Days)</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {suppliers.map(s => (
                  <TableRow key={s.id}>
                    <TableCell>{s.name}</TableCell>
                    <TableCell>{s.contact_email || s.phone || 'N/A'}</TableCell>
                    <TableCell>{s.lead_time ?? 'N/A'}</TableCell>
                    <TableCell className="text-right space-x-1">
                        <Button asChild variant="ghost" size="icon" className="h-8 w-8">
                            <Link href={`/admin/scm/suppliers/${s.id}`}><Edit className="h-4 w-4" /></Link>
                        </Button>
                        <AlertDialog>
                            <AlertDialogTrigger asChild>
                                <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive">
                                    <Trash2 className="h-4 w-4" />
                                </Button>
                            </AlertDialogTrigger>
                            <AlertDialogContent>
                                <AlertDialogHeader>
                                    <AlertDialogTitle>Delete Supplier?</AlertDialogTitle>
                                    <AlertDialogDescription>
                                        This will permanently delete the supplier "{s.name}" and all associated product links. This action cannot be undone.
                                    </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                                    <AlertDialogAction onClick={() => handleDeleteSupplier(s.id)} className="bg-destructive hover:bg-destructive/90">
                                        Delete
                                    </AlertDialogAction>
                                </AlertDialogFooter>
                            </AlertDialogContent>
                        </AlertDialog>
                    </TableCell>
                  </TableRow>
                ))}
                 {suppliers.length === 0 && (
                  <TableRow><TableCell colSpan={4} className="text-center">No suppliers added yet.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
      <div className="lg:col-span-1">
        <Card>
          <CardHeader><CardTitle>Add New Supplier</CardTitle></CardHeader>
          <CardContent className="space-y-4">
             <div className="space-y-1">
              <Label htmlFor="sup-id">Supplier ID (Optional)</Label>
              <Input id="sup-id" placeholder="Leave blank to auto-generate" value={id} onChange={e => setId(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sup-name">Company Name</Label>
              <Input id="sup-name" placeholder="Supplier Inc." value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sup-email">Contact Email</Label>
              <Input id="sup-email" type="email" placeholder="contact@supplier.com" value={email} onChange={e => setEmail(e.target.value)} />
            </div>
             <div className="space-y-1">
              <Label htmlFor="sup-phone">Phone</Label>
              <Input id="sup-phone" type="tel" placeholder="+123456789" value={phone} onChange={e => setPhone(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sup-lead-time">Lead Time (Days)</Label>
              <Input id="sup-lead-time" type="number" placeholder="14" value={leadTime} onChange={e => setLeadTime(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sup-notes">Notes</Label>
              <Textarea id="sup-notes" placeholder="Notes about supplier..." value={notes} onChange={e => setNotes(e.target.value)} />
            </div>
            <div className="space-y-2">
                <Label>Upload Documents</Label>
                <div {...getRootProps({className: 'p-4 border-2 border-dashed rounded-lg text-center cursor-pointer hover:border-primary'})}>
                    <input {...getInputProps()} />
                    <p className="text-xs text-muted-foreground">Drag 'n' drop files here, or click to select</p>
                </div>
                {documents.length > 0 && (
                    <div className="space-y-1">
                        {documents.map((file, index) => (
                            <div key={index} className="text-xs flex justify-between items-center bg-muted p-1 rounded">
                                <span>{file.name}</span>
                                <Button size="sm" variant="ghost" onClick={() => removeDocument(index)} className="h-6 w-6 p-0"><Trash2 className="h-3 w-3 text-destructive"/></Button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
            <Button className="w-full" onClick={handleAddSupplier} disabled={isLoading}>
              {isLoading ? 'Adding...' : <><FilePlus className="mr-2 h-4 w-4" />Add Supplier</>}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SupplierProductManagementTab({ suppliers }: { suppliers: Supplier[] }) {
    const { products, getProductById } = useApp();
    const [selectedSupplierId, setSelectedSupplierId] = useState<string>('');
    const [selectedProductId, setSelectedProductId] = useState<string>('');
    const [unitPrice, setUnitPrice] = useState<string>('');
    const [documentFile, setDocumentFile] = useState<File | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const { toast } = useToast();
    
    const [linkedProducts, setLinkedProducts] = useState<SupplierProduct[]>([]);

    const fetchLinkedProducts = async () => {
        try {
            const response = await fetch('/api/scm/supplier-products');
            if (!response.ok) {
                throw new Error('Failed to fetch linked products');
            }
            const data = await response.json();
            setLinkedProducts(data);
        } catch (error) {
            toast({ title: "Error", description: "Could not load linked products.", variant: "destructive"});
        }
    };

    useEffect(() => {
        fetchLinkedProducts();
    }, []);

    const handleLinkProduct = async () => {
        if (!selectedSupplierId || !selectedProductId || !unitPrice) {
            toast({ title: "Error", description: "Please select a supplier, product, and enter a unit price.", variant: "destructive" });
            return;
        }
        setIsLoading(true);
        const data: Omit<SupplierProduct, 'id' | 'document_path'> = {
            supplier_id: selectedSupplierId,
            product_id: selectedProductId,
            unit_price: parseFloat(unitPrice),
        };

        try {
            const newLink = await addSupplierProduct(data);
            if (newLink) {
                toast({ title: "Success", description: "Product linked to supplier successfully." });
                setLinkedProducts(prev => [...prev, newLink].sort((a,b) => (getProductById(a.product_id)?.name || '').localeCompare(getProductById(b.product_id)?.name || ''))); // Optimistic update
                // Reset form
                setSelectedSupplierId('');
                setSelectedProductId('');
                setUnitPrice('');
            }
        } catch (error) {
            console.error("Failed to link product", error);
            toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
        } finally {
            setIsLoading(false);
        }
    };

    const handleDeleteLinkedProduct = async (linkId: string) => {
        setIsLoading(true);
        try {
            await deleteSupplierProduct(linkId);
            toast({ title: "Success", description: "Product link removed." });
            setLinkedProducts(prev => prev.filter(p => p.id !== linkId));
        } catch (error) {
            toast({ title: "Error", description: (error as Error).message, variant: "destructive" });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
                <Card>
                    <CardHeader><CardTitle>Linked Products</CardTitle></CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Product</TableHead>
                                    <TableHead>Supplier</TableHead>
                                    <TableHead>Unit Price</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {linkedProducts.map(p => (
                                    <TableRow key={p.id}>
                                        <TableCell>{getProductById(p.product_id)?.name || p.product_id}</TableCell>
                                        <TableCell>{suppliers.find(s => s.id === p.supplier_id)?.name || p.supplier_id}</TableCell>
                                        <TableCell>OMR {typeof p.unit_price === 'number' ? p.unit_price.toFixed(2) : 'N/A'}</TableCell>
                                        <TableCell className="text-right">
                                            <AlertDialog>
                                                <AlertDialogTrigger asChild>
                                                    <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive hover:text-destructive">
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </AlertDialogTrigger>
                                                <AlertDialogContent>
                                                    <AlertDialogHeader>
                                                        <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                                                        <AlertDialogDescription>
                                                            This will remove the link between this product and supplier. It will not delete the product or the supplier themselves.
                                                        </AlertDialogDescription>
                                                    </AlertDialogHeader>
                                                    <AlertDialogFooter>
                                                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                                                        <AlertDialogAction onClick={() => handleDeleteLinkedProduct(p.id)} className="bg-destructive hover:bg-destructive/90">
                                                            Delete Link
                                                        </AlertDialogAction>
                                                    </AlertDialogFooter>
                                                </AlertDialogContent>
                                            </AlertDialog>
                                        </TableCell>
                                    </TableRow>
                                ))}
                                {linkedProducts.length === 0 && (
                                    <TableRow><TableCell colSpan={4} className="text-center">No products linked to suppliers yet.</TableCell></TableRow>
                                )}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            </div>
            <div className="lg:col-span-1">
                <Card>
                    <CardHeader><CardTitle>Link Product to Supplier</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-1">
                            <Label htmlFor="sp-supplier">Supplier</Label>
                            <Select value={selectedSupplierId} onValueChange={setSelectedSupplierId}>
                                <SelectTrigger id="sp-supplier"><SelectValue placeholder="Select supplier..." /></SelectTrigger>
                                <SelectContent>{suppliers.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-1">
                           <Label htmlFor="sp-product">Product</Label>
                           <Select value={selectedProductId} onValueChange={setSelectedProductId}>
                               <SelectTrigger id="sp-product"><SelectValue placeholder="Select product..." /></SelectTrigger>
                               <SelectContent>
                                   {products.map(p => (
                                       <SelectItem key={p.id} value={p.id}>{p.name} ({p.sku})</SelectItem>
                                   ))}
                                </SelectContent>
                           </Select>
                        </div>
                         <div className="space-y-1">
                            <Label htmlFor="sp-price">Unit Price (OMR)</Label>
                            <Input id="sp-price" type="number" placeholder="10.00" value={unitPrice} onChange={e => setUnitPrice(e.target.value)} />
                        </div>
                        <div className="space-y-1">
                            <Label htmlFor="sp-doc">Upload Contract/Agreement</Label>
                            <Input id="sp-doc" type="file" onChange={e => setDocumentFile(e.target.files ? e.target.files[0] : null)} />
                        </div>
                        <Button className="w-full" onClick={handleLinkProduct} disabled={isLoading}>
                            {isLoading ? 'Linking...' : <><FilePlus className="mr-2 h-4 w-4" />Link Product</>}
                        </Button>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

function PurchaseOrderManagementTab({ suppliers, products, getProductById, pos, onPoChange }: { suppliers: any[], products: Product[], getProductById: (id: string) => Product | undefined, pos: PurchaseOrder[], onPoChange: () => void }) {
    const [isManualProduct, setIsManualProduct] = useState(false);
    const { toast } = useToast();
    
    // State for creating a PO
    const [isLoading, setIsLoading] = useState(false);
    const [poSupplierId, setPoSupplierId] = useState('');
    const [expectedDelivery, setExpectedDelivery] = useState('');
    const [paymentDeadline, setPaymentDeadline] = useState('');
    const [poItems, setPoItems] = useState<POItem[]>([]);
    
    // State for the item being added
    const [currentItemProductId, setCurrentItemProductId] = useState('');
    const [currentItemManualName, setCurrentItemManualName] = useState('');
    const [currentItemManualSku, setCurrentItemManualSku] = useState('');
    const [currentItemQuantity, setCurrentItemQuantity] = useState('');

    const [searchTerm, setSearchTerm] = useState('');

    const filteredPOs = pos.filter(po => {
        const supplierName = suppliers.find(s => s.id === po.supplier_id)?.name || '';
        return (
            po.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
            supplierName.toLowerCase().includes(searchTerm.toLowerCase()) ||
            po.status.toLowerCase().includes(searchTerm.toLowerCase())
        );
    });


    const handleAddItemToPO = () => {
        const quantity = parseInt(currentItemQuantity);
        if (isNaN(quantity) || quantity <= 0) {
            toast({ title: "Error", description: "Please enter a valid quantity.", variant: "destructive"});
            return;
        }

        let newItem: POItem | null = null;
        if (isManualProduct) {
            if (!currentItemManualName) {
                toast({ title: "Error", description: "Please enter a name for the new product.", variant: "destructive"});
                return;
            }
            newItem = {
                name: currentItemManualName,
                sku: currentItemManualSku || `NEW-${Date.now()}`,
                quantity,
                isManual: true
            };
        } else {
            if (!currentItemProductId) {
                toast({ title: "Error", description: "Please select a product.", variant: "destructive"});
                return;
            }
            const product = getProductById(currentItemProductId);
            if (product) {
                newItem = {
                    productId: product.id,
                    name: product.name,
                    sku: product.sku,
                    quantity,
                    isManual: false
                };
            }
        }

        if (newItem) {
            setPoItems(prev => [...prev, newItem!]);
            // Reset item form
            setCurrentItemProductId('');
            setCurrentItemManualName('');
            setCurrentItemManualSku('');
            setCurrentItemQuantity('');
        }
    };
    
    const handleRemovePoItem = (index: number) => {
        setPoItems(prev => prev.filter((_, i) => i !== index));
    };

    const handleGeneratePO = async () => {
        if (!poSupplierId || poItems.length === 0) {
            toast({ title: "Error", description: "Please select a supplier and add at least one item.", variant: "destructive"});
            return;
        }
        setIsLoading(true);
        try {
            const payload = {
                supplier_id: poSupplierId,
                items: poItems,
                expected_delivery: expectedDelivery || null,
                deadline: paymentDeadline || null,
            };
            await createPurchaseOrder(payload);
            toast({ title: "Success", description: "Purchase Order created successfully." });
            // Reset form
            setPoSupplierId('');
            setPoItems([]);
            setExpectedDelivery('');
            setPaymentDeadline('');
            onPoChange();
        } catch (error) {
            toast({ title: "Error", description: (error as Error).message, variant: "destructive"});
        } finally {
            setIsLoading(false);
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
            case 'Confirmed': return 'bg-blue-100 text-blue-700 border-blue-300';
            default: return '';
        }
    }


    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
                <Card>
                    <CardHeader>
                        <CardTitle>Purchase Orders</CardTitle>
                        <div className="relative mt-2">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                            <Input
                                placeholder="Search by PO Number, Supplier, Status..."
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                                className="pl-10"
                            />
                        </div>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>PO Number</TableHead>
                                    <TableHead>Supplier</TableHead>
                                    <TableHead>Total (OMR)</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead className="text-right">Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {filteredPOs.map(p => (
                                    <TableRow key={p.id}>
                                        <TableCell>{p.id}</TableCell>
                                        <TableCell>{suppliers.find(s => s.id === p.supplier_id)?.name || 'N/A'}</TableCell>
                                        <TableCell>OMR {(p.total_amount || 0).toFixed(2)}</TableCell>
                                        <TableCell><Badge variant={getStatusVariant(p.status)} className={getStatusClass(p.status)}>{p.status}</Badge></TableCell>
                                        <TableCell className="text-right">
                                            <Button asChild variant="ghost" size="sm">
                                                <Link href={`/admin/scm/po/${p.id}`}>View</Link>
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                                {filteredPOs.length === 0 && <TableRow><TableCell colSpan={5} className="text-center">No Purchase Orders yet.</TableCell></TableRow>}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            </div>
            <div className="lg:col-span-1">
                 <Card>
                    <CardHeader><CardTitle>Create Purchase Order</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                        <div className="space-y-1">
                            <Label htmlFor="po-supplier">Supplier</Label>
                            <Select value={poSupplierId} onValueChange={setPoSupplierId}><SelectTrigger id="po-supplier"><SelectValue placeholder="Select supplier..." /></SelectTrigger><SelectContent>{suppliers.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent></Select>
                        </div>
                        
                        <Separator />
                        <h4 className="font-medium">Add Items</h4>

                        <div className="flex items-center space-x-2">
                            <Checkbox id="manual-product-toggle" checked={isManualProduct} onCheckedChange={(checked) => setIsManualProduct(Boolean(checked))} />
                            <Label htmlFor="manual-product-toggle">Add a new product not in the system</Label>
                        </div>

                        {isManualProduct ? (
                            <div className="space-y-2 p-3 border rounded-md bg-muted/50">
                                <div className="space-y-1">
                                    <Label htmlFor="po-manual-product-name">New Product Name</Label>
                                    <Input id="po-manual-product-name" placeholder="Enter product name" value={currentItemManualName} onChange={e => setCurrentItemManualName(e.target.value)} />
                                </div>
                                <div className="space-y-1">
                                    <Label htmlFor="po-manual-product-sku">New Product SKU (Optional)</Label>
                                    <Input id="po-manual-product-sku" placeholder="Enter SKU" value={currentItemManualSku} onChange={e => setCurrentItemManualSku(e.target.value)} />
                                </div>
                            </div>
                        ) : (
                            <div className="space-y-1">
                               <Label htmlFor="po-product">Product</Label>
                               <Select value={currentItemProductId} onValueChange={setCurrentItemProductId}><SelectTrigger id="po-product"><SelectValue placeholder="Select product..." /></SelectTrigger>
                               <SelectContent>
                                    {products.map(p => (
                                        <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                                    ))}
                                </SelectContent>
                               </Select>
                            </div>
                        )}
                         <div className="space-y-1">
                            <Label htmlFor="po-qty">Quantity</Label>
                            <Input id="po-qty" type="number" placeholder="100" value={currentItemQuantity} onChange={e => setCurrentItemQuantity(e.target.value)} />
                        </div>
                        <Button variant="outline" size="sm" className="w-full" onClick={handleAddItemToPO}>Add Item to PO</Button>
                        
                        {poItems.length > 0 && (
                            <>
                            <Separator />
                            <h4 className="font-medium">PO Items</h4>
                            <ScrollArea className="h-40 border rounded-md p-2">
                                <div className="space-y-2">
                                    {poItems.map((item, index) => (
                                        <div key={index} className="flex justify-between items-center text-sm p-1 bg-background rounded">
                                            <span>{item.name} (Qty: {item.quantity})</span>
                                            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => handleRemovePoItem(index)}>
                                                <Trash2 className="h-4 w-4 text-destructive" />
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            </ScrollArea>
                            </>
                        )}
                        
                        <Separator />
                        <div className="space-y-1">
                            <Label htmlFor="po-delivery">Expected Delivery Date</Label>
                            <Input id="po-delivery" type="date" value={expectedDelivery} onChange={e => setExpectedDelivery(e.target.value)}/>
                        </div>
                         <div className="space-y-1">
                            <Label htmlFor="po-deadline">Payment Deadline</Label>
                            <Input id="po-deadline" type="date" value={paymentDeadline} onChange={e => setPaymentDeadline(e.target.value)}/>
                        </div>
                        <Button className="w-full" onClick={handleGeneratePO} disabled={isLoading}>
                            {isLoading ? 'Generating...' : <><FilePlus className="mr-2 h-4 w-4"/>Generate PO</>}
                        </Button>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}

function ReceivingStorageTab({ purchaseOrders, users, suppliers }: { purchaseOrders: PurchaseOrder[], users: User[], suppliers: Supplier[] }) {
    const [searchTerm, setSearchTerm] = useState('');

    const allActivities = useMemo(() => purchaseOrders.flatMap((po): POActivity[] => {
        const activities: POActivity[] = [];
        
        activities.push({
            type: 'STATUS_CHANGE',
            poId: po.id,
            timestamp: po.createdAt,
            description: `PO created for supplier ${suppliers.find(s=>s.id === po.supplier_id)?.name || 'N/A'}. Status: Draft.`,
        });
        if(po.status !== 'Draft') {
             activities.push({
                type: 'STATUS_CHANGE',
                poId: po.id,
                timestamp: po.updatedAt,
                description: `PO status updated to ${po.status}.`,
            });
        }

        (po.attachments || []).forEach((att: POAttachment) => {
            const uploader = users.find(u => u.id === att.uploaded_by_id);
            activities.push({
                type: 'ATTACHMENT_UPLOAD',
                poId: po.id,
                timestamp: att.uploaded_at,
                description: `Attachment "${att.original_name}" uploaded.`,
                user: uploader ? {id: uploader.id, username: uploader.username} : undefined,
            });
        });

        return activities;
    }).sort((a, b) => parseISO(b.timestamp).getTime() - parseISO(a.timestamp).getTime()), [purchaseOrders, suppliers, users]);

    const filteredActivities = useMemo(() => {
        if (!searchTerm.trim()) {
            return allActivities;
        }
        return allActivities.filter(activity => activity.poId.toLowerCase().includes(searchTerm.trim().toLowerCase()));
    }, [allActivities, searchTerm]);

    return (
        <Card>
            <CardHeader>
                <CardTitle>PO Activity Log</CardTitle>
                <CardDescription>A timeline of all actions taken on purchase orders.</CardDescription>
                <div className="relative pt-2">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                      placeholder="Filter by PO Number..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-10"
                  />
                </div>
            </CardHeader>
            <CardContent>
                <ScrollArea className="h-[60vh]">
                    <div className="space-y-4">
                        {filteredActivities.map((activity, index) => (
                            <div key={index} className="flex items-start gap-4">
                                <div className="flex flex-col items-center">
                                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary">
                                        <History className="h-4 w-4" />
                                    </div>
                                    {index < filteredActivities.length -1 && <div className="h-16 w-px bg-border" />}
                                </div>
                                <div>
                                    <p className="font-medium">
                                        PO: <Link href={`/admin/scm/po/${activity.poId}`} className="text-primary hover:underline">{activity.poId}</Link>
                                    </p>
                                    <p className="text-sm">{activity.description}</p>
                                    <p className="text-xs text-muted-foreground">
                                        {format(parseISO(activity.timestamp), "PPP p")}
                                        {activity.user && ` by ${activity.user.username}`}
                                    </p>
                                </div>
                            </div>
                        ))}
                        {filteredActivities.length === 0 && <p className="text-center text-muted-foreground py-8">No activities match your search.</p>}
                    </div>
                </ScrollArea>
            </CardContent>
        </Card>
    );
}

