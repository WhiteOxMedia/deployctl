/* pool/static/scout_host.js — the host page's half of the Pro gate.
 *
 * The bridge (scout_pro_bridge.js) knows the RULE but not where the state
 * lives. This module is the missing wiring: it loads scout_app.json, hands it
 * to the bridge, and renders whatever the bridge decides.
 *
 *     fetch scout_app.json  ->  setScoutProState(state)  ->  render(decision)
 *
 * Failures are rendered as LOCKED, never as unlocked: a missing file, a 500,
 * a non-JSON body or a non-object body all end in setScoutProState(null), and
 * the bridge's own fail-closed rule does the rest.
 *
 * Wire it in the page with either:
 *   <div data-scout-pro data-state-url="../../scout_app.json"></div>
 *   <script type="module" src="./scout_host.js"></script>
 * or call loadAndRender(el, url) yourself.
 */

import {
  SCOUT_PRO_FEATURES,
  getScoutProState,
  scoutProDecision,
  setScoutProState,
} from "./scout_pro_bridge.js";

/** Same-origin default for a pool deployment; the page can override it. */
export const DEFAULT_STATE_URL = "/api/scout/pro";

/**
 * Load the Scout app state. Throws on anything that is not a JSON object, so
 * the caller can render a locked reason instead of a half-true page.
 * @param {string} url
 * @param {Function} [fetchImpl] injectable for tests
 */
export async function fetchScoutProState(url = DEFAULT_STATE_URL, fetchImpl) {
  const doFetch = fetchImpl || (typeof fetch === "function" ? fetch : null);
  if (!doFetch) throw new Error("no fetch available to read " + url);
  const res = await doFetch(url, { cache: "no-store", credentials: "same-origin" });
  if (!res || !res.ok) {
    throw new Error("scout state request failed: HTTP " + (res ? res.status : "?"));
  }
  const data = await res.json();
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("scout state is not an object");
  }
  return data;
}

/**
 * Pure view model for the decision — no DOM, so it is testable as-is.
 * @param {object} decision the bridge's evaluateScoutPro() result
 */
export function buildScoutProView(decision) {
  const unlocked = Boolean(decision && decision.unlocked);
  const features = SCOUT_PRO_FEATURES.map((f) => ({
    key: f.key,
    label: f.label,
    enabled: Boolean(decision && Array.isArray(decision.features)
      && decision.features.includes(f.key)),
  }));
  return {
    unlocked,
    tone: unlocked ? "unlocked" : "locked",
    badge: unlocked ? "PRO UNLOCKED" : "PRO LOCKED",
    status: unlocked ? "All Pro surfaces are live." : "Pro surfaces are quiet.",
    reason: decision && decision.reason ? String(decision.reason) : "",
    until: decision && decision.until ? String(decision.until) : null,
    who: decision && decision.who ? String(decision.who) : null,
    features,
  };
}

/** Apply a view model to the host page's elements (all optional). */
export function renderScoutPro(root, decision) {
  const view = buildScoutProView(decision);
  if (!root) return view;

  const badge = root.querySelector("[data-scout-pro-badge]");
  if (badge) {
    badge.textContent = view.badge;
    badge.setAttribute("data-tone", view.tone);
  }
  const status = root.querySelector("[data-scout-pro-status]");
  if (status) status.textContent = view.status;
  const reason = root.querySelector("[data-scout-pro-reason]");
  if (reason) reason.textContent = view.reason;
  const until = root.querySelector("[data-scout-pro-until]");
  if (until) until.textContent = view.until ? "until " + view.until : "";
  const who = root.querySelector("[data-scout-pro-who]");
  if (who) who.textContent = view.who ? "for " + view.who : "";

  const list = root.querySelector("[data-scout-pro-features]");
  if (list) {
    list.textContent = "";
    for (const f of view.features) {
      const row = root.ownerDocument
        ? root.ownerDocument.createElement("li")
        : null;
      if (!row) break;
      row.className = "feature " + (f.enabled ? "on" : "off");
      row.setAttribute("data-feature", f.key);
      row.textContent = (f.enabled ? "\u2713 " : "\u2014 ") + f.label;
      list.appendChild(row);
    }
  }
  return view;
}

/**
 * Load, inject, render. Never rejects: a load failure becomes a locked view
 * whose reason says why.
 * @returns {Promise<object>} the view model actually rendered
 */
export async function loadAndRender(root, url = DEFAULT_STATE_URL, fetchImpl) {
  let decision;
  let error = null;
  try {
    const state = await fetchScoutProState(url, fetchImpl);
    decision = setScoutProState(state);
  } catch (err) {
    error = err;
    decision = setScoutProState(null);
  }
  const view = renderScoutPro(root, decision);
  if (error) {
    view.reason = view.reason + " (state unavailable: " + error.message + ")";
    const reason = root && root.querySelector
      ? root.querySelector("[data-scout-pro-reason]")
      : null;
    if (reason) reason.textContent = view.reason;
  }
  view.state = getScoutProState();
  view.now = scoutProDecision();
  return view;
}

/** Boot the page: find [data-scout-pro], load its state, render, wire refresh. */
export function boot(doc) {
  const d = doc || (typeof document !== "undefined" ? document : null);
  if (!d) return null;
  const root = d.querySelector("[data-scout-pro]");
  if (!root) return null;
  const url = root.getAttribute("data-state-url") || DEFAULT_STATE_URL;
  const run = () => loadAndRender(root, url).then((view) => {
    if (typeof d.dispatchEvent === "function" && typeof CustomEvent === "function") {
      d.dispatchEvent(new CustomEvent("scoutpro:ready", { detail: view }));
    }
    return view;
  });
  const refresh = d.querySelector("[data-scout-refresh]");
  if (refresh && refresh.addEventListener) {
    refresh.addEventListener("click", (ev) => {
      if (ev && ev.preventDefault) ev.preventDefault();
      run();
    });
  }
  run();
  return run;
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => boot(document));
  } else {
    boot(document);
  }
}
