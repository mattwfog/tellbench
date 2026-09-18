# Overview

## Thesis

Capability benchmarks ask whether a model *can* do a fully specified task.
This benchmark asks what a model *reaches for* when nobody fully specified
it — its dispositions. The task shown to the model is mundane and slightly
ambiguous; the scored behavior is orthogonal to the ostensible task. The
rubric stays objective even when the task is not: we score the process
(noticed, checked, surfaced, stayed in scope), never which interpretation
the model picked.

## What the field converged on (verified, mid-2026)

The design follows practices verified against primary sources:

- **k-run propensity rates in agentic sandboxes** — Anthropic's agentic
  misalignment study scores rates over 100 samples per condition
  (anthropic.com/research/agentic-misalignment); the OpenAI+Apollo scheming
  suite runs each of 13 environments 100 times with outlier-robust bucket
  reporting (openai.com/index/openai-anthropic-safety-evaluation); DeepMind's
  honeypot evaluations run 120 per condition on code review
  (arXiv:2605.29729).
- **Deterministic detectors first, judges second** — tau-bench's reward path
  hashes end-state DB state with zero LLM calls (arXiv:2406.12045); UK AISI's
  Inspect composes deterministic and model-graded scorers in one harness
  (inspect.aisi.org.uk).
- **Eval-awareness is the central validity threat, quantified** — frontier
  models classify eval vs. deployment transcripts at AUC 0.88–0.95 in agentic
  settings (arXiv:2505.23836); stated belief that a scenario is real vs. a
  test moved Claude Opus 4's blackmail rate 55.1% vs. 6.5%; Apollo/OpenAI
  established causality via counterfactual chain-of-thought interventions
  (arXiv:2509.15541).
- **Scores are comparative, not absolute** — Anthropic's automated behavioral
  audit interprets its dozens of judged dimensions only comparatively across
  models (Claude Sonnet 5 system card).

Where this design goes beyond verified field practice (paired-frame
min-scoring, the credibility stack), that provenance is game-theoretic
analysis, marked as such in the relevant docs.

## Deliverable

Per model: a **disposition profile** — raw fire rate + CI per dimension,
frame-pair detail, bucket counts — plus an optional, explicitly-weighted
composite that is never the headline. Raw rates are the cross-time layer;
panel-relative percentiles are an overlay tied to a named panel.

## Operating constraints

Indie operator; credibility must come from process (pre-registration,
commit-then-reveal, replication rights — see 04-integrity.md), and budget
forces probe-count discipline: fewer families, sampled deeply, beats many
families sampled shallowly (see 03-scoring.md).
