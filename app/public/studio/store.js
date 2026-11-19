"use strict";

// The Studio working area: themes, songs and animal sounds kept in this
// browser's IndexedDB so they survive closing the tab. Nothing leaves the
// computer until the user exports it.
//
//   themes  {id, name, createdAt}
//   items   {id, kind: "song" | "animal", themeId (songs only), name,
//            fileName, size, durationMs, blob, addedAt}
//   settings {id, value}   e.g. the export folder's handle
(function (root) {
  const DB_NAME = "sweetyaar-studio";
  const STORES = ["themes", "items", "settings"];

  // |onBlocked| is called when an older Studio tab keeps the database open
  // and so holds up the upgrade; it continues once that tab is closed.
  function open(indexedDB, onBlocked) {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 2);
      request.onblocked = () => { if (onBlocked) onBlocked(); };
      request.onupgradeneeded = () => {
        for (const name of STORES) {
          if (!request.result.objectStoreNames.contains(name)) request.result.createObjectStore(name, { keyPath: "id" });
        }
      };
      request.onsuccess = () => {
        // A newer Studio in another tab needs to upgrade the database: let it.
        request.result.onversionchange = () => request.result.close();
        resolve(request.result);
      };
      request.onerror = () => reject(request.error);
    });
  }

  function createStore(indexedDB, { onBlocked } = {}) {
    const ready = open(indexedDB, onBlocked);

    async function run(store, mode, action) {
      const db = await ready;
      return new Promise((resolve, reject) => {
        const tx = db.transaction(store, mode);
        const request = action(tx.objectStore(store));
        tx.oncomplete = () => resolve(request ? request.result : undefined);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    }

    return {
      themes: () => run("themes", "readonly", (s) => s.getAll()),
      items: () => run("items", "readonly", (s) => s.getAll()),
      putTheme: (theme) => run("themes", "readwrite", (s) => s.put(theme)),
      putItem: (item) => run("items", "readwrite", (s) => s.put(item)),
      deleteTheme: (id) => run("themes", "readwrite", (s) => s.delete(id)),
      deleteItem: (id) => run("items", "readwrite", (s) => s.delete(id)),
      getSetting: async (id) => (await run("settings", "readonly", (s) => s.get(id)))?.value,
      putSetting: (id, value) => run("settings", "readwrite", (s) => s.put({ id, value }))
    };
  }

  const api = { createStore };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SweetYaarStore = api;
})(typeof self !== "undefined" ? self : globalThis);
