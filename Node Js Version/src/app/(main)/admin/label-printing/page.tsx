// src/app/(main)/admin/label-printing/page.tsx
'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import InvoiceIdLabelGenerator from '@/components/admin/InvoiceIdLabelGenerator';
import { Tags, ShieldAlert, FileText, Barcode as BarcodeIcon } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import ProductBarcodeGenerator from '@/components/admin/ProductBarcodeGenerator';

export default function LabelPrintingPage() {
  const { hasPermission } = useApp();

  if (!hasPermission('manage_labels')) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to manage labels.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <Tags className="mr-2 h-7 w-7 text-primary" /> Label & Barcode Printing Center
          </CardTitle>
          <CardDescription>Generate and print product labels with barcodes and invoice ID labels for packages.</CardDescription>
        </CardHeader>
      </Card>

      <Tabs defaultValue="product_labels" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="product_labels" className="flex items-center gap-2">
            <BarcodeIcon className="h-5 w-5"/> Product Labels & Barcodes
          </TabsTrigger>
          <TabsTrigger value="invoice_id_labels" className="flex items-center gap-2">
             <FileText className="h-5 w-5"/> Invoice ID Labels
          </TabsTrigger>
        </TabsList>
        <TabsContent value="product_labels">
          <Card>
            <CardHeader>
              <CardTitle>Product Label & Barcode Generator</CardTitle>
              <CardDescription>Select products, choose a barcode format, and print labels.</CardDescription>
            </CardHeader>
            <CardContent>
              <ProductBarcodeGenerator />
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="invoice_id_labels">
          <Card>
            <CardHeader>
              <CardTitle>Invoice ID Label Generator</CardTitle>
              <CardDescription>Search for existing Order or Demand Notice IDs to print labels for shipping or internal tracking.</CardDescription>
            </CardHeader>
            <CardContent>
              <InvoiceIdLabelGenerator />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
