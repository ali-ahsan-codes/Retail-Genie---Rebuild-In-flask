// src/types/index.ts


export type UserRole = 'salesperson' | 'storekeeper' | 'cashier' | 'admin' | 'logistics' | 'manager' | 'auditor' | 'display' | 'express';

export interface User {
  id: string;
  username: string;
  password?: string;
  role: UserRole;
  permissions?: string[];
  attendanceLogs?: AttendanceLog[];
  breakLogs?: BreakLog[];
  activeBreakId?: string | null;
  autoEnterAfterScan?: boolean;
}

export interface Product {
  id:string;
  name: string;
  price: number;
  quantityInStock: number;
  sku: string;
  expiryDate?: string;
  imageUrl?: string;
  category?: string;
  isDemandNoticeProduct?: boolean; // Flag for products created via DN
  lowStockThreshold?: number; // Quantity at or below which lowStockPrice applies
  lowStockPrice?: number;     // Special price when stock is low
}

export interface CartItem extends Product {
  cartQuantity: number;
  customPrice?: number;
}

export interface OrderItem {
  productId: string;
  name: string;
  sku: string;
  quantity: number;
  pricePerUnit: number;
  totalPrice: number;
}

export type OrderStatus = 'pending_payment' | 'partial_payment' | 'preparing' | 'ready_for_pickup' | 'paid' | 'completed' | 'cancelled' | 'returned';
export type DeliveryStatus = 'pending_dispatch' | 'out_for_delivery' | 'delivered' | 'delivery_failed' | 'pickup_ready';


export type PaymentMethod = 'cash' | 'card' | 'bank_transfer' | 'advance_on_dn';

export interface PaymentDetail {
  method: PaymentMethod;
  amount: number;
  transactionId?: string;
  paymentDate?: string; // ISO Date string for when the payment was made
  notes?: string; // e.g. "Advance for DN-XYZ"
  cashierId?: string;
  cashierName?: string;
}
export interface AppliedTax {
  name: string;
  rate: number;
  amount: number;
}

export interface ReturnItemDetail extends OrderItem {
  returnReason?: string;
  quantityToReturn: number;
}

export interface ExchangeItemDetail extends OrderItem {
  // For future use
}

export interface ReturnTransactionInfo {
  id: string;
  returnedAt: string;
  processedByUserId: string;
  processedByUsername: string;
  originalOrderItemsSnapshot: OrderItem[];
  itemsReturned: ReturnItemDetail[];
  notesOnExchange?: string;
  returnReasonGeneral?: string;
  totalValueOfReturnedItems: number;
  netRefundAmount: number;
  refundPaymentDetails: PaymentDetail[];
  notes?: string;
}


export interface Order {
  id: string;

  primarySalespersonId: string;
  primarySalespersonName: string;
  secondarySalespersonId?: string;
  secondarySalespersonName?: string;
  primarySalespersonCommission?: number;
  secondarySalespersonCommission?: number;

  items: OrderItem[];
  subtotal: number;
  discountAmount: number;
  appliedDiscountPercentage?: number;
  appliedGlobalDiscountPercentage?: number;
  taxes: AppliedTax[];
  totalAmount: number;
  status: OrderStatus;

  customerName?: string;
  customerPhone?: string;
  deliveryAddress?: string;
  deliveryStatus?: DeliveryStatus;

  createdAt: string;
  updatedAt: string;

  payments: PaymentDetail[];
  storekeeperNotes?: string;
  cashierNotes?: string;

  reminderDate?: string;
  reminderNotes?: string;

  returnTransactions?: ReturnTransactionInfo[];
  linkedDemandNoticeId?: string; // To link back to a Demand Notice
}

export interface ExpressTransaction {
  id: string; // e.g. EXP-00001
  cashier_id: string;
  items: OrderItem[];
  total_amount: number;
  payment_method: 'cash' | 'card' | 'bank_transfer';
  payment_details?: Record<string, any>;
  timestamp: string;
}

export interface AttendanceLog {
  id: string;
  userId: string;
  timestamp: string;
  method?: 'button' | 'selfie'; // Add method to know how it was logged
  selfieDataUri?: string; // Kept for potential direct use or temporary storage before file saving
  selfieImagePath?: string; // Path to the saved image file
}

export interface BreakLog {
  id: string;
  userId: string;
  startTime: string;
  endTime?: string;
  durationMs?: number;
}

