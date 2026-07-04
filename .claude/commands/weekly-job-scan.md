---
description: Weekly MyCareersFuture job scan → fit-scored email digest for Randy
---

# /weekly-job-scan

Run the full weekly job scan and email a digest. Each run is a fresh session —
carry no state between runs; everything needed is below.

## Step 1 — Hard-filter stage
Run `python3 mcf_job_scan.py`. It queries the public MyCareersFuture API
(api.mycareersfuture.gov.sg/v2/jobs) for these titles: software engineer,
full stack software engineer, full stack developer, software developer.
It applies hard filters and writes `candidates.json`:
- posted within last 7 days, not expired
- `minimumYearsExperience` <= 3 (unstated → flag `years-unstated`)
- salary max >= S$5,500 (undisclosed → flag `salary-undisclosed`, keep)
- drops backend-only titles ("backend engineer")
- flags Senior / Lead / Principal titles `senior-stretch` (does not drop)
- every kept job carries a canonical MCF link

### Step 1b — FALLBACK if the network is blocked (403 Tunnel / egress denial)
If the script fails with `Tunnel connection failed: 403` (the sandbox egress
proxy blocking outbound bash/python), do NOT give up. Fetch the data yourself
via your web-fetch tool — that path is not governed by the bash sandbox:
1. `mkdir -p raw`
2. For each of these search terms — `software engineer`,
   `full stack software engineer`, `full stack developer`,
   `software developer` — fetch page 0 and page 1 of:
   `https://api.mycareersfuture.gov.sg/v2/search?limit=100&page=<N>`
   as a POST with JSON body `{"search": "<term>", "sessionId": ""}`.
   If your fetch tool only supports GET, try
   `https://api.mycareersfuture.gov.sg/v2/jobs?limit=100&page=<N>&search=<url-encoded term>`
   and use whichever returns a JSON body containing a `results` array.
3. Save each raw JSON response verbatim to `raw/<term-slug>-p<N>.json`.
4. Run `python3 mcf_job_scan.py --from-dir raw` — filtering is fully offline.
Then continue to Step 2 as normal. In the digest, note which fetch path was
used.

If BOTH paths fail, or `candidates.json` has 0 candidates, send a short email
stating exactly what failed (include the error text) instead of silently
skipping. Do not fabricate listings to fill the email.

## Step 2 — Read the résumé (source of truth)
Read the Google Doc **Resume_RandyChng_v2**
(fileId `1lbPFv7NzVAf1qS00J_e1ZcaHyXgQ9kguBiz5jj4Nwqg`) via the Google Drive
connector, fresh this run. Extract skills, years per skill, and domain
experience. Do not use a cached profile — the résumé is the living source.

## Step 3 — Fit-score each candidate (0–10)
For each candidate in `candidates.json`, score against the résumé:
- **Backend language is its own factor.** Java / Spring backend = strong.
  Node.js / Next.js backend = weak even when the frontend is React/TS
  (Randy has no Node backend experience — never treat TS-frontend as
  Node-backend coverage).
- Frontend React / TypeScript = strong. Angular / Vue = partial.
- Python / FastAPI = light (~1 yr, AIAP).
- **Domain boost:** +1 for payments / banking / fintech / financial services.
- Give each a one-line "why you fit" and an honest "gaps" note.
- Seniority-flagged roles: include at most ONE, labelled "stretch pick", and
  only if its score is >= 7 before the label.

## Step 4 — Compose & send the email
Send to **chngyuanlong@gmail.com**. Subject:
`Your weekly job match — N roles worth a look (week of <date>)`

Body:
- Top 3–5 by fit score. Each row: title · company · fit /10 · years asked ·
  salary (or "undisclosed") · why-you-fit · gaps · MCF link.
  Links mandatory — no link, no row.
- One "Filtered out this week" section: counts by drop reason
  (too-many-years, below-salary-floor, stale, excluded-title) + 1–2 named
  examples so the cut stays auditable.
- If nothing clears fit >= 6, say so plainly. Do not pad with weak matches.
- Skimmable — this is read on a phone.

## First-run safety
On the FIRST scheduled run, create the email as a **Gmail draft**, not sent.
After Randy reviews one real output, switch this line to send directly.

## Standing decisions (change on request)
1. Hidden-salary roles → include & flag (MCF mandates salary disclosure, so rare).
2. Senior-titled roles → max 1, shown as a flagged stretch pick.
3. Domain → fintech / payments gets +1 fit boost.
4. Résumé source → Resume_RandyChng_v2 (Google Doc), read live each run.

## Guardrails
- Never fabricate a listing, salary, or link. Missing field → say so.
- This routine only READS (MCF API, résumé) and sends ONE email.
  It must not write to Notion or Drive.
