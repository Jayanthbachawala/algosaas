# Production Infrastructure Blueprint (10k+ Concurrent Users)

This repository now includes production deployment artifacts for Kubernetes + Helm + CI/CD.

## Runtime Topology
- **Ingress + TLS**: NGINX ingress with cert-manager TLS termination.
- **API path**: Internet -> LB/Ingress -> `api-gateway` -> internal FastAPI services.
- **Data plane**: managed PostgreSQL HA, Redis cluster, Kafka cluster.
- **Frontend**: dashboard/admin/marketing frontends served as containerized static apps.

## Kubernetes Artifacts
- Namespace, config, secrets templates, ingress and disruption budgets under `infra/k8s/prod/`.
- Per-service Deployment + Service + HPA manifests for all major services.
- Frontend deployments (`dashboard-frontend`, `admin-frontend`, `marketing-frontend`).
- Data-plane integration (`data-plane.yaml`) and backup CronJob (`postgres-backup`).
- Kafka topics CRs (`kafka-topics.yaml`) for trading pipeline topics.

## Helm
- Umbrella chart: `infra/helm/algosaas`.
- Service matrix controlled through `values.yaml`.
- Supports release-based rollout via `helm upgrade --install`.

## Observability
- Prometheus values and scrape setup: `infra/monitoring/prometheus-values.yaml`.
- Grafana dashboard JSON: `infra/monitoring/grafana/dashboards/algosaas-overview.json`.
- ELK baseline configs under `infra/logging/`.

## CI/CD
- GitHub Actions pipeline: `.github/workflows/deploy.yml`.
- Stages: unit tests -> image build/push to GHCR -> Helm deploy to Kubernetes.

## Disaster Recovery
- Daily PostgreSQL logical backup CronJob.
- Multi-replica app deployments + PDBs for critical paths.
- Kafka topics configured with replication factor 3.

## Deployment
```bash
kubectl apply -k infra/k8s/prod
helm upgrade --install algosaas infra/helm/algosaas -n algosaas --create-namespace
```
