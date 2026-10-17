// src/components/admin/AuditLauncher.tsx
'use client';
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useForm, useFieldArray, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { useApp } from '@/context/AppContext';
import type { Product, User, Audit } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
// FormLabel is imported from Form component context now
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Trash2, PlusCircle, Search, Package, ClipboardList, Store, UserCheck, Building, FileText, Loader2, Edit3 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Badge } from '@/components/ui/badge';
import { useRouter } from 'next/navigation';

const auditItemSchema = z.object({
  productId: z.string().optional(),
  productName: z.string().min(2, "Item name must be at least 2 characters."),
  productSku: z.string().optional(),
  isManual: z.boolean().default(false),
});

const launchAuditFormSchema = z.object({
  title: z.string().min(3, "Audit title must be at least 3 characters."),
  auditorId: z.string().min(1, "Auditor must be selected."),
  storeLocation: z.string().min(3, "Store location must be at least 3 characters."),
  items: z.array(auditItemSchema).min(1, "At least one item must be added to the audit."),
});

type LaunchAuditFormValues = z.infer<typeof launchAuditFormSchema>;
export type AuditItemFormData = z.infer<typeof auditItemSchema>;

interface AuditLauncherProps {
  initialDataForRelaunch?: Audit | null;
}

export default function AuditLauncher({ initialDataForRelaunch }: AuditLauncherProps) {
  const { users, products: availableProducts, getProductById, createAudit, currentUser } = useApp();
  const { toast } = useToast();
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);

  const [productSearchTerm, setProductSearchTerm] = useState('');
  const [productSearchResults, setProductSearchResults] = useState<Product[]>([]);
  const [isProductSearchOpen, setIsProductSearchOpen] = useState(false);
  const searchResultsRef = useRef<HTMLDivElement>(null);

  const [manualItemName, setManualItemName] = useState('');
  const [manualItemSku, setManualItemSku] = useState('');

  const auditors = useMemo(() => users.filter(u => u.role === 'auditor'), [users]);

  const formDefaultValues = useMemo(() => {
    if (initialDataForRelaunch) {
      return {
        title: `${initialDataForRelaunch.title} (Relaunch)`,
        auditorId: '', // Force re-selection of auditor
        storeLocation: initialDataForRelaunch.storeLocation,
        items: (initialDataForRelaunch.items || []).map(item => ({
          productId: item.productId || undefined,
          productName: item.productName,
          productSku: item.productSku || undefined,
          isManual: !item.productId,
        })),
      };
    }
    return {
      title: '',
      auditorId: '',
      storeLocation: '',
      items: [],
    };
  }, [initialDataForRelaunch]);

  const form = useForm<LaunchAuditFormValues>({
    resolver: zodResolver(launchAuditFormSchema),
    defaultValues: formDefaultValues,
  });
  
  useEffect(() => {
    // Reset form if initialDataForRelaunch changes (e.g., navigating from one relaunch to another or to new)
    form.reset(formDefaultValues);
  }, [formDefaultValues, form]);


  const { fields, append, remove, replace } = useFieldArray({
    control: form.control,
    name: "items",
  });

  useEffect(() => {
    if (productSearchTerm.trim() === "") {
      setProductSearchResults([]);
      setIsProductSearchOpen(false);
      return;
    }
    const filtered = availableProducts.filter(
      p => p.name.toLowerCase().includes(productSearchTerm.toLowerCase()) ||
           p.sku.toLowerCase().includes(productSearchTerm.toLowerCase())
    ).slice(0, 10); 
    setProductSearchResults(filtered);
  }, [productSearchTerm, availableProducts]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchResultsRef.current && !searchResultsRef.current.contains(event.target as Node)) {
        const inputElement = document.getElementById('audit-product-search-input');
        if (inputElement && !inputElement.contains(event.target as Node)) {
          setIsProductSearchOpen(false);
        }
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [searchResultsRef]);

  const handleAddProductItem = (product: Product) => {
    const existingItem = fields.find(item => item.productId === product.id && !item.isManual);
    if (existingItem) {
      toast({ title: "Item Exists", description: `${product.name} is already in the audit list.`, variant: "default" });
      return;
    }
    append({
      productId: product.id,
      productName: product.name,
      productSku: product.sku,
      isManual: false,
    });
    setProductSearchTerm('');
    setProductSearchResults([]);
    setIsProductSearchOpen(false);
  };

  const handleAddManualItem = () => {
    if (!manualItemName.trim()) {
      toast({ title: "Item Name Required", description: "Please enter a name for the manual item.", variant: "destructive" });
      return;
    }
    const existingItem = fields.find(item => item.productName.toLowerCase() === manualItemName.trim().toLowerCase() && item.productSku?.toLowerCase() === manualItemSku.trim().toLowerCase() && item.isManual);
    if (existingItem) {
      toast({ title: "Manual Item Exists", description: `${manualItemName} (SKU: ${manualItemSku || 'N/A'}) is already in the audit list.`, variant: "default" });
      return;
    }
    append({
      productName: manualItemName.trim(),
      productSku: manualItemSku.trim() || undefined,
      isManual: true,
    });
    setManualItemName('');
    setManualItemSku('');
  };

  const handleFormSubmit = async (data: LaunchAuditFormValues) => {
    if (!currentUser) {
      toast({ title: "Error", description: "Admin user not identified.", variant: "destructive" });
      return;
    }
    setIsLoading(true);
    try {
      const createdAudit = await createAudit(data); 
      if (createdAudit) {
        toast({ title: "Audit Launched Successfully!", description: `Audit ID: ${createdAudit.id} for ${data.storeLocation} has been created and assigned.`, duration: 5000 });
        form.reset({ title: '', auditorId: '', storeLocation: '', items: [] }); // Reset to truly empty form
        router.push('/admin/audits'); 
      } else {
        // Error toast is handled by createAudit in AppContext
      }
    } catch (error: any) {
      toast({ title: "Audit Launch Failed", description: error.message || "An unexpected error occurred.", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleFormSubmit)} className="space-y-8">
        <Card>
          <CardHeader><CardTitle className="flex items-center"><FileText className="mr-2 h-5 w-5 text-primary"/>Audit Details</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Audit Title</FormLabel>
                  <FormControl><Input placeholder="e.g., End of Month Stock Check - Main Branch" {...field} /></FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="auditorId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center"><UserCheck className="mr-2 h-4 w-4 text-muted-foreground"/>Assign Auditor</FormLabel>
                    <Select onValueChange={field.onChange} defaultValue={field.value} value={field.value || ''}>
                      <FormControl><SelectTrigger><SelectValue placeholder="Select an auditor" /></SelectTrigger></FormControl>
                      <SelectContent>
                        {auditors.length === 0 && <SelectItem value="" disabled>No auditors available</SelectItem>}
                        {auditors.map(auditor => (
                          <SelectItem key={auditor.id} value={auditor.id}>{auditor.username}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="storeLocation"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="flex items-center"><Store className="mr-2 h-4 w-4 text-muted-foreground"/>Store Location</FormLabel>
                    <FormControl><Input placeholder="e.g., Main Branch, Warehouse A" {...field} /></FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="flex items-center"><ClipboardList className="mr-2 h-5 w-5 text-primary"/>Items to Audit</CardTitle></CardHeader>
          <CardContent className="space-y-6">
            
            <div className="p-4 border rounded-md bg-muted/30 space-y-3">
              <h4 className="text-md font-semibold flex items-center"><Package className="mr-2 h-4 w-4 text-muted-foreground"/>Add Existing Product</h4>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="audit-product-search-input"
                  placeholder="Search by product name or SKU..."
                  value={productSearchTerm}
                  onChange={(e) => { setProductSearchTerm(e.target.value); setIsProductSearchOpen(true); }}
                  onFocus={() => { if (productSearchTerm) setIsProductSearchOpen(true); }}
                  className="pl-10"
                  autoComplete="off"
                />
                {isProductSearchOpen && productSearchResults.length > 0 && (
                  <div ref={searchResultsRef} className="absolute z-10 w-full bg-card border mt-1 rounded-md shadow-lg max-h-48 overflow-y-auto">
                    {productSearchResults.map(p => (
                      <div key={p.id} className="p-3 hover:bg-accent cursor-pointer text-sm" onClick={() => handleAddProductItem(p)}>
                        <p className="font-medium">{p.name} <Badge variant="outline" className="ml-1 text-xs">SKU: {p.sku}</Badge></p>
                        <p className="text-xs text-muted-foreground">Current Stock: {p.quantityInStock}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            
            <div className="p-4 border rounded-md bg-muted/30 space-y-3">
              <h4 className="text-md font-semibold flex items-center"><Edit3 className="mr-2 h-4 w-4 text-muted-foreground"/>Add Manual/Non-System Item</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input placeholder="Item Name (Required)" value={manualItemName} onChange={e => setManualItemName(e.target.value)} />
                <Input placeholder="Item SKU/Identifier (Optional)" value={manualItemSku} onChange={e => setManualItemSku(e.target.value)} />
              </div>
              <Button type="button" variant="outline" onClick={handleAddManualItem} className="w-full md:w-auto">
                <PlusCircle className="mr-2 h-4 w-4" /> Add Manual Item
              </Button>
            </div>

            <Separator />

            
            <h4 className="text-md font-semibold">Selected Audit Items ({fields.length})</h4>
            {fields.length === 0 ? (
              <p className="text-muted-foreground text-center py-4">No items added to the audit yet.</p>
            ) : (
              <ScrollArea className="h-64 border rounded-md">
                <div className="space-y-2 p-3">
                  {fields.map((field, index) => (
                    <Card key={field.id} className="p-3 flex justify-between items-center shadow-sm">
                      <div>
                        <p className="font-medium text-sm">{field.productName}
                          {field.isManual && <Badge variant="secondary" className="ml-2 text-xs">Manual</Badge>}
                        </p>
                        <p className="text-xs text-muted-foreground">SKU: {field.productSku || 'N/A'}</p>
                      </div>
                      <Button type="button" variant="ghost" size="icon" onClick={() => remove(index)} className="text-destructive hover:text-destructive">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </Card>
                  ))}
                </div>
              </ScrollArea>
            )}
            <FormField name="items" render={() => <FormMessage />} />
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3 pt-4">
          <Button type="button" variant="outline" onClick={() => router.back()} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : <PlusCircle className="mr-2 h-4 w-4"/>}
            Launch Audit
          </Button>
        </div>
      </form>
    </Form>
  );
}

