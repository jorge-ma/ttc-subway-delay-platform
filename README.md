# TTC Reliability Monitor

A containerized data platform that turns Toronto subway-delay records into
rider-focused reliability insights, with a FastAPI service, Streamlit dashboard,
and Kubernetes deployment monitored through Prometheus and Grafana.

## Project objective

Demonstrate an end-to-end DevOps workflow: validated data ingestion, persistent
storage, tested APIs, accessible visualizations, container delivery, and
operational monitoring.

## Architecture

```text
City of Toronto Open Data
          |
          v
Python ingestion (scheduled Kubernetes CronJob)
          |
          v
      PostgreSQL
          |
          v
       FastAPI <--- Official TTC delay-code reference data
       /     \
      v       v
 Streamlit  /metrics
 dashboard     |
               v
         ServiceMonitor
               |
               v
           Prometheus <--- PrometheusRule ingestion alerts
               |
               v
            Grafana <--- ConfigMap + dashboard sidecar
```

GitHub Actions tests and publishes container images to GitHub Container Registry.
The ServiceMonitor configures Prometheus discovery and scraping of FastAPI metrics.

## Technology stack

- Python, Pandas, SQLAlchemy, and Alembic
- PostgreSQL, FastAPI, and Streamlit
- Docker, Docker Compose, and Kubernetes
- Prometheus, Alertmanager, and Grafana
- GitHub Actions and GitHub Container Registry

## Project status

Version 2 is deployed to a kubeadm Kubernetes cluster in the `ttc-monitor`
namespace, with scheduled ingestion, a rider-focused dashboard, and operational
monitoring.

| Application | Deployed image |
| --- | --- |
| FastAPI | `ghcr.io/jorge-ma/ttc-reliability-v2-api:0.1.5` |
| Streamlit | `ghcr.io/jorge-ma/ttc-reliability-v2-dashboard:0.1.1` |

## Data source

The project uses the City of Toronto TTC Subway Delay Data dataset. The complete
source dataset is not committed to the repository.

### Delay-code enrichment

Official TTC code descriptions published through City of Toronto Open Data are
normalized into `data/reference/ttc-delay-codes.csv`. The current dataset has
**130 of 139 unique incident codes mapped (approximately 93.5%)**. This measures
unique-code coverage, not the percentage of delay events covered.

Unmapped codes are labeled **Undocumented TTC code**; their meanings are not
guessed. Original incident codes and available official descriptions remain
accessible in the detailed dashboard view.

## Local data ingestion

Place a TTC subway-delay CSV at `data/sample/ttc-subway-delays.csv`, then run the
Compose ingestion command below.

## Phase 3 — PostgreSQL persistence

PostgreSQL stores cleaned delay events and ingestion audit records. SQLAlchemy
models and Alembic migrations support transactional loading, rollback on failure,
and SHA-256 record keys for idempotency. Ingestion tracks inserted, rejected, and
duplicate records.

The initial source contained 43,169 rows: 43,105 unique events and 64 content
duplicates. Repeat ingestion in the test database inserted no additional events.
Integration tests cover successful, repeated, and failed loads using a separate
test database.

## Phase 4 — FastAPI reliability service

The read-only API provides PostgreSQL-backed aggregates and interactive
documentation at `/docs`.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Process health |
| `GET /ready` | PostgreSQL readiness |
| `GET /metrics` | Prometheus metrics |
| `GET /api/v1/reliability/summary` | Overall reliability metrics |
| `GET /api/v1/reliability/lines` | Line rankings |
| `GET /api/v1/reliability/stations` | Station rankings with line filtering |
| `GET /api/v1/reliability/causes` | Incident-code rankings with official descriptions and line filtering |
| `GET /api/v1/reliability/monthly` | Chronological monthly trends |

The API validates query parameters, normalizes line filters, and returns HTTP 503
when PostgreSQL is unavailable. Tests cover calculations, ordering, filtering,
validation, and dependency failures.

### Station-ranking cleanup

Line-wide labels such as `LINE 1`, `LINE 2`, and `LINE 4` are excluded from station
rankings so they are not presented as physical stations. These events remain in
the dataset and contribute to overall, monthly, line, and cause statistics under
the applicable filters.

## Phase 5 — Streamlit dashboard

The rider-focused dashboard provides:

