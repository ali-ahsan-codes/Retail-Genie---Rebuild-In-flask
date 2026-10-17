// src/components/admin/ProductForm.tsx
'use client';
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import * as z from "zod";
import type { Product, SupplierProduct, Supplier } from '@/types';
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { DialogFooter } from "@/components/ui/dialog";
import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import Image from "next/image";
import { UploadCloud, XCircle, AlertTriangle, Loader2, Package, Users, PlusCircle as PlusCircleIcon, Trash2 as Trash2Icon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { useRouter } from 'next/navigation';
import { addSupplierProduct as apiAddSupplierProduct, deleteSupplierProduct as apiDeleteSupplierProduct } from '@/lib/database';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useApp } from '@/context/AppContext';


const productFormSchema = z.object({
  name: z.string().min(2, { message: "Product name must be at least 2 characters." }),
  price: z.coerce.number().min(0, { message: "Price must be a positive number." }),
  quantityInStock: z.coerce.number().min(0, { message: "Quantity must be a positive number." }).int(),
  sku: z.string().min(1, { message: "Product Code is required." }),
  category: z.string().optional(),
  imageUrl: z.string().optional().or(z.literal('')), // DB path or "" or "PENDING_UPLOAD"
  expiryDate: z.string().optional(),
  lowStockThreshold: z.coerce.number().min(0).optional().nullable(),
  lowStockPrice: z.coerce.number().min(0).optional().nullable(),
}).refine(data => {
  if (data.lowStockThreshold && (data.lowStockPrice === null || data.lowStockPrice === undefined || data.lowStockPrice <= 0)) {
    return false;
  }
  if (data.lowStockPrice && data.lowStockPrice > 0 && (data.lowStockThreshold === null || data.lowStockThreshold === undefined || data.lowStockThreshold < 0)) {
    return false;
  }
  return true;
}, {
  message: "If setting a low stock threshold, a positive low stock price is required. If setting low stock price, threshold is required.",
  path: ["lowStockThreshold"],
});


type ProductFormValues = z.infer<typeof productFormSchema>;

interface ProductFormProps {
  product?: Product | null;
  onSubmit: (data: ProductFormValues) => Promise<{ success: boolean; product?: Product | null; error?: string }>;
  onCancel?: () => void;
  isLoading?: boolean;
  onUploadComplete?: () => void;
}

function AddSupplierLinkSection({
  productId,
  linkedSupplierIds,
  onSupplierLinked
}: {
  productId: string;
  linkedSupplierIds: string[];
  onSupplierLinked: () => void;
}) {
  const { suppliers } = useApp();
  const { toast } = useToast();
  const [selectedSupplierId, setSelectedSupplierId] = useState('');
  const [unitPrice, setUnitPrice] = useState('');
  const [isLinking, setIsLinking] = useState(false);

  const availableSuppliers = useMemo(() => {
    return suppliers.filter(s => !linkedSupplierIds.includes(s.id));
  }, [suppliers, linkedSupplierIds]);

  const handleLinkSupplier = async () => {
    if (!selectedSupplierId || !unitPrice) {
      toast({ title: "Error", description: "Please select a supplier and set a unit price.", variant: "destructive" });
      return;
    }
    setIsLinking(true);
    try {
      await apiAddSupplierProduct({
        supplier_id: selectedSupplierId,
        product_id: productId,
        unit_price: parseFloat(unitPrice),
      });
      toast({ title: "Success", description: "Supplier linked to product." });
      setSelectedSupplierId('');
      setUnitPrice('');
      onSupplierLinked();
    } catch (error) {
      toast({ title: "Error Linking Supplier", description: (error as Error).message, variant: "destructive" });
    } finally {
      setIsLinking(false);
    }
  };

  return (
    <div className="mt-6 p-4 border rounded-md bg-muted/30">
      <h4 className="font-semibold mb-3">Link New Supplier</h4>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        <Select value={selectedSupplierId} onValueChange={setSelectedSupplierId}>
          <SelectTrigger><SelectValue placeholder="Select a supplier..." /></SelectTrigger>
          <SelectContent>
            {availableSuppliers.length === 0 ? (
                <div className="p-2 text-xs text-muted-foreground">No unlinked suppliers</div>
            ): (
              availableSuppliers.map(s => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)
            )}
          </SelectContent>
        </Select>
        <Input
          type="number"
          placeholder="Unit Price (OMR)"
          value={unitPrice}
          onChange={(e) => setUnitPrice(e.target.value)}
          min="0"
          step="0.01"
        />
        <Button onClick={handleLinkSupplier} disabled={isLinking}>
          {isLinking ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlusCircleIcon className="mr-2 h-4 w-4" />}
          Link Supplier
        </Button>
      </div>
    </div>
  );
}


