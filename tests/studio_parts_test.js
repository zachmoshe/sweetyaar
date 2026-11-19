"use strict";

// app/public/studio/parts.js: parts of a track in the wave editor.
const assert = require("assert");
const P = require("../app/public/studio/parts.js");

const ramp = (n, from = 0) => Float32Array.from({ length: n }, (_, i) => from + i);
const arr = (ch) => [...ch];

// spans, split, fuse
{
  assert.deepStrictEqual(P.spans([], 10), [[0, 10]]);
  assert.deepStrictEqual(P.spans([7, 3, 3, 0, 10], 10), [[0, 3], [3, 7], [7, 10]]);
  assert.deepStrictEqual(P.split([], 10, 2, 6), [2, 6]);
  assert.deepStrictEqual(P.split([5], 10, 0, 5), [5]);           // edges add nothing
  assert.deepStrictEqual(P.fuse([2, 4, 6, 8], 2, 8), [2, 8]);    // parts 2-4-6-8 become one
  assert.deepStrictEqual(P.fuse([2, 4], 0, 10), []);
  assert.strictEqual(P.partAt([3, 7], 10, 0), 0);
  assert.strictEqual(P.partAt([3, 7], 10, 3), 1);
  assert.strictEqual(P.partAt([3, 7], 10, 9), 2);
  assert.strictEqual(P.nearestEdge([3, 7], 10, 4), 3);
  assert.strictEqual(P.nearestEdge([3, 7], 10, 9), 10);
}

// insert: the inserted audio becomes its own part, later bounds move
{
  const r = P.insert([ramp(6)], [4], 2, [Float32Array.from([90, 91])]);
  assert.deepStrictEqual(arr(r.channels[0]), [0, 1, 90, 91, 2, 3, 4, 5]);
  assert.deepStrictEqual(r.bounds, [2, 4, 6]);
  const atStart = P.insert([ramp(3)], [], 0, [Float32Array.from([9])]);
  assert.deepStrictEqual(arr(atStart.channels[0]), [9, 0, 1, 2]);
  assert.deepStrictEqual(atStart.bounds, [1]);
  // mono into stereo is duplicated; stereo into mono makes the track stereo
  const st = P.insert([ramp(2), ramp(2, 10)], [], 1, [Float32Array.from([7])]);
  assert.deepStrictEqual(st.channels.map(arr), [[0, 7, 1], [10, 7, 11]]);
  const up = P.insert([ramp(2)], [], 2, [Float32Array.from([7]), Float32Array.from([8])]);
  assert.deepStrictEqual(up.channels.map(arr), [[0, 1, 7], [0, 1, 8]]);
  // into an empty track
  const empty = P.insert([new Float32Array(0)], [], 0, [ramp(3)]);
  assert.deepStrictEqual(arr(empty.channels[0]), [0, 1, 2]);
  assert.deepStrictEqual(empty.bounds, []);
}

// move: reorders the audio and the bounds
{
  const ch = [Float32Array.from([1, 1, 2, 2, 2, 3])], bounds = [2, 5];
  const last = P.move(ch, bounds, 2, 0);
  assert.deepStrictEqual(arr(last.channels[0]), [3, 1, 1, 2, 2, 2]);
  assert.deepStrictEqual(last.bounds, [1, 3]);
  const first = P.move(ch, bounds, 0, 2);
  assert.deepStrictEqual(arr(first.channels[0]), [2, 2, 2, 3, 1, 1]);
  assert.deepStrictEqual(first.bounds, [3, 4]);
  assert.strictEqual(P.move(ch, bounds, 1, 1).channels, ch);
}

// afterRemoval: bounds inside the removed range collapse to its start
{
  assert.deepStrictEqual(P.afterRemoval([2, 5, 8], 10, 4, 3), [2, 4, 5]);
  assert.deepStrictEqual(P.afterRemoval([2, 5], 10, 0, 3), [2]);
}

console.log("studio parts tests passed");
