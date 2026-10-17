// src/lib/auditorCameraUtils.ts
export async function captureAuditorSelfie(): Promise<{ dataUrl: string; file: File }> {
  return captureMedia('image/*', 'user'); // Prefer front camera
}

export async function captureEvidencePhoto(): Promise<{ dataUrl: string; file: File }> {
  return captureMedia('image/*', 'environment'); // Prefer back camera
}

export async function captureEvidenceVideo(): Promise<{ dataUrl: string; file: File }> {
  return captureMedia('video/*', 'environment'); // Prefer back camera
}

async function captureMedia(accept: string, captureMode: string): Promise<{ dataUrl: string; file: File }> {
  // Note: input.capture = 'user' requests the front-facing camera.
  // 'environment' requests the back-facing camera.
  // However, browser and device behavior may vary. Some may still default
  // or offer the user a choice. This is a standard HTML attribute limitation.
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = accept;
    if (captureMode) { 
        input.capture = captureMode;
    }
    
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) {
        return reject(new Error('No file selected or capture cancelled.'));
      }
      
      try {
        const dataUrl = await readFileAsDataURL(file);
        resolve({ dataUrl, file });
      } catch (err) {
        reject(err);
      }
    };

    input.oncancel = () => {
        reject(new Error('File capture cancelled by user.'));
    };
    
    input.click();
  });
}

function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = (error) => reject(new Error(`Failed to read file: ${error}`));
    reader.readAsDataURL(file);
  });
}
