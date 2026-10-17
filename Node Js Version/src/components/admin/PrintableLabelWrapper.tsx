// src/components/admin/PrintableLabelWrapper.tsx
'use client';

import React, { useEffect, useRef } from 'react';
import JsBarcode from 'jsbarcode';
import { brandingConfig } from '@/config/branding';

export interface ProductLabelItem {
  name: string;
  sku: string;
  price: string;
  expiryDate?: string;
}

export interface InvoiceIdLabelItem {
  id: string;
  type: 'Order' | 'Demand Notice';
  customerName?: string;
  customerAddress?: string;
}

export type LabelItem = ProductLabelItem | InvoiceIdLabelItem;

interface PrintableLabelWrapperProps {
  type: 'product' | 'invoiceId';
  items: LabelItem[];
  barcodeFormat?: 'CODE128' | 'EAN-13';
}

const BarcodeComponent = ({
  value,
  type,
  format = "CODE128",
  height = 25,
  width = 1.5
}: {
  value: string;
  type: 'product' | 'invoiceId';
  format?: string;
  height?: number;
  width?: number;
}) => {
  const ref = useRef<SVGSVGElement>(null); // Use SVGSVGElement for SVG
  useEffect(() => {
    if (ref.current) {
      try {
        JsBarcode(ref.current, value, {
          format: format,
          displayValue: false,
          height: height,
          width: width,
          margin: 0,
        });
      } catch (e) {
        console.error("Barcode generation failed for value:", value, e);
      }
    }
  }, [value, format, height, width]);

  // Use an svg element instead of img for crisp rendering
  return <svg className={type === 'product' ? "product-barcode" : "barcode"} ref={ref} />;
};


const PrintableLabelWrapper: React.FC<PrintableLabelWrapperProps> = ({ type, items, barcodeFormat = 'CODE128' }) => {
  
  if (type === 'product') {
    return (
      <div className="label-grid">
        {(items as ProductLabelItem[]).map((item, index) => (
          <div key={`product-label-${index}`} className="label-container product-label">
            <div className="product-name">{item.name}</div>
            
            <div className="product-barcode-container">
               <BarcodeComponent type="product" value={item.sku} format={barcodeFormat} height={20} width={1.2} />
            </div>
            
            <div className="price">OMR {item.price}</div>
          </div>
        ))}
      </div>
    );
  }

  if (type === 'invoiceId') {
    return (
      <div className="label-grid">
        {(items as InvoiceIdLabelItem[]).map((item, index) => (
          <div key={`invoice-id-label-${index}`} className="label-container">
             <div className="label-header">
                
             </div>
             
             <div className="from-to">
                 <div className="from">
                     <strong>From:</strong><br/>
                     {brandingConfig.companyNameForInvoice}<br/>
                     {brandingConfig.companyAddressForInvoice}
                 </div>
                 <div className="to">
                     <strong>To:</strong><br/>
                     {item.customerName || 'N/A'}<br/>
                     {item.customerAddress || 'N/A'}
                 </div>
             </div>
             
             <div className="fragile-section">
                <div className="tracking-code"></div>
             </div>
             
             <div className="barcode-container">
                 <BarcodeComponent type="invoiceId" value={item.id} format="CODE128" />
             </div>
             
             <div className="delivery-instructions">
                 May be opened officially
             </div>
             
             <div className="item-number">
                 {item.type} #: {item.id}
             </div>
          </div>
        ))}
      </div>
    );
  }

  return null;
};

export default PrintableLabelWrapper;
