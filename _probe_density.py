"""_probe_density.py — forward density probe for the widening's six coins.

Replays ARB/UNI/FIL/WLD/ZEC/PUMP through diag_chaseback's own tracker
state machine (arm on a top-15 mover-list hour, 8h life, rising-EMA9
cross = turn, 4% rollover guard) with the REAL fleet ranking, then:
  - counts turn setups per coin over trailing 7/14/28 days,
  - reports each coin's LIVE tracker state at the last bar
    (armed = a tracked reject is alive and waiting for its cross),
  - reports how many of the trailing-7d setups would pass the +1%
    speak floor the unified policy proposed.
Probe only — deleted after the answer.
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import diag_chaseback as dcb
from config import DEFAULT_CONFIG as cfg
from indicators import ema as _ema

SIX = ["ARB", "UNI", "FIL", "WLD", "ZEC", "PUMP"]
BASE = Path(__file__).parent

# --- fleet stores, exactly run_study's selection ---
glob_pattern = str(BASE / dcb.STORES_GLOB)
all_paths = sorted(glob.glob(glob_pattern))
wanted = {str(p).replace("/", "_") for p in (cfg.trading_pairs or [])}
paths = [p for p in all_paths
         if Path(p).name.replace("-1h.feather", "") in wanted]

closes_by_pair = {}
for path in paths:
    pair = Path(path).name.replace("-1h.feather", "")
    try:
        closes_by_pair[pair] = dcb._load_store(path)
    except Exception:
        pass

on_list, pct_by_pair = dcb._fleet_movers_on_list(closes_by_pair, dcb.WARMUP)


def density_walk(closes, highs, idx, on_hours, warmup=dcb.WARMUP):
    """diag_chaseback._detect_setups' exact state machine, minus the
    forward grade (counting only). Returns (setups, live_tracked)."""
    n = len(closes)
    ema_s = _ema(pd.Series(closes, dtype=float), 9).to_numpy()
    ep = dcb._epoch_s(idx)
    ep_h = ep // 3600
    setups = []
    tracked = None
    for i in range(warmup, n):
        ts_s = int(ep[i])
        if tracked and (ts_s - tracked["first"]) > dcb.CHASE_MAX_AGE_H * 3600.0:
            tracked = None
        if int(ep_h[i]) in on_hours:
            if tracked is None:
                tracked = {"first": ts_s, "ref": float(closes[i])}
            else:
                tracked["ref"] = float(closes[i])
        em, em_p, em_5 = ema_s[i], ema_s[i - 1], ema_s[i - 5]
        if not (em == em and em_p == em_p and em_5 == em_5):
            continue
        rising = em > em_5
        cross = closes[i] > em and closes[i - 1] <= em_p
        if not (rising and cross):
            continue
        px = float(closes[i])
        if tracked is not None:
            drop = (tracked["ref"] - px) / tracked["ref"] * 100.0
            caught = True
        else:
            ref8 = float(np.max(closes[max(0, i - dcb.PULLBACK_LOOKBACK):i])) \
                if i >= 1 else px
            drop = (ref8 - px) / ref8 * 100.0 if ref8 > 0 else 0.0
            caught = False
        if drop > dcb.CHASE_TURN_MAX_DROP_PCT:
            continue
        pct = pct_by_pair[pair][1][i]
        setups.append({"ts": ts_s, "caught": caught,
                       "pct24": float(pct) if pct == pct else None})
        if tracked is not None:
            tracked["said"] = ts_s        # the sim's refresh (first stays)
    return setups, tracked


week = 7 * 86400.0
now_ts = max(int(dcb._epoch_s(closes_by_pair[p][2])[-1]) for p in SIX)

rows = []
for base in SIX:
    pair = base + "_USD"
    if pair not in closes_by_pair:
        rows.append((base, None, None, None, None, None, "NO STORE"))
        continue
    closes, highs, idx = closes_by_pair[pair]
    pair_rows = pct_by_pair.get(pair, ([], None))
    setups, live = density_walk(closes, highs, idx,
                                on_list.get(pair, {}))
    caught = [s for s in setups if s["caught"]]
    last7 = [s for s in caught if now_ts - s["ts"] < week]
    last14 = [s for s in caught if now_ts - s["ts"] < 2 * week]
    last28 = [s for s in caught if now_ts - s["ts"] < 4 * week]
    days_since = (now_ts - caught[-1]["ts"]) / 86400.0 if caught else None
    floor7 = sum(1 for s in last7
                 if s["pct24"] is not None and s["pct24"] >= 1.0)
    # the last on-list hour: how recently the coin was a rejected mover
    on_hours = sorted(on_list.get(pair, {}).keys())
    last_on_h = (now_ts - on_hours[-1] * 3600) / 3600.0 if on_hours else None
    armed = live is not None
    rows.append((base, len(caught), len(last7), len(last14), len(last28),
                 days_since, floor7, armed, last_on_h, len(setups)))

hdr = (f"{'coin':5} {'all-caught':>10} {'7d':>4} {'14d':>4} {'28d':>4} "
       f"{'d-since':>8} {'7d>=+1%':>8} {'ARMED':>6} {'last-on-list-h':>15}")
print(hdr)
for r in rows:
    base, allc, l7, l14, l28, ds, f7, armed, loh, _tot = r
    if allc is None:
        print(f"{base:5}  {r[-1]}")
        continue
    print(f"{base:5} {allc:>10} {l7:>4} {l14:>4} {l28:>4} "
          f"{(f'{ds:.1f}d' if ds is not None else '-'):>8} {f7:>8} "
          f"{('YES' if armed else '-'):>6} "
          f"{(f'{loh:.1f}h' if loh is not None else '-'):>15}")

tot7 = sum(r[2] or 0 for r in rows if r[1] is not None)
tot28 = sum(r[4] or 0 for r in rows if r[1] is not None)
armed_n = sum(1 for r in rows if len(r) > 7 and r[7])
print(f"\nfleet-wide: 7d caught setups across the six = {tot7}; "
      f"28d = {tot28} ({tot28/4.0:.1f}/wk avg); armed right now = {armed_n}/6")
