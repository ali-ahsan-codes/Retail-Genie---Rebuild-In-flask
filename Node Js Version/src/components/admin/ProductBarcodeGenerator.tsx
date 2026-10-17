// src/components/admin/ProductBarcodeGenerator.tsx
'use client';

import React, { useState, useMemo } from 'react';
import { useApp } from '@/context/AppContext';
import type { Product } from '@/types';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Checkbox } from '@/components/ui/checkbox';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Search, Printer, PackageOpen } from 'lucide-react';
import PrintableLabelWrapper from './PrintableLabelWrapper';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Label } from '@/components/ui/label';

interface SelectedProducts {
  [productId: string]: boolean;
}

export default function ProductBarcodeGenerator() {
  const { products, getEffectiveProductPrice } = useApp();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedProducts, setSelectedProducts] = useState<SelectedProducts>({});
  const [barcodeFormat, setBarcodeFormat] = useState<'CODE128' | 'EAN-13'>('CODE128');
  const [printContentKey, setPrintContentKey] = useState(0); // To re-mount PrintableLabelWrapper

  const filteredProducts = useMemo(() => {
    return products.filter(product =>
      product.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.sku.toLowerCase().includes(searchTerm.toLowerCase())
    ).sort((a,b) => a.name.localeCompare(b.name));
  }, [products, searchTerm]);

  const handleSelectProduct = (productId: string, isSelected: boolean) => {
    setSelectedProducts(prev => ({
      ...prev,
      [productId]: isSelected,
    }));
  };

  const handleSelectAll = (isSelected: boolean) => {
    const newSelected: SelectedProducts = {};
    if (isSelected) {
      filteredProducts.forEach(p => newSelected[p.id] = true);
    }
    setSelectedProducts(newSelected);
  };

  const productsToPrint = useMemo(() => {
    return products.filter(p => selectedProducts[p.id]);
  }, [products, selectedProducts]);
  
  const itemsToPrintForWrapper = useMemo(() => {
    return productsToPrint.map(p => ({
        name: p.name,
        sku: p.sku,
        price: getEffectiveProductPrice(p).toFixed(2),
        expiryDate: p.expiryDate ? p.expiryDate : undefined,
    }));
  }, [productsToPrint, getEffectiveProductPrice]);

  const handlePrint = () => {
    if (itemsToPrintForWrapper.length === 0) {
      alert("Please select products to print labels for.");
      return;
    }
    
    setPrintContentKey(prevKey => prevKey + 1);

    setTimeout(() => {
      const printContentEl = document.getElementById('product-and-barcode-labels-printable-area');
      if (!printContentEl) {
        alert("Printable content not found.");
        return;
      }

      const printWindow = window.open('', '_blank', 'height=800,width=1000');
      if (!printWindow) {
        alert("Popup blocked. Please allow popups for this site.");
        return;
      }

      const stylesheets = Array.from(document.styleSheets)
        .map(s => s.href ? `<link rel="stylesheet" href="${s.href}">` : '')
        .join('\n');
      
      const printHtml = `
        <html>
          <head>
            <title>Product Labels</title>
            ${stylesheets}
            <style>
              @media print {
                @page { 
                  size: A4 portrait;
                  margin: 0.1in; 
                }
                body { 
                  -webkit-print-color-adjust: exact !important;
                  color-adjust: exact !important;
                }
              }
            </style>
          </head>
          <body style="margin: 0;">
            ${printContentEl.innerHTML}
          </body>
        </html>
      `;

      printWindow.document.open();
      printWindow.document.write(printHtml);
      printWindow.document.close();
      
      setTimeout(() => {
        printWindow.focus();
        printWindow.print();
        // The window does not close itself automatically on most browsers.
        // User closes it after printing/saving.
      }, 500);

    }, 250); // Small delay to ensure React state has updated
  };


  const isAllSelected = filteredProducts.length > 0 && filteredProducts.every(p => selectedProducts[p.id]);
  const selectedCount = Object.values(selectedProducts).filter(Boolean).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
          <Input
            id="product-search-barcodes"
            type="search"
            placeholder="Search by name or Product Code..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10 h-10 w-full"
          />
        </div>
        <RadioGroup value={barcodeFormat} onValueChange={(value) => setBarcodeFormat(value as any)} className="flex items-center space-x-4">
          <Label>Barcode Type:</Label>
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="CODE128" id="code128" />
            <Label htmlFor="code128">CODE128 (Alphanumeric)</Label>
          </div>
          <div className="flex items-center space-x-2">
            <RadioGroupItem value="EAN-13" id="ean13" />
            <Label htmlFor="ean13">EAN-13 (Numeric)</Label>
          </div>
        </RadioGroup>
      </div>
      

      {filteredProducts.length > 0 ? (
        <>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="select-all-barcodes"
                checked={isAllSelected}
                onCheckedChange={(checked) => handleSelectAll(Boolean(checked))}
              />
              <label htmlFor="select-all-barcodes" className="text-sm font-medium">
                Select All Displayed ({selectedCount} selected)
              </label>
            </div>
            <div className="flex gap-2">
              <Button onClick={handlePrint} disabled={selectedCount === 0} variant="outline">
                <Printer className="mr-2 h-4 w-4" /> Print Selected ({selectedCount})
              </Button>
            </div>
          </div>
          <ScrollArea className="h-[300px] border rounded-md">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[50px]"></TableHead>
                  <TableHead>Product Name</TableHead>
                  <TableHead>Product Code (SKU)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredProducts.map(product => (
                  <TableRow key={product.id} data-state={selectedProducts[product.id] ? "selected" : ""}>
                    <TableCell>
                      <Checkbox
                        checked={selectedProducts[product.id] || false}
                        onCheckedChange={(checked) => handleSelectProduct(product.id, Boolean(checked))}
                      />
                    </TableCell>
                    <TableCell className="font-medium">{product.name}</TableCell>
                    <TableCell>{product.sku}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </>
      ) : (
        <div className="text-center py-10 text-muted-foreground">
          <PackageOpen className="mx-auto h-12 w-12 mb-4" />
          <p>No products found matching your search.</p>
        </div>
      )}

      {/* Hidden container for printing */}
      <div className="absolute -left-[9999px] top-0 opacity-0 pointer-events-none">
        <div id="product-and-barcode-labels-printable-area" className="printable-area">
          {itemsToPrintForWrapper.length > 0 && (
            <PrintableLabelWrapper 
              key={printContentKey} 
              type={'product'} 
              items={itemsToPrintForWrapper} 
              barcodeFormat={barcodeFormat} 
            />
          )}
        </div>
      </div>
    </div>
  );
}
