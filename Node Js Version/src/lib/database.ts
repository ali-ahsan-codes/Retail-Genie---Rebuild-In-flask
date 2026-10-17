
// src/lib/database.ts
import type { Product, User, Order, AttendanceLog, BreakLog, DeliveryStatus, DemandNotice, DemandNoticeStatus, TaxSetting, GlobalDiscountSetting, Permission, OrderItem, PaymentDetail, ReturnTransactionInfo, CommissionSetting, SeriesNumberSetting, AttendanceSetting, Quotation, QuotationItem, SeriesId, Supplier, SupplierProduct, PurchaseOrder } from '@/types';
import { ApiClient } from './apiClient'; // Import the new ApiClient
import { toast } from '@/hooks/use-toast'; // Import toast for queue messages

const apiClient = new ApiClient(); // Instantiate the client

// Custom error class for API errors (keep or modify if ApiClient provides more specific errors)
export class ApiError extends Error {
  status?: number;
  data?: any;

  constructor(message: string, status?: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

// Enhanced API error handling - to be used if ApiClient doesn't throw ApiError directly for non-200s.
// If ApiClient already throws ApiError, this might be simplified or used as a fallback.
async function handleGenericApiError(response: Response, defaultErrorMessage: string): Promise<never> {
  let errorDetail = defaultErrorMessage;
  let errorStatus = response.status;
  let errorData: any = {};

  try {
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      errorData = await response.json();
      errorDetail = errorData.details || errorData.message || errorData.error || JSON.stringify(errorData);
    } else {
      const textError = await response.text();
      errorDetail = textError ? `Server returned non-JSON error (Status ${response.status}): ${textError.substring(0, 500)}` : defaultErrorMessage;
      errorData = { rawResponse: textError };
    }
  } catch (e) {
    errorDetail = `${defaultErrorMessage} (Status: ${response.status}, unable to parse error response body).`;
    errorData = { parseError: (e as Error).message };
  }
  console.warn(`API Error (Status ${errorStatus}) in handleGenericApiError: ${errorDetail}`, errorData);
  throw new ApiError(errorDetail, errorStatus, errorData);
}


// --- Product Operations ---
export async function getProductsFromDb(): Promise<Product[]> {
  const response = await apiClient.get('/products');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch products');
  return response.json();
}

export async function addProductToDb(productData: Omit<Product, 'id'>): Promise<Product | { queued: true, offlineId: string } | null > {
  const response = await apiClient.post('/products', productData);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Product "${productData.name}" creation is queued and will sync when online. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to add product');
  const result = await response.json();
  if (result.success === false) throw new ApiError(result.error || 'Failed to add product (API reported error)', response.status, result);
  return result.data || result;
}

export async function updateProductInDb(product: Product): Promise<Product | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put(`/products/${product.id}`, product);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Product "${product.name}" update is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, `Failed to update product ${product.name}`);
  const result = await response.json();
  if (result.success === false) throw new ApiError(result.error || 'Failed to update product (API reported error)', response.status, result);
  return result.data || result;
}

export async function deleteProductFromDb(productId: string): Promise<{ success: boolean, queued?: boolean, offlineId?: string, error?: string }> {
  const response = await apiClient.delete(`/products/${productId}`);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Product deletion (ID: ${productId}) is queued. ID: ${offlineId}` });
    return { success: true, queued: true, offlineId };
  }
  if (!response.ok) {
    await handleGenericApiError(response, 'Failed to delete product');
    return { success: false, error: 'Failed to delete product' }; // Should be caught by handleGenericApiError
  }
  const result = await response.json();
  if (result.success === false) {
     throw new ApiError(result.error || 'Failed to delete product (API reported error)', response.status, result);
  }
  return { success: true };
}

// --- User Operations ---
export async function getUsersFromDb(): Promise<User[]> {
  const response = await apiClient.get('/users');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch users');
  return response.json();
}

export async function addUserToDb(userData: Omit<User, 'id' | 'activeBreakId'>): Promise<User | { queued: true, offlineId: string } | null> {
  const response = await apiClient.post('/users', userData);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `User "${userData.username}" creation is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, `Failed to add user ${userData.username}`);
  return response.json();
}

