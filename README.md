# nx-cleanup

Standalone Python tool to clean up a Nexus OSS Docker registry by keeping only the last **N** tags per image path.

Designed for Nexus OSS 3.x running on RHEL. No Groovy scripting API required.

---

## Directory Layout

```
nx-cleanup/
├── cleanup.py          # Core cleanup script
├── run.sh              # Cron/manual wrapper (loads .env, logs output)
├── config.env.example  # Config template — copy to .env
├── logs/               # Auto-created; last 30 run logs kept automatically
└── README.md
```

---

## Quick Start

### 1. Install dependency

```bash
pip3 install requests
# or, for RHEL without internet access:
pip3 install requests --index-url http://your-internal-pypi/simple
```

### 2. Create your config

```bash
cp config.env.example .env
vi .env   # fill in NEXUS_URL, NEXUS_USER, NEXUS_PASS, NEXUS_REPO
```

### 3. Make `run.sh` executable

```bash
chmod +x run.sh
```

### 4. Dry run first (always)

```bash
./run.sh --dry-run
```

This prints exactly what would be deleted — nothing is touched.

### 5. Live run

```bash
./run.sh
```

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

## Scheduling with cron (RHEL)

Edit the cron table for the service account that owns the Nexus cleanup:

```bash
crontab -e
```

Add a daily run at 2 AM:

```cron
0 2 * * * /opt/nx-cleanup/run.sh >> /opt/nx-cleanup/logs/cron.log 2>&1
```

Verify after first scheduled run:

```bash
tail -f /opt/nx-cleanup/logs/cron.log
```

---

## Scheduling with systemd timer (preferred on RHEL 7/8/9)

Create two files:

**`/etc/systemd/system/nx-cleanup.service`**
```ini
[Unit]
Description=Nexus Docker Registry Cleanup

[Service]
Type=oneshot
User=nexus
ExecStart=/opt/nx-cleanup/run.sh
StandardOutput=journal
StandardError=journal
```

**`/etc/systemd/system/nx-cleanup.timer`**
```ini
[Unit]
Description=Run Nexus Docker Cleanup daily at 02:00

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
systemctl daemon-reload
systemctl enable --now nx-cleanup.timer

# Check status
systemctl list-timers nx-cleanup.timer
journalctl -u nx-cleanup.service -f
```

---

## Testing Safely on a Single Production Instance

| Step | Command | Risk |
|---|---|---|
| 1. Full dry-run | `./run.sh --dry-run` | None |
| 2. Scope to one image | `FILTER=appname/develop/one-service ./run.sh --dry-run` | None |
| 3. Create test repo in Nexus UI | `NEXUS_REPO=cleanup-test ./run.sh` | Isolated |
| 4. Live on prod | `./run.sh` | Controlled |

---

## Post-Cleanup — Free Disk Space

Deleting components removes Nexus metadata but **blobs remain on disk** until:

1. **Admin → System → Tasks → Run**: `Docker - Delete unused manifests and images`
2. **Admin → System → Tasks → Run**: `Compact blob store`

Or trigger via API:

```bash
# List tasks
curl -u admin:pass http://nexus:8081/service/rest/v1/tasks

# Run a task by ID
curl -u admin:pass -X POST http://nexus:8081/service/rest/v1/tasks/<id>/run
```

---

## CLI Reference

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
