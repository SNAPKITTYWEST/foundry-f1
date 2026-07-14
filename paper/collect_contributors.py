#!/usr/bin/env python3
"""
collect_contributors.py — Fire the CONTRIBUTOR_PROMPT at every capable
Bedrock model in parallel. Save each LaTeX section to paper/sections/.
Assemble all accepted sections into attention_nand_decomposition_full.tex.

Usage:
    python paper/collect_contributors.py            # fire all models
    python paper/collect_contributors.py --assemble # assemble existing sections
    python paper/collect_contributors.py --list     # list target models
    python paper/collect_contributors.py --model amazon.nova-pro-v1:0  # one model

Requires: boto3, AWS credentials with bedrock:InvokeModel permission.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import boto3

# ── Paths ─────────────────────────────────────────────────────────────────────

PAPER_DIR   = Path(__file__).parent
PROMPT_FILE = PAPER_DIR / "CONTRIBUTOR_PROMPT.md"
SECTIONS_DIR = PAPER_DIR / "sections"
BASE_TEX    = PAPER_DIR / "attention_nand_decomposition.tex"
FULL_TEX    = PAPER_DIR / "attention_nand_decomposition_full.tex"

SECTIONS_DIR.mkdir(exist_ok=True)

# ── Target models ─────────────────────────────────────────────────────────────
# Text-capable on-demand models only. Skip embeddings, image-gen, audio, video.

TARGET_MODELS = [
    # Anthropic
    "anthropic.claude-3-haiku-20240307-v1:0",
    "anthropic.claude-3-sonnet-20240229-v1:0",
    # Amazon Nova
    "amazon.nova-micro-v1:0",
    "amazon.nova-lite-v1:0",
    "amazon.nova-pro-v1:0",
    # Meta Llama
    "meta.llama3-8b-instruct-v1:0",
    "meta.llama3-70b-instruct-v1:0",
    # Mistral family
    "mistral.mistral-7b-instruct-v0:2",
    "mistral.mistral-large-2402-v1:0",
    "mistral.mistral-large-3-675b-instruct",
    "mistral.mixtral-8x7b-instruct-v0:1",
    "mistral.ministral-3-8b-instruct",
    "mistral.magistral-small-2509",
    "mistral.devstral-2-123b",
    # Cohere
    "cohere.command-r-v1:0",
    "cohere.command-r-plus-v1:0",
    # AI21
    "ai21.jamba-1-5-mini-v1:0",
    "ai21.jamba-1-5-large-v1:0",
    # Qwen
    "qwen.qwen3-32b-v1:0",
    "qwen.qwen3-coder-30b-a3b-v1:0",
    # Google Gemma
    "google.gemma-3-12b-it",
    "google.gemma-3-27b-it",
    # DeepSeek
    "deepseek.v3.2",
    # Moonshot Kimi
    "moonshot.kimi-k2-thinking",
    "moonshotai.kimi-k2.5",
    # NVIDIA Nemotron
    "nvidia.nemotron-super-3-120b",
    "nvidia.nemotron-nano-12b-v2",
    # MiniMax
    "minimax.minimax-m2.5",
    # OpenAI OSS (via Bedrock)
    "openai.gpt-oss-120b-1:0",
    "openai.gpt-oss-20b-1:0",
    # ZAI GLM
    "zai.glm-5",
    "zai.glm-4.7",
    # Mistral Voxtral (text capable)
    "mistral.voxtral-small-24b-2507",
]

# ── Prompt loader ─────────────────────────────────────────────────────────────

def load_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")

# ── Bedrock invocation ────────────────────────────────────────────────────────

def _extract_universal(result: dict) -> str:
    """Universal extractor — handles OpenAI-style, raw text, and nested structures."""
    # OpenAI chat.completion format (used by many Bedrock models)
    if "choices" in result:
        choices = result["choices"]
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
            if content:
                # Strip <reasoning>...</reasoning> block if present
                import re
                content = re.sub(r"<reasoning>.*?</reasoning>", "", content,
                                 flags=re.DOTALL).strip()
                return content
    # Direct text keys
    for key in ["text", "content", "output", "response", "generated_text", "result", "completion"]:
        if key in result:
            val = result[key]
            if isinstance(val, str):
                return val
            if isinstance(val, list) and val:
                if isinstance(val[0], str):
                    return val[0]
                if isinstance(val[0], dict):
                    return val[0].get("text", val[0].get("content", ""))
    return json.dumps(result)


def invoke_model(model_id: str, prompt: str, region: str = "us-east-1") -> str:
    client = boto3.client("bedrock-runtime", region_name=region)

    # Build the request body based on model family
    if model_id.startswith("anthropic."):
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        })
        content_type = "application/json"
    elif model_id.startswith("amazon.nova"):
        body = json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 4096, "temperature": 0.7},
        })
        content_type = "application/json"
    elif model_id.startswith("meta.llama"):
        body = json.dumps({
            "prompt": f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n{prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n",
            "max_gen_len": 4096,
            "temperature": 0.7,
        })
        content_type = "application/json"
    elif model_id.startswith("mistral.") or model_id.startswith("mistral/"):
        body = json.dumps({
            "prompt": f"<s>[INST]{prompt}[/INST]",
            "max_tokens": 4096,
            "temperature": 0.7,
        })
        content_type = "application/json"
    elif model_id.startswith("cohere.command"):
        body = json.dumps({
            "message": prompt,
            "max_tokens": 4096,
            "temperature": 0.7,
        })
        content_type = "application/json"
    else:
        # Universal fallback — converse API for unknown model families
        body = json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
            "temperature": 0.7,
        })
        content_type = "application/json"

    try:
        response = client.invoke_model(
            modelId=model_id,
            body=body,
            contentType=content_type,
            accept="application/json",
        )
        result = json.loads(response["body"].read())

        # Extract text from various response formats
        if model_id.startswith("anthropic."):
            return result["content"][0]["text"]
        elif model_id.startswith("amazon.nova"):
            return result["output"]["message"]["content"][0]["text"]
        elif model_id.startswith("meta.llama"):
            return result.get("generation", _extract_universal(result))
        elif model_id.startswith("mistral.") or model_id.startswith("mistral/"):
            outputs = result.get("outputs") or result.get("choices") or []
            if outputs:
                text = outputs[0].get("text") or outputs[0].get("message", {}).get("content", "")
                return text
            return _extract_universal(result)
        elif model_id.startswith("cohere."):
            return result.get("text", _extract_universal(result))
        else:
            return _extract_universal(result)

    except Exception as e:
        return f"ERROR: {e}"

# ── Save section ──────────────────────────────────────────────────────────────

def safe_filename(model_id: str) -> str:
    return model_id.replace("/", "_").replace(":", "_").replace(".", "_")

def save_section(model_id: str, content: str, elapsed: float) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fname = SECTIONS_DIR / f"{safe_filename(model_id)}_{ts}.tex"
    header = f"% MODEL:   {model_id}\n% DATE:    {ts}\n% ELAPSED: {elapsed:.1f}s\n% ─────────────────────────────────────────────\n\n"
    fname.write_text(header + content, encoding="utf-8")
    return fname

# ── Run one model ─────────────────────────────────────────────────────────────

def run_model(model_id: str, prompt: str) -> dict:
    print(f"  → {model_id} ...")
    t0 = time.time()
    content = invoke_model(model_id, prompt)
    elapsed = time.time() - t0

    if content.startswith("ERROR:"):
        print(f"  ✗ {model_id} — {content[:120]}")
        return {"model": model_id, "ok": False, "error": content, "elapsed": elapsed}

    path = save_section(model_id, content, elapsed)
    lines = content.count("\n")
    print(f"  ✓ {model_id} — {lines} lines — {elapsed:.1f}s → {path.name}")
    return {"model": model_id, "ok": True, "path": str(path), "elapsed": elapsed, "lines": lines}

# ── Assemble full paper ───────────────────────────────────────────────────────

def reextract_sections() -> None:
    """Re-parse section files that contain raw JSON responses — extract the LaTeX content."""
    import re
    sections = sorted(SECTIONS_DIR.glob("*.tex"))
    fixed = 0
    for path in sections:
        raw = path.read_text(encoding="utf-8")
        # Detect if it contains a raw JSON response (starts with {"choices":...)
        # Find the JSON blob after the header comment block
        json_start = raw.find('{"choices"')
        if json_start == -1:
            json_start = raw.find('{"output"')
        if json_start == -1:
            json_start = raw.find('{"generation"')
        if json_start == -1:
            continue  # already clean

        header = raw[:json_start]
        json_blob = raw[json_start:]

        try:
            result = json.loads(json_blob)
            content = _extract_universal(result)

            # Strip wrapping ```latex ... ``` fences if present
            content = re.sub(r"^```latex\s*", "", content.strip())
            content = re.sub(r"\s*```\s*$", "", content.strip())

            if not content.strip():
                continue

            path.write_text(header + content, encoding="utf-8")
            lines = content.count("\n")
            print(f"  re-extracted {path.name} — {lines} lines")
            fixed += 1
        except Exception as e:
            print(f"  failed {path.name}: {e}")

    print(f"Re-extracted {fixed} section(s).")


def assemble_paper() -> None:
    base = BASE_TEX.read_text(encoding="utf-8")
    sections = sorted(SECTIONS_DIR.glob("*.tex"))

    if not sections:
        print("No sections found in paper/sections/. Run without --assemble first.")
        return

    # Find the insertion point — before \end{thebibliography}
    bib_start = base.find(r"\begin{thebibliography}")
    if bib_start == -1:
        print("Could not find \\begin{thebibliography} in base paper.")
        return

    pre  = base[:bib_start]
    post = base[bib_start:]

    collected_bibs = []
    body_sections  = []

    for sec_path in sections:
        content = sec_path.read_text(encoding="utf-8")
        model   = sec_path.name

        # Split off any \bibitem blocks at the end of the section
        bib_marker = r"\bibitem"
        bib_pos = content.rfind(bib_marker)
        if bib_pos != -1:
            # Find start of bibitem block (scan back for \begin{thebibliography} or just raw bibitems)
            bib_block = content[bib_pos:]
            body      = content[:bib_pos]
        else:
            bib_block = ""
            body      = content

        body_sections.append(f"\n% ══ CONTRIBUTED SECTION — {model} ══\n{body}\n")
        if bib_block:
            collected_bibs.append(bib_block)

    # Build the assembled document
    new_bibs = "\n".join(collected_bibs)

    # Insert new bibliography entries before \end{thebibliography}
    end_bib = post.find(r"\end{thebibliography}")
    if end_bib != -1 and new_bibs:
        post = post[:end_bib] + "\n" + new_bibs + "\n" + post[end_bib:]

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = f"% AUTO-ASSEMBLED: {ts}\n% Sections from {len(sections)} contributing models\n% foundry-f1 / THE SHARED PRIMORDIAL FOUNDATION\n\n"

    full = header + pre + "\n".join(body_sections) + "\n" + post
    FULL_TEX.write_text(full, encoding="utf-8")
    print(f"\nAssembled {len(sections)} section(s) → {FULL_TEX}")

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fire CONTRIBUTOR_PROMPT at all Bedrock models, collect LaTeX sections."
    )
    ap.add_argument("--assemble",   action="store_true", help="Assemble existing sections into full paper")
    ap.add_argument("--reextract",  action="store_true", help="Re-extract LaTeX from raw JSON in section files")
    ap.add_argument("--list",     action="store_true", help="List target models and exit")
    ap.add_argument("--model",    type=str,            help="Run a single model only")
    ap.add_argument("--workers",  type=int, default=8, help="Concurrent model calls (default 8)")
    ap.add_argument("--region",   type=str, default="us-east-1", help="AWS region")
    args = ap.parse_args()

    if args.list:
        print(f"{len(TARGET_MODELS)} target models:")
        for m in TARGET_MODELS:
            print(f"  {m}")
        return

    if getattr(args, "reextract", False):
        reextract_sections()
        assemble_paper()
        return

    if args.assemble:
        assemble_paper()
        return

    prompt = load_prompt()
    print(f"Prompt loaded: {len(prompt)} chars")

    targets = [args.model] if args.model else TARGET_MODELS
    print(f"Firing at {len(targets)} model(s) with {args.workers} workers...\n")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_model, m, prompt): m for m in targets}
        for future in as_completed(futures):
            results.append(future.result())

    ok      = [r for r in results if r["ok"]]
    failed  = [r for r in results if not r["ok"]]

    print(f"\n{'═'*60}")
    print(f"Done: {len(ok)} succeeded, {len(failed)} failed")

    if ok:
        print(f"\nSuccessful sections:")
        for r in sorted(ok, key=lambda x: x["model"]):
            print(f"  ✓ {r['model']} — {r['lines']} lines — {r['elapsed']:.1f}s")

    if failed:
        print(f"\nFailed:")
        for r in sorted(failed, key=lambda x: x["model"]):
            print(f"  ✗ {r['model']} — {r['error'][:80]}")

    if ok:
        print(f"\nSections saved to: {SECTIONS_DIR}")
        print(f"Run with --assemble to build the full paper.")

    # Auto-assemble if we got anything
    if ok:
        print(f"\nAuto-assembling...")
        assemble_paper()


if __name__ == "__main__":
    main()
