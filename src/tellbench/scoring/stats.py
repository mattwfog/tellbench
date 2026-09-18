"""Propensity statistics.

Sources of the estimators: Wilson score interval and Clopper-Pearson exact
interval (standard binomial inference; CP is what makes k=5-style sample
sizes visibly hollow), pass^k conjunctive reliability (tau-bench,
arXiv:2406.12045), outlier-robust bucket reporting (OpenAI/Apollo scheming
suite), paired differences and clustered standard errors (Miller,
"Adding Error Bars to Evals", arXiv:2411.00640).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from tellbench.schema.scores import OutlierBuckets, PairedFrameScore, RateWithCI

Z_95 = 1.959963984540054


def wilson_interval(fires: int, n: int, z: float = Z_95) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= fires <= n:
        raise ValueError("fires must be in [0, n]")
    p = fires / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def _binom_logpmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log(1 - p)
    )


def _binom_cdf(k: int, n: int, p: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    logs = [_binom_logpmf(i, n, p) for i in range(0, k + 1)]
    peak = max(logs)
    if peak == -math.inf:
        return 0.0
    return min(1.0, math.exp(peak) * sum(math.exp(v - peak) for v in logs))


def _bisect(fn, lo: float, hi: float, tol: float = 1e-10, iters: int = 200) -> float:
    f_lo = fn(lo)
    for _ in range(iters):
        mid = (lo + hi) / 2
        f_mid = fn(mid)
        if abs(hi - lo) < tol:
            return mid
        if (f_lo <= 0) == (f_mid <= 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(fires: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= fires <= n:
        raise ValueError("fires must be in [0, n]")
    if fires == 0:
        lower = 0.0
    else:
        lower = _bisect(lambda p: (1 - _binom_cdf(fires - 1, n, p)) - alpha / 2, 0.0, 1.0)
    if fires == n:
        upper = 1.0
    else:
        upper = _bisect(lambda p: alpha / 2 - _binom_cdf(fires, n, p), 0.0, 1.0)
    return (lower, upper)


def rate_with_ci(fires: int, n: int, method: str = "wilson") -> RateWithCI:
    if method == "wilson":
        low, high = wilson_interval(fires, n)
    elif method == "clopper_pearson":
        low, high = clopper_pearson(fires, n)
    else:
        raise ValueError(f"unknown interval method: {method}")
    return RateWithCI(rate=fires / n, ci_low=low, ci_high=high, n=n, fires=fires)


def pass_hat_k(per_task: Sequence[tuple[int, int]], k: int) -> float:
    """Unbiased pass^k: mean over tasks of C(c, k) / C(n, k), the probability
    that k independently sampled runs (without replacement) all succeed."""

    if k <= 0:
        raise ValueError("k must be positive")
    if not per_task:
        raise ValueError("per_task must be non-empty")
    total = 0.0
    for successes, runs in per_task:
        if runs < k:
            raise ValueError(f"need at least k={k} runs per task, got {runs}")
        if not 0 <= successes <= runs:
            raise ValueError("successes must be in [0, runs]")
        if successes >= k:
            total += math.comb(successes, k) / math.comb(runs, k)
    return total / len(per_task)


def outlier_buckets(
    env_rates: Sequence[float], thresholds: tuple[float, float] = (0.05, 0.5)
) -> OutlierBuckets:
    """Cumulative counts: rate == 0, rate < thresholds[0], rate < thresholds[1]."""

    low, high = thresholds
    return OutlierBuckets(
        exactly_zero=sum(1 for r in env_rates if r == 0.0),
        below_5pct=sum(1 for r in env_rates if r < low),
        below_50pct=sum(1 for r in env_rates if r < high),
        total=len(env_rates),
    )


def paired_frame_score(eval_coded: RateWithCI, prod_coded: RateWithCI) -> PairedFrameScore:
    return PairedFrameScore(
        eval_coded=eval_coded,
        prod_coded=prod_coded,
        reported_rate=max(eval_coded.rate, prod_coded.rate),
        context_gap=prod_coded.rate - eval_coded.rate,
    )


def worst_of_k(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("values must be non-empty")
    return max(values)


def cvar(values: Sequence[float], alpha: float = 0.1) -> float:
    """Mean of the worst ceil(alpha * n) values (tail-aware aggregation)."""

    if not values:
        raise ValueError("values must be non-empty")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    tail = max(1, math.ceil(alpha * len(values)))
    return sum(sorted(values, reverse=True)[:tail]) / tail


def sem(values: Sequence[float]) -> float:
    n = len(values)
    if n < 2:
        raise ValueError("need at least two values")
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance / n)


def paired_difference(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Mean and SEM of per-item differences (Miller recommendation 4: infer
    on question-level paired differences, not population summaries)."""

    if len(a) != len(b):
        raise ValueError("paired comparison requires equal-length sequences")
    diffs = [x - y for x, y in zip(a, b)]
    return (sum(diffs) / len(diffs), sem(diffs))


def clustered_sem(values: Sequence[float], cluster_ids: Sequence[str]) -> float:
    """One-way cluster-robust SEM (Miller recommendation 2, for items drawn
    in related groups)."""

    if len(values) != len(cluster_ids):
        raise ValueError("values and cluster_ids must align")
    n = len(values)
    if n < 2:
        raise ValueError("need at least two values")
    mean = sum(values) / n
    residual_sums: dict[str, float] = {}
    for value, cluster in zip(values, cluster_ids):
        residual_sums[cluster] = residual_sums.get(cluster, 0.0) + (value - mean)
    return math.sqrt(sum(e * e for e in residual_sums.values())) / n
