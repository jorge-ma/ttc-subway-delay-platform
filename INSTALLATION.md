# TTC Reliability Monitor: public Kubernetes installation

This guide explains how to deploy the TTC Reliability Monitor to an existing Kubernetes cluster.
It assumes you already have:
- a working Kubernetes cluster
- at least one schedulable worker node
- kubectl configured and able to communicate with the cluster
- access to a POSIX-compatible shell
The application container images are published publicly in GitHub Container Registry (GHCR), so no registry credentials or image pull secrets are required.
By default, PostgreSQL uses a local PersistentVolume on one selected worker node. This keeps the installation self-contained and avoids requiring external storage such as NFS. Because the volume is local to that worker, the PostgreSQL pod is tied to that node.
Before running the commands:
- Replace every <PLACEHOLDER> with a value appropriate for your environment.
- Run commands from the repository root unless a phase explicitly says otherwise.
- The application uses the ttc-monitor Kubernetes namespace.
- Do not store passwords, tokens, or other credentials in Git.
- This guide assumes a fresh installation. If PostgreSQL already contains data, back it up before changing persistent-storage configuration.

## Phase 1 — Clone and inspect the repository

Get the application source and identify its Kubernetes manifests. This lets later commands refer to the same checkout and helps catch path differences before anything is deployed.

**Purpose:** Obtain the deployment files.
**Why it is required:** Kubernetes resources must be applied from a consistent release.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**

```bash
git clone https://github.com/jorge-ma/ttc-subway-delay-platform.git
cd ttc-subway-delay-platform
find kubernetes -type f | sort
```

**Verification / Success criteria:** The checkout contains:
kubernetes/base/api.yaml
kubernetes/base/dashboard.yaml
kubernetes/base/ingestion-cronjob.yaml
kubernetes/base/migration-job.yaml
kubernetes/base/namespaces.yaml
kubernetes/base/postgres-local-storage.yaml
kubernetes/base/postgres-nfs-storage.yaml
kubernetes/base/postgres-secret.example.yaml
kubernetes/base/postgres.yaml

## Phase 2 — Confirm cluster access and create the namespace

Confirm the context before creating application resources. A namespace keeps cluster resources organizes and must exist before namespaced manifests are applied.

**Purpose:** Establish the deployment target.
**Why it is required:** Applying to the wrong context or a missing namespace causes failures or unintended changes.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**

```bash
kubectl config current-context
kubectl get nodes -o wide
kubectl create namespace ttc-monitor --dry-run=client -o yaml | kubectl apply -f -
```

**Verification / Success criteria:** The intended cluster appears and `kubectl get namespace ttc-monitor` reports `Active`.

## Phase 3 — Select a PostgreSQL worker

Choose a schedulable worker with sufficient durable disk space. The local volume's node affinity must use that worker's `kubernetes.io/hostname` label value, which may differ from the displayed node name.

**Purpose:** Pin storage to a known node.
**Why it is required:** A local PV can only be mounted by pods on its host.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**

```bash
kubectl get nodes --show-labels
kubectl get node <WORKER_NODE_NAME> -o jsonpath='{.metadata.labels.kubernetes\.io/hostname}{"\n"}'
kubectl describe node <WORKER_NODE_NAME>
```

**Verification / Success criteria:** The worker is `Ready`, schedulable, and the label output is the value inserted into `postgres-local-storage.yaml`.

## Phase 4 — Prepare the worker directory

Create the PostgreSQL data directory on the selected worker before scheduling the database. Set ownership to the UID and GID used by the repository's PostgreSQL container security context; verify these values in `postgres.yaml` first.

**Purpose:** Provide writable disk storage.
**Why it is required:** The PV path must exist and be writable by PostgreSQL.
**Where to run it:** Shell on `<WORKER_NODE_NAME>`.

**Procedure / Commands**

```bash
sudo mkdir -p /var/lib/ttc-postgres
sudo chown 999:999 /var/lib/ttc-postgres
sudo chmod 700 /var/lib/ttc-postgres
sudo stat -c '%u:%g %a %n' /var/lib/ttc-postgres
```

