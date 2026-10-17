
// src/lib/offlineQueue.ts
import { get, set, del, keys as idbKeys, update } from 'idb-keyval';

interface SerializedRequest {
  url: string;
  method: string;
  headers: [string, string][];
  body: string | null; // Store body as string
  mode?: RequestMode;
  credentials?: RequestCredentials;
  cache?: RequestCache;
  redirect?: RequestRedirect;
  referrer?: string;
}

interface QueuedDbEntry {
  id: string;
  request: SerializedRequest;
  timestamp: number;
  retries: number;
  maxRetries: number;
  lastAttempt: number; // Timestamp of the last attempt
}

const QUEUE_PREFIX = 'offline-queue-';
const DEFAULT_MAX_RETRIES = 5; // Increased default retries
const RETRY_DELAY_BASE = 5000; // 5 seconds base for exponential backoff

class EnhancedOfflineQueue {
  private isProcessing = false;
  private processingTimeoutId: NodeJS.Timeout | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', this.handleOnlineStatusChange);
      window.addEventListener('offline', this.handleOfflineStatusChange);
      // Initial processing attempt if online
      this.triggerProcessing();
    }
  }

  private handleOnlineStatusChange = () => {
    console.log("[OfflineQueue] Network status changed to ONLINE. Triggering queue processing.");
    this.triggerProcessing();
  }
  
  private handleOfflineStatusChange = () => {
    console.log("[OfflineQueue] Network status changed to OFFLINE. Pausing queue processing.");
    if (this.processingTimeoutId) {
      clearTimeout(this.processingTimeoutId);
      this.processingTimeoutId = null;
    }
    this.isProcessing = false; // Ensure processing stops if it was running
  }


  private async serializeRequest(request: Request): Promise<SerializedRequest> {
    let bodyText: string | null = null;
    // Only attempt to read body if it's a method that might have one and body is not null
    if (request.method !== 'GET' && request.method !== 'HEAD' && request.body) {
      try {
        // Try to get text, but handle cases where body might already be consumed or of different type
        bodyText = await request.text();
      } catch (e) {
        console.warn(`[OfflineQueue] Could not read body for request ${request.url}. Storing as null. Error:`, e);
        // For certain types of BodyInit (like FormData), text() might fail after cloning or if already used.
        // In a more complex scenario, one might need to handle FormData serialization specifically.
        // For now, if text() fails, we assume the body can't be easily serialized as text and store null.
      }
    }
    return {
      url: request.url,
      method: request.method,
      headers: Array.from(request.headers.entries()), // Convert Headers object to array of [key, value]
      body: bodyText,
      mode: request.mode,
      credentials: request.credentials,
      cache: request.cache,
      redirect: request.redirect,
      referrer: request.referrer,
    };
  }

  private async deserializeRequest(serialized: SerializedRequest): Promise<Request> {
    const headers = new Headers();
    serialized.headers.forEach(([key, value]) => headers.append(key, value));
    
    return new Request(serialized.url, {
      method: serialized.method,
      headers: headers,
      body: serialized.body, // Body is already string or null
      mode: serialized.mode,
      credentials: serialized.credentials,
      cache: serialized.cache,
      redirect: serialized.redirect,
      referrer: serialized.referrer,
    });
  }

  public async addRequest(request: Request, maxRetriesInput?: number): Promise<string> {
    const id = crypto.randomUUID();
    const timestamp = Date.now();
    
    // Important: Clone the request BEFORE serializing, as reading the body consumes it.
    const clonedRequest = request.clone(); 
    const serializedRequest = await this.serializeRequest(clonedRequest);

    const dbEntry: QueuedDbEntry = {
      id,
      request: serializedRequest,
      timestamp,
      retries: 0,
      maxRetries: maxRetriesInput ?? DEFAULT_MAX_RETRIES,
      lastAttempt: 0,
    };

    try {
      await set(`${QUEUE_PREFIX}${id}`, dbEntry);
      console.log(`[OfflineQueue] Request ${id} (URL: ${request.url}) added to queue.`);
      this.triggerProcessing();
    } catch (error) {
        console.error(`[OfflineQueue] Failed to add request ${id} to IDB:`, error);
        // Optionally, notify about the failure to queue
        this.broadcastFailure(id, request.url, "Failed to add to local queue");
        throw error; // Re-throw so caller knows it wasn't queued
    }
    return id; 
  }

  public triggerProcessing(): void {
    if (typeof navigator !== 'undefined' && navigator.onLine) {
      // Debounce processing slightly to batch potential rapid additions
      if (this.processingTimeoutId) clearTimeout(this.processingTimeoutId);
      this.processingTimeoutId = setTimeout(() => {
        this.processQueue();
      }, 500); // Process after 500ms of no new triggers
    } else {
      console.log("[OfflineQueue] Currently offline, processing deferred.");
    }
  }

  private async processQueue(): Promise<void> {
    if (this.isProcessing || (typeof navigator !== 'undefined' && !navigator.onLine)) {
      if(this.isProcessing) console.log("[OfflineQueue] Processing already in progress. Will check again later.");
      return;
    }
    this.isProcessing = true;
    console.log("[OfflineQueue] Starting to process queue...");

    let processedSomethingInThisRun = false;

    try {
      const allStorageKeys = await idbKeys();
      const itemKeys = allStorageKeys.filter(key => typeof key === 'string' && key.startsWith(QUEUE_PREFIX)) as string[];

      if (itemKeys.length === 0) {
          console.log("[OfflineQueue] Queue is empty.");
          this.isProcessing = false;
          return;
      }
      console.log(`[OfflineQueue] Found ${itemKeys.length} items to potentially process.`);

      // Sort keys by timestamp to process older requests first (optional, but good practice)
      const itemsWithTimestamp: {key: string, timestamp: number}[] = [];
      for (const key of itemKeys) {
        const item = await get<QueuedDbEntry>(key);
        if(item) itemsWithTimestamp.push({key, timestamp: item.timestamp});
      }
      itemsWithTimestamp.sort((a,b) => a.timestamp - b.timestamp);
      const sortedItemKeys = itemsWithTimestamp.map(it => it.key);


      for (const key of sortedItemKeys) {
        if (typeof navigator !== 'undefined' && !navigator.onLine) {
          console.log("[OfflineQueue] Went offline during processing. Pausing.");
          break; 
        }

        const item = await get<QueuedDbEntry>(key);
        if (!item) {
          console.warn(`[OfflineQueue] Item with key ${key} disappeared from IDB. Skipping.`);
          continue;
        }
        
        const retryDelay = RETRY_DELAY_BASE * Math.pow(2, Math.min(item.retries, 5)); // Cap exponential factor
        if (Date.now() - item.lastAttempt < retryDelay && item.retries > 0) {
            console.log(`[OfflineQueue] Request ${item.id} (URL: ${item.request.url}) is in retry delay. Skipping for now. Next attempt after ~${Math.round(retryDelay/1000)}s.`);
            continue;
        }

        try {
          const deserializedRequest = await this.deserializeRequest(item.request);
          console.log(`[OfflineQueue] Attempting request ${item.id} (URL: ${deserializedRequest.url}, Method: ${deserializedRequest.method}). Retries: ${item.retries}`);
          
          await update(key, (val: QueuedDbEntry | undefined) => val ? {...val, lastAttempt: Date.now()} : undefined);
          processedSomethingInThisRun = true;

          const response = await fetch(deserializedRequest);

          if (response.ok) {
            console.log(`[OfflineQueue] Request ${item.id} (URL: ${item.request.url}) successful. Removing from queue.`);
            await del(key);
            this.broadcastSuccess(item.id, item.request.url);
          } else {
            console.warn(`[OfflineQueue] Request ${item.id} (URL: ${item.request.url}) failed with status: ${response.status}.`);
            await this.handleFailedRequest(key, item, response.status);
          }
        } catch (fetchError) {
          console.error(`[OfflineQueue] Network error for request ${item.id} (URL: ${item.request.url}):`, fetchError);
          await this.handleFailedRequest(key, item, 0); // 0 status for network errors
        }
      }
    } catch (error) {
      console.error("[OfflineQueue] Error during main queue processing loop:", error);
    } finally {
      this.isProcessing = false;
      console.log("[OfflineQueue] Queue processing cycle finished.");
      
      // If still online and potentially more items or items that were in retry delay, schedule another check.
      if (typeof navigator !== 'undefined' && navigator.onLine) {
        idbKeys().then(allKeysAfterProcessing => {
            if (allKeysAfterProcessing.some(k => typeof k === 'string' && k.startsWith(QUEUE_PREFIX))) {
                 const nextCheckDelay = processedSomethingInThisRun ? 1000 : RETRY_DELAY_BASE; // Quicker check if we processed something
                 console.log(`[OfflineQueue] Scheduling next queue check in ${nextCheckDelay/1000}s.`);
                 if (this.processingTimeoutId) clearTimeout(this.processingTimeoutId);
                 this.processingTimeoutId = setTimeout(() => this.triggerProcessing(), nextCheckDelay);
            } else {
                console.log("[OfflineQueue] Queue is now confirmed empty. No further checks scheduled immediately.");
            }
        });
      }
    }
  }

  private async handleFailedRequest(itemKey: string, item: QueuedDbEntry, status: number): Promise<void> {
    const newRetries = item.retries + 1;
    
    // Do not retry client errors (4xx) other than 408 (Timeout) or 429 (Too Many Requests)
    const isClientErrorNonRetriable = status >= 400 && status < 500 && status !== 408 && status !== 429;

    if (newRetries >= item.maxRetries || isClientErrorNonRetriable) {
      const reason = isClientErrorNonRetriable ? `Client error (status ${status})` : `Max retries (${item.maxRetries}) reached`;
      console.error(`[OfflineQueue] Request ${item.id} (URL: ${item.request.url}) failed permanently. Reason: ${reason}. Removing from queue and notifying failure.`);
      await del(itemKey);
      this.broadcastFailure(item.id, item.request.url, reason);
    } else {
      console.log(`[OfflineQueue] Request ${item.id} (URL: ${item.request.url}) will be retried. Retry count: ${newRetries}.`);
      try {
        await update(itemKey, (val: QueuedDbEntry | undefined) => val ? {...val, retries: newRetries, lastAttempt: Date.now()} : undefined);
      } catch (dbError) {
        console.error(`[OfflineQueue] Failed to update retry count for ${item.id} in IDB:`, dbError);
      }
    }
  }

  private broadcastSuccess(requestId: string, requestUrl: string): void {
    if (typeof window !== 'undefined') {
      const event = new CustomEvent('offlineQueueSuccess', { detail: { requestId, requestUrl } });
      window.dispatchEvent(event);
      console.log(`[OfflineQueue] Dispatched 'offlineQueueSuccess' for ${requestId}`);
    }
  }

  private broadcastFailure(requestId: string, requestUrl: string, reason: string): void {
    if (typeof window !== 'undefined') {
      const event = new CustomEvent('offlineQueueFailure', { detail: { requestId, requestUrl, reason } });
      window.dispatchEvent(event);
      console.log(`[OfflineQueue] Dispatched 'offlineQueueFailure' for ${requestId}. Reason: ${reason}`);
    }
  }
}

// Export a singleton instance
export const offlineQueue = typeof window !== 'undefined' ? new EnhancedOfflineQueue() : null;

// Helper to listen to queue events - components can use this
export function listenToOfflineQueueEvents(
  onSuccess: (detail: { requestId: string, requestUrl: string }) => void,
  onFailure: (detail: { requestId: string, requestUrl: string, reason: string }) => void
): () => void {
  if (typeof window === 'undefined') return () => {};

  const successListener = (event: Event) => onSuccess((event as CustomEvent).detail);
  const failureListener = (event: Event) => onFailure((event as CustomEvent).detail);

  window.addEventListener('offlineQueueSuccess', successListener);
  window.addEventListener('offlineQueueFailure', failureListener);

  return () => {
    window.removeEventListener('offlineQueueSuccess', successListener);
    window.removeEventListener('offlineQueueFailure', failureListener);
  };
}
