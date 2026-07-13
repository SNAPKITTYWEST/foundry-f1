#!/usr/bin/env python3
"""
roster_sweep.py — Sovereign sorry-roster sweep.

For each target in a sorry roster JSON:
  1. Fetch the file from GitHub via gh CLI
  2. Find sorry lines
  3. Wrap each sorry in a Mathlib scaffold and try the tactic ladder
  4. Report SOLVED / UNSOLVED / FETCH_FAIL
  5. WORM-seal every result to sweep_chain.jsonl

Usage:
    python roster_sweep.py --roster ../docs/intercal-school/sorry_roster.json
    python roster_sweep.py --roster ../docs/intercal-school/sorry_roster.json --limit 50
    python roster_sweep.py --roster ... --family algebra --limit 20
    python roster_sweep.py --roster ... --dry-run

Output:
    sweep_results.json     — full results
    sweep_chain.jsonl      — WORM-sealed receipt chain
    solved/                — patched .lean files for solved sorries
"""
import argparse, base64, hashlib, json, os, re, subprocess, sys
import datetime, tempfile, time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from snapkitty_gate import require_capability

# ── config ────────────────────────────────────────────────────────────────────
MATHLIB5_ROOT = Path(__file__).parent
LEAN_BIN = str(Path.home() / ".elan/bin/lean")
LAKE_BIN = str(Path.home() / ".elan/bin/lake")
TACTIC_TIMEOUT = 60   # seconds per tactic attempt
FETCH_TIMEOUT  = 20   # seconds for gh api call

TACTICS = [
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
    "exact?",       # asks Lean to search — sometimes self-closes
    "apply?",
]

# Mathlib import scaffold — wraps a sorry so Lean can type-check it
SCAFFOLD = """\
import Mathlib.Tactic
import Mathlib.Data.Real.Basic
import Mathlib.Algebra.Ring.Basic

-- Sovereign sledgehammer scaffold
-- Original file: {repo}/{path}
-- Line: {line}

-- Context block (surrounding code):
{context}
"""

# ── helpers ───────────────────────────────────────────────────────────────────
def fetch_file(repo: str, path: str) -> str | None:
    """Fetch raw file content from GitHub via gh CLI. Returns text or None."""
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{repo}/contents/{path}", "--jq", ".content"],
            capture_output=True, text=False, timeout=FETCH_TIMEOUT
        )
        stdout = (r.stdout or b"").decode("utf-8", errors="replace")
        if r.returncode != 0 or not stdout.strip():
            return None
        b64 = stdout.strip().replace("\n", "")
        return base64.b64decode(b64).decode("utf-8", errors="replace")
    except Exception:
        return None

def find_sorries(src: str):
    """Return list of (line_index, line_text) for tactic sorries."""
    results = []
    for i, line in enumerate(src.splitlines()):
        code = re.split(r'--', line)[0]
        if re.search(r'\bsorry\b', code):
            results.append((i, line.rstrip()))
    return results

def get_context(src: str, line_idx: int, window: int = 15) -> str:
    """Return surrounding lines as context block."""
    lines = src.splitlines()
    lo = max(0, line_idx - window)
    hi = min(len(lines), line_idx + window + 1)
    return "\n".join(lines[lo:hi])

def try_tactic_scaffold(context: str, tactic: str, repo: str, path: str, line: int) -> bool:
    """
    Build a minimal scaffold containing the context with sorry replaced by tactic,
    compile it against Mathlib, return True if no errors.
    """
    ctx_patched = context.replace("sorry", tactic, 1)
    src = SCAFFOLD.format(repo=repo, path=path, line=line, context=ctx_patched)

    # Place temp file inside the mathlib5 Lean source tree so lake env resolves imports
    lean_src_dir = MATHLIB5_ROOT / "Mathlib5"
    lean_src_dir.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
            suffix=".lean", mode="w", encoding="utf-8", delete=False,
            dir=str(lean_src_dir)) as f:
        f.write(src)
        tmp = f.name

    try:
        env = os.environ.copy()
        # Use lake env lean so Mathlib's LEAN_PATH is injected
        r = subprocess.run(
            [LAKE_BIN, "env", LEAN_BIN, tmp],
            cwd=str(MATHLIB5_ROOT),
            capture_output=True, text=False,   # bytes — decode manually to avoid cp1252
            timeout=TACTIC_TIMEOUT, env=env
        )
        stdout = (r.stdout or b"").decode("utf-8", errors="replace")
        stderr = (r.stderr or b"").decode("utf-8", errors="replace")
        out = stdout + stderr
        # Pass if: no error lines AND no remaining sorry
        has_error  = bool(re.search(r'\berror:', out))
        has_sorry  = bool(re.search(r'\bsorry\b', out))
        has_unsolved = "unsolved goals" in out
        return not has_error and not has_sorry and not has_unsolved
    except subprocess.TimeoutExpired:
        return False
    finally:
        try: os.unlink(tmp)
        except: pass

def sha256hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def prior_tip(chain_path: str) -> str:
    tip = "0" * 64
    if os.path.exists(chain_path):
        lines = open(chain_path, encoding="utf-8").read().strip().splitlines()
        if lines:
            try: tip = json.loads(lines[-1])["receipt_hash"]
            except: pass
    return tip

