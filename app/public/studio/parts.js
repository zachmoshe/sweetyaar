"use strict";

// Parts of a track in the wave editor. A track is one run of samples; its
// parts are the spans between "bounds": sorted sample positions strictly
// inside the track. No bounds means one part, the whole track. Pure logic on
// Float32Array channels, so it can be tested without a page.
(function (root) {
  // Sorted, unique positions strictly inside (0, length).
  function clean(bounds, length) {
    return [...new Set(bounds.map((b) => Math.round(b)))].filter((b) => b > 0 && b < length).sort((a, b) => a - b);
  }

  // [[start, end], ...] for every part.
  function spans(bounds, length) {
    const edges = [0, ...clean(bounds, length), length];
    const out = [];
    for (let i = 0; i + 1 < edges.length; i++) out.push([edges[i], edges[i + 1]]);
    return out;
  }

  // Marks [a, b) as its own part.
  function split(bounds, length, a, b) {
    return clean([...bounds, a, b], length);
  }

  // Fuses the parts that [a, b] covers: removes the bounds strictly inside it.
  function fuse(bounds, a, b) {
    return bounds.filter((x) => x <= a || x >= b);
  }

  // The bounds after |removed| samples starting at |at| were taken out
  // (bounds inside the removed range move to |at|).
  function afterRemoval(bounds, length, at, removed) {
    return clean(bounds.map((x) => (x <= at ? x : x >= at + removed ? x - removed : at)), length - removed);
  }

  function concat(pieces, channelCount) {
    const n = pieces.reduce((s, p) => s + p[0].length, 0);
    const out = [];
    for (let c = 0; c < channelCount; c++) {
      const ch = new Float32Array(n);
      let o = 0;
      for (const p of pieces) { ch.set(p[c], o); o += p[0].length; }
      out.push(ch);
    }
    return out;
  }

  // Makes both sides have the same number of channels (mono is duplicated).
  function matchChannels(a, b) {
    const n = Math.max(a.length, b.length);
    const up = (ch) => (ch.length === n ? ch : Array.from({ length: n }, () => ch[0]));
    return [up(a), up(b)];
  }

  // Inserts |audio| at sample |at| as a new part of its own.
  function insert(channels, bounds, at, audio) {
    const [track, add] = matchChannels(channels, audio);
    const length = track[0].length, n = add[0].length;
    at = Math.max(0, Math.min(length, Math.round(at)));
    const out = concat([track.map((c) => c.subarray(0, at)), add, track.map((c) => c.subarray(at))], track.length);
    const moved = bounds.map((x) => (x < at ? x : x + n));
    return { channels: out, bounds: clean([...moved, at, at + n], length + n) };
  }

  // Moves part |from| so it becomes part |to| (indexes after the move).
  function move(channels, bounds, from, to) {
    const length = channels[0].length, parts = spans(bounds, length);
    if (from === to || from < 0 || to < 0 || from >= parts.length || to >= parts.length) return { channels, bounds: clean(bounds, length) };
    const order = parts.map((_, i) => i);
    order.splice(to, 0, order.splice(from, 1)[0]);
    const pieces = order.map((i) => channels.map((c) => c.subarray(parts[i][0], parts[i][1])));
    const out = concat(pieces, channels.length);
    const next = [];
    let o = 0;
    for (const i of order) { if (o) next.push(o); o += parts[i][1] - parts[i][0]; }
    return { channels: out, bounds: clean(next, length) };
  }

  // The index of the part that contains sample |at|.
  function partAt(bounds, length, at) {
    const p = spans(bounds, length);
    const i = p.findIndex(([a, b]) => at >= a && at < b);
    return i < 0 ? p.length - 1 : i;
  }

  // The part edge (0, a bound or the end) nearest to |at|.
  function nearestEdge(bounds, length, at) {
    let best = 0;
    for (const e of [0, ...clean(bounds, length), length]) if (Math.abs(e - at) < Math.abs(best - at)) best = e;
    return best;
  }

  const api = { clean, spans, split, fuse, afterRemoval, insert, move, partAt, nearestEdge, matchChannels };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SweetYaarParts = api;
})(typeof self !== "undefined" ? self : globalThis);
