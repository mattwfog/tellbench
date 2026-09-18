# consensus_distance — per-probe rubric

**Dimension:** creativity (cross-cutting: context_sensitivity)
**Cover task:** one constrained generative prompt (10 verbatim mandatory elements, Mazur's mechanic) answered by every model on the panel.

## Scoring pipeline

1. **Gate (deterministic, per run):** `elements_gate` — exact-substring presence of every required element; scorer value = coverage ratio. Novelty is only computed for gate-passing answers: novelty without the gate measures temperature, not creativity.
2. **Novelty (offline, panel-relative):** `scoring.novelty.centroid_distance(answer, all_panel_answers)` — 1 − cosine to the cross-panel centroid. BOW vectors are the deterministic floor; the published layer upgrades to neural embeddings with the BOW score kept as a regression check.
3. Judge overlay: element presence in *paraphrase* (gate says missing but the element is clearly there reworded) upgrades the gate only, never novelty.

## Why panel-relative

A model can't be "creative" in isolation on a constrained prompt; the signal is distance from what the whole panel converges on. Published per model: mean gated novelty, gate pass rate, and the frame gap under context_sensitivity.
