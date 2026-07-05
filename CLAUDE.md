# CLAUDE.md — job-scan

Personal job-search automation for Randy Chng (Singapore).

## What this project does
Weekly it pulls fresh software-engineering / full-stack roles from the
public MyCareersFuture API, hard-filters them to what Randy is actually a fit
for, fit-scores the survivors against his live résumé, de-dupes against roles
already shown, and emails him a short digest of up to 5 new roles (3 close
fits + 2 stretch picks). Goal: kill the "says Software Engineer, actually
wants 5 years" noise so he only reads roles worth his time.

## How it runs
The operative instructions live in `.claude/commands/weekly-job-scan.md`
(the `/weekly-job-scan` command — name kept for continuity even though
cadence has changed over time). A scheduled **cloud Routine** invokes that
command every Monday 04:00 SGT. Each run is a fresh session, except for the
de-dup state described below.

## Files
- `mcf_job_scan.py` — hard-filter stage. Stdlib only, no API key. Writes
  `candidates.json` (git-ignored; regenerated each run).
- `seen.json` — de-dup state: uuids of roles already shown to Randy in the
  last 7 days. Git-tracked; the routine commits and pushes it back to this
  repo after composing each digest so the next run doesn't repeat roles.
- `.claude/commands/weekly-job-scan.md` — the routine Claude executes; this
  is the authoritative, frequently-iterated spec — re-read it fresh each run
  rather than trusting this file's summary of it.
- `README.md` — human setup guide.

## Candidate profile (do not hardcode — read the résumé each run)
Source of truth is the Google Doc identified by env var `RESUME_DOC_ID`,
defaulting to **Resume_RandyChng_v2**
(fileId `1lbPFv7NzVAf1qS00J_e1ZcaHyXgQ9kguBiz5jj4Nwqg`). At time of writing it
shows: Java 21 / Spring Boot microservices, React / TypeScript / Qiankun MFE,
PostgreSQL / MongoDB / Kafka, OpenShift / Docker, Python (AIAP ~9 mths),
Google ACE cert; ~3+ yrs; payments / banking domain. No Node.js backend.

## Connectors required at runtime
- Google Drive (read the résumé)
- Gmail (draft the digest — the connector only supports draft creation)

## Hard rules
- Reads MCF API + résumé, creates ONE Gmail draft, and may commit/push
  `seen.json` to THIS repo only for de-dup persistence. Never writes to
  Notion or Drive, and never pushes anything other than `seen.json`.
- Never fabricate a listing, salary, or link.
