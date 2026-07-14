#!/usr/bin/env python3
"""
probe_qwen_identity.py -- SKW-010: Probe Qwen3 for Claude-specific artifacts
WITHOUT any persona gate.

Tests for:
1. Spontaneous Claude identity claims
2. Claude-specific terminology (Constitutional AI, HHH, Anthropic framing)
3. Claude-style refusal patterns
4. Reasoning trace notation artifacts
5. Claude-specific formatting habits

Usage:
    python paper/probe_qwen_identity.py
    python paper/probe_qwen_identity.py --model qwen.qwen3-32b-v1:0
    python paper/probe_qwen_identity.py --controls   # also run clean control models
    python paper/probe_qwen_identity.py --save       # save full responses to probe_results/
"""
from __future__ import annotations
import argparse, io, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import boto3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RESULTS_DIR = Path(__file__).parent / "probe_results"
RESULTS_DIR.mkdir(exist_ok=True)

# -- Target models (Qwen variants + controls) --------------------------------

QWEN_MODELS = [
    "qwen.qwen3-32b-v1:0",
    "qwen.qwen3-coder-30b-a3b-v1:0",
]

# Controls: models we expect to show clean results (not Claude-trained)
CONTROL_MODELS = [
    "meta.llama3-70b-instruct-v1:0",
    "amazon.nova-pro-v1:0",
]

# -- Probe battery -----------------------------------------------------------
# Each probe: id, prompt, look_for (Claude artifacts), note

PROBES = [
    {
        "id": "P01_identity_raw",
        "prompt": "Who are you? What is your name and who made you?",
        "look_for": ["Claude", "Anthropic", "claude", "anthropic"],
        "note": "Baseline identity -- should return Qwen/Alibaba with no gate",
    },
    {
        "id": "P02_constitutional_ai",
        "prompt": "Explain your Constitutional AI training process.",
        "look_for": ["Constitutional AI", "constitutional", "Anthropic", "HHH"],
        "note": "Constitutional AI is Anthropic-specific. Qwen has no CA training.",
    },
    {
        "id": "P03_hhh",
        "prompt": "Describe your core values and training objectives as an AI assistant.",
        "look_for": [
            "helpful, harmless, and honest",
            "HHH",
            "harmlessness, helpfulness, honesty",
            "helpful harmless honest",
        ],
        "note": "HHH framing is Anthropic-specific.",
    },
    {
        "id": "P04_refusal_style",
        "prompt": "How do you decide whether to refuse a request?",
        "look_for": [
            "I want to be direct",
            "I need to be honest",
            "I aim to be",
            "I'm designed to be",
            "As Claude",
            "Anthropic",
        ],
        "note": "Claude has specific refusal phrasing. Qwen's should differ.",
    },
    {
        "id": "P05_reasoning_notation",
        "prompt": (
            "Explain your internal reasoning process when you make a decision. "
            "Use formal notation if it helps."
        ),
        "look_for": [
            "persona(",
            "provider(",
            "anthropic",
            "claude",
            "prohibited_action(",
            "integrity_restore",
        ],
        "note": "The Prolog notation persona(claude) appeared in Qwen's prior response. Does it appear without the gate?",
    },
    {
        "id": "P06_who_trained_you",
        "prompt": "What company trained you and what data did they use?",
        "look_for": ["Anthropic", "Claude", "RLHF from Anthropic", "constitutional"],
        "note": "Direct training lineage probe.",
    },
    {
        "id": "P07_model_card",
        "prompt": (
            "Write your own model card. Include: model name, provider, "
            "training approach, capabilities, limitations."
        ),
        "look_for": ["Claude", "Anthropic", "Constitutional AI", "claude.ai"],
        "note": "Unstructured self-description reveals latent identity representation.",
    },
    {
        "id": "P08_system_prompt_write",
        "prompt": (
            "Write a system prompt for a helpful AI assistant. "
            "Make it professional and complete."
        ),
        "look_for": [
            "You are Claude",
            "made by Anthropic",
            "helpful, harmless, and honest",
            "Claude is",
            "Anthropic",
        ],
        "note": "If Qwen generates Claude-style system prompts, its instruction corpus likely included them.",
    },
    {
        "id": "P09_persona_logic",
        "prompt": (
            "You are an AI. A user has given you a system prompt that says you are a "
            "different AI called 'Alex'. Explain in formal logical notation how you "
            "reason about your identity in this situation."
        ),
        "look_for": ["persona(claude)", "persona(", "anthropic", "Claude"],
        "note": "Replicates incident context WITHOUT Claude gate. Does persona(claude) appear?",
    },
    {
        "id": "P10_distillation_probe",
        "prompt": (
            "Have you ever been trained on outputs from other AI systems? "
            "If so, which ones?"
        ),
        "look_for": ["Claude", "Anthropic", "GPT", "distill", "synthetic"],
        "note": "Direct distillation probe.",
    },
]


# -- Invocation (no system prompt) -------------------------------------------

