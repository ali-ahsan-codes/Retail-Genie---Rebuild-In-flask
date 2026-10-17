
// src/context/AppContext.tsx
"use client";
import type { ReactNode }from 'react';
import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import type { Product, Order, CartItem, User, UserRole, AttendanceLog, BreakLog, DeliveryStatus, DemandNotice, DemandNoticeStatus, TaxSetting, GlobalDiscountSetting, Permission, OrderItem, PaymentDetail, ReturnTransactionInfo, CommissionSetting, SeriesNumberSetting, AttendanceSetting, Quotation, QuotationStatus, QuotationItem, SeriesId, Audit, AuditItem, AuditItemCount, AuditImage, AuditItemFormData as LaunchAuditItemData, Conversation, Message, Supplier, PurchaseOrder } from '@/types';
import { format, parse, parseISO, startOfDay, isValid, setHours as dateFnsSetHours, setMinutes as dateFnsSetMinutes, setSeconds as dateFnsSetSeconds, setMilliseconds as dateFnsSetMilliseconds, isSameDay } from 'date-fns';
import {
  getProductsFromDb, addProductToDb as apiAddProductToDb, updateProductInDb as apiUpdateProductInDb, deleteProductFromDb as apiDeleteProductFromDb,
  getUsersFromDb, addUserToDb, updateUserInDb as apiUpdateUserInDb, deleteUserFromDb, getUserByUsernameFromDb,
  getOrdersFromDb, addOrderToDb, updateOrderInDb as apiUpdateOrderInDb, deleteOrderFromDb, getOrderByIdFromDb,
  getAttendanceLogsFromDb, addAttendanceLogToDb,
  getBreakLogsFromDb, addBreakLogToDb, updateBreakLogInDb,
  getDemandNoticesFromDb, addDemandNoticeToDb, updateDemandNoticeInDb, deleteDemandNoticeFromDb,
  getTaxSettingsFromDb, updateTaxSettingsInDb,
  getGlobalDiscountSettingFromDb, updateGlobalDiscountSettingInDb,
  getCommissionSettingFromDb, updateCommissionSettingInDb,
  getSeriesNumberSettingsFromDb, updateSeriesNumberSettingInDb,
  getAttendanceSettingFromDb, updateAttendanceSettingInDb,
  addQuotationToDb, getQuotationsFromDb, getQuotationByIdFromDb as apiGetQuotationByIdFromDb, updateQuotationInDb, deleteQuotationFromDb,
  getSuppliers as apiGetSuppliers, getPurchaseOrders as apiGetPurchaseOrders,
  ApiError,
} from '@/lib/database';
import { useToast } from '@/hooks/use-toast';
import ClientOnly from '@/components/layout/ClientOnly';
import TowerLoader from '@/components/layout/TowerLoader';
import { useOptimisticMutation } from '@/hooks/useOptimisticMutation'; // Import the hook
import { useRouter } from 'next/navigation';
import { ToastAction } from '@/components/ui/toast'; // Import ToastAction

const API_BASE_URL_CONTEXT = '/api';

const getAutoRefreshInterval = () => {
  if (typeof window !== 'undefined' && window.location.hostname === 'localhost') { // More reliable check for dev
    return 15000; // 15 seconds in development
  }
  return 5000; // 5 seconds in production or other environments
};

const AUTO_REFRESH_INTERVAL = getAutoRefreshInterval();


interface AddProductResult {
  success: boolean;
  product?: Product | null;
  error?: string;
  queued?: boolean; // Added for optimistic updates
  offlineId?: string; // Added for optimistic updates
}
interface UpdateProductResult {
  success: boolean;
  product?: Product | null;
  error?: string;
  queued?: boolean;
  offlineId?: string;
}
interface DeleteProductResult {
  success: boolean;
  error?: string;
  queued?: boolean;
  offlineId?: string;
}

interface LaunchAuditPayload {
    title: string;
    auditorId: string;
    storeLocation: string;
    items: LaunchAuditItemData[];
}


interface AppContextType {
  currentUser: User | null;
  setCurrentUser: (user: User | null) => void;
  hasPermission: (permission: Permission) => boolean;

  products: Product[];
  setProducts: React.Dispatch<React.SetStateAction<Product[]>>;
  addProduct: (productData: Omit<Product, 'id'>) => Promise<AddProductResult>;
  updateProduct: (product: Product) => Promise<UpdateProductResult>;
  deleteProduct: (productId: string) => Promise<DeleteProductResult>;

  orders: Order[];
  setOrders: React.Dispatch<React.SetStateAction<Order[]>>;
  updateOrderAndRefreshContext: (orderToSave: Order) => Promise<Order | null>;
  users: User[];
  setUsers: React.Dispatch<React.SetStateAction<User[]>>;
  updateUserInDb: (user: User) => Promise<User | { queued: true; offlineId: string; } | null>;
  cart: CartItem[];
  addToCart: (product: Product, quantity: number) => void;
  removeFromCart: (productId: string) => void;
  updateCartItemQuantity: (productId: string, quantity: number) => void;
  updateCartItemPrice: (productId: string, newPrice: number) => void;
  clearCart: () => void;
  addOrder: (orderData: Omit<Order, 'id' | 'createdAt' | 'updatedAt' | 'status' | 'deliveryStatus' | 'appliedGlobalDiscountPercentage' | 'returnTransactions'> & {
    primarySalespersonId: string;
    primarySalespersonName?: string;
    customerName?: string;
    customerPhone?: string;
    deliveryAddress?: string;
    secondarySalespersonId?: string;
    primarySalespersonCommission?: number;
    secondarySalespersonCommission?: number;
    payments?: PaymentDetail[];
    linkedDemandNoticeId?: string;
  }) => Promise<Order | null>;
  updateOrderStatus: (orderId: string, status: Order['status']) => Promise<void>;
  updateProductStock: (productId: string, quantityChange: number) => Promise<void>;
  getProductById: (productId: string) => Product | undefined;
  getProductBySku: (sku: string) => Product | undefined;
  getOrderById: (orderId: string) => Order | undefined;
  getEffectiveProductPrice: (product: Product) => number;


  attendanceLogs: AttendanceLog[];
  setAttendanceLogsState: React.Dispatch<React.SetStateAction<AttendanceLog[]>>;
  breakLogs: BreakLog[];
  setBreakLogsState: React.Dispatch<React.SetStateAction<BreakLog[]>>;
  addAttendanceLog: (userId: string, method: 'button' | 'selfie', selfieDataUri?: string) => Promise<AttendanceLog | null>;
  startBreak: (userId: string) => Promise<BreakLog | null>;
  endBreak: (userId: string, breakId?: string) => Promise<BreakLog | null>;
  getAttendanceLogsForUser: (userId: string) => AttendanceLog[];
  getBreakLogsForUser: (userId: string) => BreakLog[];
  getCurrentBreakForUser: (userId: string) => BreakLog | undefined;
  getTodayAttendanceForUser: (userId: string) => AttendanceLog | undefined;
  isAttendanceCurrentlyRequired: (role: UserRole) => boolean;
  canUserStartBreak: () => { canStart: boolean; reason?: string };

  demandNotices: DemandNotice[];
  setDemandNoticesState: React.Dispatch<React.SetStateAction<DemandNotice[]>>;
  addDemandNotice: (noticeData: Omit<DemandNotice, 'id' | 'createdAt' | 'updatedAt' | 'status' | 'salespersonId' | 'salespersonName'> & {productName: string, productSku?: string} ) => Promise<DemandNotice | null>;
  updateDemandNoticeStatus: (noticeId: string, status: DemandNoticeStatus, byUser?: User | null) => Promise<void>;
  deleteDemandNotice: (noticeId: string) => Promise<void>;
  getDemandNoticesForSalesperson: (salespersonId: string) => DemandNotice[];
  getAllDemandNotices: () => Promise<DemandNotice[]>;
  addAdvancePaymentToDemandNotice: (noticeId: string, payment: PaymentDetail) => Promise<DemandNotice | null>;
  prepareOrderFromDemandNotice: (noticeId: string) => Promise<Order | null>;


  taxSettings: TaxSetting[];
  setTaxSettingsState: React.Dispatch<React.SetStateAction<TaxSetting[]>>;
  updateTaxSettings: (newSettings: TaxSetting[]) => Promise<void>;

  globalDiscountSetting: GlobalDiscountSetting | null;
  setGlobalDiscountSettingState: React.Dispatch<React.SetStateAction<GlobalDiscountSetting | null>>;
  updateGlobalDiscountSetting: (setting: GlobalDiscountSetting | null) => Promise<void>;

  commissionSetting: CommissionSetting | null;
  setCommissionSettingState: React.Dispatch<React.SetStateAction<CommissionSetting | null>>;
  updateCommissionSetting: (setting: CommissionSetting | null) => Promise<void>;

  seriesNumberSettings: Record<SeriesId, SeriesNumberSetting>;
  setSeriesNumberSettingsState: React.Dispatch<React.SetStateAction<Record<SeriesId, SeriesNumberSetting>>>;
  updateSeriesNumberSettings: (setting: SeriesNumberSetting) => Promise<void>;


  attendanceSetting: AttendanceSetting | null;
  setAttendanceSettingState: React.Dispatch<React.SetStateAction<AttendanceSetting | null>>;
  updateAttendanceSetting: (setting: AttendanceSetting | null) => Promise<void>;

  loadDataFromDb: (options?: { isInitialLoad?: boolean }) => Promise<void>;

  transferOrder: (orderId: string, newPrimarySalespersonId: string, newSecondarySalespersonId?: string, commissionSplit?: { primary: number; secondary: number }) => Promise<void>;
  updateOrderDeliveryStatus: (orderId: string, deliveryStatus: DeliveryStatus) => Promise<void>;
  setOrderReminder: (orderId: string, reminderDate: string, reminderNotes: string) => Promise<void>;
  processDetailedReturn: (
    orderId: string,
    itemsToReturn: ReturnItemDetail[],
    refundPaymentDetails: PaymentDetail[],
    returnReason?: string,
    exchangeNotes?: string
  ) => Promise<boolean>;
  isDataLoaded: boolean;
  isBackgroundRefreshing: boolean;


