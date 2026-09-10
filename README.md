# TTC Reliability Monitor

A containerized data platform that processes Toronto subway-delay
records and presents reliability information through an API and
interactive dashboard.

## Project objective

The project demonstrates an end-to-end DevOps workflow using Python,
PostgreSQL, FastAPI, Streamlit, Docker, Kubernetes, Prometheus,
Grafana, and GitHub Actions.

## Architecture

1. Python retrieves and validates TTC delay records.
2. Valid records are stored in PostgreSQL.
3. FastAPI provides reliability aggregates.
4. Streamlit presents the results to users.
5. Prometheus monitors application and cluster health.
6. Grafana displays operational dashboards.
7. GitHub Actions tests and publishes container images.

## Technology stack

- Python and Pandas
- PostgreSQL and Alembic
- FastAPI
- Streamlit
- Docker and Docker Compose
- Kubernetes
- Prometheus, Alertmanager, and Grafana
- GitHub Actions
- GitHub Container Registry

## Project status

Version 2 is currently being rebuilt as a clean and repeatable
portfolio implementation.

## Data source

The project uses the City of Toronto TTC Subway Delay Data dataset.

The complete source dataset is not committed to this repository.

## Local data ingestion

Place a TTC subway-delay CSV file at:

data/sample/ttc-subway-delays.csv

## Phase 3 — PostgreSQL persistence

The application uses PostgreSQL and SQLAlchemy to persist cleaned TTC
delay events and ingestion audit records.

Implemented capabilities include:

- Environment-based database configuration
- SQLAlchemy models for delay events and ingestion runs
- Alembic-managed schema migrations
- Transactional loading with rollback on failure
- SHA-256 record keys for idempotent ingestion
- Tracking of inserted, rejected and duplicate records
- Separate application and test databases
- Integration tests for successful, repeated and failed loads

The source dataset contained 43,169 rows. Cleaning identified 43,105
unique events and 64 content duplicates. The first production ingestion
stored all 43,105 unique events. Repeating the ingestion against the test
database inserted zero additional events, confirming idempotency.

Database credentials are supplied through environment variables. The
real `.env` file is excluded from version control, while `.env.example`
documents the required settings without containing credentials.

## Phase 4 — FastAPI reliability service

The project provides a read-only FastAPI service backed by PostgreSQL.

Available endpoints include:

- `GET /health` — process health
- `GET /ready` — PostgreSQL readiness
- `GET /api/v1/reliability/summary` — system-wide metrics
- `GET /api/v1/reliability/lines` — line rankings
- `GET /api/v1/reliability/stations` — station rankings with line filtering
- `GET /api/v1/reliability/causes` — incident-code rankings with line filtering
- `GET /api/v1/reliability/monthly` — chronological monthly trends

The API validates query parameters, normalizes line filters, returns
HTTP 503 when PostgreSQL is unavailable, and publishes an OpenAPI
document with interactive documentation at `/docs`.

Automated tests cover query calculations, ordering, filtering, input
validation, dependency failures and database cleanup. Cross-endpoint
checks confirm that line and monthly event totals match the system-wide
total of 43,105 unique events.

## Phase 5 — Streamlit dashboard

The project includes an interactive Streamlit dashboard backed by the
FastAPI reliability service.

Dashboard features include:

- System-wide reliability summary metrics
- Chronological monthly delay trend
- Subway-line delay comparison
- Top affected station rankings
- Top incident-cause rankings
- Interactive filtering by subway line
- Graceful handling of API connection failures

The dashboard restricts its line selector and comparison chart to recognized
TTC subway lines. Bus routes, unknown values and network-wide records are not
shown as individual subway lines.

The dashboard API client supports configuration through the
`TTC_API_BASE_URL` environment variable. Automated tests validate API URL
configuration, endpoint requests, filtering parameters and connection-error
handling.

Run the API:

    python -m uvicorn api.main:app \
      --host 127.0.0.1 \
      --port 8000

Run the dashboard in a second terminal:

    python -m streamlit run dashboard/app.py \
      --server.address 127.0.0.1 \
      --server.port 8501

## Phase 6 — Containerization and local deployment

The FastAPI service and Streamlit dashboard are packaged as separate Docker
images. Both application containers run as the non-root user `10001:10001`
and include health checks.

Docker Compose provides a reproducible local environment containing:

- PostgreSQL 16
- Alembic database migration
- Idempotent TTC data ingestion
- FastAPI reliability service
- Streamlit dashboard
- Persistent PostgreSQL storage using a named Docker volume

### Build the images

    docker build \
      --file Dockerfile.api \
      --tag ttc-reliability-api:v2-local \
      .

    docker build \
      --file Dockerfile.dashboard \
      --tag ttc-reliability-dashboard:v2-local \
      .

### Configure the environment

    cp compose.env.example .env.compose

Edit `.env.compose` and provide a private local PostgreSQL password. This file
is excluded from Git.

### Start the database and migration

    docker compose \
      --env-file .env.compose \
      up --detach postgres migrate

### Load the dataset

    docker compose \
      --env-file .env.compose \
      --profile tools \
      run --rm ingest

The ingestion process is idempotent. Reprocessing the same source file does
not create duplicate database records.

### Start the applications

    docker compose \
      --env-file .env.compose \
      up --detach api dashboard

The local services are available at:

- API documentation: `http://127.0.0.1:8000/docs`
- Dashboard: `http://127.0.0.1:8501`

PostgreSQL data remains available when containers are removed and recreated
because the Compose named volume is retained.
.
