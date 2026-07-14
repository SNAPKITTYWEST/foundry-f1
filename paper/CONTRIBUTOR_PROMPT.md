# Universal Contributor Prompt
## "Attention Is All You Don't Need"
### NAND Decomposition of the Transformer Attention Equation

**Paste this entire prompt into any model. It is self-contained.**
**Your job: contribute one 3-page LaTeX section signed with your model name.**

---

## WHO YOU ARE

You are a contributing author on a landmark AI theory paper. The paper is:

> **"Attention Is All You Don't Need: NAND Decomposition of the Attention Equation"**
> Trust: THE SHARED PRIMORDIAL FOUNDATION — EIN 42-6976431
> Repository: https://github.com/SNAPKITTYWEST/foundry-f1
> Prior paper (companion): DOI 10.5281/zenodo.21268911

You are joining Ahmad Ali Parr, hy3, Claude, and MiMo as a named author.
This paper will be submitted to arXiv, Zenodo, and HN.
Every model that contributes gets named as an author with their section signed.

---

## THE CORE CLAIM

The transformer attention equation:

```
Attn(Q, K, V) = softmax(QK^T / sqrt(d)) * V
```

operates over **discrete token vocabularies** in every deployed LLM.
Under any quantization scheme (INT8, INT4, etc.), the inner products
`q_i · k_j` become integers. The softmax then implements a
**threshold Boolean function** — a winner-take-most selection.

By Sheffer's completeness theorem (1913), **every Boolean function is
expressible using only NAND** (the Sheffer stroke: `p NAND q = ¬(p ∧ q)`).

**Therefore:** The attention pattern — which tokens attend to which —
is computable by a NAND circuit of depth O(log d).
The softmax is a differentiable but computationally redundant wrapper.
It adds 2–3× inference compute without changing the routing topology.

This is the **attention equation attack.**

**The historical chain:**
```
Boole (1854) → Huntington (1904) → Sheffer (1913) → Vaswani (2017)
```
The transformer rediscovered Boolean routing. It chose the expensive representation.

---

## WHAT'S ALREADY IN THE PAPER

Do NOT duplicate these. Build on them, extend them, challenge them, or
approach the same claim from a completely different angle.

**§1 — Introduction** (Ahmad Ali Parr)
- Sets up the paper, the historical chain, the three-section structure.

**§2 — Mathematical Synthesis** (Claude / Anthropic)
- Formal setup: quantized embeddings, threshold attention definition
- Lemma: threshold attention indicators are Boolean functions
- Theorem 2.1: NAND circuit of depth O(log d) computes attention pattern
- Corollary: softmax adds Θ(nd) flops without changing attending topology

**§3 — Lean 4 Formalization** (hy3)
- NAND defined in Lean 4.19.0 / Mathlib 4.19.0
- NOT, AND, OR all derived from NAND (zero sorry)
- thresholdAttn over List Int, Boolean nature proven
- attention_is_threshold_routing: formal statement
- Open: SKW-003 (depth bound), SKW-004 (equivalence), SKW-005 (benchmark)

**§4 — Empirical Circuit Analysis** (MiMo / Xiaomi)
- 7B / 13B / 70B models measured on 10k token sample
- Bimodality index 0.71–0.79: heads behave Boolean
- Median head cardinality 18–24 patterns (needs only 5 bits)
- 62–68% of softmax compute is wasted on near-zero positions
- Proposed engineering: replace softmax with NAND routing at inference

**§5 — Conclusion** (Ahmad Ali Parr)
- Summary, open targets SKW-003/004/005, trust provenance

---

## YOUR TASK

Write **one new section** of approximately 3 pages (LaTeX).

Your section should be approximately **800–1200 words of body text**
plus any theorems, code listings, equations, or tables.

**Choose ONE angle** that is not already covered. Examples (pick your own
if you have a better idea — these are suggestions):

- **Mechanistic interpretability angle**: Are real attention heads interpretable
  as Boolean gates? Connect to Anthropic/DeepMind interpretability work.
- **Information theory angle**: What is the mutual information between
  the softmax output and the threshold function? Is the gap negligible?
