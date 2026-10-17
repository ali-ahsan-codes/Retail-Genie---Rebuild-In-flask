
'use client';

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import * as z from "zod";
import type { Product, DemandNotice } from "@/types";
import { Button } from "@/components/ui/button";
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { CalendarIcon, Search, AlertTriangle, Info } from "lucide-react";
import { Calendar } from "@/components/ui/calendar";
import { cn } from "@/lib/utils";
import { format } from 'date-fns';
import { useApp } from "@/context/AppContext";
import { Switch } from "@/components/ui/switch"; 

const demandNoticeFormSchema = z.object({
  isNewProduct: z.boolean().default(false),
  productId: z.string().optional(), 
  productName: z.string().min(2, { message: "Product name must be at least 2 characters." }),
  productSku: z.string().optional(), 
  customerContactNumber: z.string().min(7, { message: "Customer contact number is required." }),
  quantityRequested: z.coerce.number().min(1, { message: "Quantity must be at least 1." }).int(),
  agreedPrice: z.coerce.number().min(0, { message: "Agreed price must be a positive number." }),
  expectedAvailabilityDate: z.date({ required_error: "Expected availability date is required." }),
  notes: z.string().optional(),
}).refine(data => data.isNewProduct || !!data.productId, {
    message: "Please search and select an existing product, or mark as new product and enter details.",
    path: ["productId"], 
});


type DemandNoticeFormValues = z.infer<typeof demandNoticeFormSchema>;

interface DemandNoticeFormProps {
  notice?: DemandNotice | null;
  onSubmit: (data: Omit<DemandNotice, 'id' | 'createdAt' | 'updatedAt' | 'salespersonId' | 'salespersonName' | 'status' | 'payments' | 'quantityFulfilled' | 'linkedOrderId'> & { expectedAvailabilityDate: string }) => void;
  onCancel?: () => void;
  isLoading?: boolean;
}