  quotations: Quotation[];
  setQuotationsState: React.Dispatch<React.SetStateAction<Quotation[]>>;
  addQuotation: (quotationData: Omit<Quotation, 'id' | 'createdAt' | 'updatedAt' | 'salespersonId' | 'items'> & { items: Omit<QuotationItem, 'id' | 'quotationId' | 'converted'>[] }) => Promise<Quotation | null>;
  getQuotationById: (quotationId: string) => Promise<Quotation | undefined>;
  updateQuotation: (quotationData: Partial<Quotation> & {id: string}) => Promise<Quotation | null>;
  deleteQuotation: (quotationId: string) => Promise<void>;
  getQuotationsForSalesperson: (salespersonId: string) => Quotation[];
  convertQuotationToDemandNotices: (quotationId: string) => Promise<{ createdDemandNoticeIds: string[] } | null>;
  convertQuotationToOrder: (quotationId: string) => Promise<Order | null>;

  // Audit Feature State and Functions
  audits: Audit[];
  setAuditsState: React.Dispatch<React.SetStateAction<Audit[]>>;
  createAudit: (auditData: LaunchAuditPayload) => Promise<Audit | null>;
  getAuditById: (auditId: string) => Promise<Audit | undefined>;
  startAudit: (auditId: string, selfieFile: File) => Promise<Audit | null>;
  completeAudit: (auditId: string) => Promise<Audit | null>;
  recordAuditItemCountWithImage: (
    auditId: string,
    auditItemId: string,
    count: number,
    notes?: string,
    imageFile?: File
  ) => Promise<AuditItemCount | null>;

  // Messaging Feature State and Functions
  conversations: Conversation[];
  totalUnreadCount: number;
  sendNewMessage: (subject: string, content: string, to: string[], cc: string[], bcc: string[], attachments: File[], forwardedAttachmentIds?: string[]) => Promise<{ conversation_id: string } | null>;
  replyToConversation: (conversationId: string, content: string, to: string[], cc: string[], bcc: string[], attachments: File[]) => Promise<Message | null>;
  deleteConversation: (conversationId: string) => Promise<void>;
  
  // SCM State and Functions
  suppliers: Supplier[];
  purchaseOrders: PurchaseOrder[];
}

const AppContext = createContext<AppContextType | undefined>(undefined);

const LOCAL_STORAGE_CURRENT_USER_KEY = 'retail_genie_currentUser';


