# AlgoSaaS Platform Implementation (AI Brain v3 + SaaS Layer)

## SaaS Platform Layer (Commercial)
Implemented business/user-management capabilities required for production SaaS operations.

### Core SaaS Services
- `AuthService` (self-signup, email verification, login)
- `UserService` (user profile + broker integrations)
- `SubscriptionService` (plans, subscribe, feature entitlements, overrides)
- `BillingService` (invoices, paid revenue)
- `NotificationService` (signal/trade/risk/subscription reminders)
- `AdminService` (master admin dashboard + controls)

### Subscription Plans
- Basic
- Pro
- Premium

### Feature Entitlements
Features:
- `signals_access`
- `scanner_access`
- `ai_insights`
- `paper_trading`
- `auto_trading`
- `broker_connect`
- `portfolio_analytics`
- `advanced_strategies`
- `backtesting`
- `priority_signals`

Evaluation order:
1) user override (`user_feature_overrides`)
2) plan feature (`plan_features`)

### New APIs
#### Auth
- `POST /auth/register`
- `POST /auth/verify-email`
- `POST /auth/login`

#### Subscriptions
- `GET /plans`
- `POST /subscribe`
- `GET /v1/subscriptions/{user_id}/entitlements`
- `POST /v1/subscriptions/override`

#### Notifications
- `POST /v1/notifications/send`
- `GET /v1/notifications/user/{user_id}`

#### Admin
- `GET /v1/admin/dashboard`
- `GET /v1/admin/users`
- `POST /v1/admin/users/status`
- `POST /v1/admin/users/change-plan`
- `POST /v1/admin/users/grant-trial`
- `GET /v1/admin/monitoring`
- `GET /v1/admin/signals/performance`
- `POST /admin/disable-trading`
- `POST /admin/enable-trading`

### Kill Switch Integration
When `/admin/disable-trading` is called, `killswitch:global=1` is set in Redis.
`RiskManagementService` now blocks all trades while global kill-switch is active.

## AI Trading Brain v3 Layer
- FeatureEngineering v3
- OptionsFlowService
- VolatilitySurfaceService
- OrderFlowService
- PredictionService ensemble
- ReinforcementLearningService policy/reward loop
- SignalEngine v3 meta-decision with risk filter

## Frontend Additions
### Dashboard Components
- Admin Dashboard
- AI Insights panel
- Notifications panel
- Broker connection page
- Subscription management page

### Marketing Website
- Public pages: Home, Features, Pricing, Login, Signup, Documentation
- Static site entry: `frontend/marketing/index.html`

## Monitoring Dashboard Data
Admin monitoring endpoint provides:
- Redis memory usage
- active sessions
- monitoring metric series

## Run (SaaS + Brain v3)
```bash
docker compose -f infra/local/docker-compose.yml up -d
uvicorn app.main:app --app-dir services/admin-service --port 8024 --reload
uvicorn app.main:app --app-dir services/api-gateway --port 8020 --reload
```
