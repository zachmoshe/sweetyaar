"use strict";

const CACHE_PREFIX = "sweetyaar-parent";
const CACHE_VERSION = "sweetyaar-parent-v11";

const PRECACHE_URLS = [
  "./",
  "./favicon.ico",
  "./index.html",
  "./manifest.webmanifest",
  "./assets/apple-touch-icon.png",
  "./assets/favicon-16.png",
  "./assets/favicon-32.png",
  "./assets/favicon-48.png",
  "./assets/header-decoration-teddy.png",
  "./assets/header-decoration-teddy@2x.png",
  "./assets/icon-animal.png",
  "./assets/icon-bluetooth.svg",
  "./assets/icon-pause.png",
  "./assets/icon-settings-sliders.svg",
  "./assets/icon-song.png",
  "./assets/icon-stop.png",
  "./assets/icon-theme.png",
  "./assets/icon-volume.png",
  "./assets/opening-hero-art.png",
  "./assets/pwa-icon-192.png",
  "./assets/pwa-icon-512.png",
  "./assets/pwa-icon-maskable-192.png",
  "./assets/pwa-icon-maskable-512.png",
  "./assets/ready-bottom-graphics.png",
  "./assets/ready-bottom-graphics@2x.png",
  "./assets/streaming-toy-scene.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => Promise.all(
        cacheNames
          .filter((cacheName) => cacheName.startsWith(CACHE_PREFIX) && cacheName !== CACHE_VERSION)
          .map((cacheName) => caches.delete(cacheName))
      ))
      .then(() => self.clients.claim())
  );
});

function isSameOriginRequest(request) {
  return new URL(request.url).origin === self.location.origin;
}

function shouldHandleRequest(request) {
  return request.method === "GET" && isSameOriginRequest(request);
}

function isNavigationRequest(request) {
  return request.mode === "navigate";
}

function isAppShellPath(url) {
  return url.pathname.endsWith("/") || url.pathname.endsWith("/index.html");
}

function isPrecachedPath(url) {
  return PRECACHE_URLS.some((path) => new URL(path, self.location.href).href === url.href);
}

async function cachedIndexFallback(cache) {
  return (await cache.match("./index.html")) || cache.match("./");
}

async function networkFirst(request) {
  const cache = await caches.open(CACHE_VERSION);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      await cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    if (cached) {
      return cached;
    }
    const fallback = await cachedIndexFallback(cache);
    if (fallback) {
      return fallback;
    }
    throw error;
  }
}

async function staleWhileRevalidate(event) {
  const request = event.request;
  const cache = await caches.open(CACHE_VERSION);
  const cached = await cache.match(request);
  const refresh = fetch(request)
    .then((response) => {
      if (response && response.ok) {
        return cache.put(request, response.clone()).then(() => response);
      }
      return response;
    })
    .catch(() => null);

  if (cached) {
    event.waitUntil(refresh);
    return cached;
  }

  const response = await refresh;
  if (response) {
    return response;
  }
  throw new Error(`No cached SweetYaar asset: ${request.url}`);
}

self.addEventListener("fetch", (event) => {
  if (!shouldHandleRequest(event.request)) {
    return;
  }
  const url = new URL(event.request.url);
  if (isNavigationRequest(event.request) || isAppShellPath(url)) {
    event.respondWith(networkFirst(event.request));
  } else if (isPrecachedPath(url)) {
    event.respondWith(staleWhileRevalidate(event));
  }
});
