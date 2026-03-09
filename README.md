# AlgoSaaS - Production AI Options Trading Platform (India)

Enterprise-grade microservices architecture for AI-assisted options trading, paper/live execution, broker abstraction, RL feedback loops, and SaaS monetization.

## Key Design Artifacts
- `docs/production-architecture.md` - complete architecture and service design
- `database/schema.sql` - PostgreSQL production schema
- `docs/deployment-guide.md` - AWS deployment blueprint
- `docs/dashboard-layout.md` - frontend dashboard specification
- `docs/backend-microservices-implementation.md` - backend/frontend implementation details
- `.env.example` - service routing + broker OAuth configuration template

## Implemented Components
- Phase-1 to Phase-4 services and dashboard
- API Gateway + WebSocket stream
- Broker integrations: Zerodha, Upstox, Dhan, Shoonya (OAuth, refresh, order, positions, execution confirmation)

## Local Infrastructure
```bash
docker compose -f infra/local/docker-compose.yml up -d
```