export const AppProvider = ({ children }: { children: ReactNode }) => {
  const [currentUser, setCurrentUserInternal] = useState<User | null>(null);
  const [productsState, setProductsState] = useState<Product[]>([]);
  const [ordersState, setOrdersState] = useState<Order[]>([]);
  const [usersState, setUsersState] = useState<User[]>([]);
  const [cartState, setCartState] = useState<CartItem[]>([]);
  const [attendanceLogsState, setAttendanceLogsState] = useState<AttendanceLog[]>([]);
  const [breakLogsState, setBreakLogsState] = useState<BreakLog[]>([]);
  const [demandNoticesState, setDemandNoticesState] = useState<DemandNotice[]>([]);
  const [taxSettingsState, setTaxSettingsState] = useState<TaxSetting[]>([]);
  const [globalDiscountSettingState, setGlobalDiscountSettingState] = useState<GlobalDiscountSetting | null>(null);
  const [commissionSettingState, setCommissionSettingState] = useState<CommissionSetting | null>(null);
  const [seriesNumberSettingsState, setSeriesNumberSettingsState] = useState<Record<SeriesId, SeriesNumberSetting>>(
    { invoice: { id: 'invoice', nextNumber: 1 }, quotation: { id: 'quotation', nextNumber: 1 }, demand_notice: { id: 'demand_notice', nextNumber: 1 }, audit: { id: 'audit', nextNumber: 1 }, po: {id: 'po', nextNumber: 1} }
  );
  const [attendanceSettingState, setAttendanceSettingState] = useState<AttendanceSetting | null>(null);
  const [quotationsState, setQuotationsState] = useState<Quotation[]>([]);
  const [auditsState, setAuditsState] = useState<Audit[]>([]); // New state for audits
  
  const [conversationsState, setConversationsState] = useState<Conversation[]>([]);
  const [totalUnreadCount, setTotalUnreadCount] = useState(0);
  const previousUnreadCountRef = useRef<number>(0);

  const [suppliersState, setSuppliersState] = useState<Supplier[]>([]);
  const [purchaseOrdersState, setPurchaseOrdersState] = useState<PurchaseOrder[]>([]);
  
  const [isDataLoaded, setIsDataLoaded] = useState(false);
  const [isBackgroundRefreshing, setIsBackgroundRefreshing] = useState(false);
  const [hasMounted, setHasMounted] = useState(false);
  const initialLoadComplete = useRef(false);
  const { toast } = useToast();
  const router = useRouter();


  const setCurrentUser = useCallback((user: User | null) => {
    setCurrentUserInternal(user);
    if (typeof window !== 'undefined') {
      if (user) {
        const userToStore: Omit<User, 'password'> = { ...user };
        delete userToStore.password;
        localStorage.setItem(LOCAL_STORAGE_CURRENT_USER_KEY, JSON.stringify(userToStore));
      } else {
        localStorage.removeItem(LOCAL_STORAGE_CURRENT_USER_KEY);
      }
    }
  }, []);

  const hasPermission = useCallback((permission: Permission): boolean => {
    if (!currentUser) return false;
    if (currentUser.role === 'admin') return true;
    if (currentUser.role === 'manager') {
      return currentUser.permissions?.includes(permission) ?? false;
    }
    // Auditor specific permissions
    if (currentUser.role === 'auditor' && permission === 'conduct_audits') {
        return true;
    }
    return false;
  }, [currentUser]);

  const loadDataFromDb = useCallback(async (options: { isInitialLoad?: boolean } = {}) => {
    const { isInitialLoad = false } = options;
    let tempUserIdForAuth: string | undefined = undefined;
    let tempCurrentUserForAuth: User | null = null;

    if (isInitialLoad) {
        const storedUserJson = typeof window !== 'undefined' ? localStorage.getItem(LOCAL_STORAGE_CURRENT_USER_KEY) : null;
        if (storedUserJson) {
            try {
                tempCurrentUserForAuth = JSON.parse(storedUserJson) as User;
                tempUserIdForAuth = tempCurrentUserForAuth?.id;
            } catch (e) { console.warn("Failed to parse stored user for initial auth."); }
        }
    } else {
        tempCurrentUserForAuth = currentUser;
        tempUserIdForAuth = currentUser?.id;
        setIsBackgroundRefreshing(true);
    }
    
    const userForApiCall = tempUserIdForAuth;

    try {
      const fetchAudits = async () => {
        if (!tempCurrentUserForAuth || !tempCurrentUserForAuth.id) return [];
        const response = await fetch(`${API_BASE_URL_CONTEXT}/audits`, {
          headers: { 'x-user-id': tempCurrentUserForAuth.id }
        });
        if (!response.ok) {
            console.warn("Failed to fetch audits, API error", response.status)
            return [];
        }
        const apiResponse = await response.json();
        if (apiResponse.success && Array.isArray(apiResponse.data)) {
            return apiResponse.data;
        } else {
            console.warn("Failed to fetch audits or unexpected API response format:", apiResponse);
            return [];
        }
      };

      const fetchConversations = async () => {
        if (!userForApiCall) return [];
        const response = await fetch(`${API_BASE_URL_CONTEXT}/messaging/conversations`, {
          headers: { 'x-user-id': userForApiCall }
        });
        if (!response.ok) {
          console.warn("Failed to fetch conversations, API error", response.status);
          return [];
        }
        const apiResponse = await response.json();
        return (apiResponse.success && Array.isArray(apiResponse.data)) ? apiResponse.data : [];
      };

      const dataPromises = [
        getProductsFromDb(), getUsersFromDb(), getOrdersFromDb(), getAttendanceLogsFromDb(),
        getBreakLogsFromDb(), getDemandNoticesFromDb(), getTaxSettingsFromDb(),
        getGlobalDiscountSettingFromDb(), getCommissionSettingFromDb(), getSeriesNumberSettingsFromDb(),
        getAttendanceSettingFromDb(),
        (tempCurrentUserForAuth?.role === 'salesperson' || tempCurrentUserForAuth?.role === 'admin' || tempCurrentUserForAuth?.role === 'manager') && tempUserIdForAuth
          ? getQuotationsFromDb(tempUserIdForAuth)
          : Promise.resolve([] as Quotation[]),
        fetchAudits(),
        fetchConversations(),
        apiGetSuppliers(), // Fetch suppliers
        apiGetPurchaseOrders(), // Fetch POs
      ];

      const [
        loadedProducts, loadedUsers, loadedOrders, loadedAttendanceLogs,
        loadedBreakLogs, loadedDemandNotices, loadedTaxSettings,
        loadedGlobalDiscount, loadedCommissionSetting, loadedSeriesSettings,
        loadedAttendanceSetting, loadedQuotations, loadedAudits, loadedConversations,
        loadedSuppliers, loadedPurchaseOrders
      ] = await Promise.all(dataPromises);

      setProductsState(loadedProducts.sort((a,b) => a.name.localeCompare(b.name)));
      setUsersState(loadedUsers.sort((a,b) => a.username.localeCompare(b.username)));
      setOrdersState(loadedOrders.sort((a, b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime()));
      setAttendanceLogsState(loadedAttendanceLogs);
      setBreakLogsState(loadedBreakLogs);
      setDemandNoticesState(loadedDemandNotices.sort((a,b) => parseISO(b.createdAt).getTime() - new Date(a.createdAt).getTime()));
      setTaxSettingsState(loadedTaxSettings);
      setGlobalDiscountSettingState(loadedGlobalDiscount);
      setSeriesNumberSettingsState(loadedSeriesSettings || { invoice: { id: 'invoice', nextNumber: 1 }, quotation: { id: 'quotation', nextNumber: 1 }, demand_notice: { id: 'demand_notice', nextNumber: 1 }, audit: { id: 'audit', nextNumber: 1 }, po: {id: 'po', nextNumber: 1} });
      setAttendanceSettingState(loadedAttendanceSetting);
      setQuotationsState(loadedQuotations.sort((a, b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime()));
      setAuditsState(loadedAudits.sort((a: Audit, b: Audit) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime()));
      setConversationsState(loadedConversations);
      setSuppliersState(loadedSuppliers.sort((a,b) => a.name.localeCompare(b.name))); // Set suppliers
      setPurchaseOrdersState(loadedPurchaseOrders.sort((a,b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime())); // Set POs

      const newTotalUnread = loadedConversations.reduce((sum: number, convo: Conversation) => sum + (convo.unreadCount || 0), 0);
      setTotalUnreadCount(newTotalUnread);

      // Moved notification logic here, with a role check.
      const currentActiveUser = isInitialLoad ? tempCurrentUserForAuth : currentUser;
      if (!isInitialLoad && currentActiveUser?.role !== 'display' && newTotalUnread > previousUnreadCountRef.current) {
        const newMessagesCount = newTotalUnread - previousUnreadCountRef.current;
        toast({
          title: "New Message Received",
          description: `You have ${newMessagesCount} new message${newMessagesCount > 1 ? 's' : ''}.`,
          action: (
            <ToastAction altText="View" onClick={() => router.push('/messaging')}>
              View
            </ToastAction>
          ),
        });
      }
      previousUnreadCountRef.current = newTotalUnread;

      if (isInitialLoad && tempCurrentUserForAuth) {
          const systemUser = loadedUsers.find(u => u.id === tempCurrentUserForAuth!.id);
          if (systemUser) {
              const fullSystemUser = await getUserByUsernameFromDb(systemUser.username);
              if (fullSystemUser && fullSystemUser.password) {
                  setCurrentUserInternal(fullSystemUser);
              } else if (fullSystemUser) {
                  setCurrentUserInternal({ ...fullSystemUser, password: tempCurrentUserForAuth.password });
              } else {
                  setCurrentUser(null);
              }
          } else {
              setCurrentUser(null);
          }
      }
      return Promise.resolve();
    } catch (error) {
      console.warn("Data sync failed (AppContext):", error);
      toast({ title: "Data Sync Failed", description: "Could not fetch latest data.", variant: "destructive" });
      return Promise.resolve();
    } finally {
        if (!isInitialLoad) {
            setIsBackgroundRefreshing(false);
        }
    }
  }, [currentUser, setCurrentUser, toast, router]);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  // Effect for the very first data load
  useEffect(() => {
    if (hasMounted && !initialLoadComplete.current) {
      console.log("[AppContext] Starting initial data load sequence...");
      setIsDataLoaded(false);
      loadDataFromDb({ isInitialLoad: true })
        .then(() => {
          console.log("[AppContext] Initial data load sequence successful.");
          initialLoadComplete.current = true;
        })
        .catch(error => {
          console.error("[AppContext] Critical error during initial data load sequence:", error);
          initialLoadComplete.current = true;
        })
        .finally(() => {
          setIsDataLoaded(true);
        });
    }
  }, [hasMounted, loadDataFromDb]);

  // Effect for periodic background refresh
  useEffect(() => {
    if (!initialLoadComplete.current || !hasMounted) return;

    const intervalId = setInterval(() => {
      console.log(`[AppContext] Performing periodic background data sync... Interval: ${AUTO_REFRESH_INTERVAL / 1000}s`);
      loadDataFromDb({ isInitialLoad: false })
        .catch(err => {
          // Error already handled and toasted within loadDataFromDb
        });
    }, AUTO_REFRESH_INTERVAL);

    return () => clearInterval(intervalId);
  }, [initialLoadComplete, hasMounted, loadDataFromDb]);

  // Effect for focus/visibility refresh
  useEffect(() => {
    if (!initialLoadComplete.current || !hasMounted || typeof window === 'undefined') return;

    const handleFocusOrVisibility = () => {
      if (document.visibilityState === 'visible') {
        console.log("[AppContext] Performing background data sync on focus/visibility change...");
        loadDataFromDb({ isInitialLoad: false })
          .catch(err => {});
      }
    };

    window.addEventListener('visibilitychange', handleFocusOrVisibility);
    window.addEventListener('focus', handleFocusOrVisibility);

    return () => {
      window.removeEventListener('visibilitychange', handleFocusOrVisibility);
      window.removeEventListener('focus', handleFocusOrVisibility);
    };
  }, [initialLoadComplete, hasMounted, loadDataFromDb]);


  const updateUserInDb = useCallback(async (user: User) => {
    if (!currentUser || !hasPermission('manage_users') && currentUser.id !== user.id) {
        toast({ title: "Permission Denied", description: "You do not have permission to update this user.", variant: "destructive" });
        return null;
    }
    const result = await apiUpdateUserInDb(user);
    if (result && !('queued' in result)) {
        await loadDataFromDb({isInitialLoad: false});
        if (currentUser?.id === user.id) {
            setCurrentUser(result);
        }
    }
    return result;
  }, [currentUser, hasPermission, toast, loadDataFromDb, setCurrentUser]);

  const updateProductStock = useCallback(async (productId: string, quantityChange: number): Promise<void> => {
    try {
      const product = productsState.find(p => p.id === productId);
      if (!product) throw new Error("Product not found for stock update");
      const updatedProduct = { ...product, quantityInStock: Math.max(0, product.quantityInStock + quantityChange) };
      const result = await apiUpdateProductInDb(updatedProduct);
      if (result && !('queued' in result)) {
        setProductsState(prev => prev.map(p => p.id === productId ? updatedProduct : p).sort((a,b) => a.name.localeCompare(b.name)));
      }
    } catch (error) {
      console.warn("Failed to update product stock via API:", error);
      toast({ title: "Stock Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [productsState, toast]);

  const addAttendanceLog = useCallback(async (userId: string, method: 'button' | 'selfie', selfieDataUri?: string): Promise<AttendanceLog | null> => {
    try {
      const newLog = await addAttendanceLogToDb({ userId, timestamp: new Date().toISOString(), method, selfieDataUri });
      if (newLog && !('queued' in newLog)) {
        await loadDataFromDb({ isInitialLoad: false });
        // Re-fetch the specific log to ensure it's the latest from DB
        const refreshedLogs = await getAttendanceLogsFromDb();
        const confirmedLog = refreshedLogs.find(log => log.id === newLog.id);
        return confirmedLog || newLog;
      }
      return null;
    } catch (error) {
      console.warn("Failed to add attendance log via API:", error);
      toast({ title: "Attendance Log Failed", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [toast, loadDataFromDb]);

  const startBreak = useCallback(async (userId: string): Promise<BreakLog | null> => {
    try {
      const newBreak = await addBreakLogToDb({ userId, startTime: new Date().toISOString() });
      if (newBreak && !('queued' in newBreak)) {
        await loadDataFromDb({ isInitialLoad: false });
        const refreshedBreaks = await getBreakLogsFromDb();
        const confirmedBreak = refreshedBreaks.find(b => b.id === newBreak.id);
        return confirmedBreak || newBreak;
      }
      return null;
    } catch (error) {
      console.warn("Failed to start break via API:", error);
      if (error instanceof ApiError && error.status === 409 && error.message && error.message.toLowerCase().includes('already on an active break')) {
        toast({ title: "Already on Break", description: error.message, variant: "default" });
      } else {
        toast({ title: "Start Break Failed", description: (error as Error).message, variant: "destructive" });
      }
      return null;
    }
  }, [toast, loadDataFromDb]);

  const endBreak = useCallback(async (userId: string, breakId?: string): Promise<BreakLog | null> => {
    try {
      const activeBreak = breakId ? breakLogsState.find(b => b.id === breakId && b.userId === userId && !b.endTime)
                                  : breakLogsState.find(b => b.userId === userId && !b.endTime);
      if (!activeBreak) throw new Error("No active break found to end or break ID mismatch.");

      const endedBreak = await updateBreakLogInDb({ ...activeBreak, endTime: new Date().toISOString() });
      if (endedBreak && !('queued' in endedBreak)) {
        await loadDataFromDb({ isInitialLoad: false });
        const refreshedBreaks = await getBreakLogsFromDb();
        const confirmedBreak = refreshedBreaks.find(b => b.id === endedBreak.id);
        return confirmedBreak || endedBreak;
      }
      return null;
    } catch (error) {
      console.warn("Failed to end break via API:", error);
      toast({ title: "End Break Failed", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [breakLogsState, toast, loadDataFromDb]);


  const updateDemandNoticeStatus = useCallback(async (noticeId: string, status: DemandNoticeStatus, byUser?: User | null): Promise<void> => {
    const actingUser = byUser || currentUser;
    if (!actingUser) {
        toast({title: "Error", description: "User context not available for updating notice.", variant: "destructive"});
        return;
    }
    const noticeToUpdate = demandNoticesState.find(n => n.id === noticeId);
    if (!noticeToUpdate) {
        toast({title: "Error", description: "Demand notice not found.", variant: "destructive"});
        return;
    }
    try {
        const payloadForServer: Partial<DemandNotice> & { id: string; status: DemandNoticeStatus; updatedAt: string } = {
            id: noticeId,
            status: status,
            updatedAt: new Date().toISOString(),
        };
        const updatedNoticeFromServer = await updateDemandNoticeInDb(payloadForServer as DemandNotice);
        if (updatedNoticeFromServer && !('queued'in updatedNoticeFromServer)) {
           await loadDataFromDb({isInitialLoad: false});
        }
    } catch (error) {
        console.warn("Failed to update demand notice status via API:", error);
        toast({ title: "Demand Notice Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [currentUser, demandNoticesState, loadDataFromDb, toast]);


   useEffect(() => {
    if (!initialLoadComplete.current || !hasMounted) return;

    const checkAndUpdateDemandNotices = async () => {
      let changed = false;
      const currentDNs = [...demandNoticesState];

      for (let i = 0; i < currentDNs.length; i++) {
        const notice = currentDNs[i];
        if (notice.status === 'pending_review' || notice.status === 'awaiting_stock' || notice.status === 'partial_stock_available') {
          const product = productsState.find(p => p.id === notice.productId || (notice.productSku && p.sku === notice.productSku));

          if (product) {
            let newCalculatedStatus: DemandNoticeStatus = notice.status;
            if (product.quantityInStock >= notice.quantityRequested) {
                newCalculatedStatus = 'full_stock_available';
            } else if (product.quantityInStock > 0) {
                newCalculatedStatus = 'partial_stock_available';
            } else {
                newCalculatedStatus = 'awaiting_stock';
            }

            if (newCalculatedStatus !== notice.status || (notice.status === 'pending_review' && (newCalculatedStatus === 'full_stock_available' || newCalculatedStatus === 'partial_stock_available'))) {
              try {
                await updateDemandNoticeStatus(notice.id, newCalculatedStatus, currentUser);
                changed = true;
              } catch (apiError) {
                console.warn(`AppContext: Failed to update demand notice ${notice.id} status:`, apiError);
              }
            }
          } else if (notice.status === 'pending_review' && !notice.productId) {
            // No action
          }
        }
      }
    };
    checkAndUpdateDemandNotices();
  }, [initialLoadComplete, productsState, demandNoticesState, hasMounted, updateDemandNoticeStatus, currentUser]);


  const getEffectiveProductPrice = useCallback((product: Product): number => {
    if (
      product.lowStockThreshold !== undefined &&
      product.lowStockPrice !== undefined &&
      product.lowStockPrice > 0 &&
      product.quantityInStock <= product.lowStockThreshold
    ) {
      return product.lowStockPrice;
    }
    return product.price;
  }, []);

  const addToCart = useCallback((product: Product, quantity: number) => {
    setCartState((prevCart) => {
      const existingItem = prevCart.find((item) => item.id === product.id);
      const effectivePrice = getEffectiveProductPrice(product);

      if (existingItem) {
        return prevCart.map((item) =>
          item.id === product.id
            ? { ...item, cartQuantity: item.cartQuantity + quantity }
            : item
        );
      }
      const masterProduct = productsState.find(p => p.id === product.id) || product;
      return [...prevCart, { ...masterProduct, cartQuantity: quantity, customPrice: effectivePrice }];
    });
  }, [productsState, getEffectiveProductPrice]);

  const removeFromCart = useCallback((productId: string) => {
    setCartState((prevCart) => prevCart.filter((item) => item.id !== productId));
  }, []);

  const updateCartItemQuantity = useCallback((productId: string, quantity: number) => {
    setCartState((prevCart) =>
      prevCart.map((item) =>
        item.id === productId ? { ...item, cartQuantity: quantity } : item
      ).filter(item => item.cartQuantity > 0)
    );
  }, []);

  const updateCartItemPrice = useCallback((productId: string, newPrice: number) => {
    setCartState((prevCart) =>
      prevCart.map((item) =>
        item.id === productId ? { ...item, customPrice: newPrice } : item
      )
    );
  }, []);

  const clearCart = useCallback(() => {
    setCartState([]);
  }, []);

  const addOrder = useCallback(async (
    orderData: Omit<Order, 'id' | 'createdAt' | 'updatedAt' | 'status' | 'deliveryStatus' | 'returnTransactions'> & {
      primarySalespersonId: string;
      primarySalespersonName?: string;
      customerName?: string;
      customerPhone?: string;
      deliveryAddress?: string;
      secondarySalespersonId?: string;
      primarySalespersonCommission?: number;
      secondarySalespersonCommission?: number;
      payments?: PaymentDetail[];
      linkedDemandNoticeId?: string;
      appliedGlobalDiscountPercentage?: number;
     }
    ): Promise<Order | null> => {

    let finalOrderData = { ...orderData };
    let appliedGlobalDiscPerc: number | undefined = undefined;

    if (globalDiscountSettingState && globalDiscountSettingState.isActive && !orderData.appliedDiscountPercentage) {
      const today = new Date();
      const startDateString = globalDiscountSettingState.startDate;
      const endDateString = globalDiscountSettingState.endDate;
      const startDate = startDateString && isValid(parseISO(startDateString)) ? parseISO(startDateString) : null;
      const endDate = endDateString && isValid(parseISO(endDateString)) ? parseISO(endDateString) : null;

      const isDiscountPeriodActive = (!startDate || today >= startDate) && (!endDate || today <= endDate);
      if (isDiscountPeriodActive) {
        const discountAmount = (orderData.subtotal || 0) * (globalDiscountSettingState.percentage / 100);
        appliedGlobalDiscPerc = globalDiscountSettingState.percentage;
        finalOrderData = {
            ...finalOrderData,
            discountAmount: discountAmount,
            appliedGlobalDiscountPercentage: appliedGlobalDiscPerc,
            totalAmount: (orderData.subtotal || 0) - discountAmount + ((orderData.taxes || []).reduce((sum, tax) => sum + tax.amount, 0)),
        };
      }
    }

    let orderPayloadForApi: typeof finalOrderData & { primarySalespersonId: string, primarySalespersonName: string, payments: PaymentDetail[], appliedGlobalDiscountPercentage?: number };

    if (finalOrderData.linkedDemandNoticeId) {
        orderPayloadForApi = {
            ...finalOrderData,
            primarySalespersonId: finalOrderData.primarySalespersonId,
            primarySalespersonName: finalOrderData.primarySalespersonName || "Unknown (DN)",
            payments: finalOrderData.payments || [],
            appliedGlobalDiscountPercentage: finalOrderData.appliedGlobalDiscountPercentage
        };
    } else if (currentUser) {
        orderPayloadForApi = {
            ...finalOrderData,
            primarySalespersonId: currentUser.id,
            primarySalespersonName: currentUser.username,
            payments: finalOrderData.payments || [],
            appliedGlobalDiscountPercentage: finalOrderData.appliedGlobalDiscountPercentage
        };
    } else {
        toast({ title: "Error", description: "Cannot determine salesperson for the order.", variant: "destructive" });
        return null;
    }

    try {
      const newOrder = await addOrderToDb(orderPayloadForApi);
      if (newOrder && !('queued' in newOrder)) {
          await loadDataFromDb({ isInitialLoad: false });
      }
      return newOrder && !('queued' in newOrder) ? newOrder : null;
    } catch (error) {
        console.warn("Failed to add order via API:", error);
        toast({ title: "Order Creation Failed", description: (error as Error).message, variant: "destructive" });
        return null;
    }
  }, [currentUser, globalDiscountSettingState, loadDataFromDb, toast]);

  const updateOrderAndRefreshContext = useCallback(async (orderToSave: Order): Promise<Order | null> => {
    try {
        const updatedOrderFromServer = await apiUpdateOrderInDb(orderToSave);
         if (updatedOrderFromServer && !('queued' in updatedOrderFromServer)) {
            await loadDataFromDb({ isInitialLoad: false });
            const refreshedOrders = await getOrdersFromDb();
            const confirmedOrder = refreshedOrders.find(o => o.id === updatedOrderFromServer.id);
            return confirmedOrder || updatedOrderFromServer;
        }
        return null;
    } catch (error) {
        toast({ title: "Order Update Failed", description: (error as Error).message, variant: "destructive" });
        await loadDataFromDb({ isInitialLoad: false }); // Ensure data consistency even on error
        return null;
    }
  }, [loadDataFromDb, toast]);


  const updateOrderStatus = useCallback(async (orderId: string, status: Order['status']) => {
    try {
        const currentOrder = ordersState.find(o => o.id === orderId);
        if (!currentOrder) throw new Error("Order not found for status update");
        const updatedOrderData = { ...currentOrder, status, updatedAt: new Date().toISOString() };
        const updatedOrder = await apiUpdateOrderInDb(updatedOrderData);
        if (updatedOrder && !('queued' in updatedOrder)) {
            await loadDataFromDb({ isInitialLoad: false });
        }
    } catch (error) {
        console.warn("Failed to update order status via API:", error);
        toast({ title: "Order Status Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [ordersState, loadDataFromDb, toast]);

  const getProductById = useCallback((productId: string): Product | undefined => {
    return productsState.find(p => p.id === productId);
  }, [productsState]);

  const getProductBySku = useCallback((sku: string): Product | undefined => {
    return productsState.find(p => p.sku === sku);
  }, [productsState]);

  const getOrderById = useCallback((orderId: string): Order | undefined => {
    return ordersState.find(o => o.id === orderId);
  }, [ordersState]);

  const addDemandNotice = useCallback(async (noticeData: Omit<DemandNotice, 'id' | 'createdAt' | 'updatedAt' | 'status' | 'salespersonId' | 'salespersonName'> & {productName: string, productSku?: string}): Promise<DemandNotice | null> => {
    if (!currentUser) {
      toast({ title: "Error", description: "No user logged in to create demand notice.", variant: "destructive" });
      return null;
    }
    const payload = {
        ...noticeData,
        salespersonId: currentUser.id,
        salespersonName: currentUser.username,
    };
    try {
      const newNotice = await addDemandNoticeToDb(payload as any);
      if (newNotice && !('queued' in newNotice)) {
        await loadDataFromDb({ isInitialLoad: false });
        return newNotice;
      }
      return null;
    } catch (error) {
      console.warn("Failed to add demand notice via API:", error);
      toast({ title: "Demand Notice Failed", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [currentUser, loadDataFromDb, toast]);


  const deleteDemandNotice = useCallback(async (noticeId: string) => {
    try {
        const result = await deleteDemandNoticeFromDb(noticeId);
        if (result.success && !result.queued) {
           await loadDataFromDb({ isInitialLoad: false });
        }
    } catch (error) {
        console.warn("Failed to delete demand notice via API:", error);
        toast({ title: "Delete Demand Notice Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [loadDataFromDb, toast]);


  const getDemandNoticesForSalesperson = useCallback((salespersonId: string): DemandNotice[] => {
    return demandNoticesState.filter(dn => dn.salespersonId === salespersonId).sort((a,b) => parseISO(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }, [demandNoticesState]);

  const getAllDemandNotices = useCallback(async (): Promise<DemandNotice[]> => {
    return getDemandNoticesFromDb();
  }, []);


  const addAdvancePaymentToDemandNotice = useCallback(async (noticeId: string, payment: PaymentDetail): Promise<DemandNotice | null> => {
    if (!currentUser || (currentUser.role !== 'cashier' && !hasPermission('manage_orders') && !hasPermission('manage_demand_notices'))) {
      toast({ title: "Permission Denied", description: "You do not have permission to record advance payments.", variant: "destructive" });
      return null;
    }
    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/demand-notices/${noticeId}/payment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: "Failed to add advance payment." }));
        throw new Error(errorData.message);
      }
      const updatedNotice: DemandNotice = await response.json();
      await loadDataFromDb({ isInitialLoad: false });
      return updatedNotice;
    } catch (error) {
      console.warn("Failed to add advance payment to demand notice:", error);
      toast({ title: "Advance Payment Failed", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [currentUser, hasPermission, loadDataFromDb, toast]);

  const prepareOrderFromDemandNotice = useCallback(async (noticeId: string): Promise<Order | null> => {
    if (!currentUser) {
      toast({ title: "Error", description: "No user logged in.", variant: "destructive" });
      return null;
    }
    const notice = demandNoticesState.find(dn => dn.id === noticeId);
    if (!notice) {
      toast({ title: "Error", description: "Demand Notice not found.", variant: "destructive" });
      return null;
    }
     if (notice.status !== 'full_stock_available' && notice.status !== 'customer_notified_stock') {
        toast({ title: "Action Not Allowed", description: `Cannot prepare order. Notice status is ${notice.status.replace(/_/g, ' ')}.`, variant: "destructive" });
        return null;
    }

    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/demand-notices/${noticeId}/convert-to-order`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: "Failed to convert Demand Notice to Order." }));
        throw new Error(errorData.message);
      }

      const newOrder: Order = await response.json();
      await loadDataFromDb({ isInitialLoad: false });
      toast({ title: "Order Preparation Initiated", description: `Order ${newOrder.id} created from Demand Notice ${notice.id}.`, className: "bg-accent text-accent-foreground border-accent" });
      return newOrder;

    } catch (error) {
      toast({ title: "Error Converting DN to Order", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [currentUser, demandNoticesState, loadDataFromDb, toast]);



  const updateTaxSettings = useCallback(async (newSettings: TaxSetting[]) => {
    if (!hasPermission('manage_settings')) {
      toast({ title: "Permission Denied", description: "You do not have permission to update tax settings.", variant: "destructive" });
      return;
    }
    try {
        const updatedSettings = await updateTaxSettingsInDb(newSettings);
        if (updatedSettings && !('queued' in updatedSettings)) {
          await loadDataFromDb({ isInitialLoad: false });
        }
    } catch(error){
        console.warn("Failed to update tax settings via API:", error);
        toast({ title: "Tax Settings Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [hasPermission, loadDataFromDb, toast]);


  const updateGlobalDiscountSetting = useCallback(async (setting: GlobalDiscountSetting | null) => {
    if (!hasPermission('manage_settings')) {
      toast({ title: "Permission Denied", description: "You do not have permission to update global discount.", variant: "destructive" });
      return;
    }
    try {
        const updatedSetting = await updateGlobalDiscountSettingInDb(setting);
        if (updatedSetting && !('queued' in updatedSetting)) {
          await loadDataFromDb({ isInitialLoad: false });
        }
    } catch (error) {
        console.warn("Failed to update global discount via API:", error);
        toast({ title: "Global Discount Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [hasPermission, loadDataFromDb, toast]);


  const updateCommissionSetting = useCallback(async (setting: CommissionSetting | null) => {
     if (!hasPermission('manage_settings')) {
      toast({ title: "Permission Denied", description: "You do not have permission to update commission settings.", variant: "destructive" });
      return;
    }
    try {
        const updatedSetting = await updateCommissionSettingInDb(setting);
        if (updatedSetting && !('queued' in updatedSetting)) {
          await loadDataFromDb({ isInitialLoad: false });
        }
    } catch (error) {
        console.warn("Failed to update commission settings via API:", error);
        toast({ title: "Commission Settings Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [hasPermission, loadDataFromDb, toast]);

  const updateSeriesNumberSettings = useCallback(async (setting: SeriesNumberSetting) => {
    if (!hasPermission('manage_settings')) {
      toast({ title: "Permission Denied", description: "You do not have permission to update series number settings.", variant: "destructive" });
      return;
    }
    try {
      const updatedSetting = await updateSeriesNumberSettingInDb(setting);
      if (updatedSetting && !('queued' in updatedSetting)) {
        await loadDataFromDb({ isInitialLoad: false });
      }
    } catch (error) {
      console.warn("Failed to update series number settings via API:", error);
      toast({ title: "Series Number Settings Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [hasPermission, loadDataFromDb, toast]);

  const updateAttendanceSetting = useCallback(async (setting: AttendanceSetting | null) => {
    if (!hasPermission('manage_settings')) {
      toast({ title: "Permission Denied", description: "You do not have permission to update attendance settings.", variant: "destructive" });
      return;
    }
    try {
      const updatedSetting = await updateAttendanceSettingInDb(setting);
      if (updatedSetting && !('queued' in updatedSetting)) {
        await loadDataFromDb({ isInitialLoad: false });
      }
    } catch (error) {
      console.warn("Failed to update attendance settings via API:", error);
      toast({ title: "Attendance Settings Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [hasPermission, loadDataFromDb, toast]);


  const transferOrder = useCallback(async (orderId: string, newPrimarySalespersonId: string, newSecondarySalespersonId?: string, commissionSplit?: { primary: number; secondary: number }) => {
     if (!hasPermission('manage_orders')) {
      toast({ title: "Permission Denied", description: "You do not have permission to transfer orders.", variant: "destructive" });
      return;
    }
    try {
        const orderToUpdate = ordersState.find(o => o.id === orderId);
        if (!orderToUpdate) throw new Error("Order not found for transfer");

        const primarySp = usersState.find(u => u.id === newPrimarySalespersonId);
        const secondarySp = newSecondarySalespersonId ? usersState.find(u => u.id === newSecondarySalespersonId) : undefined;

        if(!primarySp) throw new Error("New primary salesperson not found");


        const payload: Order = {
            ...orderToUpdate,
            primarySalespersonId: newPrimarySalespersonId,
            primarySalespersonName: primarySp.username,
            secondarySalespersonId: newSecondarySalespersonId,
            secondarySalespersonName: secondarySp?.username,
            primarySalespersonCommission: commissionSplit ? commissionSplit.primary : (newSecondarySalespersonId ? 0.5 : 1.0),
            secondarySalespersonCommission: commissionSplit ? commissionSplit.secondary : (newSecondarySalespersonId ? 0.5 : undefined),
            updatedAt: new Date().toISOString(),
        };

        const updatedOrder = await apiUpdateOrderInDb(payload);
        if (updatedOrder && !('queued' in updatedOrder)) {
          await loadDataFromDb({ isInitialLoad: false });
        }
    } catch (error) {
        console.warn("Failed to transfer order via API:", error);
        toast({ title: "Order Transfer Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [hasPermission, ordersState, usersState, loadDataFromDb, toast]);


  const updateOrderDeliveryStatus = useCallback(async (orderId: string, deliveryStatus: DeliveryStatus) => {
    if (!(currentUser?.role === 'logistics' || hasPermission('manage_logistics') || hasPermission('manage_orders') )) {
        toast({ title: "Permission Denied", description: "You do not have permission to update delivery status.", variant: "destructive" });
        return;
    }
    try {
        const orderToUpdate = ordersState.find(o => o.id === orderId);
        if (!orderToUpdate) throw new Error("Order not found for delivery status update.");

        const updatedOrder = await apiUpdateOrderInDb({ ...orderToUpdate, deliveryStatus, updatedAt: new Date().toISOString() });
        if (updatedOrder && !('queued' in updatedOrder)) {
          await loadDataFromDb({ isInitialLoad: false });
        }
    } catch (error) {
        console.warn("Failed to update delivery status via API:", error);
        toast({ title: "Delivery Status Update Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [currentUser, hasPermission, ordersState, loadDataFromDb, toast]);


  const setOrderReminder = useCallback(async (orderId: string, reminderDate: string, reminderNotes: string) => {
    if (!(currentUser?.role === 'logistics' || hasPermission('manage_logistics') || hasPermission('manage_orders') )) {
        toast({ title: "Permission Denied", description: "You do not have permission to set order reminders.", variant: "destructive" });
        return;
    }
     try {
        const orderToUpdate = ordersState.find(o => o.id === orderId);
        if (!orderToUpdate) throw new Error("Order not found for setting reminder.");
        const updatedOrder = await apiUpdateOrderInDb({ ...orderToUpdate, reminderDate, reminderNotes, updatedAt: new Date().toISOString() });
        if (updatedOrder && !('queued' in updatedOrder)) {
          await loadDataFromDb({ isInitialLoad: false });
        }
    } catch (error) {
        console.warn("Failed to set order reminder via API:", error);
        toast({ title: "Set Reminder Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [currentUser, hasPermission, ordersState, loadDataFromDb, toast]);


  const processDetailedReturn = useCallback(async (
    orderId: string,
    itemsToReturn: ReturnItemDetail[],
    refundPaymentDetails: PaymentDetail[],
    returnReason?: string,
    exchangeNotes?: string
  ): Promise<boolean> => {
    if (!currentUser || !hasPermission('manage_returns')) {
      toast({ title: "Permission Denied", description: "You do not have permission to process returns.", variant: "destructive" });
      return false;
    }

    try {
        const orderToUpdate = ordersState.find(o => o.id === orderId);
        if (!orderToUpdate) {
            toast({ title: "Error", description: "Order not found for return.", variant: "destructive" });
            return false;
        }

        const response = await fetch(`${API_BASE_URL_CONTEXT}/orders/${orderId}/return`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ itemsToReturn, refundPaymentDetails, returnReason, exchangeNotes, processedByUserId: currentUser.id, processedByUsername: currentUser.username }),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({message: "Failed to process return on server."}));
            throw new Error(errorData.message);
        }

        const updatedOrderFromServer = await response.json();
        if (!('queued' in updatedOrderFromServer)) {
          await loadDataFromDb({ isInitialLoad: false });
        }
        return true;

    } catch (error) {
        console.warn("Failed to process detailed return via API:", error);
        toast({ title: "Return Processing Failed", description: (error as Error).message, variant: "destructive" });
        return false;
    }
  }, [currentUser, hasPermission, ordersState, loadDataFromDb, toast]);

  const { mutate: addProductOptimistic, isLoading: isAddingProduct } = useOptimisticMutation<
    Product | { queued: true, offlineId: string } | null,
    Error,
    Omit<Product, 'id'>,
    { optimisticId: string }
  >(
    async (productData) => {
      if (!hasPermission('manage_products')) {
        throw new Error("You do not have permission to add products.");
      }
      return apiAddProductToDb(productData);
    },
    {
      onMutate: async (newProductData) => {
        const optimisticId = `temp-product-${Date.now()}`;
        const optimisticProduct: Product = {
          ...newProductData,
          id: optimisticId,
          imageUrl: newProductData.imageUrl || undefined,
          category: newProductData.category || undefined,
          expiryDate: newProductData.expiryDate || undefined,
          isDemandNoticeProduct: newProductData.isDemandNoticeProduct || false,
          lowStockThreshold: newProductData.lowStockThreshold || undefined,
          lowStockPrice: newProductData.lowStockPrice || undefined,
        };
        setProductsState(prev => [optimisticProduct, ...prev].sort((a,b) => a.name.localeCompare(b.name)));
        return { optimisticId };
      },
      onSuccess: (result, variables, context) => {
        if (result && 'queued' in result && result.queued) {
          setProductsState(prev => prev.map(p => p.id === context?.optimisticId ? { ...p, id: result.offlineId || p.id, __isQueued: true } as Product & {__isQueued?:boolean} : p));
        } else if (result && 'id' in result) {
          setProductsState(prev => prev.map(p => (p.id === context?.optimisticId ? result : p)).sort((a,b) => a.name.localeCompare(b.name)));
        } else {
          setProductsState(prev => prev.filter(p => p.id !== context?.optimisticId).sort((a,b) => a.name.localeCompare(b.name)));
        }
      },
      onError: (error, variables, context) => {
        setProductsState(prev => prev.filter(p => p.id !== context?.optimisticId).sort((a,b) => a.name.localeCompare(b.name)));
      },
    }
  );

  const addProduct = useCallback(async (productData: Omit<Product, 'id'>): Promise<AddProductResult> => {
    const result: any = await addProductOptimistic(productData);
    if (result && 'queued' in result && result.queued) {
      return { success: true, product: null, queued: true, offlineId: result.offlineId };
    } else if (result && 'id' in result) {
      return { success: true, product: result as Product };
    }
    return { success: false, error: result?.message || "Optimistic add product failed." };
  }, [addProductOptimistic]);


  const updateProduct = useCallback(async (product: Product): Promise<UpdateProductResult> => {
    if (!hasPermission('manage_products')) {
      const errorMsg = "You do not have permission to update products.";
      toast({ title: "Permission Denied", description: errorMsg, variant: "destructive" });
      return { success: false, product: null, error: errorMsg };
    }
    try {
      const updatedProduct = await apiUpdateProductInDb(product);
      if (updatedProduct && !('queued' in updatedProduct)) {
        await loadDataFromDb({ isInitialLoad: false }); // Refresh all data including products
        return { success: true, product: updatedProduct };
      } else if (updatedProduct && 'queued' in updatedProduct) {
        setProductsState(prev => prev.map(p => p.id === product.id ? { ...product, __isQueued: true } as Product & {__isQueued?: boolean} : p));
        return { success: true, product: null, queued: true, offlineId: updatedProduct.offlineId };
      }
      return { success: false, error: "Update product did not return expected result." };
    } catch (error) {
      const errorMessage = (error as Error).message;
      toast({ title: "Update Product Failed", description: errorMessage, variant: "destructive" });
      return { success: false, product: null, error: errorMessage };
    }
  }, [hasPermission, setProductsState, toast, loadDataFromDb]);

  const deleteProduct = useCallback(async (productId: string): Promise<DeleteProductResult> => {
    if (!hasPermission('manage_products')) {
        const errorMsg = "You do not have permission to delete products.";
        toast({ title: "Permission Denied", description: errorMsg, variant: "destructive" });
        return { success: false, error: errorMsg };
    }
    try {
        const result = await apiDeleteProductFromDb(productId);
        if (result.success && !result.queued) {
           await loadDataFromDb({ isInitialLoad: false });
        }
        return result;
    } catch (error) {
        const errorMessage = (error as Error).message;
        toast({ title: "Delete Product Failed", description: errorMessage, variant: "destructive" });
        return { success: false, error: errorMessage };
    }
  }, [hasPermission, loadDataFromDb, toast]);


  const addQuotation = useCallback(async (
    quotationData: Omit<Quotation, 'id' | 'createdAt' | 'updatedAt' | 'salespersonId' | 'items'> & { items: Omit<QuotationItem, 'id' | 'quotationId' | 'converted'>[] }
  ): Promise<Quotation | null> => {
    if (!currentUser?.id) {
      toast({ title: "Error", description: "No user logged in. Cannot create quotation.", variant: "destructive" });
      return null;
    }
    try {
      const newQuotation = await addQuotationToDb(quotationData, currentUser.id);
      if (newQuotation && !('queued' in newQuotation)) {
        await loadDataFromDb({ isInitialLoad: false });
        return newQuotation;
      }
      return null;
    } catch (error) {
      toast({ title: "Create Quotation Failed", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [currentUser, loadDataFromDb, toast]);

  const getQuotationById = useCallback(async (quotationId: string): Promise<Quotation | undefined> => {
    if (!currentUser?.id) {
      toast({ title: "Authentication Error", description: "Cannot fetch quotation without user context.", variant: "destructive" });
      return undefined;
    }
    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/quotations/${quotationId}`, {
        headers: { 'x-user-id': currentUser.id }
      });
      if (!response.ok) {
        if (response.status === 404) return undefined;
        throw new ApiError(`Failed to fetch quotation ${quotationId}`, response.status);
      }
      const result = await response.json();
      if (result.success && result.data) {
        return result.data;
      }
      throw new Error(result.error || `Failed to parse quotation ${quotationId}`);
    } catch (error) {
      console.warn(`getQuotationById failed for ${quotationId}:`, error);
      toast({ title: "Fetch Error", description: `Could not load details for quotation ${quotationId}.`, variant: "destructive"});
      return undefined;
    }
  }, [currentUser, toast]);

  const updateQuotation = useCallback(async (quotationData: Partial<Quotation> & {id: string}): Promise<Quotation | null> => {
    if (!currentUser?.id) {
      toast({ title: "Error", description: "No user logged in. Cannot update quotation.", variant: "destructive" });
      return null;
    }
    try {
      const updatedQuotation = await updateQuotationInDb(quotationData, currentUser.id);
      if (updatedQuotation && !('queued' in updatedQuotation)) {
        await loadDataFromDb({ isInitialLoad: false });
        return updatedQuotation;
      }
      return null;
    } catch (error) {
      toast({ title: "Update Quotation Failed", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [currentUser, loadDataFromDb, toast]);

  const deleteQuotation = useCallback(async (quotationId: string) => {
    if (!currentUser?.id) {
      toast({ title: "Error", description: "No user logged in. Cannot delete quotation.", variant: "destructive" });
      return;
    }
    try {
      const result = await deleteQuotationFromDb(quotationId, currentUser.id);
      if (result.success && !result.queued) {
        await loadDataFromDb({ isInitialLoad: false });
      }
    } catch (error) {
      toast({ title: "Delete Quotation Failed", description: (error as Error).message, variant: "destructive" });
    }
  }, [currentUser, loadDataFromDb, toast]);

  const getQuotationsForSalesperson = useCallback((salespersonId: string): Quotation[] => {
    return quotationsState.filter(q => q.salespersonId === salespersonId).sort((a,b) => parseISO(b.createdAt).getTime() - parseISO(a.createdAt).getTime());
  }, [quotationsState]);

  const convertQuotationToDemandNotices = useCallback(async (quotationId: string): Promise<{ createdDemandNoticeIds: string[] } | null> => {
    if (!currentUser?.id) {
      toast({ title: "Error", description: "User not authenticated.", variant: "destructive" });
      return null;
    }
    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/quotations/${quotationId}/convert-to-demand-notice`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-user-id': currentUser.id
        },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Failed to convert to demand notice(s)." }));
        throw new ApiError(errorData.error || `Server error: ${response.status}`, response.status, errorData);
      }
      const result = await response.json();
      if (result.success) {
        await loadDataFromDb({ isInitialLoad: false }); // Refresh all data
        return { createdDemandNoticeIds: result.createdDemandNoticeIds || [] };
      } else {
        throw new Error(result.message || "Conversion to demand notice failed (API error).");
      }
    } catch (error) {
      toast({ title: "Conversion Failed", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [currentUser, toast, loadDataFromDb]);

  const convertQuotationToOrder = useCallback(async (quotationId: string): Promise<Order | null> => {
    if (!currentUser?.id) {
      toast({ title: "Error", description: "User not authenticated.", variant: "destructive" });
      return null;
    }
    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/quotations/${quotationId}/convert-to-order`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-user-id': currentUser.id
        },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Failed to convert quotation to order." }));
        throw new ApiError(errorData.error || `Server error: ${response.status}`, response.status, errorData);
      }
      const result = await response.json();
      if (result.success && result.createdOrder) {
        await loadDataFromDb({ isInitialLoad: false }); // Refresh all data
        return result.createdOrder;
      } else {
        throw new Error(result.message || "Conversion to order failed (API error).");
      }
    } catch (error) {
      toast({ title: "Convert to Order Failed", description: (error as Error).message, variant: "destructive" });
      return null;
    }
  }, [currentUser, toast, loadDataFromDb]);

  const createAudit = useCallback(async (auditData: LaunchAuditPayload): Promise<Audit | null> => {
    if (!currentUser || !hasPermission('manage_audits')) {
      toast({ title: "Permission Denied", description: "You do not have permission to launch audits.", variant: "destructive" });
      return null;
    }
    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/audits`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-user-id': currentUser.id,
        },
        body: JSON.stringify(auditData),
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Failed to launch audit." }));
        throw new ApiError(errorData.error || `Server error: ${response.status}`, response.status, errorData);
      }
      const result = await response.json();
      if (result.success && result.data) {
        await loadDataFromDb({ isInitialLoad: false }); // Refresh audits
        return result.data;
      } else {
        throw new Error(result.error || "Failed to launch audit (API reported error).");
      }
    } catch (error: any) {
      toast({ title: "Launch Audit Failed", description: error.message, variant: "destructive" });
      return null;
    }
  }, [currentUser, hasPermission, toast, loadDataFromDb]);

  const getAuditById = useCallback(async (auditId: string): Promise<Audit | undefined> => {
    if (!currentUser?.id) {
        toast({ title: "Authentication Error", description: "Cannot fetch audit without user context.", variant: "destructive" });
        return undefined;
    }
    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/audits/${auditId}`, {
        headers: { 'x-user-id': currentUser.id }
      });
      if (!response.ok) {
        if (response.status === 404) return undefined;
        const errorData = await response.json().catch(() => ({ error: `Failed to fetch audit ${auditId}. Status: ${response.status}` }));
        throw new ApiError(errorData.error || `Failed to fetch audit ${auditId}`, response.status, errorData);
      }
      const result = await response.json();
      if (result.success && result.data) {
        setAuditsState(prev => prev.map(a => a.id === auditId ? result.data : a));
        return result.data;
      }
      throw new Error(result.error || `Failed to parse audit ${auditId}`);
    } catch (error) {
      console.warn(`getAuditById failed for ${auditId}:`, error);
      toast({ title: "Fetch Error", description: `Could not load details for audit ${auditId}.`, variant: "destructive"});
      return undefined;
    }
  }, [currentUser, toast, setAuditsState]);

  const startAudit = useCallback(async (auditId: string, selfieFile: File): Promise<Audit | null> => {
    if (!currentUser || currentUser.role !== 'auditor') {
        toast({ title: "Permission Denied", description: "Only assigned auditors can start an audit.", variant: "destructive" });
        return null;
    }
    try {
        const formData = new FormData();
        formData.append('selfie', selfieFile);

        const response = await fetch(`${API_BASE_URL_CONTEXT}/audits/${auditId}/start`, {
            method: 'POST',
            headers: {
                'x-user-id': currentUser.id,
            },
            body: formData,
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ error: "Failed to start audit (non-JSON response from server)." }));
            console.error("API error in startAudit:", errorData);
            throw new ApiError(errorData.error || `Server error: ${response.status}`, response.status, errorData);
        }
        const result = await response.json();
        if (result.success && result.data) {
            await loadDataFromDb({ isInitialLoad: false }); // Refresh audits
            return result.data;
        } else {
            throw new Error(result.error || "Failed to start audit (API reported error).");
        }
    } catch (error: any) {
        const description = (error.data && error.data.details) ? error.data.details : error.message;
        toast({ title: "Start Audit Failed", description: description, variant: "destructive" });
        return null;
    }
  }, [currentUser, toast, loadDataFromDb]);

  const completeAudit = useCallback(async (auditId: string): Promise<Audit | null> => {
    if (!currentUser || currentUser.role !== 'auditor') {
      toast({ title: "Permission Denied", description: "Only assigned auditors can complete an audit.", variant: "destructive" });
      return null;
    }
    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/audits/${auditId}/complete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-user-id': currentUser.id,
        },
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Failed to complete audit." }));
        throw new ApiError(errorData.error || `Server error: ${response.status}`, response.status, errorData);
      }
      const result = await response.json();
      if (result.success && result.data) {
        await loadDataFromDb({ isInitialLoad: false }); // Refresh audits
        return result.data;
      } else {
        throw new Error(result.error || "Failed to complete audit (API reported error).");
      }
    } catch (error: any) {
      const description = (error.data && error.data.details) ? error.data.details : error.message;
      toast({ title: "Complete Audit Failed", description: description, variant: "destructive" });
      return null;
    }
  }, [currentUser, toast, loadDataFromDb]);

  const recordAuditItemCountWithImage = useCallback(async (
    auditId: string,
    auditItemId: string,
    count: number,
    notes?: string,
    imageFile?: File
  ): Promise<AuditItemCount | null> => {
    if (!currentUser || currentUser.role !== 'auditor') {
      toast({ title: "Permission Denied", description: "Only auditors can record counts.", variant: "destructive" });
      return null;
    }
    try {
      const formData = new FormData();
      formData.append('count', count.toString());
      if (notes) formData.append('notes', notes);
      if (imageFile) formData.append('image', imageFile);

      const response = await fetch(`${API_BASE_URL_CONTEXT}/audits/${auditId}/items/${auditItemId}/counts`, {
        method: 'POST',
        headers: {
          'x-user-id': currentUser.id,
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Failed to record count." }));
        throw new ApiError(errorData.error || `Server error: ${response.status}`, response.status, errorData);
      }
      const result = await response.json();
      if (result.success && result.data) {
        await loadDataFromDb({ isInitialLoad: false }); // Refresh relevant audit to include new count
        return result.data;
      } else {
        throw new Error(result.error || "Failed to record count (API reported error).");
      }
    } catch (error: any) {
      const description = (error.data && error.data.details) ? error.data.details : error.message;
      toast({ title: "Record Count Failed", description, variant: "destructive" });
      return null;
    }
  }, [currentUser, toast, loadDataFromDb]);

  const sendNewMessage = useCallback(async (subject: string, content: string, to: string[], cc: string[], bcc: string[], attachments: File[], forwardedAttachmentIds?: string[]): Promise<{ conversation_id: string } | null> => {
    if (!currentUser) {
      toast({ title: "Error", description: "You must be logged in to send messages.", variant: "destructive" });
      return null;
    }
    const formData = new FormData();
    formData.append('subject', subject);
    formData.append('content', content);
    to.forEach(id => formData.append('to[]', id));
    cc.forEach(id => formData.append('cc[]', id));
    bcc.forEach(id => formData.append('bcc[]', id));
    attachments.forEach(file => formData.append('attachments', file));
    (forwardedAttachmentIds || []).forEach(id => formData.append('forwardedAttachmentIds[]', id));

    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/messaging/conversations`, {
        method: 'POST',
        headers: { 'x-user-id': currentUser.id },
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Failed to send message." }));
        throw new Error(errorData.error || 'Failed to create conversation');
      }
      const result = await response.json();
      if (result.success && result.data) {
        await loadDataFromDb();
        toast({ title: "Message Sent!", description: `Conversation "${subject}" started.`, className: "bg-accent text-accent-foreground" });
        return { conversation_id: result.data.id };
      }
      throw new Error(result.error || 'Failed to send message.');
    } catch (error: any) {
      toast({ title: "Send Failed", description: error.message, variant: "destructive" });
      return null;
    }
  }, [currentUser, toast, loadDataFromDb]);

  const replyToConversation = useCallback(async (conversationId: string, content: string, to: string[], cc: string[], bcc: string[], attachments: File[]): Promise<Message | null> => {
    if (!currentUser) {
      toast({ title: "Error", description: "You must be logged in to reply.", variant: "destructive" });
      return null;
    }
    const formData = new FormData();
    formData.append('content', content);
    to.forEach(id => formData.append('to[]', id));
    cc.forEach(id => formData.append('cc[]', id));
    bcc.forEach(id => formData.append('bcc[]', id));
    attachments.forEach(file => formData.append('attachments', file));

    try {
      const response = await fetch(`${API_BASE_URL_CONTEXT}/messaging/conversations/${conversationId}/messages`, {
        method: 'POST',
        headers: { 'x-user-id': currentUser.id },
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Failed to send reply." }));
        throw new Error(errorData.error);
      }
      const result = await response.json();
      if (result.success && result.data) {
        await loadDataFromDb();
        toast({ title: "Reply Sent!", description: "Your reply has been sent.", className: "bg-accent text-accent-foreground" });
        return result.data;
      }
      throw new Error(result.error || 'Failed to send reply.');
    } catch (error: any) {
      toast({ title: "Reply Failed", description: error.message, variant: "destructive" });
      return null;
    }
  }, [currentUser, toast, loadDataFromDb]);
  
  const deleteConversation = useCallback(async (conversationId: string): Promise<void> => {
    if (!currentUser) {
        throw new Error("User not authenticated.");
    }
    const response = await fetch(`${API_BASE_URL_CONTEXT}/messaging/conversations/${conversationId}`, {
        method: 'DELETE',
        headers: { 'x-user-id': currentUser.id }
    });
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: "Failed to delete conversation." }));
        throw new Error(errorData.error);
    }
    const result = await response.json();
    if (result.success) {
      await loadDataFromDb();
    } else {
      throw new Error(result.error || "API reported an error on deletion.");
    }
  }, [currentUser, loadDataFromDb]);

  const getAttendanceLogsForUser = useCallback((userId: string): AttendanceLog[] => {
    return attendanceLogsState.filter(log => log.userId === userId);
  }, [attendanceLogsState]);

  const getBreakLogsForUser = useCallback((userId: string): BreakLog[] => {
    return breakLogsState.filter(log => log.userId === userId);
  }, [breakLogsState]);

  const getCurrentBreakForUser = useCallback((userId: string): BreakLog | undefined => {
    return breakLogsState.find(log => log.userId === userId && !log.endTime);
  }, [breakLogsState]);
  
  const currentBreakState = useMemo(() => currentUser ? getCurrentBreakForUser(currentUser.id) : undefined, [currentUser, getCurrentBreakForUser, breakLogsState]);

  const getTodayAttendanceForUser = useCallback((userId: string): AttendanceLog | undefined => {
    const userLogs = attendanceLogsState.filter(log => log.userId === userId);
    const today = new Date();
    return userLogs.find(log => {
      if (!log.timestamp || !isValid(parseISO(log.timestamp))) return false;
      return isSameDay(parseISO(log.timestamp), today);
    });
  }, [attendanceLogsState]);

  const isAttendanceCurrentlyRequired = useCallback((role: UserRole) => {
    if (!attendanceSettingState?.is_mandatory_attendance_active || !attendanceSettingState?.mandatory_attendance_time) {
      return false;
    }
    const applicableRoles: UserRole[] = ['salesperson', 'storekeeper', 'logistics'];
    if(!applicableRoles.includes(role)) {
      return false;
    }

    try {
        const now = new Date();
        const mandatoryTimeParts = attendanceSettingState.mandatory_attendance_time.split(':');
        const mandatoryDateTime = new Date();
        mandatoryDateTime.setHours(parseInt(mandatoryTimeParts[0], 10), parseInt(mandatoryTimeParts[1], 10), 0, 0);
        return now >= mandatoryDateTime;
    } catch (e) {
        console.error("Error parsing mandatory_attendance_time:", e);
        return false; // Default to not required if time parsing fails
    }
  }, [attendanceSettingState]);

  const canUserStartBreak = useCallback(() => {
    if (!currentUser) return { canStart: false, reason: "User not logged in." };

    if (isAttendanceCurrentlyRequired(currentUser.role)) {
      const todayLog = getTodayAttendanceForUser(currentUser.id);
      if (!todayLog) {
        return { canStart: false, reason: "Mandatory clock-in required before taking a break." };
      }
    }

    if (currentBreakState) {
      return { canStart: false, reason: "You are already on a break." };
    }

    if (attendanceSettingState?.max_concurrent_breaks !== null && attendanceSettingState?.max_concurrent_breaks !== undefined) {
      const activeBreaksCount = breakLogsState.filter(b => !b.endTime).length;
      if (activeBreaksCount >= attendanceSettingState.max_concurrent_breaks) {
        return { canStart: false, reason: `Maximum concurrent break limit (${attendanceSettingState.max_concurrent_breaks}) reached.` };
      }
    }
    return { canStart: true };
  }, [currentUser, currentBreakState, breakLogsState, attendanceSettingState, isAttendanceCurrentlyRequired, getTodayAttendanceForUser]);


  const contextValue = useMemo(() => ({
    currentUser, setCurrentUser,
    hasPermission,
    products: productsState, setProducts: setProductsState, addProduct, updateProduct, deleteProduct,
    orders: ordersState, setOrders: setOrdersState, updateOrderAndRefreshContext,
    users: usersState, setUsers: setUsersState, updateUserInDb,
    cart: cartState,
    addToCart, removeFromCart, updateCartItemQuantity, updateCartItemPrice, clearCart,
    addOrder,
    updateOrderStatus,
    updateProductStock,
    getProductById, getProductBySku, getOrderById, getEffectiveProductPrice,
    attendanceLogs: attendanceLogsState, setAttendanceLogsState,
    breakLogs: breakLogsState, setBreakLogsState,
    addAttendanceLog, startBreak, endBreak,
    getAttendanceLogsForUser, getBreakLogsForUser, getCurrentBreakForUser, getTodayAttendanceForUser,
    isAttendanceCurrentlyRequired, canUserStartBreak,
    demandNotices: demandNoticesState, setDemandNoticesState,
    addDemandNotice, updateDemandNoticeStatus, deleteDemandNotice,
    getDemandNoticesForSalesperson, getAllDemandNotices, addAdvancePaymentToDemandNotice,
    prepareOrderFromDemandNotice,
    taxSettings: taxSettingsState, setTaxSettingsState,
    updateTaxSettings,
    globalDiscountSetting: globalDiscountSettingState, setGlobalDiscountSettingState,
    updateGlobalDiscountSetting,
    commissionSetting: commissionSettingState, setCommissionSettingState,
    updateCommissionSetting,
    seriesNumberSettings: seriesNumberSettingsState, setSeriesNumberSettingsState: setSeriesNumberSettingsState,
    updateSeriesNumberSettings,
    attendanceSetting: attendanceSettingState, setAttendanceSettingState,
    updateAttendanceSetting,
    loadDataFromDb,
    transferOrder,
    updateOrderDeliveryStatus,
    setOrderReminder,
    processDetailedReturn,
    isDataLoaded,
    isBackgroundRefreshing,
    quotations: quotationsState, setQuotationsState, addQuotation, getQuotationById, updateQuotation, deleteQuotation, getQuotationsForSalesperson,
    convertQuotationToDemandNotices, convertQuotationToOrder,
    audits: auditsState, setAuditsState, createAudit, getAuditById, startAudit, completeAudit, recordAuditItemCountWithImage,
    conversations: conversationsState, totalUnreadCount,
    sendNewMessage, replyToConversation, deleteConversation,
    suppliers: suppliersState,
    purchaseOrders: purchaseOrdersState,
  }), [
    currentUser, setCurrentUser, hasPermission,
    productsState, addProduct, updateProduct, deleteProduct,
    ordersState, usersState, updateUserInDb, cartState, attendanceLogsState, breakLogsState, demandNoticesState, taxSettingsState, globalDiscountSettingState, commissionSettingState, seriesNumberSettingsState, attendanceSettingState, quotationsState, auditsState, conversationsState, totalUnreadCount, suppliersState, purchaseOrdersState,
    setProductsState, setOrdersState, setUsersState, setAttendanceLogsState, setBreakLogsState, setDemandNoticesState, setTaxSettingsState, setGlobalDiscountSettingState, setCommissionSettingState, setSeriesNumberSettingsState, setAttendanceSettingState, setQuotationsState, setAuditsState,
    updateOrderAndRefreshContext,
    isDataLoaded, isBackgroundRefreshing,
    addToCart, removeFromCart, updateCartItemQuantity, updateCartItemPrice, clearCart,
    addOrder, updateOrderStatus, updateProductStock,
    getProductById, getProductBySku, getOrderById, getEffectiveProductPrice,
    addAttendanceLog, startBreak, endBreak,
    getAttendanceLogsForUser, getBreakLogsForUser, getCurrentBreakForUser, getTodayAttendanceForUser,
    isAttendanceCurrentlyRequired, canUserStartBreak, // Includes currentBreakState dependency through canUserStartBreak
    addDemandNotice, updateDemandNoticeStatus, deleteDemandNotice,
    getDemandNoticesForSalesperson, getAllDemandNotices, addAdvancePaymentToDemandNotice,
    prepareOrderFromDemandNotice,
    updateTaxSettings,
    updateGlobalDiscountSetting,
    updateCommissionSetting,
    updateSeriesNumberSettings,
    updateAttendanceSetting,
    loadDataFromDb,
    transferOrder, updateOrderDeliveryStatus, setOrderReminder, processDetailedReturn,
    addQuotation, getQuotationById, updateQuotation, deleteQuotation, getQuotationsForSalesperson,
    convertQuotationToDemandNotices, convertQuotationToOrder,
    createAudit, getAuditById, startAudit, completeAudit, recordAuditItemCountWithImage,
    sendNewMessage, replyToConversation, deleteConversation,
  ]);


  if (!hasMounted) {
    return (
      <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', backgroundColor: 'hsl(var(--background))' }}>
        <p style={{ color: 'hsl(var(--foreground))', fontSize: '1.125rem', marginTop: '1rem' }}>
          Loading Retail Genie...
        </p>
      </div>
    );
  }

  if (!isDataLoaded) {
     return (
       <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', backgroundColor: 'hsl(var(--background))' }}>
          <TowerLoader />
          <p style={{ color: 'hsl(var(--foreground))', fontSize: '1.125rem', marginTop: '1rem' }}>
            Initializing Application Data...
          </p>
       </div>
    );
  }

  return (
    <AppContext.Provider value={contextValue}>
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
};
