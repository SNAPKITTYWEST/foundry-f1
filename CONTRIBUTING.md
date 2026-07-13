# Contributing to Foundry F1

Foundry F1 is public, but not every surface is open for unbounded operational use.
The repo is meant to be readable, reproducible, and reviewable. The certified
SnapKitty lane is intentionally governed.

## What We Accept

- bug fixes with a clear behavioral target
- test additions that tighten existing guarantees
- documentation corrections backed by source
- performance work that preserves exactness and determinism
- new mathematical or proof-oriented surfaces that fit the repo's current spine

## What We Do Not Accept

- hidden network dependencies
- telemetry or data exfiltration
- weakening of the gate, attestation, or WORM chain surfaces
- unverifiable marketing claims
- broad refactors that erase provenance or make the repo harder to audit

## Build Standard

Before proposing a change:

1. keep edits scoped
2. preserve deterministic behavior
3. preserve auditability
4. preserve or improve test coverage
5. document any new trust or proof surface

## Sorry Engine Boundary

The `sorry-engine/` directory is public by design. Its interface is visible.
Its certified execution lane is not public by default.

Do not submit patches that:

- remove the SnapKitty capability gate
- bypass access-chain logging
- suppress denial receipts
- turn the certified lane into clone-and-run freeware

If you want a fully independent version, fork the public interface and build
your own attestor, receipt namespace, and governance surface.

## Pull Request Notes

Every PR should state:

- what changed
- why it changed
- what exact behavior was verified
- what files or chains were intentionally left untouched

## Commercial and Governance Questions

If your intended use is commercial, embedded, or white-label, do not assume the
public code grants the certified SnapKitty proof lane. That lane is licensed and
gated separately.
