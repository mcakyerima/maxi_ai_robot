/**
 * Maxi PWA service worker (v3) — deliberately minimal and SAFE.
 *
 * The old worker was cache-first and intercepted EVERY request — including the
 * socket.io client CDN and the /socket.io/ realtime transport — which could
 * break the live connection ("disconnected"). This version:
 *   - never touches cross-origin requests (CDNs, fonts, socket.io client),
 *   - never touches /socket.io/ (realtime),
 *   - is network-first for same-origin GETs (fresh app after every deploy),
 *   - only serves cache as an offline fallback,
 *   - precaches best-effort (a 404 can't fail the install),
 *   - deletes the old broken caches on activate.
 */
const CACHE = "maxi-ai-v3";
const SHELL = ["/", "/chat", "/math", "/settings", "/offline"];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // allSettled so one missing asset never fails the whole install
      Promise.allSettled(SHELL.map((url) => cache.add(url)))
    )
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return; // let POST etc. go straight to network

  let url;
  try {
    url = new URL(req.url);
  } catch (e) {
    return;
  }
  // Never intervene on other origins (CDNs, fonts, socket.io client) or on the
  // realtime transport — let the browser handle those directly.
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/socket.io")) return;

  // Network-first; fall back to cache only when the network is unavailable.
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const clone = res.clone();
          caches.open(CACHE).then((c) => c.put(req, clone)).catch(() => {});
        }
        return res;
      })
      .catch(() =>
        caches.match(req).then(
          (cached) =>
            cached ||
            (req.mode === "navigate" ? caches.match("/offline") : Response.error())
        )
      )
  );
});
