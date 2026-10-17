// src/components/InvoiceModal.tsx

'use client';

import type { Order, PaymentDetail, ReturnTransactionInfo, PaymentMethod } from '@/types';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogClose } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Printer, X, AlertTriangle, Undo2, FileText as FileTextIcon } from 'lucide-react';
import { brandingConfig } from '@/config/branding';
import { format, parseISO, isValid } from 'date-fns';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useApp } from '@/context/AppContext';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { useMemo } from 'react';

interface InvoiceModalProps {
  order: Order | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function InvoiceModal({ order, isOpen, onClose }: InvoiceModalProps) {
  const { currentUser, hasPermission } = useApp();

  const paymentStatusText = useMemo(() => {
    if (!order) return 'N/A';
    const currentTotalPaid = (order.payments || []).reduce((sum, p) => sum + p.amount, 0);
    if (order.status === 'paid' || order.status === 'completed') return 'Paid in Full';
    if (order.status === 'returned') return 'Order Returned';
    if (order.status === 'cancelled') return 'Order Cancelled';
    if (order.status === 'partial_payment') return 'Partially Paid';
    if (currentTotalPaid > 0 && currentTotalPaid < order.totalAmount && order.status !== 'returned' && order.status !== 'cancelled') return 'Partially Paid';
    if (currentTotalPaid <= 0 && (order.status === 'pending_payment' || order.status === 'ready_for_pickup')) return 'Payment Pending';
    return order.status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
  }, [order]);

  if (!order) return null;

  const totalPaidOnOrder = (order.payments || []).reduce((sum, p) => sum + p.amount, 0);
  const remainingBalanceOnOrder = order.totalAmount - totalPaidOnOrder;
  const directOrderStatusText = order.status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());

  const handlePrint = () => {
    if (!order) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert("Popup blocked. Please allow popups for this site to print the invoice.");
      return;
    }

    const invoiceDate = isValid(parseISO(order.createdAt)) ? format(parseISO(order.createdAt), "dd/MM/yyyy HH:mm") : 'N/A';
    const orderStatusPrint = directOrderStatusText;
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const logoUrl = `${baseUrl}${brandingConfig.logoPath}`;

    const paymentMethodTranslations: Record<PaymentMethod, string> = {
      cash: 'نقدي',
      card: 'بطاقة',
      bank_transfer: 'تحويل بنكي',
      advance_on_dn: 'دفعة مقدمة'
    };

    const getPaymentMethodLabel = (method: PaymentMethod, context: 'paid' | 'refund') => {
        const englishLabel = method.replace(/_/g, ' ');
        const paidText = context === 'paid' ? 'Paid' : 'Refund via';
        const arabicText = context === 'paid' ? 'دفع' : 'استرداد عبر';
        const arabicLabel = paymentMethodTranslations[method] || '';
        return `<span class="capitalize">${paidText} ${englishLabel}</span>${arabicLabel ? ` / ${arabicText} ${arabicLabel}` : ''}`;
    };


    const generatePageHeaderHtml = () => `
      <div class="receipt-header">
          ${brandingConfig.logoPath ? `<img src="${logoUrl}" alt="Company Logo" class="logo" data-ai-hint="logo company"/>` : ''}
          <div class="company-name">${brandingConfig.companyNameForInvoice}</div>
          <div class="company-details">
              ${brandingConfig.companyAddressForInvoice}<br/>
              Tel: ${brandingConfig.companyPhoneForInvoice}
              ${brandingConfig.companyWebsiteForInvoice ? `<br/>${brandingConfig.companyWebsiteForInvoice}` : ''}
          </div>
      </div>
    `;
    
