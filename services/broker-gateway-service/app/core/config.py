from pydantic_settings import BaseSettings, SettingsConfigDict


class BrokerSettings(BaseSettings):
    zerodha_client_id: str = ""
    zerodha_client_secret: str = ""
    zerodha_redirect_uri: str = "http://localhost:8020/api/v1/broker/oauth/zerodha/callback"
    zerodha_auth_url: str = "https://kite.zerodha.com/connect/login"
    zerodha_token_url: str = "https://api.kite.trade/session/token"
    zerodha_orders_url: str = "https://api.kite.trade/orders/regular"
    zerodha_positions_url: str = "https://api.kite.trade/portfolio/positions"

    upstox_client_id: str = ""
    upstox_client_secret: str = ""
    upstox_redirect_uri: str = "http://localhost:8020/api/v1/broker/oauth/upstox/callback"
    upstox_auth_url: str = "https://api-v2.upstox.com/login/authorization/dialog"
    upstox_token_url: str = "https://api-v2.upstox.com/login/authorization/token"
    upstox_orders_url: str = "https://api-v2.upstox.com/order/place"
    upstox_positions_url: str = "https://api-v2.upstox.com/portfolio/short-term-positions"

    dhan_client_id: str = ""
    dhan_client_secret: str = ""
    dhan_redirect_uri: str = "http://localhost:8020/api/v1/broker/oauth/dhan/callback"
    dhan_auth_url: str = "https://api.dhan.co/oauth/authorize"
    dhan_token_url: str = "https://api.dhan.co/oauth/token"
    dhan_orders_url: str = "https://api.dhan.co/orders"
    dhan_positions_url: str = "https://api.dhan.co/positions"

    shoonya_client_id: str = ""
    shoonya_client_secret: str = ""
    shoonya_redirect_uri: str = "http://localhost:8020/api/v1/broker/oauth/shoonya/callback"
    shoonya_auth_url: str = "https://api.shoonya.com/oauth/authorize"
    shoonya_token_url: str = "https://api.shoonya.com/oauth/token"
    shoonya_orders_url: str = "https://api.shoonya.com/orders"
    shoonya_positions_url: str = "https://api.shoonya.com/positions"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


broker_settings = BrokerSettings()
