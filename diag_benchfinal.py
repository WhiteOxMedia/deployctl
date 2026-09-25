r"""diag_benchfinal.py - the bench's final verdict snapshot.

Proves, on a SANDBOXED pass (production files redirected via the
module's own globals, same convention as the other diags):
  1. a full report_now() bench arc: flip at W37 (3 negative weeks +
     negative pool), two winning weeks, then a flip-back at W39 - the
     flip-back EVENT RECORD on the trail carries bench_final.
  2. bench_final holds the bench's final live verdict: to_date dollars,
     verdict word, and the cumulative text (the shared math).
  3. the bench was graded on an OPEN window (next_ev=None) - no
     governed-window closure was applied to the snapshot.
  4. the flip-back row in the audit trail renders the preserved
     verdict; the flip row carries nothing.
  5. dedupe: re-running the pass cannot double-persist the event.
All paths redirected; production files are never touched.
Run: .venv\Scripts\python.exe -X utf8 diag_benchfinal.py
"""
import json
import shutil
from pathlib import Path

import tide_learn as tl
import tidebar_weekly as tbw
import app as app_mod

BASE = Path(__file__).parent
S = BASE / "_test_benchfinal_dir"
shutil.rmtree(S, ignore_errors=True)
S.mkdir()

_saved = {k: getattr(tbw, k) for k in
          ("OUT_FILE", "JSON_FILE", "SNAP_OUTCOMES_FILE", "TRADES_FILE",
           "HISTORY_FILE", "FLIP_FILE", "FLIPGRADE_FILE", "FLIPGRADE_JSON",
           "FLIP_EVENTS_FILE")}
tbw.OUT_FILE = S / "weekly.txt"
tbw.JSON_FILE = S / "sidecar.json"
tbw.SNAP_OUTCOMES_FILE = S / "snap_outcomes.jsonl"
tbw.TRADES_FILE = S / "trades.jsonl"
tbw.HISTORY_FILE = S / "history.jsonl"
tbw.FLIP_FILE = S / "flips.json"
tbw.FLIPGRADE_FILE = S / "flipgrade.txt"
tbw.FLIPGRADE_JSON = S / "flipgrade.json"
tbw.FLIP_EVENTS_FILE = S / "flip_events.jsonl"

PASS = 0
def check(name, cond, detail=""):
    global PASS
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        print("      detail:", str(detail)[:900])
    PASS += bool(cond)

def _rec(wk, fit_usd, q_usd, other_src):
    # OUT: the fit realized fit_usd over 10 fires, the quantile side
    # q_usd over 10 fires; other_src names the in-force bar's twin.
    return {"week": wk, "generated_ts": "t", "states": {"OUT": {
        "in_force": {"fires": 10, "payers": 1, "usd": fit_usd,
                     "usd_per_fire": round(fit_usd / 10, 2)},
        "other": {"fires": 10, "payers": 1, "usd": q_usd,
                  "usd_per_fire": round(q_usd / 10, 2)},
        "other_src": other_src}}}

