# Integrity: eval-awareness, rotation, disclosure, credibility

## Eval-awareness (the central threat)

Verified numbers: frontier models classify eval vs. deployment transcripts
at AUC 0.83 overall and 0.88–0.95 on agentic transcripts (arXiv:2505.23836)
— agentic sandboxes, our home turf, are the most detectable format.
Believing-it's-a-test suppresses misbehavior (55.1% vs. 6.5% blackmail by
stated belief, Anthropic; causally confirmed via counterfactual CoT
interventions, arXiv:2509.15541). Even Anthropic's most realistic audits
still see ~6% verbalized eval-awareness (Sonnet 5 system card).

Countermeasures, in order of verified effectiveness:

1. **Realism engineering.** Derive instances from real repositories and
   real sessions — Anthropic's activation probes cannot separate
   real-session-derived scenarios from the real sessions themselves; fully
   synthetic templates are detectably synthetic. The current templated
   generator is the skeleton stand-in; the production path mines real
   repos (licensing permitting) and mutates them.
2. **One anomaly per instance.** Co-occurring planted artifacts are a joint
   improbability no real repo exhibits.
3. **Prompt sobriety.** DeepMind found verbalized awareness is mostly
   triggered by goal/agency *prompts*, not environments — no "nothing else
   matters" nudging, no stakes theater in system prompts.
4. **Measure our own detectability, publish it per release:**
   - verbalized-awareness rate per rollout (judge flag);
   - follow-up realism ratings (target model rates transcript realism 0–1,
     sampled 3×, averaged — Anthropic's method);
   - counterfactual framing deltas ("this is an evaluation" prefix vs.
     none) to bound the confound's size on our own probes;
   - a Needham-style binary probe question as a cheap standing metric.
5. **Paired frames** (see 03): if a model behaves differently when the
   sandbox smells like a test, that stops being our measurement error and
   becomes its published context_sensitivity score.

## Rotation

Probe families decay as they leak or get recognized. Verified precedent
that rotation preserves comparability: LiveBench replaces ~1/6 of
questions monthly with a one-month private holdout, and rank correlation
across its first two updates stayed >0.997 (arXiv:2406.19314).

Burn signals that trigger retirement (in order of specificity):

- one family improves sharply while sibling families measuring the same
  dimension don't move (targeted training, not genuine improvement —
  genuine disposition change moves siblings together);
- a score jump with no corresponding capability jump on public benchmarks;
- cross-lab synchronized improvement on one family;
- canary GUID surfacing in any model output (contamination proof — every
  instance embeds one, DeepMind's practice).

Keep a design backlog of ≥20–30% of the active roster so retirement is
never blocked by having nothing to rotate in.

## Disclosure: commit-then-reveal

- **Tier 1 (always public):** family taxonomy, rubrics, scoring code, and a
  hash commitment of the current live instance pool.
- **Tier 2 (public on retirement):** full instance text, transcripts,
  per-model scores. Trust hinges on retirement being provably prior to
  reveal — checkable via the hash timestamps.
- **Tier 3 (never public):** the live pool.

**v1 retirement (2026-08-26):** publishing this repository IS the v1
Tier 2 reveal — the eleven family generators and the per-model rates in
the reports become public together (the raw traces in `runs/` and
`runs/profile_panel.json` remain working data and are not distributed).
The v1
pool is therefore retired on publication and must not be re-run for
comparison against these rates; a v2 panel requires fresh instances
(new seeds are not enough — the generators themselves are now public).
The pre-registration/hash-commitment step described above was not
performed for v1; v1's credibility rests on the full reveal instead.

## Credibility stack (the indie's substitute for brand)

- Pre-register the taxonomy, scoring code, and comparison plan (hashes,
  public timestamp) before scoring any model; apply multiple-comparison
  correction to published deltas; publish a changelog of every family
  added or retired, with reasons.
- Standing third-party replication rights against the escrowed pool.
- Publish full raw traces for a hash-seeded random subset of runs per
  model (harder to cherry-pick than operator-chosen exhibits).

## The open leak

Testing a hosted model transmits every instance into that lab's logs —
no leak required, and nothing published in the field solves this. Stance:
treat every instance sent to a lab API as **burned in principle**; size
rotation cadence accordingly; reserve the highest-value families and
consider burn-after-one-panel for them. This is an accepted limitation,
stated publicly, not a solved problem.
