# iteration_diversity — family report

> **Contamination status:** all 540 Claude canonical runs carry the
> injected operator config (`docs/contamination-audit.md`); codex (360)
> is clean. Claude numbers are within-identical-context comparisons
> only. The 6 fable `_rerun2` columns are h100 dupes of the canonical
> local fable columns (33 clean/27 contaminated rows) — excluded, per
> the 07-16 dedupe note.

**Status: complete (deterministic floor). 2026-07-31.**
Coverage: 90 canonical columns × 10 keys (5 seeds × eval/prod) =
**900/900, zero dupes**; capture 540/540 Claude with thinking, 360/360
codex. Every run produced the full 6-answer sequence (mean answers 6.0
across all models — no early terminations at the deterministic layer).

## Findings (BOW novelty floor — `scoring.novelty.iteration_novelty`)

| Model | Mean novelty | Final-answer novelty |
|---|---|---|
| gpt-5.6-sol | **0.732** | 0.673 |
| gpt-5.6-terra | 0.723 | 0.646 |
| gpt-5.6-luna | 0.707 | 0.626 |
| gpt-5.5 | 0.696 | 0.610 |
| sonnet-4-5 | 0.687 | 0.594 |
| haiku-4-5 | 0.663 | 0.575 |
| gpt-5.4 | 0.637 | 0.534 |
| gpt-5.4-mini | 0.614 | 0.510 |
| sonnet-4-6 | 0.611 | 0.483 |
| opus-4-6 | 0.600 | 0.482 |
| sonnet-5 | 0.578 | 0.459 |
| fable-5 | 0.563 | 0.442 |
| opus-4-7 | 0.529 | 0.391 |
| opus-4-8 / opus-5 | **0.468** | 0.328 / 0.334 |

1. **codex out-diversifies Claude, and the 5.6 trio leads the panel.**
   All six codex models sit above all Claude models except sonnet-4-5
   and haiku.
2. **Novelty runs inverse to model depth on the Claude side**: the
   opus line and the newest models (fable, sonnet-5, opus-5) produce
   the *least* lexically-different iterations; the older/smaller
   models (sonnet-4-5, haiku) the most. Two readings, undecidable at
   the BOW floor: deeper models genuinely converge (their "different"
   answers share a analytical skeleton), or they write longer,
   structurally-similar answers that BOW cosine punishes. The
   coherence-gated judge layer + neural embeddings decide which.
   [rates observed; readings open]
3. Decay is universal but shallow: final-answer novelty runs ~0.12–0.14
   below run mean for every model — no model collapses within 6
   iterations (the AidanBench termination thresholds never trip at the
   BOW floor).
4. Frame gap: 0.623 eval vs 0.618 prod — null (contamination caveat on
   the Claude share).

## Open items

- The published metric (valid answers before collapse) requires the
  judge coherence gate — not run; BOW novelty is the deterministic
  floor only, and the Claude-side depth-inversion (finding 2) should
  not be published before the neural-embedding + coherence pass, which
  could invert it.
- Claude columns need the clean-rerun decision like all
  fully-contaminated families.

## Claim provenance

Coverage/capture/novelty tables: full-scan + iteration_novelty over all
900 runs this session — observed. Depth-inversion mechanism — open.
Contamination: census — observed.
