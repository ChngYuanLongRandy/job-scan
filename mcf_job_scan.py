#!/usr/bin/env python3
"""
MCF Weekly Job Scan — hard-filter stage
Fetches jobs from the public MyCareersFuture API, applies Randy's hard
filters, and writes surviving candidates to candidates.json for the
LLM fit-scoring stage (done by Claude in the weekly routine).

No API key required. Uses only the Python standard library.

Usage:
    python3 mcf_job_scan.py                # fetch from API + filter
    python3 mcf_job_scan.py --days 7       # override freshness window
    python3 mcf_job_scan.py --from-dir raw # OFFLINE: filter pre-fetched JSON
                                           # pages saved as raw/*.json (for
                                           # sandboxes that block outbound
                                           # network from bash/python)
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ----------------------------- CONFIG ---------------------------------

SEARCH_ENDPOINT = "https://api.mycareersfuture.gov.sg/v2/search"

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
# Catches "Backend Engineer", "Software Engineer (Backend)", "Back-End Developer"
# etc. Full-stack roles never carry "backend" in the TITLE, so title-level is safe.
EXCLUDED_TITLE_MARKERS = re.compile(r"\bback[- ]?end\b", re.I)

# Stack keywords used only for a cheap pre-signal (real scoring is LLM-side).
CORE_STACK = ["java", "spring", "react", "typescript", "javascript"]
ANTI_STACK = ["node.js", "nodejs", "next.js", "nextjs", ".net", "c#", "golang",
              "c++", "php", "ruby", "angular only"]

# Direct-employer-only rule: drop listings posted by recruitment agencies,
# headhunters or staffing/manpower firms. MCF's own `isPostedOnBehalf` flag only
# catches agencies posting for a named client; many agencies post under their own
# name with it off, so names and licence text are checked too.
# RECRUITER = hard drop. UNVERIFIED = kept and flagged, so the routine lists it
# separately with the reason instead of presenting it as a direct-employer role.
KNOWN_AGENCIES = re.compile(
    r"\b(persol|randstad|robert walters|hays|michael page|page personnel|adecco|"
    r"manpower(group)?|robert half|kelly services|hudson|morgan mckinley|"
    r"jac recruitment|spencer ogden|kforce|talent international|aquent|"
    r"elliott moss|recruit express|recruit expert|kopi recruit|"
    r"encora technologies|jon ?davidson)\b", re.I)
AGENCY_NAME_TOKENS = re.compile(
    r"\b(recruit(ment|ers?)?|staffing|manpower|headhunt(er|ers|ing)?|"
    r"executive search|talent search|search (associates|group|partners)|"
    r"personnel|human resources?|hr services|outsourcing)\b", re.I)
WEAK_NAME_TOKENS = re.compile(
    r"\b(consult(ing|ancy|ants?)|talents?|resources?|search|solutions? provider|"
    r"career|connect)\b", re.I)          # consultancies and 'talent' firms are often agencies, often not
# Singapore Employment Agency licence / personnel registration numbers in JD text
EA_LICENCE_TEXT = re.compile(
    r"(\bEA\s*(licen[cs]e|lic\.?)\b|\bEA\s*(no|number|reg(istration)?)\b|"
    r"licen[cs]e\s*(no|number)\.?\s*[:#]?\s*\d{2}[A-Z]\d{4}|"
    r"\bR\d{7}\b|\bEAP?\s*(reg|registration)\b|employment agency)", re.I)
CLIENT_LANGUAGE = re.compile(
    r"\b(our client|on behalf of (our|a) client|client'?s? (name )?(is )?confidential|"
    r"confidential (client|employer|company)|leading (mnc|multinational) client)\b", re.I)

# -----------------------------------------------------------------------


def fetch_page(term: str, page: int) -> dict:
    """One page of search results from the MCF public API.

    MCF's keyword search is a POST to /v2/search with a JSON body; page size
    and page number go in the query string. A GET on /v2/jobs does NOT do a
    keyword search (it's the crawl-everything path). If MCF changes this and
    you get an HTTP 4xx here, that's the line to adjust — not the network.
    """
    params = urllib.parse.urlencode({"limit": RESULTS_PER_PAGE, "page": page})
    url = f"{SEARCH_ENDPOINT}?{params}"
    body = json.dumps({"search": term, "sessionId": ""}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "User-Agent": "Mozilla/5.0 (job-scan personal script)",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_job_description(uuid: str) -> str:
    """Full JD prose via the per-job detail endpoint.

    REALITY CHECK (confirmed live 2026-07-06): /v2/search's `description`
    field comes back empty for every listing — not intermittent, always.
    Only /v2/jobs/{uuid} has the actual text (e.g. "4+ years Java-J2EE...
    banking environment"), which is what the scoped-experience gate and the
    years-from-description filter below both depend on. One call per
    candidate that survives apply_structural_filters — see main().
    """
    url = f"https://api.mycareersfuture.gov.sg/v2/jobs/{uuid}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (job-scan personal script)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return re.sub(r"<[^>]+>", " ", data.get("description", "") or "")[:3000]


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
        "hiring_company": (job.get("hiringCompany") or {}).get("name"),
        "posted_on_behalf": bool(metadata.get("isPostedOnBehalf")),
        "employer_hidden": bool(metadata.get("isHideHiringEmployerName")),
        "description": re.sub(r"<[^>]+>", " ", job.get("description", ""))[:2500],
        "posted": metadata.get("newPostingDate") or metadata.get("originalPostingDate"),
        "expiry": metadata.get("expiryDate"),
        "url": (metadata.get("jobDetailsUrl")
                or f"https://www.mycareersfuture.gov.sg/job/{job.get('uuid','')}"),
    }


def poster_check(rec: dict) -> tuple[str, str]:
    """Classify who posted the listing from structured fields and name only.

    Returns ("recruiter", reason), ("unverified", reason) or ("direct", "").
    The JD-text checks (licence numbers, 'our client') run later, in
    poster_check_description(), once the real description has been fetched.
    """
    name = rec["company"] or ""
    if rec["posted_on_behalf"]:
        return "recruiter", f"posted on behalf of {rec['hiring_company'] or 'a client'} by {name}"
    if KNOWN_AGENCIES.search(name):
        return "recruiter", f"poster '{name}' is a known recruitment agency"
    if AGENCY_NAME_TOKENS.search(name):
        return "recruiter", f"poster name '{name}' is a recruitment/staffing firm"
    if rec["employer_hidden"] or name.lower() in ("", "unknown", "confidential"):
        return "unverified", "employer name is withheld or confidential"
    if WEAK_NAME_TOKENS.search(name):
        return "unverified", f"poster '{name}' looks like a consultancy or talent firm; could not confirm it is the employer"
    return "direct", ""


def poster_check_description(rec: dict) -> tuple[str, str]:
    """Second poster check on the real JD text (agency licence numbers, 'our client')."""
    desc = rec.get("description") or ""
    m = EA_LICENCE_TEXT.search(desc)
    if m:
        return "recruiter", f"JD carries an employment agency licence/registration marker ('{m.group(0).strip()}')"
    m = CLIENT_LANGUAGE.search(desc)
    if m:
        return "unverified", f"JD speaks of a client ('{m.group(0).strip()}'), so the poster may be an agency"
    return "direct", ""


def stack_signal(rec: dict) -> dict:
    """Cheap keyword pre-signal; the LLM does the real scoring."""
    text = (rec["title"] + " " + " ".join(rec["skills"]) + " "
            + rec["description"]).lower()
    return {
        "core_hits": [k for k in CORE_STACK if k in text],
        "anti_hits": [k for k in ANTI_STACK if k in text],
    }


YEARS_PATTERN = re.compile(
    r"(?:minimum|min\.?|at least)?\s*(\d{1,2})\s*(?:\+|plus)?\s*(?:-\s*\d{1,2}\s*)?"
    r"years?(?:'|s)?\s+(?:of\s+)?(?:relevant\s+|working\s+|hands[- ]on\s+|professional\s+)?"
    r"(?:experience|exp\b)", re.I)


def years_from_description(desc: str):
    """Cheap extraction of an explicit years-of-experience ask from the JD.

    Returns the LOWEST years figure mentioned with 'experience' (ranges like
    '3-5 years' read as 3, since the lower bound is the entry ask), or None.
    """
    hits = [int(m.group(1)) for m in YEARS_PATTERN.finditer(desc or "")]
    hits = [h for h in hits if 0 < h <= 20]
    return min(hits) if hits else None


def apply_structural_filters(rec: dict, cutoff: datetime) -> tuple[bool, list[str]]:
    """Return (keep, flags) using only structured API fields — no JD prose.

    Description-dependent checks (years-of-experience mentioned only in JD
    text) can't run here: /v2/search always returns an empty `description`,
    so they're deferred to apply_description_filter() after main() fetches
    the real text for whatever survives this pass. Hard-drop reasons here
    return keep=False; description-based drops happen later.
    """
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
    # The structured field is usually null (see REALITY CHECK on
    # fetch_job_description) — when it's null, defer to the description-based
    # check once the real JD text is available.
    if rec["min_years"] is not None and rec["min_years"] > MAX_YEARS_EXPERIENCE:
        return False, ["too-many-years"]
    if rec["min_years"] is None:
        flags.append("years-pending-jd-fetch")

    # Salary: drop only when a stated max is below the floor.
    # Undisclosed salary is flagged, not dropped (decision: include-and-flag).
    if rec["salary_max"] is not None and rec["salary_max"] < SALARY_FLOOR:
        return False, ["below-salary-floor"]
    if rec["salary_min"] is None and rec["salary_max"] is None:
        flags.append("salary-undisclosed")

    # Seniority: flag, don't drop (decision: show max 1 stretch pick).
    if SENIOR_MARKERS.search(rec["title"]):
        flags.append("senior-stretch")

    # Direct employers only. Runs last so the recruiter count covers only
    # listings that passed every other filter.
    status, reason = poster_check(rec)
    if status == "recruiter":
        return False, ["recruiter-posted"]
    if status == "unverified":
        flags.append("unverified-poster")
        rec["poster_note"] = reason

    return True, flags


def apply_description_filter(rec: dict) -> tuple[bool, str | None]:
    """Second pass, run after the real JD text has been fetched.

    Resolves the "years-pending-jd-fetch" placeholder left by
    apply_structural_filters: scans the now-real `description` for an
    explicit "N+ years" ask. Returns (keep, replacement_flag);
    replacement_flag is None when there was nothing to resolve.
    """
    if "years-pending-jd-fetch" not in rec["flags"]:
        return True, None
    desc_years = years_from_description(rec["description"])
    if desc_years is not None and desc_years > MAX_YEARS_EXPERIENCE + 1:
        # +1 slack: "4 years" asks are often negotiable at 3; 5+ is not.
        return False, "too-many-years-desc"
    return True, ("years-unstated" if desc_years is None
                  else f"desc-says-{desc_years}y")


def iter_pages_from_api():
    """Yield API response pages over the network (normal mode)."""
    for term in SEARCH_TERMS:
        for page in range(MAX_PAGES_PER_TERM):
            try:
                data = fetch_page(term, page)
            except Exception as exc:
                print(f"[warn] fetch failed for '{term}' p{page}: {exc}",
                      file=sys.stderr)
                break
            if not data.get("results"):
                break
            yield data
            time.sleep(1)  # be polite to a free public API


def iter_pages_from_dir(dirpath: str):
    """Yield pre-fetched API response pages from <dirpath>/*.json.

    Offline mode for sandboxes whose egress proxy blocks bash/python network:
    have the agent fetch the MCF search URLs via its own web-fetch tool, save
    each raw JSON response as a file in this directory, then run this script
    with --from-dir to do the filtering with zero network access.
    """
    import glob
    import os
    paths = sorted(glob.glob(os.path.join(dirpath, "*.json")))
    if not paths:
        print(f"[warn] no *.json files found in '{dirpath}'", file=sys.stderr)
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            print(f"[warn] could not parse {p}: {exc}", file=sys.stderr)
            continue
        # Accept either a full API response {"results": [...]} or a bare list.
        if isinstance(data, list):
            data = {"results": data}
        if data.get("results"):
            yield data


def main():
    days = FRESHNESS_DAYS
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    if "--from-dir" in sys.argv:
        source = iter_pages_from_dir(sys.argv[sys.argv.index("--from-dir") + 1])
    else:
        source = iter_pages_from_api()

    seen: set[str] = set()
    kept, dropped_summary = [], {}
    recruiter_examples = []        # 'company: reason' for listings dropped as recruiter-posted

    for data in source:
        for job in data.get("results", []):
            rec = job_record(job)
            if not rec["uuid"] or rec["uuid"] in seen:
                continue
            seen.add(rec["uuid"])
            keep, flags = apply_structural_filters(rec, cutoff)
            if keep:
                rec["flags"] = flags
                kept.append(rec)
            else:
                dropped_summary[flags[0]] = dropped_summary.get(flags[0], 0) + 1
                if flags[0] == "recruiter-posted":
                    recruiter_examples.append(f"{rec['company']}: {poster_check(rec)[1]}")

    # ---- Fetch real JD text for everything that survived structural
    # filters, so the years-of-description check and stack_signal ranking
    # both work on genuine content instead of the always-empty /v2/search
    # description field. Skipped in --from-dir mode: that mode exists for
    # sandboxes with no outbound network at all, so a per-job fetch would
    # just fail the same way the bulk fetch would.
    fetch_failures = 0
    if "--from-dir" not in sys.argv:
        for rec in kept:
            try:
                full_desc = fetch_job_description(rec["uuid"])
                if full_desc.strip():
                    rec["description"] = full_desc
            except Exception as exc:
                fetch_failures += 1
                print(f"[warn] description fetch failed for {rec['uuid']}: {exc}",
                      file=sys.stderr)
            time.sleep(0.3)  # be polite to a free public API

    # ---- Second filter pass: now that description is real, resolve the
    # years-pending-jd-fetch placeholder and drop anything whose JD text
    # asks for more years than the structured field revealed.
    resolved_kept = []
    for rec in kept:
        status, reason = poster_check_description(rec)
        if status == "recruiter":
            dropped_summary["recruiter-posted"] = dropped_summary.get("recruiter-posted", 0) + 1
            recruiter_examples.append(f"{rec['company']}: {reason}")
            continue
        if status == "unverified" and "unverified-poster" not in rec["flags"]:
            rec["flags"].append("unverified-poster")
            rec["poster_note"] = reason
        keep, replacement_flag = apply_description_filter(rec)
        if not keep:
            dropped_summary["too-many-years-desc"] = (
                dropped_summary.get("too-many-years-desc", 0) + 1)
            continue
        if replacement_flag:
            rec["flags"] = [f for f in rec["flags"] if f != "years-pending-jd-fetch"]
            rec["flags"].append(replacement_flag)
        rec["stack_signal"] = stack_signal(rec)
        resolved_kept.append(rec)
    kept = resolved_kept

    # Rough pre-sort: core-stack hits desc, anti-stack hits asc.
    kept.sort(key=lambda r: (-len(r["stack_signal"]["core_hits"]),
                             len(r["stack_signal"]["anti_hits"])))

    # ---- De-duplication against seen.json (persists across runs) ----------
    # seen.json maps job_uuid -> first_seen ISO date. We prune entries older
    # than the freshness window so the file self-cleans, mark each candidate
    # already_seen True/False, then record today's UUIDs. The LLM step shows
    # only NEW (already_seen == False) roles; seen ones are suppressed.
    # NOTE: this only persists if seen.json is committed back to the repo
    # after the run (see the routine's commit step). On ephemeral disk with
    # no commit-back, every run starts fresh and nothing is de-duplicated.
    today = datetime.now(timezone.utc).date()
    seen_store = {}
    try:
        with open("seen.json", encoding="utf-8") as fh:
            seen_store = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        seen_store = {}
    # prune expired
    seen_store = {
        uuid: d for uuid, d in seen_store.items()
        if (today - datetime.fromisoformat(d).date()).days < days
    }
    new_count = 0
    for rec in kept:
        was_seen = rec["uuid"] in seen_store
        rec["already_seen"] = was_seen
        rec["first_seen"] = seen_store.get(rec["uuid"], today.isoformat())
        if not was_seen:
            seen_store[rec["uuid"]] = today.isoformat()
            new_count += 1
    with open("seen.json", "w", encoding="utf-8") as fh:
        json.dump(seen_store, fh, indent=2, ensure_ascii=False)

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
        "new_since_last_run": new_count,
        "dropped": dropped_summary,
        "recruiter_posted_excluded": dropped_summary.get("recruiter-posted", 0),
        "recruiter_examples": sorted(set(recruiter_examples))[:6],
        "unverified_poster": sum(1 for r in kept if "unverified-poster" in r["flags"]),
        "candidates": kept[:30],   # cap what goes to the LLM scorer
    }
    with open("candidates.json", "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)

    print(f"Scanned {len(seen)} unique listings; kept {len(kept)} "
          f"({new_count} new since last run; top 30 written to candidates.json).")
    print(f"Dropped: {dropped_summary}")
    if fetch_failures:
        print(f"[warn] description fetch failed for {fetch_failures} listing(s) — "
              f"those entries fall back to an empty description.", file=sys.stderr)


if __name__ == "__main__":
    main()