export default function ProductForm({ product, onSubmit, onCancel, isLoading = false, onUploadComplete }: ProductFormProps) {
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const { toast } = useToast();
  const { suppliers } = useApp();
  const router = useRouter();

  const [linkedSupplierProducts, setLinkedSupplierProducts] = useState<SupplierProduct[]>([]);
  const [isLoadingLinks, setIsLoadingLinks] = useState(false);


  const fetchLinkedProducts = useCallback(async () => {
    if (!product?.id) {
        setLinkedSupplierProducts([]);
        return;
    };
    setIsLoadingLinks(true);
    try {
        const response = await fetch('/api/scm/supplier-products');
        if (!response.ok) throw new Error('Failed to fetch supplier links');
        const allLinks: SupplierProduct[] = await response.json();
        setLinkedSupplierProducts(allLinks.filter(link => link.product_id === product.id));
    } catch (error) {
        toast({ title: "Error", description: "Could not load supplier links.", variant: "destructive" });
    } finally {
        setIsLoadingLinks(false);
    }
  }, [product?.id, toast]);

  useEffect(() => {
    fetchLinkedProducts();
  }, [fetchLinkedProducts]);


  const defaultValues = useMemo(() => {
    const initialImageUrl = product?.imageUrl || '';
    return product
    ? {
        name: product.name,
        price: product.price,
        quantityInStock: product.quantityInStock,
        sku: product.sku,
        category: product.category || '',
        imageUrl: initialImageUrl,
        expiryDate: product.expiryDate || '',
        lowStockThreshold: product.lowStockThreshold ?? null,
        lowStockPrice: product.lowStockPrice ?? null,
      }
    : {
        name: "",
        price: 0,
        quantityInStock: 0,
        sku: "",
        category: "",
        imageUrl: "",
        expiryDate: "",
        lowStockThreshold: null,
        lowStockPrice: null,
      }
  }, [product]);

  const form = useForm<ProductFormValues>({
    resolver: zodResolver(productFormSchema),
    defaultValues,
  });

  useEffect(() => {
    form.reset(defaultValues);
    setImagePreview(defaultValues.imageUrl ? `/api/uploads/${defaultValues.imageUrl}` : null);
    setSelectedFile(null);
  }, [defaultValues, form]);


  const handleImageChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        const dataUri = reader.result as string;
        setImagePreview(dataUri);
        form.setValue("imageUrl", "PENDING_UPLOAD");
      };
      reader.readAsDataURL(file);
    } else {
      const originalApiImageUrl = product?.imageUrl ? `/api/uploads/${product.imageUrl}` : null;
      setImagePreview(originalApiImageUrl);
      setSelectedFile(null);
      form.setValue("imageUrl", product?.imageUrl || "");
    }
  };

  const removeImage = () => {
    setImagePreview(null);
    setSelectedFile(null);
    form.setValue("imageUrl", "");
    const fileInput = document.getElementById('imageUpload') as HTMLInputElement;
    if (fileInput) {
        fileInput.value = "";
    }
  };


  const handleSubmitForm = async (data: ProductFormValues) => {
    if (isLoading || isUploadingImage) return;

    let submissionData = { ...data };
    
    if (data.imageUrl === "PENDING_UPLOAD") {
      submissionData.imageUrl = product?.imageUrl || "";
    } else {
      submissionData.imageUrl = data.imageUrl;
    }
    
    submissionData.lowStockThreshold = data.lowStockThreshold === null ? undefined : data.lowStockThreshold;
    submissionData.lowStockPrice = data.lowStockPrice === null ? undefined : data.lowStockPrice;

    const productSaveResult = await onSubmit(submissionData as any); 

    if (productSaveResult.success && productSaveResult.product) {
      if (selectedFile) {
        setIsUploadingImage(true);
        const imageFormData = new FormData();
        imageFormData.append('image', selectedFile);
        imageFormData.append('product_id', productSaveResult.product.id);
        imageFormData.append('sku', productSaveResult.product.sku);

        try {
          const imageResponse = await fetch('/api/products/image', {
            method: 'POST',
            body: imageFormData,
          });

          if (!imageResponse.ok) {
            let errorMsg = `Image upload failed with status: ${imageResponse.status}`;
            try {
              const errorData = await imageResponse.json();
              errorMsg = errorData.message || errorData.error || errorMsg;
            } catch (jsonError) {
              const textError = await imageResponse.text().catch(() => "");
              errorMsg = textError ? `Image upload failed: ${textError.substring(0,100)}` : errorMsg;
            }
            throw new Error(errorMsg);
          }

          const imageApiResult = await imageResponse.json();
          toast({ title: 'Image Uploaded', description: `Image for ${productSaveResult.product.name} saved.` });
          
          if (onUploadComplete) onUploadComplete();
          
          setImagePreview(imageApiResult.public_url);
          form.setValue("imageUrl", imageApiResult.db_path);

        } catch (imgError: any) {
          console.error("Error uploading image in ProductForm:", imgError);
          toast({ title: 'Image Upload Failed', description: imgError.message || 'Could not upload image.', variant: 'destructive' });
        } finally {
          setIsUploadingImage(false);
          setSelectedFile(null);
        }
      } else {
        if (onUploadComplete) onUploadComplete();
      }
    } else if (productSaveResult.error) {
      // Error saving product details (already toasted by parent onSubmit)
    }
  };

  const isReturnedDNItem = product?.category?.includes('Return DN');
  const currentSubmitDisabled = isLoading || isUploadingImage;

  const handleDeleteLink = async (linkId: string) => {
    try {
        await apiDeleteSupplierProduct(linkId);
        toast({title: "Success", description: "Supplier link removed."});
        fetchLinkedProducts();
    } catch(error) {
        toast({ title: "Error", description: (error as Error).message, variant: "destructive"});
    }
  }

  return (
    <Tabs defaultValue="details">
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="details">
          <Package className="mr-2 h-4 w-4" /> Details
        </TabsTrigger>
        <TabsTrigger value="suppliers" disabled={!product}>
          <Users className="mr-2 h-4 w-4" /> Suppliers
        </TabsTrigger>
      </TabsList>
      <TabsContent value="details">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmitForm)} className="space-y-6 pt-4">
            {isReturnedDNItem && (
              <Badge variant="destructive" className="mb-4 text-sm p-2">
                <AlertTriangle className="h-4 w-4 mr-2" /> This item was returned via a Demand Notice. Please review.
              </Badge>
            )}
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Product Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Enter product name" {...field} disabled={currentSubmitDisabled} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="price"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Standard Price (OMR)</FormLabel>
                    <FormControl>
                      <Input type="number" placeholder="0.00" {...field} step="0.01" disabled={currentSubmitDisabled} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="quantityInStock"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Quantity in Stock</FormLabel>
                    <FormControl>
                      <Input type="number" placeholder="0" {...field} disabled={currentSubmitDisabled} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <FormField
                control={form.control}
                name="sku"
                render={({ field }) => (
                    <FormItem>
                    <FormLabel>Product Code</FormLabel>
                    <FormControl>
                        <Input placeholder="Enter Product Code" {...field} disabled={currentSubmitDisabled} />
                    </FormControl>
                    <FormMessage />
                    </FormItem>
                )}
            />
            <FormField
                control={form.control}
                name="category"
                render={({ field }) => (
                    <FormItem>
                    <FormLabel>Category (Optional)</FormLabel>
                    <FormControl>
                        <Input placeholder="Enter category" {...field} value={field.value ?? ''} disabled={currentSubmitDisabled} />
                    </FormControl>
                    <FormDescription>
                        Example: Electronics, Groceries. Use commas to separate multiple categories.
                        {isReturnedDNItem && " (Includes 'Return DN')"}
                    </FormDescription>
                    <FormMessage />
                    </FormItem>
                )}
            />

            <FormItem>
              <FormLabel>Product Image</FormLabel>
              <FormControl>
                <Input
                    id="imageUpload"
                    type="file"
                    accept="image/png, image/jpeg, image/webp"
                    onChange={handleImageChange}
                    className="block w-full text-sm text-slate-500
                               file:mr-4 file:py-2 file:px-4
                               file:rounded-full file:border-0
                               file:text-sm file:font-semibold
                               file:bg-primary/10 file:text-primary
                               hover:file:bg-primary/20"
                    disabled={currentSubmitDisabled}
                />
              </FormControl>
              {imagePreview && (
                <div className="mt-4 relative w-32 h-32 border rounded-md overflow-hidden shadow-sm">
                  <Image
                    src={imagePreview}
                    alt="Product Preview"
                    layout="fill"
                    objectFit="cover"
                    data-ai-hint="product preview"
                    unoptimized={true}
                    onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/128x128.png'; (e.target as HTMLImageElement).srcset = ''; }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute top-1 right-1 h-6 w-6 bg-destructive/70 hover:bg-destructive text-destructive-foreground rounded-full p-1"
                    onClick={removeImage}
                    aria-label="Remove image"
                    disabled={currentSubmitDisabled}
                   >
                    <XCircle className="h-4 w-4"/>
                  </Button>
                </div>
              )}
              {!imagePreview && (
                <div className="mt-4 flex items-center justify-center w-32 h-32 border-2 border-dashed border-muted-foreground/30 rounded-md bg-muted/50">
                    <UploadCloud className="h-8 w-8 text-muted-foreground/50"/>
                </div>
              )}
              <FormDescription>Upload an image for the product (PNG, JPG, WEBP). Image will be uploaded after product details are saved/updated. If you remove an image and save, the image association will be cleared.</FormDescription>
               <FormField
                control={form.control}
                name="imageUrl"
                render={({ field }) => <Input type="hidden" {...field} value={field.value ?? ''} />}
               />
              <FormMessage />
            </FormItem>

            <FormField
                control={form.control}
                name="expiryDate"
                render={({ field }) => (
                    <FormItem>
                    <FormLabel>Expiry Date (Optional)</FormLabel>
                    <FormControl>
                        <Input type="date" {...field} value={field.value ?? ''} disabled={currentSubmitDisabled} />
                    </FormControl>
                    <FormDescription>Leave blank if not applicable.</FormDescription>
                    <FormMessage />
                    </FormItem>
                )}
            />

            <div className="space-y-2 p-4 border rounded-md bg-muted/30">
              <h4 className="text-md font-semibold text-primary flex items-center">
                <AlertTriangle className="h-5 w-5 mr-2 text-orange-500" /> Low Stock Pricing (Optional)
              </h4>
              <p className="text-xs text-muted-foreground">
                Set a special price that applies when stock quantity reaches or falls below the threshold.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
                <FormField
                  control={form.control}
                  name="lowStockThreshold"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Low Stock Threshold</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder="e.g., 5"
                          {...field}
                          value={field.value ?? ''}
                          onChange={e => field.onChange(e.target.value === '' ? null : Number(e.target.value))}
                          disabled={currentSubmitDisabled}
                        />
                      </FormControl>
                      <FormDescription>At what stock level this price applies.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="lowStockPrice"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Low Stock Price (OMR)</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          placeholder="0.00"
                          step="0.01"
                          {...field}
                          value={field.value ?? ''}
                          onChange={e => field.onChange(e.target.value === '' ? null : Number(e.target.value))}
                          disabled={currentSubmitDisabled}
                        />
                      </FormControl>
                       <FormDescription>Special price when stock is low.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            <DialogFooter className="pt-4">
                {onCancel && <Button type="button" variant="outline" onClick={onCancel} disabled={currentSubmitDisabled}>Cancel</Button>}
                <Button type="submit" disabled={currentSubmitDisabled}>
                    {isLoading ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving Details...</> :
                     isUploadingImage ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Uploading Image...</> :
                     (product ? "Save Changes" : "Add Product")}
                </Button>
            </DialogFooter>
          </form>
        </Form>
      </TabsContent>
      <TabsContent value="suppliers">
        <div className="p-4">
          <CardHeader className="p-0 mb-4">
            <CardTitle>Product Suppliers</CardTitle>
            <CardDescription>Manage suppliers for this product.</CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {isLoadingLinks ? <p>Loading supplier links...</p> : (
            <>
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead>Supplier</TableHead>
                            <TableHead>Unit Price (OMR)</TableHead>
                            <TableHead>Lead Time</TableHead>
                            <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {linkedSupplierProducts.length > 0 ? (
                          linkedSupplierProducts.map(link => {
                            const supplierInfo = suppliers.find(s => s.id === link.supplier_id);
                            return (
                                <TableRow key={link.id}>
                                    <TableCell>{supplierInfo?.name || 'Unknown Supplier'}</TableCell>
                                    <TableCell>{link.unit_price.toFixed(2)}</TableCell>
                                    <TableCell>{supplierInfo?.lead_time ?? 'N/A'} days</TableCell>
                                    <TableCell className="text-right">
                                        <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => handleDeleteLink(link.id)}>
                                            <Trash2Icon className="h-4 w-4" />
                                        </Button>
                                    </TableCell>
                                </TableRow>
                            )
                          })
                        ) : (
                          <TableRow>
                              <TableCell colSpan={4} className="text-center text-muted-foreground">
                                  No suppliers are linked to this product yet.
                              </TableCell>
                          </TableRow>
                        )}
                    </TableBody>
                </Table>
                {product && (
                  <AddSupplierLinkSection
                    productId={product.id}
                    linkedSupplierIds={linkedSupplierProducts.map(l => l.supplier_id)}
                    onSupplierLinked={fetchLinkedProducts}
                  />
                )}
            </>
            )}
          </CardContent>
        </div>
      </TabsContent>
    </Tabs>
  );
}
