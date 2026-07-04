# job-scan

Weekly MyCareersFuture job scan → fit-scored email digest.

Pulls fresh software-engineer / full-stack roles from the public
MyCareersFuture API, hard-filters them to what I'm actually a fit for,
fit-scores the survivors against my live résumé, and emails a short digest
every Monday morning. Cuts the "says Software Engineer, actually wants 5
years" noise.

## Layout

```
job-scan/
├── README.md
├── CLAUDE.md                        # project context for the routine
├── mcf_job_scan.py                  # hard-filter stage (stdlib only)
├── .gitignore
└── .claude/commands/
    └── weekly-job-scan.md           # the /weekly-job-scan routine
```

## What each stage does

1. **`mcf_job_scan.py`** — queries `api.mycareersfuture.gov.sg/v2/jobs`
   (public, no key), applies hard filters (≤3 yrs, salary ≥ S$5,500,
   posted ≤7 days, links mandatory, backend-only titles dropped, Senior
   titles flagged), writes `candidates.json`.
2. **`/weekly-job-scan`** — runs the script, reads my résumé live from
   Google Drive, fit-scores each candidate (backend language weighted as its
   own factor; +1 for fintech/payments), and emails the digest via Gmail.

## Local test (before scheduling)

```bash
python3 mcf_job_scan.py          # needs outbound network to mycareersfuture.gov.sg
cat candidates.json              # eyeball the survivors + drop reasons
python3 mcf_job_scan.py --days 14  # widen the window if a quiet week
```

Python 3.9+; no dependencies. Tune the constants at the top of the script
(SALARY_FLOOR, MAX_YEARS_EXPERIENCE, SEARCH_TERMS, FRESHNESS_DAYS).

## Schedule it as a cloud Routine

1. Push this folder to a GitHub repo.
2. Connect the repo to Claude Code on the web.
3. **Routines** panel → **New Routine**.
4. Trigger = schedule, cron `0 8 * * 1`, timezone **Asia/Singapore**.
5. Instruction: `Run /weekly-job-scan`.
6. Authorize the **Gmail** and **Google Drive** connectors for the routine.
7. Leave the first run as a **Gmail draft** (already specified in the command);
   review one real output, then flip the command's "First-run safety" line to
   send directly.
8. Do a manual test run before trusting the schedule.

Requires a paid plan (Pro/Max/Team/Enterprise) with Claude Code on web.

## Honest caveats

- The MCF API field names are verified against its documented structure, but
  this was not run against live API responses in a networked environment —
  expect maybe one small fix on the first real run.
- Claude Code UI labels drift between releases; if a step above doesn't match,
  the authoritative reference is Anthropic's own docs (code.claude.com/docs,
  Scheduled Tasks / Routines).
- Standing decisions (salary floor, senior handling, domain boost, résumé
  source) are all editable in `.claude/commands/weekly-job-scan.md`.
```
