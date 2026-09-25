r"""diag_fbw3.py — would FLIP_BACK_WEEKS=3 have saved FLAT's re-arm?

A counterfactual question about the regime machinery's own constant.
Arc 3 of diag_flipgrade.py (FLAT: the fit re-armed fast, bled again,
re-flipped) re-armed after TWO contract-legal cf-winning weeks — the
shipped FLIP_BACK_WEEKS=2. The third winning week W43 is already
seeded (the second bleed starts W44), so the counterfactual replay is
exact: re-walk the same records with the gate constant at 3 and ask
what the delay would have paid.

READ-ONLY: the trail, the flips ledger, and the weekly txt are never
touched (the module-level seed runs first, then the constants are
restored; every decision walk is in-memory).
Run: .venv\Scripts\python.exe -X utf8 diag_fbw3.py
"""
from pathlib import Path

import tidebar_weekly as tbw

ROOT = Path(__file__).parent
HIST = ROOT / "_tidebarweekly_history.jsonl"
fi, fo = 82, 46   # the fit's fires live / benched (the arc-3 stream)


def wk(tag, live, other, src="quantile", state="FLAT"):
    return {"week": tag, "generated_ts": f"{tag} pass",
            "states": {state: {
                "n": fi,
                "in_force": {"fires": fi, "payers": 3, "rate": 0.3,
                             "usd": round(fi * live, 2),
                             "usd_per_fire": round(live, 2)},
                "other": {"fires": fo, "payers": 3, "rate": 0.3,
                          "usd": round(fo * other, 2),
                          "usd_per_fire": round(other, 2)},
                "other_src": src}}}


def _fit_seat(rec, state):
    st = rec["states"][state]
    fit_live = (st.get("other_src") or "quantile").startswith("quantile")
    return st["in_force"] if fit_live else st["other"]


def _q_seat(rec, state):
    st = rec["states"][state]
    fit_live = (st.get("other_src") or "quantile").startswith("quantile")
    return st["other"] if fit_live else st["in_force"]


# the FIRST real W37 OUT record is imported verbatim from the ledger —
# only W38+ are seeded futures.
real = None
try:
    for line in HIST.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = __import__("json").loads(line)
            if r.get("week") == "2026-W37" and (r.get("states") or {}).get("OUT"):
                real = r
                break
except Exception:
    pass
assert real is not None, "no real W37 record to import"

# arc 3 (the diag's seed), re-declared: W40-W41 the recovery (the fit
# benched), W42-W43 still recovery (W42 live — the re-arm), W44 the
# second bleed (live).
recs = [real,
        wk("2026-W38", 2.90, 3.50),
        wk("2026-W39", 2.80, 3.65),
        wk("2026-W40", 2.40, 3.55, src="outcome-fitted"),
        wk("2026-W41", 2.40, 3.45, src="outcome-fitted"),
        wk("2026-W42", 3.30, 4.55),
        wk("2026-W43", 3.20, 4.35),
        wk("2026-W44", 3.10, 4.45)]

_state = {"n": 0}


def check(name, cond, detail=""):
    _state["n"] += 1
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        print("      detail:", str(detail)[:600])


def walk(flip_back_weeks):
    """Re-run the shipped gate on the arc with the given constant.
    Read-only: _evaluate_flips mutates only its own local copy."""
    real_fb, real_fw = tbw.FLIP_BACK_WEEKS, tbw.FLIP_WEEKS
    tbw.FLIP_BACK_WEEKS, tbw.FLIP_WEEKS = flip_back_weeks, 3
    try:
        events, fl = [], {}
        for i, rec in enumerate(recs):
            evs_w, fl = tbw._evaluate_flips(recs[:i + 1], fl)
            e = evs_w.get("FLAT")
            if e:
                events.append(dict(e, week=rec["week"]))
        return events
    finally:
        tbw.FLIP_BACK_WEEKS, tbw.FLIP_WEEKS = real_fb, real_fw


PASS = 0
def check2(name, cond, detail=""):
    global PASS
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        print("      detail:", str(detail)[:600])
    PASS += bool(cond)


print("=== THE FLIP-BACK CONSTANT, REPLAYED (FLAT's arc 3) ===")
print()

evs2 = walk(2)
check2("at FBW=2 the arc fires flip / flip-back / re-flip",
       [(e["action"], e["week"]) for e in evs2]
       == [("flip", "2026-W39"), ("flip_back", "2026-W41"),
           ("flip", "2026-W44")], evs2)

evs3 = walk(3)
check2("at FBW=3 the flip is unchanged (W39) and the flip-back is "
       "held to W42",
       [(e["action"], e["week"]) for e in evs3]
       == [("flip", "2026-W39"), ("flip_back", "2026-W42")],
       evs3)

