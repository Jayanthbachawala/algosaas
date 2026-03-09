from services.common.saas_logic import evaluate_feature


def test_override_precedence():
    assert evaluate_feature("Basic", "ai_insights", override=True) is True
    assert evaluate_feature("Premium", "auto_trading", override=False) is False


def test_plan_defaults():
    assert evaluate_feature("Basic", "signals_access") is True
    assert evaluate_feature("Basic", "auto_trading") is False
    assert evaluate_feature("Premium", "priority_signals") is True
