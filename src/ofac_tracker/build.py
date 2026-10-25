"""Build the analytical model (SQLite star schema), Power BI CSV exports and the
dashboard JSON from the raw OFAC Recent Actions archive.

Usage:
    python -m ofac_tracker.build            # rebuild everything from data/raw
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .parse_actions import parse_body
from .programs import family, primary_family

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "ofac_recent_actions_raw.json"
DB = ROOT / "data" / "ofac_tracker.sqlite"
PBI = ROOT / "data" / "powerbi"
DASH = ROOT / "docs" / "data.json"
SCHEMA = ROOT / "sql" / "schema.sql"

COUNTRY_ALIASES = {
    "Russian Federation": "Russia",
    "United Arab Emirates": "United Arab Emirates",
    "UAE": "United Arab Emirates",
    "Korea, North": "North Korea",
    "Hong Kong": "China (Hong Kong)",
    "Burma": "Burma (Myanmar)",
    "Turkiye": "Turkey",
    "Türkiye": "Turkey",
}


def norm_country(c: str) -> str:
    c = (c or "Unknown").strip().strip(".")
    if c.lower().startswith("undetermined") or not c:
        return "Unknown"
    return COUNTRY_ALIASES.get(c, c)


def load_actions(raw_path: Path = RAW) -> list[dict]:
    data = json.loads(raw_path.read_text())
    actions = []
    for item in data["list"]:
        det = data["detail"].get(item["url"], {})
        actions.append({**item, "body": det.get("body", "")})
    # newest first in source; sort ascending for stable ids
    actions.sort(key=lambda a: (a.get("date") or "", a["url"]))
    return actions


def build(raw_path: Path = RAW) -> dict:
    actions = load_actions(raw_path)
    PBI.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    # rebuild in place (drop objects instead of deleting the file)
    con.executescript("""DROP VIEW IF EXISTS v_monthly_net; DROP TABLE IF EXISTS bridge_change_program;
        DROP TABLE IF EXISTS fact_list_change; DROP TABLE IF EXISTS dim_action; DROP TABLE IF EXISTS dim_date;""")
    con.executescript(SCHEMA.read_text())

    change_rows, bridge_rows = [], []
    cid = 0
    for aid, a in enumerate(actions, start=1):
        changes = parse_body(a["body"])
        con.execute(
            "INSERT INTO dim_action VALUES (?,?,?,?,?)",
            (aid, a["date"], a["title"], "https://ofac.treasury.gov" + a["url"], len(changes)),
        )
        for ch in changes:
            cid += 1
            fam = primary_family(ch.programs)
            row = (cid, aid, a["date"], ch.action, ch.list_name, ch.entity_type, ch.name,
                   norm_country(ch.country), "|".join(ch.programs) or "UNSPECIFIED", fam)
            change_rows.append(row)
            for p in ch.programs or ["UNSPECIFIED"]:
                bridge_rows.append((cid, p, family(p) if p != "UNSPECIFIED" else "Unspecified"))

    con.executemany("INSERT INTO fact_list_change VALUES (?,?,?,?,?,?,?,?,?,?)", change_rows)
    con.executemany("INSERT INTO bridge_change_program VALUES (?,?,?)", bridge_rows)

    # date dimension
    dates = sorted({r[2] for r in change_rows if r[2]} | {a["date"] for a in actions if a["date"]})
    if dates:
        d0, d1 = dt.date.fromisoformat(dates[0]), dt.date.fromisoformat(dates[-1])
        cur, drows = d0, []
        while cur <= d1:
            drows.append((cur.isoformat(), cur.year, (cur.month - 1) // 3 + 1, cur.month,
                          cur.strftime("%Y-%m"), cur.strftime("%b"), cur.isoweekday()))
            cur += dt.timedelta(days=1)
        con.executemany("INSERT INTO dim_date VALUES (?,?,?,?,?,?,?)", drows)
    con.commit()
    con.execute("VACUUM")

    _export_csv(con)
    summary = _export_dashboard(con)
    con.close()
    return summary


def _export_csv(con: sqlite3.Connection) -> None:
    for table in ("fact_list_change", "bridge_change_program", "dim_action", "dim_date"):
        cur = con.execute(f"SELECT * FROM {table}")
        cols = [c[0] for c in cur.description]
        with open(PBI / f"{table}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            w.writerows(cur.fetchall())


def _export_dashboard(con: sqlite3.Connection) -> dict:
    q = lambda sql, *p: con.execute(sql, p).fetchall()  # noqa: E731

    # Compact cube for client-side filtering: month x action x family x country x type
    cube = q("""SELECT substr(change_date,1,7) m, action, program_family, country, entity_type,
                       list_name, COUNT(*) FROM fact_list_change GROUP BY 1,2,3,4,5,6""")
    latest = q("""SELECT f.change_date, f.action, f.entity_type, f.name, f.country, f.programs,
                         f.program_family, a.url
                  FROM fact_list_change f JOIN dim_action a USING(action_id)
                  WHERE f.list_name='SDN'
                  ORDER BY f.change_date DESC, f.change_id DESC LIMIT 400""")
    actions = q("""SELECT action_date, title, url, n_changes FROM dim_action
                   ORDER BY action_date DESC LIMIT 60""")
    n_actions = q("SELECT COUNT(*), MIN(action_date), MAX(action_date) FROM dim_action")[0]
    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coverage": {"from": n_actions[1], "to": n_actions[2], "actions": n_actions[0]},
        "dims": ["month", "action", "family", "country", "type", "list"],
        "cube": [list(r) for r in cube],
        "latest": [dict(zip(["date", "action", "type", "name", "country", "programs", "family", "url"], r))
                   for r in latest],
        "actions": [dict(zip(["date", "title", "url", "n"], r)) for r in actions],
    }
    DASH.write_text(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return summary




def render_dashboards() -> None:
    """docs/index.html (GitHub Pages, fetches data.json) + dist/ofac_dashboard.html (self-contained)."""
    tpl = (ROOT / "dashboard" / "template.html").read_text()
    head = "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
    page = tpl.replace("<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">", "<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">", 1)
    (ROOT / "docs" / "index.html").write_text(head + page.replace("<header class=\"mast\">", "</head><body>\n<header class=\"mast\">", 1) + "\n</body></html>\n")
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    data = DASH.read_text().replace("</", "<\\/")
    (dist / "ofac_dashboard.html").write_text(tpl.replace("__DATA__", data))


if __name__ == "__main__":
    s = build()
    render_dashboards()
    print(f"Built {len(s['cube'])} cube rows; coverage {s['coverage']}")
