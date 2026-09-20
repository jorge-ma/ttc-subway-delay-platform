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

Start by cloning the project repository and confirming that the Kubernetes deployment manifests are present. This ensures all later commands are run from a consistent copy of the project and helps identify any missing or renamed files before deployment begins.

Purpose: Obtain the application source code and Kubernetes deployment manifests.
Why it is required: The installation depends on the manifests stored in the repository. Verifying them at the beginning prevents path or file-name issues later in the deployment.
Where to run it: Kubernetes Controller.

Clone the repository:
git clone https://github.com/jorge-ma/ttc-subway-delay-platform.git
Enter the project directory:
cd ttc-subway-delay-platform
List the Kubernetes manifests:
find kubernetes -type f | sort
Verification / Success criteria
Confirm that the following files are present:
kubernetes/base/api.yaml
kubernetes/base/dashboard.yaml
kubernetes/base/ingestion-cronjob.yaml
kubernetes/base/migration-job.yaml
kubernetes/base/namespaces.yaml
kubernetes/base/postgres-local-storage.yaml
kubernetes/base/postgres-nfs-storage.yaml
kubernetes/base/postgres-secret.example.yaml
kubernetes/base/postgres.yaml
If these files are present, the repository is ready for the next deployment phase.

## Phase 2 — Confirm cluster access and create the namespace

Before deploying the application, confirm that kubectl is connected to the correct Kubernetes cluster. Then create the ttc-monitor namespace, which keeps the application resources grouped together and separated from other workloads in the cluster.
Purpose: Confirm the target cluster and prepare the application namespace.
Why it is required: Running commands against the wrong Kubernetes context can modify the wrong cluster. The namespace must also exist before namespaced TTC resources can be created.
Where to run it: Kubernetes Controller.
Procedure / Commands
Confirm the current Kubernetes context:
kubectl config current-context
Confirm the cluster nodes are reachable:
kubectl get nodes -o wide
Create the ttc-monitor namespace:
kubectl create namespace ttc-monitor \
  --dry-run=client \
  -o yaml | kubectl apply -f -
The --dry-run=client -o yaml | kubectl apply -f - pattern makes the command safe to run more than once. If the namespace already exists, Kubernetes keeps it instead of returning an error.
Verification / Success criteria
Verify the namespace:
kubectl get namespace ttc-monitor
Expected status:
NAME          STATUS   AGE
ttc-monitor   Active   ...
Also confirm that the nodes shown by kubectl get nodes -o wide belong to the cluster where you intend to deploy the application.

## Phase 3 — Select a PostgreSQL worker

Because this installation uses a local PersistentVolume, PostgreSQL storage must be tied to one specific Kubernetes worker node. Choose a healthy, schedulable worker with enough local disk space and identify the exact kubernetes.io/hostname label value that Kubernetes will use for local-volume node affinity.
Purpose: Select the worker node that will host the PostgreSQL data directory.
Why it is required: Local PersistentVolumes are physically tied to one node. Kubernetes must schedule the PostgreSQL pod onto that same worker so it can access the local storage path.
Where to run it: Kubernetes Controller.
Procedure / Commands
List the cluster nodes and their labels:
kubectl get nodes --show-labels
Choose the worker you want to use for PostgreSQL, then retrieve its hostname label:
kubectl get node <WORKER_NODE_NAME> \
  -o jsonpath='{.metadata.labels.kubernetes\.io/hostname}{"\n"}'
Review the selected node:
kubectl describe node <WORKER_NODE_NAME>
Confirm that the node is:
- Ready
- not cordoned
- not under disk pressure
- suitable for the PostgreSQL workload
Verification / Success criteria
The selected worker is healthy and schedulable.
Record the value returned by:
kubectl get node <WORKER_NODE_NAME> \
  -o jsonpath='{.metadata.labels.kubernetes\.io/hostname}{"\n"}'
