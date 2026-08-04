"""jobs-mcp — an MCP server that surfaces live US software-engineering jobs.

Any MCP client (Claude Code, etc.) can call these tools to search current openings
pulled live from company ATS boards (Greenhouse / Lever / Ashby) and a community
new-grad listing feed. Results are US-only and exclude security-clearance /
US-citizenship-required postings (not satisfiable for many candidates). No API
keys — every source is a public endpoint.

Run:  python -m jobs_mcp        (stdio transport, for an MCP client)
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import urllib.request
from datetime import datetime, timezone

from mcp.server import MCPServer

server = MCPServer(
    "jobs-mcp",
    version="0.1.0",
    instructions="Search live US software-engineering job openings from company "
    "ATS boards and community listings. Clearance/citizenship roles are excluded.",
)

# ---- sources ----
COMPANIES = [
    ("greenhouse", "stripe", "Stripe"), ("greenhouse", "databricks", "Databricks"),
    ("greenhouse", "coinbase", "Coinbase"), ("greenhouse", "discord", "Discord"),
    ("greenhouse", "robinhood", "Robinhood"), ("greenhouse", "reddit", "Reddit"),
    ("greenhouse", "pinterest", "Pinterest"), ("greenhouse", "gitlab", "GitLab"),
    ("greenhouse", "airbnb", "Airbnb"), ("greenhouse", "anthropic", "Anthropic"),
    ("greenhouse", "samsara", "Samsara"), ("greenhouse", "brex", "Brex"),
    ("ashby", "ramp", "Ramp"), ("ashby", "notion", "Notion"), ("ashby", "openai", "OpenAI"),
    ("lever", "palantir", "Palantir"),
]
SIMPLIFY_URL = ("https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/"
                "dev/.github/scripts/listings.json")

# ---- filters ----
NON_US = re.compile(
    r"(\b(canada|poland|spain|india|brazil|germany|uk|ireland|mexico|portugal|"
    r"netherlands|france|australia|singapore|japan|israel|toronto|ontario|"
    r"vancouver|london|emea|apac|latam|europe)\b|,\s*(ON|BC|QC|AB)\s*,?\s*CA\b)", re.IGNORECASE)
US_OK = re.compile(
    r"\b(united states|usa|u\.s\.|remote|us[\s-]|, [A-Z]{2}\b|\bSF\b|\bNYC\b|"
    r"new york|san francisco|seattle|austin|boston|chicago)\b", re.IGNORECASE)
CLEARANCE = re.compile(
    r"(\bTS\s*[/&-]\s*SCI\b|\btop[\s-]secret\b|\bsecret\s+clearance\b|"
    r"\b(security|DoD|government|active|current)\s+clearance\b|\bpolygraph\b|"
    r"\bpublic\s+trust\b|\bclearance\s+(required|eligib\w*)\b|\bITAR\b|"
    r"\bU\.?S\.?\s+citizen(ship)?\s+(is\s+)?required\b|\bU\.?S\.?\s+person\b|"
    r"\bannapolis\s+junction\b|\bfort\s+meade\b)", re.IGNORECASE)
CLEAR_COMPANIES = {"lockheed martin", "raytheon", "northrop grumman", "booz allen",
                   "leidos", "saic", "l3harris", "gdit", "caci", "peraton"}


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "jobs-mcp/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _row(company, title, loc, url, posted, source):
    return {"company": company, "title": title, "location": loc,
            "url": url, "posted": posted, "source": source}


def _greenhouse(slug, name):
    d = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false")
    return [_row(name, j["title"], (j.get("location") or {}).get("name", ""),
                 j["absolute_url"], (j.get("updated_at") or "")[:10], "greenhouse")
            for j in d.get("jobs", [])]


def _lever(slug, name):
    d = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    return [_row(name, j["text"], (j.get("categories") or {}).get("location", ""),
                 j["hostedUrl"], "", "lever") for j in d]


def _ashby(slug, name):
    d = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    return [_row(name, j["title"], j.get("location", ""), j["jobUrl"],
                 (j.get("publishedAt") or "")[:10], "ashby") for j in d.get("jobs", [])]


def _simplify():
    out = []
    for j in _get(SIMPLIFY_URL):
        if not (j.get("active") and j.get("is_visible", True)):
            continue
        if j.get("sponsorship") == "U.S. Citizenship is Required":
            continue
        posted = j.get("date_posted")
        posted = (datetime.fromtimestamp(posted, tz=timezone.utc).date().isoformat()
                  if posted else "")
        out.append(_row(j.get("company_name", ""), j.get("title", ""),
                        "; ".join(j.get("locations", []) or []), j.get("url", ""),
                        posted, "SimplifyJobs"))
    return out


FETCH = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def _in_us(loc: str) -> bool:
    if NON_US.search(loc or ""):
        return False
    return US_OK.search(loc or "") is not None or (loc or "") == ""


def _blocked(company: str, title: str, loc: str) -> bool:
    if company.strip().lower() in CLEAR_COMPANIES:
        return True
    return bool(CLEARANCE.search(f"{title} {company} {loc}"))


def _matches(title: str, terms: list[str]) -> bool:
    t = title.lower()
    return all(term in t for term in terms)


def _collect() -> list[dict]:
    """Fetch every source concurrently; a failed source is skipped, not fatal."""
    rows: list[dict] = []
    tasks = [(FETCH[a], s, n) for (a, s, n) in COMPANIES]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(fn, s, n) for (fn, s, n) in tasks]
        futs.append(ex.submit(_simplify))
        for f in concurrent.futures.as_completed(futs):
            try:
                rows += f.result()
            except Exception:  # noqa: BLE001, S112 - one dead board shouldn't fail the search
                continue
    return rows


def _search(query: str, location: str, limit: int) -> list[dict]:
    terms = [w for w in re.split(r"\s+", query.lower().strip()) if w]
    seen, out = set(), []
    loc_l = (location or "").lower()
    for r in _collect():
        title, company, loc = r["title"] or "", r["company"] or "", r["location"] or ""
        if terms and not _matches(title, terms):
            continue
        if not _in_us(loc):
            continue
        if loc_l and loc_l not in ("us", "usa", "united states", "remote") \
                and loc_l not in loc.lower():
            continue
        if _blocked(company, title, loc):
            continue
        key = (company.lower(), title.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    out.sort(key=lambda r: r["posted"] or "", reverse=True)
    return out[: max(1, min(limit, 100))]


@server.tool()
def search_jobs(query: str = "software engineer", location: str = "us",
                limit: int = 20) -> list[dict]:
    """Search live US software-engineering job openings.

    Pulls current postings from company ATS boards (Greenhouse/Lever/Ashby) and a
    community new-grad feed, filters to US roles, excludes security-clearance /
    US-citizenship-required postings, de-duplicates, and returns newest first.

    Args:
        query: words that must all appear in the job title, e.g. "backend engineer",
               "new grad software engineer". Default "software engineer".
        location: "us" for anywhere in the US, or a city/state substring like
                  "New York" or "remote".
        limit: max results (1-100).

    Returns a list of {company, title, location, url, posted, source}.
    """
    return _search(query, location, limit)


@server.tool()
def list_sources() -> dict:
    """List the job sources this server pulls from (ATS boards + community feed)."""
    return {
        "ats_companies": [{"ats": a, "company": n} for (a, _s, n) in COMPANIES],
        "community_feed": "SimplifyJobs/New-Grad-Positions",
        "filters": ["US-only", "security-clearance / citizenship roles excluded"],
    }


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
