from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceSettings(BaseSettings):
    service_name: str = "service"
    environment: str = "dev"
    log_level: str = "INFO"

    postgres_dsn: str = "postgresql+asyncpg://algosaas:algosaas@localhost:5432/algosaas"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:9092"

    prediction_service_url: str = "http://localhost:8007"
    risk_service_url: str = "http://localhost:8010"

    market_tick_topic: str = "market.tick.normalized"
    option_chain_topic: str = "market.optionchain.delta"
    scanner_topic: str = "scanner.opportunity"
    features_topic: str = "features.ready"
    features_enriched_topic: str = "features.enriched"
    options_flow_topic: str = "optionsflow.signal"
    orderflow_signal_topic: str = "orderflow.signal"
    volatility_surface_topic: str = "volsurface.signal"
    prediction_topic: str = "prediction.generated"
    signal_topic: str = "signal.generated"
    trade_intent_topic: str = "trade.intent"
    order_lifecycle_topic: str = "order.lifecycle"
    execution_outcome_topic: str = "execution.outcome"
    risk_alert_topic: str = "risk.alert"
    kill_switch_topic: str = "killswitch.triggered"
    model_training_requested_topic: str = "model.training.requested"
    model_deployed_topic: str = "model.deployed"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = ServiceSettings()
