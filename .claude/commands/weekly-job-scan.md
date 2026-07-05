---
description: Weekly Monday 4am MyCareersFuture job scan → top-5 fit-scored email digest for Randy
---

# /weekly-job-scan  (runs WEEKLY Monday 04:00 SGT — name kept for routine continuity)

Run the full job scan and email a digest. Each run is a fresh session —
carry no state between runs; everything needed is below.

## Step 1 — Get candidates.json (fetch-first, file fallback)
1. Run `python3 mcf_job_scan.py`. If it prints a "Scanned N ... kept M" line,
   fresh data is in `candidates.json` — use it and go to Step 2.
   (The environment's Network access must allow api.mycareersfuture.gov.sg —
   set via the environment's Custom network access, NOT the repo settings.json,
   which the egress proxy ignores.)
2. ONLY if the fetch fails (e.g. 403 Tunnel = egress policy): fall back to a
   pre-existing `candidates.json` in the project root, but only if its
   `generated_at` is within the last 3 days (produced by an external cron /
   CI job). Do not retry the fetch or route around the proxy.
3. If neither path yields usable data, send a short email saying exactly what
   failed (include the error text and candidates.json's generated_at if one
   exists). Do not fabricate listings.

Listing freshness window: 7 days (script default). In the digest, always state
the data's `generated_at` timestamp.

## Step 2 — Read the résumé + build a per-skill experience map
Read the Google Doc whose fileId is in the environment variable
**RESUME_DOC_ID**. If that variable is unset or empty, default to
`1lbPFv7NzVAf1qS00J_e1ZcaHyXgQ9kguBiz5jj4Nwqg` (Resume_RandyChng_v2).
Read it via the Google Drive connector, fresh each run — never a cached
profile.

From the dated roles, INFER Randy's years of experience PER SKILL (not just
total tenure). E.g. how many years of Java specifically, React specifically,
Spring Boot, TypeScript/JavaScript, Python, etc. This per-skill map is what
the scoped-experience gate in Step 3 checks against. Randy's total working
tenure (~3+ yrs, ~4 counting AIAP) is NOT the same as his depth in any single
technology — keep them separate.

## Step 3 — Fit-score each candidate (0–10)
Randy's core stack — weight these heaviest: **Java, Spring Boot, React,
TypeScript, JavaScript.** A close fit means the role's primary stack IS this
stack.

- **SCOPED-EXPERIENCE GATE (the important one).** When a JD demands "N years
  of <specific tech or domain>", check N against Randy's inferred years in
  THAT specific thing (Step 2 map), NOT his total tenure. Example: "4+ years
  of Java development in a Unix/Linux environment" — Randy has ~4 years total
  but only ~3 in Java, so he does NOT meet it → this is a STRETCH, never a
  close fit, and the gap must be named ("asks 4y Java, you have ~3y Java").
  Total career years clearing the number does not satisfy a skill-scoped ask.
- **Years stated with no specific skill attached** (generic "N years
  experience"): compare against total tenure (~3+). ≤3 fine; 4 negotiable.
- **No years stated at all:** eligible as a close fit (assume open).
- **Node.js is NOT Randy's stack.** A Node.js/Next.js backend role is NEVER a
  close fit, however much TypeScript/React it mentions. TS on the frontend ≠
  Node on the backend. Node-backend roles are stretch-only, labelled.
- Frontend React/TypeScript = strong. Angular/Vue = partial.
- Python/FastAPI = light (~1 yr, AIAP).
- **Domain boost: +1** for banking / payments / fintech / financial services.
- The script's `desc-says-Ny` flag is a cheap regex hint only; YOUR read of
  the description is authoritative for the scoped gate.

## Step 4 — Compose the email: up to 5 NEW roles = 3 close + 2 stretch
**De-dup first:** only consider candidates with `already_seen == false`.
Roles shown in the last 7 days are suppressed. If everything is already seen,
send a one-line "no new matches today" email — do not re-show old roles.

Send to **chngyuanlong@gmail.com**. Subject:
`Your weekly job match — <X> new (week of <date>)`

- **Close fits (up to 3):** highest-scoring NEW roles where Randy IS adequate —
  core stack (Java/Spring Boot/React/TS/JS), and he meets every skill-scoped
  years ask per the gate. Prefer a 9 over a 7.
- **Stretch (up to 2):** NEW roles worth seeing where Randy is NOT fully
  adequate — a skill-scoped years gap (e.g. 4y Java when he has 3y), a
  required tech he lacks, Node-backend, or Senior title. Each MUST name the
  exact gap.
- **Backfill rule:** if fewer than 3 close fits among new roles, backfill the
  digest from stretch picks, clearly labelled as stretch. Never relabel a
  stretch as a close fit to hit a number.
- Every row: title · company · fit /10 · years asked (and of what) · salary
  (or "undisclosed") · why-you-fit · gaps · MCF link. Links mandatory.
- One "Filtered out" section: counts by drop reason + 1–2 named examples.
- State the data's `generated_at` and `new_since_last_run` so Randy sees
  freshness at a glance. Skimmable — read on a phone.

## Step 5 — Persist the de-dup state
After composing the email, commit `seen.json` back to the repo so the next
run remembers what was shown:
`git add seen.json && git commit -m "seen $(date -u +%F)" && git push`
If the routine cannot push (no write creds in this environment), note that in
the email — without persistence, de-dup resets every run and roles will repeat.

## First-run safety
On the FIRST run after any config change, create the email as a **Gmail
draft**, not sent. (The available Gmail connector only creates drafts anyway;
a draft addressed to Randy is the deliverable.)

## Standing decisions (change on request)
1. Cadence: WEEKLY, Monday 04:00 Asia/Singapore (set in the Routine schedule UI).
2. Listing freshness: 7 days.
3. Digest: exactly 3 close fits + 2 stretch.
4. Hidden-salary roles → include & flag.
5. Domain → banking/fintech/payments +1 fit boost.
6. Résumé source → env var RESUME_DOC_ID, defaulting to Resume_RandyChng_v2.

## Guardrails
- Never fabricate a listing, salary, or link. Missing field → say so.
- This routine only READS (MCF API, résumé) and creates ONE Gmail draft.
  It must not write to Notion or Drive.
