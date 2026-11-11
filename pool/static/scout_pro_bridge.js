/* pool/static/scout_pro_bridge.js — Scout Pro gate, backed by the app state.
 *
 * `scout_app.json` (written by the Scout app) is the single source of truth.
 * Before this change the bridge answered `isScoutProUnlocked() => false`
 * unconditionally, so an unlocked install still rendered every Pro surface
 * locked. The decision is now ONE pure function so the UI, the host and the
 * tests cannot disagree about it:
 *
 *     unlocked  <=>  state.pro_unlocked === true
 *                    AND state.pro_until (epoch SECONDS) is in the future
 *
 * Fails closed: no state, no flag, a zero/absent `pro_until`, or an expired
 * `pro_until` all yield locked — a failed read can never hand out Pro.
 *
 * The host injects the state one of two ways:
 *   - set it on the global before this module loads:  globalThis.SCOUT_APP_STATE
 *   - call setScoutProState(state) after loading it from scout_app.json
 */

export const SCOUT_PRO_FEATURES = [
  { key: "remote_alerts", label: "Remote Alerts" },
  { key: "nfty_messages", label: "NFTY Messages" },
  { key: "jackpot_notifications", label: "Jackpot Notifications" },
  { key: "profile_sync", label: "Profile Sync" },
  { key: "server_watchdog", label: "Server Watchdog" },
];

const GLOBAL = typeof globalThis !== "undefined" ? globalThis : {};
const ALL_FEATURE_KEYS = SCOUT_PRO_FEATURES.map((f) => f.key);

let _state = GLOBAL.SCOUT_APP_STATE || null;

/**
 * The gate decision. Pure: same state + same clock -> same answer.
 * @param {object|null} state the scout_app.json object (or null)
 * @param {number} nowMs current epoch milliseconds
 */
export function evaluateScoutPro(state, nowMs) {
  const src = state && typeof state === "object" && !Array.isArray(state)
    ? state
    : null;
  const now = Number.isFinite(Number(nowMs)) ? Number(nowMs) : Date.now();
  const rawUntil = src ? Number(src.pro_until) : NaN;
  const untilMs = Number.isFinite(rawUntil) && rawUntil > 0 ? rawUntil * 1000 : 0;
  const flag = Boolean(src && src.pro_unlocked === true);
  const who = src && typeof src.pro_unlocked_for === "string"
    ? src.pro_unlocked_for
    : null;
  const untilIso = untilMs ? new Date(untilMs).toISOString() : null;

  const locked = (reason) => ({
    unlocked: false, reason, until: untilIso, who, features: [],
  });

  if (!src) return locked("no scout app state: locked");
  if (!flag) return locked("pro_unlocked is not set: locked");
  if (!untilMs) return locked("pro_until is missing or zero: locked");
  if (untilMs <= now) {
    return locked("pro_until " + untilIso + " has passed: locked");
  }
  return {
    unlocked: true,
    reason: "pro unlocked" + (who ? " for " + who : "") + " until " + untilIso,
    until: untilIso,
    who,
    features: ALL_FEATURE_KEYS.slice(),
  };
}

/** Adopt a state object (the host's scout_app.json) and re-evaluate. */
export function setScoutProState(state) {
  _state = state && typeof state === "object" ? state : null;
  return evaluateScoutPro(_state);
}

/** The state the bridge is currently judging (read-only for callers). */
export function getScoutProState() {
  return _state;
}

/** The full decision, for UI copy ("unlocked until ..." / why it is locked). */
export function scoutProDecision(nowMs) {
  return evaluateScoutPro(_state, nowMs);
}

/** True only for a live unlock: flag set AND pro_until in the future. */
export function isScoutProUnlocked(nowMs) {
  return evaluateScoutPro(_state, nowMs).unlocked;
}

/** Re-evaluate against the current state (optionally adopting a new one). */
export function unlockScoutPro(state) {
  if (state !== undefined) return setScoutProState(state).unlocked;
  return isScoutProUnlocked();
}

/** Re-read the hosted state (for a host that refreshed scout_app.json). */
export function refreshScoutPro(state) {
  return unlockScoutPro(state);
}

GLOBAL.scoutPro = {
  evaluate: evaluateScoutPro,
  setState: setScoutProState,
  getState: getScoutProState,
  decision: scoutProDecision,
  isUnlocked: isScoutProUnlocked,
  features: SCOUT_PRO_FEATURES.slice(),
};