Use that exact value in postgres-local-storage.yaml under the local PV nodeAffinity section.
For example:
values:
  - worker1
The hostname label may match the node name, but do not assume it does—use the value returned by Kubernetes.

## Phase 4 — Prepare the worker directory
Create the PostgreSQL data directory on the worker selected in the previous phase. Because the local PersistentVolume will point directly to this directory, it must exist before PostgreSQL is deployed and its ownership must match the user and group configured for the PostgreSQL container.
Purpose: Prepare writable local storage for PostgreSQL.
Why it is required: A local PersistentVolume does not create the underlying directory automatically. PostgreSQL must be able to read and write this path when the pod starts.
Where to run it: Shell on <WORKER_NODE_NAME>.
1. Confirm the PostgreSQL UID and GID
Before changing directory ownership, check the security context in the repository:
grep -A8 -n "securityContext" kubernetes/base/postgres.yaml
Use the configured runAsUser and runAsGroup values as the source of truth.
For example, if the manifest contains:
runAsUser: 999
runAsGroup: 999
use 999:999 below.
2. Create the PostgreSQL data directory
On the selected worker:
sudo mkdir -p /var/lib/ttc-postgres
Set ownership to match the PostgreSQL container:
sudo chown 999:999 /var/lib/ttc-postgres
Restrict access to the PostgreSQL user:
sudo chmod 700 /var/lib/ttc-postgres
3. Verify the directory
sudo stat -c '%u:%g %a %n' /var/lib/ttc-postgres
Expected output:
999:999 700 /var/lib/ttc-postgres
Verification / Success criteria
The directory:
/var/lib/ttc-postgres
exists on the selected worker, has mode 700, and its UID/GID match the runAsUser and runAsGroup values in kubernetes/base/postgres.yaml.
Important: Do not assume 999:999 if you modify the PostgreSQL image or security context. Always make the host-directory ownership match the values configured in postgres.yaml.

## Phase 5 — Create the PostgreSQL Secret

Phase 5 — Create the PostgreSQL Secret
Create a local copy of the example Secret and replace the placeholder password with a strong value that will be used by PostgreSQL and the application. The populated Secret file should remain local to the administrator and must never be committed to Git.
Purpose: Provide the database credentials required by PostgreSQL and the TTC application.
Why it is required: PostgreSQL and the application must use the same database name, username, and password. Keeping these values in a Kubernetes Secret avoids hard-coding credentials directly into application manifests.
Where to run it: Kubernetes Controller.
1. Create a protected local Secret file
Set restrictive default permissions for newly created files:
umask 077
Copy the example Secret:
cp kubernetes/base/postgres-secret.example.yaml \
  kubernetes/base/postgres-secret.yaml
Ensure only your user can read or modify it:
chmod 600 kubernetes/base/postgres-secret.yaml
2. Edit the Secret
Open the file:
nano kubernetes/base/postgres-secret.yaml
Replace:
POSTGRES_PASSWORD: CHANGE_ME
with a strong, unique password.
Do not change the database name or username unless you also update the related application configuration.
3. Apply the Secret
kubectl apply -f kubernetes/base/postgres-secret.yaml
Verify that Kubernetes created it:
kubectl get secret postgres-secret -n ttc-monitor
4. Confirm the populated file is ignored by Git
git check-ignore kubernetes/base/postgres-secret.yaml
Expected output:
kubernetes/base/postgres-secret.yaml
Also check:
git status --short
The populated postgres-secret.yaml file should not appear.
Verification / Success criteria
The phase is complete when:
- postgres-secret exists in the ttc-monitor namespace
- the local Secret file is mode 600
- git check-ignore confirms the populated file is ignored
- git status does not list the populated Secret
Important: Kubernetes Secrets are encoded, not encrypted by default. Protect both the local Secret file and access to the Kubernetes cluster, and never paste the password into documentation, issue reports, screenshots, or logs.

## Phase 6 — Create the local PV and PVC

