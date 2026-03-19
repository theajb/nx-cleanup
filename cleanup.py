#!/usr/bin/env python3
"""
cleanup.py
----------
Nexus OSS Docker Registry Cleanup
Keeps the last N tags per unique image path.

Tag format: YYYYMMDD.commithash  (e.g. 20250318.abc1f23)
This sorts correctly in reverse-lexicographic order — no date parsing needed.

How the directory structure maps to Nexus API:
  Docker push path  : v2/appname/develop/microservice-x/manifests/20250318.abc1f23
  Nexus component   :
      name    → "appname/develop/microservice-x"   (full nested path as-is)
      version → "20250318.abc1f23"                 (tag)

Each unique `name` is an independent image — keep logic applies per image,
regardless of nesting depth.

Usage:
  python3 cleanup.py --help
  python3 cleanup.py --dry-run            # preview only, nothing deleted
  python3 cleanup.py                      # live delete
"""

import argparse
import sys
import logging
import requests
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("nx-cleanup")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Nexus OSS Docker cleanup — keep last N tags per image path."
    )
    p.add_argument("--url",      required=True,               help="Nexus base URL (e.g. http://nexus.example.com:8081)")
    p.add_argument("--repo",     required=True,               help="Docker hosted repo name (e.g. dkr-4-test)")
    p.add_argument("--user",     required=True,               help="Nexus username")
    p.add_argument("--password", required=True,               help="Nexus password")
    p.add_argument("--keep",     default=2, type=int,         help="Tags to keep per image path (default: 2)")
    p.add_argument("--dry-run",  action="store_true",         help="Preview only — nothing is deleted")
    p.add_argument("--filter",   default=None,                help="Only process image paths containing this string")
    p.add_argument("--verbose",  action="store_true",         help="Show every retained tag as well")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Nexus REST helpers
# ---------------------------------------------------------------------------

def list_all_components(session, nexus_url, repo):
    """
    Pages through /service/rest/v1/components until continuationToken is None.
    Nexus returns max 50 items per page.
    """
    components = []
    token = None
    page  = 0

    while True:
        params = {"repository": repo}
        if token:
            params["continuationToken"] = token

        try:
            r = session.get(
                f"{nexus_url}/service/rest/v1/components",
                params=params,
                timeout=30,
            )
            r.raise_for_status()
        except requests.exceptions.RequestException as e:
            log.error("Failed fetching page %d: %s", page + 1, e)
            sys.exit(1)

        data  = r.json()
        items = data.get("items", [])
        components.extend(items)
        token  = data.get("continuationToken")
        page  += 1
        log.info("Fetched page %d — %d items (running total: %d)", page, len(items), len(components))

        if not token:
            break

    return components


def delete_component(session, nexus_url, comp_id, label, dry_run):
    if dry_run:
        log.info("  [DRY RUN] Would delete: %s", label)
        return True

    try:
        r = session.delete(
            f"{nexus_url}/service/rest/v1/components/{comp_id}",
            timeout=30,
        )
        if r.status_code == 204:
            log.info("  [DELETED]  %s", label)
            return True
        else:
            log.error("  [ERROR]    %s — HTTP %d", label, r.status_code)
            return False
    except requests.exceptions.RequestException as e:
        log.error("  [ERROR]    %s — %s", label, e)
        return False


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def group_components(components, path_filter):
    """
    Groups components by their Nexus `name` field (= full Docker image path).

    Examples of `name` values you will see:
      "appname/develop/payments-service"
      "appname/master/payments-service"
      "appname/develop-sprint/auth-service"
      "appname/master-sprint/notification-service"

    The nesting depth does not matter — the full path is the key.
    """
    grouped = defaultdict(list)
    skipped = 0

    for c in components:
        name    = c.get("name", "").strip()
        version = c.get("version", "").strip()

        if not name or not version:
            skipped += 1
            continue

        if path_filter and path_filter not in name:
            continue

        grouped[name].append(c)

    if skipped:
        log.warning("Skipped %d component(s) with missing name or version.", skipped)

    return grouped


def run_cleanup(session, nexus_url, grouped, keep_n, dry_run, verbose):
    total_images   = len(grouped)
    retained_count = 0
    deleted_count  = 0
    error_count    = 0

    sep = "=" * 72
    log.info(sep)
    log.info(
        "%sProcessing %d image path(s) — keeping last %d tag(s) each",
        "[DRY RUN] " if dry_run else "",
        total_images,
        keep_n,
    )
    log.info(sep)

    for image_path, items in sorted(grouped.items()):
        tag_count = len(items)

        # Sort descending: YYYYMMDD.hash → lexicographic order works correctly
        sorted_items = sorted(items, key=lambda x: x.get("version", ""), reverse=True)

        if tag_count <= keep_n:
            log.info("[RETAIN ALL] %-50s (%d tag(s))", image_path, tag_count)
            for item in sorted_items:
                log.info("  [KEEP]     %s:%s", image_path, item.get("version", "?"))
            retained_count += tag_count
            continue

        to_keep   = sorted_items[:keep_n]
        to_delete = sorted_items[keep_n:]

        log.info("[IMAGE] %s", image_path)
        log.info(
            "  Tags: total=%d  keep=%d  delete=%d",
            tag_count, len(to_keep), len(to_delete),
        )

        for item in to_keep:
            log.info("  [KEEP]     %s:%s", image_path, item.get("version", "?"))

        for item in to_delete:
            version = item.get("version", "?")
            label   = f"{image_path}:{version}"
            ok = delete_component(session, nexus_url, item["id"], label, dry_run)
            if ok:
                deleted_count += 1
            else:
                error_count += 1

        retained_count += len(to_keep)

    log.info(sep)
    log.info("Results:")
    log.info("  Unique image paths : %d", total_images)
    log.info("  Tags retained      : %d", retained_count)
    log.info(
        "  Tags %-14s: %d",
        "would be deleted" if dry_run else "deleted",
        deleted_count,
    )
    if error_count:
        log.warning("  Errors             : %d", error_count)
    log.info(sep)

    if dry_run:
        log.info("DRY RUN complete — no changes were made.")
        log.info("Remove --dry-run flag to apply deletions.")
    else:
        log.info("Cleanup complete.")
        log.info("")
        log.info("NEXT STEPS — run these Nexus tasks to reclaim disk space:")
        log.info("  1. Admin > System > Tasks > 'Docker - Delete unused manifests and images'")
        log.info("  2. Admin > System > Tasks > 'Compact blob store'")

    return error_count == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    log.info("Nexus OSS Docker Cleanup")
    log.info("  URL       : %s", args.url)
    log.info("  Repo      : %s", args.repo)
    log.info("  Keep last : %d tag(s) per image", args.keep)
    log.info("  Filter    : %s", args.filter or "(none — all images)")
    log.info("  Mode      : %s", "DRY RUN" if args.dry_run else "LIVE")
    log.info("")

    session      = requests.Session()
    session.auth = (args.user, args.password)

    log.info("Fetching all components from '%s'...", args.repo)
    components = list_all_components(session, args.url, args.repo)
    log.info("Total components: %d", len(components))
    log.info("")

    grouped = group_components(components, args.filter)
    success = run_cleanup(
        session, args.url, grouped,
        args.keep, args.dry_run, args.verbose
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