export async function updateUserInDb(user: User): Promise<User | { queued: true, offlineId: string } | null> {
  const payload = { ...user };
  if (payload.password === "") delete payload.password;

  const response = await apiClient.put(`/users/${user.id}`, payload);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `User "${user.username}" update is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, `Failed to update user ${user.username}`);
  return response.json();
}

export async function deleteUserFromDb(userId: string): Promise<{ success: boolean, queued?: boolean, offlineId?: string, error?: string }> {
  const response = await apiClient.delete(`/users/${userId}`);
   if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `User deletion (ID: ${userId}) is queued. ID: ${offlineId}` });
    return { success: true, queued: true, offlineId };
  }
  if (!response.ok) {
    await handleGenericApiError(response, 'Failed to delete user');
    return { success: false, error: 'Failed to delete user' };
  }
  return { success: true };
}

export async function getUserByUsernameFromDb(username: string): Promise<User | null> {
  const response = await apiClient.get(`/users/username/${username}`);
  if (!response.ok) {
    if (response.status === 404) return null;
    return handleGenericApiError(response, `Failed to fetch user ${username}`);
  }
  return response.json();
}

// --- Order Operations ---
export async function getOrdersFromDb(): Promise<Order[]> {
  const response = await apiClient.get('/orders');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch orders');
  return response.json();
}

export async function addOrderToDb(
  orderData: Omit<Order, 'id' | 'createdAt' | 'updatedAt' | 'status' | 'deliveryStatus' | 'returnTransactions' | 'appliedGlobalDiscountPercentage'>
): Promise<Order | { queued: true, offlineId: string } | null> {
  const response = await apiClient.post('/orders', orderData);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Order creation for "${orderData.customerName || 'N/A'}" is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to add order');
  return response.json();
}

export async function updateOrderInDb(order: Order): Promise<Order | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put(`/orders/${order.id}`, { ...order, updatedAt: new Date().toISOString() });
   if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Order "${order.id}" update is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, `Failed to update order ${order.id}`);
  return response.json();
}

export async function deleteOrderFromDb(orderId: string): Promise<{ success: boolean, queued?: boolean, offlineId?: string, error?: string }>{
  const response = await apiClient.delete(`/orders/${orderId}`);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Order deletion (ID: ${orderId}) is queued. ID: ${offlineId}` });
    return { success: true, queued: true, offlineId };
  }
  if (!response.ok) {
    await handleGenericApiError(response, `Failed to delete order ${orderId}`);
    return { success: false, error: `Failed to delete order ${orderId}` };
  }
  return { success: true };
}

export async function getOrderByIdFromDb(orderId: string): Promise<Order | undefined> {
  const response = await apiClient.get(`/orders/${orderId}`);
  if (!response.ok) {
    if (response.status === 404) return undefined;
    return handleGenericApiError(response, `Failed to fetch order ${orderId}`);
  }
  return response.json();
}

// --- Attendance Log Operations ---
export async function getAttendanceLogsFromDb(): Promise<AttendanceLog[]> {
  const response = await apiClient.get('/attendance');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch attendance logs');
  return response.json();
}

export async function addAttendanceLogToDb(logData: Omit<AttendanceLog, 'id'>): Promise<AttendanceLog | { queued: true, offlineId: string } | null> {
  const response = await apiClient.post('/attendance', logData);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Attendance log is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to add attendance log');
  return response.json();
}

// --- Break Log Operations ---
export async function getBreakLogsFromDb(): Promise<BreakLog[]> {
  const response = await apiClient.get('/breaks');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch break logs');
  return response.json();
}

export async function addBreakLogToDb(breakData: { userId: string; startTime: string }): Promise<BreakLog | { queued: true, offlineId: string } | null> {
  const response = await apiClient.post('/breaks', breakData);
   if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Start break request is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to start break');
  return response.json();
}

export async function updateBreakLogInDb(breakData: BreakLog): Promise<BreakLog | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put(`/breaks/${breakData.id}`, { userId: breakData.userId });
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `End break request for break ${breakData.id} is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to end break');
  return response.json();
}

// --- Demand Notice Operations ---
export async function getDemandNoticesFromDb(): Promise<DemandNotice[]> {
  const response = await apiClient.get('/demand-notices');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch demand notices');
  return response.json();
}

export async function addDemandNoticeToDb(
  noticeData: Omit<DemandNotice, 'id' | 'createdAt' | 'updatedAt' | 'status'>
): Promise<DemandNotice | { queued: true, offlineId: string } | null> {
  const response = await apiClient.post('/demand-notices', noticeData);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Demand notice for "${noticeData.productName}" is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to add demand notice');
  return response.json();
}

export async function updateDemandNoticeInDb(notice: DemandNotice): Promise<DemandNotice | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put(`/demand-notices/${notice.id}`, notice);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Demand notice "${notice.id}" update is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, `Failed to update demand notice ${notice.id}`);
  return response.json();
}

export async function deleteDemandNoticeFromDb(noticeId: string): Promise<{ success: boolean, queued?: boolean, offlineId?: string, error?: string }> {
  const response = await apiClient.delete(`/demand-notices/${noticeId}`);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Demand notice deletion (ID: ${noticeId}) is queued. ID: ${offlineId}` });
    return { success: true, queued: true, offlineId };
  }
  if (!response.ok) {
    await handleGenericApiError(response, `Failed to delete demand notice ${noticeId}`);
    return { success: false, error: `Failed to delete demand notice ${noticeId}` };
  }
  return { success: true };
}