Phase 6 — Create the local PV and PVC
Create the PostgreSQL PersistentVolume and PersistentVolumeClaim using the local-storage template. The manifest contains a <WORKER_NODE_NAME> placeholder, which should be replaced at deployment time with the exact kubernetes.io/hostname value identified in Phase 3.
The template keeps the placeholder in Git, while the rendered manifest is sent directly to Kubernetes. The PVC is named postgres-data, and the PV uses a Retain reclaim policy so the underlying database files are not deleted automatically if the claim is removed.
Purpose: Provide persistent local storage for PostgreSQL.
Why it is required: PostgreSQL data must survive pod restarts and replacement. Because this installation uses local storage, the volume must also be tied to the worker node where /var/lib/ttc-postgres was created.
Where to run it: Kubernetes Controller.
1. Set the selected worker hostname
Use the exact hostname label recorded in Phase 3:
WORKER_NODE_NAME=<HOSTNAME_LABEL_FROM_PHASE_3>
For example:
WORKER_NODE_NAME=worker1
Confirm the value:
echo "$WORKER_NODE_NAME"
2. Apply the local storage manifest
Render the worker name into the manifest and apply it directly:
sed "s/<WORKER_NODE_NAME>/$WORKER_NODE_NAME/" \
  kubernetes/base/postgres-local-storage.yaml \
  | kubectl apply -f -
This does not modify the tracked template in the repository.
3. Verify the PersistentVolume
kubectl get pv postgres-local-pv
4. Verify the PersistentVolumeClaim
kubectl get pvc postgres-data -n ttc-monitor
Both should eventually show:
STATUS   Bound
5. Confirm PostgreSQL uses the correct claim
grep -n "claimName" kubernetes/base/postgres.yaml
Expected value:
claimName: postgres-data
Verification / Success criteria
The phase is complete when:
- postgres-local-pv exists
- postgres-data exists in the ttc-monitor namespace
- both PV and PVC show Bound
- postgres.yaml references claimName: postgres-data
- the local PV is pinned to the worker selected in Phase 3
Important: Do not apply postgres-nfs-storage.yaml for this installation. Use only one PostgreSQL storage option at a time.

## Phase 7 — Deploy PostgreSQL

Deploy the PostgreSQL Service and StatefulSet after the namespace, Secret, and persistent storage are ready. The StatefulSet will mount the postgres-data PVC created in the previous phase and start the database on the worker selected for local storage.
Wait for PostgreSQL to become ready before running Alembic migrations or deploying components that depend on the database.
Purpose: Start the PostgreSQL database used by the TTC Reliability Monitor.
Why it is required: Database migrations, ingestion, and API services all depend on a healthy PostgreSQL instance.
Where to run it: Kubernetes Controller.
1. Deploy PostgreSQL
Apply the PostgreSQL manifest:
kubectl apply -f kubernetes/base/postgres.yaml
2. Check the database resources
kubectl get statefulset,pods,service -n ttc-monitor
You should see:
- StatefulSet postgres
- Pod postgres-0
- Service postgres
3. Wait for the StatefulSet to become ready
kubectl rollout status \
  statefulset/postgres \
  -n ttc-monitor \
  --timeout=5m
Expected result:
statefulset rolling update complete ...
4. Confirm the PostgreSQL pod is running
kubectl get pod postgres-0 -n ttc-monitor -o wide
Confirm that:
- STATUS is Running
- READY is 1/1
- the pod is running on the worker selected in Phase 3
5. Confirm the PVC is still bound
kubectl get pvc postgres-data -n ttc-monitor
Expected:
STATUS   Bound
6. Optional: check PostgreSQL startup logs
kubectl logs postgres-0 -n ttc-monitor
Look for a message indicating PostgreSQL is ready to accept connections.
Verification / Success criteria
The phase is complete when:
- StatefulSet postgres reports 1/1 ready
- Pod postgres-0 is Running
- the pod is scheduled on the selected local-storage worker
- Service postgres exists on port 5432
- PVC postgres-data remains Bound
- PostgreSQL logs show the database started successfully
If the pod stays in Pending, verify the local PV node affinity and the selected worker. If it enters CrashLoopBackOff, check the pod logs and confirm the host-directory ownership matches the UID/GID configured in postgres.yaml.

