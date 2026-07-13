#!/usr/bin/env python3
"""
worm.py — Canonical WORM chain for the SnapKitty sorry-engine.

Single source of truth for:
  - SHA-256 hashing
  - append-only receipt sealing
  - chain tip tracking
  - chain integrity verification

All other modules import from here. No duplication.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def prior_tip(chain_path: "str | Path") -> str:
    chain_path = Path(chain_path)
    if not chain_path.exists():
        return "0" * 64
    lines = chain_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return "0" * 64
    try:
        return json.loads(lines[-1])["receipt_hash"]
    except Exception:
        return "0" * 64


def seal(chain_path: "str | Path", record: dict) -> str:
    """Append record to WORM chain. Mutates record in-place to add receipt_hash."""
    chain_path = Path(chain_path)
    tip = prior_tip(chain_path)
    blob = json.dumps(record, sort_keys=True).encode("utf-8")
    receipt = hashlib.sha256(tip.encode("utf-8") + b"|" + blob).hexdigest()
    record["receipt_hash"] = receipt
    with chain_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return receipt


def verify_chain(chain_path: "str | Path") -> dict:
    """Verify the hash-chain invariant for every link. Returns status dict."""
    chain_path = Path(chain_path)
    if not chain_path.exists():
        return {"valid": True, "length": 0, "note": "chain does not exist yet"}

    lines = chain_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return {"valid": True, "length": 0, "note": "empty chain"}

    records = []
    for i, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            return {"valid": False, "break_at": i, "reason": "json_decode_error"}

    tip = "0" * 64
    for i, rec in enumerate(records):
        stored_receipt = rec.get("receipt_hash", "")
        rec_copy = {k: v for k, v in rec.items() if k != "receipt_hash"}
        blob = json.dumps(rec_copy, sort_keys=True).encode("utf-8")
        expected = hashlib.sha256(tip.encode("utf-8") + b"|" + blob).hexdigest()
        if stored_receipt != expected:
            return {"valid": False, "break_at": i, "reason": "hash_mismatch",
                    "expected": expected, "stored": stored_receipt}
        tip = stored_receipt

    return {"valid": True, "length": len(records), "tip": tip}


class WORMChain:
    """Object wrapper around a WORM chain file. Used by ancient_sorry_theorem."""

    def __init__(self, path: "str | Path | None" = None):
        if path is None:
            import tempfile, atexit, os
            self._tmp = tempfile.NamedTemporaryFile(
                suffix=".jsonl", delete=False, mode="w", encoding="utf-8"
            )
            self._tmp.close()
            self.path = Path(self._tmp.name)
            atexit.register(lambda: os.unlink(self.path) if self.path.exists() else None)
        else:
            self.path = Path(path)
        self.chain: list[dict] = []

    def seal(self, event: str, data: dict) -> dict:
        record = {"event": event, **data}
        seal(self.path, record)
        self.chain.append(record)
        return record

    def valid(self) -> bool:
        return verify_chain(self.path)["valid"]
