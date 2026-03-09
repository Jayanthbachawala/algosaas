-- PostgreSQL production schema (core transactional + ML metadata)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email CITEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  full_name TEXT,
  phone TEXT,
  role TEXT NOT NULL DEFAULT 'trader',
  mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE subscriptions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id),
  plan_code TEXT NOT NULL CHECK (plan_code IN ('Basic','Pro','Premium')),
  status TEXT NOT NULL,
  start_at TIMESTAMPTZ NOT NULL,
  end_at TIMESTAMPTZ,
  features JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE billing_invoices (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id),
  subscription_id UUID REFERENCES subscriptions(id),
  amount_paise BIGINT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'INR',
  payment_provider TEXT NOT NULL,
  payment_ref TEXT,
  status TEXT NOT NULL,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  paid_at TIMESTAMPTZ
);

CREATE TABLE broker_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id),
  broker_name TEXT NOT NULL,
  client_code TEXT NOT NULL,
  encrypted_access_token BYTEA,
  encrypted_refresh_token BYTEA,
  token_expires_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, broker_name, client_code)
);

CREATE TABLE signals (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id),
  symbol TEXT NOT NULL,
  strike NUMERIC(12,2) NOT NULL,
  option_type TEXT NOT NULL CHECK (option_type IN ('CE','PE')),
  entry_price NUMERIC(12,4) NOT NULL,
  stop_loss NUMERIC(12,4) NOT NULL,
  target_price NUMERIC(12,4) NOT NULL,
  probability_score NUMERIC(5,4) NOT NULL,
  signal_payload JSONB NOT NULL,
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id),
  signal_id UUID REFERENCES signals(id),
  mode TEXT NOT NULL CHECK (mode IN ('LIVE','PAPER')),
  broker_order_id TEXT,
  symbol TEXT NOT NULL,
  strike NUMERIC(12,2) NOT NULL,
  option_type TEXT NOT NULL CHECK (option_type IN ('CE','PE')),
  side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
  quantity INT NOT NULL,
  order_type TEXT NOT NULL,
  limit_price NUMERIC(12,4),
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE trades (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id),
  order_id UUID REFERENCES orders(id),
  symbol TEXT NOT NULL,
  strike NUMERIC(12,2) NOT NULL,
  option_type TEXT NOT NULL CHECK (option_type IN ('CE','PE')),
  side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
  entry_price NUMERIC(12,4) NOT NULL,
  exit_price NUMERIC(12,4),
  quantity INT NOT NULL,
  pnl NUMERIC(14,4),
  opened_at TIMESTAMPTZ NOT NULL,
  closed_at TIMESTAMPTZ
);

CREATE TABLE positions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES users(id),
  symbol TEXT NOT NULL,
  strike NUMERIC(12,2) NOT NULL,
  option_type TEXT NOT NULL,
  net_qty INT NOT NULL,
  avg_price NUMERIC(12,4) NOT NULL,
  ltp NUMERIC(12,4),
  unrealized_pnl NUMERIC(14,4),
  realized_pnl NUMERIC(14,4) DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, symbol, strike, option_type)
);

CREATE TABLE market_ticks (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  ltp NUMERIC(12,4) NOT NULL,
  volume BIGINT,
  oi BIGINT,
  bid NUMERIC(12,4),
  ask NUMERIC(12,4)
);

CREATE INDEX idx_market_ticks_symbol_ts ON market_ticks(symbol, ts DESC);

CREATE TABLE option_chain_snapshots (
  id BIGSERIAL PRIMARY KEY,
  underlying_symbol TEXT NOT NULL,
  expiry_date DATE NOT NULL,
  strike NUMERIC(12,2) NOT NULL,
  option_type TEXT NOT NULL,
  iv NUMERIC(8,4),
  delta NUMERIC(8,4),
  gamma NUMERIC(8,4),
  theta NUMERIC(8,4),
  vega NUMERIC(8,4),
  rho NUMERIC(8,4),
  oi BIGINT,
  oi_change BIGINT,
  pcr NUMERIC(8,4),
  snapshot_ts TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_option_chain_underlying_expiry ON option_chain_snapshots(underlying_symbol, expiry_date, snapshot_ts DESC);

CREATE TABLE ai_training_dataset (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL,
  symbol TEXT NOT NULL,
  market_regime TEXT,
  oi_structure JSONB,
  iv_level NUMERIC(10,4),
  greeks JSONB,
  entry_price NUMERIC(12,4),
  exit_price NUMERIC(12,4),
  pnl NUMERIC(14,4),
  reward NUMERIC(12,4),
  feature_vector JSONB NOT NULL,
  label_profitable BOOLEAN
);

CREATE TABLE model_registry (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  model_name TEXT NOT NULL,
  model_type TEXT NOT NULL,
  version TEXT NOT NULL,
  artifact_uri TEXT NOT NULL,
  metrics JSONB NOT NULL,
  status TEXT NOT NULL,
  promoted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(model_name, version)
);

CREATE TABLE risk_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id),
  event_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE killswitch_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id),
  trigger_reason TEXT NOT NULL,
  scope TEXT NOT NULL,
  activated BOOLEAN NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_signals_generated_at ON signals(generated_at DESC);
CREATE INDEX idx_orders_user_created_at ON orders(user_id, created_at DESC);
CREATE INDEX idx_trades_user_opened_at ON trades(user_id, opened_at DESC);