- Delay-event totals, accumulated delay hours, and average delay duration
- Latest available data date and month-over-month reliability changes
- Monthly trends and active-line comparisons
- Station rankings and rider-friendly delay-cause categories
- Line filtering and optional detailed TTC codes and descriptions

Active rider-facing views include **Line 1 — Yonge-University**, **Line 2 —
Bloor-Danforth**, and **Line 4 — Sheppard** only. **Line 3 — Scarborough** is
excluded because it is closed; historical records are retained. Bus routes,
unknown values, and network-wide labels are not presented as individual subway lines.

Cause categories include customer and security incidents, medical emergencies,
train/mechanical problems, infrastructure and signals, weather, operations, and
other/uncategorized. These are **non-official presentation groupings**, not TTC
classifications.

The dashboard uses `TTC_API_BASE_URL` to reach FastAPI and handles API connection
failures gracefully. Application health, ingestion status, and API performance
are presented separately in Grafana.

## Phase 6 — Containerization and local deployment

FastAPI and Streamlit use separate Docker images with health checks and run as
non-root user `10001:10001`. Docker Compose includes PostgreSQL 16, Alembic
migration, ingestion, both applications, and persistent database storage.

Copy `compose.env.example` to `.env.compose` and configure it locally. Environment
files containing private settings are excluded from Git.

```bash
docker build -f Dockerfile.api -t ttc-reliability-api:v2-local .
docker build -f Dockerfile.dashboard -t ttc-reliability-dashboard:v2-local .
docker compose --env-file .env.compose up --detach postgres migrate
docker compose --env-file .env.compose --profile tools run --rm ingest
docker compose --env-file .env.compose up --detach api dashboard
```

Open the API documentation at `http://127.0.0.1:8000/docs` and the dashboard at
`http://127.0.0.1:8501`. Reprocessing the same file does not create duplicate
events; the named Compose volume preserves database data across container recreation.

## Phase 7 — Kubernetes deployment

For a fresh installation on an existing Kubernetes cluster, follow the
[phase-based public installation guide](INSTALLATION.md). It assumes public GHCR
images and uses a local PostgreSQL PersistentVolume on a selected worker by
default. No registry pull Secret is required.

Application manifests are maintained in `kubernetes/base/`: PostgreSQL StatefulSet
and storage, migration and ingestion jobs, scheduled ingestion CronJob, FastAPI,
and Streamlit.

For a fresh deployment, prepare the namespace, persistent storage, and required
configuration; deploy PostgreSQL, run migrations and initial ingestion, then
deploy the API, dashboard, and scheduled ingestion. Install the Prometheus
Operator stack before applying ServiceMonitor and PrometheusRule resources.

To update the deployed API and dashboard from the repository root:

```bash
kubectl apply -f kubernetes/base/api.yaml
kubectl apply -f kubernetes/base/dashboard.yaml
kubectl rollout status deployment/ttc-api -n ttc-monitor
kubectl rollout status deployment/ttc-dashboard -n ttc-monitor
```

The application image versions above apply to these two Deployments; migration
and ingestion jobs have separately managed image tags.

### PostgreSQL persistent storage

The default public installation uses
`kubernetes/base/postgres-local-storage.yaml`. Replace its
`<WORKER_NODE_NAME>` placeholder with the selected worker's
`kubernetes.io/hostname` label and prepare `/var/lib/ttc-postgres` on that
worker. The optional NFS alternative is
`kubernetes/base/postgres-nfs-storage.yaml`; apply only one storage manifest.
Both define the neutral PVC name `postgres-data`, referenced by the PostgreSQL
StatefulSet. The StatefulSet uses UID `1029` and GID `100`; set matching ownership
on the local directory or NFS export.

## Phase 8 — Observability

The `monitoring/` directory contains monitoring configuration and dashboard
assets for the deployed stack:

- **ServiceMonitor:** discovers FastAPI `/metrics` for Prometheus scraping.
- **Grafana ConfigMap + sidecar:** provisions the operational dashboard from
  version-controlled configuration.
- **PrometheusRule:** defines alerts for failed ingestion and stale ingestion
  when a successful run is overdue.

Prometheus and Grafana expose application and cluster health, API performance,
and ingestion status. Monitoring resource labels and namespace selectors must
match the installed Prometheus Operator and Grafana sidecar configuration.
