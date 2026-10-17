// src/components/admin/InvoiceIdLabelGenerator.tsx
'use client';

import React, { useState, useMemo } from 'react';
import { useApp } from '@/context/AppContext';
import type { Order, DemandNotice } from '@/types';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Search, Printer, FileText, BellRing, ListChecks } from 'lucide-react';
import PrintableLabelWrapper, { type InvoiceIdLabelItem } from './PrintableLabelWrapper';

interface SelectableSystemItem {
  id: string;
  type: 'Order' | 'Demand Notice';
  displayId: string;
  data: Order | DemandNotice;
}

interface SelectedItems {
  [itemId: string]: boolean;
}

export default function InvoiceIdLabelGenerator() {
  const { orders, demandNotices } = useApp();
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedItems, setSelectedItems] = useState<SelectedItems>({});
  const [printContentKey, setPrintContentKey] = useState(0);

  const allSearchableItems: SelectableSystemItem[] = useMemo(() => {
    const orderItems: SelectableSystemItem[] = orders.map(o => ({ id: o.id, type: 'Order', displayId: o.id, data: o }));
    const dnItems: SelectableSystemItem[] = demandNotices.map(dn => ({ id: dn.id, type: 'Demand Notice', displayId: dn.id, data: dn }));
    return [...orderItems, ...dnItems];
  }, [orders, demandNotices]);

  const filteredItems = useMemo(() => {
    if (!searchTerm.trim()) {
      return [];
    }
    return allSearchableItems.filter(item =>
      item.displayId.toLowerCase().includes(searchTerm.toLowerCase())
    ).sort((a,b) => a.displayId.localeCompare(b.displayId));
  }, [allSearchableItems, searchTerm]);

  const handleSelectItem = (itemId: string, isSelected: boolean) => {
    setSelectedItems(prev => ({
      ...prev,
      [itemId]: isSelected,
    }));
  };

  const itemsToPrintForLabelWrapper: InvoiceIdLabelItem[] = useMemo(() => {
    return allSearchableItems
      .filter(item => selectedItems[item.id])
      .map(item => {
        const labelItem: InvoiceIdLabelItem = { id: item.displayId, type: item.type };
        if (item.type === 'Order') {
          const orderData = item.data as Order;
          labelItem.customerName = orderData.customerName || 'N/A';
          labelItem.customerAddress = orderData.deliveryAddress || 'Not Provided';
        } else {
             const dnData = item.data as DemandNotice;
             labelItem.customerName = `Cust. Ph: ${dnData.customerContactNumber}`;
             labelItem.customerAddress = `Requested Item: ${dnData.productName}`;
        }
        return labelItem;
      });
  }, [allSearchableItems, selectedItems]);

  const handlePrintLabels = () => {
    if (itemsToPrintForLabelWrapper.length === 0) {
      alert("Please select IDs to print labels for.");
      return;
    }

    setPrintContentKey(prevKey => prevKey + 1);

    setTimeout(() => {
      const printContentEl = document.getElementById('existing-id-labels-printable-area');
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
            <title>ID Labels</title>
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

    }, 250);
  };

  const isAllFilteredSelected = filteredItems.length > 0 && filteredItems.every(item => selectedItems[item.id]);

  const handleSelectAllFiltered = (isSelected: boolean) => {
    const newSelected: SelectedItems = { ...selectedItems };
    filteredItems.forEach(item => {
      newSelected[item.id] = isSelected;
    });
    setSelectedItems(newSelected);
  };

  const selectedItemCount = Object.values(selectedItems).filter(Boolean).length;

  return (
    <div className="space-y-6">
      <Alert variant="default" className="bg-sky-50 border-sky-300 text-sky-700">
        <ListChecks className="h-5 w-5 text-sky-600" />
        <AlertTitle className="text-sky-800">Search and Print Existing IDs</AlertTitle>
        <AlertDescription className="text-sky-700">
          Search for existing Order or Demand Notice IDs to print labels for shipping or internal tracking.
        </AlertDescription>
      </Alert>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
        <Input
          type="search"
          placeholder="Search by Order ID or Demand Notice ID..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="pl-10 h-10 w-full"
        />
      </div>

      {searchTerm.trim() && filteredItems.length === 0 && (
        <p className="text-muted-foreground text-center py-4">No matching Order or Demand Notice IDs found for "{searchTerm}".</p>
      )}

      {filteredItems.length > 0 && (
        <>
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="select-all-filtered-ids"
                checked={isAllFilteredSelected}
                onCheckedChange={(checked) => handleSelectAllFiltered(Boolean(checked))}
              />
              <label htmlFor="select-all-filtered-ids" className="text-sm font-medium">
                Select All Displayed ({selectedItemCount} selected)
              </label>
            </div>
             <div className="flex gap-2">
              <Button onClick={handlePrintLabels} disabled={selectedItemCount === 0} variant="outline">
                <Printer className="mr-2 h-4 w-4" /> Print Selected ({selectedItemCount})
              </Button>
            </div>
          </div>
          <ScrollArea className="h-[250px] border rounded-md">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[50px]"></TableHead>
                  <TableHead>ID</TableHead>
                  <TableHead>Type</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems.map(item => (
                  <TableRow key={item.id} data-state={selectedItems[item.id] ? "selected" : ""}>
                    <TableCell>
                      <Checkbox
                        checked={selectedItems[item.id] || false}
                        onCheckedChange={(checked) => handleSelectItem(item.id, Boolean(checked))}
                      />
                    </TableCell>
                    <TableCell className="font-medium">{item.displayId}</TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        item.type === 'Order' ? 'bg-blue-100 text-blue-800' : 'bg-purple-100 text-purple-800'
                      }`}>
                        {item.type === 'Order' ? <FileText className="h-3 w-3 mr-1.5" /> : <BellRing className="h-3 w-3 mr-1.5" />}
                        {item.type}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        </>
      )}

      {/* Hidden container for printing */}
      <div className="absolute -left-[9999px] top-0 opacity-0 pointer-events-none">
        <div id="existing-id-labels-printable-area" className="printable-area">
          {itemsToPrintForLabelWrapper.length > 0 && (
            <PrintableLabelWrapper 
              key={printContentKey} 
              type="invoiceId" 
              items={itemsToPrintForLabelWrapper} 
            />
          )}
        </div>
      </div>
    </div>
  );
}
