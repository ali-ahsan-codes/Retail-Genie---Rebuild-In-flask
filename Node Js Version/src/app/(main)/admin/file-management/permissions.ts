
// src/app/(main)/admin/file-management/permissions.ts
import type { UserRole } from '@/types';

type FileManagementAction = 
  | 'view'                     // View the file management page
  | 'upload_cloud'             // Upload to their own cloud
  | 'delete_product_image'     // Delete any product image (system-wide)
  | 'delete_attendance_selfie' // Delete any attendance selfie (system-wide)
  | 'delete_cloud_file'        // Delete their own cloud files
  | 'edit_cloud_notes';        // Edit notes on their own cloud files

const FILE_MANAGEMENT_PERMISSIONS: Record<UserRole, Record<FileManagementAction, boolean>> = {
  admin: {
    view: true,
    upload_cloud: true,
    delete_product_image: true,
    delete_attendance_selfie: true,
    delete_cloud_file: true,
    edit_cloud_notes: true,
  },
  manager: {
    view: true,
    upload_cloud: true,
    delete_product_image: true, // Managers can manage product images
    delete_attendance_selfie: true, // Managers can manage attendance selfies
    delete_cloud_file: true,
    edit_cloud_notes: true,
  },
  salesperson: { 
    view: true, // Can view the page (will only see their cloud files)
    upload_cloud: true, 
    delete_product_image: false, 
    delete_attendance_selfie: false, 
    delete_cloud_file: true, 
    edit_cloud_notes: true 
  },
  storekeeper: { 
    view: true, 
    upload_cloud: true, 
    delete_product_image: false, 
    delete_attendance_selfie: false, 
    delete_cloud_file: true, 
    edit_cloud_notes: true 
  },
  cashier: { 
    view: true, 
    upload_cloud: true, 
    delete_product_image: false, 
    delete_attendance_selfie: false, 
    delete_cloud_file: true, 
    edit_cloud_notes: true 
  },
  logistics: { 
    view: true, 
    upload_cloud: true, 
    delete_product_image: false, 
    delete_attendance_selfie: false, 
    delete_cloud_file: true, 
    edit_cloud_notes: true 
  },
};

export function canUserManageFile(userRole: UserRole | undefined, action: FileManagementAction): boolean {
  if (!userRole) return false;
  return FILE_MANAGEMENT_PERMISSIONS[userRole]?.[action] || false;
}

