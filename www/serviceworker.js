_STATIC_ASSETS = [
    "./",
    "./site.webmanifest",
    "./index.html",
    "./app.js",
    "./index.js",
    "./assets/bootstrap.bundle.min.js",
    "./assets/jquery.min.js",
    "./assets/bootstrap-icons.css",
    "./assets/bootstrap.min.css",
    "./assets/fonts/bootstrap-icons.woff?524846017b983fc8ded9325d94ed40f3",
    "./assets/fonts/bootstrap-icons.woff2?524846017b983fc8ded9325d94ed40f3",
    "./images/background.png",
    "./offline-images/metadata.json",
    "./offline-images/offline.jpg",
    "./icons/android-chrome-192x192.png",
    "./icons/android-chrome-512x512.png",
    "./icons/favicon-32x32.png",
    "./icons/favicon-16x16.png",
];

async function addResourcesToCache(resources) {
    cache = await caches.open("static");
    try {
        await cache.addAll(resources);
    } catch (error) {
        console.log("Couldn't cache resources:");
        console.log(error);
    }
}

self.addEventListener("install", e => {
    e.waitUntil(addResourcesToCache(_STATIC_ASSETS));
});

async function serveFromCacheFirst(req) {
    const response = await caches.match(req.url);
    if (response) {
        return response;
    } else {
        return fetch(req);
    }
}

async function fetchMetadataJson(request) {
    // If metadata.json fetching fails (no network) serve the cached files form "/offline-images".
    try {
        response = await fetch(request);
    } catch (error) {
        response = caches.match("/offline-images/metadata.json");
    }
    return response;
}

self.addEventListener('fetch', event => {
    if (new URL(event.request.url).pathname == "/images/metadata.json") {
        // metadata.json has as special handling
        response = fetchMetadataJson(event.request);
        event.respondWith(response);
    } else {
        // reset of the resources goes with the cache-first policy.
        try {
            event.respondWith(serveFromCacheFirst(event.request));
        } catch (error) {
            console.log(`Couldn't fetch content for ${req.url} from cache or network.`);
            console.log(error);
            throw error;
        }
    }
});
