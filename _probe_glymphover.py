"""Probe: the FLAT trend line's flip-back glyph, from a sandbox sidecar.
Run: .venv\\Scripts\\python.exe -X utf8 _probe_glymphover.py"""
import json
from pathlib import Path
import app

fake = {
    "generated_ts": "t", "flips": {},
    "trend": {"OUT": [0.5, -0.8, None, -0.91],
              "FLAT": [1.2, 1.6, 2.5, 3.16], "RISING": []},
    "flip_marks": {"OUT": [None, None, "flip@2026-W36", None],
                   "FLAT": [None, "flip_back@2026-W35", None, None],
                   "RISING": []},
    "states": {
        "OUT": {"n": 1, "in_force": {"bar": 80.0, "fires": 1, "payers": 1,
                                     "rate": 0.5, "usd": 1.0,
                                     "usd_per_fire": 1.0},
                "other": {"bar": 86.0, "fires": 1, "payers": 1,
                          "rate": 0.5, "usd": 1.0, "usd_per_fire": 1.0},
                "other_src": "quantile"},
        "FLAT": {"n": 1, "in_force": {"bar": 89.0, "fires": 1, "payers": 1,
                                      "rate": 0.5, "usd": 1.0,
                                      "usd_per_fire": 1.0},
                 "other": {"bar": 80.0, "fires": 1, "payers": 1,
                           "rate": 0.5, "usd": 1.0, "usd_per_fire": 1.0},
                 "other_src": "outcome-fitted"},
        "RISING": None},
    "fills": "no fired-popup records"}
p = Path("_sbx_probe.json")
p.write_text(json.dumps(fake), encoding="utf-8")
try:
    h = app._tidebar_verdict(jf_path=p)
    i = h.find("trend")
    seg = h[i:i + 700]
    print(seg)
finally:
    p.unlink()
