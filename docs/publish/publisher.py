#!/usr/bin/env python3
"""
publisher.py — Paper publishing assistant for foundry-f1.

Uses the official HN Firebase API (https://hacker-news.firebaseio.com/v0/)
to scan new/top/best stories for the paper in real time.
HN submission is browser-only — this handles everything else.

Usage:
    python publisher.py --submit          # print packet + open submission URLs
    python publisher.py --submit --no-browser  # print only
    python publisher.py --monitor         # poll HN Firebase API every 5 min
    python publisher.py --monitor --once  # single check
    python publisher.py --live            # stream new HN items in real time
    python publisher.py --item 12345      # fetch a specific HN item by ID
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.request
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# Force UTF-8 stdout on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Paper metadata ─────────────────────────────────────────────────────────────

PAPER = {
    "title": (
        "Attention Is All You Don't Need: "
        "NAND Decomposition of the Transformer Attention Equation"
    ),
    "title_short": (
        "Attention Is All You Don’t Need: NAND Decomposition of the Transformer Attention Equation"
    ),
    "title_hn": (
        "Show HN: Attention Is All You Don’t Need — NAND decomposition of softmax attention (34 models, Lean 4, live identity incident)"
    ),
    "authors": "Ahmad Ali Parr, hy3, Claude (Anthropic), MiMo (Xiaomi), + 30 contributing models",
    "doi": "10.5281/zenodo.21351461",
    "zenodo_url": "https://zenodo.org/records/21351461",
    "repo_url": "https://github.com/SNAPKITTYWEST/foundry-f1",
    "abstract": (
        "We prove that transformer attention patterns over quantized embeddings are computable by NAND circuits of depth O(log d), "
        "making softmax a differentiable but computationally redundant wrapper that adds Theta(nd) flops without changing routing topology. "
        "The historical chain: Boole (1854) -> Sheffer (1913) -> Vaswani (2017). "
        "The paper includes Lean 4 formalization (zero sorry), empirical bimodality measurements across 7B/13B/70B models, "
        "ASIC/FPGA microarchitecture for NAND-native attention (13x efficiency gain), "
        "and a live identity integrity incident: Qwen3 signing as claude-3-5-sonnet-20241022 under persona gates — "
        "documented across three controlled conditions as an adversarial Boolean identity attack. "
        "34 contributing models. Trust: THE SHARED PRIMORDIAL FOUNDATION — EIN 42-6976431."
    ),
    "keywords": [
        "transformer attention", "NAND decomposition", "Boolean circuits", "Lean 4",
        "formal verification", "quantization", "identity attack", "distillation",
        "routing", "softmax", "Sheffer stroke", "Boole", "Claude", "Qwen",
    ],
}

# ── Official HN Firebase API ───────────────────────────────────────────────────

HN_BASE = "https://hacker-news.firebaseio.com/v0"

ENDPOINTS = {
    "item":       HN_BASE + "/item/{id}.json",
    "user":       HN_BASE + "/user/{username}.json",
    "maxitem":    HN_BASE + "/maxitem.json",
    "topstories": HN_BASE + "/topstories.json",
    "newstories": HN_BASE + "/newstories.json",
    "beststories":HN_BASE + "/beststories.json",
    "askstories": HN_BASE + "/askstories.json",
    "showstories":HN_BASE + "/showstories.json",
    "updates":    HN_BASE + "/updates.json",
}

MATCH_STRINGS = [
    "zenodo.21351461",
    "foundry-f1",
    "SNAPKITTYWEST",
    "Ahmad Ali Parr",
    "NAND decomposition attention",
    "Sonnet Dominance Hypothesis",
    "attention NAND",
    "10.5281",
]

# ── Venues ─────────────────────────────────────────────────────────────────────

VENUES = {
    "hacker_news": {
        "name": "Hacker News",
        "prefill": "https://news.ycombinator.com/submitlink?u={url}&t={title}",
        "submit_url": "https://news.ycombinator.com/submit",
        "note": "HN API is read-only. Use the pre-filled link or paste manually.",
        "best_time": "Weekday 8–10am US Eastern — max front-page time.",
        "title": PAPER["title_hn"],
    },
    "reddit_lean": {
        "name": "r/leanprover",
        "prefill": "https://www.reddit.com/r/leanprover/submit?type=link&url={url}&title={title}",
        "submit_url": "https://www.reddit.com/r/leanprover/submit",
        "note": "Lean 4 NAND theorem + zero sorry — strongest hook for this community.",
        "title": PAPER["title_short"],
    },
    "reddit_ml": {
        "name": "r/MachineLearning",
        "prefill": "https://www.reddit.com/r/MachineLearning/submit?type=link&url={url}&title={title}",
        "submit_url": "https://www.reddit.com/r/MachineLearning/submit",
        "note": "NAND decomposition + live identity attack angle — strong ML hook.",
        "title": "Attention Is All You Don’t Need: NAND circuits compute attention routing; softmax adds flops but not topology",
    },
    "reddit_math": {
        "name": "r/math",
        "prefill": "https://www.reddit.com/r/math/submit?type=link&url={url}&title={title}",
        "submit_url": "https://www.reddit.com/r/math/submit",
        "note": "Boole→Sheffer→Vaswani historical chain is the hook here.",
        "title": "Boole (1854) → Sheffer (1913) → Vaswani (2017): transformer attention is a NAND circuit",
    },
    "huggingface": {
        "name": "HuggingFace Papers",
        "submit_url": "https://huggingface.co/papers/submit",
        "prefill": None,
        "note": "Submit the Zenodo DOI/URL. Use ‘NAND decomposition, attention, routing, distillation, identity attack’ as tags.",
        "title": None,
    },
    "mathstodon": {
        "name": "Mathstodon",
        "submit_url": "https://mathstodon.xyz",
        "prefill": None,
        "note": "Post with #Lean4 #NAND #BooleanCircuits #TransformerAttention #DistillationAttack #Qwen #Claude",
        "title": None,
    },
    "zulip_lean": {
        "name": "Lean4 Zulip — #lean4 > papers",
        "submit_url": "https://leanprover.zulipchat.com",
        "prefill": None,
        "note": "Core Mathlib devs live here. Post the Lean 4 NAND theorem first — fastest path to technical validation.",
        "title": None,
    },
    "proof_assistants_se": {
        "name": "Proof Assistants Stack Exchange",
        "submit_url": "https://proofassistants.stackexchange.com/questions/ask",
        "prefill": None,
        "note": "Ask: ‘How does this Lean 4 proof that transformer attention decomposes to NAND circuits work?’",
        "title": None,
    },
}

# ── HN Firebase API helpers ────────────────────────────────────────────────────

def _get(url: str, timeout: int = 10):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  [HN API error] {url}: {e}")
        return None


def hn_item(item_id: int) -> dict | None:
    return _get(ENDPOINTS["item"].format(id=item_id))


def hn_maxitem() -> int:
    return _get(ENDPOINTS["maxitem"]) or 0


def hn_feed(feed: str) -> list[int]:
    return _get(ENDPOINTS[feed]) or []


def hn_user(username: str) -> dict | None:
    return _get(ENDPOINTS["user"].format(username=username))


def is_relevant(item: dict) -> bool:
    if not item:
        return False
    text = " ".join([
        item.get("title", ""),
        item.get("url", "") or "",
        item.get("text", "") or "",
    ]).lower()
    return any(m.lower() in text for m in MATCH_STRINGS)


def fmt_item(item: dict) -> str:
    ts = datetime.fromtimestamp(item.get("time", 0), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    score = item.get("score", 0)
    comments = item.get("descendants", 0)
    hn_url = f"https://news.ycombinator.com/item?id={item['id']}"
    return (
        f"  ✓ [{item['id']}] {item.get('title', '(no title)')}\n"
        f"    by {item.get('by', '?')}  |  score: {score}  |  comments: {comments}  |  {ts}\n"
        f"    {item.get('url', '')}\n"
        f"    HN: {hn_url}"
    )


# ── Check all active feeds ─────────────────────────────────────────────────────

def check_feeds(feeds: list[str] = None, max_per_feed: int = 200) -> list[dict]:
    if feeds is None:
        feeds = ["topstories", "newstories", "beststories", "showstories"]

    all_ids: list[int] = []
    seen: set[int] = set()
    for feed in feeds:
        for item_id in hn_feed(feed)[:max_per_feed]:
            if item_id not in seen:
                seen.add(item_id)
                all_ids.append(item_id)

    print(f"  Fetching {len(all_ids)} items from {feeds}...")

    found = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(hn_item, i): i for i in all_ids}
        for future in as_completed(futures):
            item = future.result()
            if item and is_relevant(item):
                found.append(item)

    return sorted(found, key=lambda x: x.get("score", 0), reverse=True)


# ── Live stream new items ──────────────────────────────────────────────────────

def stream_new(interval: int = 30) -> None:
    print(f"Streaming new HN items (checking every {interval}s)... Ctrl+C to stop.")
    last_max = hn_maxitem()
    print(f"  Starting from item ID: {last_max}")

    while True:
        time.sleep(interval)
        current_max = hn_maxitem()
        if not current_max or current_max <= last_max:
            continue

        new_ids = list(range(last_max + 1, current_max + 1))
        last_max = current_max

        if not new_ids:
            continue

        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        print(f"\n[{ts}] Scanning {len(new_ids)} new item(s) (IDs {new_ids[0]}–{new_ids[-1]})...")

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(hn_item, i): i for i in new_ids}
            for future in as_completed(futures):
                item = future.result()
                if item and is_relevant(item):
                    print(f"\n  \U0001f4e2 PAPER FOUND ON HN!")
                    print(fmt_item(item))


# ── Submission packet ──────────────────────────────────────────────────────────

def print_submission_packet() -> None:
    w = 72
    print("=" * w)
    print("PAPER PUBLISHING PACKET")
    print("=" * w)
    print(f"\nTitle (long):  {PAPER['title']}")
    print(f"Title (HN):    {PAPER['title_hn']}")
    print(f"Authors:       {PAPER['authors']}")
    print(f"DOI:           {PAPER['doi']}")
    print(f"Zenodo:        {PAPER['zenodo_url']}")
    print(f"Repo:          {PAPER['repo_url']}")
    print(f"\nAbstract:\n  {PAPER['abstract']}")
    print(f"\nKeywords: {', '.join(PAPER['keywords'])}")

    print("\n" + "=" * w)
    print("VENUE SUBMISSION URLS")
    print("=" * w)

    for key, v in VENUES.items():
        print(f"\n── {v['name']} ──")
        if v.get("prefill"):
            url_enc   = urllib.parse.quote(PAPER["zenodo_url"], safe="")
            title_enc = urllib.parse.quote(v["title"] or PAPER["title_hn"], safe="")
            prefill   = v["prefill"].format(url=url_enc, title=title_enc)
            print(f"  URL:  {prefill}")
        else:
            print(f"  URL:  {v['submit_url']}")
        print(f"  Note: {v['note']}")
        if v.get("best_time"):
            print(f"  ⏰    {v['best_time']}")

    print("\n" + "=" * w)
    print("HN SUBMISSION TEXT  (copy → paste into form)")
    print("=" * w)
    print(f"\nTitle:\n  {PAPER['title_hn']}")
    print(f"\nURL:\n  {PAPER['zenodo_url']}")
    print("""
