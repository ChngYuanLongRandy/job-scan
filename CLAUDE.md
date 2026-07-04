# CLAUDE.md — job-scan

Personal weekly job-search automation for Randy Chng (Singapore).

## What this project does
Once a week it pulls fresh software-engineering / full-stack roles from the
public MyCareersFuture API, hard-filters them to what Randy is actually a fit
for, fit-scores the survivors against his live résumé, and emails him a short
digest. Goal: kill the "says Software Engineer, actually wants 5 years" noise
so he only reads roles worth his time.

## How it runs
The operative instructions live in `.claude/commands/weekly-job-scan.md`
(the `/weekly-job-scan` command). A scheduled **cloud Routine** invokes that
command every Monday 08:00 SGT. Each run is a fresh, stateless session.

## Files
- `mcf_job_scan.py` — hard-filter stage. Stdlib only, no API key. Writes
  `candidates.json` (git-ignored; regenerated each run).
- `.claude/commands/weekly-job-scan.md` — the routine Claude executes.
- `README.md` — human setup guide.

## Candidate profile (do not hardcode — read the résumé each run)
Source of truth is the Google Doc **Resume_RandyChng_v2**
(fileId `1lbPFv7NzVAf1qS00J_e1ZcaHyXgQ9kguBiz5jj4Nwqg`). At time of writing it
shows: Java 21 / Spring Boot microservices, React / TypeScript / Qiankun MFE,
PostgreSQL / MongoDB / Kafka, OpenShift / Docker, Python (AIAP ~9 mths),
Google ACE cert; ~3+ yrs; payments / banking domain. No Node.js backend.

## Connectors required at runtime
- Google Drive (read the résumé)
- Gmail (send / draft the digest)

## Hard rules
- Read-only except for sending ONE email. Never writes to Notion or Drive.
- Never fabricate a listing, salary, or link.
