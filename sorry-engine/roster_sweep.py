#!/usr/bin/env python3
"""
roster_sweep.py — Sovereign sorry-roster sweep.

For each target in a sorry roster JSON:
  1. Fetch the file from GitHub via gh CLI (with retry)
  2. Find sorry lines
  3. Wrap each sorry in a Mathlib scaffold and try the tactic ladder
  4. Report SOLVED / PARTIAL / UNSOLVED / FETCH_FAIL / NO_SORRY
  5. WORM-seal every result to sweep_chain.jsonl

Concurrent by default (--workers N, default 4). Each worker processes
one target at a time; Lean invocations are still sequential per target
to avoid thrashing the same lakefile.

Usage:
    python roster_sweep.py --roster rosters/sorry_roster.json
    python roster_sweep.py --roster rosters/sorry_roster.json --limit 50
    python roster_sweep.py --roster rosters/sorry_roster.json --family algebra --workers 8
    python roster_sweep.py --roster rosters/sorry_roster.json --dry-run

Output:
    sweep_output/sweep_results.json   — full results
    sweep_output/sweep_chain.jsonl    — WORM-sealed receipt chain
    sweep_output/solved/              — patched .lean files for solved sorries
"""
from __future__ import annotations

import argparse
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from snapkitty_gate import require_capability
from worm import seal

MATHLIB5_ROOT = Path(__file__).parent
LEAN_BIN = str(Path.home() / ".elan/bin/lean")
LAKE_BIN = str(Path.home() / ".elan/bin/lake")
TACTIC_TIMEOUT = 60
FETCH_TIMEOUT = 20
FETCH_RETRIES = 3

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
    "exact?",
    "apply?",
]

SCAFFOLD = """\
import Mathlib.Tactic
import Mathlib.Data.Real.Basic
import Mathlib.Algebra.Ring.Basic

-- Sovereign sledgehammer scaffold
-- Original file: {repo}/{path}
-- Line: {line}

-- Context block:
{context}
"""

_chain_lock = Lock()


def fetch_file(repo: str, path: str) -> str | None:
    for attempt in range(FETCH_RETRIES):
        try:
            r = subprocess.run(
                ["gh", "api", f"repos/{repo}/contents/{path}", "--jq", ".content"],
                capture_output=True, text=False, timeout=FETCH_TIMEOUT,
            )
            stdout = (r.stdout or b"").decode("utf-8", errors="replace")
            if r.returncode != 0 or not stdout.strip():
                if attempt < FETCH_RETRIES - 1:
                    time.sleep(1.5 ** attempt)
                    continue
                return None
            b64 = stdout.strip().replace("\n", "")
            return base64.b64decode(b64).decode("utf-8", errors="replace")
        except Exception:
            if attempt < FETCH_RETRIES - 1:
                time.sleep(1.5 ** attempt)
    return None


def find_sorries(src: str) -> list[tuple[int, str]]:
    results = []
    for i, line in enumerate(src.splitlines()):
        code = re.split(r"--", line)[0]
        if re.search(r"\bsorry\b", code):
            results.append((i, line.rstrip()))
    return results


def get_context(src: str, line_idx: int, window: int = 15) -> str:
    lines = src.splitlines()
    lo = max(0, line_idx - window)
    hi = min(len(lines), line_idx + window + 1)
    return "\n".join(lines[lo:hi])


