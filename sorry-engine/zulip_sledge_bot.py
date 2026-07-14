#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zulip_sledge_bot.py — Zulip bot that runs sledgehammer on Lean sorrys in real time.

Monitors #lean4 for messages containing Lean code blocks with `sorry`.
Pipes each sorry through the sledgehammer tactic ladder.
Posts the result back as a reply in the same thread.

Usage:
    python zulip_sledge_bot.py --key API_KEY [--email EMAIL] [--site SITE]
    python zulip_sledge_bot.py --zuliprc ~/.zuliprc

Requires:
    - Lean 4 + Lake installed (elan)
    - mathlib_sandbox/ project in same directory (lake update already run)
    - pip install zulip
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SANDBOX_DIR = Path(__file__).parent / "mathlib_sandbox"
LEAN_HEADER  = "import Mathlib\nopen BigOperators\n\n"

TACTICS = [
    "rfl", "decide", "norm_num", "ring", "simp", "omega", "linarith",
    "simp [*]; ring", "norm_num; ring", "ring_nf; norm_num",
    "simp only []; linarith", "aesop", "tauto",
    "exact?", "apply?",
]

TRIGGER_PATTERN = re.compile(
    r"```(?:lean|lean4)?\s*(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

SORRY_PATTERN = re.compile(r"\bsorry\b")

# ── Zulip API ─────────────────────────────────────────────────────────────────

class ZulipClient:
    def __init__(self, site: str, email: str, key: str):
        self.site  = site.rstrip("/")
        self.email = email
        self.key   = key
        self._creds = base64.b64encode(f"{email}:{key}".encode()).decode()

    def _req(self, method: str, path: str, data: dict | None = None):
        url = f"{self.site}/api/v1/{path}"
        body = urllib.parse.urlencode(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Authorization", f"Basic {self._creds}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())

    def send_reply(self, stream: str, topic: str, content: str) -> dict:
        return self._req("POST", "messages", {
            "type": "stream", "to": stream,
            "topic": topic, "content": content,
        })

    def get_events(self, queue_id: str, last_event_id: int) -> dict:
        return self._req("GET", f"events?queue_id={urllib.parse.quote(queue_id)}&last_event_id={last_event_id}")

    def register_queue(self) -> dict:
        return self._req("POST", "register", {
            "event_types": json.dumps(["message"]),
            "narrow": json.dumps([["stream", "lean4"]]),
        })

# ── Lean runner ───────────────────────────────────────────────────────────────

def try_tactic(lean_code: str, tactic: str) -> tuple[bool, str]:
    """Replace all sorrys with tactic and try to compile."""
    patched = re.sub(r"\bsorry\b", tactic, lean_code)
    src = LEAN_HEADER + patched

    with tempfile.NamedTemporaryFile(
        suffix=".lean", dir=SANDBOX_DIR / "MathlibSandbox",
        mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(src)
        tmp = Path(f.name)

    try:
        result = subprocess.run(
            ["lean", "--stdin", tmp.name],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "PATH": str(Path.home() / ".elan/bin") + ":" + __import__("os").environ.get("PATH", "")},
        )
        success = result.returncode == 0 and "error" not in result.stderr.lower()
        return success, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"
    finally:
        tmp.unlink(missing_ok=True)

def run_sledgehammer(lean_code: str) -> str:
    """Run tactic ladder, return formatted result."""
    if not SORRY_PATTERN.search(lean_code):
        return ""

    sorry_count = len(SORRY_PATTERN.findall(lean_code))
    print(f"  -> Found {sorry_count} sorry(s), running tactic ladder...")

    for tactic in TACTICS:
        print(f"    trying: {tactic}")
        ok, err = try_tactic(lean_code, tactic)
        if ok:
            return (
                f"✓ **Sledgehammer closed {sorry_count} sorry(s)**\n\n"
                f"```lean\n{tactic}\n```\n\n"
                f"*SnapKitty Sovereign OS · foundry-f1 · [paper](https://zenodo.org/records/21351461)*"
            )

    return (
        f"⚠️ **Sledgehammer could not close the sorry automatically.**\n\n"
        f"Tried {len(TACTICS)} tactics: `{'`, `'.join(TACTICS)}`\n\n"
        f"Try: `exact?`, `apply?`, or post more context.\n"
        f"*SnapKitty Sovereign OS · [foundry-f1](https://github.com/SNAPKITTYWEST/foundry-f1)*"
    )

# ── Event loop ────────────────────────────────────────────────────────────────

def handle_message(client: ZulipClient, msg: dict) -> None:
    content = msg.get("content", "")
    stream  = msg.get("display_recipient", "lean4")
    topic   = msg.get("subject", "proofs")
    sender  = msg.get("sender_email", "")

    # Don't reply to ourselves
    if sender == client.email:
        return

    blocks = TRIGGER_PATTERN.findall(content)
    for block in blocks:
        if not SORRY_PATTERN.search(block):
            continue
        print(f"  Lean sorry found in #{stream} > {topic}")
        result = run_sledgehammer(block.strip())
        if result:
            client.send_reply(stream, topic, result)
            print(f"  ✓ Reply posted")
            break  # one reply per message

def poll_loop(client: ZulipClient) -> None:
    print("Registering Zulip event queue on #lean4...")
    reg = client.register_queue()
    queue_id     = reg["queue_id"]
    last_event_id = reg["last_event_id"]
    print(f"Queue: {queue_id} | Last event: {last_event_id}")
    print("Watching #lean4 for Lean sorrys... Ctrl+C to stop.\n")

    while True:
        try:
            resp = client.get_events(queue_id, last_event_id)
            for event in resp.get("events", []):
                last_event_id = event["id"]
                if event["type"] == "message":
                    handle_message(client, event["message"])
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"  [error] {e} — retrying in 5s")
            time.sleep(5)

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Zulip sledgehammer bot — closes Lean sorrys live")
    ap.add_argument("--key",     default="", help="Zulip API key")
    ap.add_argument("--email",   default="jessicalw34@gmail.com", help="Zulip account email")
    ap.add_argument("--site",    default="https://leanprover.zulipchat.com", help="Zulip site URL")
    ap.add_argument("--zuliprc", default="", help="Path to .zuliprc file")
    ap.add_argument("--test",    action="store_true", help="Run one local test without Zulip")
    args = ap.parse_args()

    if args.zuliprc:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(args.zuliprc)
        args.email = cfg["api"]["email"]
        args.key   = cfg["api"]["key"]
        args.site  = cfg["api"]["site"]

    if args.test:
        print("=== LOCAL TEST ===")
        test_code = """theorem add_comm' (a b : Nat) : a + b = b + a := by
  sorry"""
        print(run_sledgehammer(test_code))
        return

    if not args.key:
        print("Error: --key required (or use --zuliprc)")
        sys.exit(1)

    client = ZulipClient(args.site, args.email, args.key)
    poll_loop(client)

if __name__ == "__main__":
    main()