## Phase 8 — Run Alembic migration

Run the database migration after PostgreSQL is healthy. The migration Job uses Alembic to create or update the database schema required by the API and ingestion components.
The Job should use the same PostgreSQL Secret and application image version as the rest of the deployment.
Purpose: Create or update the PostgreSQL schema used by the TTC Reliability Monitor.
Why it is required: The API and ingestion components expect the required tables and schema objects to exist before they start using the database.
Where to run it: Kubernetes Controller.
1. Apply the migration Job
kubectl apply -f kubernetes/base/migration-job.yaml
2. Wait for the migration to complete
kubectl wait \
  -n ttc-monitor \
  --for=condition=complete \
  job/ttc-db-migration \
  --timeout=5m
3. Review the migration logs
kubectl logs \
  -n ttc-monitor \
  job/ttc-db-migration
You should see Alembic connect to PostgreSQL and apply the expected migration revision without errors.
4. Confirm the Job status
kubectl get job ttc-db-migration -n ttc-monitor
Expected result:
COMPLETIONS   1/1
Verification / Success criteria
The phase is complete when:
- Job ttc-db-migration shows 1/1 completion
- the migration logs contain no Alembic or PostgreSQL errors
- the expected migration revision is applied successfully
Important: A Kubernetes Job with the same name cannot simply be recreated if it already exists. For a future upgrade, use the migration procedure documented for that release, or remove only a previously completed migration Job before applying a new one.
## Phase 9 — Deploy the API

Deploy the FastAPI service after the database schema is ready. The API exposes TTC reliability data to the dashboard and also provides health, readiness, and Prometheus metrics endpoints.
Because the GHCR images are public, the deployment can pull the API image directly without an image pull secret.
Purpose: Start the application API that serves reliability data.
Why it is required: The Streamlit dashboard reads data from the API, and Prometheus uses the API's metrics endpoint for application monitoring.
Where to run it: Kubernetes Controller.
1. Deploy the API
kubectl apply -f kubernetes/base/api.yaml
2. Wait for the deployment to become ready
kubectl rollout status \
  deployment/ttc-api \
  -n ttc-monitor \
  --timeout=5m
3. Verify the API pods and service
kubectl get deployment,pods,service -n ttc-monitor
Confirm that the ttc-api deployment has all expected replicas ready and that the ttc-api Service exists.
4. Port-forward the API for testing
Run:
kubectl port-forward \
  -n ttc-monitor \
  service/ttc-api \
  8000:8000
Keep this terminal open while testing.
5. Test the health endpoints
In a second terminal, run:
curl -f http://127.0.0.1:8000/health
Then:
curl -f http://127.0.0.1:8000/ready
If both commands return successfully, the API is healthy and ready.
Verification / Success criteria
The phase is complete when:
- the ttc-api deployment is available
- all API pods are Running and Ready
- the ttc-api Service exists
- /health returns successfully
- /ready returns successfully
Stop the port-forward with Ctrl+C when testing is complete.

## Phase 10 — Schedule and test ingestion

