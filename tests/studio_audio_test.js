"use strict";

// app/public/studio/audio.js: conversion and editing helpers.
const assert = require("assert");
const A = require("../app/public/studio/audio.js");

const RATE = 44100;
const tone = (sec, amp, freq = 440) => Float32Array.from({ length: Math.round(sec * RATE) }, (_, i) => amp * Math.sin(2 * Math.PI * freq * i / RATE));
const concat = (...parts) => { const out = new Float32Array(parts.reduce((n, p) => n + p.length, 0)); let o = 0; for (const p of parts) { out.set(p, o); o += p.length; } return out; };
const db = (x) => 20 * Math.log10(x);

// WAV round trip and format check
{
  const left = tone(0.1, 0.5), right = tone(0.1, 0.25);
  const wav = A.encodeWav([left, right], RATE);
  const info = A.wavInfo(wav);
  assert.deepStrictEqual(info, { format: 1, channels: 2, rate: RATE, bits: 16 });
  assert.ok(A.isToyWav(info));
  assert.strictEqual(wav.byteLength, 44 + left.length * 4);
  assert.ok(!A.isToyWav({ ...info, rate: 48000 }));
  assert.ok(!A.isToyWav({ ...info, bits: 24 }));
  assert.ok(!A.isToyWav({ ...info, channels: 6 }));
  assert.strictEqual(A.wavInfo(new ArrayBuffer(8)), null);
  assert.strictEqual(A.wavInfo(new TextEncoder().encode("ID3 not a wav file at all").buffer), null);
}

// trimSilence
{
  const quiet = new Float32Array(RATE);           // 1 s of silence
  const x = concat(quiet, tone(0.5, 0.5), quiet.slice(0, RATE / 2));
  const out = A.trimSilence([x], RATE, { thresholdDb: -50, padMs: 30 });
  const keptSec = out.channels[0].length / RATE;
  assert.ok(Math.abs(keptSec - 0.56) < 0.03, `kept ${keptSec}`);
  assert.ok(Math.abs(out.removedSec - (2 - 0.56)) < 0.05);
  assert.strictEqual(A.trimSilence([quiet], RATE).silent, true);
  const noisy = A.trimSilence([concat(tone(0.2, 0.5))], RATE);
  assert.ok(noisy.removedSec < 0.01);
}

// fades
{
  const x = new Float32Array(RATE).fill(1);
  const [y] = A.applyFade([x], RATE, 0.25, 0.5);
  assert.strictEqual(y[0], 0);
  assert.strictEqual(y[y.length - 1], 0);
  assert.ok(Math.abs(y[Math.round(RATE * 0.125)] - 0.5) < 0.01);
  assert.strictEqual(y[Math.round(RATE * 0.4)], 1);
  assert.strictEqual(x[0], 1, "input untouched");
}

// applyGain on a range
{
  const x = new Float32Array(RATE).fill(0.1);
  const [y] = A.applyGain([x], -6.0206, { from: 0.25, to: 0.5 }, RATE);   // about half
  assert.strictEqual(y[0], x[0]);
  assert.ok(Math.abs(y[Math.round(RATE * 0.3)] - 0.05) < 1e-4);
  assert.strictEqual(y[Math.round(RATE * 0.6)], x[0]);
  const mid = y[Math.round(RATE * 0.25) - 50];
  assert.ok(mid < 0.1 && mid > 0.05, "blended edge");
  assert.ok(Math.abs(A.applyGain([x], 0, { from: 0, to: 1 }, RATE)[0][100] - 0.1) < 1e-6);
  assert.ok(Math.abs(A.applyGain([x], -6.0206)[0][5] - 0.05) < 1e-4);
}

// cutRange
{
  const x = new Float32Array(RATE).fill(0.5);
  const [y] = A.cutRange([x], RATE, 0.25, 0.5);
  assert.ok(Math.abs(y.length / RATE - (0.75 - 0.005)) < 0.001, `length ${y.length}`);
  assert.ok(y.every((v) => Math.abs(v - 0.5) < 1e-6), "constant signal stays constant across the join");
  assert.strictEqual(A.cutRange([x], RATE, 0.3, 0.3)[0], x);
  const edge = A.cutRange([x], RATE, 0, 0.5)[0];
  assert.strictEqual(edge.length, RATE / 2);
  assert.strictEqual(A.cutRange([x], RATE, 0.5, 5)[0].length, RATE / 2);
}

