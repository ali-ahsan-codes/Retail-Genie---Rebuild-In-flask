// src/components/audit/AuditorSelfie.tsx
'use client';
import { useState, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { captureAuditorSelfie } from '@/lib/auditorCameraUtils';
import { Camera, CheckCircle, RotateCcw, Loader2 } from 'lucide-react';
import Image from 'next/image';
import { useToast } from '@/hooks/use-toast';

interface AuditorSelfieProps {
  onSelfieCaptured: (selfieFile: File | null) => void;
  isProcessingStart?: boolean; 
}

export default function AuditorSelfie({ onSelfieCaptured, isProcessingStart = false }: AuditorSelfieProps) {
  const [imgSrc, setImgSrc] = useState<string | null>(null); // This will be a data URI
  const [isCapturing, setIsCapturing] = useState(false);
  const { toast } = useToast();

  const handleTakeSelfie = useCallback(async () => {
    try {
      setIsCapturing(true);
      setImgSrc(null); 
      onSelfieCaptured(null); 
      const { dataUrl, file } = await captureAuditorSelfie();
      setImgSrc(dataUrl);
      onSelfieCaptured(file); 
    } catch (error: any) {
      toast({
        title: "Selfie Capture Error",
        description: error.message || "Could not capture selfie. Check camera permissions.",
        variant: "destructive",
      });
      console.error('Error capturing selfie:', error);
      onSelfieCaptured(null); 
    } finally {
      setIsCapturing(false);
    }
  }, [onSelfieCaptured, toast]);

  const handleRetakeSelfie = () => {
    setImgSrc(null);
    onSelfieCaptured(null); 
  };

  return (
    <div className="flex flex-col items-center space-y-4 p-4 border rounded-md bg-muted/20">
      <h3 className="text-lg font-medium">Auditor Selfie Verification</h3>
      
      {!imgSrc ? (
        <Button 
          onClick={handleTakeSelfie}
          className="w-full sm:w-auto"
          disabled={isCapturing || isProcessingStart}
        >
          <Camera className="mr-2 h-4 w-4" />
          {isCapturing ? <><Loader2 className="mr-2 h-4 w-4 animate-spin"/>Opening Camera...</> : 'Take Auditor Selfie'}
        </Button>
      ) : (
        <div className="w-full space-y-4 text-center">
          <p className="text-sm font-medium">Selfie Preview:</p>
          <Image
            src={imgSrc} // This is a data URI
            alt="Auditor selfie preview"
            width={200}
            height={200}
            className="rounded-md object-cover mx-auto shadow-md aspect-square"
            data-ai-hint="selfie auditor"
            unoptimized={true} // Important for data URIs
            onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/200x200.png'; (e.target as HTMLImageElement).srcset = ''; }}
          />
          <div className="flex flex-col sm:flex-row gap-2 justify-center">
            <Button variant="outline" onClick={handleRetakeSelfie} disabled={isProcessingStart || isCapturing}>
              <RotateCcw className="mr-2 h-4 w-4" /> Retake Selfie
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