Phase 10 — Schedule and test ingestion
Apply the ingestion CronJob so TTC data can be loaded automatically on its configured schedule. Before relying on the schedule, create one manual Job from the CronJob and verify that it completes successfully.
The commands below generate a unique Job name using the current timestamp so the test can be repeated without conflicting with an existing Job.
Purpose: Populate the PostgreSQL database and verify the ingestion workflow.
Why it is required: The API and dashboard depend on ingested reliability data. A manual test confirms that source-data access, database connectivity, and ingestion logic are working before the scheduled CronJob is left to run automatically.
Where to run it: Kubernetes Controller.
1. Apply the ingestion CronJob
kubectl apply -f kubernetes/base/ingestion-cronjob.yaml
2. Verify the CronJob
kubectl get cronjob -n ttc-monitor
Confirm that ttc-ingestion is listed.
3. Generate a unique name for the manual test Job
JOB_NAME="ingestion-manual-$(date +%Y%m%d%H%M%S)"
Verify the generated name:
echo "$JOB_NAME"
Example:
ingestion-manual-20260919201530
4. Create a manual Job from the CronJob
kubectl create job \
  -n ttc-monitor \
  --from=cronjob/ttc-ingestion \
  "$JOB_NAME"
5. Wait for the ingestion Job to complete
kubectl wait \
  -n ttc-monitor \
  --for=condition=complete \
  "job/$JOB_NAME" \
  --timeout=15m
6. Review the ingestion logs
kubectl logs \
  -n ttc-monitor \
  "job/$JOB_NAME"
7. Confirm the Job status
kubectl get job "$JOB_NAME" -n ttc-monitor
Expected result:
COMPLETIONS   1/1
Verification / Success criteria
The phase is complete when:
- the ttc-ingestion CronJob exists
- the manually created Job reaches Complete
- the Job shows 1/1 completion
- the ingestion logs report successfully processed or inserted records
- no source-data or PostgreSQL connection errors are reported
- 
## Phase 11 — Deploy and access the dashboard

Deploy the Streamlit dashboard after the API is healthy and the ingestion workflow has populated the database. The dashboard connects to the API and provides the user-facing view of the TTC reliability data.
For a simple lab installation, use kubectl port-forward to make the dashboard reachable from another machine on the same network as the Kubernetes controller.
Purpose: Provide the user-facing dashboard for TTC reliability data.
Why it is required: The dashboard is the main interface for viewing the reliability metrics collected by the ingestion process and exposed by the API.
Where to run it: Kubernetes Controller and a browser on another machine in the same network.
1. Deploy the dashboard
kubectl apply -f kubernetes/base/dashboard.yaml
2. Wait for the deployment to become ready
kubectl rollout status \
  deployment/ttc-dashboard \
  -n ttc-monitor \
  --timeout=5m
3. Verify the dashboard pod and service
kubectl get deployment,pods,service -n ttc-monitor
Confirm that the ttc-dashboard deployment is ready and its pod is Running.
4. Make the dashboard reachable from the local network
Run:
kubectl port-forward \
  --address 0.0.0.0 \
  -n ttc-monitor \
  service/ttc-dashboard \
  8501:8501
Keep this terminal open while testing.
You should see:
Forwarding from 0.0.0.0:8501 -> 8501
5. Open the dashboard
From another machine on the same network, browse to:
http://<KUBERNETES_CONTROLLER_IP>:8501
For example:
http://10.10.10.180:8501
Verification / Success criteria
The phase is complete when:
- the ttc-dashboard deployment is available
- the dashboard pod is Running and Ready
- the dashboard service exists
- the dashboard opens successfully in a browser
- reliability data is displayed
Stop the port-forward with Ctrl+C when testing is complete.
Note: --address 0.0.0.0 exposes the forwarded port on the controller's network interfaces. Use this method only in a trusted lab or test network.

## Phase 12 — Optional Prometheus and Grafana