// normalize: loudness lands on target and peaks stay under the ceiling
{
  const x = concat(tone(2, 0.05), new Float32Array(RATE / 2), tone(2, 0.05));
  for (const mode of ["standard", "child"]) {
    const { targetRmsDb, ceilingDb } = A.LOUDNESS[mode];
    const out = A.normalize([x], RATE, mode);
    assert.ok(Math.abs(A.gatedRmsDb(out.channels, RATE) - targetRmsDb) < 1.0, `${mode} rms`);
    assert.ok(db(A.peakOf(out.channels)) <= ceilingDb + 0.05, `${mode} peak`);
  }
  // spiky material is limited, not clipped flat
  const spiky = tone(2, 0.1); spiky[40000] = 0.99;
  const out = A.normalize([spiky], RATE, "child");
  assert.ok(db(A.peakOf(out.channels)) <= -6 + 0.05);
  assert.deepStrictEqual(A.normalize([new Float32Array(1000)], RATE, "standard").gainDb, 0);
}

// peaks
{
  const x = Float32Array.from([0, 0.5, -0.25, 0.125]);
  const p = A.buildPeaks([x], 2);
  assert.deepStrictEqual([...p.max], [0.5, 0.125]);
  assert.deepStrictEqual([...p.min], [0, -0.25]);
}

// processRange: only the range changes; same length is cross-faded, other lengths are spliced
{
  const ch = [Float32Array.from({ length: 1000 }, () => 1)];
  const half = A.processRange(ch, 1000, 0.2, 0.6, (s) => s.map((c) => c.map((x) => x * 0.5)));
  assert.strictEqual(half.channels[0].length, 1000);
  assert.strictEqual(half.channels[0][100], 1);
  assert.strictEqual(half.channels[0][400], 0.5);
  assert.strictEqual(half.channels[0][800], 1);
  assert.ok(half.channels[0][200] > 0.5 && half.channels[0][200] < 1);   // blended edge
  const shorter = A.processRange(ch, 1000, 0.2, 0.6, (s) => s.map((c) => c.slice(0, 100)));
  assert.strictEqual(shorter.channels[0].length, 700);
  assert.deepStrictEqual([shorter.a, shorter.b, shorter.length], [200, 600, 100]);
}

// noise reduction: learns the noise from the quiet start, lowers it, keeps the tone
{
  let seed = 1;
  const rnd = () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648 * 2 - 1; };
  const n = RATE * 2, x = new Float32Array(n);
  for (let i = 0; i < n; i++) x[i] = 0.01 * rnd() + (i > RATE / 2 ? 0.3 * Math.sin(2 * Math.PI * 440 * i / RATE) : 0);
  const rmsDb = (a, s, e) => { let q = 0; for (let i = s; i < e; i++) q += a[i] * a[i]; return db(Math.sqrt(q / (e - s))); };
  const profile = A.noiseProfile([x], RATE);
  assert.ok(profile.contrastDb > 20);
  const quiet = [2000, RATE / 2 - 2000], loud = [RATE, n - 5000];
  let last = rmsDb(x, ...quiet);
  for (const amount of ["light", "medium", "strong"]) {
    const [y] = A.reduceNoise([x], RATE, profile, amount);
    assert.strictEqual(y.length, n);
    const noise = rmsDb(y, ...quiet);
    assert.ok(noise < last - 3, `${amount} lowers the noise further`);
    assert.ok(Math.abs(rmsDb(y, ...loud) - rmsDb(x, ...loud)) < 0.5, `${amount} keeps the tone`);
    last = noise;
  }
  // with no noise to remove, the audio comes back unchanged
  const [same] = A.reduceNoise([x], RATE, { power: new Float32Array(1025) }, "strong");
  let maxErr = 0; for (let i = 0; i < n; i++) maxErr = Math.max(maxErr, Math.abs(same[i] - x[i]));
  assert.ok(maxErr < 1e-4);
  assert.strictEqual(A.noiseProfile([new Float32Array(1000)], RATE), null);   // too short
}

// doll speaker preset: deep bass removed, voice range kept and lifted a little, peaks limited
{
  const gainAt = (freq) => {
    const x = tone(1, 0.1, freq), [y] = A.dollSpeaker([x], RATE);
    const rms = (a) => { let q = 0; for (let i = RATE / 2; i < RATE; i++) q += a[i] * a[i]; return Math.sqrt(q / (RATE / 2)); };
    return db(rms(y) / rms(x));
  };
  assert.ok(gainAt(60) < -30, "60 Hz hum and deep bass are gone");
  assert.ok(gainAt(100) < -20);
  assert.ok(Math.abs(gainAt(200) + 3) < 1, "-3 dB at the 200 Hz corner");
  assert.ok(Math.abs(gainAt(800)) < 1, "voice fundamentals unchanged");
  assert.ok(Math.abs(gainAt(2500) - 3) < 1, "+3 dB presence at 2.5 kHz");
  const loud = [tone(0.5, 0.99, 2500)], [y] = A.dollSpeaker(loud, RATE);
  assert.ok(A.peakOf([y]) <= Math.pow(10, -1 / 20) + 1e-3, "peaks limited to -1 dBFS");
}

console.log("studio audio tests passed");
