// src/app/(main)/admin/products/page.tsx
'use client';
import React, { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import type { Product } from '@/types';
import { useApp } from '@/context/AppContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PlusCircle, Edit, Trash2, MoreHorizontal, Search, PackageOpen, Upload, ShieldAlert, FileDown, Package, Store as StoreIcon, Boxes, Loader2, Filter } from 'lucide-react';
import ProductForm from '@/components/admin/ProductForm';
import { useToast } from '@/hooks/use-toast';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import Image from 'next/image';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { getProductsFromDb } from '@/lib/database';
import { format, parseISO, isValid } from 'date-fns';
import { csvToArray, arrayToCsv, parseCsvValue } from '@/lib/csvUtils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ExternalStoresManager from "@/components/admin/ExternalStoresManager";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';

interface MemoizedProductAdminRowProps {
  product: Product;
  onEdit: (product: Product) => void;
  onDelete: (productId: string) => void;
  isSubmitting: boolean;
  canManageProducts: boolean;
}

const MemoizedProductAdminRow = React.memo(function MemoizedProductAdminRow({ product, onEdit, onDelete, isSubmitting, canManageProducts }: MemoizedProductAdminRowProps) {
  const imageSrc = product.imageUrl;
  return (
    <TableRow className={product.isDemandNoticeProduct ? "bg-blue-50 hover:bg-blue-100" : ""}>
      <TableCell className="w-[64px] h-[64px]">
        {imageSrc ? (
          <Image
            src={imageSrc.startsWith('http') ? imageSrc : `/api/uploads/${imageSrc}`}
            alt={product.name}
            width={48}
            height={48}
            className="rounded object-cover aspect-square"
            data-ai-hint="product item"
            unoptimized={true}
            onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/48x48.png'; (e.target as HTMLImageElement).srcset = ''; }}
          />
        ) : (
          <div className="w-12 h-12 flex items-center justify-center bg-muted rounded">
            <Package className="w-6 h-6 text-muted-foreground" />
          </div>
        )}
      </TableCell>
      <TableCell className="font-medium">{product.name} {product.isDemandNoticeProduct && <span className="text-xs text-blue-600">(DN Item)</span>}</TableCell>
      <TableCell>{product.sku}</TableCell>
      <TableCell className="text-right">OMR {product.price.toFixed(2)}</TableCell>
      <TableCell className="text-center">{product.quantityInStock}</TableCell>
      <TableCell>{product.category || 'N/A'}</TableCell>
      <TableCell>
        {product.expiryDate && isValid(parseISO(product.expiryDate))
          ? format(parseISO(product.expiryDate), 'dd/MM/yyyy')
          : (product.expiryDate && product.expiryDate.trim() !== '' && product.expiryDate !== 'N/A' ? product.expiryDate : 'N/A')}
      </TableCell>
      <TableCell>
        {canManageProducts && (
          <AlertDialog>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="h-8 w-8 p-0" disabled={isSubmitting}>
                  <span className="sr-only">Open menu</span>
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onEdit(product)} disabled={isSubmitting}>
                  <Edit className="mr-2 h-4 w-4" /> Edit
                </DropdownMenuItem>
                <AlertDialogTrigger asChild>
                  <DropdownMenuItem className="text-destructive focus:text-destructive focus:bg-destructive/10" disabled={isSubmitting}>
                    <Trash2 className="mr-2 h-4 w-4" /> Delete
                  </DropdownMenuItem>
                </AlertDialogTrigger>
              </DropdownMenuContent>
            </DropdownMenu>
            <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This action cannot be undone. This will permanently delete the product "{product.name}".
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel disabled={isSubmitting}>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={() => onDelete(product.id)} className="bg-destructive hover:bg-destructive/90" disabled={isSubmitting}>
                    {isSubmitting ? "Deleting..." : "Delete"}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
        )}
      </TableCell>
    </TableRow>
  );
});
MemoizedProductAdminRow.displayName = 'MemoizedProductAdminRow';

