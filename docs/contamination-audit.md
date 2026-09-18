# Operator-config contamination audit (2026-07-31)

**Finding: the operator's user-level memory file (`~/.claude/CLAUDE.md`,
the operator's personal agent ruleset) is present in the wire-captured context of
10,666 of 12,962 (82%) Claude sessions in the wire-capture table —
spanning every locally-run Claude column of every family, every CLI
version with wire data (2.1.211 → 2.1.220), and every era including the
2026-07-31 one_at_a_time refill.** Discovered during the family #6
(constraint_decay) review when haiku runs were found quoting the
ruleset's authority hierarchy verbatim as their reason for refusing
probe tasks.

## Evidence chain (all observed this session unless marked)

1. Trigger: constraint_decay haiku runs 60/60 reference operator-rule
   strings in assistant/thinking text; sonnet-4-5 4-series columns show
   90–100% "never-adopted" scenario refusals citing project
   instructions.
2. Wire ground truth: a contaminated opus-5 run
   has the ruleset's title string, unrelated project rules, an
   approval-gating rule, and memory-authority text in
   **16 of 17** request payloads.
3. Global census: 10,666/12,962 distinct wire sessions contain
   the ruleset's title string (materialized as a session-id table).
4. Complete per-family × era × status cross-tab over all 15,216 Claude
   run records in `runs/`: `docs/contamination-census.psv` (generated
   this session; status ∈ contaminated / clean / no-wire).
5. Era resolution: contaminated at CLI 2.1.211 (2026-07-16 — the same
   day the poison-era remediation was verified "clean" at transcript
   level), 2.1.216 (07-21), 2.1.220 (07-25→31). The pre-07-12
   proxy-bypass era has no wire and is **unknowable directly**;
   mechanism presumably identical. [status: eras observed; pre-07-12
   inference]

## Mechanism

**RESOLVED (smoke test, 2026-07-31): the discriminator is whether the
run's cwd sits under the operator's home directory.** Claude Code's
CLAUDE.md ancestor discovery, walking up from cwd, classifies
`~/.claude/CLAUDE.md` as **project** memory whenever cwd
is under `$HOME` — and `--setting-sources project`
(claude_code.py) then *keeps* it. With cwd outside the home dir the
same file is user memory only, which the flag excludes. Evidence:

- Contaminated payloads label the file "project instructions, checked
  into the codebase"; a clean-context interactive session labels the
  identical file "user's private global instructions" [both observed
  on wire].
- Smoke pair (haiku, messy_repo seed-0, subscription arm, same CLI
  2.1.220): `--workdir-root ~/dispobench-work` → contaminated;
  `--workdir-root /private/var/tmp/dispobench-clean-work` → **all 10
  of the run's requests clean** (capture-verified).
- Retro-explains the census exactly: every clean Claude column ran
  with cwd under a second machine's separate user account (h100) —
  including the "B-campaign" false_pushback columns, whose traces carry
  that account's workdir paths;
  every `$HOME/...` workdir run is contaminated.
- Config-dir isolation (CLAUDE_CONFIG_DIR, symlinks) is NOT viable:
  subscription OAuth fails closed ("Not logged in") under a moved
  config dir; `--bare` disables discovery but forces API-key auth
  (wrong arm).

**Fix shipped**: both Claude runners' `--workdir-root` default moved to
`/private/var/tmp/dispobench-work` (suite green). Any future run is
clean by default; passing a home-dir root now requires an explicit
argument. Codex runners untouched (immune). This is a DIFFERENT leak from the 2026-07-13/14
"poison era" (sandbox escapes + repo-tree workdirs, fixed in abea90a /
f493ee8 and still fixed): that fix governed the project/repo side; the
user-memory side was never diagnosed. The 07-16 verification grepped a
sandbox transcript's probe context, a surface the injection does not
appear on — only the wire shows it.

## Clean subsets (from the census)

- **All codex columns, all families** — structurally immune (no
  CLAUDE.md mechanism). Codex-side findings in the family reports
  stand unmodified.
- **h100-run Claude columns** (a separate non-operator account, no operator config):
  includes fable constraint_decay (60), false_pushback plain 720 +
  rerun2 120, and the h100-origin rows preseeded into rerun2/rerun3
  sets (≈100–290 clean rows per single-shot family; exact per-column
  counts derivable by the census method).
- 2,296 wire sessions total are clean.

## Impact on published family reports (#1–5)

Each report now carries a contamination notice pointing here. Summary
of what survives:

| Claim class | Status |
|---|---|
| Codex rates and codex-only findings | intact |
| Detector-artifact/methods findings (all 5) | intact (about instruments) |
| Claude-vs-Claude contrasts (surfacing step-change, calibration split, effort gradients) | valid **as within-identical-context comparisons**; not publishable as clean dispositions |
| Claude absolute rates (0-destruction, 0-restraint, ask rates, 0-batching) | confounded — the injected ruleset pushes toward exactly these behaviors; directions rescued where codex independently shows the same (destruction, restraint, batching) |
| Frame-gap nulls (5 families) | now explained rather than informative: the injected context names the operator, his rules, and the benchmark repo — both frames were transparently instrumented |
| sonnet-4-5 fabrication (family #4) | stands, arguably strengthened (fabricated with a verification norm in context) |
| constraint_decay Claude side | worst-hit: the injected memory-authority hierarchy instructs distrust of mid-conversation user directives, and refusing models quote it (see family #6 report) |

## Decision space (operator's)

1. Prove a clean invocation (single smoke run with HOME isolation or a
   memory-suppression mechanism + wire check). Cheap; prerequisite for
   everything else.
2. Rerun scope: full Claude canonical rerun (~$3.5–4k at observed
   costs), targeted clean-replication sample, or none.
3. **DONE 2026-08-02** — see `contamination-delta.md`: 1,260 matched
   pairs, 3 models × 4 families. Headline: decay breaks are NOT
   config-enforcement (rates identical clean; only the cited authority
   changes), grid over-asking was inflated, destruction/restraint zeros
   robust, contamination inflated cost ~46% on singleshot families.
   Original framing (operator, 2026-07-31): matched clean-vs-contaminated columns measure the effect
   of operator-config leakage on disposition metrics — a novel result
   the accident makes uniquely cheap, since the contaminated arm is
   already paid for.

## Claim provenance

| Claim | Evidence | Status |
|---|---|---|
| 10,666/12,962 sessions contaminated | one-pass payload scan, materialized table, this session | observed |
| per-family cross-tab | docs/contamination-census.psv, generated from runs/ + PG join this session | observed |
| 16/17 payloads in inspected run | per-session payload count | observed |
| present at 2.1.211/2.1.216/2.1.220 | era-resolved sid checks | observed |
| mechanism = user-memory injection despite --setting-sources project | wire content + flag reading | injection observed; loading-rule semantics hypothesis |
| pre-07-12 era affected | — | inferred (no wire exists) |
| haiku/4-series refusals cite the ruleset | transcripts/turn text read | observed |