export default function DemandNoticeForm({ notice, onSubmit, onCancel, isLoading = false }: DemandNoticeFormProps) {
  const { products, currentUser, getProductBySku } = useApp(); // Added getProductBySku
  const [productSearch, setProductSearch] = React.useState("");
  const [productSearchResults, setProductSearchResults] = React.useState<Product[]>([]);
  const [isProductSearchOpen, setIsProductSearchOpen] = React.useState(false);
  const [confirmedSelectedProduct, setConfirmedSelectedProduct] = React.useState<Product | null>(null);
  const searchResultsRef = React.useRef<HTMLDivElement>(null);
  const [isCalendarOpen, setIsCalendarOpen] = React.useState(false);


  const form = useForm<DemandNoticeFormValues>({
    resolver: zodResolver(demandNoticeFormSchema),
    defaultValues: notice
      ? {
          isNewProduct: notice.isNewProduct,
          productId: notice.productId || "",
          productName: notice.productName,
          productSku: notice.productSku,
          customerContactNumber: notice.customerContactNumber,
          quantityRequested: notice.quantityRequested,
          agreedPrice: notice.agreedPrice,
          expectedAvailabilityDate: new Date(notice.expectedAvailabilityDate),
          notes: notice.notes || "",
        }
      : {
          isNewProduct: false,
          productId: "",
          productName: "",
          productSku: "",
          customerContactNumber: "",
          quantityRequested: 1,
          agreedPrice: 0,
          expectedAvailabilityDate: undefined,
          notes: "",
        },
  });

  const isNewProductMode = form.watch("isNewProduct");
  const quantityRequested = form.watch("quantityRequested");
  const agreedPrice = form.watch("agreedPrice");
  const productSkuValue = form.watch("productSku");

  const totalAgreedAmount = React.useMemo(() => {
    const qty = Number(quantityRequested) || 0;
    const price = Number(agreedPrice) || 0;
    return qty * price;
  }, [quantityRequested, agreedPrice]);

   React.useEffect(() => {
    if (notice && products.length > 0 && !confirmedSelectedProduct && !notice.isNewProduct && notice.productId) {
      const initialProduct = products.find(p => p.id === notice.productId);
      if (initialProduct) {
        setConfirmedSelectedProduct(initialProduct);
        setProductSearch(initialProduct.name);
        form.setValue("productId", initialProduct.id);
        form.setValue("productName", initialProduct.name);
        form.setValue("productSku", initialProduct.sku);
        form.setValue("agreedPrice", initialProduct.price); 
      }
    } else if (notice && notice.isNewProduct) {
        form.setValue("productName", notice.productName);
        form.setValue("productSku", notice.productSku);
        setProductSearch(notice.productName); 
    }
  }, [notice, products, form, confirmedSelectedProduct]);


  React.useEffect(() => {
    if (isNewProductMode) {
        setProductSearchResults([]);
        setIsProductSearchOpen(false);
        setConfirmedSelectedProduct(null);
        form.setValue("productId", undefined); 
    }
  }, [isNewProductMode, form]);


  React.useEffect(() => {
    if (isNewProductMode || (confirmedSelectedProduct && productSearch === confirmedSelectedProduct.name)) {
        setProductSearchResults([]);
        setIsProductSearchOpen(false);
        return;
    }
    if (productSearch.trim() === "" && !confirmedSelectedProduct) {
      setProductSearchResults([]);
      return;
    }

    const filtered = products.filter(
      (p) =>
        p.name.toLowerCase().includes(productSearch.toLowerCase()) ||
        p.sku.toLowerCase().includes(productSearch.toLowerCase()) 
    );
    setProductSearchResults(filtered);
  }, [productSearch, products, confirmedSelectedProduct, isNewProductMode]);
  
   React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchResultsRef.current && !searchResultsRef.current.contains(event.target as Node)) {
        const inputElement = document.getElementById('product-search-input'); 
        if (inputElement && !inputElement.contains(event.target as Node)) {
            setIsProductSearchOpen(false);
        }
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [searchResultsRef]);

  React.useEffect(() => {
    if (isNewProductMode && productSkuValue && productSkuValue.trim() !== "") {
        const existingProduct = getProductBySku(productSkuValue.trim());
        if (existingProduct) {
            form.setError("productSku", {
                type: "manual",
                message: `Product Code '${productSkuValue.trim()}' already exists. Use a different code or uncheck "New Product".`
            });
        } else {
            form.clearErrors("productSku");
        }
    } else {
        form.clearErrors("productSku");
    }
  }, [productSkuValue, isNewProductMode, getProductBySku, form]);


  const handleSubmit = (data: DemandNoticeFormValues) => {
    if (!data.isNewProduct && (!confirmedSelectedProduct || data.productId !== confirmedSelectedProduct.id)) {
      form.setError("productId", { type: "manual", message: "Please search and select a valid existing product." });
      return;
    }
    
    const submissionData: any = {
      ...data,
      expectedAvailabilityDate: format(data.expectedAvailabilityDate, "yyyy-MM-dd'T'HH:mm:ss.SSSxxx"),
    };

    if (data.isNewProduct) {
        submissionData.productId = undefined; 
    } else if (confirmedSelectedProduct) {
        submissionData.productName = confirmedSelectedProduct.name;
        submissionData.productSku = confirmedSelectedProduct.sku;
        submissionData.productId = confirmedSelectedProduct.id;
    }
    
    onSubmit(submissionData);
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        <FormField
            control={form.control}
            name="isNewProduct"
            render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3 shadow-sm">
                <div className="space-y-0.5">
                    <FormLabel>New Product Request?</FormLabel>
                    <FormDescription>
                    Enable if this product is not in our current inventory.
                    </FormDescription>
                </div>
                <FormControl>
                    <Switch
                    checked={field.value}
                    onCheckedChange={(checked) => {
                        field.onChange(checked);
                        if (!checked && confirmedSelectedProduct) { // If switching back from new to existing, re-populate if a product was selected
                            form.setValue("productName", confirmedSelectedProduct.name);
                            form.setValue("productSku", confirmedSelectedProduct.sku);
                            form.setValue("agreedPrice", confirmedSelectedProduct.price);
                        } else if (checked) { // If switching to new, clear product selection info
                           // form.setValue("productName", ""); // Keep user entered name if any
                           // form.setValue("productSku", ""); // Keep user entered sku if any
                           form.setValue("agreedPrice", 0);
                           setConfirmedSelectedProduct(null);
                           setProductSearch(form.getValues("productName")); // Keep search field consistent if user typed name then hit new
                        }
                    }}
                    />
                </FormControl>
                </FormItem>
            )}
        />

        {!isNewProductMode ? (
            <FormField
            control={form.control}
            name="productId"
            render={({ field }) => (
                <FormItem>
                <FormLabel>Search Existing Product</FormLabel>
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                    id="product-search-input"
                    placeholder="Search by name or Product Code..."
                    value={productSearch}
                    onChange={(e) => {
                        setProductSearch(e.target.value);
                        if (confirmedSelectedProduct && e.target.value !== confirmedSelectedProduct.name) {
                        setConfirmedSelectedProduct(null);
                        field.onChange(undefined); 
                        form.setValue("agreedPrice", 0); 
                        form.setValue("productName", ""); // Clear product name too
                        form.setValue("productSku", "");   // Clear product sku too
                        }
                        setIsProductSearchOpen(true); 
                    }}
                    onFocus={() => setIsProductSearchOpen(true)}
                    className="pl-10"
                    autoComplete="off"
                    disabled={isNewProductMode}
                    />
                    {isProductSearchOpen && productSearchResults.length > 0 && !isNewProductMode && (
                    <div ref={searchResultsRef} className="absolute z-50 w-full bg-card border mt-1 rounded-md shadow-lg max-h-60 overflow-y-auto">
                        {productSearchResults.map((p) => (
                        <div
                            key={p.id}
                            className="p-3 hover:bg-accent cursor-pointer text-sm"
                            onClick={() => {
                            field.onChange(p.id);
                            setConfirmedSelectedProduct(p);
                            setProductSearch(p.name);
                            form.setValue("productName", p.name);
                            form.setValue("productSku", p.sku);
                            setIsProductSearchOpen(false);
                            if (form.getValues("agreedPrice") === 0 || !notice) {
                                form.setValue("agreedPrice", p.price, {shouldValidate: true});
                            }
                            }}
                        >
                            <p className="font-medium">{p.name} <span className="text-xs text-muted-foreground">(Code: {p.sku})</span></p>
                            <p className="text-xs text-muted-foreground">Stock: {p.quantityInStock}</p>
                        </div>
                        ))}
                    </div>
                    )}
                </div>
                {confirmedSelectedProduct && confirmedSelectedProduct.quantityInStock > 0 && !isNewProductMode && (
                    <FormDescription className="text-orange-600 flex items-center gap-1">
                    <AlertTriangle className="h-4 w-4"/> Note: This product has {confirmedSelectedProduct.quantityInStock} unit(s) in stock.
                    </FormDescription>
                )}
                <FormMessage />
                </FormItem>
            )}
            />
        ) : (
            <>
             <FormField
                control={form.control}
                name="productName"
                render={({ field }) => (
                    <FormItem>
                    <FormLabel>Product Name (New)</FormLabel>
                    <FormControl><Input placeholder="Enter new product name" {...field} /></FormControl>
                    <FormMessage />
                    </FormItem>
                )}
                />
                <FormField
                control={form.control}
                name="productSku"
                render={({ field }) => (
                    <FormItem>
                    <FormLabel>Product Code (New - Optional)</FormLabel>
                    <FormControl><Input placeholder="Leave blank to auto-generate" {...field} value={field.value || ''} /></FormControl>
                    <FormDescription>Backend will auto-generate a unique code if left blank for a new product.</FormDescription>
                    <FormMessage />
                    </FormItem>
                )}
                />
            </>
        )}

        <FormField
          control={form.control}
          name="customerContactNumber"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Customer Contact Number</FormLabel>
              <FormControl>
                <Input placeholder="e.g., 91234567" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        
        <div className="grid grid-cols-2 gap-4">
            <FormField
            control={form.control}
            name="quantityRequested"
            render={({ field }) => (
                <FormItem>
                <FormLabel>Quantity Requested</FormLabel>
                <FormControl>
                    <Input type="number" placeholder="1" {...field} />
                </FormControl>
                <FormMessage />
                </FormItem>
            )}
            />
            <FormField
            control={form.control}
            name="agreedPrice"
            render={({ field }) => (
                <FormItem>
                <FormLabel>Agreed Price per Unit</FormLabel>
                <FormControl>
                    <Input type="number" placeholder="0.00" {...field} step="0.01" />
                </FormControl>
                <FormMessage />
                </FormItem>
            )}
            />
        </div>

        <div className="mt-2 p-3 border rounded-md bg-muted/50">
            <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-foreground">Total Agreed Amount:</span>
                <span className="text-lg font-bold text-primary">OMR {totalAgreedAmount.toFixed(2)}</span>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
                This is calculated as Quantity Requested × Agreed Price per Unit.
            </p>
        </div>


        <FormField
          control={form.control}
          name="expectedAvailabilityDate"
          render={({ field }) => (
            <FormItem className="flex flex-col">
              <FormLabel>Expected Availability Date</FormLabel>
              <Popover open={isCalendarOpen} onOpenChange={setIsCalendarOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant={"outline"}
                    className={cn(
                      "w-full justify-start text-left font-normal",
                      !field.value && "text-muted-foreground"
                    )}
                  >
                    {field.value ? (
                      format(field.value, "PPP")
                    ) : (
                      <span>Pick a date</span>
                    )}
                    <CalendarIcon className="ml-auto h-4 w-4 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={field.value}
                    onSelect={(date) => {
                      field.onChange(date);
                      setIsCalendarOpen(false);
                    }}
                    disabled={(date) => date < new Date(new Date().setHours(0,0,0,0))} 
                    initialFocus
                  />
                </PopoverContent>
              </Popover>
              <FormMessage />
            </FormItem>
          )}
        />
        
        <FormField
          control={form.control}
          name="notes"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Notes (Optional)</FormLabel>
              <FormControl>
                <Textarea placeholder="Any specific details or customer requests..." {...field} value={field.value ?? ''}/>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex justify-end gap-2 pt-4">
          {onCancel && <Button type="button" variant="outline" onClick={onCancel} disabled={isLoading}>Cancel</Button>}
          <Button 
            type="submit" 
            disabled={
                isLoading || 
                (!isNewProductMode && !confirmedSelectedProduct) ||
                (isNewProductMode && !!form.formState.errors.productSku)
            }
          >
            {isLoading ? "Saving..." : (notice ? "Save Changes" : "Create Demand Notice")}
          </Button>
        </div>
      </form>
    </Form>
  );
}
    
