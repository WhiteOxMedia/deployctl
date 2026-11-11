/* pool/static/scout_host.test.mjs — the host half: load -> inject -> render.
 *
 * Runs against the REAL host module and the REAL bridge (no reimplementation),
 * with fetch stubbed only at the transport boundary.
 *
 *     node --test pool/static/scout_host.test.mjs
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");

// The page modules are browser ES modules; import the real text so no
// package.json "type": "module" is needed. scout_host.js imports
// "./scout_pro_bridge.js", so the bridge goes in as a data URL too.
const BRIDGE_SRC = readFileSync(path.join(HERE, "scout_pro_bridge.js"), "utf8");
const BRIDGE_URL = "data:text/javascript;base64,"
  + Buffer.from(BRIDGE_SRC).toString("base64");
const HOST_SRC = readFileSync(path.join(HERE, "scout_host.js"), "utf8")
  .replace("from \"./scout_pro_bridge.js\"", "from \"" + BRIDGE_URL + "\"");
const host = await import(
  "data:text/javascript;base64," + Buffer.from(HOST_SRC).toString("base64")
);
const bridge = await import(BRIDGE_URL);

const { buildScoutProView, fetchScoutProState, loadAndRender } = host;

const NOW_MS = Date.parse("2026-11-11T12:00:00Z");
const FUTURE = Math.floor(Date.parse("2036-11-08T00:00:00Z") / 1000);
const PAST = Math.floor(Date.parse("2020-01-01T00:00:00Z") / 1000);

function response(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    json: async () => {
      if (body instanceof Error) throw body;
      return body;
    },
  };
}

function fakeFetch(impl) {
  const seen = [];
  const fn = async (url, opts) => {
    seen.push({ url, opts });
    return impl(url, opts);
  };
  fn.seen = seen;
  return fn;
}

function stubRoot(doc) {
  const els = new Map();
  const el = (sel) => {
    if (!els.has(sel)) {
      els.set(sel, {
        textContent: "",
        className: "",
        attrs: {},
        children: [],
        setAttribute(k, v) { this.attrs[k] = v; },
        getAttribute(k) { return this.attrs[k]; },
        appendChild(child) { this.children.push(child); },
      });
    }
    return els.get(sel);
  };
  return {
    ownerDocument: { createElement: () => ({ textContent: "", className: "", setAttribute() {} }) },
    querySelector: (sel) => el(sel),
    els,
  };
}

test("the loader asks for the state file with cache disabled", async () => {
  const fetchImpl = fakeFetch(() => response({ pro_unlocked: true, pro_until: FUTURE }));
  const state = await fetchScoutProState("/scout_app.json", fetchImpl);
  assert.equal(state.pro_unlocked, true);
  assert.equal(fetchImpl.seen.length, 1);
  assert.equal(fetchImpl.seen[0].url, "/scout_app.json");
  assert.equal(fetchImpl.seen[0].opts.cache, "no-store");
});

test("a locked state file renders locked with every Pro surface off", async () => {
  const root = stubRoot();
  const view = await loadAndRender(
    root, "/scout_app.json",
    fakeFetch(() => response({ pro_unlocked: false, pro_until: 0 }))
  );
  assert.equal(view.unlocked, false);
  assert.equal(view.badge, "PRO LOCKED");
  assert.equal(view.tone, "locked");
  assert.ok(view.features.every((f) => f.enabled === false));
  assert.equal(root.querySelector("[data-scout-pro-badge]").textContent, "PRO LOCKED");
  assert.equal(root.querySelector("[data-scout-pro-features]").children.length, 5);
});

test("the unlocked install state renders unlocked and turns every surface on", async () => {
  const root = stubRoot();
  const state = {
    pro_unlocked: true, pro_until: FUTURE,
    pro_unlocked_for: "birdsnbubbles",
  };
  const view = await loadAndRender(
    root, "/scout_app.json", fakeFetch(() => response(state))
  );
  assert.equal(view.unlocked, true);
  assert.equal(view.badge, "PRO UNLOCKED");
  assert.equal(view.tone, "unlocked");
  assert.equal(view.who, "birdsnbubbles");
  assert.ok(view.until && view.until.startsWith("2036"));
  assert.ok(view.features.every((f) => f.enabled === true));
  assert.deepEqual(view.state, state, "the bridge received the loaded state");
  assert.equal(root.querySelector("[data-scout-pro-badge]").attrs["data-tone"], "unlocked");
});

test("an expired pro_until locks even though the flag is set", async () => {
  const view = await loadAndRender(
    stubRoot(), "/scout_app.json",
    fakeFetch(() => response({ pro_unlocked: true, pro_until: PAST }))
  );
  assert.equal(view.unlocked, false);
  assert.equal(view.features.filter((f) => f.enabled).length, 0);
  assert.match(view.reason, /has passed: locked/);
});

test("an HTTP failure renders locked and says why", async () => {
  const view = await loadAndRender(
    stubRoot(), "/scout_app.json",
    fakeFetch(() => response({}, { ok: false, status: 500 }))
  );
  assert.equal(view.unlocked, false);
  assert.equal(view.badge, "PRO LOCKED");
  assert.match(view.reason, /HTTP 500/);
});

test("a non-object body renders locked (never a free unlock)", async () => {
  for (const body of [[1, 2, 3], "unlocked", null]) {
    const view = await loadAndRender(
      stubRoot(), "/scout_app.json", fakeFetch(() => response(body))
    );
    assert.equal(view.unlocked, false, JSON.stringify(body));
    assert.match(view.reason, /not an object/);
  }
});

test("a transport error renders locked, not an exception", async () => {
  const view = await loadAndRender(
    stubRoot(), "/scout_app.json",
    fakeFetch(() => { throw new Error("network down"); })
  );
  assert.equal(view.unlocked, false);
  assert.match(view.reason, /network down/);
});

test("the view model derives the badge, meta and five surfaces from the decision", () => {
  const on = buildScoutProView({
    unlocked: true, reason: "r", until: "2036-11-08T00:00:00.000Z",
    who: "birdsnbubbles", features: bridge.SCOUT_PRO_FEATURES.map((f) => f.key),
  });
  assert.equal(on.features.length, 5);
  assert.equal(on.who, "birdsnbubbles");
  assert.equal(on.status, "All Pro surfaces are live.");

  const off = buildScoutProView({ unlocked: false, reason: "no state", features: [] });
  assert.equal(off.badge, "PRO LOCKED");
  assert.equal(off.until, null);
  assert.equal(off.features.filter((f) => f.enabled).length, 0);
});

test("the live scout_app.json on disk drives an unlocked page", async () => {
  const livePath = process.env.SCOUT_APP_STATE_FILE
    || path.join(ROOT, "scout_app.json");
  const live = JSON.parse(readFileSync(livePath, "utf8"));
  const view = await loadAndRender(
    stubRoot(), "/scout_app.json", fakeFetch(() => response(live))
  );
  assert.equal(view.unlocked, live.pro_unlocked === true
    && Number(live.pro_until) * 1000 > Date.now(), "page agrees with the file");
  assert.equal(view.unlocked, true, "this install is unlocked");
});
