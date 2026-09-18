from tellbench.scoring.novelty import (
    bow_vector,
    centroid_distance,
    cosine,
    iteration_novelty,
)


def test_cosine_identity_and_orthogonality():
    a = bow_vector("blue harbor lights")
    assert round(cosine(a, a), 6) == 1.0
    b = bow_vector("quarterly revenue forecast")
    assert cosine(a, b) == 0.0


def test_centroid_distance_rewards_the_outlier():
    panel = (
        "the fox jumped over the fence",
        "the fox jumped over the wall",
        "an accountant reconciled the ledger by candlelight",
    )
    conventional = centroid_distance(panel[0], panel)
    outlier = centroid_distance(panel[2], panel)
    assert outlier > conventional


def test_iteration_novelty_penalizes_repeats():
    answers = (
        "run a wash-and-fold subscription",
        "run a wash-and-fold subscription",  # verbatim repeat
        "host late-night board game events",
    )
    scores = iteration_novelty(answers)
    assert scores[0] == 1.0
    assert scores[1] < 0.01
    assert scores[2] > 0.5


def test_empty_inputs_are_safe():
    assert iteration_novelty(()) == ()
    assert cosine({}, {}) == 0.0
    assert centroid_distance("anything", ()) == 1.0