export type DemandNoticeStatus =
  'pending_review' |          // New DN, esp. for new products, awaiting admin check/product creation
  'awaiting_stock' |          // Product defined, awaiting stock
  'partial_stock_available' | // Some stock available, not all
  'full_stock_available' |    // All requested stock is available
  'customer_notified_stock' | // Salesperson informed customer of stock
  'awaiting_customer_action'| // Salesperson waiting for customer decision after notification
  'order_processing' |        // Salesperson clicked "Prepare the Order"; linked Order created/updated
  'preparing_stock' |         // Storekeeper is actively gathering items for this DN order
  'ready_for_collection' |    // Storekeeper has packed all items, ready for customer payment/pickup
  'fulfilled' |               // Fully paid and customer collected/delivered (if applicable)
  'cancelled';                // Cancelled by admin or salesperson

export interface DemandNotice {
  id: string; // Auto-generated, e.g., DN-timestamp-random
  salespersonId: string;
  salespersonName: string;
  customerContactNumber: string;

  productId?: string; // Optional: if existing product is chosen.
  productName: string; // Mandatory: User-entered or selected product name
  productSku: string;  // Mandatory: User-entered (for new) or system product code. Auto-generated for new.

  quantityRequested: number;
  quantityFulfilled?: number; // Track how much is actually available or has been allocated

  agreedPrice: number;
  expectedAvailabilityDate: string;
  status: DemandNoticeStatus;

  isNewProduct: boolean; // True if this DN is for a product not yet in inventory

  createdAt: string;
  updatedAt: string;
  notes?: string;

  payments?: PaymentDetail[]; // For advance payments on the DN
  linkedOrderId?: string; // ID of the Order created from this DN
}

export interface TaxSetting {
  id: string;
  name: string;
  rate: number;
  enabled: boolean;
}

export interface GlobalDiscountSetting {
  id: string;
  percentage: number;
  startDate: string | null;
  endDate: string | null;
  isActive: boolean;
  description?: string;
}

export interface CommissionSetting {
  id: string;
  salesTarget: number;
  commissionInterval: number;
  commissionPercentage: number;
  isActive: boolean;
}

export type SeriesId = 'invoice' | 'quotation' | 'demand_notice' | 'audit' | 'po';

export interface SeriesNumberSetting {
  id: SeriesId;
  nextNumber: number;
}


export interface AttendanceSetting {
  id: string;
  mandatory_attendance_time: string | null;
  is_mandatory_attendance_active: boolean;
  max_concurrent_breaks?: number | null;
}


export const ALL_PERMISSIONS_DEFINITIONS = [
  'view_admin_dashboard',
  'manage_products',
  'manage_orders',
  'manage_users',
  'manage_demand_notices',
  'manage_settings',
  'view_reports',
  'view_salesperson_reports',
  'manage_logistics',
  'manage_returns',
  'view_activity_logs',
  'manage_labels',
  'manage_cloud_files',
  'manage_audits',    // New permission for managing audit creation, assignment, viewing reports
  'conduct_audits',   // New permission for auditors to perform audits
  'manage_suppliers', // SCM Permission
  'create_pos',       // SCM Permission
  'approve_pos',      // SCM Permission
  'receive_stock',     // SCM Permission
  'express_checkout' // Express Role Permission
] as const;

export type Permission = typeof ALL_PERMISSIONS_DEFINITIONS[number];


export interface CustomItem {
  id: string;
  name: string;
  price: number;
}


export interface ExtendedOrderItem extends OrderItem {
  itemType: 'product' | 'custom';
  product?: Product;
  customItem?: CustomItem;
}


export interface ExtendedOrder extends Omit<Order, 'items'> {
  orderItems: ExtendedOrderItem[];
}


export interface CloudFileMetadata {
  file_id: string;
  userId: string;
  original_filename: string;
  saved_filename: string;
  path: string;
  public_url: string;
  file_type: string;
  file_size: number;
  upload_timestamp: string;
  notes?: string;
  ownerUsername?: string; // Added for admin file view
}


export type QuotationStatus = 'draft' | 'sent' | 'accepted' | 'rejected' | 'revision' | 'hold' | 'converted';

export interface Quotation {
  id: string;
  salespersonId: string;
  customerName?: string;
  customerPhone?: string;
  customerEmail?: string;
  customerAddress?: string;
  preparationDays: number;
  validUntil: string;
  status: QuotationStatus;
  createdAt: string;
  updatedAt: string;
  totalAmount: number;
  notes?: string;
  items?: QuotationItem[];
}

export interface QuotationItem {
  id: string;
  quotationId: string;
  productId?: string;
  productName: string;
  productSku?: string;
  price: number;
  quantity: number;
  isExternal: boolean;
  converted: boolean;
}

