
// src/app/(main)/salesperson/quotations/create/page.tsx
'use client';
import QuotationForm from '@/components/salesperson/QuotationForm';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { FileSignature } from 'lucide-react';

export default function CreateQuotationPage() {
  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <FileSignature className="mr-2 h-7 w-7 text-primary" /> Create New Quotation
          </CardTitle>
          <CardDescription>
            Build a new quotation for a customer by adding products and specifying terms.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <QuotationForm />
        </CardContent>
      </Card>
    </div>
  );
}
