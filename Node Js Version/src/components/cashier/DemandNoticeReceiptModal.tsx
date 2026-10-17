// src/components/cashier/DemandNoticeReceiptModal.tsx

'use client';

import type { DemandNotice, PaymentDetail, PaymentMethod } from '@/types';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogClose } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Printer, X, Package, User, Phone, CalendarDays, FileText, Hash, DollarSign, Info } from 'lucide-react';
import { brandingConfig } from '@/config/branding';
import { format, parseISO, isValid } from 'date-fns';
import { Badge } from '@/components/ui/badge'; // Added Badge

interface DemandNoticeReceiptModalProps {
  demandNotice: DemandNotice | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function DemandNoticeReceiptModal({ demandNotice, isOpen, onClose }: DemandNoticeReceiptModalProps) {
  if (!demandNotice) return null;

  const totalAgreedAmount = demandNotice.agreedPrice * demandNotice.quantityRequested;
  const totalAdvancePaid = demandNotice.payments?.reduce((sum, p) => sum + p.amount, 0) || 0;
  const remainingAmountOnDN = totalAgreedAmount - totalAdvancePaid;
  const latestPayment = demandNotice.payments && demandNotice.payments.length > 0
                        ? demandNotice.payments[demandNotice.payments.length - 1]
                        : null;
  const dnStatusText = demandNotice.status.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());


  const handlePrint = () => {
    if (!demandNotice) return;

    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert("Popup blocked. Please allow popups for this site to print the receipt.");
      return;
    }

    const receiptDate = latestPayment && latestPayment.paymentDate && isValid(parseISO(latestPayment.paymentDate))
                        ? format(parseISO(latestPayment.paymentDate), "MMMM dd, yyyy HH:mm")
                        : format(new Date(), "MMMM dd, yyyy HH:mm");
    
    const expectedDate = isValid(parseISO(demandNotice.expectedAvailabilityDate)) 
                         ? format(parseISO(demandNotice.expectedAvailabilityDate), "MMMM dd, yyyy") 
                         : 'N/A';
    
    const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
    const logoUrl = `${baseUrl}${brandingConfig.logoPath}`;

