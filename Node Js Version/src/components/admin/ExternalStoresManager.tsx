
'use client';

import CsvUploader from "@/components/admin/CsvUploader";
import CsvViewer from "@/components/shared/CsvViewer";
import React, { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { AlertTriangle, Trash2, ListFilter, AlertCircle } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

interface CsvFileWithData {
  filename: string;
  data: any[];
  error?: string;
}

export default function ExternalStoresManager() {
  const [allCsvFiles, setAllCsvFiles] = useState<CsvFileWithData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  const fetchCsvData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
      const apiUrl = `${baseUrl}/api/stores`;
      const response = await fetch(apiUrl);
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
  }, [toast]);

  useEffect(() => {
    fetchCsvData();
  }, [fetchCsvData]);

  const handleDeleteFile = async (filename: string) => {
    try {
      const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
      const apiUrl = `${baseUrl}/api/stores?filename=${encodeURIComponent(filename)}`;
      const response = await fetch(apiUrl, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: `Error deleting file: ${response.statusText}` }));
        throw new Error(errorData.message);
      }
      const result = await response.json();
      toast({ title: "File Deleted", description: result.message });
      fetchCsvData(); // Refresh the list
    } catch (err) {
      const errorMessage = (err as Error).message || 'An error occurred while deleting the file.';
      toast({ title: "Error Deleting File", description: errorMessage, variant: "destructive" });
      console.error('Error deleting file:', err);
    }
  };

  const handleClearAllFiles = async () => {
    try {
      const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
      const apiUrl = `${baseUrl}/api/stores?action=deleteAll`;
      const response = await fetch(apiUrl, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: `Error clearing files: ${response.statusText}` }));
        throw new Error(errorData.message);
      }
      const result = await response.json();
      toast({ title: "All CSVs Cleared", description: result.message, className: "bg-destructive text-destructive-foreground" });
      fetchCsvData(); // Refresh the list
    } catch (err) {
      const errorMessage = (err as Error).message || 'An error occurred while clearing files.';
      toast({ title: "Error Clearing Files", description: errorMessage, variant: "destructive" });
      console.error('Error clearing files:', err);
    }
  };


  return (
    <div className="space-y-6 mt-4">
      <Card className="shadow-sm border">
        <CardHeader>
          <CardTitle className="text-xl">Upload External Store Inventory</CardTitle>
          <CardDescription>Upload CSV files containing product availability from other stores. These files are stored persistently.</CardDescription>
        </CardHeader>
        <CardContent>
          <CsvUploader onUploadSuccess={fetchCsvData} />
        </CardContent>
      </Card>

      <Card className="shadow-sm border">
        <CardHeader className="flex flex-row justify-between items-center">
          <div>
            <CardTitle className="text-xl">Uploaded CSV Files</CardTitle>
            <CardDescription>View and manage uploaded CSV files for external stores.</CardDescription>
          </div>
          {allCsvFiles.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm">
                  <Trash2 className="mr-2 h-4 w-4" /> Clear All Uploaded CSVs
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This action cannot be undone. This will permanently delete all uploaded CSV files from the server.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleClearAllFiles} className="bg-destructive hover:bg-destructive/80">
                    Yes, Clear All
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </CardHeader>
        <CardContent>
          {loading && (
            <div className="space-y-4">
              {[...Array(2)].map((_, i) => (
                <div key={i} className="space-y-2">
                  <Skeleton className="h-8 w-1/3" />
                  <Skeleton className="h-32 w-full" />
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
              <p className="text-lg">No CSV files have been uploaded yet.</p>
            </div>
          )}

          {!loading && !error && allCsvFiles.length > 0 && (
            <div className="space-y-6">
              {allCsvFiles.map((fileItem) => (
                <Card key={fileItem.filename} className="bg-card border">
                  <CardHeader className="flex flex-row justify-between items-center py-3 px-4">
                    <div>
                      <CardTitle className="text-lg">{fileItem.filename}</CardTitle>
                      {fileItem.error && <CardDescription className="text-destructive text-xs">Error: {fileItem.error}</CardDescription>}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteFile(fileItem.filename)}
                      className="text-destructive hover:text-destructive hover:bg-destructive/10"
                    >
                      <Trash2 className="mr-2 h-4 w-4"/> Delete
                    </Button>
                  </CardHeader>
                  <CardContent className="px-4 pb-4">
                    {fileItem.data && fileItem.data.length > 0 ? (
                      <CsvViewer data={fileItem.data} />
                    ) : (
                      <p className="text-muted-foreground text-sm">No data to display for this file (or it was empty/unparsable).</p>
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
