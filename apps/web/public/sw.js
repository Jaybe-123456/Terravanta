const CACHE_NAME = "terravanta-shell-v1";
const OFFLINE_PAGE = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);
    await cache.add(OFFLINE_PAGE);
    try {
      const response = await fetch("/", { cache: "no-store" });
      if (response.ok) {
        const html = await response.clone().text();
        await cache.put("/", response);
        const assets = [...html.matchAll(/(?:src|href)=["']([^"']*\/_next\/static\/[^"']+)["']/g)]
          .map((match) => new URL(match[1], self.location.origin).href);
        await Promise.all(assets.map(async (asset) => {
          try {
            const assetResponse = await fetch(asset, { cache: "no-store" });
            if (assetResponse.ok) await cache.put(asset, assetResponse);
          } catch { /* Offline shell remains available even if a secondary chunk misses. */ }
        }));
      }
    } catch { /* Install can still succeed with the explicit offline page. */ }
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("terravanta-shell-") && key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).then((response) => {
      if (response.ok && url.pathname === "/") {
        const copy = response.clone();
        void caches.open(CACHE_NAME).then((cache) => cache.put("/", copy));
      }
      return response;
    }).catch(async () => (await caches.match("/")) || (await caches.match(OFFLINE_PAGE))));
    return;
  }

  if (!url.pathname.startsWith("/_next/static/")) return;
  event.respondWith(caches.open(CACHE_NAME).then(async (cache) => {
    const cached = await cache.match(request);
    if (cached) return cached;
    const response = await fetch(request);
    if (response.ok) {
      await cache.put(request, response.clone());
      const keys = await cache.keys();
      const assets = keys.filter((key) => new URL(key.url).pathname.startsWith("/_next/static/"));
      if (assets.length > 120) await cache.delete(assets[0]);
    }
    return response;
  }));
});