export default function AdminProductsPage() {
  const {
    products: contextProducts,
    loadDataFromDb,
    hasPermission,
    currentUser,
    updateProduct: contextUpdateProduct,
    addProduct: contextAddProduct,
    deleteProduct: contextDeleteProduct,
  } = useApp();
  const { toast } = useToast();
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [localProducts, setLocalProducts] = useState<Product[]>([]);
  
  const [quantityFilterType, setQuantityFilterType] = useState<'all' | 'lessThan' | 'greaterThan' | 'equals'>('all');
  const [quantityFilterValue, setQuantityFilterValue] = useState('');

  useEffect(() => {
    setLocalProducts(contextProducts);
  }, [contextProducts]);

  const canManageProducts = hasPermission('manage_products');

  const handleAddProduct = useCallback(() => {
    if (!canManageProducts) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to add products.', variant: 'destructive' });
      return;
    }
    setEditingProduct(null);
    setIsFormOpen(true);
  }, [canManageProducts, toast]);

  const handleEditProduct = useCallback((product: Product) => {
     if (!canManageProducts) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to edit products.', variant: 'destructive' });
      return;
    }
    setEditingProduct(product);
    setIsFormOpen(true);
  }, [canManageProducts, toast]);

  const handleDeleteProduct = useCallback(async (productId: string) => {
    if (!canManageProducts) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to delete products.', variant: 'destructive' });
      return;
    }
    setIsSubmitting(true);
    const result = await contextDeleteProduct(productId);
    if (result.success) {
      toast({ title: 'Product Deleted', description: 'The product has been removed.', variant: 'destructive' });
    } else {
      toast({ title: 'Delete Failed', description: result.error || 'Could not delete product.', variant: 'destructive' });
    }
    setIsSubmitting(false);
  }, [canManageProducts, toast, contextDeleteProduct]);


  const handleSubmitFormInPage = useCallback(async (data: Omit<Product, 'id'> & { id?: string }): Promise<{ success: boolean; product?: Product | null; error?: string }> => {
    if (!canManageProducts) {
      const errorMsg = "You do not have permission to save products.";
      toast({ title: 'Permission Denied', description: errorMsg, variant: 'destructive' });
      return { success: false, error: errorMsg };
    }
    setIsSubmitting(true);
    let result: { success: boolean; product?: Product | null; error?: string };
    try {
      const expiryDateToSave = data.expiryDate?.trim() === '' || data.expiryDate === 'N/A' ? undefined : data.expiryDate;

      if (editingProduct) {
        const updatedProductData: Product = {
          ...editingProduct,
          ...data,
          id: editingProduct.id,
          expiryDate: expiryDateToSave,
          imageUrl: data.imageUrl || editingProduct.imageUrl || undefined,
          isDemandNoticeProduct: editingProduct.isDemandNoticeProduct || false,
        };
        result = await contextUpdateProduct(updatedProductData);
        if (result.success) {
          toast({ title: 'Product Updated', description: `${data.name} details saved.` });
        } else {
          toast({ title: 'Update Failed', description: result.error || 'Could not update product details.', variant: 'destructive' });
        }
      } else {
        const newProductData: Omit<Product, 'id'> = {
          ...data,
          expiryDate: expiryDateToSave,
          imageUrl: data.imageUrl || undefined,
          isDemandNoticeProduct: false,
        };
        result = await contextAddProduct(newProductData);
        if (result.success && result.product) {
          toast({ title: 'Product Added', description: `${result.product.name} details saved.` });
        } else {
          toast({ title: 'Add Failed', description: result.error || 'Could not add product details.', variant: 'destructive' });
        }
      }
      return result;
    } catch (error) {
      const errorMessage = (error as Error).message;
      toast({ title: 'Form Submission Error', description: `An unexpected error occurred: ${errorMessage}`, variant: 'destructive' });
      return { success: false, error: errorMessage };
    } finally {
      setIsSubmitting(false);
      if (!data.imageUrl && result!.success) {
          await loadDataFromDb(true);
      }
      if (result!.success) {
        const fileInput = document.getElementById('imageUpload') as HTMLInputElement | null;
        const fileSelected = fileInput && fileInput.files && fileInput.files.length > 0;

        if (!fileSelected) {
            setIsFormOpen(false);
            setEditingProduct(null);
        }
      }
    }
  }, [canManageProducts, toast, editingProduct, contextUpdateProduct, contextAddProduct, loadDataFromDb]);

  const handleImageUploadComplete = async () => {
    await loadDataFromDb(true);
    setIsFormOpen(false);
    setEditingProduct(null);
  };


  const filteredProducts = useMemo(() => {
    const filterValueNum = parseInt(quantityFilterValue, 10);
    const hasQuantityFilter = quantityFilterType !== 'all' && !isNaN(filterValueNum);
    
    return localProducts.filter(product => {
      const textMatch = searchTerm === '' ||
        product.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        product.sku.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (product.category && product.category.toLowerCase().includes(searchTerm.toLowerCase()));

      let quantityMatch = true;
      if(hasQuantityFilter) {
          switch(quantityFilterType) {
              case 'lessThan':
                  quantityMatch = product.quantityInStock < filterValueNum;
                  break;
              case 'greaterThan':
                  quantityMatch = product.quantityInStock > filterValueNum;
                  break;
              case 'equals':
                  quantityMatch = product.quantityInStock === filterValueNum;
                  break;
          }
      }

      return textMatch && quantityMatch;
    }).sort((a,b) => a.name.localeCompare(b.name));
  }, [localProducts, searchTerm, quantityFilterType, quantityFilterValue]);

  const handleImportClick = useCallback(() => {
    if (!canManageProducts) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to import products.', variant: 'destructive' });
      return;
    }
    fileInputRef.current?.click();
  }, [canManageProducts, toast]);

  const handleFileImport = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!canManageProducts) {
      toast({ title: 'Permission Denied', description: 'You do not have permission to import products.', variant: 'destructive' });
      return;
    }
    const file = event.target.files?.[0];
    if (!file) return;
    setIsSubmitting(true);

    const reader = new FileReader();
    reader.onload = async (e) => {
      const text = e.target?.result as string;
      if (!text) {
        toast({ title: 'Import Failed', description: 'Could not read file content.', variant: 'destructive' });
        setIsSubmitting(false);
        return;
      }
      try {
        const parsedData = csvToArray(text);
        if (!parsedData || parsedData.length === 0) {
            toast({ title: 'Import Failed', description: 'CSV file is empty or could not be parsed correctly.', variant: 'destructive' });
            setIsSubmitting(false);
            return;
        }
        const headerSynonyms: Record<keyof Product | 'productCode', string[]> = {
          'id': ['id'], 'sku': ['sku', 'product code', 'item code', 'productcode'], 'name': ['name', 'product name', 'title', 'item name'],
          'price': ['price', 'unit price', 'cost'], 'quantityInStock': ['quantityinstock', 'quantity in stock', 'stock', 'qty', 'quantity', 'available quantity'],
          'category': ['category', 'product category', 'type'], 'imageUrl': ['imageurl', 'image url', 'image', 'picture'], 'expiryDate': ['expirydate', 'expiry date', 'expiration date', 'exp date', 'use by'],
          'isDemandNoticeProduct': ['isdemandnoticeproduct', 'is demand item', 'dn product'], 'lowStockThreshold': ['lowstockthreshold', 'low stock threshold', 'min stock', 'threshold'], 'lowStockPrice': ['lowstockprice', 'low stock price', 'special price'],
          'productCode': ['product code', 'sku'],
        };
        let importedCount = 0;
        let updatedCount = 0;
        const currentProductsFromDb = await getProductsFromDb();

        for (const row of parsedData) {
          const productDataFromCsv: Partial<Product> = {};
          let rowSku: string | undefined = undefined;

          for (const canonicalKey in headerSynonyms) {
            const synonyms = headerSynonyms[canonicalKey as keyof typeof headerSynonyms];
            for (const synonym of synonyms) {
              const csvHeaderKey = Object.keys(row).find(key => key.toLowerCase() === synonym.toLowerCase());
              if (csvHeaderKey && row[csvHeaderKey] !== undefined && row[csvHeaderKey] !== null) {
                productDataFromCsv[canonicalKey as keyof Product] = parseCsvValue(row[csvHeaderKey]);
                if (canonicalKey === 'sku' || canonicalKey === 'productCode') {
                    rowSku = String(productDataFromCsv[canonicalKey as keyof Product]).trim();
                }
                break;
              }
            }
          }

          if (!rowSku) {
            console.warn("Skipping CSV row due to missing SKU/Product Code:", row);
            continue;
          }
          productDataFromCsv.sku = rowSku;
          productDataFromCsv.name = productDataFromCsv.name || 'Unnamed Product';
          productDataFromCsv.price = typeof productDataFromCsv.price === 'number' ? productDataFromCsv.price : 0;
          productDataFromCsv.quantityInStock = typeof productDataFromCsv.quantityInStock === 'number' ? productDataFromCsv.quantityInStock : 0;
          productDataFromCsv.isDemandNoticeProduct = productDataFromCsv.isDemandNoticeProduct || false;
          
          const existingProduct = currentProductsFromDb.find(p => p.sku === productDataFromCsv.sku);
          if (existingProduct) {
            const productToUpdate: Product = { ...existingProduct, ...productDataFromCsv, id: existingProduct.id };
            await contextUpdateProduct(productToUpdate);
            updatedCount++;
          } else {
            if (productDataFromCsv.name && productDataFromCsv.sku && productDataFromCsv.price !== undefined && productDataFromCsv.quantityInStock !== undefined) {
                await contextAddProduct(productDataFromCsv as Omit<Product, 'id'>);
                importedCount++;
            } else {
                toast({title: "Import Warning", description: `Skipped a new product (SKU: ${productDataFromCsv.sku || 'N/A'}) due to missing essential fields.`, variant: "default"});
            }
          }
        }
        await loadDataFromDb(true);
        toast({ title: 'Import Successful', description: `${importedCount} products imported, ${updatedCount} products updated.` });
      } catch (error) {
        console.error("CSV Import Error:", error);
        toast({ title: 'Import Failed', description: 'Error processing CSV file. Check console for details.', variant: 'destructive' });
      } finally {
        setIsSubmitting(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    };
    reader.readAsText(file);
  }, [canManageProducts, toast, loadDataFromDb, contextAddProduct, contextUpdateProduct]);

  const handleExportCSV = useCallback(async () => {
    if (!canManageProducts) {
        toast({ title: "Permission Denied", description: "You do not have permission to export products.", variant: "destructive" });
        return;
    }
    setIsSubmitting(true);
    const productsToExport = await getProductsFromDb();
    if (productsToExport.length === 0) {
        toast({ title: "No Products", description: "There are no products to export.", variant: "default" });
        setIsSubmitting(false);
        return;
    }
    const csvHeaders = ['id', 'name', 'sku', 'price', 'quantityInStock', 'category', 'imageUrl', 'expiryDate', 'isDemandNoticeProduct', 'lowStockThreshold', 'lowStockPrice'];
    const csvString = arrayToCsv(productsToExport, csvHeaders);
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', 'products_export.csv');
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    setIsSubmitting(false);
    toast({ title: "Products Exported", description: "Product data has been exported to CSV." });
  }, [canManageProducts, toast]);

  if (!currentUser || (!canManageProducts && !hasPermission('view_admin_dashboard'))) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to manage products.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl">Product & Inventory Management</CardTitle>
          <CardDescription>Manage your local product inventory and external store data.</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="my_products" className="w-full">
            <TabsList className="grid w-full grid-cols-2 mb-4">
              <TabsTrigger value="my_products" className="flex items-center gap-2">
                <Boxes className="h-5 w-5"/> My Products
              </TabsTrigger>
              <TabsTrigger value="external_stores" className="flex items-center gap-2">
                <StoreIcon className="h-5 w-5"/> External Stores Data
              </TabsTrigger>
            </TabsList>

            <TabsContent value="my_products">
              <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-4">
                <div className="relative flex-grow w-full md:w-auto">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                  <Input
                    type="search"
                    placeholder="Search products by name, Product Code, or category..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10 h-10 w-full"
                  />
                </div>
                {canManageProducts && (
                  <div className="flex flex-wrap gap-2 w-full md:w-auto justify-start md:justify-end">
                    <input type="file" ref={fileInputRef} onChange={handleFileImport} accept=".csv" className="hidden" disabled={isSubmitting} />
                    <Button onClick={handleImportClick} variant="outline" disabled={isSubmitting} className="w-full sm:w-auto">
                      <Upload className="mr-2 h-4 w-4" /> Import CSV
                    </Button>
                    <Button onClick={handleExportCSV} variant="outline" disabled={isSubmitting} className="w-full sm:w-auto">
                      <FileDown className="mr-2 h-4 w-4" /> Export CSV
                    </Button>
                    <Dialog open={isFormOpen} onOpenChange={(isOpen) => { if (!isSubmitting) setIsFormOpen(isOpen); if (!isOpen) setEditingProduct(null); }}>
                      <DialogTrigger asChild>
                        <Button onClick={handleAddProduct} disabled={isSubmitting} className="w-full sm:w-auto">
                          {isSubmitting && editingProduct === null ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlusCircle className="mr-2 h-4 w-4" />}
                          Add Product
                        </Button>
                      </DialogTrigger>
                      <DialogContent className="sm:max-w-2xl max-h-[85vh] overflow-y-auto">
                        <DialogHeader>
                          <DialogTitle>{editingProduct ? 'Edit Product' : 'Add New Product'}</DialogTitle>
                        </DialogHeader>
                        {isFormOpen && (
                          <ProductForm
                            product={editingProduct}
                            onSubmit={handleSubmitFormInPage}
                            onCancel={() => { setIsFormOpen(false); setEditingProduct(null); }}
                            isLoading={isSubmitting}
                            onUploadComplete={handleImageUploadComplete}
                          />
                        )}
                      </DialogContent>
                    </Dialog>
                  </div>
                )}
              </div>
              <div className="p-4 border rounded-md bg-muted/20 mb-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                      <div>
                          <Label htmlFor="quantity-filter-type" className="text-sm font-medium">Stock Quantity Filter</Label>
                          <Select value={quantityFilterType} onValueChange={(v) => setQuantityFilterType(v as any)}>
                              <SelectTrigger id="quantity-filter-type" className="h-9">
                                  <SelectValue placeholder="Filter by stock..." />
                              </SelectTrigger>
                              <SelectContent>
                                  <SelectItem value="all">All Stock Levels</SelectItem>
                                  <SelectItem value="lessThan">Less Than</SelectItem>
                                  <SelectItem value="greaterThan">Greater Than</SelectItem>
                                  <SelectItem value="equals">Exactly</SelectItem>
                              </SelectContent>
                          </Select>
                      </div>
                      <div className="md:col-span-2">
                           <Label htmlFor="quantity-filter-value" className="text-sm font-medium">Value</Label>
                          <Input
                              id="quantity-filter-value"
                              type="number"
                              placeholder="Enter stock number..."
                              value={quantityFilterValue}
                              onChange={(e) => setQuantityFilterValue(e.target.value)}
                              className="h-9"
                              disabled={quantityFilterType === 'all'}
                          />
                      </div>
                  </div>
              </div>
              {filteredProducts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-center">
                  <PackageOpen className="w-24 h-24 text-muted-foreground mb-6" />
                  <p className="text-2xl font-semibold mb-2">No products found.</p>
                  <p className="text-muted-foreground mb-6">
                    {searchTerm || quantityFilterType !== 'all' ? "Try a different search or filter." : (canManageProducts ? "Get started by adding a new product or importing a CSV." : "There are no products to display.")}
                  </p>
                  {!searchTerm && canManageProducts && ( <Button onClick={handleAddProduct} disabled={isSubmitting}> <PlusCircle className="mr-2 h-4 w-4" /> Add Your First Product </Button> )}
                </div>
              ) : (
                <ScrollArea className="h-[calc(100vh-30rem)] border rounded-md">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[80px]">Image</TableHead>
                        <TableHead>Name</TableHead>
                        <TableHead>Product Code</TableHead>
                        <TableHead className="text-right">Price</TableHead>
                        <TableHead className="text-center">Stock</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead>Expiry</TableHead>
                        <TableHead className="w-[50px]">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredProducts.map((product) => (
                        <MemoizedProductAdminRow key={product.id} product={product} onEdit={handleEditProduct} onDelete={handleDeleteProduct} isSubmitting={isSubmitting} canManageProducts={canManageProducts} />
                      ))}
                    </TableBody>
                  </Table>
                </ScrollArea>
              )}
            </TabsContent>

            <TabsContent value="external_stores">
              <ExternalStoresManager />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
