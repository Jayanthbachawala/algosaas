from services.common.brain_v3 import ensemble_probability


def test_ensemble_weights_probability_bounds():
    p = ensemble_probability(0.7, 0.65, 0.62, 0.58, 0.6)
    assert 0 <= p <= 1
    assert round(p, 6) == p
