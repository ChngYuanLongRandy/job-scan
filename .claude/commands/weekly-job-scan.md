---
description: Daily 4am MyCareersFuture job scan → top-5 fit-scored email digest for Randy
---

# /weekly-job-scan  (now runs DAILY at 04:00 SGT — name kept for routine continuity)

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

## Step 2 — Read the résumé (source of truth)
Read the Google Doc whose fileId is in the environment variable
**RESUME_DOC_ID**. If that variable is unset or empty, default to
`1lbPFv7NzVAf1qS00J_e1ZcaHyXgQ9kguBiz5jj4Nwqg` (Resume_RandyChng_v2).
Read it via the Google Drive connector, fresh each run — never a cached
profile. Extract skills, years per skill, and domain experience.

## Step 3 — Fit-score each candidate (0–10)
Randy's core stack — weight these heaviest: **Java, Spring Boot, React,
TypeScript, JavaScript.** A close fit means the role's primary stack IS this
stack.
- **Years check (important):** the API's `minimumYearsExperience` is usually
  null in search results, so READ THE DESCRIPTION for the actual years ask.
  Randy has 3+ years. A close fit asks ≤3 (or ≤4, negotiable).
- **Node.js is NOT Randy's stack.** A Node.js/Next.js backend role is NEVER
  a close fit, no matter how much TypeScript/React it mentions. TS on the
  frontend ≠ Node on the backend. Node-backend roles may only ever appear as
  a stretch pick, explicitly labelled with that gap.
- Frontend React/TypeScript = strong. Angular/Vue = partial.
- Python/FastAPI = light (~1 yr, AIAP).
- **Domain boost: +1** for banking / payments / fintech / financial services.
- Candidates flagged `desc-says-Ny` had a cheap regex pass; your own read of
  the description is authoritative.

## Step 4 — Compose the email: EXACTLY top 5 = 3 close fits + 2 stretch
Send to **chngyuanlong@gmail.com**. Subject:
`Your daily job match — 3 close fits + 2 stretch (week of <date>)`

- **Close fits (3):** the three highest-scoring roles where Randy IS adequate:
  stack matches his core (Java/Spring Boot/React/TS/JS), years ask ≤ his 3+,
  no critical missing technology. As close as possible — prefer a 9 over a 7.
- **Stretch (2):** roles worth seeing where Randy is NOT fully adequate —
  more years required than he has, or a required technology he hasn't used or
  lacks depth in (incl. Senior-titled roles, Node-backend roles). Each stretch
  pick MUST state exactly what's missing ("asks 5y, you have 3+";
  "backend is Node.js — not your stack").
- Every row: title · company · fit /10 · years asked · salary (or
  "undisclosed") · why-you-fit · gaps · MCF link. Links mandatory — no link,
  no row.
- If fewer than 3 genuine close fits exist, say so plainly and fill the
  shortfall with stretch picks, clearly labelled. Never relabel a stretch as
  a close fit to hit the quota.
- One "Filtered out" section: counts by drop reason + 1–2 named examples.
- Skimmable — read on a phone.

## First-run safety
On the FIRST run after any config change, create the email as a **Gmail
draft**, not sent. (The available Gmail connector only creates drafts anyway;
a draft addressed to Randy is the deliverable.)

## Standing decisions (change on request)
1. Cadence: DAILY at 04:00 Asia/Singapore (set in the Routine's schedule UI).
2. Listing freshness: 7 days.
3. Digest: exactly 3 close fits + 2 stretch.
4. Hidden-salary roles → include & flag.
5. Domain → banking/fintech/payments +1 fit boost.
6. Résumé source → env var RESUME_DOC_ID, defaulting to Resume_RandyChng_v2.

## Guardrails
- Never fabricate a listing, salary, or link. Missing field → say so.
- This routine only READS (MCF API, résumé) and creates ONE Gmail draft.
  It must not write to Notion or Drive.
