"""_cb_inject.py — one-shot sentinel injector for diag_clockbombs census 4.

Re-finds sites with the diag's own engine (import _runtime_scan), inserts
the triaged sentinel line above each, preserves line endings/indentation,
deletes itself.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import diag_clockbombs as dc  # noqa: E402

ROOT = Path(__file__).parent

LP = "LIVE-PROBE (manual bot-day report — reports on the live system by design)"
SENTINELS = {
    ("test_allgoodlead.py", 23):
        "LIVE-PROBE (backup/seed/restore — determinism comes from the seed, not the book)",
    ("test_allgoodlead.py", 47):
        "SANDBOXED (backup/restore byte-for-byte in the try/finally below)",
    ("test_allgoodlead.py", 103):
        "SANDBOXED (backup/restore byte-for-byte in the try/finally below)",
    ("test_bot_day.py", 12): LP,
    ("test_cooldownreview.py", 45):
        "LIVE-PROBE (same-ledger cross-aggregation — the drive seeds the row it grades)",
    ("test_cooldownreview.py", 77):
        "LIVE-PROBE (absence grep for today's Buy line — absence is the expected verdict)",
    ("test_cooldownreview.py", 155):
        "LIVE-PROBE (same-ledger cross-aggregation — sold-kind count vs the seeded rows)",
    ("test_dopamine.py", 12): LP,
    ("test_dupcheck.py", 12):
        "SANDBOXED (transaction-rollback drill — BEGIN/ROLLBACK leaves no residue; :41 proves it)",
    ("test_dupcheck.py", 41):
        "LIVE-PROBE (existence/count pin — expects zero residue from the rollback above)",
    ("test_dupfinal.py", 61):
        "SANDBOXED (snapshot read for byte-for-byte restore in the finally)",
    ("test_herwords.py", 73):
        "SANDBOXED (deliberate hand-back to production after the sandbox; leak-audit documented)",
    ("test_hype_now.py", 31):
        "LIVE-PROBE (reads the live watch entry, shape-probed via .get defaults)",
    ("test_liq_cal.py", 9): LP,
    ("test_liq_filter.py", 40): LP,
    ("test_night.py", 17): LP,
    ("test_night.py", 32): LP,
    ("test_no_alerts.py", 21): LP,
    ("test_one_asset.py", 41): LP,
    ("test_pending.py", 6): LP,
    ("test_profitguard.py", 368):
        "LIVE-PROBE (existence-only walk for the real repo root; documented gate-scratch-safe)",
    ("test_ratchet.py", 70): LP,
    ("test_ratchet.py", 73): LP,
    ("test_resetrebaseline.py", 49):
        "LIVE-PROBE (read-only, existence-gated pin — documented non-brittle)",
    ("test_sunday.py", 14): LP,
    ("test_surethingautorefit.py", 231):
        "LIVE-PROBE (read-only verdict-shape assertion on the production ledger)",
    ("test_tidebarweekly.py", 504):
        "SANDBOXED (tbw.SNAP_OUTCOMES_FILE redirected into the sandbox at :492)",
    ("test_tidestamp.py", 162):
        "SANDBOXED (deliberate hand-back to production after the sandbox; leak-audit documented)",
    ("test_tour_state.py", 13): LP,
    ("test_why_rejected.py", 6): LP,
    ("test_worthdial.py", 45):
        "SANDBOXED (backup/seed/restore harness — _acct_bak/_cs_bak restored in the finally)",
    ("test_xrp_signals.py", 38): LP,
    ("test_zec_trace.py", 35): LP,
}


def main() -> None:
    # 1. gather sites fresh, group by file
    by_file = {}
    for py in sorted(ROOT.glob("test_*.py")):
        src = py.read_text(encoding="utf-8", errors="replace")
        sites = []
        for s in dc._runtime_scan(src, py.name):
            ln = int(s.split(":", 1)[1].split(" ", 1)[0])
            sites.append((ln, s))
        if sites:
            by_file[py] = (src, sorted(sites))

    # 2. rewrite bottom-up per file
    n_ins = 0
    for py, (src, sites) in sorted(by_file.items()):
        eol = "\r\n" if "\r\n" in src[:4000] else "\n"
        lines = src.split(eol)
        for ln, s in reversed(sites):
            v = SENTINELS.get((py.name, ln))
            if v is None:
                print(f"!! NO VERDICT: {py.name}:{ln} — {s[:70]}")
                sys.exit(1)
            indent = ""
            for j in range(ln - 1, max(ln - 5, -1), -1):
                m = re.match(r"(\s*)\S", lines[j])
                if m:
                    indent = m.group(1)
                    break
            lines.insert(ln - 1,
                         f"{indent}# clock-audit: ok — {v} (clockbombs census 4)")
            n_ins += 1
        py.write_text(eol.join(lines), encoding="utf-8")
    print(f"inserted {n_ins} sentinels across {len(by_file)} files")


main()
