#!/usr/bin/env python3
"""
trainer/sledgehammer.py — tactic-ladder auto-prover for Lean 4 sorry closure.

This variant works on the actual source file (editing it in place after
verification) rather than a temp scaffold, making it suitable for project-local
Lean files with complex import trees.

FIX vs original: we write to a temp file first, verify it compiles, THEN
patch the source. The original wrote directly to disk before compile check,
corrupting the file on timeout/interrupt.

Usage:
    python sledgehammer.py <file.lean> [--project <lake-root>]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snapkitty_gate import require_capability
from worm import sha256, seal

LADDER: list[str] = [
    "rfl",
    "decide",
    "norm_num",
    "ring",
    "simp",
    "omega",
    "linarith",
    "simp [*]; ring",
    "norm_num; ring",
    "ring_nf; norm_num",
    "aesop",
    "tauto",
]

SORRY_RE = re.compile(r"\bsorry\b")


def elan_bin() -> str | None:
    cand = Path.home() / ".elan" / "bin"
    return str(cand) if cand.is_dir() else None


def find_project_root(start: str) -> str:
    d = Path(start).resolve().parent
    while True:
        if (d / "lakefile.toml").exists() or (d / "lakefile.lean").exists():
            return str(d)
        parent = d.parent
        if parent == d:
            return str(Path(start).resolve().parent)
        d = parent


def run_lean(filepath: str, project_root: str) -> tuple[bool, str, int]:
    env = os.environ.copy()
    eb = elan_bin()
    if eb:
        env["PATH"] = eb + os.pathsep + env.get("PATH", "")

    has_lake = (
        (Path(project_root) / "lakefile.toml").exists()
        or (Path(project_root) / "lakefile.lean").exists()
    )
    rel = os.path.relpath(filepath, project_root)
    cmd = ["lake", "env", "lean", rel] if has_lake else ["lean", rel]

    try:
        r = subprocess.run(
            cmd, cwd=project_root, capture_output=True,
            text=True, timeout=900, env=env,
        )
    except FileNotFoundError:
        r = subprocess.run(
            ["lean", rel], cwd=project_root, capture_output=True,
            text=True, timeout=900, env=env,
        )
    return r.returncode == 0, (r.stdout or "") + (r.stderr or ""), r.returncode


def try_tactic_safe(text: str, sorry_span: tuple[int, int], tactic: str,
                    project_root: str) -> tuple[bool, str]:
    """
    Build a patched version in memory, write to a temp file, verify it compiles.
    Returns (ok, patched_text). Never writes to the original file.
    """
    s, e = sorry_span
    candidate = text[:s] + tactic + text[e:]

    # Write candidate to temp file in project dir so imports resolve
    with tempfile.NamedTemporaryFile(
        suffix=".lean", mode="w", encoding="utf-8", delete=False,
        dir=project_root,
    ) as f:
        f.write(candidate)
        tmp = f.name

    try:
        ok, _, _ = run_lean(tmp, project_root)
        return ok, candidate
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--project", default=None)
    args = ap.parse_args()

    filepath = Path(args.file).resolve()
    if not filepath.exists():
        print(f"ERROR: {filepath} not found", file=sys.stderr)
        sys.exit(2)

    project_root = args.project or find_project_root(str(filepath))
    receipts_path = Path(__file__).parent / "sledgehammer_receipts.jsonl"

    text = filepath.read_text(encoding="utf-8")
    sorry_spans = [(m.start(), m.end()) for m in SORRY_RE.finditer(text)]

    print(
        f"[sledgehammer] {filepath.relative_to(project_root)}: "
        f"{len(sorry_spans)} sorry(s)  ladder={LADDER}"
    )

    closed: list[tuple[int, str]] = []
    hard: list[int] = []

    # Process last-to-first so earlier byte offsets remain valid as we patch
    for i in range(len(sorry_spans) - 1, -1, -1):
        span = sorry_spans[i]
        line_no = text[: span[0]].count("\n") + 1
        won = None
        current_text = text

        for tac in LADDER:
            ok, patched = try_tactic_safe(current_text, span, tac, project_root)
            if ok:
                text = patched
                # recalc spans for earlier sorries since we changed text length
                sorry_spans = [(m.start(), m.end()) for m in SORRY_RE.finditer(text)]
                won = tac
                break

        if won:
            rec = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "file": str(filepath.relative_to(project_root)),
                "line": line_no,
                "tactic": won,
                "status": "CLOSED",
                "sha256": sha256(text),
            }
            seal(str(receipts_path), rec)
            closed.append((line_no, won))
            print(f"  [CLOSED] line {line_no}: `{won}`")
        else:
            hard.append(line_no)
            print(f"  [HARD]   line {line_no}: no ladder tactic closed it")

    # Only write to disk after all tactics are decided
    filepath.write_text(text, encoding="utf-8")

    print(f"\n[sledgehammer] summary:")
    print(f"  closed  : {len(closed)}  -> {closed}")
    print(f"  hard    : {len(hard)}    -> lines {hard}")
    print(f"  receipts: {receipts_path}")
    sys.exit(0)


if __name__ == "__main__":
    require_capability("trainer/sledgehammer")
    main()
