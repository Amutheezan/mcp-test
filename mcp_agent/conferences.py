"""Conference-deadline and paper-search data sources for the MCP server.

Conference data comes from the ccfddl/ccf-deadlines GitHub repo (curated,
community-maintained yaml files, no auth needed). Paper search uses the
public arXiv Atom API.
"""
import datetime as dt
import xml.etree.ElementTree as ET

import requests
import yaml

GITHUB_API = "https://api.github.com/repos/ccfddl/ccf-deadlines/contents/conference"
RAW_BASE = "https://raw.githubusercontent.com/ccfddl/ccf-deadlines/main/conference"
ARXIV_API = "http://export.arxiv.org/api/query"

CATEGORY_ALIASES = {
    "ai": "AI", "ml": "AI", "machine-learning": "AI", "artificial-intelligence": "AI",
    "security": "SC", "sec": "SC",
    "database": "DB", "db": "DB",
    "network": "NW", "networking": "NW",
    "software": "SE", "se": "SE",
    "hci": "HI",
    "graphics": "CG",
    "theory": "CT",
    "data-science": "DS", "ds": "DS",
    "multimedia": "MX",
}
CATEGORIES = {"AI", "SC", "DB", "NW", "SE", "HI", "CG", "CT", "DS", "MX"}


def normalize_category(category: str) -> str:
    category = category.strip()
    if category.upper() in CATEGORIES:
        return category.upper()
    key = category.strip().lower()
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    raise ValueError(
        f"unknown category '{category}'. Use one of: ai, ml, security, database, "
        f"network, software, hci, graphics, theory, data-science, multimedia "
        f"(or a raw code: {sorted(CATEGORIES)})"
    )


def _list_conference_files(category_code: str) -> list[str]:
    resp = requests.get(f"{GITHUB_API}/{category_code}", timeout=15)
    resp.raise_for_status()
    return [f["name"] for f in resp.json() if f["name"].endswith(".yml")]


def _fetch_conference_yaml(category_code: str, filename: str) -> dict:
    resp = requests.get(f"{RAW_BASE}/{category_code}/{filename}", timeout=15)
    resp.raise_for_status()
    data = yaml.safe_load(resp.text)
    return data[0] if data else {}


def _parse_dt(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _next_deadline(entry: dict) -> tuple[dict, dt.datetime] | None:
    """Among an entry's confs (one per year), find the nearest future deadline."""
    now = dt.datetime.utcnow()
    best = None
    for conf in entry.get("confs", []):
        for line in conf.get("timeline", []):
            deadline = _parse_dt(line.get("deadline"))
            if deadline and deadline >= now:
                if best is None or deadline < best[1]:
                    best = ({**conf, "deadline_str": line.get("deadline"),
                             "abstract_deadline": line.get("abstract_deadline")}, deadline)
    return best


def list_upcoming_conferences(category: str, limit: int = 20) -> list[dict]:
    category_code = normalize_category(category)
    filenames = _list_conference_files(category_code)
    results = []
    for filename in filenames:
        try:
            entry = _fetch_conference_yaml(category_code, filename)
        except Exception:
            continue
        nxt = _next_deadline(entry)
        if not nxt:
            continue
        conf, deadline = nxt
        results.append({
            "acronym": filename[:-4],
            "title": entry.get("title"),
            "description": entry.get("description"),
            "rank": entry.get("rank"),
            "year": conf.get("year"),
            "deadline": conf.get("deadline_str"),
            "abstract_deadline": conf.get("abstract_deadline"),
            "timezone": conf.get("timezone"),
            "date": conf.get("date"),
            "place": conf.get("place"),
            "link": conf.get("link"),
        })
    results.sort(key=lambda r: r["deadline"])
    return results[:limit]


def get_conference_details(acronym: str, category: str) -> dict:
    category_code = normalize_category(category)
    filename = f"{acronym.strip().lower()}.yml"
    entry = _fetch_conference_yaml(category_code, filename)
    if not entry:
        raise ValueError(f"no data for '{acronym}' in category '{category_code}'")
    return {
        "acronym": acronym.lower(),
        "title": entry.get("title"),
        "description": entry.get("description"),
        "rank": entry.get("rank"),
        "dblp": entry.get("dblp"),
        "years": entry.get("confs", []),
    }


def search_papers(topic: str, max_results: int = 10) -> list[dict]:
    params = {
        "search_query": f"all:{topic}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    resp = requests.get(ARXIV_API, params=params, timeout=15)
    resp.raise_for_status()
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    papers = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", default="", namespaces=ns).strip()
        summary = entry.findtext("atom:summary", default="", namespaces=ns).strip()
        published = entry.findtext("atom:published", default="", namespaces=ns)
        authors = [a.findtext("atom:name", default="", namespaces=ns)
                   for a in entry.findall("atom:author", ns)]
        link = ""
        for l in entry.findall("atom:link", ns):
            if l.get("type") == "application/pdf":
                link = l.get("href")
                break
        papers.append({
            "title": title,
            "authors": authors,
            "published": published,
            "summary": summary[:500],
            "pdf_link": link,
        })
    return papers