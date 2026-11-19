"use strict";

// Audio helpers for the Studio wave editor. They work on plain arrays of
// Float32Array channels (-1..1) so they can be tested without a browser.
(function (root) {
  const OUTPUT_RATE = 44100;
  const db = (x) => 20 * Math.log10(x);
  const lin = (d) => Math.pow(10, d / 20);

  // The toy plays 44.1 kHz, 16-bit PCM WAV, mono or stereo.
  function wavInfo(arrayBuffer) {
    const v = new DataView(arrayBuffer);
    if (v.byteLength < 12 || v.getUint32(0) !== 0x52494646 || v.getUint32(8) !== 0x57415645) return null;
    let pos = 12, info = null;
    while (pos + 8 <= v.byteLength) {
      const id = v.getUint32(pos), size = v.getUint32(pos + 4, true);
      if (id === 0x666d7420 && pos + 24 <= v.byteLength) {
        info = { format: v.getUint16(pos + 8, true), channels: v.getUint16(pos + 10, true), rate: v.getUint32(pos + 12, true), bits: v.getUint16(pos + 22, true) };
      }
      pos += 8 + size + (size & 1);
    }
    return info;
  }
  function isToyWav(info) {
    return !!info && info.format === 1 && info.bits === 16 && info.rate === OUTPUT_RATE && (info.channels === 1 || info.channels === 2);
  }

  function encodeWav(channels, rate) {
    const n = channels[0].length, nch = channels.length;
    const buf = new ArrayBuffer(44 + n * nch * 2), v = new DataView(buf);
    const text = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    text(0, "RIFF"); v.setUint32(4, 36 + n * nch * 2, true); text(8, "WAVE"); text(12, "fmt ");
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, nch, true); v.setUint32(24, rate, true);
    v.setUint32(28, rate * nch * 2, true); v.setUint16(32, nch * 2, true); v.setUint16(34, 16, true);
    text(36, "data"); v.setUint32(40, n * nch * 2, true);
    let o = 44;
    for (let i = 0; i < n; i++) {
      for (let c = 0; c < nch; c++) {
        const x = Math.max(-1, Math.min(1, channels[c][i]));
        v.setInt16(o, Math.round(x < 0 ? x * 32768 : x * 32767), true); o += 2;
      }
    }
    return buf;
  }

  function peakOf(channels) {
    let p = 0;
    for (const ch of channels) for (let i = 0; i < ch.length; i++) { const a = Math.abs(ch[i]); if (a > p) p = a; }
    return p;
  }

  // With |range| ({from, to} in seconds) only that part changes; it is
  // blended in and out over 5 ms so the edges do not click.
  function applyGain(channels, gainDb, range, rate = OUTPUT_RATE) {
    const g = lin(gainDb);
    if (!range) return channels.map((ch) => ch.map((x) => x * g));
    const n = channels[0].length, ramp = Math.round(rate * 0.005);
    const a = Math.max(0, Math.min(n, Math.round(range.from * rate))), b = Math.max(a, Math.min(n, Math.round(range.to * rate)));
    const factor = (i) => {
      if (i >= a && i < b) return g;
      if (i < a) return 1 + (g - 1) * (i - (a - ramp) + 1) / (ramp + 1);
      return g + (1 - g) * (i - b + 1) / (ramp + 1);
    };
    return channels.map((src) => {
      const ch = src.slice();
      for (let i = Math.max(0, a - ramp); i < Math.min(n, b + ramp); i++) ch[i] *= factor(i);
      return ch;
    });
  }

  // Cuts quiet audio from both ends, keeping a short margin.
  function trimSilence(channels, rate, { thresholdDb = -50, padMs = 30 } = {}) {
    const n = channels[0].length, win = Math.max(1, Math.round(rate * 0.01)), thr = lin(thresholdDb);
    const loud = (from) => { for (let c = 0; c < channels.length; c++) for (let i = from; i < Math.min(n, from + win); i++) if (Math.abs(channels[c][i]) > thr) return true; return false; };
    let first = -1, last = -1;
    for (let i = 0; i < n; i += win) if (loud(i)) { first = i; break; }
    if (first < 0) return { channels, removedSec: 0, silent: true };
    for (let i = Math.floor((n - 1) / win) * win; i >= 0; i -= win) if (loud(i)) { last = Math.min(n, i + win); break; }
    const pad = Math.round(rate * padMs / 1000);
    const from = Math.max(0, first - pad), to = Math.min(n, last + pad);
    return { channels: channels.map((ch) => ch.slice(from, to)), removedSec: (n - (to - from)) / rate, silent: false, from, to };
  }

  // Removes [fromSec, toSec). The two sides are cross-faded over a few
  // milliseconds so the join does not click.
  function cutRange(channels, rate, fromSec, toSec) {
    const n = channels[0].length;
    const a = Math.max(0, Math.min(n, Math.round(fromSec * rate))), b = Math.max(a, Math.min(n, Math.round(toSec * rate)));
    if (b === a) return channels;
    const x = Math.min(Math.round(rate * 0.005), a, n - b);
    return channels.map((ch) => {
      const out = new Float32Array(n - (b - a) - x);
      out.set(ch.subarray(0, a - x));
      for (let i = 0; i < x; i++) {
        const t = (i + 1) / (x + 1);
        out[a - x + i] = ch[a - x + i] * (1 - t) + ch[b + i] * t;
      }
      out.set(ch.subarray(b + x), a);
      return out;
    });
  }

  // Smooth raised-cosine fades.
  function applyFade(channels, rate, inSec, outSec) {
    const n = channels[0].length;
    const fi = Math.min(n, Math.round(inSec * rate)), fo = Math.min(n, Math.round(outSec * rate));
    return channels.map((src) => {
      const ch = src.slice();
      for (let i = 0; i < fi; i++) ch[i] *= 0.5 - 0.5 * Math.cos(Math.PI * i / fi);
      for (let i = 0; i < fo; i++) ch[n - 1 - i] *= 0.5 - 0.5 * Math.cos(Math.PI * i / fo);
      return ch;
    });
  }

  // Average loudness (RMS, dBFS) of the parts that are not near-silent.
  function gatedRmsDb(channels, rate) {
    const n = channels[0].length, win = Math.max(1, Math.round(rate * 0.05));
    let sum = 0, count = 0;
    for (let s = 0; s < n; s += win) {
      const e = Math.min(n, s + win);
      let w = 0;
      for (const ch of channels) for (let i = s; i < e; i++) w += ch[i] * ch[i];
      w /= (e - s) * channels.length;
      if (w > 1e-5) { sum += w; count++; }   // above about -50 dBFS
    }
    return count ? db(Math.sqrt(sum / count)) : -Infinity;
  }

  // Keeps every sample at or below |ceiling| by lowering the gain smoothly
  // around loud spots (look-ahead of 10 ms), so peaks are not clipped.
  function limit(channels, rate, ceilingDb) {
    const n = channels[0].length, ceiling = lin(ceilingDb), L = Math.max(1, Math.round(rate * 0.01));
    const need = new Float32Array(n).fill(1);
    for (let i = 0; i < n; i++) {
      let p = 0;
      for (const ch of channels) { const a = Math.abs(ch[i]); if (a > p) p = a; }
      if (p > ceiling) need[i] = ceiling / p;
    }
    // minimum over [i-L, i+L], then average over [i-L/2, i+L/2]
    const mins = new Float32Array(n), deque = [];
    for (let i = 0, j = 0; i < n; i++) {
      const hi = Math.min(n - 1, i + L);
      for (; j <= hi; j++) { while (deque.length && need[deque[deque.length - 1]] >= need[j]) deque.pop(); deque.push(j); }
      while (deque[0] < i - L) deque.shift();
      mins[i] = need[deque[0]];
    }
    const half = Math.max(1, L >> 1), prefix = new Float64Array(n + 1);
    for (let i = 0; i < n; i++) prefix[i + 1] = prefix[i] + mins[i];
    const env = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const a = Math.max(0, i - half), b = Math.min(n, i + half + 1);
      env[i] = (prefix[b] - prefix[a]) / (b - a);
    }
    return channels.map((ch) => ch.map((x, i) => x * env[i]));
  }

  // Brings the average loudness to a target, then limits peaks.
  const LOUDNESS = {
    standard: { targetRmsDb: -18, ceilingDb: -3 },
    child: { targetRmsDb: -24, ceilingDb: -6 }
  };
  function normalize(channels, rate, mode) {
    const { targetRmsDb, ceilingDb } = LOUDNESS[mode] || LOUDNESS.standard;
    const rms = gatedRmsDb(channels, rate);
    if (!isFinite(rms)) return { channels, gainDb: 0 };
    const gainDb = Math.max(-24, Math.min(24, targetRmsDb - rms));
    return { channels: limit(applyGain(channels, gainDb), rate, ceilingDb), gainDb };
  }

  // ---- Background noise reduction (spectral gating) ----
  // The noise is learned from the quietest moments of the track: the average
  // spectrum of its quietest 10 % of frames. Every frame is then turned down,
  // per frequency, where it is not clearly louder than that noise. Gains are
  // smoothed over frequency and time so the result does not "warble". Works
  // for steady noise: hiss, hum, fans and room tone.
  const NR_N = 2048, NR_HOP = 512;
  const NR_WINDOW = Float32Array.from({ length: NR_N }, (_, i) => 0.5 - 0.5 * Math.cos(2 * Math.PI * i / NR_N));
  const NOISE_AMOUNT = {
    light: { overSub: 1.5, floorDb: -8 },
    medium: { overSub: 2, floorDb: -14 },
    strong: { overSub: 3, floorDb: -22 }
  };

  // In-place radix-2 FFT (|re| and |im| have a power-of-two length).
  function fft(re, im) {
    const n = re.length;
    for (let i = 1, j = 0; i < n; i++) {
      let bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (let len = 2; len <= n; len <<= 1) {
      const half = len >> 1, step = -2 * Math.PI / len;
      for (let k = 0; k < half; k++) {
        const wr = Math.cos(step * k), wi = Math.sin(step * k);
        for (let i = k; i < n; i += len) {
          const b = i + half, tr = re[b] * wr - im[b] * wi, ti = re[b] * wi + im[b] * wr;
          re[b] = re[i] - tr; im[b] = im[i] - ti; re[i] += tr; im[i] += ti;
        }
      }
    }
  }

  // Calls fn(re, im) for every frame of |x| (zero-padded at both ends) and
  // overlap-adds the changed frames back. Returns the new samples.
  function stft(x, fn) {
    const n = x.length, pad = NR_N, total = n + 2 * pad;
    const out = new Float32Array(total), re = new Float64Array(NR_N), im = new Float64Array(NR_N);
    const norm = 1.5;   // sum of the squared Hann window at 75 % overlap
    for (let start = 0, f = 0; start + NR_N <= total; start += NR_HOP, f++) {
      for (let i = 0; i < NR_N; i++) {
        const k = start + i - pad;
        re[i] = (k >= 0 && k < n ? x[k] : 0) * NR_WINDOW[i]; im[i] = 0;
      }
      fft(re, im);
      fn(re, im, f);
      for (let i = 0; i < NR_N; i++) im[i] = -im[i];   // inverse FFT via conjugation
      fft(re, im);
      for (let i = 0; i < NR_N; i++) out[start + i] += re[i] / NR_N * NR_WINDOW[i] / norm;
    }
    return out.slice(pad, pad + n);
  }

  // The noise's power per frequency bin, or null when the track is too short
  // or silent. |contrastDb| says how much quieter the quiet frames are than the
  // typical frame; a small value means there was no real pause to learn from.
  function noiseProfile(channels, rate) {
    const n = channels[0].length;
    if (n < NR_N * 2) return null;
    const mono = new Float32Array(n);
    for (const ch of channels) for (let i = 0; i < n; i++) mono[i] += ch[i] / channels.length;
    const bins = NR_N / 2 + 1, frames = [];
    const re = new Float64Array(NR_N), im = new Float64Array(NR_N);
    for (let start = 0; start + NR_N <= n; start += NR_HOP) {
      for (let i = 0; i < NR_N; i++) { re[i] = mono[start + i] * NR_WINDOW[i]; im[i] = 0; }
      fft(re, im);
      const p = new Float32Array(bins);
      let e = 0;
      for (let b = 0; b < bins; b++) { p[b] = re[b] * re[b] + im[b] * im[b]; e += p[b]; }
      frames.push({ p, e });
    }
    const sorted = frames.map((f) => f.e).sort((a, b) => a - b);
    const median = sorted[sorted.length >> 1];
    if (!(median > 0)) return null;
    const count = Math.max(3, Math.round(frames.length * 0.1)), cut = sorted[Math.min(sorted.length - 1, count - 1)];
    const power = new Float32Array(bins);
    let used = 0, quiet = 0;
    for (const f of frames) {
      if (f.e > cut || used >= count) continue;
      for (let b = 0; b < bins; b++) power[b] += f.p[b];
      quiet += f.e; used++;
    }
    for (let b = 0; b < bins; b++) power[b] /= used;
    const contrastDb = 10 * Math.log10(median / Math.max(1e-20, quiet / used));
    return { power, contrastDb, rate };
  }

  // Reduces the noise described by |profile| (from noiseProfile) by |amount|:
  // "light", "medium" or "strong". Keeps the length.
  function reduceNoise(channels, rate, profile, amount = "medium") {
    const { overSub, floorDb } = NOISE_AMOUNT[amount] || NOISE_AMOUNT.medium;
    const floor = lin(floorDb), bins = NR_N / 2 + 1, noise = profile.power;
    return channels.map((x) => {
      if (x.length < NR_HOP) return x.slice();
      const prev = new Float32Array(bins).fill(1), g = new Float32Array(bins), sm = new Float32Array(bins);
      return stft(x, (re, im) => {
        for (let b = 0; b < bins; b++) {
          const p = re[b] * re[b] + im[b] * im[b];
          g[b] = p > 0 ? Math.max(floor, 1 - overSub * noise[b] / p) : floor;
        }
        // smooth over neighbouring bins, then let gains fall slowly and rise fast
        for (let b = 0; b < bins; b++) sm[b] = (g[Math.max(0, b - 1)] + g[b] + g[Math.min(bins - 1, b + 1)]) / 3;
        for (let b = 0; b < bins; b++) {
          const v = sm[b] < prev[b] ? prev[b] * 0.5 + sm[b] * 0.5 : sm[b];
          prev[b] = v;
          re[b] *= v; im[b] *= v;
          if (b > 0 && b < NR_N / 2) { re[NR_N - b] *= v; im[NR_N - b] *= v; }
        }
      });
    });
  }

  // ---- Doll speaker preset (small 4 ohm speaker behind fabric) ----
  // A small speaker cannot play deep bass: below its resonance the cone only
  // moves further (rattle, distortion) and the amplifier wastes power on sound
  // nobody hears. So the preset (1) removes bass below 200 Hz with a steep
  // 24 dB/octave high-pass (two Butterworth biquads), (2) lifts the voice
  // range a little (+3 dB around 2.5 kHz) and the top (+2 dB shelf from
  // 6 kHz) to make up for the doll's fabric, then (3) limits peaks to -1 dBFS.
  // These are starting values until the chosen speaker's response is measured.
  const DOLL_SPEAKER = { highPassHz: 200, presenceHz: 2500, presenceDb: 3, presenceQ: 1, shelfHz: 6000, shelfDb: 2, ceilingDb: -1 };

  // RBJ "Audio EQ Cookbook" biquads, normalized so a0 = 1.
  function biquadCoeffs(type, rate, f0, q, gainDb = 0) {
    const w = 2 * Math.PI * f0 / rate, cos = Math.cos(w), sin = Math.sin(w), alpha = sin / (2 * q), A = Math.pow(10, gainDb / 40);
    let b0, b1, b2, a0, a1, a2;
    if (type === "highpass") {
      b0 = (1 + cos) / 2; b1 = -(1 + cos); b2 = (1 + cos) / 2; a0 = 1 + alpha; a1 = -2 * cos; a2 = 1 - alpha;
    } else if (type === "peak") {
      b0 = 1 + alpha * A; b1 = -2 * cos; b2 = 1 - alpha * A; a0 = 1 + alpha / A; a1 = -2 * cos; a2 = 1 - alpha / A;
    } else {   // highshelf, shelf slope 1
      const s = 2 * Math.sqrt(A) * alpha;
      b0 = A * ((A + 1) + (A - 1) * cos + s); b1 = -2 * A * ((A - 1) + (A + 1) * cos); b2 = A * ((A + 1) + (A - 1) * cos - s);
      a0 = (A + 1) - (A - 1) * cos + s; a1 = 2 * ((A - 1) - (A + 1) * cos); a2 = (A + 1) - (A - 1) * cos - s;
    }
    return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0];
  }
  function runBiquad(x, [b0, b1, b2, a1, a2]) {
    const y = new Float32Array(x.length);
    let x1 = 0, x2 = 0, y1 = 0, y2 = 0;
    for (let i = 0; i < x.length; i++) {
      const v = b0 * x[i] + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
      x2 = x1; x1 = x[i]; y2 = y1; y1 = v; y[i] = v;
    }
    return y;
  }
  function dollSpeaker(channels, rate, opts = DOLL_SPEAKER) {
    const o = { ...DOLL_SPEAKER, ...opts };
    const stages = [
      biquadCoeffs("highpass", rate, o.highPassHz, 0.5412),   // 4th-order Butterworth = two biquads
      biquadCoeffs("highpass", rate, o.highPassHz, 1.3066),
      biquadCoeffs("peak", rate, o.presenceHz, o.presenceQ, o.presenceDb),
      biquadCoeffs("highshelf", rate, o.shelfHz, 0.7071, o.shelfDb)
    ];
    const filtered = channels.map((ch) => stages.reduce((x, c) => runBiquad(x, c), ch));
    return limit(filtered, rate, o.ceilingDb);
  }

  // Runs |fn| on the samples of [fromSec, toSec) only and puts the result back.
  // When the length is unchanged, the edges are cross-faded over 5 ms with the
  // original so they do not click. Returns { channels, a, b, length }.
  function processRange(channels, rate, fromSec, toSec, fn) {
    const n = channels[0].length;
    const a = Math.max(0, Math.min(n, Math.round(fromSec * rate))), b = Math.max(a, Math.min(n, Math.round(toSec * rate)));
    const out = fn(channels.map((ch) => ch.slice(a, b)));
    const m = out[0].length, x = m === b - a ? Math.min(Math.round(rate * 0.005), Math.floor(m / 2)) : 0;
    const result = channels.map((ch, c) => {
      const o = new Float32Array(n - (b - a) + m), s = out[c].slice();
      for (let i = 0; i < x; i++) {
        const t = (i + 1) / (x + 1);
        s[i] = ch[a + i] * (1 - t) + s[i] * t;
        s[m - 1 - i] = ch[b - 1 - i] * (1 - t) + s[m - 1 - i] * t;
      }
      o.set(ch.subarray(0, a)); o.set(s, a); o.set(ch.subarray(b), a + m);
      return o;
    });
    return { channels: result, a, b, length: m };
  }

  // Min/max per block of samples, for drawing the waveform quickly.
  function buildPeaks(channels, block) {
    const n = channels[0].length, count = Math.ceil(n / block);
    const min = new Float32Array(count), max = new Float32Array(count);
    for (let b = 0; b < count; b++) {
      let lo = 0, hi = 0;
      for (const ch of channels) for (let i = b * block, e = Math.min(n, i + block); i < e; i++) { const x = ch[i]; if (x < lo) lo = x; if (x > hi) hi = x; }
      min[b] = lo; max[b] = hi;
    }
    return { block, min, max };
  }

  const api = { OUTPUT_RATE, LOUDNESS, wavInfo, isToyWav, encodeWav, peakOf, applyGain, trimSilence, applyFade, cutRange, processRange, gatedRmsDb, limit, normalize, buildPeaks, noiseProfile, reduceNoise, NOISE_AMOUNT, dollSpeaker, DOLL_SPEAKER };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SweetYaarAudio = api;
})(typeof self !== "undefined" ? self : globalThis);