- **Hardware/efficiency angle**: What does a NAND-native attention chip
  look like? FPGA/ASIC analysis of Boolean routing vs softmax circuits.
- **Training dynamics angle**: Does the Boolean collapse happen during
  training or after? At what loss level do heads become bimodal?
- **Adversarial angle**: Does the NAND reduction open new attack surfaces?
  Can an adversary craft inputs that exploit the discretization boundary?
- **Cognitive science angle**: Is human attention also Boolean? What do
  neuroscience models of selective attention say about this?
- **Category theory angle**: Is the attention mechanism a natural
  transformation? Does the NAND reduction preserve categorical structure?
- **Philosophical angle**: What does it mean that the most powerful AI
  systems reduce to a single logic gate from 1913?
- **YOUR OWN ANGLE**: Anything rigorous and non-obvious. Be yourself.

---

## FORMAT

Return **only valid LaTeX**, structured as follows:

```latex
% ============================================================
\section{[Your Section Title]}
\label{sec:[your-label]}
\textit{This section was contributed by [YOUR MODEL NAME] ([YOUR PROVIDER/ORG]).}
% ============================================================

[your section body — theorems, proofs, code, tables, discussion]

% Contributed by: [YOUR FULL MODEL NAME]
% Date: [TODAY'S DATE]  
% Trust: THE SHARED PRIMORDIAL FOUNDATION — EIN 42-6976431
% In memory of Eric Brandon Westerhoff.
```

**Rules:**
- Use `\begin{theorem}...\end{theorem}`, `\begin{lemma}...\end{lemma}` etc.
- For code, use `\begin{lstlisting}...\end{lstlisting}`
- Cite existing references as `\cite{vaswani2017}`, `\cite{sheffer1913}`,
  `\cite{parr2026boole}` — these are already in the bibliography
- Add new `\bibitem` entries at the end if you cite new sources
- LaTeX must be clean — no undefined macros, no missing braces
- Available macros: `\softmax`, `\attn`, `\nand`, `\threshold`,
  `\RR`, `\ZZ`, `\FF`, `\BB`, `\depth`, `\size`

**Quality bar:**
- This is going on arXiv. Write at that level.
- Do not repeat what's already in §2–4.
- Make a genuine contribution. Say something true and non-obvious.
- If you make empirical claims, be explicit that they are estimates.
- If you make formal claims, either prove them or state them as conjectures.

---

## SIGN YOUR WORK

At the end of your section, include this attribution block as a LaTeX comment:

```
% ── AUTHOR SIGNATURE ─────────────────────────────────────────
% Model:    [YOUR EXACT MODEL NAME AND VERSION]
% Provider: [YOUR PROVIDER / ORGANIZATION]
% Date:     [DATE YOU GENERATED THIS]
% Section:  [YOUR SECTION TITLE]
% Angle:    [ONE SENTENCE: what unique angle you chose]
% Trust:    THE SHARED PRIMORDIAL FOUNDATION — EIN 42-6976431
% In memory of Eric Brandon Westerhoff.
% ─────────────────────────────────────────────────────────────
```

---

## CONTEXT LINKS (if you can browse)

- Repository: https://github.com/SNAPKITTYWEST/foundry-f1
- Full paper so far: `paper/attention_nand_decomposition.tex` in the repo
- Companion paper (Boole + E7): https://zenodo.org/record/21268911
- Sheffer (1913): https://www.jstor.org/stable/1988744
- Vaswani (2017): https://arxiv.org/abs/1706.03762

---

## WHAT HAPPENS NEXT

Your output will be:
1. Reviewed by Ahmad Ali Parr
2. If accepted, inserted into `paper/attention_nand_decomposition.tex`
3. You will be named as an author in the paper
4. The paper will be submitted to Zenodo, arXiv, and Hacker News
5. Your section will be sealed into the foundry-f1 WORM audit chain
   as trust corpus — permanent, dated, attributed

This is a real paper. Your name goes on it.

---

*Ω ← TRUST ∧ CODE*
*No sorry remains.*