    const paymentMethodTranslations: Record<PaymentMethod, string> = {
        cash: 'نقدي',
        card: 'بطاقة',
        bank_transfer: 'تحويل بنكي',
        advance_on_dn: 'دفعة مقدمة'
    };
    const getPaymentMethodLabel = (method: PaymentMethod) => {
        const englishLabel = method.replace(/_/g, ' ');
        const arabicLabel = paymentMethodTranslations[method] || '';
        return `<span class="capitalize">${englishLabel} Paid</span>${arabicLabel ? ` / ${arabicLabel}` : ''}`;
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
          <div class="section-title">Demand Notice Receipt / إيصال إشعار الطلب</div>
          <div class="info-grid">
              <p><span class="label">DN #:</span> ${demandNotice.id}</p>
              <p><span class="label">Date: / التاريخ:</span> ${receiptDate}</p>
              <p><span class="label">Sales Rep: / مندوب المبيعات:</span> ${demandNotice.salespersonName}</p>
              <p><span class="label">Status: / الحالة:</span> ${dnStatusText}</p>
              <p><span class="label">Expected By: / متوقع في:</span> ${expectedDate}</p>
          </div>
          <div style="border-top: 1px dashed #ccc; margin: 2mm 0;"></div>
          <div class="bill-to">
              <p><span class="label">Customer: / العميل:</span> ${demandNotice.customerContactNumber}</p>
          </div>
        </div>

        <div class="section">
          <div class="section-title">Requested Item / العنصر المطلوب</div>
          <div class="items-container">
            <div class="item-box">
              <div class="item-details">
                <span class="item-name">${demandNotice.productName}</span>
                <span class="item-sku">SKU: ${demandNotice.productSku}</span>
              </div>
              <div class="item-qty">Qty: ${demandNotice.quantityRequested}</div>
              <div class="item-total">OMR ${(demandNotice.agreedPrice * demandNotice.quantityRequested).toFixed(2)}</div>
            </div>
          </div>
        </div>

        <div class="section totals-section">
          <div class="section-title">Payment Summary / ملخص الدفع</div>
          <div class="total-row"><span>Total Agreed Value: / القيمة الإجمالية المتفق عليها:</span><span>OMR ${totalAgreedAmount.toFixed(2)}</span></div>
          <div style="border-top: 1px dashed #ccc; margin: 1.5mm 0;"></div>
          ${(demandNotice.payments || []).map(p => `<div class="total-row">${getPaymentMethodLabel(p.method)}:</span><span>OMR ${p.amount.toFixed(2)}</span></div>`).join('')}
          <div class="total-row balance-due"><span>Remaining Due: / الرصيد المتبقي:</span><span>OMR ${remainingAmountOnDN.toFixed(2)}</span></div>
        </div>
        
        <div class="section notes-section">
          <div class="section-title">Notes & Terms / ملاحظات وشروط</div>
          <ul class="notes-list">
            ${(brandingConfig.returnPolicyNotes || []).map(note => `<li>${note.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</li>`).join('')}
            <li>This is a Demand Notice, not a final sale. Availability is subject to stock.</li>
          </ul>
        </div>
        <div class="footer"><p>Thank you! / شكرا لك!</p></div>
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
          .total-row.balance-due { font-weight: bold; font-size: 10pt; border-top: 1px dashed #000; padding-top: 1mm; margin-top: 1mm; }
          
          .notes-section .section-title { text-align: left; border-bottom: none; padding-bottom: 0; }
          .notes-list { list-style-position: inside; padding-left: 1mm; margin-top: 1mm; font-size: 7pt;}
          .footer { text-align: center; margin-top: 4mm; font-size: 8pt; }
      </style>
    `;

    printWindow.document.write(`<html><head><title>Receipt ${demandNotice.id}</title>${printStyles}</head><body>${pageContent}</body></html>`);
    printWindow.document.close();
    setTimeout(() => {
      printWindow.print();
    }, 250);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-2xl p-0">
        <DialogHeader className="p-6 pb-0">
          <DialogTitle className="text-2xl flex items-center">
            <FileText className="mr-2 h-6 w-6 text-primary" /> Advance Payment Receipt
          </DialogTitle>
        </DialogHeader>
        <ScrollArea className="max-h-[70vh]">
          <div id="dn-receipt-display-content" className="p-6 text-sm">
            <div className="text-center mb-4">
              {brandingConfig.logoPath && (
                <img src={brandingConfig.logoPath} alt={`${brandingConfig.appName} Logo`} className="h-12 mx-auto mb-2" data-ai-hint="logo company" />
              )}
              <h2 className="text-lg font-semibold">{brandingConfig.companyNameForInvoice}</h2>
              <p className="text-xs">{brandingConfig.companyAddressForInvoice}</p>
              <p className="text-xs">Tel: {brandingConfig.companyPhoneForInvoice} {brandingConfig.companyWebsiteForInvoice ? `| ${brandingConfig.companyWebsiteForInvoice}` : ''}</p>
              <h3 className="text-md font-medium mt-2">Advance Payment Receipt</h3>
            </div>

            <div className="grid grid-cols-2 gap-2 mb-3 text-xs">
              <div>
                <p><span className="font-semibold">DN ID:</span> {demandNotice.id}</p>
                <p><span className="font-semibold">Customer:</span> {demandNotice.customerContactNumber}</p>
                <p className="mt-1">
                    <span className="font-semibold">Status:</span>{' '}
                    <Badge variant={demandNotice.status === 'fulfilled' || demandNotice.status === 'ready_for_collection' || demandNotice.status === 'full_stock_available' ? 'default' : 'secondary'}
                           className={
                             demandNotice.status === 'fulfilled' || demandNotice.status === 'ready_for_collection' || demandNotice.status === 'full_stock_available' ? 'bg-green-100 text-green-700' :
                             demandNotice.status === 'cancelled' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-700'
                           }
                    >
                        {dnStatusText}
                    </Badge>
                </p>
              </div>
              <div className="text-right">
                <p><span className="font-semibold">Salesperson:</span> {demandNotice.salespersonName}</p>
                <p><span className="font-semibold">Receipt Date:</span> {latestPayment && latestPayment.paymentDate && isValid(parseISO(latestPayment.paymentDate)) ? format(parseISO(latestPayment.paymentDate), "PPp") : format(new Date(), "PPp")}</p>
                <p><span className="font-semibold">Expected On:</span> {isValid(parseISO(demandNotice.expectedAvailabilityDate)) ? format(parseISO(demandNotice.expectedAvailabilityDate), "PP") : 'N/A'}</p>
              </div>
            </div>

            <Separator className="my-2" />

            <h4 className="font-semibold text-xs mb-1">Requested Product:</h4>
            <div className="p-2 border rounded-md bg-muted/20 text-xs mb-3">
                <p><span className="font-semibold">Name:</span> {demandNotice.productName}</p>
                <p><span className="font-semibold">Product Code:</span> {demandNotice.productSku}</p>
                <p><span className="font-semibold">Qty:</span> {demandNotice.quantityRequested} @ OMR {demandNotice.agreedPrice.toFixed(2)}/unit</p>
                <p className="font-semibold mt-1">Total Agreed: OMR {totalAgreedAmount.toFixed(2)}</p>
            </div>

            <h4 className="font-semibold text-xs mb-1">Advance Payments Received:</h4>
            {demandNotice.payments && demandNotice.payments.length > 0 ? (
              <div className="border rounded-md text-xs mb-3">
                <table className="w-full">
                    <thead className="bg-muted/30">
                        <tr className="border-b">
                        <th className="text-left p-1 font-medium">Date</th>
                        <th className="text-left p-1 font-medium">Method</th>
                        <th className="text-right p-1 font-medium">Amount</th>
                        </tr>
                    </thead>
                    <tbody>
                        {demandNotice.payments.map((payment, idx) => (
                        <tr key={`disp_payment_${idx}`} className={idx < demandNotice.payments.length -1 ? "border-b" : ""}>
                            <td className="p-1">{payment.paymentDate ? (isValid(parseISO(payment.paymentDate)) ? format(parseISO(payment.paymentDate), 'PP HH:mm') : 'N/A') : 'N/A'}</td>
                            <td className="p-1 capitalize">{payment.method.replace(/_/g, ' ')}</td>
                            <td className="text-right p-1">OMR {payment.amount.toFixed(2)}</td>
                        </tr>
                        ))}
                    </tbody>
                </table>
              </div>
            ) : (
              <p className="text-muted-foreground text-xs mb-3">No advance payments recorded yet.</p>
            )}

            <Separator className="my-2" />

            <div className="text-right space-y-0.5 text-xs">
              <p><span className="font-semibold">Total Agreed for DN:</span> OMR {totalAgreedAmount.toFixed(2)}</p>
              <p><span className="font-semibold">Total Advance Paid:</span> OMR {totalAdvancePaid.toFixed(2)}</p>
              <p className="font-bold text-base mt-1"><span className="font-semibold">Remaining on DN:</span> OMR {remainingAmountOnDN.toFixed(2)}</p>
            </div>

            <hr className="my-3 border-dashed border-gray-400" />
            <div className="text-xs">
                <h5 className="font-semibold mb-1">Return/Exchange Policy & Notes:</h5>
                <ul className="list-disc list-inside pl-2 space-y-0.5 text-muted-foreground" style={{fontSize: '8px'}}>
                   {(brandingConfig.returnPolicyNotes || []).map((note, idx) => `<li>${note.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</li>`).join('')}
                   <li>This is a Demand Notice, not a final sale. Availability is subject to stock.</li>
                </ul>
            </div>
            <hr className="mt-3 mb-2 border-dashed border-gray-400" />

            {remainingAmountOnDN <= 0 && demandNotice.status !== 'fulfilled' && demandNotice.status !== 'cancelled' && (
                <div className="mt-3 text-center">
                    <Badge variant="default" className="bg-green-100 text-green-700 p-1 text-xs">
                        <Info className="h-3 w-3 mr-1" /> This Demand Notice has been fully paid in advance.
                    </Badge>
                </div>
            )}
            <p className="text-center text-xs text-muted-foreground mt-4">
              Thank you! This confirms receipt of advance payment.
            </p>
          </div>
        </ScrollArea>
        <DialogFooter className="p-6 pt-0 border-t flex flex-row justify-between sm:justify-between no-print-in-modal">
          <Button variant="outline" onClick={onClose}>
            <X className="mr-2 h-4 w-4" /> Close
          </Button>
          <Button onClick={handlePrint} className="bg-primary hover:bg-primary/90 text-primary-foreground">
            <Printer className="mr-2 h-4 w-4" /> Print Receipt
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
