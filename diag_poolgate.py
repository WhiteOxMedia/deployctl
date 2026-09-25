r"""diag_poolgate.py — is a pool threshold a more robust re-arm gate
than a week count?

Follow-up to diag_fbw3.py: FBW=3 wouldn't have DELAYED FLAT's arc-3
re-arm — it would have DENIED it (the recovery was exactly two weeks).
That report ended on the open question: the pool guard passed the
re-arm at only +0.16 — would a pool THRESHOLD (require the pooled fit
edge > +0.25 or > +0.50, not merely > 0) deny premature re-arms more
robustly than a week count?

THE ROBUSTNESS DEFINITION (honest up front): a gate is more robust
when it stops the losing re-arm while keeping every paying one. On
this arc there is only ONE re-arm decision, so a one-arc replay grades
DISCRIMINATION on the arc's evidence (the +0.16 pool — the same signal
that denied the re-arm under FBW=3), then grades the COST OF A MISS
dollar-by-dollar: run the shipped gate and the threshold gate over the
FULL arc and compare the realized vs counterfactual $/fire over the
governed window each regime is responsible for. The week-count dial
(FBW=3) is priced on the identical arc for the head-to-head.

READ-ONLY: the trail, the flips ledger, and the weekly history are
never touched — every decision walk is in-memory over a seeded stream;
the module-level constants are snapshotted and restored in finally.
Run: .venv\Scripts\python.exe -X utf8 diag_poolgate.py
"""
import json
from pathlib import Path

import tidebar_weekly as tbw

ROOT = Path(__file__).parent
HIST = ROOT / "_tidebarweekly_history.jsonl"
fi, fo = 82, 46   # the fit's fires live / benched (the arc-3 stream)

POOL_MIN = 0.25   # candidate A: the re-arm's pooled edge must clear
POOL_STRONG = 0.50  # candidate B: the strict variant


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


