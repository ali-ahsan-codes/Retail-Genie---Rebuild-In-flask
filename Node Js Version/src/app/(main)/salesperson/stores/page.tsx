
'use client';

import { useEffect, useState } from 'react';
import CsvViewer from '@/components/shared/CsvViewer';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { AlertTriangle, ListFilter } from 'lucide-react'; // Corrected icon import
import { useToast } from '@/hooks/use-toast';

interface CsvFileWithData {
  filename: string;
  data: any[];
  error?: string;
}

export default function SalespersonStoresPage() {
  const [allCsvFiles, setAllCsvFiles] = useState<CsvFileWithData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  useEffect(() => {
    const fetchCsvData = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/stores');
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ message: `Error fetching CSV data: ${response.statusText}` }));
          throw new Error(errorData.message);
        }
        const data: CsvFileWithData[] = await response.json();
        setAllCsvFiles(data);
      } catch (err) {
        const errorMessage = (err as Error).message || 'An error occurred while fetching data.';
        setError(errorMessage);
        toast({ title: "Error Fetching CSVs", description: errorMessage, variant: "destructive" });
        console.error('Error fetching CSV data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchCsvData();
  }, [toast]);

  return (
    <div className="p-6 space-y-6">
      <Card className="shadow-md">
        <CardHeader>
          <CardTitle className="text-2xl flex items-center"><ListFilter className="mr-2 h-6 w-6 text-primary"/>External Stores Inventory</CardTitle>
          <CardDescription>View product availability from other stores.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading && (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="space-y-2">
                  <Skeleton className="h-8 w-1/3" />
                  <Skeleton className="h-40 w-full" />
                </div>
              ))}
            </div>
          )}

          {error && (
            <div className="text-destructive bg-destructive/10 p-4 rounded-md">
              <AlertTriangle className="inline-block mr-2 h-5 w-5" />
              Error: {error}
            </div>
          )}

          {!loading && !error && allCsvFiles.length === 0 && (
            <div className="text-center text-muted-foreground py-8">
              <ListFilter className="mx-auto h-12 w-12 mb-4" />
              <p className="text-lg">No external store inventory files are currently available.</p>
            </div>
          )}

          {!loading && !error && allCsvFiles.length > 0 && (
            <div className="space-y-8">
              {allCsvFiles.map((fileItem) => (
                <Card key={fileItem.filename} className="bg-card border">
                  <CardHeader>
                    <CardTitle className="text-xl">{fileItem.filename}</CardTitle>
                    {fileItem.error && <CardDescription className="text-destructive">Error: {fileItem.error}</CardDescription>}
                  </CardHeader>
                  <CardContent>
                    {fileItem.data && fileItem.data.length > 0 ? (
                      <CsvViewer data={fileItem.data} />
                    ) : (
                      <p className="text-muted-foreground">No data to display for this file (or it was empty/unparsable).</p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
