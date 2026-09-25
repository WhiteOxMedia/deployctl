from pathlib import Path

p = Path("test_apptest.py")
src = p.read_text(encoding="utf-8")
anchor = '''        check("the live aftermath pends honestly on a missing ledger too",
              "live aftermath: pending \u2014 no post-decision weeks graded yet"
              in _aud_m and "CURRENTLY BENCHED: OUT" in _aud_m, _aud_m[-400:])
        _tbw_mod.HISTORY_FILE = _h_sbx
        # \u2500\u2500 the SIM worked example on the trail (Sep 11): the diag's
'''
assert src.count(anchor) == 1, f"anchor x{src.count(anchor)}"
block = '''        check("the live aftermath pends honestly on a missing ledger too",
              "live aftermath: pending \u2014 no post-decision weeks graded yet"
              in _aud_m and "CURRENTLY BENCHED: OUT" in _aud_m, _aud_m[-400:])
        _tbw_mod.HISTORY_FILE = _h_sbx
        # \u2500\u2500 THE FBW=3 CLAUSE (Sep 12): a real flip-back whose aftermath
        #    grades COSTING earns its own question on the row \u2014 would
        #    ONE more re-arm week (FBW=3) have saved it? One fixture
        #    exercises the REAL helper end to end (a never-arms deny,
        #    arc 3's shape); the other statuses' row wording is pinned
        #    with the helper stubbed (its math lives in the weekly
        #    suite). Flip rows, PAYING flip-backs and sims never get a
        #    clause. \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        _ev_sbx_fb = BASE / "_sbx_flip_events_fb3.jsonl"
        _h_sbx_fb = BASE / "_sbx_audit_history_fb3.jsonl"
        _ev_sbx_fb.write_text(
            "\\n".join([
                json.dumps({"action": "flip", "state": "OUT",
                            "week": "2026-W39", "ts": "t",
                            "losing_weeks": 3, "roll_delta": -1.28,
                            "evidence": [
                                {"week": "2026-W37", "fit_edge": -0.82},
                                {"week": "2026-W38", "fit_edge": -1.52},
                                {"week": "2026-W39", "fit_edge": -1.52}]}),
                json.dumps({"action": "flip_back", "state": "OUT",
                            "week": "2026-W40", "ts": "t",
                            "winning_weeks": 2, "roll_delta": 0.21,
                            "evidence": [
                                {"week": "2026-W39", "fit_edge": 0.5},
                                {"week": "2026-W40", "fit_edge": 0.6}]})])
            + "\\n", encoding="utf-8")
        # W37/W40 the flipped regime (the quantile in force), W41 the
        # re-armed fit bleeding $1.00 vs the quantile's $3.00 \u2014 the
        # re-arm COSTS and its edge never wins again: never-arms
        _h_sbx_fb.write_text("\\n".join([
            json.dumps({"week": "2026-W37", "generated_ts": "t",
                        "states": {"OUT": {
                            "in_force": {"fires": 10, "payers": 3,
                                         "rate": 0.3, "usd": 20.0,
                                         "usd_per_fire": 2.0},
                            "other": {"fires": 10, "payers": 3,
                                      "rate": 0.3, "usd": 10.0,
                                      "usd_per_fire": 1.0},
                            "other_src": "outcome-fitted"}}}),
            json.dumps({"week": "2026-W40", "generated_ts": "t",
                        "states": {"OUT": {
                            "in_force": {"fires": 10, "payers": 3,
                                         "rate": 0.3, "usd": 30.0,
                                         "usd_per_fire": 3.0},
                            "other": {"fires": 10, "payers": 3,
                                      "rate": 0.3, "usd": 10.0,
                                      "usd_per_fire": 1.0},
                            "other_src": "outcome-fitted"}}}),
            json.dumps({"week": "2026-W41", "generated_ts": "t",
                        "states": {"OUT": {
                            "in_force": {"fires": 10, "payers": 3,
                                         "rate": 0.3, "usd": 10.0,
                                         "usd_per_fire": 1.0},
                            "other": {"fires": 10, "payers": 3,
                                      "rate": 0.3, "usd": 30.0,
                                      "usd_per_fire": 3.0},
                            "other_src": "quantile"}}}),
        ]) + "\\n", encoding="utf-8")
        _real_evs_fb, _real_hist_fb = (_tbw_mod.FLIP_EVENTS_FILE,
                                       _tbw_mod.HISTORY_FILE)
        _tbw_mod.FLIP_EVENTS_FILE = _ev_sbx_fb
        _tbw_mod.HISTORY_FILE = _h_sbx_fb
        try:
            _aud_fb = app_mod._render_flip_audit()
            check("a COSTING flip-back grades the aftermath and names it "
                  "on the row (the re-arm's own dollars)",
                  "aftermath: in the 1 weeks after, the fit realized "
                  "$+1.00/fire (10 fires) vs the quantile's $+3.00/fire"
                  in _aud_fb and "the decision COST" in _aud_fb,
                  _aud_fb[:900])
            check("the fbw3 clause renders the REAL never-arms deny on "
                  "the costing row (no third winning week, the decision's "
                  "own avoided cost: $2.00/fire over 10 fires = $20.00)",
                  "the extra re-arm week (FBW=3) would have denied this "
                  "re-arm entirely (no third winning week) \u2014 saved "
                  "$+20.00 ($+2.00/fire over the 1 weeks after)"
                  in _aud_fb,
                  _aud_fb[_aud_fb.find("FLIP-BACK"):][:1200])
            check("the clause sits between the aftermath and the bench's "
                  "final verdict on the row",
                  _aud_fb.find("aftermath: in the 1 weeks after")
                  < _aud_fb.find("the extra re-arm week (FBW=3)")
                  < _aud_fb.find("the bench's final live verdict")
                  if "the bench's final live verdict" in _aud_fb else True,
                  _aud_fb[:1400])
            check("the flip row (PAYING) never earns a clause",
                  _aud_fb.count("the extra re-arm week (FBW=3)") == 1
                  and _aud_fb.find("the extra re-arm week (FBW=3)")
                  > _aud_fb.find("FLIP-BACK to live duty"),
                  _aud_fb.count("the extra re-arm week (FBW=3)"))
            check("the census counts the graded pair (1 PAYING \u00b7 1 "
                  "COSTING)",
                  "verdicts: 1 PAYING \u00b7 1 COSTING \u00b7 0 pending"
                  in _aud_fb,
                  _aud_fb[-400:])
        finally:
            _tbw_mod.FLIP_EVENTS_FILE = _real_evs_fb
            _tbw_mod.HISTORY_FILE = _real_hist_fb
        _ev_sbx_fb.unlink(missing_ok=True)
        _h_sbx_fb.unlink(missing_ok=True)
        # the other statuses' ROW WORDING, helper stubbed (the real math
        # is pinned in the weekly suite) \u2014 restore in finally, always
        _real_fbw = _tbw_mod.fbw3_counterfactual
        try:
            _tbw_mod.fbw3_counterfactual = (
                lambda *a, **k: {
                    "status": "denied", "arm_week": "2026-W45",
                    "delayed_fires": 20, "delayed_per_fire": 3.50,
                    "saved_per_fire": 1.00, "saved_total": 20.0})
            _aud_d = app_mod._render_flip_audit()
            check("a positive deny names the later arm week and its "
                  "save in dollars",
                  "the extra re-arm week (FBW=3) would have held the "
                  "bench one more week, re-arming at 2026-W45 \u2014 would "
                  "have saved $+20.00 ($+1.00/fire over the delayed "
                  "arm's 20 fires)" in _aud_d, _aud_d[:1400])
            _tbw_mod.fbw3_counterfactual = (
                lambda *a, **k: {
                    "status": "denied", "arm_week": "2026-W45",
                    "delayed_fires": 20, "delayed_per_fire": 0.50,
                    "saved_per_fire": -2.00, "saved_total": -40.0})
            _aud_dn = app_mod._render_flip_audit()
            check("a negative deny says the extra week would have "
                  "cost \u2014 no fake savings",
                  "the extra re-arm week (FBW=3) would have re-armed "
                  "later at 2026-W45 and paid $40.00 LESS \u2014 the extra "
                  "week would have cost here" in _aud_dn, _aud_dn[:1400])
            _tbw_mod.fbw3_counterfactual = (
                lambda *a, **k: {"status": "same-week"})
            _aud_sw = app_mod._render_flip_audit()
            check("a same-week replay credits the pool guard, not the "
                  "week count",
                  "the extra re-arm week (FBW=3) re-arms on the same "
                  "week \u2014 the pool guard, not the week count, held this "
                  "arm; nothing to save" in _aud_sw, _aud_sw[:1400])
            _tbw_mod.fbw3_counterfactual = (
                lambda *a, **k: {"status": "delayed",
                                 "arm_week": "2026-W44"})
            _aud_dl = app_mod._render_flip_audit()
            check("an unpriced delayed arm stays honest",
                  "the extra re-arm week (FBW=3) delays the re-arm to "
                  "2026-W44 \u2014 too few weeks have traded since to price "
                  "it" in _aud_dl, _aud_dl[:1400])
        finally:
            _tbw_mod.fbw3_counterfactual = _real_fbw
        # \u2500\u2500 the SIM worked example on the trail (Sep 11): the diag's
'''
src = src.replace(anchor, block)
p.write_text(src, encoding="utf-8")
print("block inserted")