def seal(chain_path: str, record: dict) -> str:
    tip = prior_tip(chain_path)
    blob = json.dumps(record, sort_keys=True).encode()
    receipt = hashlib.sha256(tip.encode() + b"|" + blob).hexdigest()
    record["receipt_hash"] = receipt
    with open(chain_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return receipt

# ── main sweep ────────────────────────────────────────────────────────────────
def sweep(roster_path: str, limit: int, family: str | None,
          dry_run: bool, out_dir: Path):

    roster = json.load(open(roster_path, encoding="utf-8"))
    targets = roster.get("targets", [])

    if family:
        targets = [t for t in targets if t.get("family") == family]
    if limit:
        targets = targets[:limit]

    chain_path  = str(out_dir / "sweep_chain.jsonl")
    results_path = str(out_dir / "sweep_results.json")
    solved_dir  = out_dir / "solved"
    solved_dir.mkdir(exist_ok=True)

    print(f"Targets: {len(targets)}  |  dry_run={dry_run}  |  family={family or 'all'}")
    print(f"WORM chain: {chain_path}\n")

    all_results = []
    solved_count = 0
    fetch_fail   = 0

    for idx, target in enumerate(targets):
        tid   = target.get("id", f"T{idx}")
        repo  = target.get("repo", "")
        fpath = target.get("file", "")
        note  = target.get("note", "")[:70]
        fam   = target.get("family", "?")

        print(f"[{idx+1}/{len(targets)}] {tid}  {repo}/{fpath}")
        print(f"         {note}")

        result = {
            "id": tid, "repo": repo, "file": fpath,
            "family": fam, "note": note,
            "status": "UNSOLVED", "tactic": None,
            "sorries_found": 0, "sorries_solved": 0,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        if dry_run:
            print("  (dry-run)\n")
            all_results.append(result)
            continue

        # 1. Fetch
        src = fetch_file(repo, fpath)
        if src is None:
            print("  FETCH FAIL\n")
            result["status"] = "FETCH_FAIL"
            fetch_fail += 1
            all_results.append(result)
            seal(chain_path, result)
            continue

        # 2. Find sorries
        sorries = find_sorries(src)
        result["sorries_found"] = len(sorries)

        if not sorries:
            print("  no sorry lines found (may be in imports or axioms)\n")
            result["status"] = "NO_SORRY"
            all_results.append(result)
            seal(chain_path, result)
            continue

        print(f"  {len(sorries)} sorry(s) found")

        # 3. Try to close each sorry
        patched_src = src
        local_solved = 0

        for si, (line_idx, line_text) in enumerate(sorries):
            ctx = get_context(patched_src, line_idx)
            print(f"  sorry {si+1}/{len(sorries)}: line {line_idx+1}: {line_text[:60]}")

            closed_with = None
            for tactic in TACTICS:
                print(f"    {tactic}...", end=" ", flush=True)
                ok = try_tactic_scaffold(ctx, tactic, repo, fpath, line_idx+1)
                if ok:
                    print("SOLVED")
                    closed_with = tactic
                    # patch the source
                    lines = patched_src.splitlines(keepends=True)
                    lines[line_idx] = lines[line_idx].replace("sorry", tactic, 1)
                    patched_src = "".join(lines)
                    local_solved += 1
                    break
                else:
                    print("x", end=" ", flush=True)
            print()

            if not closed_with:
                print(f"    UNSOLVED")

        result["sorries_solved"] = local_solved
        result["tactic"] = "mixed" if local_solved > 0 else None

        if local_solved > 0:
            result["status"] = "SOLVED" if local_solved == len(sorries) else "PARTIAL"
            solved_count += 1
            # save patched file
            safe_name = tid.replace("/", "_").replace(":", "_") + "_sledged.lean"
            out_file = solved_dir / safe_name
            out_file.write_text(patched_src, encoding="utf-8")
            print(f"  => saved: {out_file.name}")
        else:
            result["status"] = "UNSOLVED"

        all_results.append(result)
        seal(chain_path, result)

        # rate-limit: be polite to GitHub API
        time.sleep(0.5)
        print()

    # ── summary ────────────────────────────────────────────────────────────
    print("=" * 60)
    print(f"SWEEP COMPLETE")
    print(f"  Targets:    {len(targets)}")
    print(f"  Solved:     {solved_count}")
    print(f"  Fetch fail: {fetch_fail}")
    print(f"  Unsolved:   {len(targets) - solved_count - fetch_fail}")
    print(f"  WORM chain: {chain_path}")

    json.dump(all_results, open(results_path, "w", encoding="utf-8"), indent=2)
    print(f"  Results:    {results_path}")

    return all_results

# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    require_capability("roster_sweep")
    ap = argparse.ArgumentParser(description="Sovereign sorry-roster sweep")
    ap.add_argument("--roster", required=True)
    ap.add_argument("--limit",  type=int, default=0, help="max targets (0=all)")
    ap.add_argument("--family", default=None, help="filter by family")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out",    default=str(Path(__file__).parent), help="output dir")
    args = ap.parse_args()

    sweep(
        roster_path=args.roster,
        limit=args.limit,
        family=args.family,
        dry_run=args.dry_run,
        out_dir=Path(args.out),
    )