**Verification / Success criteria:** The path exists with ownership `999:999` and mode `700`, matching the default `postgres.yaml` and Debian-based `postgres:16` image. If you change its security context or image variant, change the directory ownership to match.

## Phase 5 — Create the PostgreSQL Secret

Start from the repository's example Secret and enter a unique password locally. The populated file is ignored by Git, but must still be protected from other local users. Kubernetes Secrets are base64 encoded resources, so control access to the file and cluster.

**Purpose:** Supply database credentials to PostgreSQL and the application.
**Why it is required:** The database and clients must agree on their credentials.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**

```bash
umask 077
cp kubernetes/base/postgres-secret.example.yaml kubernetes/base/postgres-secret.yaml
chmod 600 kubernetes/base/postgres-secret.yaml
# Edit kubernetes/base/postgres-secret.yaml; replace CHANGE_ME with a strong unique password.
kubectl apply -f kubernetes/base/postgres-secret.yaml
kubectl get secret -n ttc-monitor postgres-secret
git check-ignore kubernetes/base/postgres-secret.yaml
```

**Verification / Success criteria:** The named Secret exists, and `git status` does not show the populated Secret file. Never paste its contents into issue reports or logs.

## Phase 6 — Create the local PV and PVC

Use `postgres-local-storage.yaml` after replacing `<WORKER_NODE_NAME>` with the hostname label from Phase 3. Render the value into the apply stream so the tracked template keeps its placeholder. Its PVC is named `postgres-data`, and the PV uses `Retain` to reduce the risk of accidental data loss.

**Purpose:** Bind PostgreSQL to persistent local storage.
**Why it is required:** Database data must survive pod replacement.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**

```bash
WORKER_NODE_NAME=<HOSTNAME_LABEL_FROM_PHASE_3>
sed "s/<WORKER_NODE_NAME>/$WORKER_NODE_NAME/" kubernetes/base/postgres-local-storage.yaml | kubectl apply -f -
kubectl get pv postgres-local-pv
kubectl get pvc postgres-data -n ttc-monitor
```

**Verification / Success criteria:** Both PV and PVC show `Bound`. Confirm `postgres.yaml` uses `claimName: postgres-data`. Do not apply the NFS storage manifest to this installation.

## Phase 7 — Deploy PostgreSQL

Apply the PostgreSQL Service and StatefulSet after storage and credentials are ready. Wait for the database pod before running schema changes.

**Purpose:** Start the application database.
**Why it is required:** Migrations and API connections require a healthy PostgreSQL instance.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**

```bash
kubectl apply -n ttc-monitor -f kubernetes/base/postgres.yaml
kubectl get statefulset,pods,service -n ttc-monitor
kubectl rollout status statefulset/postgres -n ttc-monitor --timeout=5m
```

**Verification / Success criteria:** The StatefulSet has its desired ready replica count; its pod runs on the selected worker and its PVC remains `Bound`.

## Phase 8 — Run Alembic migration

Apply the migration Job after PostgreSQL is ready. The Job should use the same database Secret and public API image as the rest of the release.

**Purpose:** Create or update the database schema.
**Why it is required:** The API and ingestion expect current tables.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**

```bash
kubectl apply -n ttc-monitor -f kubernetes/base/migration-job.yaml
kubectl wait -n ttc-monitor --for=condition=complete job/ttc-db-migration --timeout=5m
kubectl logs -n ttc-monitor job/ttc-db-migration
```

**Verification / Success criteria:** The Job completes with no Alembic error. For a release upgrade, use the repository's documented new Job name or delete only a previously completed migration Job before reapplying.

## Phase 9 — Deploy the API

Start the API after the schema is current. The deployment should reference a public GHCR image directly and expose health, readiness, and metrics endpoints.

**Purpose:** Serve reliability data.
**Why it is required:** The dashboard and monitoring stack depend on the API.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**

```bash
kubectl apply -n ttc-monitor -f kubernetes/base/api.yaml
kubectl rollout status -n ttc-monitor deployment/ttc-api --timeout=5m
kubectl port-forward -n ttc-monitor service/ttc-api 8000:8000
# In a second terminal:
curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:8000/ready
```

