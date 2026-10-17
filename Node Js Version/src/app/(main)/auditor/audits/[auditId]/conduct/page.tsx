// src/app/(main)/auditor/audits/[auditId]/conduct/page.tsx
'use client';

import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useApp } from '@/context/AppContext';
import type { Audit, AuditItem, AuditItemCount } from '@/types';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { Button, buttonVariants } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Loader2, ArrowLeft, AlertTriangle, PlayCircle, ShieldAlert, Camera, VideoOff, CheckCircle, Package, Info, Edit3, List, PlusCircle, ImagePlus, XCircle, Video, ClipboardCheck } from 'lucide-react';
import Image from 'next/image';
import { useToast } from '@/hooks/use-toast';
import { Spinner } from '@/components/ui/spinner';
import { Alert, AlertDescription as UIDescription, AlertTitle as UITitle } from '@/components/ui/alert';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { format, parseISO } from 'date-fns';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import AuditorSelfie from '@/components/audit/AuditorSelfie';
import EvidenceCapture from '@/components/audit/EvidenceCapture';

interface ItemCountInputState {
  [itemId: string]: {
    quantity: string;
    notes: string;
    mediaFile?: File | null;
    mediaPreviewUrl?: string | null;
    mediaType?: 'image' | 'video' | null;
  };
}

