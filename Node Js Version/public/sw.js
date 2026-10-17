// public/sw.js
const CACHE_NAME = 'retail-genie-cache-v1.6'; // Increment version for updates
const URLS_TO_CACHE = [
  '/',
  '/login',
  // Add other important static assets: CSS, JS, logo, favicon, fonts
  '/assets/logo.svg',
  '/assets/favicon.svg',
  // '/manifest.json', // If you have one
  // Be careful caching API routes by default unless they are truly static
];

self.addEventListener('install', (event) => {
  console.log('[SW] Install event');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Opened cache, caching URLs:', URLS_TO_CACHE);
        return cache.addAll(URLS_TO_CACHE);
      })
      .catch(err => {
        console.error('[SW] Failed to cache URLs during install:', err);
      })
      .then(() => self.skipWaiting()) // Activate new SW immediately
  );
});

self.addEventListener('activate', (event) => {
  console.log('[SW] Activate event');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim()) // Take control of uncontrolled clients
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Network first for HTML pages to get latest content, fallback to cache
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          // If fetch is successful, clone it and cache it
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then(cache => {
              cache.put(request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // If fetch fails (offline), try to get from cache
          return caches.match(request).then(cachedResponse => {
            return cachedResponse || caches.match('/') || new Response("Network error and no cache fallback.", { status: 503, statusText: "Service Unavailable"});
          });
        })
    );
    return;
  }

  // For API routes (including /api/uploads/), always go to network.
  // These should not be cached by the service worker.
  // Offline handling for API mutations is done by the ApiClient and OfflineQueue.
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }
  
  // Cache-first for other assets (CSS, JS, images not from /api/uploads)
  event.respondWith(
    caches.match(request)
      .then((cachedResponse) => {
        if (cachedResponse) {
          // console.log('[SW] Serving from cache:', request.url);
          return cachedResponse;
        }
        // console.log('[SW] Fetching from network and caching:', request.url);
        return fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.ok) {
            const responseToCache = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseToCache);
            });
          }
          return networkResponse;
        });
      })
      .catch(error => {
        console.error('[SW] Fetch error:', error, request.url);
        // Optionally, provide a generic fallback for assets if needed
        // For example, a placeholder image for failed image requests
      })
  );
});


self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'invalidate-cache') {
    const keyToDelete = event.data.key;
    if (keyToDelete) {
      caches.open(CACHE_NAME).then((cache) => {
        console.log(`[SW] Received 'invalidate-cache' message for key: ${keyToDelete}. Attempting to delete.`);
        cache.delete(keyToDelete).then((found) => {
          if (found) {
            console.log(`[SW] Cache entry deleted for ${keyToDelete}`);
          } else {
            console.log(`[SW] No cache entry found for ${keyToDelete} to delete.`);
          }
        });
      });
    }
  } else if (event.data && event.data.type === 'SKIP_WAITING') {
    console.log("[SW] Received 'SKIP_WAITING' message. Activating new SW.");
    self.skipWaiting();
  }
});
