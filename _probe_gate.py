import tidebar_weekly as tbw

_flip = {"state": "FLAT", "action": "flip", "week": "2026-W39",
         "roll_delta": -0.5, "evidence": []}
_ev = {"state": "FLAT", "action": "flip_back", "week": "2026-W41",
       "roll_delta": 0.3, "winning_weeks": 2,
       "evidence": [{"week": "2026-W40", "fit_edge": 0.2},
                    {"week": "2026-W41", "fit_edge": 0.4}]}


def wpmk(tag, fi, fo, src):
    return {"week": tag, "generated_ts": tag, "states": {"FLAT": {
        "in_force": {"fires": 10, "payers": 3, "rate": 0.3,
                     "usd": 10 * fi, "usd_per_fire": fi},
        "other": {"fires": 10, "payers": 3, "rate": 0.3,
                  "usd": 10 * fo, "usd_per_fire": fo},
        "other_src": src}}}


recs = [wpmk("2026-W40", 2.0, 2.2, "outcome-fitted"),
        wpmk("2026-W41", 2.4, 2.0, "quantile"),
        wpmk("2026-W42", 1.0, 3.0, "quantile"),
        wpmk("2026-W43", 1.0, 3.0, "quantile")]
recs += [wpmk(f"2026-W{w}", 2.4, 2.0, "quantile") for w in (45, 46, 47, 48)]
evs = [_flip, _ev]
for k in range(1, len(recs) + 1):
    rp = tbw.recommend_pool_min(recs[:k], evs)
    print(f"k={k} wk={recs[k-1]['week']} rec={rp['recommendation']} "
          f"stable={rp['stable']} staged={rp['staged']} "
          f"priced={rp['n_priced']}")
rf = tbw.recommend_fbw(recs, [_flip, _ev], min_events=1)
print("fbw full rec:", rf["recommendation"], "stable:", rf["stable"])