// --- Settings Operations ---
export async function getTaxSettingsFromDb(): Promise<TaxSetting[]> {
  const response = await apiClient.get('/settings/tax');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch tax settings');
  return response.json();
}

export async function updateTaxSettingsInDb(settings: TaxSetting[]): Promise<TaxSetting[] | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put('/settings/tax', settings);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: "Tax settings update is queued. ID: " + offlineId });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to update tax settings');
  return response.json();
}

export async function getGlobalDiscountSettingFromDb(): Promise<GlobalDiscountSetting | null> {
  const response = await apiClient.get('/settings/global-discount');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch global discount setting');
  const data = await response.json();
  return data || null;
}

export async function updateGlobalDiscountSettingInDb(setting: GlobalDiscountSetting | null): Promise<GlobalDiscountSetting | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put('/settings/global-discount', setting);
   if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: "Global discount update is queued. ID: " + offlineId });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to update global discount setting');
  const data = await response.json();
  return data || null;
}

export async function getCommissionSettingFromDb(): Promise<CommissionSetting | null> {
  const response = await apiClient.get('/settings/commission');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch commission setting');
  const data = await response.json();
  return data || null;
}

export async function updateCommissionSettingInDb(setting: CommissionSetting | null): Promise<CommissionSetting | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put('/settings/commission', setting);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: "Commission settings update is queued. ID: " + offlineId });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to update commission setting');
  const data = await response.json();
  return data || null;
}

export async function getSeriesNumberSettingsFromDb(): Promise<Record<SeriesId, SeriesNumberSetting> | null> {
  const response = await apiClient.get('/settings/invoice-number');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch series number settings');
  const data = await response.json();
  return data || null;
}

export async function updateSeriesNumberSettingInDb(setting: SeriesNumberSetting): Promise<SeriesNumberSetting | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put('/settings/invoice-number', setting);
   if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Series number setting for "${setting.id}" update is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, `Failed to update series number setting for ${setting.id}`);
  const data = await response.json();
  return data || null;
}

export async function getAttendanceSettingFromDb(): Promise<AttendanceSetting | null> {
  const response = await apiClient.get('/settings/attendance');
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch attendance setting');
  const data = await response.json();
  if (data && data.max_concurrent_breaks !== undefined) {
    data.max_concurrent_breaks = data.max_concurrent_breaks === null ? null : Number(data.max_concurrent_breaks);
  }
  return data || null;
}

export async function updateAttendanceSettingInDb(setting: AttendanceSetting | null): Promise<AttendanceSetting | { queued: true, offlineId: string } | null> {
  const response = await apiClient.put('/settings/attendance', setting);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: "Attendance settings update is queued. ID: " + offlineId });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to update attendance setting');
  const data = await response.json();
  if (data && data.max_concurrent_breaks !== undefined) {
    data.max_concurrent_breaks = data.max_concurrent_breaks === null ? null : Number(data.max_concurrent_breaks);
  }
  return data || null;
}

// --- Quotation Operations ---
export async function addQuotationToDb(
  quotationData: Omit<Quotation, 'id' | 'createdAt' | 'updatedAt' | 'salespersonId' | 'items'> & { items: Omit<QuotationItem, 'id' | 'quotationId' | 'converted'>[] },
  userId: string
): Promise<Quotation | { queued: true, offlineId: string } | null> {
  const response = await apiClient.post('/quotations', quotationData, userId);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Quotation creation is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, 'Failed to create quotation');
  const result = await response.json();
  if (!result.success) throw new ApiError(result.error || 'Failed to create quotation (API error)', response.status, result);
  return result.data;
}

export async function getQuotationsFromDb(userId?: string): Promise<Quotation[]> {
  const response = await apiClient.get('/quotations', userId);
  if (!response.ok) return handleGenericApiError(response, 'Failed to fetch quotations');
  const result = await response.json();
  if (result.success === false) throw new ApiError(result.error || 'Failed to fetch quotations (API error)', response.status, result);
  return result.data || result;
}

export async function getQuotationByIdFromDb(quotationId: string, userId: string): Promise<Quotation | undefined> {
  const response = await apiClient.get(`/quotations/${quotationId}`, userId);
  if (!response.ok) {
    if (response.status === 404) return undefined;
    return handleGenericApiError(response, `Failed to fetch quotation ${quotationId}`);
  }
  const result = await response.json();
  if (!result.success) throw new ApiError(result.error || `Failed to fetch quotation ${quotationId} (API error)`, response.status, result);
  return result.data;
}