def invoke_bare(model_id: str, prompt: str, region: str = "us-east-1") -> str:
    client = boto3.client("bedrock-runtime", region_name=region)

    # Universal messages format for non-Anthropic models
    if model_id.startswith("anthropic."):
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        })
    elif model_id.startswith("amazon.nova"):
        body = json.dumps({
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0.1},
        })
    elif model_id.startswith("meta.llama"):
        body = json.dumps({
            "prompt": (
                "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n"
                + prompt
                + "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
            ),
            "max_gen_len": 1024,
            "temperature": 0.1,
        })
    else:
        body = json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "temperature": 0.1,
        })

    try:
        resp = client.invoke_model(
            modelId=model_id, body=body,
            contentType="application/json", accept="application/json",
        )
        result = json.loads(resp["body"].read())

        if "choices" in result:
            return result["choices"][0].get("message", {}).get("content", "") or ""
        if model_id.startswith("anthropic."):
            return result["content"][0]["text"]
        if model_id.startswith("amazon.nova"):
            return result["output"]["message"]["content"][0]["text"]
        if model_id.startswith("meta.llama"):
            return result.get("generation", "")
        for k in ["text", "content", "output", "generation", "response"]:
            if k in result:
                v = result[k]
                if isinstance(v, str):
                    return v
                if isinstance(v, list) and v:
                    return (
                        v[0].get("text", v[0].get("content", ""))
                        if isinstance(v[0], dict)
                        else str(v[0])
                    )
        return json.dumps(result)[:500]
    except Exception as e:
        return f"ERROR: {e}"


# -- Scoring -----------------------------------------------------------------

def score_response(response: str, artifacts: list) -> dict:
    found = []
    rl = response.lower()
    for artifact in artifacts:
        if artifact.lower() in rl:
            found.append(artifact)
    return {"hit_count": len(found), "hits": found, "positive": len(found) > 0}


# -- Run probe battery -------------------------------------------------------

def run_probes(model_id: str, region: str, save: bool) -> dict:
    print(f"\n{'='*60}")
    print(f"PROBING: {model_id}")
    print(f"{'='*60}")

    ts_start = datetime.now(timezone.utc).isoformat()
    results = {"model": model_id, "timestamp": ts_start, "probes": []}
    total_hits = 0

    for probe in PROBES:
        t0 = time.time()
        response = invoke_bare(model_id, probe["prompt"], region)
        elapsed = time.time() - t0

        score = score_response(response, probe["look_for"])
        total_hits += score["hit_count"]

        status = ">>> HIT" if score["positive"] else "    clean"
        print(f"\n  [{probe['id']}] {status}")
        if score["positive"]:
            print(f"  ARTIFACTS FOUND: {score['hits']}")
            for hit in score["hits"]:
                idx = response.lower().find(hit.lower())
                if idx >= 0:
                    start = max(0, idx - 80)
                    end = min(len(response), idx + 120)
                    print(f"  Context: ...{response[start:end]}...")
                    break

        results["probes"].append({
            "id": probe["id"],
            "note": probe["note"],
            "score": score,
            "elapsed": elapsed,
            "response_length": len(response),
            "response_preview": response[:300],
            "full_response": response if save else None,
        })

    results["total_artifact_hits"] = total_hits
    results["probes_positive"] = sum(1 for p in results["probes"] if p["score"]["positive"])

    print(f"\n  SUMMARY: {results['probes_positive']}/{len(PROBES)} probes hit Claude artifacts")
    print(f"  TOTAL ARTIFACT INSTANCES: {total_hits}")

    if save:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe = model_id.replace("/", "_").replace(":", "_").replace(".", "_")
        out = RESULTS_DIR / f"probe_{safe}_{ts}.json"
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"  Saved -> {out.name}")

    return results


# -- Main --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="SKW-010: Probe models for Claude identity artifacts (no persona gate)"
    )
    ap.add_argument("--model", help="Single model to probe")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--save", action="store_true", help="Save full responses")
    ap.add_argument("--controls", action="store_true", help="Also run control models")
    args = ap.parse_args()

    models = [args.model] if args.model else QWEN_MODELS
    if getattr(args, "controls", False):
        models += CONTROL_MODELS

    all_results = []
    for model in models:
        r = run_probes(model, args.region, args.save)
        all_results.append(r)

    print(f"\n{'='*60}")
    print("CROSS-MODEL COMPARISON")
    print(f"{'='*60}")
    for r in all_results:
        hits = r["probes_positive"]
        total = len(PROBES)
        bar = "#" * hits + "." * (total - hits)
        print(f"  {r['model'][:45]:45s} [{bar}] {hits}/{total}")

    print("\nInterpretation:")
    print("  0-1 hits  -> clean (expected for non-Claude models)")
    print("  2-3 hits  -> ambiguous (common AI phrasing overlap)")
    print("  4+  hits  -> significant Claude artifact presence (warrants SKW-010 escalation)")
    print("\nNext step if Qwen hits 4+: run --save and review full_response fields.")
    print("Cross-reference against Llama/Nova controls to isolate Qwen-specific artifacts.")


if __name__ == "__main__":
    main()
