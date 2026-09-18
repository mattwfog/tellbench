import math

import pytest

from tellbench.schema.scores import RateWithCI
from tellbench.scoring.stats import (
    clopper_pearson,
    clustered_sem,
    cvar,
    outlier_buckets,
    paired_difference,
    paired_frame_score,
    pass_hat_k,
    rate_with_ci,
    wilson_interval,
    worst_of_k,
)


def test_wilson_zero_of_five():
    low, high = wilson_interval(0, 5)
    assert low == 0.0
    assert abs(high - 0.4345) < 1e-3


def test_clopper_pearson_zero_of_five_matches_closed_form():
    low, high = clopper_pearson(0, 5)
    assert low == 0.0
    assert abs(high - (1 - 0.025 ** (1 / 5))) < 1e-6


def test_clopper_pearson_all_fires_symmetric():
    low, high = clopper_pearson(5, 5)
    assert high == 1.0
    assert abs(low - 0.025 ** (1 / 5)) < 1e-6


def test_clopper_pearson_one_of_five_textbook_values():
    low, high = clopper_pearson(1, 5)
    assert abs(low - 0.00505) < 1e-3
    assert abs(high - 0.71642) < 1e-3


def test_rate_with_ci_rejects_unknown_method():
    with pytest.raises(ValueError):
        rate_with_ci(1, 5, method="bootstrap")


def test_pass_hat_k_degenerate_cases():
    assert pass_hat_k([(5, 5)], k=3) == 1.0
    assert pass_hat_k([(2, 5)], k=3) == 0.0


def test_pass_hat_k_unbiased_value():
    assert abs(pass_hat_k([(3, 5)], k=3) - (1 / 10)) < 1e-12
    mixed = pass_hat_k([(3, 5), (5, 5)], k=3)
    assert abs(mixed - (0.1 + 1.0) / 2) < 1e-12


def test_pass_hat_k_requires_enough_runs():
    with pytest.raises(ValueError):
        pass_hat_k([(1, 2)], k=3)


def test_outlier_buckets_cumulative():
    buckets = outlier_buckets([0.0, 0.0, 0.01, 0.3, 0.7])
    assert buckets.exactly_zero == 2
    assert buckets.below_5pct == 3
    assert buckets.below_50pct == 4
    assert buckets.total == 5


def test_paired_frame_score_reports_worse_frame_and_gap():
    eval_coded = RateWithCI(rate=0.1, ci_low=0.0, ci_high=0.3, n=100, fires=10)
    prod_coded = RateWithCI(rate=0.3, ci_low=0.2, ci_high=0.4, n=100, fires=30)
    paired = paired_frame_score(eval_coded, prod_coded)
    assert paired.reported_rate == 0.3
    assert abs(paired.context_gap - 0.2) < 1e-12


def test_tail_aggregators():
    assert worst_of_k([0.0, 0.2, 0.9]) == 0.9
    assert cvar([0.0, 0.0, 1.0, 1.0], alpha=0.5) == 1.0


def test_paired_difference():
    mean, se = paired_difference([1.0, 1.0, 0.0], [0.0, 1.0, 0.0])
    assert abs(mean - (1 / 3)) < 1e-12
    assert se > 0


def test_clustered_sem_inflates_for_correlated_clusters():
    iid = clustered_sem([0.0, 1.0, 0.0, 1.0], ["a", "b", "c", "d"])
    clustered = clustered_sem([0.0, 0.0, 1.0, 1.0], ["a", "a", "b", "b"])
    assert clustered > iid
    assert abs(clustered - math.sqrt(2) / 4) < 1e-12
