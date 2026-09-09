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
