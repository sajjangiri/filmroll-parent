self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// Intentionally no fetch handler. Next.js payloads are versioned per build;
// caching them here would serve a stale app after a deploy. Capture itself
// does not need the worker: photos land in IndexedDB from the page, and the
// drain loop runs whenever this origin is open again.
