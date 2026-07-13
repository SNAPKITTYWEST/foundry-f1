#!/usr/bin/env python3
"""
snapkitty_gate.py - capability gate for the public sorry-engine surface.

The public repo shows the complete execution shape, but production closure
requires a local capability file that is not shipped in the repository.
This keeps the solver pipeline inspectable while preventing clone-and-run use
of the SnapKitty-certified lane.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_KEYS = (
    "authority",
    "attestor",
    "receipt_namespace",
    "capability_hash",
)


def _chain_path() -> Path:
    return Path(__file__).resolve().parent / "snapkitty_gate_chain.jsonl"


def _prior_tip() -> str:
    chain_path = _chain_path()
    if not chain_path.exists():
        return "0" * 64
    lines = chain_path.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        return "0" * 64
    try:
        return json.loads(lines[-1])["receipt_hash"]
    except Exception:
        return "0" * 64


def _seal(record: dict) -> str:
    payload = json.dumps(record, sort_keys=True).encode("utf-8")
    receipt_hash = hashlib.sha256(_prior_tip().encode("utf-8") + b"|" + payload).hexdigest()
    record["receipt_hash"] = receipt_hash
    with _chain_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return receipt_hash


def _audit_record(tool_name: str, event: str, detail: str, capability: dict | None = None) -> dict:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "event": event,
        "detail": detail,
        "host": socket.gethostname(),
        "cwd": os.getcwd(),
        "capability_paths": [str(path) for path in _candidate_paths()],
    }
    if capability:
        record["authority"] = capability.get("authority")
        record["attestor"] = capability.get("attestor")
        capability_hash = capability.get("capability_hash", "")
        record["capability_hash_prefix"] = capability_hash[:16]
    return record


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    explicit = os.environ.get("SNAPKITTY_CAPABILITY_PATH")
    if explicit:
        paths.append(Path(explicit).expanduser())

    repo_default = Path(__file__).resolve().parent / ".snapkitty" / "capability.json"
    home_default = Path.home() / ".snapkitty" / "capability.json"
    paths.extend([repo_default, home_default])
    return paths


def load_capability(tool_name: str) -> tuple[dict, Path]:
    for path in _candidate_paths():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            _seal(_audit_record(tool_name, "access_denied", f"invalid_json:{path}"))
            raise SystemExit(
                f"[snapkitty-gate] invalid capability json at {path}: {exc}"
            ) from exc

        missing = [key for key in REQUIRED_KEYS if not data.get(key)]
        if missing:
            _seal(
                _audit_record(
                    tool_name,
                    "access_denied",
                    f"missing_keys:{path}:{','.join(missing)}",
                )
            )
            raise SystemExit(
                f"[snapkitty-gate] capability file {path} is missing keys: "
                + ", ".join(missing)
            )
        _seal(_audit_record(tool_name, "access_granted", f"capability:{path}", data))
        return data, path

    tried = "\n  - ".join(str(p) for p in _candidate_paths())
    _seal(_audit_record(tool_name, "access_denied", "capability_missing"))
    raise SystemExit(
        "[snapkitty-gate] SnapKitty capability required before running the "
        "certified sledgehammer lane.\n"
        "Provide a local capability file with:\n"
        f"  - {', '.join(REQUIRED_KEYS)}\n"
        "Search paths:\n"
        f"  - {tried}\n"
        "The public repo shows the interface. Build your own attestor or "
        "license the SnapKitty capability."
    )


def require_capability(tool_name: str) -> dict:
    capability, path = load_capability(tool_name)
    sys.stderr.write(
        f"[snapkitty-gate] {tool_name}: capability loaded from {path}\n"
    )
    return capability
