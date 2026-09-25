"""run_battery.py — THE ONE-COMMAND BATTERY (Sep 14).

WHY THIS EXISTS: "full verification" was a remembered incantation — the
weekly suite, the AppTest battery, the five structural analyzers, the
pool-gate gate, the bot's three suites, the trail guard — each run by
hand in the right order, and any one forgotten silently narrowed the
net. This is the one command that runs every gate in one pass and
prints a summary table, so a green battery is EVIDENCE, not recollection.

WHAT IT RUNS
  1. THE CORE — the gates that must never be skipped, listed by name:
     the weekly tide-bar suite, the AppTest battery, the six structural
     analyzers (st-shadow, widget-sweep, cache-sweep, prefs-mirror,
     silent-swallow, sizing-audit — each selftested against its planted
     bug inside its own run), and the pool-gate exit gate.
  2. DISCOVERED SUITES — every test_*.py in the scout repo and the bot
     repo that is offline (a strict network-import regex excludes
     live-API tests; they stay ad-hoc on purpose).
  3. DISCOVERED DIAGS — every diag_*.py that FAILS LOUDLY: it joins
     the battery only if it exits nonzero on failure (sys.exit /
     SystemExit in its source). Report-writer diags with no exit code
     are studies, not gates, and are listed as skipped, not run.

GUARDS
  - FLIP-TRAIL HERMETICITY: tide_bar_flip_events.jsonl is hashed before
    and after the whole run; any byte of drift fails the battery — the
    monthly lesson that a test can edit production history, enforced.
  - HEALTH PASS: health_check.py runs at the end (scanner, bot, vol,
    console, 14 ledgers). Informational only — a deliberately stopped
    process shows WARN but never fails a code-verification run.

USAGE
  .venv/Scripts/python.exe -X utf8 run_battery.py            # full
  .venv/Scripts/python.exe -X utf8 run_battery.py --quick    # core only
  .venv/Scripts/python.exe -X utf8 run_battery.py --list     # show entries
  .venv/Scripts/python.exe -X utf8 run_battery.py --only tide surething

Exit code 0 = every entry passed, trail byte-identical. 1 = any failure.
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
BOT_ROOT = ROOT.parent / "kraken_xrp_trading_bot"
BOT_PY = str(BOT_ROOT / ".venv" / "Scripts" / "python.exe")
TRAIL = ROOT / "tide_bar_flip_events.jsonl"

# A suite is "network" only if a module-level import proves it talks to
# a live API. (Comment mentions don't count — the ^ anchors to code.)
NET_RE = re.compile(r"^\s*(?:import|from)\s+(urllib|requests|ccxt|kraken_api|websockets)\b", re.M)
EXIT_RE = re.compile(r"\bsys\.exit\b|\bSystemExit\b")

# The gates that must never be skipped, in run order.
CORE = [
    ("test_tidebarweekly.py", "suite"),
    ("test_apptest.py", "suite"),
    ("diag_stshadow.py", "diag"),
    ("diag_widgetsweep.py", "diag"),
    ("diag_cachesweep.py", "diag"),
    ("diag_prefsmirror.py", "diag"),
    ("diag_silentpass.py", "diag"),
    ("diag_sizingaudit.py", "diag"),
    ("diag_poolgate.py", "diag"),
]


def _net(src: str) -> bool:
    return bool(NET_RE.search(src))


def _file_net(path: Path) -> bool:
    try:
        return _net(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return True  # unreadable -> don't run it


def discover():
    """Every offline suite in both repos + every exit-coded offline diag."""
    suites, diags, skipped = [], [], []
    for path in sorted(ROOT.glob("test_*.py")):
        (suites if not _file_net(path) else skipped).append(("scout", path.name, "suite"))
    if BOT_ROOT.exists():
        for path in sorted(BOT_ROOT.glob("test_*.py")):
            (suites if not _file_net(path) else skipped).append(("bot", path.name, "suite"))
    for path in sorted(ROOT.glob("diag_*.py")):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _net(src):
            skipped.append(("scout", path.name, "diag"))
        elif EXIT_RE.search(src):
            diags.append(("scout", path.name, "diag"))
        else:
            skipped.append(("scout", path.name, "diag"))
    return suites, diags, skipped


def build_entries(quick: bool, only):
    entries = list(CORE)
    if not quick:
        suites, diags, _ = discover()
        seen = {name for _, name, _ in entries}
        entries += [(repo, name, kind) for repo, name, kind in suites + diags if name not in seen]
    if only:
        entries = [e for e in entries if any(tok.lower() in e[1].lower() for tok in only)]
    return entries


def run_one(repo: str, name: str, kind: str):
    root = ROOT if repo == "scout" else BOT_ROOT
    python = PY if repo == "scout" else BOT_PY
    timeout = 600 if kind == "diag" else 300
    t0 = time.time()
    try:
        proc = subprocess.run(
            [python, "-X", "utf8", name],
            cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except subprocess.TimeoutExpired:
        return False, timeout, f"TIMEOUT after {timeout}s", ""
    secs = time.time() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 0
    m = re.findall(r"(\d+)\s*passed[^\d]*(\d+)\s*failed", out)
    if not m:
        m = re.findall(r"(\d+)/(\d+)\b", out)  # the family's own 62/0 form
    detail = f"{m[-1][0]}/{m[-1][1]}" if m else ("clean" if ok else f"exit {proc.returncode}")
    if not ok and detail == "clean":
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        detail = (lines[-1] if lines else f"exit {proc.returncode}")[:80]
    return ok, secs, detail, out


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "(absent)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Run every battery gate in one pass.")
    ap.add_argument("--quick", action="store_true", help="core gates only")
    ap.add_argument("--only", nargs="*", help="run entries whose name contains these substrings")
    ap.add_argument("--list", action="store_true", help="show the entry plan and exit")
    args = ap.parse_args()

    entries = build_entries(args.quick, args.only)
    if args.list:
        for repo, name, kind in entries:
            print(f"  {repo:5s} {kind:5s} {name}")
        print(f"{len(entries)} entries")
        return 0

    trail_before = _sha(TRAIL)
    print(f"BATTERY — {len(entries)} entries (trail {trail_before[:12]})")
    results, failures = [], []
    for i, (repo, name, kind) in enumerate(entries, 1):
        print(f"  [{i:>3}/{len(entries)}] {repo}/{name} ... ", flush=True)
        ok, secs, detail, out = run_one(repo, name, kind)
        print(f"        {'PASS' if ok else 'FAIL'}  {secs:6.1f}s  {detail}", flush=True)
        results.append((repo, name, kind, ok, secs, detail))
        if not ok:
            failures.append((name, out))

    if not args.quick:
        _, _, skipped = discover()
    else:
        skipped = []

    trail_after = _sha(TRAIL)
    trail_ok = trail_before == trail_after

    w = max(len(n) for _, n, _, _, _, _ in results) + 1
    print("\n" + "=" * 74)
    print(f"{'ENTRY':<{w}} {'KIND':<6}{'RESULT':<8}{'SECS':>7}  DETAIL")
    print("-" * 74)
    for repo, name, kind, ok, secs, detail in results:
        print(f"{(repo + '/' + name):<{w}} {kind:<6}{'PASS' if ok else 'FAIL':<8}{secs:>6.1f}s  {detail}")
    print("-" * 74)
    npass = sum(1 for r in results if r[3])
    print(f"{npass}/{len(results)} entries passed"
          + ("" if not skipped else f"   (skipped as non-gates/live: {len(skipped)})"))

    if failures:
        print("\n-- FAILURE OUTPUT (last 20 lines each) --")
        for name, out in failures:
            print(f"\n### {name}")
            for ln in out.splitlines()[-20:]:
                print("  " + ln)

    print(f"\nFLIP-TRAIL HERMETICITY: "
          + (f"OK — byte-identical {trail_after[:12]}" if trail_ok
             else f"DRIFTED {trail_before[:12]} -> {trail_after[:12]}"))

    if not args.only:  # informational health pass (never fails the battery)
        try:
            h = subprocess.run([PY, "-X", "utf8", "health_check.py"],
                               cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=120)
            tail = [ln for ln in (h.stdout or "").splitlines() if ln.strip()][-6:]
            print("FLEET HEALTH (informational):")
            for ln in tail:
                print("  " + ln)
        except Exception as exc:
            print(f"FLEET HEALTH: unavailable ({exc})")

    verdict = npass == len(results) and trail_ok
    print(f"\nBATTERY {'GREEN' if verdict else 'RED'} — "
          + ("all gates hold, history untouched" if verdict
             else "fix the failures above before shipping"))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
