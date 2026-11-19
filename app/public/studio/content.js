"use strict";

// Shared Studio content (song themes, animal sounds and spoken prompts), read
// straight from the public bucket gs://sweetyaar-studio-resources:
//
//   songs/<theme>/<song>.wav, songs/<theme>/metadata.json, songs/<theme>/ATTRIBUTION.txt
//   animal-sounds/<animal>.wav, animal-sounds/ATTRIBUTION.txt
//   animal-prompts/<lang>/<animal>.wav, animal-prompts/ATTRIBUTION.txt
//
// Every ATTRIBUTION.txt has the same format (see parseAttribution): its first
// line is the short credit shown in the UI, the other lines are the long one.
//
// Listings use the Cloud Storage JSON API; the bucket allows any origin to GET.
(function (root) {
  const DEFAULT_BUCKET = "sweetyaar-studio-resources";
  const NAME = /^[a-z0-9][a-z0-9_-]{0,39}$/;
  const LANG = /^[a-z]{2,3}(-[a-z0-9]{2,8})?$/;


  // Markdown kept small and safe: [links](https://...), bare https links,
  // **bold** and *italic*; headings lose their #; anything else, HTML
  // included, is plain text. Blank lines separate paragraphs, and each line
  // stays a line.
  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const link = (url, text) => `<a href="${url}" target="_blank" rel="noopener">${text}</a>`;
  function inlineHtml(line) {
    return esc(line.replace(/^\s*#+\s*/, "").trim())
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, text, url) => link(url, text))
      .replace(/(^|[\s(])(https?:\/\/[^\s<]*[^\s<.,;:)])/g, (_, before, url) => before + link(url, url))
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
      .replace(/(^|[^*])\*([^*]+)\*/g, "$1<i>$2</i>");
  }
  function markdownHtml(text) {
    return String(text || "").split(/\r?\n\s*\r?\n/)
      .map((block) => block.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map(inlineHtml).join("<br>"))
      .filter(Boolean).map((p) => `<p>${p}</p>`).join("");
  }

  // The one attribution format of the whole app. The first line is the short
  // credit (Markdown), shown wherever the content appears; the remaining
  // lines, without the blank lines at their start and end, are the long
  // credit, opened on request. Null without a short credit.
  function parseAttribution(text) {
    const lines = String(text || "").split(/\r?\n/);
    const short = inlineHtml(lines[0] || "");
    if (!short) return null;
    const rest = lines.slice(1);
    while (rest.length && !rest[0].trim()) rest.shift();
    while (rest.length && !rest[rest.length - 1].trim()) rest.pop();
    return { short, long: markdownHtml(rest.join("\n")) };
  }

  // |fetchImpl| is window.fetch.
  function createContent(fetchImpl, bucket = DEFAULT_BUCKET) {
    const files = `https://storage.googleapis.com/${bucket}`;
    const listUrl = `https://storage.googleapis.com/storage/v1/b/${bucket}/o`;
    const fileUrl = (path) => files + "/" + path.split("/").map(encodeURIComponent).join("/");

    async function get(url, kind) {
      const response = await fetchImpl(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return kind === "text" ? response.text() : response.json();
    }

    // Object names (with their sizes) and sub-folders directly under |prefix|.
    async function list(prefix) {
      const out = { names: [], sizes: {}, prefixes: [] };
      let token = "";
      do {
        const q = new URLSearchParams({ prefix, delimiter: "/", fields: "items(name,size),prefixes,nextPageToken" });
        if (token) q.set("pageToken", token);
        const body = await get(`${listUrl}?${q}`);
        for (const item of body.items || []) {
          const name = item.name.slice(prefix.length);
          out.names.push(name); out.sizes[name] = Number(item.size) || 0;
        }
        for (const p of body.prefixes || []) out.prefixes.push(p.slice(prefix.length, -1));
        token = body.nextPageToken || "";
      } while (token);
      return out;
    }
    const wavs = (names) => names.filter((n) => n.endsWith(".wav") && NAME.test(n.slice(0, -4))).map((n) => ({ name: n.slice(0, -4) })).sort((a, b) => a.name.localeCompare(b.name));

    // One library theme, songs/<id>/: its metadata.json (name, shuffle, the
    // one-line credit for the toy), ATTRIBUTION.txt and its songs. A song's
    // length is worked out from its size, since every library file is
    // 44.1 kHz mono 16-bit WAV.
    async function theme(id) {
      const prefix = `songs/${id}/`, listing = await list(prefix);
      let meta = {}, attribution = null;
      if (listing.names.includes("metadata.json")) {
        try { meta = await get(fileUrl(prefix + "metadata.json")) || {}; } catch { /* optional */ }
      }
      if (listing.names.includes("ATTRIBUTION.txt")) {
        try { attribution = parseAttribution(await get(fileUrl(prefix + "ATTRIBUTION.txt"), "text")); } catch { /* optional */ }
      }
      const songs = listing.names.filter((n) => /\.wav$/i.test(n) && !n.startsWith(".") && !n.includes("/"))
        .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
        .map((file) => ({ file, name: file.slice(0, -4), size: listing.sizes[file], durationMs: Math.max(0, Math.round((listing.sizes[file] - 44) / 88.2)) }));
      return {
        id, name: typeof meta.name === "string" && meta.name.trim() ? meta.name.trim() : id,
        shuffle: !!meta.shuffle, credit: typeof meta.attribution === "string" ? meta.attribution : "",
        attribution, songs
      };
    }

    return {
      files,
      // The song themes under songs/, each with its songs; a theme that fails
      // to load is left out.
      async themes() {
        const ids = (await list("songs/")).prefixes.filter((id) => NAME.test(id)).sort();
        return (await Promise.all(ids.map((id) => theme(id).catch(() => null)))).filter((t) => t && t.songs.length);
      },
      songUrl: (themeId, file) => fileUrl(`songs/${themeId}/${file}`),
      async sounds() {
        const listing = await list("animal-sounds/");
        let attribution = null;
        if (listing.names.includes("ATTRIBUTION.txt")) {
          try { attribution = parseAttribution(await get(fileUrl("animal-sounds/ATTRIBUTION.txt"), "text")); } catch { /* optional */ }
        }
        return { files: wavs(listing.names), attribution };
      },
      async languages() {
        return (await list("animal-prompts/")).prefixes.filter((l) => LANG.test(l)).sort();
      },
      async prompts(lang) {
        return wavs((await list(`animal-prompts/${lang}/`)).names);
      },
      // The prompts' attribution ({short, long} HTML), or null when there is none.
      async promptsAttribution() {
        try { return parseAttribution(await get(fileUrl("animal-prompts/ATTRIBUTION.txt"), "text")); } catch { return null; }
      },
      soundUrl: (name) => fileUrl(`animal-sounds/${name}.wav`),
      promptUrl: (lang, name) => fileUrl(`animal-prompts/${lang}/${name}.wav`)
    };
  }

  const api = { createContent, parseAttribution, markdownHtml, DEFAULT_BUCKET };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SweetYaarContent = api;
})(typeof self !== "undefined" ? self : globalThis);
