// src/app/(main)/auditor/audits/[auditId]/report/page.tsx
'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import type { Audit, AuditItem, AuditItemCount } from '@/types'; 
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Loader2, ArrowLeft, FileText, ShieldAlert, Image as ImageIcon, Video as VideoIcon, CheckCircle, AlertTriangle as WarningIcon, Info, Printer } from 'lucide-react';
import Image from 'next/image';
import { format, parseISO, isValid } from 'date-fns';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

export default function AuditorAuditReportPage() {
  const router = useRouter();
  const params = useParams();
  const auditId = params.auditId as string;

  const { getAuditById, currentUser, isDataLoaded, users, getProductById } = useApp();
  const [audit, setAudit] = useState<Audit | null | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchAuditDetails() {
      if (!auditId || !isDataLoaded) return;

      if (!currentUser || currentUser.role !== 'auditor') {
        router.replace('/login');
        return;
      }
      
      setIsLoading(true);
      const fetchedAudit = await getAuditById(auditId);
      
      if (fetchedAudit && fetchedAudit.auditorId === currentUser.id) {
        setAudit(fetchedAudit);
      } else if (fetchedAudit) {
        // Audit exists but not assigned to this auditor
        setAudit(null); 
        router.replace('/auditor/audits'); // Redirect to their list
      } else {
        setAudit(null); // Audit not found
      }
      setIsLoading(false);
    }
    fetchAuditDetails();
  }, [auditId, getAuditById, currentUser, isDataLoaded, router]);
  
  const getAdminUsername = (adminId?: string): string => {
    if (!adminId) return 'Unknown';
    const admin = users.find(u => u.id === adminId);
    return admin?.username || 'Unknown Admin';
  };
  
  const getStatusBadgeVariant = (status: Audit['status']) => {
    switch (status) {
      case 'pending': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'in_progress': return 'bg-blue-100 text-blue-700 border-blue-300';
      case 'completed': return 'bg-green-100 text-green-700 border-green-300';
      case 'cancelled': return 'bg-red-100 text-red-700 border-red-300';
      default: return 'bg-gray-100 text-gray-700 border-gray-300';
    }
  };

  if (isLoading || !isDataLoaded) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="ml-2 text-muted-foreground">Loading your audit report...</p>
      </div>
    );
  }

  if (audit === null) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Audit Report Not Found</h1>
        <p className="text-muted-foreground">
          The audit report (ID: {auditId}) does not exist or is not assigned to you.
        </p>
        <Button onClick={() => router.push('/auditor/audits')} className="mt-4">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to My Audits
        </Button>
      </div>
    );
  }
  
  if (audit === undefined) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="ml-2 text-muted-foreground">Initializing report...</p>
      </div>
    );
  }
  
  const totalSystemStockValue = audit.items?.reduce((sum, item) => sum + (item.currentStock * (getProductById(item.productId || '')?.price || 0)), 0) || 0;
  const totalAuditedValue = audit.items?.reduce((sum, item) => sum + ((item.finalAuditedQty ?? 0) * (getProductById(item.productId || '')?.price || 0)), 0) || 0;
  const varianceValue = totalAuditedValue - totalSystemStockValue;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <Button variant="outline" onClick={() => router.push('/auditor/audits')} className="print:hidden">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to My Audits
        </Button>
        <Button onClick={() => window.print()} className="print:hidden">
          <Printer className="mr-2 h-4 w-4" /> Print Report
        </Button>
      </div>
      <Card className="shadow-md printable-area">
        <CardHeader className="border-b pb-4">
           <div className="flex flex-col sm:flex-row justify-between items-start">
            <div>
              <img src="/assets/logo.svg" alt="Company Logo" className="h-12 mb-2 print:h-10" data-ai-hint="logo company"/>
              <h1 className="text-2xl font-bold text-primary print:text-xl">{audit.title} - Audit Report</h1>
            </div>
            <div className="text-left sm:text-right mt-4 sm:mt-0 print:text-xs">
              <p><strong>Audit ID:</strong> {audit.id}</p>
              <p><strong>Location:</strong> {audit.storeLocation}</p>
              <p><strong>Status:</strong> <Badge variant="outline" className={cn("capitalize print:text-xs", getStatusBadgeVariant(audit.status))}>{audit.status.replace(/_/g, ' ')}</Badge></p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6 text-sm print:text-xs print:gap-3">
            <div>
              <p><strong>Launched By Admin:</strong> {getAdminUsername(audit.adminId)}</p>
              <p><strong>Launched At:</strong> {audit.createdAt ? format(parseISO(audit.createdAt), 'PPpp') : 'N/A'}</p>
            </div>
            <div className="md:text-right">
              <p><strong>Auditor:</strong> {currentUser?.username}</p>
              <p><strong>Started At:</strong> {audit.startedAt ? format(parseISO(audit.startedAt), 'PPpp') : 'Not Started'}</p>
              <p><strong>Completed At:</strong> {audit.completedAt ? format(parseISO(audit.completedAt), 'PPpp') : (audit.status === 'in_progress' ? 'In Progress' : 'Not Completed')}</p>
            </div>
          </div>
          {audit.auditorSelfiePath && (
            <div className="mb-6">
              <h4 className="font-semibold mb-2 text-sm print:text-xs">My Start Verification Selfie:</h4>
              <Image 
                src={`/api/uploads/${audit.auditorSelfiePath}`} 
                alt="Auditor start selfie" 
                width={100} 
                height={100} 
                className="rounded-md shadow-md print:w-20 print:h-20" 
                data-ai-hint="selfie person"
                unoptimized={true}
                onError={(e) => { 
                  console.error(`Failed to load auditor selfie: /api/uploads/${audit.auditorSelfiePath}`);
                  e.currentTarget.style.display = 'none'; 
                  const parent = e.currentTarget.parentElement;
                  if (parent) {
                    const errorMsg = document.createElement('span');
                    errorMsg.textContent = '[Selfie Image Error]';
                    errorMsg.className = 'text-destructive text-xs';
                    parent.appendChild(errorMsg);
                  }
                }}
              />
            </div>
          )}
          <Separator className="my-6 print:my-3" />
          <h3 className="text-lg font-semibold mb-3 print:text-base">Audit Items Summary</h3>
          <Table className="print:text-xs">
            <TableHeader>
              <TableRow>
                <TableHead>Product Name (SKU)</TableHead>
                <TableHead className="text-center">System Stock</TableHead>
                <TableHead className="text-center">Audited Qty</TableHead>
                <TableHead className="text-center">Variance (Qty)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(audit.items || []).map(item => {
                const variance = (item.finalAuditedQty ?? 0) - item.currentStock;
                const varianceColor = variance < 0 ? 'text-red-600 print:text-red-600' : variance > 0 ? 'text-green-600 print:text-green-600' : 'text-muted-foreground print:text-gray-500';
                return (
                <TableRow key={item.id}>
                  <TableCell>
                    {item.productName}
                    <span className="block text-xs text-muted-foreground print:text-gray-500">({item.productSku || 'N/A'})</span>
                  </TableCell>
                  <TableCell className="text-center">{item.currentStock}</TableCell>
                  <TableCell className="text-center font-semibold">{item.finalAuditedQty ?? '-'}</TableCell>
                  <TableCell className={cn("text-center font-semibold", varianceColor)}>{variance > 0 ? `+${variance}` : variance < 0 ? variance : '-'}</TableCell>
                </TableRow>
              );})}
            </TableBody>
          </Table>
           <div className="mt-6 pt-4 border-t print:mt-3 print:pt-2">
            <h4 className="font-semibold text-md mb-2 print:text-sm">Overall Audit Value Summary (Based on Standard Price):</h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm print:text-xs">
                <p><strong>Total System Stock Value:</strong> OMR {totalSystemStockValue.toFixed(2)}</p>
                <p><strong>Total Audited Stock Value:</strong> OMR {totalAuditedValue.toFixed(2)}</p>
                <p className={cn("font-bold", varianceValue < 0 ? "text-red-600 print:text-red-600" : "text-green-600 print:text-green-600")}>
                    <strong>Value Variance:</strong> OMR {varianceValue.toFixed(2)}
                </p>
            </div>
          </div>
          <Separator className="my-6 print:my-3" />
          <h3 className="text-lg font-semibold mb-3 print:text-base">Detailed Item Counts & Media</h3>
          {(audit.items || []).length > 0 ? (
            <ScrollArea className="max-h-[500px] print:max-h-none print:overflow-visible">
              <div className="space-y-4">
                {(audit.items || []).map(item => (
                  <Card key={`detail-${item.id}`} className="bg-muted/30 print:border print:border-gray-300 print:shadow-none">
                    <CardHeader className="pb-2 pt-3 px-4">
                       <CardTitle className="text-md print:text-sm">{item.productName} <span className="text-xs font-normal text-muted-foreground print:text-gray-500">(SKU: {item.productSku || 'N/A'})</span></CardTitle>
                      <CardDescription className="text-xs print:text-xs">System Stock: {item.currentStock} | Final Audited: {item.finalAuditedQty ?? 'N/A'}</CardDescription>
                    </CardHeader>
                    <CardContent className="px-4 pb-3">
                      {(item.counts || []).length > 0 ? (
                        <ul className="space-y-2 text-xs print:text-xxs">
                          {(item.counts || []).map(count => (
                            <li key={count.id} className="p-2 border rounded-md bg-background print:border-gray-200">
                              <div className="flex justify-between items-center mb-1">
                                <span className="font-medium">Counted: {count.count}</span>
                                <span className="text-muted-foreground print:text-gray-500">{count.createdAt ? format(parseISO(count.createdAt), 'PPp') : 'N/A'}</span>
                              </div>
                              {count.notes && <p className="italic text-muted-foreground print:text-gray-500">Notes: {count.notes}</p>}
                              {(count.images || []).length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {(count.images || []).map(img => (
                                    <div key={img.id} className="relative print:w-16 print:h-16">
                                      {img.imagePath.match(/\.(jpeg|jpg|gif|png)$/i) ? (
                                        <Image 
                                          src={`/api/uploads/${img.imagePath}`} 
                                          alt={`Audit media for count ${count.id}`} 
                                          width={80} 
                                          height={80} 
                                          className="rounded object-cover print:w-16 print:h-16" 
                                          data-ai-hint="audit evidence"
                                          unoptimized={true}
                                          onError={(e) => { 
                                            console.error(`Failed to load audit item image: /api/uploads/${img.imagePath}`);
                                            e.currentTarget.style.display = 'none';
                                            const parent = e.currentTarget.parentElement;
                                            if (parent) {
                                              const errorMsg = document.createElement('span');
                                              errorMsg.textContent = '[Media Error]';
                                              errorMsg.className = 'text-destructive text-xs';
                                              parent.appendChild(errorMsg);
                                            }
                                          }}
                                        />
                                      ) : img.imagePath.match(/\.(mp4|webm|ogg)$/i) ? (
                                        <video src={`/api/uploads/${img.imagePath}`} width="120" height="90" controls className="rounded print:w-24 print:h-16" />
                                      ) : (
                                        <a href={`/api/uploads/${img.imagePath}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline print:text-blue-700">View Media File</a>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-xs text-muted-foreground print:text-gray-500">No specific counts recorded for this item during the audit process.</p>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </ScrollArea>
          ) : (
            <p className="text-muted-foreground print:text-gray-500">No items were defined for this audit.</p>
          )}
        </CardContent>
        <CardFooter className="border-t pt-4 text-xs text-muted-foreground print:text-xxs print:pt-2">
            Report Viewed: {format(new Date(), 'PPpp')} by {currentUser?.username}
        </CardFooter>
      </Card>
    </div>
  );
}
