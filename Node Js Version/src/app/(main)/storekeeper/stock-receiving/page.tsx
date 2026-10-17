// src/app/(main)/storekeeper/stock-receiving/page.tsx
'use client';
import { useState, useMemo, useEffect, useCallback } from 'react';
import { useApp } from '@/context/AppContext';
import type { PurchaseOrder, POItem, Product, User } from '@/types';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Bell, Truck, History, Package, Search, CheckSquare, Loader2, AlertCircle, ImageUp, File as FileIcon } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { getPurchaseOrders } from '@/lib/database';
import { format, parseISO } from 'date-fns';
import { useDropzone } from 'react-dropzone';
import Image from 'next/image';

type ReceivedItem = {
    poItemId: string;
    productId: string;
    receivedQuantity: number;
    notes: string;
};

// New component for the table row
function StockReceivingItemRow({
    item,
    receivedItem,
    onReceivedItemChange,
}: {
    item: POItem;
    receivedItem: ReceivedItem;
    onReceivedItemChange: (poItemId: string, field: 'receivedQuantity' | 'notes', value: string | number) => void;
}) {
    const { getProductById } = useApp();
    const product = getProductById(item.product_id);
    const remaining = item.quantity_ordered - (item.quantity_received || 0);

    return (
        <TableRow>
            <TableCell>{product?.name || 'N/A'}</TableCell>
            <TableCell>{item.quantity_ordered}</TableCell>
            <TableCell>{remaining}</TableCell>
            <TableCell>
                <Input type="number" max={remaining} min="0" value={receivedItem?.receivedQuantity || ''} onChange={(e) => onReceivedItemChange(item.id, 'receivedQuantity', parseInt(e.target.value) || 0)} className="w-24" />
            </TableCell>
            <TableCell>
                <Input value={receivedItem?.notes || ''} onChange={(e) => onReceivedItemChange(item.id, 'notes', e.target.value)} placeholder="Optional notes..." />
            </TableCell>
        </TableRow>
    );
}

