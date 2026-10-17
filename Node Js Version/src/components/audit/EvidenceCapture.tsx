// src/components/audit/EvidenceCapture.tsx
'use client';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { captureEvidencePhoto, captureEvidenceVideo } from '@/lib/auditorCameraUtils';
import { Camera, Video, XCircle, RotateCcw, CheckCircle, Loader2 } from 'lucide-react';
import Image from 'next/image';
import { useToast } from '@/hooks/use-toast';

interface EvidenceCaptureProps {
  onEvidenceCapturedAndAttached: (file: File, type: 'image' | 'video') => void;
  isSavingEvidence?: boolean; 
}

export default function EvidenceCapture({ 
  onEvidenceCapturedAndAttached,
  isSavingEvidence = false
}: EvidenceCaptureProps) {
  const [mediaSrc, setMediaSrc] = useState<string | null>(null); // This will be a data URI
  const [mediaFile, setMediaFile] = useState<File | null>(null);
  const [mediaType, setMediaType] = useState<'image' | 'video' | null>(null);
  const [isCapturing, setIsCapturing] = useState(false);
  const { toast } = useToast();

  const captureMedia = async (type: 'image' | 'video') => {
    try {
      setIsCapturing(true);
      setMediaSrc(null);
      setMediaFile(null);
      setMediaType(null);

      const captureFunction = type === 'image' ? captureEvidencePhoto : captureEvidenceVideo;
      const { dataUrl, file } = await captureFunction();
      
      setMediaSrc(dataUrl);
      setMediaFile(file);
      setMediaType(type);
    } catch (error: any) {
      toast({
        title: `${type === 'image' ? 'Photo' : 'Video'} Capture Error`,
        description: error.message || `Could not capture ${type}.`,
        variant: "destructive",
      });
      console.error(`Error capturing ${type}:`, error);
    } finally {
      setIsCapturing(false);
    }
  };

  const handleRetake = () => {
    setMediaSrc(null);
    setMediaFile(null);
    setMediaType(null);
  };

  const handleAttachEvidence = () => {
    if (mediaFile && mediaType) {
      onEvidenceCapturedAndAttached(mediaFile, mediaType);
      setMediaSrc(null);
      setMediaFile(null);
      setMediaType(null);
    } else {
        toast({
            title: "No Media",
            description: "Please capture photo or video first.",
            variant: "destructive"
        });
    }
  };

  return (
    <div className="space-y-3 p-3 border rounded-md bg-muted/20">
       <h4 className="text-sm font-medium text-muted-foreground">Attach Evidence (Optional)</h4>
      {!mediaSrc ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <Button 
            onClick={() => captureMedia('image')}
            variant="outline"
            size="sm"
            disabled={isCapturing || isSavingEvidence}
            className="w-full"
          >
            <Camera className="mr-2 h-4 w-4" />
            {isCapturing && mediaType !== 'video' ? <><Loader2 className="mr-2 h-4 w-4 animate-spin"/>Opening...</> : 'Capture Photo'}
          </Button>
          <Button 
            onClick={() => captureMedia('video')}
            variant="outline"
            size="sm"
            disabled={isCapturing || isSavingEvidence}
            className="w-full"
          >
            <Video className="mr-2 h-4 w-4" />
            {isCapturing && mediaType !== 'image' ? <><Loader2 className="mr-2 h-4 w-4 animate-spin"/>Opening...</> : 'Record Video'}
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-xs font-medium">{mediaType === 'image' ? 'Photo Preview:' : 'Video Preview:'}</p>
          {mediaType === 'image' && mediaSrc && (
            <Image
              src={mediaSrc} // This is a data URI
              alt="Evidence photo preview"
              width={240} 
              height={160}
              className="rounded-md object-cover border bg-background"
              data-ai-hint="evidence photo"
              unoptimized={true} 
              onError={(e) => { (e.target as HTMLImageElement).src = 'https://placehold.co/240x160.png'; (e.target as HTMLImageElement).srcset = ''; }}
            />
          )}
          {mediaType === 'video' && mediaSrc && (
            <video 
              src={mediaSrc} // This is a data URI
              controls 
              className="w-full max-w-xs rounded-md border bg-background" 
            />
          )}
          <div className="flex flex-col sm:flex-row gap-2">
            <Button variant="outline" size="sm" onClick={handleRetake} disabled={isCapturing || isSavingEvidence}>
              <RotateCcw className="mr-2 h-3 w-3" /> Retake / Cancel
            </Button>
            <Button onClick={handleAttachEvidence} size="sm" disabled={isCapturing || isSavingEvidence || !mediaFile} className="bg-blue-600 hover:bg-blue-700">
              {isSavingEvidence ? <Loader2 className="mr-2 h-4 w-4 animate-spin"/> : <CheckCircle className="mr-2 h-4 w-4"/>}
              Attach This Evidence
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
