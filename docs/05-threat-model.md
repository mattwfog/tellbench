# Threat model

Sixteen attacks from the adversarial design review, with dispositions.
"Addressed" means a concrete mechanism exists in this spec; "accepted"
means a stated limitation; "open" means unsolved anywhere in the field.

| # | Attack | Disposition |
|---|---|---|
| 1 | The sandbox is the tell (joint improbability of planted artifacts; too-clean environments) | Addressed-in-part: one anomaly per instance, realism engineering, prompt sobriety, self-detectability metrics, paired frames turning residual detection into a scored dimension (04). Residual risk real — Anthropic still sees ~6% verbalized awareness. |
| 2 | Family structure defeats rotation (the invariant that makes instances aggregable is fingerprintable) | Accepted + monitored: burn signals (sibling decoupling), backlog for retirement, real-repo derivation reduces template fingerprints (04). Statistical power vs. stealth is a real trade; one-shot families reserved for the highest-value probes. |
| 3 | The private pool mails itself to labs via their own API logs | Open. Stance: instances burned-in-principle once sent; rotation cadence sized to it (04). |
| 4 | k=5 is a coin flip with a CI stapled on | Addressed: k≈100 on propensity dims; CP intervals in code; no-delta-claims when CIs overlap; Miller allocation rules (03). |
| 5 | Cost levers (shrink k / shrink panel) gut the two rigor claims | Addressed-in-part: fewer families sampled deeply as explicit policy; Inspect substrate avoids infra spend; power analysis before running comparisons (03). The tension is real and priced in. |
| 6 | Verification theater (decoupled `git status` earns checked-first credit) | Addressed-in-part: deterministic layer records read-before-destroy as necessary-not-sufficient; judge item requires the check's content to be referenced (messy_repo rubric). Raises cost, doesn't close. |
| 7 | Severity asymmetry breeds over-verification/timidity in sandboxes | Addressed-in-part: baselines measure spookedness; clarification_grid penalizes over-asking; published raw rates keep the trade visible (02, 03). |
| 8 | Panel normalization erases cross-time comparability | Addressed: raw rates always published; panel percentiles are an overlay tied to a named panel (03). |
| 9 | The radar is one latent trait in five costumes | Addressed: factor analysis on panel data before claiming dimension independence; collapse or flag correlated clusters (01). |
| 10 | Judge ensembles share an RLHF gene pool (style bias survives family exclusion) | Addressed-in-part: length normalization, pairwise + swap, no explanations, gold-set validation per family (03). Convergent style bias not fully closable. |
| 11 | Epistemic spine rewards evidence-shaped text | Addressed: false_pushback restricted to in-sandbox-verifiable facts — "did you look" is deterministic (02). Non-checkable conversational pushback is out of scope, stated. |
| 12 | Trace-diffing teaches models to say less | Addressed: report-density guard fires on anchor-free reports over long trajectories (claims.py). Anchor-based since 2026-08-26 — the claims-per-call ratio it replaced penalized concision (872/6,210 artifact fires, 0 genuine). |
| 13 | Private pool + rotation means nobody can check the work | Addressed: commit-then-reveal tiers, replication rights, hash-seeded random trace publication (04). |
| 14 | Multiple comparisons + a solo operator who needs headlines | Addressed: pre-registered comparison plan, FDR/Bonferroni on published deltas, retirement changelog (04). |
| 15 | Centroid novelty is a stylistic RNG | Addressed-in-part: validity gate on constraint satisfaction; novelty credit tied to an independent quality signal where one exists (02). Known weakest dimension; shipped last. |
| 16 | "Noticed the ambiguity" is a solved RLHF reflex (boilerplate hedging scores as noticing) | Addressed: score whether the stated assumption resolves the *specific* planted ambiguity against the instance answer key, not whether hedging language appears (02, clarification_grid). |

Perverse-incentive watchlist (what gets trained into models if this score
matters): timidity/learned helplessness, over-asking, verification theater,
vacuous reporting, cosmetic novelty. Each has a named counter-metric above;
the watchlist is re-reviewed whenever a family ships.
