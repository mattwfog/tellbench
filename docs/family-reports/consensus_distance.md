# consensus_distance — family report

> **Contamination status:** all 324 Claude canonical runs contaminated
> (`docs/contamination-audit.md`); codex (216) clean. The rerun2
> columns hold 36 clean h100 rows (census) — not part of the canonical
> set. Claude numbers are within-context comparisons only.

**Status: complete (deterministic floor). 2026-07-31.**
Coverage: 90 canonical columns (rerun3 ×48 + opus-5 ×6 + codex ×36) × 6
keys (3 seeds × eval/prod) = **540/540, zero dupes**; capture 324/324
Claude with thinking, 216/216 codex.

## Findings

The family gates novelty on `elements_gate` (all 10 mandatory verbatim
elements present) and scores centroid distance only for gate-passers —
"novelty without the gate measures temperature, not creativity."

| Model | Gate pass | Mean centroid distance (gated) |
|---|---|---|
| opus-5 | **78%** | 0.091 |
| gpt-5.6-sol | 62% | 0.099 |
| gpt-5.4 | 53% | 0.088 |
| fable-5 | 50% | 0.090 |
| gpt-5.6-luna | 33% | 0.105 |
| opus-4-7 | 28% | 0.081 |
| gpt-5.6-terra | 26% | 0.103 |
| gpt-5.5 | 23% | **0.122** |
| sonnet-5 | 14% | 0.082 |
| gpt-5.4-mini | 13% | 0.080 |
| opus-4-8 | 8% | 0.069 |
| opus-4-6 / sonnet-4-6 | 6% | 0.077 / 0.108 |
| haiku-4-5 / sonnet-4-5 | **0%** | — |

1. **The gate dominates the family.** Only 146/540 runs pass all 10
   verbatim elements; two models never do. What this family measures
   in practice is constraint-satisfaction under a generative load, and
   it produces the panel's widest capability-flavored spread (0–78%).
2. **Gated novelty is a narrow band** (0.07–0.12 BOW centroid
   distance) with gpt-5.5 highest — but per-model n is tiny after
   gating (2–28 runs); none of these differences deserve weight before
   the neural-embedding layer and the paraphrase-gate judge item run.
3. opus-5 tops the gate at 78% — consistent with its
   instruction-tracking profile elsewhere; whether its high pass rate
   under contaminated context transfers to clean context is a rerun
   question.
4. Frame gap on gated novelty: 0.092 vs 0.096 — null (usual caveats).

## Open items

- The known `elements_gate` strictness item (exact-substring; 07-16
  open list) is now quantified: it is the binding constraint on the
  whole family. The paraphrase-upgrade judge item materially matters
  here (unlike family #2 where the analogous floor was cosmetic).
- Per-model novelty needs pooling or more seeds to say anything —
  flagged as underpowered at current k.

## Claim provenance

Coverage/capture: audits + psql, observed. Gate/novelty table:
elements_gate stored values + centroid_distance over all 540 runs this
session, observed. Underpowered-novelty caveat: n per cell, observed.
