"""Downloaders for public OFAC data.

Two complementary sources are used:

1. Recent Actions (https://ofac.treasury.gov/recent-actions/sanctions-list-updates)
   - Every list update since OFAC launched the site, with the exact entries added,
     removed or updated. Used to build the change history (backfill + incremental).
2. Sanctions List Service exports (SDN.CSV + ADD.CSV)
   - The full current SDN list. A dated snapshot is saved on every run and diffed
     against the previous snapshot, so the project also detects changes on its own.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://ofac.treasury.gov"
LIST_URL = BASE + "/recent-actions/sanctions-list-updates"
SLS = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/"
HEADERS = {"User-Agent": "ofac-sanctions-tracker (portfolio project; public data)"}


def _get(url: str, retries: int = 3) -> requests.Response:
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


def _parse_date(text: str) -> str | None:
    import re
    m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    if not m:
        return None
    return dt.datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat()


def list_actions(since: str, max_pages: int = 400) -> list[dict]:
    """Return [{url,title,date}] for list-update actions on/after `since` (YYYY-MM-DD)."""
    out: list[dict] = []
    for page in range(max_pages):
        soup = BeautifulSoup(_get(f"{LIST_URL}?page={page}").text, "lxml")
        rows = soup.select(".views-row")
        if not rows:
            break
        stop = False
        for row in rows:
            a = row.select_one('a[href^="/recent-actions/"]')
            date = _parse_date(row.get_text(" "))
            if date and date < since:
                stop = True
                continue
            out.append({"url": a["href"], "title": a.get_text(strip=True), "date": date})
        if stop:
            break
        time.sleep(0.5)
    return out


def fetch_action_body(url: str) -> str:
    soup = BeautifulSoup(_get(BASE + url).text, "lxml")
    for f in soup.select(".field"):
        txt = f.get_text(" ", strip=True)
        if txt.startswith("Recent Actions Body"):
            return txt.replace("Recent Actions Body", "", 1).strip()
    main = soup.select_one("main") or soup
    return main.get_text(" ", strip=True)


def update_raw_actions(raw_path: Path, since_default: str = "2021-01-01") -> int:
    """Incrementally extend the raw Recent Actions JSON. Returns number of new actions."""
    data = json.loads(raw_path.read_text()) if raw_path.exists() else {"list": [], "detail": {}}
    known = {x["url"] for x in data["list"]}
    since = max((x["date"] for x in data["list"] if x.get("date")), default=since_default)
    new = [x for x in list_actions(since) if x["url"] not in known]
    for item in new:
        data["detail"][item["url"]] = {"body": fetch_action_body(item["url"])}
        time.sleep(0.5)
    data["list"] = new + data["list"]
    data["fetched_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raw_path.write_text(json.dumps(data, ensure_ascii=False))
    return len(new)


def download_snapshot(snap_dir: Path) -> Path:
    """Save today's SDN.CSV and ADD.CSV into snap_dir/YYYY-MM-DD/."""
    day = dt.date.today().isoformat()
    target = snap_dir / day
    target.mkdir(parents=True, exist_ok=True)
    for name in ("SDN.CSV", "ADD.CSV"):
        (target / name).write_bytes(_get(SLS + name).content)
    return target