Use this phase only if the Kubernetes cluster does not already provide Prometheus and Grafana.
The project uses the kube-prometheus-stack Helm chart, which installs Prometheus, Grafana, Alertmanager, the Prometheus Operator, and supporting monitoring components. The Helm release name is monitoring because the TTC-specific monitoring resources in the next phase are designed to work with that release.
Purpose: Add monitoring, metrics, alerting, and dashboards.
Why it is required: The TTC ServiceMonitor, alert rules, and Grafana dashboard depend on Prometheus and Grafana being available in the cluster.
Where to run it: Kubernetes Controller with kubectl access.
1. Install Helm
If Helm is not already installed and the controller uses Snap:
sudo snap install helm --classic
Verify:
helm version
If Helm is already installed, skip this step.
2. Add the Prometheus Community Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
Update the local Helm repository index:
helm repo update
3. Create the monitoring namespace
kubectl create namespace monitoring
If the namespace already exists, continue to the next step.
4. Install the monitoring stack
Run this command from the repository root:
helm upgrade --install monitoring \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --wait \
  --timeout 10m \
  -f monitoring/monitoring-values.yaml
This installs Prometheus, Grafana, Alertmanager, the Prometheus Operator, and the other components included in kube-prometheus-stack.
5. Verify the monitoring pods
kubectl get pods -n monitoring
Wait until the main monitoring components are Running and ready.
You should see components such as:
monitoring-grafana-...
monitoring-kube-prometheus-operator-...
prometheus-monitoring-kube-prometheus-prometheus-0
alertmanager-monitoring-kube-prometheus-alertmanager-0
monitoring-kube-state-metrics-...
monitoring-prometheus-node-exporter-...
6. Verify the Helm release
helm list -n monitoring
The monitoring release should show:
STATUS
deployed
7. Retrieve the Grafana administrator password
The Helm chart generates the Grafana administrator password automatically.
Retrieve it only when you need to log in:
kubectl get secret monitoring-grafana \
  -n monitoring \
  -o jsonpath="{.data.admin-password}" | base64 -d
echo
The default Grafana username is:
admin
Do not store the generated password in the repository or documentation.
Verification / Success criteria
The phase is complete when:
- Helm is installed and working
- the monitoring namespace exists
- the monitoring Helm release shows deployed
- Prometheus is running
- Grafana is running
- Alertmanager and the Prometheus Operator are running
- the Grafana administrator password can be retrieved from the Kubernetes Secret
Important: The supplied monitoring-values.yaml does not contain a Grafana password. The password is generated by the Helm chart and stored in a Kubernetes Secret. Retrieve it only when needed and do not commit credentials to Git.

## Phase 13 — Optional TTC monitoring resources

Use this phase after Prometheus and Grafana are running.
The manifests in the monitoring/ directory add the TTC-specific observability configuration that the base kube-prometheus-stack does not provide. They configure Prometheus to scrape the TTC API, add TTC alert rules, and automatically provision the TTC Grafana dashboard.
Purpose: Add TTC application metrics, alerts, and dashboard visualizations.
Why it is required: Prometheus and Grafana are installed by the Helm chart, but they do not automatically know how to monitor the TTC application.
Where to run it: Kubernetes Controller with kubectl configured.
1. Apply the TTC monitoring resources
kubectl apply -f monitoring/ttc-api-servicemonitor.yaml
kubectl apply -f monitoring/ttc-alerts.yaml
kubectl apply -f monitoring/ttc-grafana-dashboard-configmap.yaml
2. Verify the ServiceMonitor
kubectl get servicemonitor -n monitoring
Confirm that ttc-api appears.
3. Verify the alert rules
kubectl get prometheusrule -n monitoring
Confirm that ttc-alerts appears.
4. Verify the Grafana dashboard ConfigMap
kubectl get configmap -n monitoring -l grafana_dashboard=1
Confirm that the TTC dashboard ConfigMap appears.
5. Find the Prometheus and Grafana services
kubectl get service -n monitoring
With the monitoring Helm release name used in this guide, the services will normally be:
monitoring-kube-prometheus-prometheus
monitoring-grafana
6. Access Prometheus
Run:
kubectl port-forward \
  --address 0.0.0.0 \
  -n monitoring \
  service/monitoring-kube-prometheus-prometheus \
  9090:9090
