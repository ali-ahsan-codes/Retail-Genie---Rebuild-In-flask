
// src/components/shared/SelfieImageDisplay.tsx
'use client';
import React, { useState } from 'react';
import Image from 'next/image';
import { Package, AlertTriangle } from 'lucide-react';

interface SelfieImageDisplayProps {
  src?: string | null;
  alt: string;
  width: number;
  height: number;
  className?: string;
  placeholderText?: string;
}

const SelfieImageDisplay: React.FC<SelfieImageDisplayProps> = ({
  src,
  alt,
  width,
  height,
  className,
  placeholderText = "No Img"
}) => {
  const [imageError, setImageError] = useState(false);

  // Construct the image source URL
  // If src is a data URI or an absolute HTTP/HTTPS URL, use it directly.
  // Otherwise, assume it's a relative path from the 'uploads' directory
  // and construct the API path.
  let imageSource: string | null = null;
  if (src) {
    if (src.startsWith('data:') || src.startsWith('http://') || src.startsWith('https://')) {
      imageSource = src;
    } else {
      // Prepend /api/uploads/ if it's a relative path and doesn't already start with it
      // (though DB paths shouldn't start with /api/uploads/)
      const pathPrefix = src.startsWith('/') ? '' : '/'; // Handle if src already has a leading slash somehow
      imageSource = `/api/uploads${pathPrefix}${src.startsWith('uploads/') ? src.substring('uploads/'.length) : src}`;
    }
  }


  if (!imageSource || imageError) {
    return (
      <div
        className={`flex items-center justify-center bg-muted rounded-sm text-xs text-center p-1 ${className || ''}`}
        style={{ width, height }}
        title={alt + (imageError ? ` (Failed to load image)` : ' (No image available)')}
      >
        {imageError ? <AlertTriangle className="w-3/4 h-3/4 text-destructive" /> : <Package className="w-3/4 h-3/4 text-muted-foreground" />}
      </div>
    );
  }

  return (
    <Image
      src={imageSource}
      alt={alt}
      width={width}
      height={height}
      className={className}
      data-ai-hint="selfie attendance"
      onError={() => {
        // console.error(`Error: Error loading image. Original src prop: ${src}, Processed imageSource: ${imageSource}`);
        setImageError(true);
      }}
      unoptimized={true} 
    />
  );
};

export default SelfieImageDisplay;