// Audit Feature Types
export type AuditStatus = 'pending' | 'in_progress' | 'completed' | 'cancelled';

export interface Audit {
  id: string; // e.g., AUD-000001
  title: string;
  adminId: string; // User ID of admin who launched
  auditorId?: string; // User ID of assigned auditor (can be nullable initially)
  storeLocation: string;
  status: AuditStatus;
  startedAt?: string; // ISO date
  completedAt?: string; // ISO date
  createdAt: string; // ISO date
  updatedAt: string; // ISO date
  auditorSelfiePath?: string; // Path to selfie at start
  items?: AuditItem[];
}

export interface AuditItem {
  id: string;
  auditId: string;
  productId?: string; // If it's a known product
  productName: string; // Name of the product or item being audited
  productSku?: string; // SKU if applicable
  currentStock: number; // System stock at audit launch
  finalAuditedQty?: number; // Final audited quantity after all counts (populated at audit completion)
  notes?: string; // Overall notes for this item's audit, if needed after counts
  createdAt: string; // ISO date
  updatedAt: string; // ISO date
  counts?: AuditItemCount[]; // Array of individual count events
}

// Represents one counting instance for an audit item
export interface AuditItemCount {
  id: string;
  auditItemId: string;
  count: number; // Quantity counted in this specific event
  notes?: string; // Notes specific to this count event
  createdAt: string; // ISO date of this count event
  images?: AuditImage[]; // Populated when fetching full details
}

export interface AuditImage {
  id: string;
  countEventId: string; // Links to AuditItemCount
  imagePath: string; // Path to the image file on the server
  createdAt: string; // ISO date when image was taken/uploaded
}

// Type for form data when adding items to an audit during launch
export interface AuditItemFormData {
  productId?: string;
  productName: string;
  productSku?: string;
  isManual: boolean; // To distinguish between selected product and manually added item
}

// Messaging System Types
export interface Conversation {
    id: string;
    subject: string;
    created_at: string;
    creator_id: string;
    lastMessageContent?: string;
    lastMessageAt?: string;
    lastMessageSender?: string;
    participants?: string;
    unreadCount?: number;
    readStatus?: 'read' | 'unread' | 'none'; // New field for sender's view
    folder?: 'inbox' | 'sent'; // Added for easier frontend filtering
}

export interface Message {
    id: string;
    conversation_id: string;
    sender_id: string;
    content: string;
    sent_at: string;
    // Populated by API logic
    sender?: Pick<User, 'id' | 'username'>;
    recipients?: MessageRecipient[];
    attachments?: Attachment[];
}

export type RecipientType = 'to' | 'cc' | 'bcc';

export interface MessageRecipient {
    id: string;
    message_id: string;
    recipient_id: string;
    recipient_type: RecipientType;
    read_at?: string | null;
    // Populated by API logic
    recipient?: Pick<User, 'id' | 'username'>;
}

export interface Attachment {
    id: string;
    message_id: string;
    file_path: string;
    original_name: string;
    mime_type: string;
}

// SCM Types
export interface Supplier {
  id: string;
  name: string;
  contact_email?: string | null;
  phone?: string | null;
  lead_time?: number | null;
  notes?: string | null;
  attachments?: SupplierAttachment[];
}

export interface SupplierAttachment {
  id: string;
  supplier_id: string;
  file_path: string;
  original_name: string;
  uploaded_at: string;
  uploaded_by_id?: string;
}

export interface SupplierProduct {
  id: string;
  supplier_id: string;
  product_id: string;
  unit_price: number;
  document_path?: string;
  lead_time?: number; // Added to display lead time
}

export interface POAttachment {
  id: string;
  po_id: string;
  file_path: string;
  original_name: string;
  notes?: string;
  uploaded_at: string;
  uploaded_by_id?: string;
  type?: 'grn' | 'storage_evidence' | 'other';
}

export interface PurchaseOrder {
  id: string;
  supplier_id: string;
  status: 'Draft' | 'Pending' | 'Confirmed' | 'Shipped' | 'Received' | 'Cancelled';
  total_amount?: number;
  advance_paid?: number;
  deadline?: string;
  expected_delivery?: string;
  invoice_path?: string;
  createdAt: string;
  updatedAt: string;
  items: POItem[];
  attachments?: POAttachment[];
  transportationDetails?: { // Changed from transportation_details
    vehicle_number?: string;
    driver_contact?: string;
    notes?: string;
    eta?: string;
  } | null;
}

export interface POItem {
  id: string;
  po_id: string;
  product_id: string;
  quantity_ordered: number;
  quantity_received: number;
}