export default function StockReceivingPage() {
  const [activeTab, setActiveTab] = useState('pending');
  const [allPOs, setAllPOs] = useState<PurchaseOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedPO, setSelectedPO] = useState<PurchaseOrder | null>(null);
  const [receivedItems, setReceivedItems] = useState<Record<string, ReceivedItem>>({});
  const [grnAttachments, setGrnAttachments] = useState<File[]>([]);
  const [storageEvidence, setStorageEvidence] = useState<File[]>([]);
  const { getProductById, suppliers, isDataLoaded, currentUser, loadDataFromDb } = useApp();
  const { toast } = useToast();
  const [searchTerm, setSearchTerm] = useState('');

  const fetchPOs = useCallback(async () => {
    setIsLoading(true);
    try {
      const pos = await getPurchaseOrders();
      setAllPOs(pos.sort((a, b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime()));
    } catch (error) {
      toast({ title: "Error", description: "Failed to load purchase orders.", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (isDataLoaded) {
      fetchPOs();
    }
  }, [isDataLoaded, fetchPOs]);
  
  const { getRootProps: getGrnRootProps, getInputProps: getGrnInputProps } = useDropzone({ onDrop: (files) => setGrnAttachments(prev => [...prev, ...files]) });
  const { getRootProps: getEvidenceRootProps, getInputProps: getEvidenceInputProps } = useDropzone({ onDrop: (files) => setStorageEvidence(prev => [...prev, ...files]) });


  const handleSelectPO = (po: PurchaseOrder) => {
    setSelectedPO(po);
    const initialReceived: Record<string, ReceivedItem> = {};
    po.items.forEach(item => {
      const remaining = Math.max(0, item.quantity_ordered - (item.quantity_received || 0));
      initialReceived[item.id] = {
        poItemId: item.id,
        productId: item.product_id,
        receivedQuantity: remaining, // Pre-fill with remaining qty
        notes: item.notes || ''
      };
    });
    setReceivedItems(initialReceived);
    setGrnAttachments([]);
    setStorageEvidence([]);
  };
  
  const handleReceivedItemChange = (poItemId: string, field: 'receivedQuantity' | 'notes', value: string | number) => {
    setReceivedItems(prev => ({
      ...prev,
      [poItemId]: {
        ...(prev[poItemId] || { poItemId, productId: '', receivedQuantity: 0, notes: '' }),
        [field]: value
      }
    }));
  };

  const handleSubmitReceivedStock = async () => {
    if (!selectedPO || !currentUser) return;
    
    const itemsToReceive = Object.values(receivedItems).filter(item => item.receivedQuantity > 0);
    if(itemsToReceive.length === 0) {
        toast({ title: "No items to receive", description: "Please enter a received quantity for at least one item.", variant: "destructive"});
        return;
    }
    
    const formData = new FormData();
    formData.append('poId', selectedPO.id);
    formData.append('items', JSON.stringify(itemsToReceive));
    
    grnAttachments.forEach(file => {
        formData.append('grnAttachments', file); // Use grnAttachments key
    });
    storageEvidence.forEach(file => {
        formData.append('storageEvidence', file);
    });

    setIsSubmitting(true);
    try {
      const response = await fetch(`/api/purchase-orders/${selectedPO.id}/receive`, {
        method: 'POST',
        headers: {
            'x-user-id': currentUser.id,
        },
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to submit received stock');
      }
      toast({ title: "Success", description: "Stock received successfully." });
      setSelectedPO(null);
      setReceivedItems({});
      setGrnAttachments([]);
      setStorageEvidence([]);
      await loadDataFromDb(); // Use AppContext reload
      await fetchPOs(); // Refetch POs to get the latest state for the lists
      setActiveTab('history');
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive"});
    } finally {
      setIsSubmitting(false);
    }
  };

  const filteredPOs = useMemo(() => {
    return allPOs.filter(po => {
        const supplierName = suppliers.find(s => s.id === po.supplier_id)?.name || '';
        const searchMatch =
            po.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
            supplierName.toLowerCase().includes(searchTerm.toLowerCase()) ||
            po.status.toLowerCase().includes(searchTerm.toLowerCase());

        let statusMatch = false;
        if (activeTab === 'pending') {
            statusMatch = po.status === 'Confirmed';
        } else if (activeTab === 'in_transit') {
            statusMatch = po.status === 'Shipped';
        } else if (activeTab === 'history') {
            statusMatch = po.status === 'Received';
        }

        return searchMatch && statusMatch;
    });
  }, [allPOs, suppliers, searchTerm, activeTab]);

  if (isLoading) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="animate-spin h-8 w-8 text-primary" /></div>;
  }

  const renderFileList = (files: File[], onRemove: (index: number) => void) => (
    <div className="space-y-2">
      {files.map((file, index) => (
          <div key={index} className="flex items-center justify-between p-2 border rounded-md bg-muted/30">
              <div className="flex items-center gap-2 text-sm">
                  <FileIcon className="h-4 w-4"/>
                  {file.name}
              </div>
              <Button size="sm" variant="ghost" className="text-destructive" onClick={() => onRemove(index)}>Remove</Button>
          </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-6">
       <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Stock Receiving</CardTitle>
          <CardDescription>Process incoming stock from confirmed purchase orders.</CardDescription>
        </CardHeader>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-1 sm:grid-cols-3">
            <TabsTrigger value="pending"><Bell className="mr-2 h-4 w-4" />Awaiting Delivery ({allPOs.filter(p => p.status === 'Confirmed').length})</TabsTrigger>
            <TabsTrigger value="in_transit"><Truck className="mr-2 h-4 w-4" />In Transit ({allPOs.filter(p => p.status === 'Shipped').length})</TabsTrigger>
            <TabsTrigger value="history"><History className="mr-2 h-4 w-4" />Receiving History</TabsTrigger>
        </TabsList>
        
        <div className="my-4">
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                    placeholder="Search by PO Number or Supplier..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                />
            </div>
        </div>
        
        <TabsContent value="pending" className="mt-4">
             {selectedPO ? (
             <Card>
                <CardHeader>
                    <CardTitle>Receive Stock for PO: {selectedPO.id}</CardTitle>
                    <CardDescription>Supplier: {suppliers.find(s => s.id === selectedPO.supplier_id)?.name}</CardDescription>
                     <Button onClick={() => setSelectedPO(null)} variant="outline" size="sm" className="mt-2">Back to PO List</Button>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Product</TableHead>
                                <TableHead>Ordered</TableHead>
                                <TableHead>Remaining</TableHead>
                                <TableHead>Quantity to Receive</TableHead>
                                <TableHead>Notes</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {selectedPO.items.filter(item => (item.quantity_ordered - (item.quantity_received || 0)) > 0).map(item => (
                                <StockReceivingItemRow
                                    key={item.id}
                                    item={item}
                                    receivedItem={receivedItems[item.id]}
                                    onReceivedItemChange={handleReceivedItemChange}
                                />
                            ))}
                        </TableBody>
                    </Table>

                    <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                       <div className="space-y-2">
                            <Label className="font-semibold">Upload GRN Documents</Label>
                             <div {...getGrnRootProps({className: 'p-4 border-2 border-dashed rounded-lg text-center cursor-pointer hover:border-primary'})}>
                                <input {...getGrnInputProps()} />
                                <div className="flex flex-col items-center gap-2 text-muted-foreground"><ImageUp className="h-8 w-8" /><p>Drop GRN/Invoice here</p></div>
                            </div>
                            {grnAttachments.length > 0 && renderFileList(grnAttachments, (index) => setGrnAttachments(prev => prev.filter((_, i) => i !== index)))}
                        </div>
                        <div className="space-y-2">
                           <Label className="font-semibold">Upload Storage Evidence</Label>
                           <div {...getEvidenceRootProps({className: 'p-4 border-2 border-dashed rounded-lg text-center cursor-pointer hover:border-primary'})}>
                                <input {...getEvidenceInputProps()} />
                                <div className="flex flex-col items-center gap-2 text-muted-foreground"><ImageUp className="h-8 w-8" /><p>Drop storage photos here</p></div>
                            </div>
                            {storageEvidence.length > 0 && renderFileList(storageEvidence, (index) => setStorageEvidence(prev => prev.filter((_, i) => i !== index)))}
                        </div>
                    </div>
                    
                    <div className="mt-6 flex justify-end">
                        <Button onClick={handleSubmitReceivedStock} disabled={isLoading || isSubmitting}>
                            {isSubmitting ? <Loader2 className="animate-spin mr-2"/> : <CheckSquare className="mr-2 h-4 w-4"/>}
                            Submit Received Stock
                        </Button>
                    </div>
                </CardContent>
             </Card>
           ) : (
            <Card>
                <CardContent className="p-4">
                    {filteredPOs.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <AlertCircle className="mx-auto h-10 w-10 mb-4" />
                            <p>No confirmed purchase orders are awaiting delivery.</p>
                        </div>
                    ) : (
                    <Table>
                        <TableHeader><TableRow><TableHead>PO Number</TableHead><TableHead>Supplier</TableHead><TableHead>Expected Delivery</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                        <TableBody>
                            {filteredPOs.map(po => (
                                <TableRow key={po.id}>
                                    <TableCell>{po.id}</TableCell>
                                    <TableCell>{suppliers.find(s => s.id === po.supplier_id)?.name || 'N/A'}</TableCell>
                                    <TableCell>{po.expected_delivery ? format(parseISO(po.expected_delivery), 'PPP') : 'N/A'}</TableCell>
                                    <TableCell className="text-right"><Button variant="outline" size="sm" onClick={() => handleSelectPO(po)}>Receive Stock</Button></TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                    )}
                </CardContent>
            </Card>
           )}
        </TabsContent>
        <TabsContent value="in_transit" className="mt-4">
             {selectedPO ? (
             <Card>
                <CardHeader>
                    <CardTitle>Receive Stock for PO: {selectedPO.id}</CardTitle>
                    <CardDescription>Supplier: {suppliers.find(s => s.id === selectedPO.supplier_id)?.name}</CardDescription>
                     <Button onClick={() => setSelectedPO(null)} variant="outline" size="sm" className="mt-2">Back to PO List</Button>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Product</TableHead>
                                <TableHead>Ordered</TableHead>
                                <TableHead>Remaining</TableHead>
                                <TableHead>Quantity to Receive</TableHead>
                                <TableHead>Notes</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {selectedPO.items.filter(item => (item.quantity_ordered - (item.quantity_received || 0)) > 0).map(item => (
                                <StockReceivingItemRow
                                    key={item.id}
                                    item={item}
                                    receivedItem={receivedItems[item.id]}
                                    onReceivedItemChange={handleReceivedItemChange}
                                />
                            ))}
                        </TableBody>
                    </Table>

                    <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                       <div className="space-y-2">
                            <Label className="font-semibold">Upload GRN Documents</Label>
                             <div {...getGrnRootProps({className: 'p-4 border-2 border-dashed rounded-lg text-center cursor-pointer hover:border-primary'})}>
                                <input {...getGrnInputProps()} />
                                <div className="flex flex-col items-center gap-2 text-muted-foreground"><ImageUp className="h-8 w-8" /><p>Drop GRN/Invoice here</p></div>
                            </div>
                            {grnAttachments.length > 0 && renderFileList(grnAttachments, (index) => setGrnAttachments(prev => prev.filter((_, i) => i !== index)))}
                        </div>
                        <div className="space-y-2">
                           <Label className="font-semibold">Upload Storage Evidence</Label>
                           <div {...getEvidenceRootProps({className: 'p-4 border-2 border-dashed rounded-lg text-center cursor-pointer hover:border-primary'})}>
                                <input {...getEvidenceInputProps()} />
                                <div className="flex flex-col items-center gap-2 text-muted-foreground"><ImageUp className="h-8 w-8" /><p>Drop storage photos here</p></div>
                            </div>
                            {storageEvidence.length > 0 && renderFileList(storageEvidence, (index) => setStorageEvidence(prev => prev.filter((_, i) => i !== index)))}
                        </div>
                    </div>
                    
                    <div className="mt-6 flex justify-end">
                        <Button onClick={handleSubmitReceivedStock} disabled={isLoading || isSubmitting}>
                            {isSubmitting ? <Loader2 className="animate-spin mr-2"/> : <CheckSquare className="mr-2 h-4 w-4"/>}
                            Submit Received Stock
                        </Button>
                    </div>
                </CardContent>
             </Card>
           ) : (
            <Card>
                <CardContent className="p-4">
                    {filteredPOs.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <AlertCircle className="mx-auto h-10 w-10 mb-4" />
                            <p>No orders are currently in transit.</p>
                        </div>
                    ) : (
                    <Table>
                        <TableHeader><TableRow><TableHead>PO Number</TableHead><TableHead>Supplier</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
                        <TableBody>
                            {filteredPOs.map(po => (
                                <TableRow key={po.id}>
                                    <TableCell>{po.id}</TableCell>
                                    <TableCell>{suppliers.find(s => s.id === po.supplier_id)?.name || 'N/A'}</TableCell>
                                    <TableCell><Badge variant="default" className="bg-cyan-100 text-cyan-700">{po.status}</Badge></TableCell>
                                    <TableCell className="text-right"><Button variant="outline" size="sm" onClick={() => handleSelectPO(po)}>Receive Stock</Button></TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                    )}
                </CardContent>
           </Card>
           )}
        </TabsContent>
        <TabsContent value="history" className="mt-4">
           <Card>
              <CardHeader><CardTitle>Receiving History</CardTitle></CardHeader>
              <CardContent>
                 <Table>
                    <TableHeader><TableRow><TableHead>PO Number</TableHead><TableHead>Supplier</TableHead><TableHead>Received On</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                    <TableBody>
                        {filteredPOs.map(po => (
                             <TableRow key={po.id}>
                                <TableCell>{po.id}</TableCell>
                                <TableCell>{suppliers.find(s => s.id === po.supplier_id)?.name || 'N/A'}</TableCell>
                                <TableCell>{format(parseISO(po.updatedAt), 'PPP')}</TableCell>
                                <TableCell><Badge>Received</Badge></TableCell>
                            </TableRow>
                        ))}
                        {filteredPOs.length === 0 && (
                            <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">No receiving history yet.</TableCell></TableRow>
                        )}
                    </TableBody>
                 </Table>
              </CardContent>
           </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
