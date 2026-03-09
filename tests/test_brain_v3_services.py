from services.common.brain_v3 import (
    OptionsFlowInput,
    build_surface_signal,
    compute_options_flow_score,
    detect_orderflow,
)


def test_options_flow_analyzer_score_range():
    out = compute_options_flow_score(
        OptionsFlowInput(call_volume=200000, put_volume=50000, oi_change=0.5, price_momentum=0.02, block_trade_size=10000)
    )
    assert 0 <= out["options_flow_score"] <= 1


def test_vol_surface_signal_output():
    out = build_surface_signal(28, 0.12, 0.08, 0.1, 0.05)
    assert 0 <= out["vol_surface_signal"] <= 1


def test_orderflow_detector_output():
    out = detect_orderflow(0.8, 0.6, 0.5, 0.4)
    assert 0 <= out["institutional_accumulation"] <= 1
    assert 0 <= out["institutional_distribution"] <= 1
