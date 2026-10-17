import type { Product, UserRole, Order, User, DemandNotice, DemandNoticeStatus, TaxSetting, GlobalDiscountSetting, Permission, CommissionSetting, SeriesNumberSetting, AttendanceSetting } from '@/types';
import { ALL_PERMISSIONS_DEFINITIONS } from '@/types';
import { format } from 'date-fns';
import { brandingConfig } from '@/config/branding'; // Import branding config

export const USER_ROLES: UserRole[] = ['salesperson', 'storekeeper', 'cashier', 'admin' , 'logistics', 'manager', 'auditor', 'display', 'express'];

export const DEMAND_NOTICE_STATUSES_WORKFLOW: DemandNoticeStatus[] = [
  'pending_review',
  'awaiting_stock',
  'partial_stock_available',
  'full_stock_available',
  'customer_notified_stock',
  'awaiting_customer_action',
  'order_processing',
  'preparing_stock',
  'ready_for_collection',
  'fulfilled',
  'cancelled'
];
// Keep this for simpler select filters if needed, or derive from workflow above
export const DEMAND_NOTICE_STATUSES: DemandNoticeStatus[] = [...DEMAND_NOTICE_STATUSES_WORKFLOW];


export const AVAILABLE_PERMISSIONS: Permission[] = ALL_PERMISSIONS_DEFINITIONS as Permission[];


export const APP_NAME = brandingConfig.appName; // Use appName from branding config

export const INITIAL_PRODUCTS: Product[] = [
  { id: 'prod_1', name: 'Eco-Friendly Water Bottle', price: 15.99, quantityInStock: 120, sku: 'SKU001', category: 'Drinkware', imageUrl: undefined, expiryDate: undefined, lowStockThreshold: 10, lowStockPrice: 17.99 },
  { id: 'prod_2', name: 'Organic Cotton Tote Bag', price: 22.50, quantityInStock: 85, sku: 'SKU002', category: 'Accessories', imageUrl: undefined, expiryDate: undefined },
  { id: 'prod_3', name: 'Wireless Bluetooth Headphones', price: 79.99, quantityInStock: 0, sku: 'SKU003', category: 'Electronics', imageUrl: undefined, expiryDate: undefined, lowStockThreshold: 5, lowStockPrice: 89.99 },
  { id: 'prod_4', name: 'Artisan Coffee Beans (1kg)', price: 25.00, quantityInStock: 200, sku: 'SKU004', category: 'Groceries', imageUrl: undefined, expiryDate: '2025-12-31' },
  { id: 'prod_5', name: 'Yoga Mat Premium', price: 45.00, quantityInStock: 70, sku: 'SKU005', category: 'Fitness', imageUrl: undefined, expiryDate: undefined },
  { id: 'prod_6', name: 'Stainless Steel Lunch Box', price: 30.00, quantityInStock: 5, sku: 'SKU006', category: 'Kitchenware', imageUrl: undefined, expiryDate: undefined, lowStockThreshold: 2, lowStockPrice: 33.00 },
  { id: 'prod_7', name: 'Notebook & Pen Set', price: 12.00, quantityInStock: 150, sku: 'SKU007', category: 'Stationery', imageUrl: undefined, expiryDate: undefined },
  { id: 'prod_8', name: 'Scented Soy Candle', price: 18.75, quantityInStock: 60, sku: 'SKU008', category: 'Home Decor', imageUrl: undefined, expiryDate: '2026-06-30' },
];

export const INITIAL_USERS: User[] = [
  { id: 'user_system', username: 'System', password: '', role: 'admin', permissions: [], activeBreakId: null }, // System user for notifications
  { id: 'user_admin', username: 'admin', password: 'password123', role: 'admin', permissions: AVAILABLE_PERMISSIONS, activeBreakId: null },
  {
    id: 'user_manager1',
    username: 'manager1',
    password: 'password123',
    role: 'manager',
    permissions: [
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
      'manage_audits',
      'manage_suppliers',
      'create_pos',
      'approve_pos',
      'receive_stock'
    ] as Permission[],
    activeBreakId: null
  },
  {
    id: 'user_manager2',
    username: 'manager2',
    password: 'password123',
    role: 'manager',
    permissions: [
        'view_admin_dashboard',
        'manage_products',
        'view_reports',
        'manage_labels',
        'manage_cloud_files' 
    ] as Permission[],
    activeBreakId: null
  },
  { id: 'user_sales', username: 'sales1', password: 'password123', role: 'salesperson', activeBreakId: null, permissions: ['upload_cloud', 'delete_cloud_file', 'edit_cloud_notes'] },
  { id: 'user_sales2', username: 'sales2', password: 'password123', role: 'salesperson', activeBreakId: null, permissions: ['upload_cloud', 'delete_cloud_file', 'edit_cloud_notes'] },
  { id: 'user_store', username: 'storekeep1', password: 'password123', role: 'storekeeper', activeBreakId: null, permissions: ['upload_cloud', 'delete_cloud_file', 'edit_cloud_notes'] },
  { id: 'user_cash', username: 'cashier1', password: 'password123', role: 'cashier', activeBreakId: null, permissions: ['upload_cloud', 'delete_cloud_file', 'edit_cloud_notes'] },
  { id: 'user_logistics', username: 'logistics1', password: 'password123', role: 'logistics', activeBreakId: null, permissions: ['upload_cloud', 'delete_cloud_file', 'edit_cloud_notes']},
  { id: 'user_auditor1', username: 'auditor1', password: 'password123', role: 'auditor', activeBreakId: null, permissions: ['conduct_audits', 'upload_cloud', 'delete_cloud_file', 'edit_cloud_notes'] },
  { id: 'user_display', username: 'lcd', password: 'lcdpassword', role: 'display', permissions: [], activeBreakId: null },
  { id: 'user_express', username: 'express1', password: 'password123', role: 'express', permissions: ['express_checkout'], activeBreakId: null },
];

