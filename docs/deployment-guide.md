# AWS Deployment Guide - AI Options Trading SaaS

## Environments
- `dev`: shared low-cost cluster
- `staging`: production-like with masked data replay
- `prod`: multi-AZ HA

## Core AWS Services
- EKS for microservices
- MSK for Kafka event bus
- ElastiCache Redis for low latency caches/state
- RDS PostgreSQL (Multi-AZ) + read replicas
- S3 for data lake/model artifacts
- ALB + WAF for ingress security
- Route53 + ACM for DNS/TLS

## Network Topology
- VPC with 3 private subnets + 3 public subnets across AZs
- EKS nodes in private subnets
- NAT gateways for outbound only
- Bastion-less access via SSM Session Manager

## Deployment Pattern
1. GitOps (ArgoCD) watches environment manifests.
2. CI builds immutable images and signs them.
3. CD promotes through dev -> staging -> prod with progressive canary.
4. Rollback via previous Helm release and feature-flag disable.

## Autoscaling
- HPA based on CPU/memory + custom Kafka lag metrics
- KEDA for event-driven consumers
- Cluster autoscaler with spot/on-demand mixed node groups

## Reliability
- Pod disruption budgets for critical services
- Multi-AZ database deployment
- Kafka replication factor 3
- Redis with replicas and automatic failover

## Security Controls
- Secret injection via Secrets Manager CSI driver
- KMS encryption at rest for DB, S3, and secrets
- OPA/Gatekeeper policies for workload hardening
- Runtime scanning + container image vulnerability gating

## DR & Backups
- RDS PITR enabled
- S3 versioning and cross-region replication
- Daily snapshots for config and model registry
- Regional failover runbook with Route53 health checks


## Repository Artifacts for Deployment
- Kubernetes manifests: `infra/k8s/prod/`
- Helm chart: `infra/helm/algosaas/`
- CI/CD workflow: `.github/workflows/deploy.yml`
- Monitoring configs: `infra/monitoring/`
- Logging configs: `infra/logging/`

## Scaling Policy (10k+ users)
- API Gateway, Prediction and Signal Engine are configured for `minReplicas=2`, `maxReplicas=20`.
- Remaining services scale from `1` to `8` replicas via HPA based on CPU and memory.
- Use cluster autoscaler/Karpenter with multi-AZ node groups for sustained high concurrency.