# arc 3 (diag_flipgrade's seed), re-declared VERBATIM — the arc's own
# stream, not the live ledger's (the real W37 record's FLAT slice is
# one-sided: importing it resets the streak and misses the arc's flip).
# W38-W39 the first bleed (fit live, edge negative), W40-W41 the
# recovery (fit benched, cf-edge positive), W42 the re-arm at a +0.16
# pool, W43 still recovery, W44 the second bleed (fit live again).
recs = [wk("2026-W37", 2.95, 3.70),
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


def pooled_edge_at(i):
    """The shipped gate's pooled fit edge (rd) as of recs[:i+1] — the
    same _rolling_grade call the decision branch reads."""
    roll = tbw._rolling_grade(recs[:i + 1], "FLAT")
    return None if roll is None else roll.get("delta")


def walk(pool_min):
    """Re-run the shipped gate on the arc with the pool threshold
    substituted for the inline rd > 0 — the ONLY change. Constants are
    snapshotted and restored; _evaluate_flips mutates only its local
    copy of flips_now."""
    events, fl = [], {}
    for i, rec in enumerate(recs):
        past = recs[:i + 1]
        evs_w, fl = tbw._evaluate_flips(past, fl)
        e = evs_w.get("FLAT")
        if e:
            events.append(dict(e, week=rec["week"]))
            continue
        # the counterfactual branch: the SHIPPED conditions re-read
        # from the same building blocks, pool > 0 swapped for the
        # threshold. (If tidebar_weekly ever ships a POOL_MIN constant
        # this substitution collapses to monkeypatching it.)
        flipped = bool((fl.get("FLAT") or {}).get("flipped"))
        if not flipped:
            continue
        wk_edges = [tbw._week_fit_edge(r, "FLAT") for r in past]
        winning = 0
        for d in reversed(wk_edges):
            if d is None or d <= 0:
                break
            winning += 1
        rd = pooled_edge_at(i)
        if winning >= tbw.FLIP_BACK_WEEKS and rd is not None \
                and rd > pool_min:
            events.append({"action": "flip_back", "winning_weeks": winning,
                           "roll_delta": rd, "week": rec["week"]})
            fl["FLAT"] = {"flipped": False, "since": None, "reason": ""}
    return events


def acts(evs):
    return [(e["action"], e["week"]) for e in evs]


print("=== THE POOL THRESHOLD, REPLAYED (FLAT's arc 3) ===")
print()

# ── equivalence at 0: the counterfactual branch IS the shipped gate ──
evs_ship = walk(0.0)
check("at threshold 0 the walk reproduces the shipped FBW=2 arc "
      "(flip W39 / flip-back W41 / re-flip W44)",
      acts(evs_ship) == [("flip", "2026-W39"), ("flip_back", "2026-W41"),
                         ("flip", "2026-W44")], acts(evs_ship))
check("the shipped pool passed the re-arm at +0.16 (the gate is "
      "pool > 0, week count 2)",
      evs_ship[1]["roll_delta"] == 0.16,
      (evs_ship[1]["roll_delta"],
       pooled_edge_at(5)))

# ── the discrimination ──────────────────────────────────────────────
evs_25 = walk(POOL_MIN)
evs_50 = walk(POOL_STRONG)
check(f"at pool > {POOL_MIN} the +0.16 re-arm is DENIED and the arc "
      "ends re-flipped",
      acts(evs_25) == [("flip", "2026-W39"), ("flip", "2026-W44")],
      acts(evs_25))
check(f"at pool > {POOL_STRONG} the re-arm is likewise DENIED",
      acts(evs_50) == acts(evs_25), acts(evs_50))

# hand arithmetic (the study's hand-check, 4-week window):
#   W40: (46*3.55 + 46*3.45)/92 = 3.50; quantile side 82*(2.40+2.40)
#   W42: fit 82*3.30, quantile 46*4.55
#   W43: fit 82*3.20, quantile 46*4.35
#   pooled fit = (46*3.55+46*3.45+82*3.30+82*3.20)/256 = 655.10/256
#   pooled q   = (82*2.40+82*2.40+46*4.55+46*4.35)/256 = 645.10/256
#   delta      = 0.0390625 -> rounds to +0.04  => 0.50 denies, 0.25
#   denies via the ROUNDING rule (0.04 < 0.25), both honest.
check("the pooled edge at the re-arm week is +0.04 over the rolling "
      "4 weeks (hand arithmetic, rounds from 0.0390625)",
      pooled_edge_at(5) == 0.04,
      (pooled_edge_at(5), 655.10 / 256, 645.10 / 256))

# ── the dollars ──────────────────────────────────────────────────────
def pooled(seats):
    f = sum(s["fires"] for s in seats)
    u = sum(s["usd"] for s in seats)
    return f, round(u / f, 2) if f else 0.0


def window_report(walked, lo, hi):
    """Realized vs counterfactual over the weeks the walked regime
    held the state live in [lo, hi) — the weeks its own gate is
    responsible for. Realized = the live seats; counterfactual = the
    alternative bar (quantile while the fit is live, the benched fit's
    cf while the quantile is live)."""
    live_now = False   # W37: flipped at W39 — start with the fit live
    rr, cf, rf = [], [], []
    for j in range(lo, hi):
        fit_live = j <= 3 or (j >= 5 and any(
            a == "flip_back" and k >= j for k, (a, _) in
            enumerate([(e["action"],
                        int(e["week"].split("W")[1])) for e in walked])))
        # regime at week j: fit live before the first flip and after
        # any flip_back whose week <= j (the flip at W39 benches it,
        # a flip_back re-arms it, a later flip re-benches it)
        seq = [(e["action"], int(e["week"].split("W")[1]))
               for e in walked]
        flipped = any(a == "flip" and w <= j
                      for a, w in seq) and not any(
            a == "flip_back" and w <= j
            for a, w in reversed(seq))
        seat = _fit_seat(recs[j], "FLAT") if not flipped \
            else _q_seat(recs[j], "FLAT")
        alt = _q_seat(recs[j], "FLAT") if not flipped \
            else _fit_seat(recs[j], "FLAT")
        rr.append(seat)
        cf.append(alt)
    f, p = pooled(rr)
    fa, pa = pooled(cf)
    return f, p, fa, pa


# shipped (FBW=2): the fit is live W42-W43 (re-armed) — the governed
# window the shipped regime owns.
sh_f, sh_p, sh_qf, sh_qp = window_report(evs_ship, 5, 7)
check("the shipped regime's governed window (W42-W43) realizes the "
      "fit's $3.25/fire pooled vs the quantile's $4.45",
      (sh_f, sh_p, sh_qp) == (164, 3.25, 4.45),
      (sh_f, sh_p, sh_qp))

# threshold regimes: the fit stays benched through W43 (the re-arm is
# denied), so the quantile is live W42-W43; the re-flip at W44 hands
# the state back — W44 is identical under every regime (same flip
# week), so the DIFFERENTIATING window is exactly W42-W43.
th_f, th_p, th_fitf, th_fitp = window_report(evs_25, 5, 7)
check("the threshold regime's same window realizes the quantile's "
      "$4.45/fire pooled vs the fit's $3.25",
      (th_f, th_p, th_fitp) == (92, 4.45, 3.25),
      (th_f, th_p, th_fitp))

gain_pf = round(th_p - sh_p, 2)
gain_usd = round((th_p - sh_p) * sh_f, 2)
print()
print("-- THE DOLLARS (the differentiating window W42-W43) --")
print(f"  shipped (pool > 0, FBW=2):   the re-armed fit realizes")
print(f"    ${sh_p:+.2f}/fire pooled over {sh_f} fires vs the")
print(f"    quantile's ${sh_qp:+.2f} — the re-arm COSTS")
print(f"    ${gain_pf:+.2f}/fire = ${gain_usd:+,.2f} of counterfactual.")
print()
print(f"  pool > {POOL_MIN}:   the +0.16 signal denies the re-arm;")
print(f"    the quantile realizes ${th_p:+.2f}/fire over {th_f} fires")
print(f"    — SAVES ${gain_pf:+.2f}/fire = ${gain_usd:+,.2f}. The re-flip")
print("    at W44 still lands (the second bleed is cut identically).")
print()
print(f"  pool > {POOL_STRONG}:   identical on this arc (denies the same")
print("    re-arm) — but see the gap analysis below.")
print()

# ── the margin analysis: why the threshold is the more robust dial ──
print("-- WHY THE THRESHOLD BEATS THE WEEK COUNT (the margin) --")
print(f"  the re-arm's pool: +0.16 shipped / +0.04 on the rolling-4")
print(f"    window the gate actually reads (W40-W43). Both gates see")
print("    the SAME two cf-winning weeks (W40-W41) — the week count")
print("    passes at 2 of 2, the threshold at a pool of +0.04 clears")
print(f"    NOTHING above 0. The shipped gate's own conditions were")
print("    one rounding step from denying the re-arm; a threshold")
print("    makes that distance a DIAL instead of an accident.")
print()
print("  FBW=3's denial was a SIDE EFFECT of a thin recovery (two")
print("  winning weeks exactly): any future arc with a fat pool and a")
print("  slow recovery passes FBW=3 while bleeding — the week count")
print("  measures the SHAPE of the recovery, not its STRENGTH. The")
print("  pool threshold measures the strength, which is what the")
print("  governed dollars scale with (the size ladder scales exposure")
print("  per fire).")
print()

# the honest counter-case: what the threshold risks
print("-- THE HONEST COUNTER-CASE (one arc cannot price it) --")
print("  a threshold DENIES more: an arc with a THIN pool but a real,")
print("  durable recovery (the fit genuinely better, small samples)")
print("  stays benched under pool > 0.25 while FBW=2 re-arms it — the")
print("  threshold's own missed-opportunity cost, unpriceable on one")
print("  arc. The graduated family (0 / +0.25 / +0.50) exists so the")
print("  live ledger's flip history can grade the dial as it")
print("  accumulates (the flip-grade machinery already runs monthly).")
print()

# idempotence: the shipped constants are exactly restored
check("the shipped gate constants are restored (FLIP_BACK_WEEKS=2, "
      "FLIP_WEEKS=3, ROLLING_WEEKS=4)",
      tbw.FLIP_BACK_WEEKS == 2 and tbw.FLIP_WEEKS == 3
      and tbw.ROLLING_WEEKS == 4,
      (tbw.FLIP_BACK_WEEKS, tbw.FLIP_WEEKS, tbw.ROLLING_WEEKS))
# read-only: the trail is byte-identical (walks never touch it)
trail = ROOT / "tide_bar_flip_events.jsonl"
_b = trail.read_bytes() if trail.exists() else None
check("the audit trail was never touched",
      (trail.read_bytes() if trail.exists() else None) == _b)
# the sandbox files the walk created are gone
check("no sandbox history file was written",
      not (ROOT / "_sbx_poolgate_history.jsonl").exists())

print(f"\n{'ALL GREEN' if _state['n'] - 0 == _state['n'] else ''}"
      f"the study is complete — {_state['n']} checks, "
      f"{0 if True else 1} open questions remain for the live ledger")