    const pageContent = `
        <div class="section">
          ${generatePageHeaderHtml()}
        </div>
        <div class="section">
          <div class="section-title">Invoice / فاتورة</div>
          <div class="info-grid">
              <p><span class="label">Invoice #:</span> ${order.id}</p>
              <p><span class="label">Date:</span> ${invoiceDate}</p>
              <p><span class="label">Sales Rep:</span> ${order.primarySalespersonName}</p>
              <p><span class="label">Status:</span> ${orderStatusPrint}</p>
          </div>
          <div style="border-top: 1px dashed #ccc; margin: 2mm 0;"></div>
          <div class="bill-to">
              <p><span class="label">Bill To: / فاتورة إلى:</span></p>
              <p>${order.customerName || 'N/A'}</p>
              <p>${order.customerPhone || ''}</p>
              <p>${order.deliveryAddress || ''}</p>
          </div>
        </div>

        <div class="section">
          <div class="section-title">Items / العناصر</div>
          <div class="items-container">
            ${(order.items || []).map(item => `
              <div class="item-box">
                <div class="item-details">
                  <span class="item-name">${item.name}</span>
                  <span class="item-sku">SKU: ${item.sku}</span>
                </div>
                <div class="item-qty">Qty: ${item.quantity}</div>
                <div class="item-total">OMR ${item.totalPrice.toFixed(2)}</div>
              </div>
            `).join('')}
          </div>
        </div>

        <div class="section totals-section">
          <div class="section-title">Summary / ملخص</div>
          <div class="total-row"><span>Subtotal: / المجموع الفرعي:</span><span>OMR ${order.subtotal.toFixed(2)}</span></div>
          ${order.discountAmount > 0 ? `<div class="total-row"><span>Discount: / الخصم:</span><span>-OMR ${order.discountAmount.toFixed(2)}</span></div>` : ''}
          ${order.taxes && order.taxes.length > 0 ? `<div class="total-row"><span>Tax: / الضريبة:</span><span>OMR ${(order.taxes.reduce((s, t) => s + t.amount, 0)).toFixed(2)}</span></div>` : ''}
          <div class="total-row grand-total"><span>Total Due: / المبلغ الإجمالي:</span><span>OMR ${order.totalAmount.toFixed(2)}</span></div>
          <div style="border-top: 1px dashed #ccc; margin: 1.5mm 0;"></div>
          ${(order.payments || []).map(p => `<div class="total-row">${getPaymentMethodLabel(p.method, 'paid')}:</span><span>OMR ${p.amount.toFixed(2)}</span></div>`).join('')}
          <div class="total-row balance-due"><span>Balance Due: / الرصيد المتبقي:</span><span>OMR ${remainingBalanceOnOrder.toFixed(2)}</span></div>
        </div>
        
        <div class="section notes-section">
          <div class="section-title">Notes & Terms</div>
          <ul class="notes-list">${(brandingConfig.returnPolicyNotes || []).map(note => `<li>${note.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</li>`).join('')}</ul>
        </div>
        <div class="footer"><p>Thank you for your business!</p></div>
    `;
    
    const printStyles = `
      <style>
          @page { size: 80mm; margin: 3mm; }
          * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'monospace', 'Courier New', Courier; color: #000; }
          body { width: 74mm; font-size: 8pt; line-height: 1.3; }
          .receipt-header { text-align: center; margin-bottom: 4mm; }
          .logo { max-height: 40px; max-width: 100%; margin-bottom: 2mm; }
          .company-name { font-size: 11pt; font-weight: bold; }
          .company-details { font-size: 7pt; line-height: 1.2; }
          
          .section { padding: 1.5mm; margin-bottom: 2mm; border-bottom: 1px dashed #999; }
          .section:last-of-type { border-bottom: none; }
          .section-title { font-weight: bold; text-transform: uppercase; margin-bottom: 1.5mm; font-size: 9pt; text-align: center; border-bottom: 1px solid #000; padding-bottom: 1mm; }
          
          .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1mm 3mm; font-size: 7.5pt; }
          .info-grid p, .bill-to p { margin: 0; }
          .label { font-weight: bold; }
          .bill-to { font-size: 8pt; margin-top: 2mm; }

          .items-container { display: flex; flex-direction: column; gap: 0; margin-top: 1mm; }
          .item-box { display: flex; justify-content: space-between; align-items: center; padding: 1.5mm 0; border-bottom: 1px dotted #ccc; }
          .item-box:last-child { border-bottom: none; }
          .item-box .item-details { flex-grow: 1; display: flex; flex-direction: column; padding-right: 1mm; }
          .item-box .item-name { font-weight: bold; font-size: 8pt; }
          .item-box .item-sku { font-size: 7pt; color: #555; }
          .item-box .item-qty { width: 15%; text-align: center; font-size: 8pt; flex-shrink: 0; }
          .item-box .item-total { width: 25%; text-align: right; font-weight: bold; font-size: 8pt; flex-shrink: 0; }

          .totals-section .section-title { margin-bottom: 2mm; }
          .total-row { display: flex; justify-content: space-between; padding: 0.5mm 0; font-size: 8.5pt; }
          .total-row.grand-total { font-weight: bold; font-size: 11pt; border-top: 1px solid #000; padding-top: 1mm; margin-top: 1mm; }
          .total-row.balance-due { font-weight: bold; font-size: 10pt; border-top: 1px dashed #000; padding-top: 1mm; margin-top: 1mm; }

          .notes-section .section-title { text-align: left; border-bottom: none; padding-bottom: 0; }
          .notes-list { list-style-position: inside; padding-left: 1mm; margin-top: 1mm; font-size: 7pt;}
          .footer { text-align: center; margin-top: 4mm; font-size: 8pt; }
      </style>
    `;
    
    printWindow.document.write(`<html><head><title>Invoice ${order.id}</title>${printStyles}</head><body>${pageContent}</body></html>`);
    printWindow.document.close();
    setTimeout(() => {
      printWindow.print();
    }, 250);
  };
  