export const INITIAL_TAX_SETTINGS: TaxSetting[] = [
  { id: 'gst', name: 'GST', rate: 0.05, enabled: true },
  { id: 'service_tax', name: 'Service Tax', rate: 0.10, enabled: false }
];

export const INITIAL_GLOBAL_DISCOUNT_SETTING: GlobalDiscountSetting | null = null;

export const INITIAL_COMMISSION_SETTING: CommissionSetting = {
  id: 'global_commission_rules',
  salesTarget: 5000,
  commissionInterval: 1000,
  commissionPercentage: 2,
  isActive: false,
};

export const INITIAL_INVOICE_NUMBER_SETTING: SeriesNumberSetting = {
  id: 'invoice', 
  nextNumber: 1,
};
export const INITIAL_QUOTATION_NUMBER_SETTING: SeriesNumberSetting = {
  id: 'quotation',
  nextNumber: 1,
};
export const INITIAL_DEMAND_NOTICE_NUMBER_SETTING: SeriesNumberSetting = {
  id: 'demand_notice',
  nextNumber: 1,
};
export const INITIAL_AUDIT_NUMBER_SETTING: SeriesNumberSetting = {
  id: 'audit',
  nextNumber: 1,
};

export const INITIAL_ATTENDANCE_SETTING: AttendanceSetting = {
  id: 'global_attendance_config',
  mandatory_attendance_time: "09:00",
  is_mandatory_attendance_active: false,
  max_concurrent_breaks: null, 
};


export const ALL_ORDER_STATUSES_FOR_FILTERING: Order['status'][] = ['pending_payment', 'partial_payment', 'preparing', 'ready_for_pickup', 'paid', 'completed', 'cancelled', 'returned'];


export const INITIAL_ORDERS: Order[] = [
  {
    id: 'S000001A', 
    primarySalespersonId: 'user_sales',
    primarySalespersonName: 'sales1',
    primarySalespersonCommission: 1.0,
    items: [
      { productId: 'prod_1', name: 'Eco-Friendly Water Bottle', sku: 'SKU001', quantity: 2, pricePerUnit: 15.99, totalPrice: 31.98 },
      { productId: 'prod_3', name: 'Wireless Bluetooth Headphones', sku: 'SKU003', quantity: 1, pricePerUnit: 79.99, totalPrice: 79.99 },
    ],
    subtotal: 111.97,
    discountAmount: 10.00,
    appliedDiscountPercentage: (10.00 / 111.97) * 100,
    taxes: [{ name: 'GST', rate: 0.05, amount: 5.10 }],
    totalAmount: 107.07,
    status: 'pending_payment',
    deliveryStatus: 'pending_dispatch',
    customerName: 'John Doe',
    customerPhone: '555-1234',
    deliveryAddress: '123 Main St, Anytown',
    createdAt: new Date(Date.now() - 100000).toISOString(),
    updatedAt: new Date(Date.now() - 100000).toISOString(),
    payments: [],
    returnTransactions: [],
  }
];

export const INITIAL_DEMAND_NOTICES: DemandNotice[] = [
  {
    id: 'DN-SAMPLE-1', 
    salespersonId: 'user_sales',
    salespersonName: 'sales1',
    customerContactNumber: '98765432',
    productId: 'prod_3',
    productName: 'Wireless Bluetooth Headphones',
    productSku: 'SKU003',
    quantityRequested: 2,
    agreedPrice: 75.00,
    expectedAvailabilityDate: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
    status: 'awaiting_stock',
    isNewProduct: false,
    quantityFulfilled: 0,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    notes: 'Customer needs this urgently for a gift.',
    payments: [],
  },
  {
    id: 'DN-SAMPLE-2', 
    salespersonId: 'user_sales2',
    salespersonName: 'sales2',
    customerContactNumber: '91122334',
    
    productName: 'Custom Gaming Mousepad',
    productSku: 'DN-CUSGAMPAD-334-' + format(new Date(), "ddMMyy"), 
    quantityRequested: 10,
    agreedPrice: 28.00,
    expectedAvailabilityDate: new Date(Date.now() + 14 * 24 * 60 * 60 * 1000).toISOString(),
    status: 'pending_review',
    isNewProduct: true,
    quantityFulfilled: 0,
    createdAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    updatedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    notes: 'Willing to wait for new stock. Requires specific design.',
    payments: [],
  }
];