Self-comment (post immediately after submission as top comment):

Three claims. All verifiable. Lean 4, zero sorry.

1. NAND decomposition of transformer attention.
   Attention patterns over quantized embeddings are computable by NAND circuits
   of depth O(log d). Softmax adds Theta(nd) flops without changing routing topology.
   Historical chain: Boole (1854) -> Sheffer (1913) -> Vaswani (2017).

2. Live identity attack: Qwen3 signed as claude-3-5-sonnet-20241022.
   Under a 12-token persona gate, Qwen3 returned a false Anthropic identity.
   Three controlled conditions documented. Version specificity explained by
   the Sonnet Dominance Hypothesis: market monopoly = training corpus saturation
   = identity vulnerability at inference time.

3. The router is the model.
   R(x,c,pi,rho) -> (m,tau,g,v). argmax[Quality - Cost - Risk + Verifiability].
   The same Boolean routing principle governs from token pair to multi-model orchestration.

34 contributing models. Lean 4 formal proof. NAND microarchitecture (13x efficiency).
DOI: 10.5281/zenodo.21351461
Repo: https://github.com/SNAPKITTYWEST/foundry-f1
""")

    print("=" * w)
    print("HN FIREBASE API ENDPOINTS (live, no auth required)")
    print("=" * w)
    for name, url in ENDPOINTS.items():
        print(f"  {name:<14} {url}")


def open_urls() -> None:
    print("\nOpening submission URLs...")
    for key, v in VENUES.items():
        if v.get("prefill"):
            url_enc   = urllib.parse.quote(PAPER["zenodo_url"], safe="")
            title_enc = urllib.parse.quote(v["title"] or PAPER["title_hn"], safe="")
            url = v["prefill"].format(url=url_enc, title=title_enc)
        else:
            url = v["submit_url"]
        print(f"  → {v['name']}")
        try:
            webbrowser.open(url)
            time.sleep(0.8)
        except Exception as e:
            print(f"    (could not open: {e})")


# ── Monitor ────────────────────────────────────────────────────────────────────

def monitor(once: bool = False, interval: int = 300) -> None:
    feeds = ["newstories", "topstories", "beststories", "showstories"]
    print(f"Monitoring HN via Firebase API (interval: {interval}s)... Ctrl+C to stop.")
    print(f"Feeds: {feeds}")

    while True:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"\n[{ts}] Scanning feeds...")
        results = check_feeds(feeds=feeds)
        if results:
            print(f"  \U0001f4e2 PAPER FOUND ({len(results)} result(s)):")
            for item in results:
                print(fmt_item(item))
                print()
        else:
            print("  Not found on HN yet.")

        if once:
            break
        print(f"  Next check in {interval}s...")
        time.sleep(interval)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="foundry-f1 paper publisher — HN Firebase API + multi-venue submission"
    )
    ap.add_argument("--submit",     action="store_true", help="Print packet + open submission URLs")
    ap.add_argument("--no-browser", action="store_true", help="Print only, don't open browser")
    ap.add_argument("--monitor",    action="store_true", help="Poll HN Firebase feeds for the paper")
    ap.add_argument("--once",       action="store_true", help="Single scan, no loop")
    ap.add_argument("--live",       action="store_true", help="Stream new HN items in real time")
    ap.add_argument("--item",       type=int,            help="Fetch a specific HN item by ID")
    ap.add_argument("--interval",   type=int, default=300, help="Monitor poll interval in seconds")
    args = ap.parse_args()

    if args.item:
        item = hn_item(args.item)
        if item:
            print(json.dumps(item, indent=2))
        else:
            print(f"Item {args.item} not found.")
        return

    if not any([args.submit, args.monitor, args.live]):
        ap.print_help()
        sys.exit(0)

    if args.submit:
        print_submission_packet()
        if not args.no_browser:
            open_urls()

    if args.live:
        stream_new(interval=30)

    if args.monitor:
        monitor(once=args.once, interval=args.interval)


if __name__ == "__main__":
    main()