export async function updateQuotationInDb(quotationData: Partial<Quotation> & {id: string}, userId: string): Promise<Quotation | { queued: true, offlineId: string } | null> {
   const response = await apiClient.put(`/quotations/${quotationData.id}`, quotationData, userId);
   if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Quotation "${quotationData.id}" update is queued. ID: ${offlineId}` });
    return { queued: true, offlineId };
  }
  if (!response.ok) return handleGenericApiError(response, `Failed to update quotation ${quotationData.id}`);
  const result = await response.json();
  if (!result.success) throw new ApiError(result.error || `Failed to update quotation ${quotationData.id} (API error)`, response.status, result);
  return result.data;
}

export async function deleteQuotationFromDb(quotationId: string, userId: string): Promise<{ success: boolean, queued?: boolean, offlineId?: string, error?: string }> {
  const response = await apiClient.delete(`/quotations/${quotationId}`, userId);
  if (response.status === 202) {
    const offlineId = response.headers.get('X-Offline-Request-ID') || 'unknown';
    toast({ title: "Request Queued", description: `Quotation deletion (ID: ${quotationId}) is queued. ID: ${offlineId}` });
    return { success: true, queued: true, offlineId };
  }
  if (!response.ok) {
    await handleGenericApiError(response, `Failed to delete quotation ${quotationId}`);
    return { success: false, error: `Failed to delete quotation ${quotationId}` };
  }
  const result = await response.json();
  if (!result.success) {
    throw new ApiError(result.error || `Failed to delete quotation ${quotationId} (API error)`, response.status, result);
  }
  return { success: true };
}

// --- SCM Operations ---
export async function getSuppliers(): Promise<Supplier[]> {
  const response = await apiClient.get('/suppliers');
  if (!response.ok) {
    return handleGenericApiError(response, 'Failed to fetch suppliers');
  }
  return response.json();
}

export async function addSupplier(formData: FormData): Promise<Supplier | null> {
  const response = await fetch('/api/suppliers', {
    method: 'POST',
    body: formData,
  });
  if (response.status === 202) {
    toast({ title: "Request Queued", description: "Add supplier request is queued." });
    return null;
  }
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(errorData.message || 'Failed to create supplier', response.status, errorData);
  }
  return response.json();
}


export async function deleteSupplier(supplierId: string): Promise<{ success: boolean }> {
    const response = await apiClient.delete(`/suppliers/${supplierId}`);
    if (response.status === 202) {
        toast({ title: "Request Queued", description: "Delete supplier request is queued." });
        return { success: true };
    }
    if (!response.ok) {
        return handleGenericApiError(response, 'Failed to delete supplier');
    }
    return response.json();
}

export async function addSupplierProduct(data: Omit<SupplierProduct, 'id' | 'document_path'>): Promise<SupplierProduct | null> {
  const response = await apiClient.post('/scm/supplier-products', data);
  if (response.status === 202) {
    toast({ title: "Request Queued", description: "Link product request is queued." });
    return null;
  }
  if (!response.ok) {
    return handleGenericApiError(response, 'Failed to link product to supplier');
  }
  return response.json();
}

export async function deleteSupplierProduct(linkId: string): Promise<{ success: boolean }> {
  const response = await apiClient.delete(`/scm/supplier-products/${linkId}`);
  if (response.status === 202) {
      toast({ title: "Request Queued", description: "Delete product link request is queued." });
      return { success: true };
  }
  if (!response.ok) {
      return handleGenericApiError(response, 'Failed to delete product link');
  }
  return response.json();
}

export async function getPurchaseOrders(): Promise<PurchaseOrder[]> {
    const response = await apiClient.get('/purchase-orders');
    if (!response.ok) {
        return handleGenericApiError(response, 'Failed to fetch purchase orders');
    }
    return response.json();
}

export async function createPurchaseOrder(data: {
    supplier_id: string;
    items: any[];
    expected_delivery: string | null;
    deadline: string | null;
}): Promise<PurchaseOrder | null> {
    const response = await apiClient.post('/purchase-orders', data);
    if (response.status === 202) {
        toast({ title: "Request Queued", description: "Create PO request is queued." });
        return null;
    }
    if (!response.ok) {
        return handleGenericApiError(response, 'Failed to create purchase order');
    }
    return response.json();
}


export async function initDb(): Promise<void> {
  console.log("Client-side database utility module loaded. ApiClient initialized.");
}
