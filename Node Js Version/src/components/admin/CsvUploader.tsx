
'use client';

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { Upload } from 'lucide-react'; // Added Upload icon

interface CsvUploaderProps {
  onUploadSuccess?: () => void;
  onUploadError?: (error: string) => void;
}

export default function CsvUploader({ onUploadSuccess, onUploadError }: CsvUploaderProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const { toast } = useToast();

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      setSelectedFile(event.target.files[0]);
    } else {
      setSelectedFile(null);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      const noFileMsg = "Please select a file to upload.";
      toast({ title: "Upload Error", description: noFileMsg, variant: "destructive" });
      onUploadError?.(noFileMsg);
      return;
    }

    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const baseUrl = typeof window !== 'undefined' ? window.location.origin : '';
      const apiUrl = `${baseUrl}/api/stores`;
      const response = await fetch(apiUrl, {
        method: 'POST',
        body: formData,
      });

      const responseBody = await response.text(); // Read as text first

      if (!response.ok) {
        let errorMessage = `Upload failed with status: ${response.status}`;
        try {
          const errorData = JSON.parse(responseBody); // Try to parse as JSON
          errorMessage = errorData.message || errorData.error || errorMessage;
        } catch (e) {
          // If JSON parsing fails, use the text response (or part of it)
          errorMessage = responseBody ? responseBody.substring(0, 200) : errorMessage;
        }
        throw new Error(errorMessage);
      }

      // If response is OK, try to parse as JSON to get filename
      let resultFilename = selectedFile.name; // Fallback to original filename
      try {
        const result = JSON.parse(responseBody);
        resultFilename = result.filename || resultFilename;
      } catch (e) {
        // If JSON parsing fails, it's fine, we can still show success with original filename
        console.warn("CSVUploader: Upload API response was not JSON, but status was OK.", responseBody);
      }

      toast({ title: "Upload Successful", description: `File "${resultFilename}" uploaded.` });
      onUploadSuccess?.();
      setSelectedFile(null); 
      const fileInput = document.getElementById('csv-file-input') as HTMLInputElement;
      if (fileInput) {
        fileInput.value = "";
      }

    } catch (error: any) {
      console.error('Upload error in CsvUploader:', error);
      const errMsg = error.message || 'An error occurred during upload.';
      toast({ title: "Upload Failed", description: errMsg, variant: "destructive" });
      onUploadError?.(errMsg);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex flex-col space-y-4 sm:flex-row sm:space-y-0 sm:space-x-4 items-center">
      <Input 
        id="csv-file-input"
        type="file" 
        accept=".csv" 
        onChange={handleFileChange} 
        disabled={isUploading} 
        className="flex-grow"
      />
      <Button onClick={handleUpload} disabled={!selectedFile || isUploading} className="w-full sm:w-auto">
        <Upload className="mr-2 h-4 w-4" />
        {isUploading ? 'Uploading...' : 'Upload CSV'}
      </Button>
    </div>
  );
}