Keep this terminal open.
From another machine on the same network, open:
http://<KUBERNETES_CONTROLLER_IP>:9090/targets
Find the ttc-api target and confirm its state is:
UP
7. Access Grafana
In a second terminal, run:
kubectl port-forward \
  --address 0.0.0.0 \
  -n monitoring \
  service/monitoring-grafana \
  3000:80
From another machine on the same network, open:
http://<KUBERNETES_CONTROLLER_IP>:3000
If needed, retrieve the Grafana administrator password:
kubectl get secret monitoring-grafana \
  -n monitoring \
  -o jsonpath="{.data.admin-password}" | base64 -d
echo
Log in with:
Username: admin
Password: <generated password>
Then open Dashboards and confirm that the TTC dashboard appears.
Verification / Success criteria
The monitoring integration is complete when:
- ServiceMonitor ttc-api exists
- PrometheusRule ttc-alerts exists
- the TTC Grafana dashboard ConfigMap exists
- the ttc-api target is UP in Prometheus
- TTC alert rules are visible in Prometheus
- the TTC dashboard appears in Grafana
Note: --address 0.0.0.0 makes the port-forward reachable from other machines on the same network. Use this only in a trusted lab or testing environment.

## Phase 14 — Validate the installation

Perform a final end-to-end check after the application components are deployed and ingestion has completed. A successful pod rollout confirms only that containers started; this phase verifies that storage, database initialization, ingestion, API responses, dashboard access, and optional monitoring all work together.
Purpose: Confirm the complete TTC Reliability Monitor installation is functioning correctly.
Why it is required: This final validation catches issues that may not be visible from pod status alone, including storage problems, failed migrations, missing ingestion data, service connectivity issues, or monitoring misconfiguration.
Where to run it: Kubernetes Controller and browser.
1. Review application resources
kubectl get pods,jobs,cronjobs,services,pvc -n ttc-monitor
Confirm that:
- PostgreSQL is Running
- API pods are Running and Ready
- dashboard pod is Running and Ready
- migration Job completed
- manual ingestion Job completed
- ingestion CronJob exists
- PVC postgres-data is Bound
2. Verify the local PersistentVolume
kubectl get pv postgres-local-pv
Confirm that the volume is bound to the postgres-data claim.
3. Review recent application events
kubectl get events \
  -n ttc-monitor \
  --sort-by=.lastTimestamp
Review recent events for failed mounts, image pull errors, scheduling problems, probe failures, or container restarts.
4. Test the API
Start a local port-forward:
kubectl port-forward \
  -n ttc-monitor \
  service/ttc-api \
  8000:8000
Keep this terminal open.
In a second terminal, test the health endpoint:
curl -f http://127.0.0.1:8000/health
Test readiness:
curl -f http://127.0.0.1:8000/ready
Confirm that reliability data is available:
curl -f http://127.0.0.1:8000/api/v1/reliability/summary
The summary endpoint should return populated reliability data rather than an empty dataset.
5. Verify the dashboard
If the dashboard port-forward is not already running:
kubectl port-forward \
  --address 0.0.0.0 \
  -n ttc-monitor \
  service/ttc-dashboard \
  8501:8501