def try_tactic_scaffold(context: str, tactic: str, repo: str, path: str, line: int) -> bool:
    ctx_patched = context.replace("sorry", tactic, 1)
    src = SCAFFOLD.format(repo=repo, path=path, line=line, context=ctx_patched)

    lean_src_dir = MATHLIB5_ROOT / "Mathlib5"
    lean_src_dir.mkdir(exist_ok=True)

    with tempfile.NamedTemporaryFile(
        suffix=".lean", mode="w", encoding="utf-8", delete=False,
        dir=str(lean_src_dir),
    ) as f:
        f.write(src)
        tmp = f.name

    try:
        env = os.environ.copy()
        r = subprocess.run(
            [LAKE_BIN, "env", LEAN_BIN, tmp],
            cwd=str(MATHLIB5_ROOT),
            capture_output=True, text=False,
            timeout=TACTIC_TIMEOUT, env=env,
        )
        stdout = (r.stdout or b"").decode("utf-8", errors="replace")
        stderr = (r.stderr or b"").decode("utf-8", errors="replace")
        out = stdout + stderr
        return (
            not re.search(r"\berror:", out)
            and not re.search(r"\bsorry\b", out)
            and "unsolved goals" not in out
        )
    except subprocess.TimeoutExpired:
        return False
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def process_target(
    target: dict,
    idx: int,
    total: int,
    dry_run: bool,
    chain_path: str,
    solved_dir: Path,
) -> dict:
    tid = target.get("id", f"T{idx}")
    repo = target.get("repo", "")
    fpath = target.get("file", "")
    note = target.get("note", "")[:70]
    fam = target.get("family", "?")

    prefix = f"[{idx+1}/{total}] {tid}  {repo}/{fpath}"
    print(prefix)

    result: dict = {
        "id": tid, "repo": repo, "file": fpath,
        "family": fam, "note": note,
        "status": "UNSOLVED", "tactic": None,
        "sorries_found": 0, "sorries_solved": 0,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    if dry_run:
        print(f"  {tid}: dry-run")
        return result

    src = fetch_file(repo, fpath)
    if src is None:
        print(f"  {tid}: FETCH_FAIL")
        result["status"] = "FETCH_FAIL"
        with _chain_lock:
            seal(chain_path, result)
        return result

    sorries = find_sorries(src)
    result["sorries_found"] = len(sorries)

    if not sorries:
        print(f"  {tid}: NO_SORRY")
        result["status"] = "NO_SORRY"
        with _chain_lock:
            seal(chain_path, result)
        return result

    patched_src = src
    local_solved = 0

    for si, (line_idx, line_text) in enumerate(sorries):
        ctx = get_context(patched_src, line_idx)
        closed_with = None
        for tactic in TACTICS:
            if try_tactic_scaffold(ctx, tactic, repo, fpath, line_idx + 1):
                closed_with = tactic
                lines = patched_src.splitlines(keepends=True)
                lines[line_idx] = lines[line_idx].replace("sorry", tactic, 1)
                patched_src = "".join(lines)
                local_solved += 1
                break

        status_char = f"SOLVED({closed_with})" if closed_with else "UNSOLVED"
        print(f"  {tid} sorry {si+1}/{len(sorries)} line {line_idx+1}: {status_char}")

    result["sorries_solved"] = local_solved
    result["tactic"] = "mixed" if local_solved > 0 else None

    if local_solved > 0:
        result["status"] = "SOLVED" if local_solved == len(sorries) else "PARTIAL"
        safe_name = tid.replace("/", "_").replace(":", "_") + "_sledged.lean"
        (solved_dir / safe_name).write_text(patched_src, encoding="utf-8")
        print(f"  {tid}: {result['status']} — saved {safe_name}")
    else:
        result["status"] = "UNSOLVED"
        print(f"  {tid}: UNSOLVED")

    with _chain_lock:
        seal(chain_path, result)

    return result


def sweep(
    roster_path: str,
    limit: int,
    family: str | None,
    dry_run: bool,
    out_dir: Path,
    workers: int,
) -> list[dict]:
    roster = json.loads(Path(roster_path).read_text(encoding="utf-8"))
    targets = roster.get("targets", [])

    if family:
        targets = [t for t in targets if t.get("family") == family]
    if limit:
        targets = targets[:limit]

    chain_path = str(out_dir / "sweep_chain.jsonl")
    results_path = out_dir / "sweep_results.json"
    solved_dir = out_dir / "solved"
    solved_dir.mkdir(exist_ok=True)

    total = len(targets)
    print(f"Targets: {total}  workers: {workers}  dry_run: {dry_run}  family: {family or 'all'}")
    print(f"WORM chain: {chain_path}\n")

    all_results: list[dict] = [None] * total  # type: ignore

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                process_target,
                t, i, total, dry_run, chain_path, solved_dir,
            ): i
            for i, t in enumerate(targets)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                all_results[i] = future.result()
            except Exception as exc:
                print(f"  [ERROR] target {i}: {exc}")
                all_results[i] = {"id": targets[i].get("id", f"T{i}"), "status": "ERROR", "error": str(exc)}

    all_results = [r for r in all_results if r is not None]

    solved = sum(1 for r in all_results if r.get("status") == "SOLVED")
    partial = sum(1 for r in all_results if r.get("status") == "PARTIAL")
    fetch_fail = sum(1 for r in all_results if r.get("status") == "FETCH_FAIL")

    print(f"\n{'='*60}")
    print(f"SWEEP COMPLETE")
    print(f"  Targets:    {total}")
    print(f"  Solved:     {solved}")
    print(f"  Partial:    {partial}")
    print(f"  Fetch fail: {fetch_fail}")
    print(f"  Unsolved:   {total - solved - partial - fetch_fail}")
    print(f"  WORM chain: {chain_path}")

    results_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"  Results:    {results_path}")

    return all_results


if __name__ == "__main__":
    require_capability("roster_sweep")
    ap = argparse.ArgumentParser(description="Sovereign sorry-roster sweep")
    ap.add_argument("--roster", required=True)
    ap.add_argument("--limit", type=int, default=0, help="max targets (0=all)")
    ap.add_argument("--family", default=None, help="filter by family")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).parent / "sweep_output"), help="output dir")
    ap.add_argument("--workers", type=int, default=4, help="concurrent workers (default: 4)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(exist_ok=True)

    sweep(
        roster_path=args.roster,
        limit=args.limit,
        family=args.family,
        dry_run=args.dry_run,
        out_dir=out,
        workers=args.workers,
    )
