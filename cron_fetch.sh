#!/usr/bin/env bash
# cron_fetch.sh — run OUTSIDE any Claude sandbox (plain OS cron).
# Fetches MCF listings into candidates.json for the Claude routine to score.
#
# Crontab (daily 04:00 SGT (plan-B only; the routine fetches directly now)):
#   0 4 * * * /full/path/to/job-scan/cron_fetch.sh >> /full/path/to/job-scan/scan.log 2>&1
#
# Windows: use Task Scheduler to run:  bash cron_fetch.sh  (or just the python line)

set -euo pipefail
cd "$(dirname "$0")"

echo "=== job-scan cron fetch: $(date -u +%FT%TZ) ==="
python3 mcf_job_scan.py

# ── CLOUD-ROUTINE VARIANT ────────────────────────────────────────────────
# If your Claude scheduled task runs in the CLOUD (pulls from GitHub), it can
# only see candidates.json if we push it. Uncomment the block below.
# If your Claude task runs LOCALLY (Cowork/Desktop) it reads the file directly
# and you should leave this commented out.
#
# git add candidates.json
# git commit -m "weekly scan data $(date -u +%F)" || echo "nothing to commit"
# git push
