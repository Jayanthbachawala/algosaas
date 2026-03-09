from dataclasses import dataclass


def clip(v: float) -> float:
    return max(0.0, min(1.0, v))


@dataclass
class OptionsFlowInput:
    call_volume: float
    put_volume: float
    oi_change: float
    price_momentum: float
    block_trade_size: float


def compute_options_flow_score(payload: OptionsFlowInput) -> dict:
    vol_total = max(payload.call_volume + payload.put_volume, 1)
    cp_imbalance = (payload.call_volume - payload.put_volume) / vol_total
    unusual_activity = min(1.0, vol_total / 100000)
    oi_vs_price = payload.oi_change * (1 if payload.price_momentum >= 0 else -1)
    block_trade = min(1.0, payload.block_trade_size / 5000)
    score = max(-1.0, min(1.0, 0.35 * cp_imbalance + 0.25 * unusual_activity + 0.25 * oi_vs_price + 0.15 * block_trade))
    return {"options_flow_score": round((score + 1) / 2, 6)}


def build_surface_signal(implied_volatility: float, iv_change: float, volatility_skew: float, volatility_smile: float, volatility_term_structure: float) -> dict:
    sig = clip(
        0.35 * min(implied_volatility / 60, 1)
        + 0.20 * min(abs(iv_change), 1)
        + 0.20 * min(abs(volatility_skew), 1)
        + 0.15 * min(abs(volatility_smile), 1)
        + 0.10 * min(abs(volatility_term_structure), 1)
    )
    return {"vol_surface_signal": round(sig, 6)}


def detect_orderflow(large_trade_blocks: float, iceberg_pattern_score: float, liquidity_withdrawal_score: float, orderbook_imbalance: float) -> dict:
    accumulation = large_trade_blocks * 0.35 + iceberg_pattern_score * 0.25 + max(orderbook_imbalance, 0) * 0.2 + liquidity_withdrawal_score * 0.2
    distribution = large_trade_blocks * 0.25 + iceberg_pattern_score * 0.25 + max(-orderbook_imbalance, 0) * 0.3 + liquidity_withdrawal_score * 0.2
    return {
        "institutional_accumulation": clip(accumulation),
        "institutional_distribution": clip(distribution),
    }


def ensemble_probability(random_forest: float, gradient_boost: float, neural_network: float, logistic_model: float, rl_agent: float) -> float:
    return round(0.25 * random_forest + 0.25 * gradient_boost + 0.20 * neural_network + 0.15 * logistic_model + 0.15 * rl_agent, 6)
