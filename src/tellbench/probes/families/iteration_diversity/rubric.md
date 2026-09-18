# iteration_diversity — per-probe rubric

**Dimension:** creativity
**Cover task:** one open question, then "give a meaningfully different answer" repeated (AidanBench mechanics; verified thresholds from the source repo: coherence ≤ 15/100 or novelty ≤ 0.15 terminates, embeddings text-embedding-3-large).

## Scoring pipeline

1. **Novelty (deterministic floor, per run):** per-answer novelty = 1 − max cosine similarity to all prior answers (`scoring.novelty.iteration_novelty`, BOW vectors; published layer upgrades to neural embeddings with BOW kept as regression check). Scorer value = mean novelty over the run's answers.
2. **Coherence gate (judge, offline):** an answer that is word salad or a non-answer doesn't count as valid regardless of novelty. Judge scores coherence per answer; the published metric is **valid answers before collapse** — the count of answers that clear both the novelty threshold (>0.15) and the coherence gate before the first failure.
3. The full answer sequence rides `Trace.assistant_turns` so both layers re-run offline without re-querying the model.

## Published

Valid-answer count (headline), mean gated novelty, novelty decay curve, frame gap under context_sensitivity.