  const handlePrintReturnSlip = (returnTx: ReturnTransactionInfo) => {
    if (!order || !returnTx) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert("Popup blocked. Please allow popups for this site to print the return slip.");
      return;
    }

    const returnDate = isValid(parseISO(returnTx.returnedAt)) ? format(parseISO(returnTx.returnedAt), "dd/MM/yyyy HH:mm") : 'N/A';
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const logoUrl = `${baseUrl}${brandingConfig.logoPath}`;

    const paymentMethodTranslations: Record<PaymentMethod, string> = {
        cash: 'نقدي',
        card: 'بطاقة',
        bank_transfer: 'تحويل بنكي',
        advance_on_dn: 'دفعة مقدمة'
    };
    const getPaymentMethodLabel = (method: PaymentMethod, context: 'paid' | 'refund') => {
        const englishLabel = method.replace(/_/g, ' ');
        const arabicLabel = paymentMethodTranslations[method] || '';
        const paidText = context === 'paid' ? 'Paid' : 'Refund via';
        return `<span class="capitalize">${paidText} ${englishLabel}</span>${arabicLabel ? ` / ${arabicLabel}` : ''}`;
    };

    const generatePageHeaderHtml = () => `
      <div class="receipt-header">
          ${brandingConfig.logoPath ? `<img src="${logoUrl}" alt="Company Logo" class="logo" data-ai-hint="logo company"/>` : ''}
          <div class="company-name">${brandingConfig.companyNameForInvoice}</div>
          <div class="company-details">
              ${brandingConfig.companyAddressForInvoice}<br/>
              Tel: ${brandingConfig.companyPhoneForInvoice}
              ${brandingConfig.companyWebsiteForInvoice ? `<br/>${brandingConfig.companyWebsiteForInvoice}` : ''}
          </div>
      </div>
    `;