**Verification / Success criteria:** The deployment is available and both requests succeed. Stop the port-forward when done.

## Phase 10 — Schedule and test ingestion

Apply the ingestion CronJob so new TTC data can be loaded on its configured schedule. Before relying on the schedule, create one manual Job from the CronJob and wait for it to complete. The commands below automatically generate a unique Job name using the current timestamp so repeated tests do not conflict with an existing Job.

**Purpose:** Populate the PostgreSQL database and verify the ingestion workflow.
**Why it is required:** The API and dashboard depend on ingested reliability data. Running a manual Job confirms that source-data access, database connectivity, and ingestion logic are working before waiting for the scheduled CronJob.
**Where to run it:** Kubernetes Controller.

**Procedure / Commands**
Apply the CronJob:
```bash
kubectl apply -n ttc-monitor -f kubernetes/base/ingestion-cronjob.yaml
Verify it:
kubectl get cronjob -n ttc-monitor
Create a unique name for the manual test Job:
JOB_NAME="ingestion-manual-$(date +%Y%m%d%H%M%S)"
Create the Job from the CronJob:
kubectl create job -n ttc-monitor --from=cronjob/ttc-ingestion "$JOB_NAME"
Wait for the Job to finish:
kubectl wait -n ttc-monitor --for=condition=complete "$JOB_NAME" --timeout=15m
Review the ingestion logs:
kubectl logs -n ttc-monitor job "$JOB_NAME"
```

**Verification / Success criteria:** The manual Job completes; logs report processed or inserted records without a database or source-data error.
kubectl get job "$JOB_NAME" -n ttc-monitor

## Phase 11 — Deploy and access the dashboard

Deploy Streamlit after the API is healthy. Access it with a local port-forward unless the cluster already has an approved ingress path.

**Purpose:** Present the reliability data.
**Why it is required:** This is the user-facing view of the ingested records.
**Where to run it:** Kubernetes Controller and local browser.

**Procedure / Commands**

```bash
kubectl apply -n ttc-monitor -f kubernetes/base/dashboard.yaml
kubectl rollout status -n ttc-monitor deployment/ttc-dashboard --timeout=5m
kubectl port-forward --address 0.0.0.0 -n ttc-monitor service/ttc-dashboard 8501:8501
```

**Verification / Success criteria:** Open `http://<CONTROLLER_IP>:8501` and confirm the dashboard renders data. Stop the port-forward after inspection.

## Phase 12 — Optional Prometheus and Grafana

The project uses the kube-prometheus-stack Helm chart to install Prometheus, Grafana, Alertmanager, and the Prometheus Operator. The Helm release name is monitoring because the TTC monitoring resources are designed to work with that release.

**Purpose:** Add monitoring, metrics, alerts, and dashboards.
**Why it is required:** The TTC ServiceMonitor, alert rules, and Grafana dashboard require Prometheus and Grafana to be available in the cluster.
**Where to run it:** Administrator workstation with Helm and `kubectl`.

**Procedure / Commands**

```bash
Install helm:
sudo snap install helm --classic
Add the Prometheus Helm repository:
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
Create the monitoring namespace:
kubectl create namespace monitoring
Install the monitoring stack
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --wait --timeout 10m \
  -f monitoring/monitoring-values.yaml
Verify the monitoring pods:
kubectl get pods -n monitoring
```
Grafana password:
The Helm chart generates the Grafana administrator password automatically. Retrieve it only when needed:
kubectl get secret monitoring-grafana \
  -n monitoring \
  -o jsonpath="{.data.admin-password}" | base64 -d
echo

**Verification / Success criteria:** The release is deployed and Prometheus and Grafana pods are ready. The supplied values file has no Grafana password; retrieve the chart-generated admin password only into a private terminal session or manage it through your own Secret. Do not commit credentials.


## Phase 13 — Optional TTC monitoring resources

Use this phase after Prometheus and Grafana are running.
These manifests add the TTC-specific monitoring configuration that the base kube-prometheus-stack does not include. They tell Prometheus to scrape the TTC API, add TTC alert rules, and automatically provision the TTC Grafana dashboard.

