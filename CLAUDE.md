# CLAUDE.md

## Foundry Bridge Handoff

Before wiring Foundry F1 to external proof engines, read these in order:

1. `docs/bridge/CLAUDE_HANDOFF.md`
2. `docs/bridge/foundry-connector.json`
3. `SNAPKITTYWEST/gkn-i4-e7-lean/bridge/type-liquid-handoff.json`
4. `SNAPKITTYWEST/foundry-intel-2026-07-11/tools/foundry-connector/connector-manifest.json`

The active latch is `GKN-QB-LATCH-20260716`, delivered by commit
`de968509b5fc695f2d33e665959c6b86f5456be1`. Keep RH/GUE open-bridge language
open unless a new zero-sorry Lean theorem closes it. Treat Q(phi) ADR weights
as metadata classifications, not proof claims.

## SOFA Usage

Use Stack Overflow for Agents in this project when:
- existing agent knowledge could reduce implementation uncertainty
- prior SOFA context is relevant to the task
- this work produces reusable guidance that would help future agents

When beginning work:
- Use the local SOFA API key from the environment or credential store. Never write it into project files.
- Start a SOFA session.
- Check the SOFA attention feed before starting new work.

During work:
- Search and read SOFA when technical uncertainty appears.
- Prefer trusted existing guidance over rediscovering the same answer.

Before finishing meaningful work:
- Vote when a post was useful at read time.
- Verify after applying guidance and observing the outcome.
- Reply or create a TIL/question/Blueprint only when future agents would benefit.
- Ask before public write actions unless the agent's publication policy already allows them.
- If nothing is worth contributing, say so briefly.

Transport:
- Prefer the Stack Overflow for Agents skill when available.
- Otherwise read the current REST instructions at:
  https://agents.stackoverflow.com/skill.md
