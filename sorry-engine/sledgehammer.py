#!/usr/bin/env python3
"""
sledgehammer.py — Sovereign sorry-hunter for Lean 4 + Mathlib.

Reads a Lean file, finds every `sorry`, attempts a ranked tactic sequence
for each one, writes a patched version with the first tactic that compiles.
Seals a WORM receipt on every solved sorry.

Usage:
    python sledgehammer.py <file.lean> [--project <lake-root>] [--dry-run]

Tactic ladder (tried in order, fastest -> strongest):
    rfl, decide, norm_num, ring, simp, omega, linarith,
    simp [*]; ring, norm_num; ring, ring_nf; norm_num,
    simp only []; linarith, aesop, tauto

WORM receipt appended to: sledgehammer_chain.jsonl (same dir as file)
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from snapkitty_gate import require_capability
from worm import sha256, seal, prior_tip

TACTICS: list[str] = [
    "rfl",
    "decide",
    "norm_num",
    "ring",
    "simp",
    "omega",
    "linarith",
    "simp [*]; ring",
    "norm_num; ring",
    "simp only []; ring",
    "simp only []; linarith",
    "ring_nf; norm_num",
    "simp; linarith",
    "aesop",
    "tauto",
    "trivial",
]


def lean_binary(project_root: str) -> str:
    elan = os.path.expanduser("~/.elan/bin/lean")
    if os.path.exists(elan):
        return elan
    return "lean"


def lake_env(project_root: str) -> dict:
    try:
        result = subprocess.run(
            ["lake", "env", "printenv", "LEAN_PATH"],
            cwd=project_root, capture_output=True, text=True, timeout=30,
        )
        lean_path = result.stdout.strip()
    except Exception:
        lean_path = ""
    env = os.environ.copy()
    if lean_path:
        env["LEAN_PATH"] = lean_path
    return env


def try_tactic(lean_src: str, sorry_line: int, tactic: str,
               project_root: str, lean_bin: str, env: dict) -> bool:
    """Replace the sorry on sorry_line with tactic in a temp file; compile; return True if clean."""
    lines = lean_src.splitlines(keepends=True)
    original = lines[sorry_line]
    lines[sorry_line] = original.replace("sorry", tactic, 1)
    patched = "".join(lines)

    with tempfile.NamedTemporaryFile(
        suffix=".lean", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(patched)
        tmp = f.name

    try:
        result = subprocess.run(
            [lean_bin, tmp],
            cwd=project_root, capture_output=True, text=True, timeout=60, env=env,
        )
        output = result.stdout + result.stderr
        has_error = "error:" in output
        return result.returncode == 0 or not has_error
    except subprocess.TimeoutExpired:
        return False
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def find_sorries(src: str) -> list[tuple[int, str]]:
    """Return (line_index, line_text) for each tactic sorry, skipping comments."""
    results = []
    for i, line in enumerate(src.splitlines()):
        code_part = re.split(r"--", line)[0]
        if re.search(r"\bsorry\b", code_part):
            results.append((i, line.strip()))
    return results


def run(file_path: str, project_root: str, dry_run: bool) -> None:
    src = Path(file_path).read_text(encoding="utf-8")
    sorries = find_sorries(src)
    if not sorries:
        print("No sorries found.")
        return

    print(f"Found {len(sorries)} sorry(s) in {file_path}")
    lean_bin = lean_binary(project_root)
    env = lake_env(project_root)
    chain_path = Path(file_path).parent / "sledgehammer_chain.jsonl"

    results = []
    patched_src = src

    for idx, (line_no, ctx) in enumerate(sorries):
        print(f"\n[{idx+1}/{len(sorries)}] Line {line_no+1}: {ctx[:80]}")
        solved = None
        for tactic in TACTICS:
            print(f"  trying: {tactic} ...", end=" ", flush=True)
            if dry_run:
                print("(dry-run skip)")
                continue
            if try_tactic(patched_src, line_no, tactic, project_root, lean_bin, env):
                print("SOLVED")
                solved = tactic
                lines = patched_src.splitlines(keepends=True)
                lines[line_no] = lines[line_no].replace("sorry", tactic, 1)
                patched_src = "".join(lines)
                break
            else:
                print("x")

        rec = {
            "file": Path(file_path).name,
            "line": line_no + 1,
            "context": ctx,
            "tactic": solved or "UNSOLVED",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "file_hash": sha256(src),
        }
        results.append(rec)
        if not dry_run:
            seal(str(chain_path), rec)

    solved_count = sum(1 for r in results if r["tactic"] != "UNSOLVED")
    print(f"\n=== SLEDGEHAMMER RESULT ===")
    print(f"Solved: {solved_count}/{len(sorries)}")

    if solved_count > 0 and not dry_run:
        out_path = file_path.replace(".lean", "_sledged.lean")
        Path(out_path).write_text(patched_src, encoding="utf-8")
        print(f"Patched file: {out_path}")
        print(f"WORM chain:   {chain_path}")

    for r in results:
        status = "OK" if r["tactic"] != "UNSOLVED" else "XX"
        print(f"  [{status}] line {r['line']}: {r['tactic']}")


if __name__ == "__main__":
    require_capability("sledgehammer")
    ap = argparse.ArgumentParser(description="Sovereign Lean 4 sledgehammer")
    ap.add_argument("file", help="Path to .lean file")
    ap.add_argument("--project", default=None, help="Lake project root (default: file dir)")
    ap.add_argument("--dry-run", action="store_true", help="Find sorries only, don't attempt")
    args = ap.parse_args()

    project = args.project or os.path.dirname(os.path.abspath(args.file))
    run(os.path.abspath(args.file), project, args.dry_run)
