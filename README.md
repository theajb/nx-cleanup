# nx-cleanup

Standalone Python tool to clean up a Nexus OSS Docker registry by keeping only the last **N** tags per image path.

Designed for Nexus OSS 3.x. No Groovy scripting API required.

---

## Directory Layout

```
nx-cleanup/
├── cleanup.py                  # Core cleanup script
├── Jenkinsfile.nexus-cleanup   # Jenkins Pipeline definition
├── nexus-cleanup-agent.yaml    # Kubernetes Pod template for Jenkins in GKE
└── README.md
```

---

## Jenkins Pipeline Setup (GKE)

This project is fully configured to run inside a Jenkins Pipeline hosted on Google Kubernetes Engine (GKE).

### 1. Requirements in Jenkins
1. **Kubernetes Plugin:** Installed and configured so Jenkins can spin up dynamic build pods.
2. **Credentials:** A "Username with password" credential named `nexus-admin-creds` containing your Nexus admin credentials.

### 2. Job Configuration
1. Create a new **Pipeline Job** in Jenkins.
2. Point the Pipeline section to this Git repository.
3. Set the Script Path to `Jenkinsfile.nexus-cleanup`.

### 3. Running the Job
When you run the job for the first time, Jenkins will load the pipeline and present you with these parameters on future runs:

* **`DRY_RUN`** (Boolean - Default: `true`): Safely preview what would be deleted.
* **`FILTER`** (String - Default: *Empty*): Test against a single image or branch (e.g. `appname/develop`).
* **`KEEP_N`** (String - Default: `2`): The number of tags to retain per image path.

---

## How the Directory Structure Is Handled

Your registry paths follow this structure:

```
v2 / appname / <branch> / <microservice> / manifests / <tag>
```

Nexus stores this as a single component with:

| Nexus field | Value |
|---|---|
| `name`    | `appname/develop/payments-service` |
| `version` | `20250318.abc1f23` |

The full nested path becomes the key — cleanup is applied **per image path**, regardless of depth. Each unique path is treated independently.

**Example — 4 image paths, each on a different branch:**

```
appname/develop/payments-service         → 7 tags → keep 2, delete 5
appname/master/payments-service          → 3 tags → keep 2, delete 1
appname/develop-sprint/auth-service      → 2 tags → RETAIN ALL (at threshold)
appname/master-sprint/notification-svc   → 1 tag  → RETAIN ALL (below threshold)
```

---

## Post-Cleanup — Free Disk Space

Deleting components removes Nexus metadata but **blobs remain on disk** until you schedule the following built-in Nexus Admin System Tasks:

1. **Admin → System → Tasks → Run**: `Docker - Delete unused manifests and images`
2. **Admin → System → Tasks → Run**: `Compact blob store`

Ensure these two tasks are scheduled to run gracefully *after* the Jenkins pipeline finishes.

---

## CLI Reference (For manual testing)

```
usage: cleanup.py [-h] --url URL --repo REPO --user USER --password PASSWORD
                  [--keep N] [--dry-run] [--filter FILTER] [--verbose]

  --url        Nexus base URL (e.g. http://nexus.example.com:8081)
  --repo       Docker hosted repo name (e.g. dkr-4-test)
  --user       Nexus username
  --password   Nexus password
  --keep N     Tags to retain per image path (default: 2)
  --dry-run    Preview only — nothing is deleted
  --filter     Only process image paths containing this substring
  --verbose    Also log each retained tag
```