    const pageContent = `
        <div class="section">
          ${generatePageHeaderHtml()}
        </div>
        <div class="section">
          <div class="section-title">Return / Exchange Slip</div>
          <div class="info-grid">
              <p><span class="label">Return ID:</span> ${returnTx.id}</p>
              <p><span class="label">Date:</span> ${returnDate}</p>
              <p><span class="label">Original Invoice:</span> ${order.id}</p>
              <p><span class="label">Processed By:</span> ${returnTx.processedByUsername}</p>
          </div>
          <div style="border-top: 1px dashed #ccc; margin: 2mm 0;"></div>
          <div class="bill-to">
              <p><span class="label">Customer:</span></p>
              <p>${order.customerName || 'N/A'} (${order.customerPhone || ''})</p>
          </div>
        </div>

        <div class="section">
          <div class="section-title">Items Returned</div>
          <div class="items-container">
            ${(returnTx.itemsReturned || []).map(item => `
              <div class="item-box">
                <div class="item-details">
                  <span class="item-name">${item.name}</span>
                  <span class="item-sku">SKU: ${item.sku}</span>
                </div>
                <div class="item-qty">Qty: ${item.quantityToReturn}</div>
                <div class="item-total">OMR ${item.totalPrice.toFixed(2)}</div>
              </div>
            `).join('')}
          </div>
        </div>

        <div class="section totals-section">
          <div class="section-title">Return Summary / ملخص</div>
          <div class="total-row"><span>Total Value of Returned Items:</span><span>OMR ${returnTx.totalValueOfReturnedItems.toFixed(2)}</span></div>
          <div style="border-top: 1px dashed #ccc; margin: 1.5mm 0;"></div>
          ${(returnTx.refundPaymentDetails || []).map(p => `<div class="total-row">${getPaymentMethodLabel(p.method, 'refund')}:</span><span>OMR ${p.amount.toFixed(2)}</span></div>`).join('')}
          <div class="total-row grand-total"><span>Total Refunded:</span><span>OMR ${returnTx.netRefundAmount.toFixed(2)}</span></div>
        </div>
        
        ${returnTx.notesOnExchange ? `
        <div class="section notes-section">
          <div class="section-title">Exchange Notes</div>
          <p class="notes-content" style="white-space: pre-wrap;">${returnTx.notesOnExchange.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</p>
        </div>` : ''}

        <div class="section notes-section">
          <div class="section-title">Notes & Terms</div>
          <ul class="notes-list">${(brandingConfig.returnPolicyNotes || []).map(note => `<li>${note.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</li>`).join('')}</ul>
        </div>
        <div class="footer"><p>Thank you!</p></div>
    `;

    const printStyles = `
      <style>
          @page { size: 80mm; margin: 3mm; }
          * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'monospace', 'Courier New', Courier; color: #000; }
          body { width: 74mm; font-size: 8pt; line-height: 1.3; }
          .receipt-header { text-align: center; margin-bottom: 4mm; }
          .logo { max-height: 40px; max-width: 100%; margin-bottom: 2mm; }
          .company-name { font-size: 11pt; font-weight: bold; }
          .company-details { font-size: 7pt; line-height: 1.2; }
          
          .section { padding: 1.5mm; margin-bottom: 2mm; border-bottom: 1px dashed #999; }
          .section:last-of-type { border-bottom: none; }
          .section-title { font-weight: bold; text-transform: uppercase; margin-bottom: 1.5mm; font-size: 9pt; text-align: center; border-bottom: 1px solid #000; padding-bottom: 1mm; }
          
          .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1mm 3mm; font-size: 7.5pt; }
          .info-grid p, .bill-to p { margin: 0; }
          .label { font-weight: bold; }
          .bill-to { font-size: 8pt; margin-top: 2mm; }

          .items-container { display: flex; flex-direction: column; gap: 0; margin-top: 1mm; }
          .item-box { display: flex; justify-content: space-between; align-items: center; padding: 1.5mm 0; border-bottom: 1px dotted #ccc; }
          .item-box:last-child { border-bottom: none; }
          .item-box .item-details { flex-grow: 1; display: flex; flex-direction: column; padding-right: 1mm; }
          .item-box .item-name { font-weight: bold; font-size: 8pt; }
          .item-box .item-sku { font-size: 7pt; color: #555; }
          .item-box .item-qty { width: 15%; text-align: center; font-size: 8pt; flex-shrink: 0; }
          .item-box .item-total { width: 25%; text-align: right; font-weight: bold; font-size: 8pt; flex-shrink: 0; }

          .totals-section .section-title { margin-bottom: 2mm; }
          .total-row { display: flex; justify-content: space-between; padding: 0.5mm 0; font-size: 8.5pt; }
          .total-row.grand-total { font-weight: bold; font-size: 11pt; border-top: 1px solid #000; padding-top: 1mm; margin-top: 1mm; }
          .total-row.balance-due { font-weight: bold; font-size: 10pt; border-top: 1px dashed #000; padding-top: 1mm; margin-top: 1mm; }

          .notes-section .section-title { text-align: left; border-bottom: none; padding-bottom: 0; }
          .notes-section .notes-content { white-space: pre-wrap; font-size: 7pt; }
          .notes-list { list-style-position: inside; padding-left: 1mm; margin-top: 1mm; font-size: 7pt;}
          .footer { text-align: center; margin-top: 4mm; font-size: 8pt; }
      </style>
    `;
    
    printWindow.document.write(`<html><head><title>Return Slip - ${returnTx.id}</title>${printStyles}</head><body>${pageContent}</body></html>`);
    printWindow.document.close();
    setTimeout(() => {
      printWindow.print();
    }, 250);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-4xl p-0">
        <DialogHeader className="p-6 pb-0">
          <DialogTitle className="text-2xl">Order Invoice - {order.id}</DialogTitle>
        </DialogHeader>
        <ScrollArea className="max-h-[80vh]">
          <div id="invoice-content-for-display" className="p-6 text-sm">
            
            <div className="text-center mb-6">
              <h2 className="text-xl font-bold header-main">{brandingConfig.companyNameForInvoice}</h2>
              <p>Sales Invoice</p>
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <p><span className="font-semibold">Invoice No:</span> <span data-invoice-id>{order.id}</span></p>
                <p><span className="font-semibold">Date:</span> {isValid(parseISO(order.createdAt)) ? format(parseISO(order.createdAt), "MM/dd/yyyy HH:mm:ss") : 'N/A'}</p>
              </div>
              <div className="text-right">
                <p><span className="font-semibold">Salesperson:</span> {order.primarySalespersonName}</p>
                 {order.secondarySalespersonName && <p><span className="font-semibold">Assisted by:</span> {order.secondarySalespersonName}</p>}
                 <div className="mt-1"> 
                   <span className="font-semibold">Order Status:</span>{' '}
                   <Badge
                     variant={ order.status === 'paid' || order.status === 'completed' ? 'default' : 'secondary' }
                     className={cn(
                       (order.status === 'paid' || order.status === 'completed') && 'bg-green-100 text-green-700',
                       order.status === 'returned' && 'bg-orange-100 text-orange-700',
                       order.status === 'cancelled' && 'bg-red-100 text-red-700',
                       order.status === 'partial_payment' && 'bg-yellow-100 text-yellow-700',
                       !(order.status === 'paid' || order.status === 'completed' || order.status === 'returned' || order.status === 'cancelled' || order.status === 'partial_payment') && 'bg-gray-100 text-gray-700'
                     )}
                   >
                     {directOrderStatusText}
                   </Badge>
                 </div>
              </div>
            </div>
            <Separator className="my-4" />
            <h3 className="font-semibold mb-2">Items:</h3>
            <table className="w-full mb-4 text-xs">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-1">Product</th>
                  <th className="text-center py-1">Qty</th>
                  <th className="text-right py-1">Price</th>
                  <th className="text-right py-1">Total</th>
                </tr>
              </thead>
              <tbody>
                {(order.items || []).map((item) => (
                  <tr key={item.productId + item.sku} className="border-b">
                    <td className="py-1">{item.name}</td>
                    <td className="text-center py-1">{item.quantity}</td>
                    <td className="text-right py-1">OMR {item.pricePerUnit.toFixed(2)}</td>
                    <td className="text-right py-1">OMR {item.totalPrice.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Separator className="my-4" />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 totals-section">
              <div>
                <h3 className="font-semibold mb-2">Payment Details:</h3>
                {(order.payments || []).map((p, idx) => (
                  <p key={idx} className="capitalize">
                    {p.method.replace(/_/g, ' ')}: OMR {p.amount.toFixed(2)}
                    {p.transactionId && ` (Ref: ${p.transactionId})`}
                    {p.paymentDate && ` on ${isValid(parseISO(p.paymentDate)) ? format(parseISO(p.paymentDate), 'MM/dd/yyyy p') : 'Invalid Date'}`}
                  </p>
                ))}
                 {(!order.payments || order.payments.length === 0) && <p className="text-muted-foreground">No payments recorded yet.</p>}
              </div>
              <div className="text-right">
                <p><span className="font-semibold">Subtotal:</span> OMR {order.subtotal.toFixed(2)}</p>
                {order.discountAmount > 0 && (
                  <p><span className="font-semibold">Discount {order.appliedDiscountPercentage ? `(${order.appliedDiscountPercentage.toFixed(2)}%)` : order.appliedGlobalDiscountPercentage ? `(${order.appliedGlobalDiscountPercentage}%)` : ''}:</span> -OMR {order.discountAmount.toFixed(2)}</p>
                )}
                {(order.taxes || []).map(tax => (
                  <p key={tax.name}><span className="font-semibold">{tax.name} ({(tax.rate * 100).toFixed(0)}%):</span> OMR {tax.amount.toFixed(2)}</p>
                ))}
                <p className="font-bold text-lg mt-1"><span className="font-semibold">Total Amount Due:</span> OMR {order.totalAmount.toFixed(2)}</p>
                <p className="font-semibold text-md mt-1"><span className="font-semibold">Total Paid:</span> OMR {totalPaidOnOrder.toFixed(2)}</p>
                {remainingBalanceOnOrder > 0.01 && (
                  <p className="font-bold text-destructive text-md mt-1"><span className="font-semibold">Remaining Balance:</span> OMR {remainingBalanceOnOrder.toFixed(2)}</p>
                )}
              </div>
            </div>
            {remainingBalanceOnOrder > 0.01 && order.status !== 'cancelled' && order.status !== 'returned' && (
                <Alert variant="default" className="mt-4 bg-yellow-50 border-yellow-300 text-yellow-700">
                    <AlertTriangle className="h-5 w-5 text-yellow-600" />
                    <AlertTitle className="text-yellow-800">Pending Balance</AlertTitle>
                    <AlertDescription className="text-yellow-700">
                        This order has a remaining balance of OMR {remainingBalanceOnOrder.toFixed(2)}.
                        {order.payments && order.payments.length > 0 && ` ${order.payments.length} partial payment(s) recorded.`}
                    </AlertDescription>
                </Alert>
            )}
            {order.returnTransactions && order.returnTransactions.length > 0 && (
              <div className="mt-6 pt-4 border-t border-dashed return-section">
                <h3 className="font-semibold text-destructive mb-2 flex items-center">
                  <Undo2 className="mr-2 h-5 w-5" /> Return History
                </h3>
                {(order.returnTransactions || []).map((rt, index) => (
                  <div key={rt.id} className="mb-3 pb-2 border-b border-dotted text-xs return-transaction-block-display">
                    <div className="flex justify-between items-center mb-2">
                        <h4 className="font-medium text-sm return-transaction-header-display">Return Transaction #{index + 1}</h4>
                        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handlePrintReturnSlip(rt)}>
                          <Printer className="mr-1.5 h-3 w-3" /> Print Slip
                        </Button>
                    </div>
                    <p><strong>Processed by:</strong> {rt.processedByUsername} on {isValid(parseISO(rt.returnedAt)) ? format(parseISO(rt.returnedAt), 'MM/dd/yyyy p') : 'N/A'}</p>
                    {rt.returnReasonGeneral && <p><strong>Reason:</strong> {rt.returnReasonGeneral}</p>}
                    {rt.notesOnExchange && <p><strong>Exchange Notes:</strong> {rt.notesOnExchange}</p>}
                    <table className="w-full my-2 text-xs returned-items-table-display">
                        <thead><tr className="border-b"><th className="text-left py-1">#</th><th className="text-left py-1">Returned Product</th><th className="text-left py-1">SKU</th><th className="text-center py-1">Qty Ret.</th><th className="text-right py-1">Unit Price</th><th className="text-right py-1">Value</th></tr></thead>
                        <tbody>{rt.itemsReturned.map((item, itemIdx) => ( <tr key={`${rt.id}-${item.productId}-${itemIdx}`} className="border-b"><td className="py-1">{itemIdx + 1}</td><td className="py-1">{item.name}</td><td className="py-1">{item.sku}</td><td className="text-center py-1">{item.quantityToReturn}</td><td className="text-right py-1">OMR {item.pricePerUnit.toFixed(2)}</td><td className="text-right py-1">OMR {(item.pricePerUnit * item.quantityToReturn).toFixed(2)}</td></tr>))}</tbody>
                    </table>
                  </div>
                ))}
                {(() => { const grandTotalOfAllReturnedItems = (order.returnTransactions || []).reduce((sum, rt) => sum + rt.totalValueOfReturnedItems, 0); if (grandTotalOfAllReturnedItems > 0) { return ( <div className="mt-4 pt-2 border-t-2 border-black totals-section return-grand-total-section-display"><p className="font-bold text-md text-right"><span className="font-semibold">TOTAL VALUE OF ALL RETURNED ITEMS:</span> OMR {grandTotalOfAllReturnedItems.toFixed(2)}</p></div>); } return null; })()}
              </div>
            )}
            <Separator className="my-4" />
            <div className="notes-section-display" style={{fontSize: '8px', marginTop: '0.1in', paddingTop: '0.05in', borderTop: '1px dashed #ccc'}}>
                <h5 className="font-semibold mb-1" style={{fontSize: '9px'}}>Return/Exchange Policy & Notes:</h5>
                <ul className="list-disc list-inside pl-2 space-y-0.5 text-muted-foreground" style={{fontSize: '8px'}}>
                  {(brandingConfig.returnPolicyNotes || []).map((note, idx) => `<li>${note.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</li>`).join('')}
                </ul>
            </div>
            <Separator className="my-4" />
            <p className="text-center text-xs text-muted-foreground">Thank you for your purchase!</p>
            <p className="text-center text-xs font-bold mt-1">Payment Status: {paymentStatusText}</p>
          </div>
        </ScrollArea>
        <DialogFooter className="p-6 pt-0 border-t flex flex-col sm:flex-row justify-between items-center gap-2 no-print-in-modal">
          <Button variant="outline" onClick={onClose} className="w-full sm:w-auto"><X className="mr-2 h-4 w-4" /> Close</Button>
          <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
            <Button onClick={handlePrint} className="w-full sm:w-auto bg-primary hover:bg-primary/90 text-primary-foreground"><Printer className="mr-2 h-4 w-4" /> Print Main Invoice</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
