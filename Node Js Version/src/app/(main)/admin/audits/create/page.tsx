// src/app/(main)/admin/audits/create/page.tsx
'use client';

import React, { useEffect, useState } from 'react'; // Added useEffect, useState
import { useSearchParams } from 'next/navigation'; // Added useSearchParams
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { PlusCircle, ShieldAlert, ArrowLeft, Loader2 } from 'lucide-react';
import { useApp } from '@/context/AppContext';
import { useRouter } from 'next/navigation';
import AuditLauncher from '@/components/admin/AuditLauncher';
import type { Audit } from '@/types'; // Added Audit type

export default function AdminLaunchAuditPage() {
  const { currentUser, hasPermission, isDataLoaded, getAuditById } = useApp();
  const router = useRouter();
  const searchParams = useSearchParams();
  const relaunchFromId = searchParams.get('relaunchFrom');

  const [originalAuditForRelaunch, setOriginalAuditForRelaunch] = useState<Audit | null | undefined>(undefined);
  const [isLoadingOriginalAudit, setIsLoadingOriginalAudit] = useState(false);

  useEffect(() => {
    async function fetchOriginalAudit() {
      if (relaunchFromId && isDataLoaded) {
        setIsLoadingOriginalAudit(true);
        const fetchedAudit = await getAuditById(relaunchFromId);
        setOriginalAuditForRelaunch(fetchedAudit || null);
        setIsLoadingOriginalAudit(false);
      }
    }
    fetchOriginalAudit();
  }, [relaunchFromId, getAuditById, isDataLoaded]);


  if (!isDataLoaded || isLoadingOriginalAudit) {
    return (
        <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <Loader2 className="w-12 h-12 animate-spin text-primary mb-4" />
            <p className="text-muted-foreground">
              {isLoadingOriginalAudit ? "Loading original audit data for relaunch..." : "Loading audit creation page..."}
            </p>
        </div>
    );
  }

  if (!currentUser || !(currentUser.role === 'admin' || (currentUser.role === 'manager' && hasPermission('manage_audits')))) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <ShieldAlert className="w-16 h-16 text-destructive mb-4" />
        <h1 className="text-2xl font-bold">Access Denied</h1>
        <p className="text-muted-foreground">You do not have permission to launch audits.</p>
        <Button onClick={() => router.push('/admin/audits')} className="mt-4">
            <ArrowLeft className="mr-2 h-4 w-4" /> Back to Audits
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="outline" onClick={() => router.push('/admin/audits')} className="mb-4 print:hidden">
        <ArrowLeft className="mr-2 h-4 w-4" /> Back to Audit Management
      </Button>
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center">
            <PlusCircle className="mr-2 h-7 w-7 text-primary" /> 
            {relaunchFromId ? 'Relaunch Audit' : 'Launch New Audit'}
          </CardTitle>
          <CardDescription>
            {relaunchFromId && originalAuditForRelaunch ? 
              `Re-launching audit based on "${originalAuditForRelaunch.title}". Review details and assign an auditor.` :
              'Configure and start a new stock audit for a specific location and auditor.'
            }
             {relaunchFromId && !originalAuditForRelaunch && !isLoadingOriginalAudit && (
              <span className="text-destructive"> Original audit ID '{relaunchFromId}' not found. Proceeding with new audit.</span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AuditLauncher initialDataForRelaunch={originalAuditForRelaunch} />
        </CardContent>
      </Card>
    </div>
  );
}
