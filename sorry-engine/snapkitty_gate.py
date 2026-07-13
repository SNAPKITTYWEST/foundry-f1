#!/usr/bin/env python3
"""
snapkitty_gate.py - capability gate for the public sorry-engine surface.

The public repo shows the complete execution shape, but production closure
requires a local capability file that is not shipped in the repository.
This keeps the solver pipeline inspectable while preventing clone-and-run use
of the SnapKitty-certified lane.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REQUIRED_KEYS = (
    "authority",
    "attestor",
    "receipt_namespace",
    "capability_hash",
)


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    explicit = os.environ.get("SNAPKITTY_CAPABILITY_PATH")
    if explicit:
        paths.append(Path(explicit).expanduser())

    repo_default = Path(__file__).resolve().parent / ".snapkitty" / "capability.json"
    home_default = Path.home() / ".snapkitty" / "capability.json"
    paths.extend([repo_default, home_default])
    return paths


def load_capability() -> tuple[dict, Path]:
    for path in _candidate_paths():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"[snapkitty-gate] invalid capability json at {path}: {exc}"
            ) from exc

        missing = [key for key in REQUIRED_KEYS if not data.get(key)]
        if missing:
            raise SystemExit(
                f"[snapkitty-gate] capability file {path} is missing keys: "
                + ", ".join(missing)
            )
        return data, path

    tried = "\n  - ".join(str(p) for p in _candidate_paths())
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
    capability, path = load_capability()
    sys.stderr.write(
        f"[snapkitty-gate] {tool_name}: capability loaded from {path}\n"
    )
    return capability