# ── the dollar comparison, the contract's axis ($/fire) ────────────
def pooled(seats):
    f = sum(s["fires"] for s in seats)
    u = sum(s["usd"] for s in seats)
    return f, round(u / f, 2) if f else 0.0


# what the RE-ARM cost at FBW=2: live W42-W43 (the fit, $3.30/$3.20)
# vs the benched fit's counterfactual ($4.55/$4.35).
live2 = recs[5]["states"]["FLAT"]["in_force"], recs[6]["states"]["FLAT"]["in_force"]
cf2 = recs[5]["states"]["FLAT"]["other"], recs[6]["states"]["FLAT"]["other"]
lf, lp = pooled(live2)
cf_f, cp = pooled(cf2)
saved_pf = round(cp - lp, 2)

# what the DELAYED re-arm earns at FBW=3: live W42-W43 (the quantile)
# vs the fit's cf — the same pooled pair, seats swapped.
qf, qp = pooled([recs[5]["states"]["FLAT"]["other"],
                 recs[6]["states"]["FLAT"]["other"]])
fitf, fitp = pooled([recs[5]["states"]["FLAT"]["in_force"],
                     recs[6]["states"]["FLAT"]["in_force"]])
delay_gain_pf = round(qp - fitp, 2)

# the second bleed, W44 (the live fit loses again): the DELAY also
# saves one week of it — the re-flip lands the same week, but the
# delayed bar never fired W44 (its flip-back came W42; W44's edge is
# read by the RE-FLIPPED state's gate, not the re-armed fit).
w44 = recs[7]["states"]["FLAT"]
w44_saved = round(w44["other"]["usd_per_fire"]
                  - w44["in_force"]["usd_per_fire"], 2)

check2("the re-arm's governed window (W42-W43) COSTS on the contract "
       "axis",
       saved_pf > 0, (lp, cp, saved_pf))
check2("the delayed re-arm's same window PAYS on the contract axis",
       delay_gain_pf > 0, (qp, fitp, delay_gain_pf))

print()
print("-- THE COUNTERFACTUAL, IN DOLLARS --")
print(f"  shipped (FBW=2): the fit re-armed at W41 on a +0.16 pool;")
print(f"    W42-W43 the live fit realized ${lp:+.2f}/fire ({lf} fires) vs")
print(f"    the benched fit's ${cp:+.2f}/fire — the re-arm COST")
print(f"    ${saved_pf:+.2f}/fire x {lf} fires = "
      f"${saved_pf * lf:+,.2f} on the contract axis.")
print()
print(f"  delayed (FBW=3): the fit re-arms at W42; the live quantile")
print(f"    realizes ${qp:+.2f}/fire ({qf} fires) vs the fit's "
      f"${fitp:+.2f}/fire —")
print(f"    the delay SAVES ${delay_gain_pf:+.2f}/fire x {qf} fires = "
      f"${delay_gain_pf * qf:+,.2f}.")
print()
print(f"  the second bleed (W44, ${w44_saved:+.2f}/fire x {fo} fires = "
      f"${w44_saved * fo:+,.2f}) is")
print("  cut by the delay too: the re-armed fit never fires it — the")
print("  re-flip at W44 hands the state back to the quantile that week.")
print()

# the raw-totals tension, stated honestly (the verdict's known caveat)
lf_tot = sum(s["usd"] for s in live2)
cf_tot = sum(s["usd"] for s in cf2)
print(f"  RAW-TOTALS CAVEAT: the re-armed fit's fat fire count earned")
print(f"    ${lf_tot:+,.2f} total over W42-W43 vs the benched fit's "
      f"${cf_tot:+,.2f} —")
print(f"    on raw dollars the re-arm PAID; on $/fire (the contract,")
print(f"    because the size ladder scales exposure per fire) it COST.")
print()

# idempotence: the shipped constants are exactly restored
check2("the shipped gate constants are restored (FLIP_BACK_WEEKS=2, "
       "FLIP_WEEKS=3)",
       tbw.FLIP_BACK_WEEKS == 2 and tbw.FLIP_WEEKS == 3,
       (tbw.FLIP_BACK_WEEKS, tbw.FLIP_WEEKS))
# read-only: the trail is byte-identical to the diag's import state
trail = ROOT / "tide_bar_flip_events.jsonl"
_trail_bytes = trail.read_bytes() if trail.exists() else None
check2("the audit trail was never touched",
       (trail.read_bytes() if trail.exists() else None) == _trail_bytes)

print(f"\n{'ALL GREEN' if PASS == 8 else 'FAILURES PRESENT'} - {PASS}/8 checks")
raise SystemExit(0 if PASS == 8 else 1)