From another machine on the same network, open:
http://<KUBERNETES_CONTROLLER_IP>:8501
Confirm that the dashboard loads and displays reliability data returned by the API.
6. Optional monitoring validation
If Prometheus and Grafana were installed, confirm the TTC monitoring resources:
kubectl get servicemonitor -n monitoring ttc-api
kubectl get prometheusrule -n monitoring ttc-alerts
kubectl get configmap -n monitoring -l grafana_dashboard=1
Then verify:
- the ttc-api target is UP in Prometheus
- TTC alert rules are visible
- the TTC dashboard appears in Grafana
Verification / Success criteria
The installation is complete when:
- PVC postgres-data is Bound
- PostgreSQL is healthy
- the Alembic migration Job completed successfully
- the manual ingestion Job completed successfully
- API pods are ready
- /health succeeds
- /ready succeeds
- /api/v1/reliability/summary returns populated data
- the dashboard loads and displays reliability information
- if monitoring is enabled, the TTC Prometheus target is UP, alert rules are loaded, and the Grafana dashboard is available
Stop temporary port-forwards with Ctrl+C when validation is complete.
Advanced option — NFS storage
The default installation uses a local PersistentVolume because it requires no external storage infrastructure. NFS can be used instead when the cluster already has access to a reliable NFS server.
Use this option only when:
- an NFS server is available
- every worker that may run PostgreSQL has NFS client support installed
- a dedicated writable export is available for this installation
- the NFS permissions match the PostgreSQL container UID/GID
1. Prepare a dedicated NFS export
Use a separate NFS directory for this deployment. Do not reuse a PostgreSQL data directory that is actively mounted by another PostgreSQL instance.
With the default postgres.yaml, verify the PostgreSQL UID and GID first:
grep -A8 -n "securityContext" kubernetes/base/postgres.yaml
If the manifest uses:
runAsUser: 999
runAsGroup: 999
the NFS export must allow that identity to read and write the data directory.
If you change the PostgreSQL image or security context, adjust the NFS ownership and permissions to match.
2. Confirm NFS client support
On every worker that may host PostgreSQL, verify the NFS mount helper exists:
command -v mount.nfs
If it is missing on Ubuntu/Debian:
sudo apt update
sudo apt install -y nfs-common
3. Configure the NFS storage manifest
Do not modify the tracked template permanently. Render the placeholders at deployment time.
Set the NFS server and export path:
NFS_SERVER=<NFS_SERVER_IP>
NFS_EXPORT=<NFS_EXPORT_PATH>
Apply the rendered manifest:
sed \
  -e "s|<NFS_SERVER_IP>|$NFS_SERVER|" \
  -e "s|<NFS_EXPORT_PATH>|$NFS_EXPORT|" \
  kubernetes/base/postgres-nfs-storage.yaml \
  | kubectl apply -f -
4. Verify the NFS PV and PVC
kubectl get pv postgres-nfs-pv
kubectl get pvc postgres-data -n ttc-monitor
The PVC should show:
STATUS   Bound
Important storage rules
Both the local-storage and NFS manifests create the same PVC:
postgres-data
Therefore:
- apply either postgres-local-storage.yaml
- or postgres-nfs-storage.yaml
- never apply both for the same installation
Changing the PV definition does not migrate PostgreSQL data. To move an existing database between local storage and NFS, perform a proper PostgreSQL backup and restore.

Prometheus
kubectl port-forward \
  --address 0.0.0.0 \
  -n monitoring \
  service/monitoring-kube-prometheus-prometheus \
  9090:9090
Open the Prometheus interface:
http://<KUBERNETES_CONTROLLER_IP>:9090
To verify the TTC API target:
http://<KUBERNETES_CONTROLLER_IP>:9090/targets
The ttc-api target should show:
UP
Grafana
kubectl port-forward \
  --address 0.0.0.0 \
  -n monitoring \
  service/monitoring-grafana \
  3000:80
Open:
http://<KUBERNETES_CONTROLLER_IP>:3000
Grafana username:
admin
Retrieve the generated administrator password with:
kubectl get secret monitoring-grafana \
  -n monitoring \
  -o jsonpath="{.data.admin-password}" | base64 -d
echo
Example
If the Kubernetes controller IP is:
192.168.10.20
the URLs would be:
TTC Dashboard:      http://192.168.10.20:8501
Prometheus:         http://192.168.10.20:9090
Prometheus targets: http://192.168.10.20:9090/targets
Grafana:            http://192.168.10.20:3000
Note: --address 0.0.0.0 exposes the forwarded ports on the Kubernetes controller's network interfaces. Use these commands only on a trusted lab or test network, and stop each port-forward with Ctrl+C when finished.
