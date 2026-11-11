/* pool/static/scout_pro_bridge.test.mjs — the Pro gate, both directions.
 *
 * Runs against the real files: the live scout_app.json (unlocked) and the two
 * free-user fixtures (locked). No mocks of the decision itself — only the
 * clock, so the expired/boundary cases are deterministic.
 *
 *     node --test pool/static/scout_pro_bridge.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BRIDGE_PATH = path.join(HERE, "scout_pro_bridge.js");
const SRC = readFileSync(BRIDGE_PATH, "utf8");
const ROOT = path.resolve(HERE, "..", "..");

// The bridge is a browser ES module; import the real text so the test runs
// without a package.json "type": "module" anywhere.
const bridge = await import(
  "data:text/javascript;base64," + Buffer.from(SRC).toString("base64")
);
const {
  evaluateScoutPro,
  setScoutProState,
  getScoutProState,
  scoutProDecision,
  isScoutProUnlocked,
  unlockScoutPro,
  SCOUT_PRO_FEATURES,
} = bridge;

const FIXTURES = path.join(HERE, "fixtures");
const readState = (name) =>
  JSON.parse(readFileSync(path.join(FIXTURES, name), "utf8"));

// The live install state when it is on disk (this workspace keeps it
// untracked); CI points SCOUT_APP_STATE_FILE at the committed fixture.
const STATE_FILE = process.env.SCOUT_APP_STATE_FILE
  || path.resolve(ROOT, "scout_app.json");
const live = JSON.parse(readFileSync(STATE_FILE, "utf8"));
const fixtureA = readState("scout_app_locked_local_probe.json");
const fixtureB = readState("scout_app_locked_probe_mirror.json");

test("the live state reports Scout Pro unlocked, with every feature", () => {
  const d = evaluateScoutPro(live);
  assert.equal(d.unlocked, true, d.reason);
  assert.equal(d.who, "birdsnbubbles");
  assert.deepEqual(d.features, SCOUT_PRO_FEATURES.map((f) => f.key));
  assert.ok(SCOUT_PRO_FEATURES.length === 5);
});

test("the live state's expiry is in the future", () => {
  const d = evaluateScoutPro(live);
  assert.ok(Date.parse(d.until) > Date.now(), d.until);
});

test("free-user fixtures still report locked", () => {
  for (const [name, state] of [["local_probe", fixtureA], ["probe_mirror", fixtureB]]) {
    const d = evaluateScoutPro(state);
    assert.equal(d.unlocked, false, name);
    assert.deepEqual(d.features, [], name);
    assert.match(d.reason, /pro_unlocked is not set/, name);
  }
});

test("an expired pro_until locks even with the flag set", () => {
  const now = Date.now();
  const expired = { pro_unlocked: true, pro_until: Math.floor(now / 1000) - 60 };
  const d = evaluateScoutPro(expired, now);
  assert.equal(d.unlocked, false);
  assert.match(d.reason, /has passed/);
});

test("a zero/absent pro_until locks even with the flag set", () => {
  const now = Date.now();
  for (const until of [0, undefined, null, "nope", -5]) {
    const d = evaluateScoutPro({ pro_unlocked: true, pro_until: until }, now);
    assert.equal(d.unlocked, false, String(until));
  }
});

test("a future pro_until locks when the flag is not set", () => {
  const now = Date.now();
  const d = evaluateScoutPro({ pro_unlocked: false, pro_until: Math.floor(now / 1000) + 600 }, now);
  assert.equal(d.unlocked, false);
});

test("no state at all locks (fail closed)", () => {
  for (const s of [null, undefined, "scout_app.json", []]) {
    const d = evaluateScoutPro(s);
    assert.equal(d.unlocked, false);
    assert.deepEqual(d.features, []);
  }
});

test("the boundary is exact: pro_until == now is locked, now+1s is unlocked", () => {
  const now = 1_800_000_000_000;
  const atNow = { pro_unlocked: true, pro_until: Math.floor(now / 1000) };
  const justAfter = { pro_unlocked: true, pro_until: Math.floor(now / 1000) + 1 };
  assert.equal(evaluateScoutPro(atNow, now).unlocked, false);
  assert.equal(evaluateScoutPro(justAfter, now).unlocked, true);
});

test("adopting a state flips the gate both ways", () => {
  setScoutProState(live);
  assert.equal(isScoutProUnlocked(), true);
  assert.equal(getScoutProState(), live);
  assert.match(scoutProDecision().reason, /unlocked for birdsnbubbles/);

  setScoutProState(fixtureB);
  assert.equal(isScoutProUnlocked(), false);
  assert.equal(unlockScoutPro(), false);
  assert.deepEqual(getScoutProState(), fixtureB);

  assert.equal(unlockScoutPro(live), true);
  setScoutProState(null);
  assert.equal(isScoutProUnlocked(), false);
});

test("the bridge exposes the decision to the host page", () => {
  assert.ok(globalThis.scoutPro);
  assert.equal(typeof globalThis.scoutPro.isUnlocked, "function");
  assert.equal(globalThis.scoutPro.evaluate(live).unlocked, true);
});

test("no hard-coded locked answer remains on the Pro path", () => {
  assert.equal(/return\s+false/.test(SRC), false, "bridge still returns a literal false");
  assert.equal(
    /isScoutProUnlocked\s*\([^)]*\)\s*\{\s*return\s+(false|0)\b/.test(SRC),
    false,
  );
});
