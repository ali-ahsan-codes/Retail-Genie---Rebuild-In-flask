// src/lib/apiClient.ts
import { offlineQueue } from './offlineQueue';
import { ApiError } from './database'; // Assuming ApiError is exported from database.ts

const DEFAULT_TIMEOUT = 10000; // 10 seconds for direct fetch attempts

export class ApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;

  constructor(baseUrl: string = '/api') {
    this.baseUrl = baseUrl;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
  }

  private notifyServiceWorkerToInvalidate(endpoint: string) {
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      // Construct the full URL for the GET request that needs invalidation
      // This assumes that your GET endpoints match your mutation endpoints
      // e.g., POST /api/products invalidates GET /api/products
      // For more complex scenarios (e.g., POST /api/products invalidates GET /api/products/some-category),
      // you might need a more sophisticated keying or tagging system.
      const getEndpointUrl = new URL(this.baseUrl + endpoint, window.location.origin).toString();
      
      console.log(`[ApiClient] Notifying SW to invalidate cache for: ${getEndpointUrl}`);
      navigator.serviceWorker.controller.postMessage({
        type: 'invalidate-cache',
        key: getEndpointUrl 
      });
    }
  }

  private async fetchWithTimeout(request: Request, timeout: number = DEFAULT_TIMEOUT): Promise<Response> {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);

    try {
      const response = await fetch(request, { signal: controller.signal });
      clearTimeout(id);
      return response;
    } catch (error) {
      clearTimeout(id);
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError('Request timed out', 408);
      }
      throw error; // Re-throw network errors or other fetch issues
    }
  }

  async request(
    method: string,
    endpoint: string,
    body: any = null,
    userId?: string,
    customHeaders: Record<string, string> = {}
  ): Promise<Response> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = new Headers({
      ...this.defaultHeaders,
      ...customHeaders,
    });

    if (userId) {
      headers.append('X-User-ID', userId);
    }

    const requestOptions: RequestInit = {
      method,
      headers,
    };

    if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
      requestOptions.body = JSON.stringify(body);
    }
    
    const request = new Request(url, requestOptions);

    if (typeof navigator !== 'undefined' && !navigator.onLine && method !== 'GET') {
      console.log(`[ApiClient] Offline, queuing ${method} request to ${url}`);
      const offlineId = await offlineQueue.addRequest(request.clone());
      const offlineHeaders = new Headers();
      offlineHeaders.append('X-Offline-Request-ID', offlineId);
      return new Response(null, { status: 202, statusText: 'Request Queued Offline', headers: offlineHeaders });
    }

    try {
      const response = await this.fetchWithTimeout(request.clone());

      if (!response.ok) {
        // For server errors (5xx) or specific client errors (408, 429), try queuing if it's a mutating request
        if (method !== 'GET' && (response.status >= 500 || response.status === 408 || response.status === 429)) {
          console.warn(`[ApiClient] Server error ${response.status} for ${method} ${url}. Attempting to queue.`);
          const offlineId = await offlineQueue.addRequest(request.clone());
          const offlineHeaders = new Headers();
          offlineHeaders.append('X-Offline-Request-ID', offlineId);
          // Return a 202 to indicate it was queued due to server-side issue.
          return new Response(JSON.stringify({ message: `Request queued after server error ${response.status}` }), { status: 202, statusText: 'Request Queued After Server Error', headers: offlineHeaders });
        }
        // For other non-ok responses (e.g., 400, 401, 403, 404), throw an ApiError
        const errorData = await response.json().catch(() => ({ error: `HTTP error! status: ${response.status}` }));
        throw new ApiError(errorData.message || errorData.error || `HTTP error! status: ${response.status}`, response.status, errorData);
      }

      // If a mutating request was successful (and not 202 from queueing), invalidate cache
      if (method !== 'GET' && response.status !== 202) {
        this.notifyServiceWorkerToInvalidate(endpoint);
      }

      return response; // Successful response
    } catch (error) {
      if (error instanceof ApiError) { // Re-throw ApiErrors
          throw error;
      }
      // Check for network errors (TypeError: Failed to fetch)
      if (error instanceof TypeError && error.message.toLowerCase().includes('failed to fetch')) {
        if (method !== 'GET') { // Only queue mutating requests on network error
          console.error(`[ApiClient] Network error for ${method} ${url}. Queuing request.`, error);
          const offlineId = await offlineQueue.addRequest(request.clone());
          const offlineHeaders = new Headers();
          offlineHeaders.append('X-Offline-Request-ID', offlineId);
          return new Response(null, { status: 202, statusText: 'Request Queued Due to Network Error', headers: offlineHeaders });
        } else {
            // For GET requests, if SW cache doesn't handle it, this will propagate as a network error.
             console.error(`[ApiClient] Network error for GET ${url}. Not queueing GET. Service worker should handle caching/offline.`, error);
            throw new ApiError('Network error while fetching data. Please check your connection.', 0, { originalError: error });
        }
      }
      // For other unexpected errors
      console.error(`[ApiClient] Unexpected error in request to ${url}:`, error);
      throw new ApiError((error as Error).message || 'An unexpected error occurred', 0, { originalError: error });
    }
  }

  async get(endpoint: string, userId?: string, customHeaders?: Record<string, string>): Promise<Response> {
    return this.request('GET', endpoint, null, userId, customHeaders);
  }

  async post(endpoint: string, body: any, userId?: string, customHeaders?: Record<string, string>): Promise<Response> {
    return this.request('POST', endpoint, body, userId, customHeaders);
  }

  async put(endpoint: string, body: any, userId?: string, customHeaders?: Record<string, string>): Promise<Response> {
    return this.request('PUT', endpoint, body, userId, customHeaders);
  }

  async delete(endpoint: string, userId?: string, body: any = null, customHeaders?: Record<string, string>): Promise<Response> {
    // Added body to delete for consistency, although it might not always be used
    return this.request('DELETE', endpoint, body, userId, customHeaders);
  }
}