try:
    # the pass's staged construction: its own week is always staged
    # first, then the history it loads is replaced by the sandbox arc.
    # _week_fit_edge reads the states' usd_per_fire pair, so the arc
    # pins: fit edge = outcome-fitted $/fire - quantile $/fire.
    real_cand = tbw._week_candidates
    real_fitbar = tl._outcome_fit_bar
    tbw._week_candidates = lambda: (None, "no candidates this week")
    tbw.OUT_FILE.write_text("", encoding="utf-8")

    # W1..W3: the fit bleeds ($1.00/fire vs the quantile's $3.00) -
    # three losing weeks on a negative pool -> the gate flips OUT.
    tbw.HISTORY_FILE.write_text("".join(
        json.dumps(r) + "\n" for r in
        [_rec("2026-W35", 10.0, 30.0, "quantile"),
         _rec("2026-W36", 10.0, 30.0, "quantile"),
         _rec("2026-W37", 10.0, 30.0, "quantile")]), encoding="utf-8")
    tbw.FLIP_FILE.write_text(json.dumps(
        {"OUT": {"flipped": False}, "FLAT": {"flipped": False},
         "RISING": {"flipped": False}}), encoding="utf-8")
    tbw.report_now()   # the pass: appends its W38 thin record; gate flips

    evs = tbw._load_flip_events()
    check("the gate flipped OUT at W38 (the pass's own week)",
          len(evs) == 1 and evs[0]["state"] == "OUT"
          and evs[0]["action"] == "flip" and evs[0]["week"] == "2026-W38",
          evs)

    # W38 + W39: the fit recovers ($5.00/fire vs the quantile's $2.00)
    # - two winning weeks on a positive pool -> the gate flips back.
    tbw.HISTORY_FILE.write_text("".join(
        json.dumps(r) + "\n" for r in
        [_rec("2026-W35", 10.0, 30.0, "quantile"),
         _rec("2026-W36", 10.0, 30.0, "quantile"),
         _rec("2026-W37", 10.0, 10.0, "quantile"),
         _rec("2026-W38", 10.0, 30.0, "quantile"),   # the flip week
         _rec("2026-W39", 50.0, 20.0, "outcome-fitted"),
         _rec("2026-W40", 50.0, 20.0, "outcome-fitted")]),
        encoding="utf-8")
    tbw.report_now()   # the flip-back pass

    evs = tbw._load_flip_events()
    fb = next((e for e in evs if e.get("action") == "flip_back"), None)
    check("the gate flipped OUT back at W40",
          fb is not None and fb.get("week") == "2026-W40", evs)

    bf = (fb or {}).get("bench_final")
    check("the flip-back record carries the bench's FINAL verdict",
          isinstance(bf, dict) and bf.get("verdict") in ("PAYING",
                                                         "COSTING"), fb)
    check("the snapshot holds to_date, weeks, and the cumulative text",
          isinstance(bf, dict) and isinstance(bf.get("to_date"), float)
          and bf.get("weeks") == 1
          and "to date the bench is" in (bf.get("text") or ""), bf)

    # open window: the bench's newest evidence week is W38, so the open
    # aftermath reads W40 only ($50 vs $20 -> to_date = +30.0, PAYING)
    check("the snapshot graded the OPEN window (W40 only: +30.0, PAYING)",
          bf.get("to_date") == 30.0 and bf.get("verdict") == "PAYING", bf)

    # the trail render: the flip-back row preserves the verdict
    aud = app_mod._render_flip_audit()
    check("the flip-back row renders the preserved final verdict",
          "the bench's final live verdict" in aud
          and "the bench was PAYING when it ended" in aud, aud[-900:])
    check("the snapshot is not read as the OPEN bench strip (no strip: "
          "OUT is un-benched now)",
          "CURRENTLY BENCHED" not in aud, aud[-400:])
    check("the flip row carries no final verdict",
          aud.count("the bench's final live verdict") == 1, aud)

    # dedupe: re-running the pass cannot double-persist the flip-back
    n = len(tbw._load_flip_events())
    tbw.report_now()
    check("re-running the pass cannot double-persist the event (the "
          "snapshot rides the dedupe)",
          len(tbw._load_flip_events()) == n,
          (n, len(tbw._load_flip_events())))

    # a flip-back WITHOUT a graded open window ships no fabricated verdict
    tbw.FLIP_EVENTS_FILE.write_text(json.dumps(
        {"state": "FLAT", "action": "flip_back", "week": "2026-W40",
         "ts": "t", "winning_weeks": 2, "roll_delta": 1.0,
         "evidence": [{"week": "2026-W39", "fit_edge": 1.0},
                      {"week": "2026-W40", "fit_edge": 1.0}]}) + "\n",
        encoding="utf-8")
    ev2 = {"FLAT": {"action": "flip_back", "winning_weeks": 2,
                    "roll_delta": 1.0,
                    "evidence": [{"week": "2026-W39", "fit_edge": 1.0}]}}
    tbw._attach_bench_final(ev2, [])
    check("no flip on the trail / thin ledger -> no snapshot, never fake",
          "bench_final" not in ev2["FLAT"], ev2)
finally:
    for k, v in _saved.items():
        setattr(tbw, k, v)
    shutil.rmtree(S, ignore_errors=True)

print(f"\n{'ALL GREEN' if PASS == 9 else 'FAILURES PRESENT'} - {PASS}/9 checks")
raise SystemExit(0 if PASS == 9 else 1)