export default function ConductAuditPage() {
  const router = useRouter();
  const params = useParams();
  const auditId = params.auditId as string;
  const { toast } = useToast();

  const { getAuditById, currentUser, isDataLoaded, startAudit, recordAuditItemCountWithImage, completeAudit } = useApp();
  const [audit, setAudit] = useState<Audit | null | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [isProcessingStart, setIsProcessingStart] = useState(false);
  const [isSavingCount, setIsSavingCount] = useState<string | null>(null);
  const [isCompletingAudit, setIsCompletingAudit] = useState(false);
  const [itemCountInputs, setItemCountInputs] = useState<ItemCountInputState>({});
  const [capturedSelfieFile, setCapturedSelfieFile] = useState<File | null>(null);


  const fetchAndSetAudit = useCallback(async () => {
    if (!auditId || !isDataLoaded || !currentUser) return;
    setIsLoading(true);
    const fetchedAudit = await getAuditById(auditId);
    if (fetchedAudit && fetchedAudit.auditorId === currentUser.id) {
      if (fetchedAudit.status === 'completed' || fetchedAudit.status === 'cancelled') {
        router.replace(`/auditor/audits/${auditId}/report`);
        setAudit(null);
      } else {
        setAudit(fetchedAudit);
        if (fetchedAudit.items) {
          const initialInputs: ItemCountInputState = {};
          fetchedAudit.items.forEach(item => {
            initialInputs[item.id] = { quantity: '', notes: '', mediaFile: null, mediaPreviewUrl: null, mediaType: null };
          });
          setItemCountInputs(initialInputs);
        }
      }
    } else {
      setAudit(null);
      if (fetchedAudit) {
          toast({ title: "Access Denied", description: "You are not assigned to this audit.", variant: "destructive"});
          router.replace('/auditor/audits');
      }
    }
    setIsLoading(false);
  }, [auditId, getAuditById, currentUser, isDataLoaded, router, toast]);

  useEffect(() => {
    fetchAndSetAudit();
  }, [fetchAndSetAudit]);

  const handleSelfieFileCaptured = (selfieFile: File | null) => {
    setCapturedSelfieFile(selfieFile);
  };

  const handleStartAuditWithSelfie = async () => {
    if (!audit || !capturedSelfieFile || !currentUser) {
      toast({ title: "Error", description: "Audit details or selfie file missing.", variant: "destructive"});
      return;
    }
    setIsProcessingStart(true);
    const updatedAudit = await startAudit(audit.id, capturedSelfieFile);
    setIsProcessingStart(false);
    if (updatedAudit) {
      toast({ title: "Audit Started", description: `Audit ${updatedAudit.id} is now in progress.`, className: "bg-accent text-accent-foreground" });
      setAudit(updatedAudit);
      setCapturedSelfieFile(null); // Clear after successful submission
    } else {
      // Error toast handled by AppContext or startAudit function
      setCapturedSelfieFile(null); // Clear even on failure to allow retake
    }
  };


  const handleItemCountInputChange = (itemId: string, field: 'quantity' | 'notes', value: string) => {
    setItemCountInputs(prev => ({
      ...prev,
      [itemId]: {
        ...(prev[itemId] || { quantity: '', notes: '', mediaFile: null, mediaPreviewUrl: null, mediaType: null }),
        [field]: value,
      },
    }));
  };

  const handleEvidenceCaptured = (itemId: string, file: File, type: 'image' | 'video') => {
     setItemCountInputs(prev => {
      const currentItemInput = prev[itemId] || { quantity: '', notes: '' };
      if (currentItemInput.mediaPreviewUrl) {
        URL.revokeObjectURL(currentItemInput.mediaPreviewUrl);
      }
      return {
        ...prev,
        [itemId]: {
          ...currentItemInput,
          mediaFile: file,
          mediaPreviewUrl: URL.createObjectURL(file),
          mediaType: type,
        },
      };
    });
  };

  const handleRemoveMedia = (itemId: string) => {
    setItemCountInputs(prev => {
      const currentItemInput = prev[itemId];
      if (currentItemInput?.mediaPreviewUrl) {
        URL.revokeObjectURL(currentItemInput.mediaPreviewUrl);
      }
      return {
        ...prev,
        [itemId]: {
          ...(currentItemInput || { quantity: '', notes: '' }),
          mediaFile: null,
          mediaPreviewUrl: null,
          mediaType: null,
        },
      };
    });
  };


  const handleSaveItemCount = async (auditItemId: string) => {
    if (!audit) return;
    const currentInput = itemCountInputs[auditItemId];
    if (!currentInput || !currentInput.quantity.trim()) {
      toast({ title: "Missing Quantity", description: "Please enter a quantity for this count.", variant: "destructive" });
      return;
    }
    const quantity = parseInt(currentInput.quantity, 10);
    if (isNaN(quantity) || quantity < 0) {
      toast({ title: "Invalid Quantity", description: "Quantity must be a non-negative number.", variant: "destructive" });
      return;
    }

    setIsSavingCount(auditItemId);
    const newCount = await recordAuditItemCountWithImage(
      audit.id,
      auditItemId,
      quantity,
      currentInput.notes || undefined,
      currentInput.mediaFile || undefined
    );
    setIsSavingCount(null);

    if (newCount) {
      toast({ title: "Count Recorded", description: `Count for item recorded: ${quantity}.`, className: "bg-accent text-accent-foreground"});
      setItemCountInputs(prev => ({
        ...prev,
        [auditItemId]: { quantity: '', notes: '', mediaFile: null, mediaPreviewUrl: null, mediaType: null },
      }));
      await fetchAndSetAudit(); // Refresh audit data to show new count
    }
  };


  const handleFinalizeAudit = async () => {
    if (!audit || !currentUser) return;
    setIsCompletingAudit(true);
    const updatedAudit = await completeAudit(audit.id);
    setIsCompletingAudit(false);
    if (updatedAudit && updatedAudit.status === 'completed') {
      toast({ title: "Audit Completed!", description: `Audit ${audit.id} has been finalized.`, className: "bg-accent text-accent-foreground", duration: 5000 });
      router.push(`/auditor/audits/${audit.id}/report`);
    } else {
      toast({ title: "Error", description: "Failed to complete the audit. Please try again.", variant: "destructive" });
      await fetchAndSetAudit(); // Refresh to get latest state if completion failed
    }
  };


  if (isLoading || !isDataLoaded) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="ml-2 text-muted-foreground">Loading audit...</p>
      </div>
    );
  }

  if (!audit) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-center">
        <AlertTriangle className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Audit Not Found or Inaccessible</h1>
        <p className="text-muted-foreground">The audit (ID: ${auditId}) could not be loaded, may not be assigned to you, or is already completed/cancelled.</p>
        <Button onClick={() => router.push('/auditor/audits')} className="mt-4">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to My Audits
        </Button>
      </div>
    );
  }

  if (currentUser?.role !== 'auditor') {
     return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">Only auditors can conduct audits.</p>
        <Button onClick={() => router.push('/login')} className="mt-4"><ArrowLeft className="mr-2 h-4 w-4" /> Back to Login</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="outline" onClick={() => router.push('/auditor/audits')} className="print:hidden">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to My Audits
      </Button>
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <PlayCircle className="mr-2 h-7 w-7 text-primary" /> Conduct Audit: {audit.title}
          </CardTitle>
          <CardDescription>
            Audit ID: {audit.id} | Location: {audit.storeLocation} | Status: <span className="capitalize font-semibold">{audit.status.replace(/_/g, ' ')}</span>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {audit.status === 'pending' && (
            <>
              <AuditorSelfie
                onSelfieCaptured={handleSelfieFileCaptured}
                isProcessingStart={isProcessingStart}
              />
              {capturedSelfieFile && (
                <Button
                  onClick={handleStartAuditWithSelfie}
                  disabled={isProcessingStart || !capturedSelfieFile}
                  className="w-full mt-4 bg-green-600 hover:bg-green-700"
                >
                  {isProcessingStart ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : <CheckCircle className="mr-2 h-4 w-4"/>}
                  Confirm Selfie & Start Audit
                </Button>
              )}
            </>
          )}


          {audit.status === 'in_progress' && (
            <div className="space-y-6">
              {audit.auditorSelfiePath && (
                <div className="mb-4 p-3 border rounded-md bg-green-50">
                  <p className="text-sm font-medium text-green-700 flex items-center"><CheckCircle className="mr-2 h-4 w-4"/>Audit started successfully at {audit.startedAt ? new Date(audit.startedAt).toLocaleString() : 'N/A'}.</p>
                  <Image 
                    src={`/api/uploads/${audit.auditorSelfiePath}`} 
                    alt="Auditor start selfie" 
                    width={100} height={100} 
                    className="mt-2 rounded-md shadow" 
                    data-ai-hint="selfie person" 
                    unoptimized={true}
                    onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/100x100.png'; (e.target as HTMLImageElement).srcset = ''; }}
                  />
                </div>
              )}
              <Card>
                <CardHeader>
                    <CardTitle className="text-lg flex items-center"><Package className="mr-2 h-5 w-5 text-primary"/>Step 2: Audit Items & Counts</CardTitle>
                    <CardDescription>Record counts for each item. Add notes or attach media (photo/video) for discrepancies if needed.</CardDescription>
                </CardHeader>
                <CardContent>
                    {(!audit.items || audit.items.length === 0) ? (
                        <Alert variant="default" className="bg-yellow-50 border-yellow-300 text-yellow-700">
                            <Info className="h-5 w-5 text-yellow-600" />
                            <UITitle className="text-yellow-800">No Items Defined</UITitle>
                            <UIDescription className="text-yellow-700">
                            This audit has no items defined by the administrator.
                            </UIDescription>
                        </Alert>
                    ) : (
                    <ScrollArea className="h-[60vh] pr-2">
                        <div className="space-y-4">
                        {audit.items.map((item) => (
                            <Card key={item.id} className="shadow-sm">
                                <CardHeader className="pb-3 pt-4 px-4">
                                    <div className="flex justify-between items-start">
                                        <div>
                                            <CardTitle className="text-md">{item.productName}</CardTitle>
                                            <CardDescription className="text-xs">SKU: {item.productSku || 'N/A'} | System Stock: {item.currentStock}</CardDescription>
                                        </div>
                                    </div>
                                </CardHeader>
                                <CardContent className="px-4 pb-4 space-y-3">
                                    <div className="space-y-2">
                                        <Label htmlFor={`count-qty-${item.id}`} className="text-xs">New Count Quantity</Label>
                                        <Input
                                            id={`count-qty-${item.id}`}
                                            type="number"
                                            placeholder="Enter quantity"
                                            value={itemCountInputs[item.id]?.quantity || ''}
                                            onChange={(e) => handleItemCountInputChange(item.id, 'quantity', e.target.value)}
                                            className="h-9"
                                            min="0"
                                            disabled={isSavingCount === item.id}
                                        />
                                        <Label htmlFor={`count-notes-${item.id}`} className="text-xs">Notes for this Count (Optional)</Label>
                                        <Textarea
                                            id={`count-notes-${item.id}`}
                                            placeholder="e.g., Found in different location, damaged items"
                                            value={itemCountInputs[item.id]?.notes || ''}
                                            onChange={(e) => handleItemCountInputChange(item.id, 'notes', e.target.value)}
                                            rows={2}
                                            className="text-xs"
                                            disabled={isSavingCount === item.id}
                                        />
                                        <EvidenceCapture
                                          onEvidenceCapturedAndAttached={(file, type) => handleEvidenceCaptured(item.id, file, type as 'image' | 'video')}
                                          isSavingEvidence={isSavingCount === item.id}
                                        />
                                        {itemCountInputs[item.id]?.mediaPreviewUrl && (
                                          <div className="mt-2 relative w-32 h-24 border rounded-md overflow-hidden bg-black">
                                            {itemCountInputs[item.id]?.mediaType === 'image' ? (
                                              <Image src={itemCountInputs[item.id]!.mediaPreviewUrl!} alt="Media preview" layout="fill" objectFit="contain" unoptimized={true} onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/128x96.png'; (e.target as HTMLImageElement).srcset = ''; }} />
                                            ) : itemCountInputs[item.id]?.mediaType === 'video' ? (
                                              <video src={itemCountInputs[item.id]!.mediaPreviewUrl!} controls className="w-full h-full object-contain" />
                                            ) : null}
                                            <Button
                                              type="button" variant="ghost" size="icon"
                                              className="absolute top-0.5 right-0.5 h-5 w-5 bg-destructive/70 hover:bg-destructive text-destructive-foreground rounded-full p-0.5"
                                              onClick={() => handleRemoveMedia(item.id)} disabled={isSavingCount === item.id}
                                            > <XCircle className="h-3 w-3"/> </Button>
                                          </div>
                                        )}
                                        <Button size="sm" variant="default" onClick={() => handleSaveItemCount(item.id)} disabled={isSavingCount === item.id || !itemCountInputs[item.id]?.quantity.trim()} className="w-full sm:w-auto mt-2">
                                            {isSavingCount === item.id ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PlusCircle className="mr-2 h-4 w-4" />}
                                            Save This Count
                                        </Button>
                                    </div>
                                    {item.counts && item.counts.length > 0 && (
                                      <div className="mt-3 pt-3 border-t">
                                        <h4 className="text-xs font-semibold mb-1 text-muted-foreground flex items-center"><List className="mr-1 h-3 w-3"/>Recorded Counts:</h4>
                                        <ScrollArea className="h-24 pr-1">
                                          <ul className="space-y-1 text-xs">
                                            {item.counts.map(c => (
                                              <li key={c.id} className="p-1.5 border rounded-md bg-muted/30 text-muted-foreground">
                                                <div className="flex justify-between items-center">
                                                  <span>Count: <span className="font-semibold text-foreground">{c.count}</span></span>
                                                  <span className="text-xs">{c.createdAt ? format(parseISO(c.createdAt), 'p, PP') : 'N/A'}</span>
                                                </div>
                                                {c.notes && <p className="text-xs italic mt-0.5">Notes: {c.notes}</p>}
                                                {c.images && c.images.length > 0 && c.images[0].imagePath && (
                                                  <div className="mt-1">
                                                    {c.images[0].imagePath.match(/\.(jpeg|jpg|gif|png)$/i) ? (
                                                      <Image src={`/api/uploads/${c.images[0].imagePath}`} alt="Count image" width={60} height={60} className="rounded-sm object-cover" unoptimized={true} onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/60x60.png'; (e.target as HTMLImageElement).srcset = ''; }} />
                                                    ) : c.images[0].imagePath.match(/\.(mp4|webm|ogg)$/i) ? (
                                                      <video src={`/api/uploads/${c.images[0].imagePath}`} width="80" height="60" controls className="rounded-sm" />
                                                    ) : (
                                                      <a href={`/api/uploads/${c.images[0].imagePath}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">View Media File</a>
                                                    )}
                                                  </div>
                                                )}
                                              </li>
                                            ))}
                                          </ul>
                                        </ScrollArea>
                                      </div>
                                    )}
                                </CardContent>
                            </Card>
                        ))}
                        </div>
                    </ScrollArea>
                    )}
                </CardContent>
                <CardFooter className="border-t pt-4">
                    <Button
                        className="w-full"
                        disabled={isLoading || isSavingCount !== null || isCompletingAudit}
                        onClick={handleFinalizeAudit}
                    >
                        {isCompletingAudit ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : <ClipboardCheck className="mr-2 h-5 w-5"/>}
                        Finalize & Complete Audit
                    </Button>
                </CardFooter>
              </Card>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
