// src/app/(main)/salesperson/quotations/[quotationId]/view/page.tsx
'use client';
import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import type { Quotation } from '@/types';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ArrowLeft, Edit3 as RevisionIcon, FileText, Loader2, AlertTriangle, Printer, Send, CheckCircle, XCircle, CornerDownLeft, FileStack, PauseCircle } from 'lucide-react';
import { format, parseISO, isValid } from 'date-fns';
import Link from 'next/link';
import { brandingConfig } from '@/config/branding';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from '@/components/ui/dialog';


export default function ViewQuotationPage() {
  const router = useRouter();
  const params = useParams();
  const quotationId = params.quotationId as string;
  const { getQuotationById, currentUser, isDataLoaded, updateQuotation, convertQuotationToDemandNotices, convertQuotationToOrder } = useApp();
  const [quotation, setQuotation] = useState<Quotation | null | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isPrintDialogOpen, setIsPrintDialogOpen] = useState(false);
  const { toast } = useToast();

  const items = useMemo(() => quotation?.items || [], [quotation]);

  const hasUnconvertedInternalItems = useMemo(() =>
    items.some(item => !item.isExternal && !item.converted),
  [items]);

  const hasUnconvertedExternalItems = useMemo(() =>
    items.some(item => item.isExternal && !item.converted),
  [items]);


  const fetchQuotationData = useCallback(async () => {
    if (quotationId && currentUser?.id && isDataLoaded) {
      setIsLoading(true);
      const fetchedQuotation = await getQuotationById(quotationId);
      setQuotation(fetchedQuotation || null);
      setIsLoading(false);
    } else if (isDataLoaded && !currentUser?.id) {
      router.replace('/login');
    }
  }, [quotationId, getQuotationById, currentUser, isDataLoaded, router]);

  useEffect(() => {
    fetchQuotationData();
  }, [fetchQuotationData]);

  const handlePrint = (printFormat: 'A4' | 'A5') => {
    if (!quotation || !currentUser) {
        toast({ title: "Error", description: "Quotation data or user data is not available.", variant: "destructive"});
        return;
    }

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      toast({ title: "Print Error", description: "Please allow popups for this site to print.", variant: "destructive" });
      return;
    }
    
    setIsPrintDialogOpen(false); // Close the dialog after initiating print

    const quotationDate = isValid(parseISO(quotation.createdAt)) ? format(parseISO(quotation.createdAt), "MMMM dd, yyyy") : 'N/A';
    const quotationValidUntil = isValid(parseISO(quotation.validUntil)) ? format(parseISO(quotation.validUntil), "MMMM dd, yyyy") : 'N/A';
    const quotationStatusPrint = quotation.status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());

    const pageLayoutCss = printFormat === 'A4'
      ? `@page { size: A4; margin: 2in 0.5in 0.5in 0.5in; } body { font-size: 10pt; }` // Margin for letterhead
      : `@page { size: A5; margin: 0.5in; } body { font-size: 9pt; }`;

    const printStyles = `
      <style>
        ${pageLayoutCss}
        body { font-family: Arial, sans-serif; -webkit-print-color-adjust: exact !important; color-adjust: exact !important; color: #333; }
        .print-container { width: 100%; }
        .header { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 1rem; border-bottom: 2px solid #ddd; }
        .header-left { text-align: left; }
        .header-right { text-align: right; }
        .quotation-title { font-size: 2em; font-weight: bold; color: #555; }
        .details-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-top: 1.5rem; padding: 1rem; border: 1px solid #eee; background-color: #fcfcfc; border-radius: 8px;}
        .details-grid h3 { font-size: 0.9em; font-weight: bold; color: #666; margin-bottom: 0.5rem; border-bottom: 1px solid #eee; padding-bottom: 0.25rem; }
        .details-grid p { margin: 0 0 0.25rem 0; font-size: 0.9em; }
        .items-table { width: 100%; border-collapse: collapse; margin-top: 1.5rem; font-size: 0.9em; }
        .items-table th, .items-table td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }
        .items-table th { background-color: #f8f8f8 !important; font-weight: bold; }
        .items-table .text-right { text-align: right; }
        .items-table .text-center { text-align: center; }
        .totals-section { margin-top: 1.5rem; display: flex; justify-content: flex-end; }
        .totals-box { width: 40%; min-width: 250px; }
        .totals-box .total-row { display: flex; justify-content: space-between; padding: 0.4rem 0; }
        .totals-box .grand-total { font-size: 1.2em; font-weight: bold; border-top: 2px solid #333; margin-top: 0.5rem; padding-top: 0.5rem; }
        .notes-section { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #eee; font-size: 0.8em; color: #666; }
        .notes-section h4 { font-weight: bold; margin-bottom: 0.5rem; color: #444; }
        .notes-section ul { list-style-position: inside; padding-left: 0.5rem; }
        .footer { text-align: center; margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #ddd; font-size: 0.8em; color: #888; }
      </style>
    `;
    
    const pageContent = `
      <div class="print-container">
        <div class="header">
          <div class="header-left">
            <h2 class="quotation-title">QUOTATION / عرض سعر</h2>
            <p><strong>Quotation ID: / رقم عرض السعر:</strong> ${quotation.id}</p>
            <p><strong>Status: / الحالة:</strong> ${quotationStatusPrint}</p>
          </div>
          <div class="header-right">
            <p><strong>Date Created: / تاريخ الإنشاء:</strong> ${quotationDate}</p>
            <p><strong>Valid Until: / صالح حتى:</strong> ${quotationValidUntil}</p>
          </div>
        </div>

        <div class="details-grid">
          <div>
            <h3>Bill To: / فاتورة إلى:</h3>
            <p><strong>${quotation.customerName || 'N/A'}</strong></p>
            <p>${quotation.customerAddress || ''}</p>
            <p>P: ${quotation.customerPhone || 'N/A'}</p>
            <p>E: ${quotation.customerEmail || 'N/A'}</p>
          </div>
          <div>
            <h3>From: / من:</h3>
            <p><strong>${brandingConfig.companyNameForInvoice}</strong></p>
            <p>${brandingConfig.companyAddressForInvoice}</p>
            <p>P: ${brandingConfig.companyPhoneForInvoice}</p>
            <p><strong>Sales Rep: / مندوب المبيعات:</strong> ${currentUser.username}</p>
            <p><strong>Preparation Time: / وقت التحضير:</strong> ${quotation.preparationDays} day(s)</p>
          </div>
        </div>

        <table class="items-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Item Description / وصف السلعة</th>
              <th class="text-center">Qty / الكمية</th>
              <th class="text-right">Unit Price / سعر الوحدة</th>
              <th class="text-right">Total / المجموع</th>
            </tr>
          </thead>
          <tbody>
            ${(quotation.items || []).map((item, index) => `
              <tr>
                <td>${index + 1}</td>
                <td>
                  ${item.productName}
                  ${item.isExternal ? ' <em style="font-size: 0.9em; color: #555;">(External)</em>' : ''}
                </td>
                <td class="text-center">${item.quantity}</td>
                <td class="text-right">OMR ${item.price.toFixed(2)}</td>
                <td class="text-right">OMR ${(item.price * item.quantity).toFixed(2)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
        
        <div class="totals-section">
            <div class="totals-box">
                <div class="total-row grand-total">
                    <span>Grand Total: / المجموع الإجمالي:</span>
                    <span>OMR ${quotation.totalAmount.toFixed(2)}</span>
                </div>
            </div>
        </div>
        
        <div class="notes-section">
          ${quotation.notes ? `<h4>Notes: / ملاحظات:</h4><p style="white-space: pre-wrap;">${quotation.notes}</p>` : ''}
          ${(brandingConfig.returnPolicyNotes && brandingConfig.returnPolicyNotes.length > 0) ? `
            <h4 style="margin-top: 1rem;">Company Terms: / شروط الشركة:</h4>
            <ul>${brandingConfig.returnPolicyNotes.map(note => `<li>${note}</li>`).join('')}</ul>
          ` : ''}
        </div>

        <div class="footer">
          <p>Thank you for your business! / شكرا لتعاملكم معنا!</p>
          <p>${brandingConfig.companyNameForInvoice}</p>
        </div>
      </div>
    `;

    printWindow.document.write(`<html><head><title>Quotation - ${quotation.id}</title>${printStyles}</head><body>${pageContent}</body></html>`);
    printWindow.document.close();
    setTimeout(() => {
      printWindow.print();
    }, 500);
  };


  const handleStatusUpdate = async (newStatus: Quotation['status']) => {
    if (!quotation) return;
    setIsProcessing(true);
    try {
      const updatedQuotation = await updateQuotation({ id: quotation.id, status: newStatus });
      if (updatedQuotation) {
        setQuotation(updatedQuotation);
        toast({ title: "Status Updated", description: `Quotation status changed to ${newStatus}.`});
      } else {
        toast({ title: "Error", description: "Failed to update quotation status.", variant: "destructive"});
      }
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive"});
    } finally {
      setIsProcessing(false);
    }
  };

  const handleConvertToDemandNotice = async () => {
    if (!quotation || !currentUser) return;
    setIsProcessing(true);
    try {
      const result = await convertQuotationToDemandNotices(quotation.id);
      if (result && result.createdDemandNoticeIds.length > 0) {
        toast({
          title: "Conversion Successful",
          description: `${result.createdDemandNoticeIds.length} demand notice(s) created.`,
          className: "bg-accent text-accent-foreground"
        });
        await fetchQuotationData();
      } else if (result) {
         toast({ title: "No Items Converted", description: "No external, unconverted items were found in this quotation."});
      } else {
         toast({ title: "Conversion Failed", description: "Could not convert to Demand Notice(s).", variant: "destructive"});
      }
    } catch (error) {
      toast({ title: "Error", description: (error as Error).message, variant: "destructive"});
    } finally {
      setIsProcessing(false);
    }
  };

  const handleConvertToOrder = async () => {
    if (!quotation || !currentUser) return;
    setIsProcessing(true);
    try {
      const createdOrder = await convertQuotationToOrder(quotation.id);
      if (createdOrder) {
        toast({
          title: "Conversion Successful",
          description: `Order ${createdOrder.id} created from quotation.`,
          className: "bg-accent text-accent-foreground"
        });
        await fetchQuotationData(); 
      }
    } catch (error) { 
      toast({ title: "Error", description: (error as Error).message || "Could not convert to Order.", variant: "destructive"});
    } finally {
      setIsProcessing(false);
    }
  };

  if (isLoading || !isDataLoaded) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="h-8 w-8 animate-spin text-primary" /> <span className="ml-2">Loading quotation...</span></div>;
  }

  if (quotation === null) { 
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <AlertTriangle className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Quotation Not Found</h1>
        <p className="text-muted-foreground">The quotation you are looking for does not exist or you do not have permission to view it.</p>
        <Button onClick={() => router.back()} className="mt-4"><ArrowLeft className="mr-2 h-4 w-4" /> Go Back</Button>
      </div>
    );
  }
  
  if (quotation === undefined) { 
     return <div className="flex justify-center items-center h-64"><Loader2 className="h-8 w-8 animate-spin text-primary" /> <span className="ml-2">Preparing editor...</span></div>;
  }

  const {
    id, customerName: qCustomerName, customerPhone: qCustomerPhone, customerEmail: qCustomerEmail, customerAddress: qCustomerAddress,
    preparationDays, validUntil: qValidUntil, status, createdAt: qCreatedAt,
    totalAmount, notes
  } = quotation;

  const getStatusBadgeVariant = (currentStatus: Quotation['status']) => {
    switch (currentStatus) {
      case 'draft': return 'bg-gray-200 text-gray-700 border-gray-300';
      case 'sent': return 'bg-blue-100 text-blue-700 border-blue-300';
      case 'accepted': return 'bg-green-100 text-green-700 border-green-300';
      case 'rejected': return 'bg-red-100 text-red-700 border-red-300';
      case 'revision': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'hold': return 'bg-purple-100 text-purple-700 border-purple-300';
      case 'converted': return 'bg-teal-100 text-teal-700 border-teal-300';
      default: return 'bg-muted text-muted-foreground';
    }
  };

  return (
    <div className="space-y-6 printable-area">
      <div className="flex justify-between items-center no-print">
        <Button variant="outline" onClick={() => router.back()}><ArrowLeft className="mr-2 h-4 w-4" /> Back to Quotations</Button>
        <div className="flex gap-2">
          {(status === 'draft' || status === 'revision') && (
            <Button variant="outline" asChild>
              <Link href={`/salesperson/quotations/${id}/edit`}><RevisionIcon className="mr-2 h-4 w-4" /> Edit</Link>
            </Button>
          )}
           <Dialog open={isPrintDialogOpen} onOpenChange={setIsPrintDialogOpen}>
              <DialogTrigger asChild>
                <Button><Printer className="mr-2 h-4 w-4" /> Print Options</Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-md">
                  <DialogHeader>
                      <DialogTitle>Choose Print Format</DialogTitle>
                      <DialogDescription>
                          Select the paper size and format for your quotation.
                      </DialogDescription>
                  </DialogHeader>
                  <div className="flex flex-col space-y-3 py-4">
                      <Button onClick={() => handlePrint('A4')} className="w-full">Print A4 (for Letterhead)</Button>
                      <Button onClick={() => handlePrint('A5')} className="w-full">Print A5 (Small Slip)</Button>
                  </div>
              </DialogContent>
          </Dialog>
        </div>
      </div>

      <Card className="shadow-lg">
        <CardHeader className="border-b pb-4">
            <div className="flex flex-col sm:flex-row justify-between items-start">
                <div>
                    <div className="flex items-center gap-2 mb-1">
                        <img src={brandingConfig.logoPath} alt="Company Logo" className="h-10" data-ai-hint="logo company"/>
                        <h1 className="text-2xl font-bold text-primary">{brandingConfig.companyNameForInvoice}</h1>
                    </div>
                    <p className="text-xs text-muted-foreground">{brandingConfig.companyAddressForInvoice}</p>
                    <p className="text-xs text-muted-foreground">Tel: {brandingConfig.companyPhoneForInvoice}</p>
                </div>
                <div className="text-left sm:text-right mt-4 sm:mt-0">
                    <h2 className="text-3xl font-bold text-gray-700">QUOTATION</h2>
                    <p className="text-sm"><strong>Quotation ID:</strong> {id}</p>
                    <p className="text-sm"><strong>Date Created:</strong> {isValid(parseISO(qCreatedAt)) ? format(parseISO(qCreatedAt), 'PPp') : 'N/A'}</p>
                    <p className="text-sm"><strong>Valid Until:</strong> {isValid(parseISO(qValidUntil)) ? format(parseISO(qValidUntil), 'PP') : 'N/A'}</p>
                </div>
            </div>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <div>
              <h3 className="font-semibold mb-1 text-gray-600">Bill To:</h3>
              <p>{qCustomerName || 'N/A'}</p>
              <p>{qCustomerAddress || 'N/A'}</p>
              <p>Phone: {qCustomerPhone || 'N/A'}</p>
              <p>Email: {qCustomerEmail || 'N/A'}</p>
            </div>
            <div className="md:text-right">
              <p className="text-sm"><strong className="text-gray-600">Preparation Time:</strong> {preparationDays} day(s)</p>
              <p className="text-sm"><strong className="text-gray-600">Status:</strong> <Badge className={cn("capitalize", getStatusBadgeVariant(status))}>{status.replace(/_/g, ' ')}</Badge></p>
              <p className="text-sm"><strong className="text-gray-600">Salesperson:</strong> {currentUser?.username}</p>
            </div>
          </div>

          <h3 className="font-semibold text-gray-600 mb-2">Items:</h3>
          <ScrollArea className="max-h-[300px] border rounded-md">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[50px]">#</TableHead>
                  <TableHead>Product / Service</TableHead>
                  <TableHead>SKU</TableHead>
                  <TableHead className="text-center">Qty</TableHead>
                  <TableHead className="text-right">Unit Price</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item, index) => (
                  <TableRow key={item.id}>
                    <TableCell>{index + 1}</TableCell>
                    <TableCell>
                        {item.productName}
                        {item.isExternal && <Badge variant="outline" className="ml-2 text-xs">External</Badge>}
                         {item.converted && <Badge variant="outline" className="ml-2 text-xs bg-green-100 text-green-700 border-green-300">Converted</Badge>}
                    </TableCell>
                    <TableCell>{item.productSku || 'N/A'}</TableCell>
                    <TableCell className="text-center">{item.quantity}</TableCell>
                    <TableCell className="text-right">OMR {item.price.toFixed(2)}</TableCell>
                    <TableCell className="text-right">OMR {(item.price * item.quantity).toFixed(2)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>

          <div className="flex justify-end mt-6">
            <div className="w-full max-w-xs space-y-1 text-sm">
              <div className="flex justify-between">
                <span>Subtotal:</span>
                <span>OMR {(items.reduce((sum, item) => sum + item.price * item.quantity, 0)).toFixed(2)}</span>
              </div>
              <div className="flex justify-between font-bold text-lg border-t pt-2 mt-1 text-primary">
                <span>Grand Total:</span>
                <span>OMR {totalAmount.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {notes && (
            <div className="mt-6 pt-4 border-t">
              <h4 className="font-semibold text-gray-600 mb-1">Notes &amp; Terms:</h4>
              <p className="text-xs whitespace-pre-wrap text-muted-foreground">{notes}</p>
            </div>
          )}

          <div className="mt-8 pt-4 border-t text-center text-xs text-muted-foreground no-print">
            <p>If you have any questions concerning this quotation, please contact {currentUser?.username}.</p>
            <p>Thank you for your business!</p>
          </div>
        </CardContent>

        {status !== 'converted' && status !== 'rejected' && (
          <CardFooter className="border-t p-4 flex flex-col sm:flex-row justify-end gap-2 no-print">
            {status === 'draft' && (
                <Button variant="outline" onClick={() => handleStatusUpdate('sent')} disabled={isProcessing || items.length === 0}><Send className="mr-2 h-4 w-4"/> Mark as Sent</Button>
            )}
            {status === 'sent' && (
              <>
                <Button variant="secondary" onClick={() => handleStatusUpdate('revision')} disabled={isProcessing}><RevisionIcon className="mr-2 h-4 w-4"/> Revision Requested</Button>
                <Button className="bg-green-600 hover:bg-green-700 text-white" onClick={() => handleStatusUpdate('accepted')} disabled={isProcessing}><CheckCircle className="mr-2 h-4 w-4"/> Mark as Accepted</Button>
                <Button variant="destructive" onClick={() => handleStatusUpdate('rejected')} disabled={isProcessing}><XCircle className="mr-2 h-4 w-4"/>Mark as Rejected</Button>
                <Button variant="outline" onClick={() => handleStatusUpdate('hold')} disabled={isProcessing}><PauseCircle className="mr-2 h-4 w-4"/> Put on Hold</Button>
              </>
            )}
            {status === 'accepted' && (
              <>
                <Button variant="outline" className="border-blue-500 text-blue-600 hover:bg-blue-50" onClick={handleConvertToOrder} disabled={isProcessing || !hasUnconvertedInternalItems}>
                    <FileText className="mr-2 h-4 w-4"/> Convert Internal to Order
                </Button>
                <Button variant="outline" className="border-purple-500 text-purple-600 hover:bg-purple-50" onClick={handleConvertToDemandNotice} disabled={isProcessing || !hasUnconvertedExternalItems}>
                    <FileStack className="mr-2 h-4 w-4"/> Convert External to DN
                </Button>
                <Button variant="outline" onClick={() => handleStatusUpdate('hold')} disabled={isProcessing}><PauseCircle className="mr-2 h-4 w-4"/> Put on Hold</Button>
                <Button variant="outline" onClick={() => handleStatusUpdate('sent')} disabled={isProcessing}><Send className="mr-2 h-4 w-4"/> Revert to Sent</Button>
              </>
            )}
             {status === 'revision' && (
                <Button variant="outline" onClick={() => handleStatusUpdate('sent')} disabled={isProcessing}><Send className="mr-2 h-4 w-4"/> Resend Quotation</Button>
            )}
            {status === 'hold' && (
              <>
                <Button variant="outline" onClick={() => handleStatusUpdate('sent')} disabled={isProcessing}><Send className="mr-2 h-4 w-4"/> Resume (Mark as Sent)</Button>
                <Button className="bg-green-600 hover:bg-green-700 text-white" onClick={() => handleStatusUpdate('accepted')} disabled={isProcessing}><CheckCircle className="mr-2 h-4 w-4"/> Mark as Accepted</Button>
                <Button variant="destructive" onClick={() => handleStatusUpdate('rejected')} disabled={isProcessing}><XCircle className="mr-2 h-4 w-4"/>Mark as Rejected</Button>
              </>
            )}
          </CardFooter>
        )}
         {status === 'converted' && (
             <CardFooter className="border-t p-4 flex flex-col sm:flex-row justify-center gap-2 no-print">
                <Badge className="text-md p-2 bg-teal-100 text-teal-700 border-teal-300"><CheckCircle className="mr-2 h-5 w-5"/>All applicable items in this quotation have been converted.</Badge>
            </CardFooter>
         )}
      </Card>
    </div>
  );
}
