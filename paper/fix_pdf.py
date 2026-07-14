#!/usr/bin/env python3
"""Fix duplicate labels and UTF-8 issues in assembled paper, then compile to PDF."""
import io, re, subprocess, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PAPER_DIR = Path(__file__).parent
FULL_TEX  = PAPER_DIR / "attention_nand_decomposition_full.tex"

# ── Step 1: fix UTF-8 issues in section files ──────────────────────────────
print("Step 1: checking section files for encoding issues...")
sections = sorted((PAPER_DIR / "sections").glob("*.tex"))
for s in sections:
    try:
        raw = s.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        # rewrite clean utf-8
        s.write_text(text, encoding="utf-8")
    except Exception as e:
        print(f"  warning {s.name}: {e}")

# ── Step 2: reassemble ─────────────────────────────────────────────────────
print("Step 2: reassembling paper...")
result = subprocess.run(
    [sys.executable, str(PAPER_DIR / "collect_contributors.py"), "--assemble"],
    capture_output=True, text=True, cwd=str(PAPER_DIR)
)
print(result.stdout[-300:] if result.stdout else "")

# ── Step 3: fix duplicate labels in assembled file ─────────────────────────
print("Step 3: fixing duplicate labels...")
text = FULL_TEX.read_text(encoding="utf-8", errors="replace")

seen_labels = set()
counter = [0]

def dedup_label(m):
    lbl = m.group(1)
    if lbl in seen_labels:
        counter[0] += 1
        new_lbl = f"{lbl}-dup{counter[0]}"
        print(f"  renamed: {lbl} -> {new_lbl}")
        return f"\\label{{{new_lbl}}}"
    seen_labels.add(lbl)
    return m.group(0)

# use a simple string-based approach to avoid regex escape issues
lines = text.split("\n")
out_lines = []
for line in lines:
    if "\\label{" in line:
        # extract label
        start = line.find("\\label{")
        end = line.find("}", start)
        if start >= 0 and end >= 0:
            lbl = line[start+7:end]
            if lbl in seen_labels:
                counter[0] += 1
                new_lbl = f"{lbl}-dup{counter[0]}"
                print(f"  renamed: {lbl} -> {new_lbl}")
                line = line[:start+7] + new_lbl + line[end:]
            else:
                seen_labels.add(lbl)
    out_lines.append(line)

text = "\n".join(out_lines)

# ── Step 4: ensure inputenc utf8 is in preamble ────────────────────────────
if "\\usepackage[utf8]{inputenc}" not in text and "\\usepackage{inputenc}" not in text:
    text = text.replace(
        "\\documentclass",
        "% UTF-8 encoding\n\\PassOptionsToPackage{utf8}{inputenc}\n\\documentclass",
        1
    )

FULL_TEX.write_text(text, encoding="utf-8")
print(f"Fixed. Labels seen: {len(seen_labels)}, dupes renamed: {counter[0]}")

# ── Step 5: compile ────────────────────────────────────────────────────────
print("\nStep 4: compiling PDF (pass 1)...")
for pass_num in range(1, 3):
    r = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", FULL_TEX.name],
        capture_output=True, text=True, cwd=str(PAPER_DIR), encoding="utf-8", errors="replace"
    )
    # show only errors and final output line
    for line in r.stdout.split("\n"):
        if line.startswith("Output written") or (line.startswith("!") and "UTF" not in line):
            print(f"  pass {pass_num}: {line}")

pdf = PAPER_DIR / "attention_nand_decomposition_full.pdf"
if pdf.exists():
    size_mb = pdf.stat().st_size / 1024 / 1024
    print(f"\nPDF ready: {pdf} ({size_mb:.1f} MB)")
else:
    print("\nPDF not found — check log for errors")
    log = PAPER_DIR / "attention_nand_decomposition_full.log"
    if log.exists():
        lines = log.read_text(encoding="utf-8", errors="replace").split("\n")
        errors = [l for l in lines if l.startswith("!")]
        for e in errors[:10]:
            print(f"  {e}")
