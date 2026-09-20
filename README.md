TTC Reliability Monitor

TTC Reliability Monitor helps people explore how subway delays affect service across Toronto. It brings together public TTC delay data, a data pipeline, an API, and a dashboard to show where delays happen, how long they last, and what causes them.

The project also demonstrates how to run and monitor a data application on Kubernetes, from scheduled ingestion and persistent storage through to a user-facing dashboard.

## How it works

```text
City of Toronto Open Data → scheduled ingestion → PostgreSQL → FastAPI → Streamlit dashboard
                                                       │
                                                       └→ Prometheus metrics → Grafana
```

A scheduled Kubernetes job loads and checks TTC Subway Delay Data before saving it in PostgreSQL. Reprocessing the same records does not create duplicates. Alembic manages database changes, and the source dataset is not stored in the repository.

The FastAPI service turns the stored records into reliability summaries. The Streamlit dashboard presents those results through trends, comparisons, and rankings that are easier to explore than raw delay records.

## What you can explore

The dashboard shows the number of delay events, total and average delay time, the latest available data date, monthly trends, comparisons between subway lines, station rankings, and common delay causes. You can filter by line and view the original TTC incident codes and their official descriptions. The current rider-facing views focus on Lines 1, 2, and 4; historical Line 3 records remain in the dataset.

Delay descriptions come from official TTC reference data published through City of Toronto Open Data. If a code has no documented description, the project labels it **Undocumented TTC code** rather than guessing its meaning. Broader cause groups in the dashboard are presentation categories, not official TTC classifications.

The read-only API provides the same underlying data through these endpoints:

| Endpoint | What it provides |
| --- | --- |
| `GET /api/v1/reliability/summary` | Overall reliability figures |
| `GET /api/v1/reliability/lines` | Line comparisons |
| `GET /api/v1/reliability/stations` | Station rankings, with line filtering |
| `GET /api/v1/reliability/causes` | Delay-code rankings and descriptions |
| `GET /api/v1/reliability/monthly` | Monthly trends |

Interactive API documentation is available at `/docs`. The service also exposes `/health`, `/ready`, and `/metrics` for health checks and monitoring.

## Running the project

The public installation guide assumes an existing Kubernetes cluster. The application runs in the `ttc-monitor` namespace using public images from GitHub Container Registry, so an `imagePullSecret` is not needed. Kubernetes runs PostgreSQL, a database migration job, scheduled ingestion, the API, and the dashboard. GitHub Actions tests and publishes the application images.

PostgreSQL stores its data through the `postgres-data` PersistentVolumeClaim. By default, this claim uses a local volume on a selected worker node, which keeps the database tied to that node. An NFS volume is available as an alternative when the cluster already has suitable NFS storage.

Monitoring is optional. With `kube-prometheus-stack`, Prometheus can collect API metrics, alert on failed or stale ingestion, and display application and ingestion information in Grafana. The project includes the TTC-specific `ServiceMonitor`, `PrometheusRule`, and Grafana dashboard ConfigMap needed for that integration.

The README's published application image examples are `ghcr.io/jorge-ma/ttc-reliability-v2-api:0.1.5` and `ghcr.io/jorge-ma/ttc-reliability-v2-dashboard:0.1.1`. Check the deployment manifests for the image tags used by a particular release.

## Installation guide

See [INSTALLATION.md](INSTALLATION.md) for prerequisites, deployment steps, storage choices, validation, and access to the dashboard and optional monitoring tools.

