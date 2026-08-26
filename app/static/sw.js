// PracticeLoop Service Worker (PWA Offline Cache & Push Dispatches)

const CACHE_NAME = "practiceloop-v3";
const ASSETS_TO_CACHE = [
  "/static/icons/sprite.svg",
  "/static/tailwindcss.js",
  "/static/htmx.min.js",
  "/static/alpine.min.js"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request).catch(() => {
      return caches.match(event.request);
    })
  );
});

self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : { title: "PracticeLoop", body: "Уведомление от ИИ-Ассистента" };
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/static/icons/sprite.svg",
      badge: "/static/icons/sprite.svg"
    })
  );
});
