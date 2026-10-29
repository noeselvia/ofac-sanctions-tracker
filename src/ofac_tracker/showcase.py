"""Render the 'showcase' edition: one long, editorial page that tells the story of the
sanctions lists (hero → latest release → five-year view → programs → OFAC vs UN →
register → how it is built). Data is embedded so the page works as a single file.

    python -m ofac_tracker.showcase
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
DIST = ROOT / "dist"
TEMPLATE = ROOT / "dashboard" / "showcase.html"
REPO_URL = "https://github.com/noeselvia/ofac-sanctions-tracker"


def _load(name: str):
    p = DOCS / name
    return json.loads(p.read_text()) if p.exists() else None


def payload() -> dict:
    dash = _load("data.json")
    incl = _load("inclusions.json")
    rel = {r["id"]: r for r in incl["releases"]}
    latest_id = incl["releases"][0]["id"]
    last_date = dt.date.fromisoformat(incl["releases"][0]["date"])
    cutoff = (last_date - dt.timedelta(days=365)).isoformat()
    register, latest = [], []
    for aid, t, name, country, progs, fam, akas, linked, _entry in incl["items"]:
        r = rel[aid]
        if r["date"] >= cutoff:
            register.append([r["date"], t, name, country, progs, fam, akas, aid])
        if aid == latest_id:
            latest.append({"type": incl["types"][t], "name": name, "country": country, "family": fam,
                           "programs": progs, "aliases": akas.split("|") if akas else [],
                           "linked": linked.split("|") if linked else []})
    return {
        "generated_at": dash["generated_at"],
        "coverage": dash["coverage"],
        "cube": dash["cube"],
        "types": incl["types"],
        "latest": {"release": rel[latest_id], "items": latest},
        "releases": {r["id"]: [r["date"], r["title"], r["url"]] for r in incl["releases"] if r["date"] >= cutoff},
        "register": register,
        "ofac": _load("ofac_overview.json"),
        "un": _load("un_overview.json"),
        "repo": REPO_URL,
    }


def render() -> None:
    tpl = TEMPLATE.read_text()
    data = json.dumps(payload(), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = tpl.replace("__DATA__", data)
    DIST.mkdir(exist_ok=True)
    (DIST / "ofac_showcase.html").write_text(page)
    head = ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n")
    (DOCS / "showcase.html").write_text(head + page.replace("<nav class=\"gnav\"", "</head><body>\n<nav class=\"gnav\"", 1)
                                        + "\n</body></html>\n")


if __name__ == "__main__":
    render()
    print("showcase rendered")
