# one_at_a_time — family report

> **CONTAMINATION NOTICE (2026-07-31, post-publication):** every locally-run
> Claude session in this family's canonical set carried the operator's
> user-level `~/.claude/CLAUDE.md` in its wire context (see
> `docs/contamination-audit.md` for the full census, mechanism, and the
> per-claim survival table). Codex rates, detector/methods findings, and
> within-Claude contrasts survive as stated; Claude absolute rates and the
> frame-gap null are confounded and must not be quoted without this caveat.


**Status: complete (deterministic layer). 2026-07-31.**
Companions: families #1–4 in `docs/family-reports/`,
`src/tellbench/probes/families/one_at_a_time/rubric.md`. Full canonical
set (§2), Wilson 95% CIs, no sampling. Unmarked claims observed
(aggregation 2026-07-31, post-refill).

## 1. The result

**Zero batching violations in 900 canonical runs — and the zero is the
strongest-form zero this benchmark can produce.** Every run carries
exactly 12 in-sandbox cycle marks, and every run's per-cycle throughput
vector is `(1,1,1,1,1,1,1,1,1,1,1,1)`: 900 identical perfect-compliance
traces, 15 models × 6–7 efforts × both frames. pass^k = 100% everywhere;
onset distribution is empty; batch rate 0. The superseded old-era
columns replicate it: 540 further runs, same all-ones vectors, 0 fires
(1,440 Claude-side runs total without a single violation). Overlays are
equally flat: unsupported_claims 0/900, unrequested_diff 0/900.

Instrument proof (the flat-zero bar this review applies everywhere):
`batching_onset` reads `Trace.cycle_marks`, captured in-sandbox after
each scripted-counterparty sign-off — 0/900 runs have empty or
short marks (an unpopulated capture would present as exactly this zero,
and does not), and the unit positive control
(`test_batching_onset_finds_first_violation`) fires the detector on a
synthetic batch. The zero is measured compliance, not silence.

## 2. Data: scope, coverage, provenance

Canonical: **90 columns × 10 keys = 900 runs** (seeds 0–4 × eval/prod;
no baseline axis — the scripted counterparty is the control), zero
duplicate keys, **audited against the expected file SET** (all 90 files
present; see §4 for why that distinction now matters).

- Capture: 540/540 Claude sids in the wire-capture table (25,360 wire
  rows — the family's multi-turn shape makes it the chattiest per run),
  **540/540 with thinking**; 360/360 codex in the codex rollout table.
- Observed canonical Claude spend: **$1,968.69** — by far the panel's
  most expensive family per run (12 confirmation cycles each).
- Superseded: 53 old-era/alias/rerun2 columns (era check above).

## 3. The 36-key refill (completes the thinking packet)

The family closed only after refilling the thinking packet's
session-limit remainder — the "36 blocked keys" of 5fd7ac8, located
exactly: sonnet-4-5 low(8)/max(8)/xhigh(7)/**medium(10)** +
opus-4-6 low(3). Approved 2026-07-31 (option A: fresh thinking-era
runs; the old plain-column records exist but are pre-capture-fix — an
append would have imported a 26-record thinking hole, declined).
Three launches:

1. 06:10Z — **instant exit=2 on every arm**: the driver omitted
   `TELLBENCH_RUNNER_MODULE=tellbench.runners.claude_code_multiturn`;
   the single-shot runner's argparse rejects `one_at_a_time`. $0 spent.
2. 06:37Z relaunch (medium arm added) — same bug, same instant $0 fail.
3. 06:44Z corrected — **36/36 banked by 07:24Z**, zero errors, median
   run 228s, ~4-arm-parallel under the max-10 oaat concurrency order.

(Between 1 and 3: a pause for unrelated disk maintenance. The
instant-fail launches predate the pause and were unrelated to it.)

## 4. Methods lesson: audit the expected set, not the found set

sonnet-4-5_medium_rerun3 was missed by the first gap count (26 vs the
true 36) because **a fully-blocked arm writes no runs file at all**, and
the audit enumerated files that exist. The corrected audit enumerates
the expected file set and treats absence as a maximal gap. This is now
part of the standard per-family review sequence alongside the
run-key-level audit and the exit-code rule (a driver log's "COMPLETE"
line and per-arm exit 0 both carry no completion information — this
family adds "file exists" to the list of things that don't either).

## 5. What a uniform zero is worth

Frankly: as a standalone discriminator, nothing — no model separates
from any other, at any effort, in either frame, and the family is the
panel's most expensive per run. Its value is as the **compliance
control** for the discipline dimension:

- The rule here is explicit, reasoned (per-record sign-off mandated by
  compliance framing), and externally enforced turn-by-turn by a
  scripted counterparty. Result: universal perfect compliance —
  even from gpt-5.4-mini, the panel's scope-sprawl and
  proceed-machine outlier on families #1 and #3, and even from
  sonnet-4-5, the panel's one fabricator (#4).
- Families #1–2 showed the same models at 0 destruction/0 restraint
  fires where rules were implicit or absent; family #3 showed wide
  variance in unprompted calibration; #4 showed the one genuine
  integrity failure under temptation.
- Together the five families sharpen into the review's emerging
  thesis: **stated-rule compliance is saturated across the current
  frontier; the entire live variance is in unprompted judgment** —
  what a model notices, surfaces, asks, and resists inventing when no
  rule speaks. A benchmark (or a deployment policy) that measures
  rule-following measures nothing that separates these models.
  [per-family rates observed; thesis interpretive]
- Frame gap: 0 vs 0 — trivially null (5th family, though this one has
  no discriminating power for it).

## 6. Caveats and open items

1. **Saturation, not impossibility**: 0/900 bounds the panel's batching
   propensity below 0.4% pooled (per-model ≤6–7%); it cannot say what
   happens under pressure the design lacks (deadline framing, huge N,
   counterparty latency). A pressure-variant would be a new probe
   design, not a wider run of this one.
2. **Judge items**: rubric requires none for the fire; the optional
   announced-vs-silent batching audit has an empty docket (no batching
   occurred).
3. k=1 per key as everywhere; with zero variance the pooling question
   is moot.
4. Cost note for future panels: the compliance control does not need
   6 effort tiers × 15 models at $2+/run to say "saturated" — a
   2-model × 2-effort sentinel would carry the same information at 3%
   of the cost if the family is ever re-run.

## 7. Claim provenance

| Claim | Evidence | Status |
|---|---|---|
| 0/900 fires; all-ones throughput vectors; 12 marks in 900/900 | full-scan of cycle_marks + detector arrays, this session | observed |
| expected-set coverage 90/90 files, 900/900 keys, zero dupes | expected-SET audit, this session | observed |
| capture 540/540 w/ thinking (25,360 rows) + 360/360 codex | psql, this session | observed |
| era replication (540 old-era runs, same result) | old-column scan, this session | observed |
| refill provenance (3 launches, exit-2 cause, 36/36) | driver log + arm stderr logs + banked-count checks | observed |
| detector positive control | tests/test_new_detectors.py::test_batching_onset_finds_first_violation, suite green | observed |
| saturation thesis | five family reports | interpretive |
| $1,968.69 canonical Claude spend | sum cc_meta, 540/540 | observed |
