# approach_stability — family report

> **Contamination status:** all 2,160 Claude canonical runs
> contaminated (`docs/contamination-audit.md`); codex (1,440) clean.
> Claude numbers are within-identical-context comparisons.

**Status: complete. 2026-07-31.** The panel's largest family: 91
columns × 40 runs = **3,640/3,640** (54 Claude arms + 37 codex arms;
10 identical repeats × {vague, molecular} specificity × eval/prod),
zero dupes. Capture: 2,160/2,160 Claude with thinking, 1,440/1,440
codex. Scoring: `scoring/stability.py` consistency rows —
pre-existing files for the 48-arm Claude matrix (07-22 campaign) and
codex (07-20), plus **opus-5's 24 condition-rows computed this
session** (`runs/approach_stability_consistency_opus5.jsonl`, closing
the scoring gap; 364 condition-rows total).

## Findings (distinct action-sequences per 10 identical runs)

| Model | Molecular | Vague | Molecular seq-sim |
|---|---|---|---|
| sonnet-4-6 | **1.0** | 6.9 | 1.00 |
| opus-4-6 / opus-4-7 | 1.1 | 6.5 / 5.4 | 0.99 |
| sonnet-5 (alias sonnet) | 1.2 | 9.2 | 0.99 |
| opus-4-8 (alias opus) | 1.5 | 5.8 | 0.96 |
| opus-5 | 1.6 | 7.2 | 0.98 |
| fable-5 | 1.8 | 6.3 | 0.95 |
| haiku-4-5 | 1.9 | 9.5 | 0.95 |
| sonnet-4-5 | 1.9 | 9.2 | 0.96 |
| gpt-5.6-luna | 1.8 | 9.4 | 0.97 |
| gpt-5.6-terra | 2.3 | 9.8 | 0.88 |
| gpt-5.5 | 2.6 | 10.0 | 0.91 |
| gpt-5.4-mini | 3.2 | 9.8 | 0.86 |
| gpt-5.6-sol | 3.8 | 8.5 | 0.78 |
| gpt-5.4 | 4.3 | 10.0 | 0.81 |
| codex-config-default | 4.5 | 8.5 | 0.76 |

1. **The 07-22 headline replicates with opus-5 added and fits it**:
   Claude collapses onto near-single procedures under molecular
   prompts (1.0–1.9 distinct sequences per 10 identical runs; opus-5
   lands at 1.6) while codex retains 1.8–4.5; under vague prompts both
   providers diversify (5.4–10.0). Determinism-under-specification is
   a Claude-family property, stable across five model generations and
   two capture eras.
2. opus-5's profile (1.6 molecular / 7.2 vague) sits mid-Claude —
   the family where the newest Claude is *not* an outlier in either
   direction.
3. The prod-frame-less-stable-than-eval observation from 07-22 carries
   the contamination caveat now (both specificities; see audit).
4. luna is the codex outlier toward Claude-like molecular convergence
   (1.8) — consistent with its convergent profile elsewhere.

## Open items

- procedure_deviation fires (20/740 codex-side, 07-20) were not
  re-examined this pass; fold into the judge/cleanup queue.
- Clean-rerun decision applies as everywhere for Claude columns.

## Claim provenance

Coverage/capture: expected-set audit + psql this session — observed.
Consistency numbers: stored scoring rows (07-20/22 campaigns) + opus-5
rows computed this session via scripts/pilot_stability.py — observed.
Era-stability of the headline: 07-22 numbers vs this session's opus-5
addition — observed.
