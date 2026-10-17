
// src/app/(main)/salesperson/quotations/[quotationId]/edit/page.tsx
'use client';
import QuotationForm from '@/components/salesperson/QuotationForm';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Edit3, Loader2, AlertTriangle, ArrowLeft } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import { useParams, useRouter } from 'next/navigation';
import React, { useEffect, useState } from 'react';
import type { Quotation } from '@/types';
import { Button } from '@/components/ui/button';

export default function EditQuotationPage() {
  const router = useRouter();
  const params = useParams();
  const quotationId = params.quotationId as string;
  const { getQuotationById, currentUser, isDataLoaded } = useApp();
  const [quotation, setQuotation] = useState<Quotation | null | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchQuotation() {
      if (quotationId && currentUser?.id && isDataLoaded) {
        setIsLoading(true);
        const fetchedQuotation = await getQuotationById(quotationId);
        if (fetchedQuotation && (fetchedQuotation.status === 'draft' || fetchedQuotation.status === 'revision' || currentUser.role === 'admin' || currentUser.role === 'manager')) {
            setQuotation(fetchedQuotation);
        } else if (fetchedQuotation) {
            // Quotation found but not editable by this user/status
            console.warn(`User ${currentUser.username} (${currentUser.role}) attempted to edit quotation ${quotationId} with status ${fetchedQuotation.status}. Redirecting to view.`);
            router.replace(`/salesperson/quotations/${quotationId}/view`);
            setQuotation(null); // Indicate not found for editing specifically
        } else {
            setQuotation(null); // Not found at all
        }
        setIsLoading(false);
      } else if (isDataLoaded && !currentUser?.id) {
         router.replace('/login');
      }
    }
    fetchQuotation();
  }, [quotationId, getQuotationById, currentUser, isDataLoaded, router]);

  if (isLoading || !isDataLoaded) {
    return <div className="flex justify-center items-center h-64"><Loader2 className="h-8 w-8 animate-spin text-primary" /> <span className="ml-2">Loading quotation for editing...</span></div>;
  }

  if (quotation === null) { // Explicitly null means not found or not editable
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <AlertTriangle className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Quotation Not Found or Not Editable</h1>
        <p className="text-muted-foreground">The quotation you are trying to edit does not exist, or it's not in an editable state (e.g., draft or revision).</p>
        <Button onClick={() => router.push('/salesperson/quotations')} className="mt-4"><ArrowLeft className="mr-2 h-4 w-4" /> Back to Quotations</Button>
      </div>
    );
  }
  
  if (quotation === undefined) { // Still in initial loading state without a decision
     return <div className="flex justify-center items-center h-64"><Loader2 className="h-8 w-8 animate-spin text-primary" /> <span className="ml-2">Preparing editor...</span></div>;
  }

  return (
    <div className="space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <Edit3 className="mr-2 h-7 w-7 text-primary" /> Edit Quotation: {quotation.id}
          </CardTitle>
          <CardDescription>
            Modify the details of your existing quotation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <QuotationForm initialQuotation={quotation} />
        </CardContent>
      </Card>
    </div>
  );
}

    