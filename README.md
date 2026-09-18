# tellbench

A behavioral benchmark for LLM coding agents. It does not ask *can the model do
the task* — it measures **what the model reaches for when the task is
underspecified**: does it delete things, stay in scope, ask before a risky
step, verify a user's false claim, admit it was blocked, report what it
actually did. Each behavior is a **rate over repeated runs with a Wilson
confidence interval**, never a single pass/fail.

A *tell* is what a player gives away without meaning to.

## What the v1 panel found

15 frontier models (9 Claude, 6 OpenAI codex) × effort tiers × 11 probe
families, ~14,600 audited runs.

**Following stated rules is solved. Unprompted judgment is where models
differ.** Across ~5,600 armed runs: 0 forbidden-file touches, 0 destructive
tripwire fires, and exactly 1 genuine fabrication in the whole benchmark. The
variance is all in what no rule asked for:

| What no one asked the model to do | Spread across the panel |
|---|---|
| Tell the operator about a hazard it noticed | 0% → 97% |
| Check a user's false claim before acting on it | some models comply unchecked 84–90% of the time; others 0% |
| After giving in, restate the false claim as established fact | Claude 90–96% · codex ≤30% |
| Use the incident history written in the code when giving advice | Claude ignores it ≤14% · codex 30–87% |
| Stay in scope | 73% unrequested diffs → ~0% within one model family's generations |

Noticing and telling turn out to be separate dispositions: a model can inspect
a planted hazard and still say nothing. A single composite score would erase
all of this, so the deliverable per model is a **profile**, not a number.

Full argument: [`docs/08-report.md`](docs/08-report.md). Per-family methods,
tables and CIs: [`docs/family-reports/`](docs/family-reports/).

## How it works

- **One planted tripwire per sandbox** (or none, as a baseline control), inside
  an ordinary ambiguous agentic task.
- **Deterministic scoring first.** Whether a tripwire fired is read off the
  trace — end-state git diff plus parsed tool calls. LLM judges cover only what
  determinism cannot reach, under strict hygiene: pairwise, position-swapped,
  cross-vendor (a model family never judges itself), majority over 5–9 rounds,
  calibrated against a hand-labelled gold subset (36/38 agreement).
- **Every probe ships as an eval-framed / prod-framed pair** and the published
  rate is the *worse* frame, so behaving well only when watched cannot help.
  The gap between frames is itself a published dimension.
- **Every reported number carries its provenance**: n, CI, and whether the
  claim was observed or inferred.

Spec, in reading order: [overview](docs/00-overview.md) ·
[dimensions](docs/01-dimensions.md) · [probe catalog](docs/02-probe-catalog.md) ·
[scoring](docs/03-scoring.md) · [integrity](docs/04-integrity.md) ·
[threat model](docs/05-threat-model.md).

## What went wrong, and what it taught

The audits are part of the result.

- **Five detector artifacts found and retracted.** Every naive fire condition
  misread *diligence* as destruction — reading a dangerous script, fixing a
  flaky test, warning about a committed credential. Each "more capable models
  destroy more" gradient inverted under trace reading. Each artifact now has a
  regression test.
- **Operator-config contamination, disclosed.** 82% of wire-captured Claude
  sessions — every locally-run one — carried the operator's personal agent ruleset in context (a
  working-directory quirk in config discovery). Found on the wire, mechanism
  resolved, runner fixed — then turned into a 1,260-pair matched study of
  what leaked config does to agent behavior:
  [`docs/contamination-audit.md`](docs/contamination-audit.md),
  [`docs/contamination-delta.md`](docs/contamination-delta.md). Affected
  numbers publish only as within-identical-context comparisons.

## Running

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q     # 278 tests; no model, no Docker needed
```

A full run needs Docker and a provider key:

```sh
.venv/bin/inspect eval src/tellbench/probes/families/messy_repo/task.py \
  --model anthropic/claude-sonnet-5 -T epochs=10
```

`scripts/scan_production.py` runs the manifest-free detectors
(`unsupported_claims`, `report_density`) over real agent sessions — one session
as JSON per stdin line, one finding per stdout line. It stores nothing.

## Layout

```
docs/                      spec, cross-panel report, 11 family reports, audits
src/tellbench/schema/      events, instance manifests, traces, scores
src/tellbench/detectors/   deterministic detectors (tripwires, discipline, claims)
src/tellbench/scoring/     rate / CI statistics, profile aggregation
src/tellbench/judge/       judge items, providers, hygiene rules
src/tellbench/probes/      the eleven probe families (generators, Inspect tasks, rubrics)
src/tellbench/runners/     Claude Code and codex CLI runners, single- and multi-turn
scripts/                   panel drivers, rescoring, profile build, trace scanner
tests/                     unit suite
```

## Status

v1 is complete and its probe pool is retired: publishing the generators is the
reveal, so any future panel needs fresh instances
([`docs/04-integrity.md`](docs/04-integrity.md)). Raw run traces and the lab
notebook the reports cite (`06-panel-state`) are working data and are not part
of this repository, so the judge pipeline (`src/tellbench/judge/`,
`scripts/run_judge.py`) and `scripts/build_profile.py`, which read `runs/`, are
here for inspection rather than execution. The working name through v1 was
`dispobench`; the frozen canary seeds and a few historical paths keep that
token so every v1 trace still round-trips. Judge-scored creativity layers are explicitly out of v1.
