#!/usr/bin/env python3
"""
MCF Weekly Job Scan — hard-filter stage
Fetches jobs from the public MyCareersFuture API, applies Randy's hard
filters, and writes surviving candidates to candidates.json for the
LLM fit-scoring stage (done by Claude in the weekly routine).

No API key required. Uses only the Python standard library.

Usage:
    python3 mcf_job_scan.py            # writes candidates.json + prints summary
    python3 mcf_job_scan.py --days 7   # override freshness window
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ----------------------------- CONFIG ---------------------------------

API_BASE = "https://api.mycareersfuture.gov.sg/v2/jobs"

SEARCH_TERMS = [
    "software engineer",
    "full stack software engineer",
    "full stack developer",
    "software developer",
]

MAX_YEARS_EXPERIENCE = 3        # drop roles asking for more than this
SALARY_FLOOR = 5500             # SGD/month; None-salary roles are FLAGGED, not dropped
FRESHNESS_DAYS = 7              # only roles posted within this window
RESULTS_PER_PAGE = 100          # API max
MAX_PAGES_PER_TERM = 3          # safety cap: 300 listings per term

# Titles containing these words are seniority-flagged.
# Rule: keep at most ONE as a "stretch" pick; the routine handles that cap.
SENIOR_MARKERS = re.compile(r"\b(senior|snr|sr\.?|lead|principal|staff|head)\b", re.I)

# Titles that are explicitly out of scope (Randy: no backend-only roles).
EXCLUDED_TITLE_MARKERS = re.compile(
    r"\b(backend engineer|back-end engineer|back end engineer)\b", re.I
)

# Stack keywords used only for a cheap pre-signal (real scoring is LLM-side).
CORE_STACK = ["java", "spring", "react", "typescript", "javascript"]
ANTI_STACK = ["node.js", "nodejs", "next.js", "nextjs", ".net", "c#", "golang",
              "c++", "php", "ruby", "angular only"]

# -----------------------------------------------------------------------


def fetch_page(term: str, page: int) -> dict:
    """One page of search results from the MCF public API."""
    params = urllib.parse.urlencode({
        "search": term,
        "limit": RESULTS_PER_PAGE,
        "page": page,
        "sortBy": "new_posting_date",
    })
    url = f"{API_BASE}?{params}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (job-scan personal script)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_date(value):
    """MCF dates arrive in a few shapes; normalise to aware UTC datetime."""
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def job_record(job: dict) -> dict:
    """Extract only the fields we filter and score on."""
    salary = job.get("salary") or {}
    company = (job.get("postedCompany") or {}).get("name", "Unknown")
    metadata = job.get("metadata") or {}
    skills = [s.get("skill", "") for s in (job.get("skills") or [])]
    position_levels = [p.get("position", "")
                       for p in (job.get("positionLevels") or [])]
    return {
        "uuid": job.get("uuid", ""),
        "title": job.get("title", ""),
        "company": company,
        "min_years": job.get("minimumYearsExperience"),
        "salary_min": salary.get("minimum"),
        "salary_max": salary.get("maximum"),
        "position_levels": position_levels,
        "skills": skills,
        "description": re.sub(r"<[^>]+>", " ", job.get("description", ""))[:2500],
        "posted": metadata.get("newPostingDate") or metadata.get("originalPostingDate"),
        "expiry": metadata.get("expiryDate"),
        "url": (metadata.get("jobDetailsUrl")
                or f"https://www.mycareersfuture.gov.sg/job/{job.get('uuid','')}"),
    }


def stack_signal(rec: dict) -> dict:
    """Cheap keyword pre-signal; the LLM does the real scoring."""
    text = (rec["title"] + " " + " ".join(rec["skills"]) + " "
            + rec["description"]).lower()
    return {
        "core_hits": [k for k in CORE_STACK if k in text],
        "anti_hits": [k for k in ANTI_STACK if k in text],
    }


def apply_filters(rec: dict, cutoff: datetime) -> tuple[bool, list[str]]:
    """Return (keep, flags). Hard-drop reasons return keep=False."""
    flags = []

    # Rule: no canonical link, no inclusion.
    if not rec["url"] or not rec["uuid"]:
        return False, ["no-link"]

    # Freshness: posted within window (API returns only live listings,
    # but we also check expiry defensively).
    posted = parse_date(rec["posted"])
    if posted is None or posted < cutoff:
        return False, ["stale"]
    expiry = parse_date(rec["expiry"])
    if expiry is not None and expiry < datetime.now(timezone.utc):
        return False, ["expired"]

    # Excluded titles (backend-only per Randy's preference).
    if EXCLUDED_TITLE_MARKERS.search(rec["title"]):
        return False, ["excluded-title"]

    # Years of experience: drop if the structured field asks for more.
    if rec["min_years"] is not None and rec["min_years"] > MAX_YEARS_EXPERIENCE:
        return False, ["too-many-years"]
    if rec["min_years"] is None:
        flags.append("years-unstated")

    # Salary: drop only when a stated max is below the floor.
    # Undisclosed salary is flagged, not dropped (decision: include-and-flag).
    if rec["salary_max"] is not None and rec["salary_max"] < SALARY_FLOOR:
        return False, ["below-salary-floor"]
    if rec["salary_min"] is None and rec["salary_max"] is None:
        flags.append("salary-undisclosed")

    # Seniority: flag, don't drop (decision: show max 1 stretch pick).
    if SENIOR_MARKERS.search(rec["title"]):
        flags.append("senior-stretch")

    return True, flags


def main():
    days = FRESHNESS_DAYS
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    seen: set[str] = set()
    kept, dropped_summary = [], {}

    for term in SEARCH_TERMS:
        for page in range(MAX_PAGES_PER_TERM):
            try:
                data = fetch_page(term, page)
            except Exception as exc:
                print(f"[warn] fetch failed for '{term}' p{page}: {exc}",
                      file=sys.stderr)
                break
            results = data.get("results", [])
            if not results:
                break
            for job in results:
                rec = job_record(job)
                if rec["uuid"] in seen:
                    continue
                seen.add(rec["uuid"])
                keep, flags = apply_filters(rec, cutoff)
                if keep:
                    rec["flags"] = flags
                    rec["stack_signal"] = stack_signal(rec)
                    kept.append(rec)
                else:
                    dropped_summary[flags[0]] = dropped_summary.get(flags[0], 0) + 1
            time.sleep(1)  # be polite to a free public API

    # Rough pre-sort: core-stack hits desc, anti-stack hits asc.
    kept.sort(key=lambda r: (-len(r["stack_signal"]["core_hits"]),
                             len(r["stack_signal"]["anti_hits"])))

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "freshness_days": days,
        "filters": {
            "max_years": MAX_YEARS_EXPERIENCE,
            "salary_floor": SALARY_FLOOR,
            "titles": SEARCH_TERMS,
        },
        "scanned": len(seen),
        "kept": len(kept),
        "dropped": dropped_summary,
        "candidates": kept[:30],   # cap what goes to the LLM scorer
    }
    with open("candidates.json", "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"Scanned {len(seen)} unique listings; kept {len(kept)} "
          f"(top 30 written to candidates.json).")
    print(f"Dropped: {dropped_summary}")


if __name__ == "__main__":
    main()
