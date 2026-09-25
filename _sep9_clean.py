#!/usr/bin/env python3
"""One-shot patch for background_scanner.py — contest-size aware popups.

Reading this file always does git HEAD backup first, then fingerprints the
target to decide which edits still need applying, applies the pending ones,
and runs an ast.parse gate.

Editing this file is safe: every edit is idempotent behind a fingerprint
guard (edit applies at most once).  Re-running is harmless.
"""
import ast
import io
import pathlib
import sys
import uuid

BD = pathlib.Path(__file__).resolve().parent
SRC = BD / "background_scanner.py"

JOURNAL = BD / "_sep9_clean_journal.txt"
JOURNAL.write_text(JOURNAL.read_text(encoding="utf-8") + f"\n[{uuid.uuid4().hex[:8]}] begin: BEGIN FIRE SNAPSHOT ctx edit\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def err(msg: str) -> None:
    print("ERR:", msg, file=sys.stderr)


def dbg(msg: str) -> None:
    print("DBG:", msg)


def must_find(text: str, needle: str, start: int = 0) -> int:
    i = text.find(needle, start)
    if i < 0:
        err(f"missing anchor: {needle!r}")
        err(f"tail snippet: {text[start:start+120]!r}")
        raise SystemExit(1)
    return i


def rx(pattern: str) -> str:
    """Return the regex pattern string verbatim so callers don't forget escaping."""
    return pattern


# ---------------------------------------------------------------------------
# Git backup
# ---------------------------------------------------------------------------
def git_backup() -> None:
    import subprocess
    bak = BD / "_git_backup"
    bak.mkdir(exist_ok=True)
    ts = pathlib.Path("._ts").write_text(str(uuid.uuid4()), encoding="utf-8")
    subprocess.run(
        ["git", "show", "HEAD:background_scanner.py"],
        cwd=str(BD),
        stdout=(bak / "background_scanner.py").open("wb"),
        check=True,
        capture_output=False,
    )
    dbg("git backup written")


# ---------------------------------------------------------------------------
# Fingerprint registry (idempotency guards)
# ---------------------------------------------------------------------------
EDITS = {}


def fingerprint(prefix: str, key: str):
    def dec(fn):
        EDITS[key] = fn
        fn._fingerprint_prefix = prefix
        fn._fingerprint_key = key
        return fn
    return dec


# ---------------------------------------------------------------------------
# Edit 6: BEGIN FIRE SNAPSHOT ctx (add contest_size)
# ---------------------------------------------------------------------------
@fingerprint("begin_fire_snapshot_ctx", "begin_fire_snapshot_ctx")
def edit_begin_fire_snapshot_ctx(t: str) -> str:
    """Add contest_size to the fire-time ctx snapshot so suppression and the
    popup_CAP dollars helper both see the same per-fire stamp."""
    old_ctx = '    ctx = {"pair": pair, "quick": quick_conf}\n'
    new_ctx = '    ctx = {"pair": pair, "quick": quick_conf, "contest_size": _contest_size()}\n'
    if old_ctx not in t:
        err("old begin_fire_snapshot ctx line not found (maybe already edited?)")
        err(f"snippet: {t[must_find(t, 'def _begin_fire_snapshot'):][:200]!r}")
        raise SystemExit(1)
    if new_ctx in t:
        dbg("begin_fire_snapshot ctx: already contains contest_size")
        return t
    return t.replace(old_ctx, new_ctx, 1)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def apply_edits(t: str) -> str:
    applied = []
    skipped = []
    for key, fn in EDITS.items():
        if key not in fingerprint_state():
            try:
                t2 = fn(t)
            except SystemExit:
                skipped.append(key)
                continue
            if t2 is t:
                skipped.append(key)
                continue
            t = t2
            applied.append(key)
            JOURNAL.write_text(
                JOURNAL.read_text(encoding="utf-8")
                + f"[{uuid.uuid4().hex[:8]}] APPLIED edit {key}\n",
                encoding="utf-8",
            )
        else:
            skipped.append(key)
    return t, applied, skipped


def fingerprint_state() -> set:
    state_path = BD / "_sep9_edit_state.txt"
    if not state_path.exists():
        return set()
    text = state_path.read_text(encoding="utf-8")
    return set(line.strip() for line in text.splitlines() if line.strip())


def record_state(applied: list) -> None:
    state_path = BD / "_sep9_edit_state.txt"
    current = fingerprint_state()
    current |= set(applied)
    state_path.write_text("\n".join(sorted(current)) + "\n", encoding="utf-8")


def main() -> None:
    git_backup()

    t = SRC.read_text(encoding="utf-8")
    t, applied, skipped = apply_edits(t)

    SRC.write_text(t, encoding="utf-8")

    ast.parse(t)
    print("SYNTAX OK")
    print(f"applied: {applied}")
    print(f"skipped: {skipped}")

    for needle in sorted(set(fn._fingerprint_key for fn in EDITS.values())):
        print(f"  {needle:45} present={needle in t}")

    JOURNAL.write_text(
        JOURNAL.read_text(encoding="utf-8") + f"[{uuid.uuid4().hex[:8]}] end: DONE\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
