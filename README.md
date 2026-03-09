# AlgoSaaS - Production AI Options Trading Platform (India)

Enterprise-grade microservices architecture for AI-assisted options trading, SaaS subscriptions, broker integrations, risk controls, and AI insights.

## Implemented Platform Layers
- AI Trading Brain v3 (ensemble + options flow + vol surface + order flow + RL + meta-decision)
- SaaS commercial layer (signup, plans, entitlements, admin controls, notifications)
- Trading platform layer (signals, paper/live execution, risk management, broker gateway)
- Frontend layer (React dashboard + marketing website)

## Key Artifacts
- `database/schema.sql`
- `docs/backend-microservices-implementation.md`
- `docs/production-architecture.md`
- `docs/deployment-guide.md`
- `docs/dashboard-layout.md`
- `docs/production-infrastructure.md`
- `.env.example`

## Local Infrastructure
```bash
docker compose -f infra/local/docker-compose.yml up -d
```

## Production Kubernetes Deployment
```bash
kubectl apply -k infra/k8s/prod
helm upgrade --install algosaas infra/helm/algosaas -n algosaas --create-namespace
```
