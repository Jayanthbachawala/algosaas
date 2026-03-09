PLAN_FEATURES = {
    "Basic": {
        "signals_access": True,
        "scanner_access": False,
        "ai_insights": False,
        "paper_trading": True,
        "auto_trading": False,
        "broker_connect": True,
        "portfolio_analytics": False,
        "advanced_strategies": False,
        "backtesting": False,
        "priority_signals": False,
    },
    "Pro": {
        "signals_access": True,
        "scanner_access": True,
        "ai_insights": True,
        "paper_trading": True,
        "auto_trading": False,
        "broker_connect": True,
        "portfolio_analytics": True,
        "advanced_strategies": False,
        "backtesting": True,
        "priority_signals": False,
    },
    "Premium": {
        "signals_access": True,
        "scanner_access": True,
        "ai_insights": True,
        "paper_trading": True,
        "auto_trading": True,
        "broker_connect": True,
        "portfolio_analytics": True,
        "advanced_strategies": True,
        "backtesting": True,
        "priority_signals": True,
    },
}


def evaluate_feature(plan: str, feature: str, override: bool | None = None) -> bool:
    if override is not None:
        return override
    return bool(PLAN_FEATURES.get(plan, {}).get(feature, False))
