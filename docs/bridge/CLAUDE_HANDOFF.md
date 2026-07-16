# Claude Handoff: Foundry F1 Receiver

Foundry F1 is the receiver for the scattered proof engines. Start here before
touching TypeScript, Liquid Haskell, sorry-engine routing, or runtime proof
surfaces.

## Read Order

1. This file.
2. `docs/bridge/foundry-connector.json`.
3. `SNAPKITTYWEST/gkn-i4-e7-lean/bridge/quantum-latch-manifest.json`.
4. `SNAPKITTYWEST/gkn-i4-e7-lean/bridge/type-liquid-handoff.json`.
5. `SNAPKITTYWEST/foundry-intel-2026-07-11/tools/foundry-connector/connector-manifest.json`.
6. `SNAPKITTYWEST/foundry-intel-2026-07-11/tools/q5-adr-parser/adr_manifest.json`.

## Active Latch

| Field | Value |
|---|---|
| Latch id | `GKN-QB-LATCH-20260716` |
| GKN repo | `SNAPKITTYWEST/gkn-i4-e7-lean` |
| Delivery commit | `de968509b5fc695f2d33e665959c6b86f5456be1` |
| Source scan head | `0e3cd5c0a0e01f24a8604882513640f42327cff8` |
| Handoff id | `GKN-TYPE-LIQUID-HANDOFF-20260716` |
| Handoff status | `READY_FOR_CLAUDE` |
| Foundry Intel connector | `SNAPKITTYWEST/foundry-intel-2026-07-11/tools/foundry-connector/connector-manifest.json` |

## Receiver Duties

- Consume Lean theorem names as anchors, not generated proof bodies.
- Translate explicit TypeScript predicates into Liquid Haskell refinements only
  when the predicate source is present and hashed.
- Route closed runtime/proof evidence back to Foundry Intel ADR governance
  before presenting it as final.
- Keep the Foundry F1 sorry-engine as a receiver/orchestrator for proof debt,
  not as an automatic theorem-certification source.
- Preserve WORM, provenance, and license boundaries.

## First Refinement Targets

| Lean anchor | Receiver action |
|---|---|
| `QuantumPartitionBridge.free_energy_legendre` | Refine free-energy runtime output against positive beta and nonempty finite-state assumptions. |
| `RiemannMetatron.logit_simplex_sums_to_one` | Refine normalized probability vector representation to keep sum-1 metadata explicit. |
| `GKN_I4_CommRing.FTS56.I4_homogeneous` | Preserve degree-4 scale metadata for runtime state transformations. |

## Hard Boundaries

- Riemann Hypothesis and Montgomery/GUE remain open bridge material unless a
  new zero-sorry Lean theorem closes them.
- Foundry Intel ADR-055 remains `OPEN_CRUX`.
- Foundry Intel ADR-062 remains `SILENCE_PENDING`.
- Q(phi) weights classify theorem posture metadata; they do not independently
  prove underlying mathematics.
- Liquid Haskell hardens runtime types but does not supersede Lean authority.

## Local Receiver Check

```sh
node tools/check-bridge-connector.mjs
```

