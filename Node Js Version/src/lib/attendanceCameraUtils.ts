
// src/lib/attendanceCameraUtils.ts
export async function captureAttendanceSelfie(): Promise<string> {
  // Note: input.capture = 'user' requests the front-facing camera.
  // However, browser and device behavior may vary. Some may still default
  // to the rear camera or offer the user a choice. This is a standard
  // HTML attribute limitation for simple file inputs.
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.capture = 'user'; // Ensure this attribute is set for front camera preference
    
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return reject(new Error('No file selected'));
      
      try {
        // Convert to data URL for immediate preview
        const dataUrl = await readFileAsDataURL(file);
        resolve(dataUrl);
      } catch (err) {
        reject(err);
      }
    };
    
    // Handle cancellation
    input.oncancel = () => { 
      reject(new Error('Selfie capture cancelled by user.'));
    };
        
    input.click();
  });
}

function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error('Failed to read file'));
    reader.readAsDataURL(file);
  });
}