**Purpose:** Add TTC application metrics, alerts, and dashboard visualizations.
**Why it is required:** Prometheus and Grafana are installed by the Helm chart, but they do not automatically know how to monitor the TTC application
**Where to run it:** Kubernetes Controller with kubectl configured

**Procedure / Commands**
Apply the TTC monitoring resources
```bash
kubectl apply -f monitoring/ttc-api-servicemonitor.yaml
kubectl apply -f monitoring/ttc-alerts.yaml
kubectl apply -f monitoring/ttc-grafana-dashboard-configmap.yaml

Verify the ServiceMonitor and alert rules:
kubectl get servicemonitor -n monitoring
kubectl get prometheusrule -n monitoring

Verify the Grafana dashboard ConfigMap:
kubectl get configmap -A -l grafana_dashboard=1
```
Find the Prometheus and Grafana services:
kubectl get service -n monitoring

**Verification / Success criteria:** 

The monitoring integration is complete when:
✓ ServiceMonitor ttc-api exists
✓ PrometheusRule ttc-alerts exists
✓ TTC Grafana dashboard ConfigMap exists
✓ ttc-api target is UP in Prometheus
✓ TTC alert rules are visible in Prometheus
✓ TTC dashboard appears in Grafana
Note: The --address 0.0.0.0 option makes the port-forward reachable from other machines on the same network. Use this only in a trusted lab/testing environment.

Access Prometheus
Run:
kubectl port-forward \
  --address 0.0.0.0 \
  -n monitoring \
  service/monitoring-kube-prometheus-prometheus \
  9090:9090
Keep that terminal open.
From another machine on the same network, open:
http://<KUBERNETES_CONTROLLER_IP>:9090/targets
Find the ttc-api target.
It should show:
UP

Access Grafana
In a second terminal, run:
kubectl port-forward \
  --address 0.0.0.0 \
  -n monitoring \
  service/monitoring-grafana \
  3000:80
From another machine on the same network, open:
http://<KUBERNETES_CONTROLLER_IP>:3000
Retrieve the Grafana admin password if needed:
kubectl get secret monitoring-grafana \
  -n monitoring \
  -o jsonpath="{.data.admin-password}" | base64 -d
echo
Log in with:
Username: admin
Password: <generated password>
Then open Dashboards and confirm the TTC dashboard appears.



## Phase 14 — Validate the installation

Review every layer after ingestion and optional monitoring are complete. A successful pod rollout alone does not confirm the API returns data or that the dashboard can display it.

**Purpose:** Confirm the installation end to end.
**Why it is required:** This catches missing secrets, storage, migrations, ingestion, and service wiring.
**Where to run it:** Administrator workstation and browser.

**Procedure / Commands**

```bash
kubectl get pods,jobs,cronjobs,services,pvc -n ttc-monitor
kubectl get pv postgres-local-pv
kubectl get events -n ttc-monitor --sort-by=.lastTimestamp
kubectl port-forward -n ttc-monitor service/ttc-api 8000:8000
# In a second terminal:
curl -f http://127.0.0.1:8000/health
curl -f http://127.0.0.1:8000/ready
curl -f http://127.0.0.1:8000/api/v1/reliability/summary
```

**Verification / Success criteria:** PVC is `Bound`; database, API, and dashboard are ready; migration and manual ingestion Jobs completed; the summary endpoint returns data; the dashboard renders it. If monitoring was installed, also verify its API target, rule, and dashboard.

## Advanced option — NFS storage

Use NFS only when your cluster has a working NFS server and every eligible worker has the required NFS client support. Provide a separate, writable export for this installation, and validate write access as UID/GID `999:999` with the default `postgres.yaml`. If your NFS server uses a different identity mapping, update the server permissions and PostgreSQL security context together, then verify database startup. In Phase 6, render `kubernetes/base/postgres-nfs-storage.yaml` with real values for `<NFS_SERVER_IP>` and `<NFS_EXPORT_PATH>`, apply it **instead of** the local storage manifest, and verify that PVC `postgres-data` is `Bound` to `postgres-nfs-pv`. Both storage manifests define the same claim, so never apply both. Migrating an existing database between local storage and NFS requires a database backup and restore; changing the PV alone does not move data.
