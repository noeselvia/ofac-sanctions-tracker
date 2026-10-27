"""Build the JSON behind the two list-overview pages (OFAC and UN).

Each page mirrors a compliance "list status" report:
last update · total records · total aliases · nationals of a focus country ·
new additions in the latest publication (+ their aliases) · type split ·
monthly inclusion trend for the current year · countries involved.

Vessels are excluded throughout.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter
from pathlib import Path

from . import current_lists as cl
from .geo import lookup

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "ofac_tracker.sqlite"
SNAPSHOTS = ROOT / "data" / "snapshots"
UN_XML = ROOT / "data" / "un" / "consolidated.xml"
OUT_OFAC = ROOT / "docs" / "ofac_overview.json"
OUT_UN = ROOT / "docs" / "un_overview.json"
MONTHS_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
             "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _countries_block(counter: Counter) -> list[dict]:
    out = []
    for name, n in counter.most_common():
        g = lookup(name)
        out.append({"name": name, "n": n, "iso": g[0] if g else None,
                    "lat": g[1] if g else None, "lon": g[2] if g else None})
    return out


def _latest_snapshot() -> Path | None:
    if not SNAPSHOTS.exists():
        return None
    days = sorted(p for p in SNAPSHOTS.iterdir() if p.is_dir() and (p / "SDN.CSV").exists())
    return days[-1] if days else None


# --------------------------------------------------------------------------- OFAC
def build_ofac() -> dict:
    con = sqlite3.connect(DB)
    q = lambda sql, *p: con.execute(sql, p).fetchall()  # noqa: E731
    rel = q("""SELECT a.action_id, a.action_date, a.title, a.url FROM dim_action a
               JOIN fact_list_change f USING(action_id)
               WHERE f.action='added' AND f.list_name='SDN' AND f.entity_type<>'vessel'
               GROUP BY 1 ORDER BY a.action_date DESC, a.action_id DESC LIMIT 1""")[0]
    last_any = q("SELECT MAX(action_date) FROM dim_action")[0][0]
    rows = q("""SELECT name, entity_type, country, programs, aliases FROM fact_list_change
                WHERE action_id=? AND action='added' AND list_name='SDN' AND entity_type<>'vessel'
                ORDER BY change_id""", rel[0])
    # nationalities are re-parsed from the stored notice text
    from .build import load_actions
    from .parse_actions import parse_body
    body = next(a["body"] for a in load_actions() if "https://ofac.treasury.gov" + a["url"] == rel[3])
    nat_by_name = {c.name: c.nationalities for c in parse_body(body) if c.action == "added"}

    snap_dir = _latest_snapshot()
    snap = cl.read_ofac(snap_dir) if snap_dir else None
    uid_by_name = {cl.name_key(e["name"]): e["uid"] for e in snap["entries"].values()} if snap else {}

    new_rows, new_aliases = [], []
    for name, etype, country, progs, akas in rows:
        uid = uid_by_name.get(cl.name_key(name))
        nats = nat_by_name.get(name) or ([] if etype != "individual" else [country])
        new_rows.append({"uid": uid, "name": name, "type": etype, "nationalities": nats,
                         "country": country, "programs": progs.replace("|", " · ")})
        if snap and uid:
            for a in snap["aliases"]:
                if a["uid"] == uid:
                    new_aliases.append({"uid": uid, "alt_uid": a["alt_uid"], "alias": a["alias"],
                                        "quality": a["quality"], "nationality": ", ".join(nats)})
        else:
            for a in [x for x in akas.split("|") if x]:
                new_aliases.append({"uid": uid, "alt_uid": None, "alias": a, "quality": "a.k.a.",
                                    "nationality": ", ".join(nats)})

    year = rel[1][:4]
    monthly = dict(q("""SELECT CAST(substr(change_date,6,2) AS INT), COUNT(*) FROM fact_list_change
                        WHERE action='added' AND list_name='SDN' AND entity_type<>'vessel'
                          AND substr(change_date,1,4)=? GROUP BY 1""", year))
    last_month = int(rel[1][5:7])
    trend = [{"m": MONTHS_ES[i - 1], "n": monthly.get(i, 0)} for i in range(1, last_month + 1)]

    ctry = Counter()
    for r in new_rows:
        for c in (r["nationalities"] or [r["country"]]):
            if c and c != "Unknown":
                ctry[c] += 1
    type_new = Counter(r[0] for r in q("""SELECT entity_type FROM fact_list_change
                       WHERE action='added' AND list_name='SDN' AND entity_type<>'vessel'
                         AND substr(change_date,1,4)=?""", year))
    out = {
        "list": "OFAC",
        "generated_at": _now(),
        "last_update": last_any,
        "stats": cl.ofac_stats(snap) if snap else None,
        "snapshot_date": snap_dir.name if snap_dir else None,
        "type_fallback": {"label": f"Inclusiones {year}", "by_type": dict(type_new)},
        "new": {"date": rel[1], "title": rel[2], "url": rel[3], "rows": new_rows, "aliases": new_aliases},
        "trend": {"year": year, "months": trend},
        "countries": _countries_block(ctry),
    }
    OUT_OFAC.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    con.close()
    return out


# --------------------------------------------------------------------------- UN
def build_un() -> dict:
    if not UN_XML.exists():
        out = {"list": "ONU", "generated_at": _now(), "available": False}
        OUT_UN.write_text(json.dumps(out))
        return out
    un = cl.read_un(UN_XML)
    ents = un["entries"]
    last_listed = max((e["listed_on"] for e in ents if e["listed_on"]), default="")
    new = [e for e in ents if e["listed_on"] == last_listed]
    year = last_listed[:4]
    monthly = Counter(int(e["listed_on"][5:7]) for e in ents if e["listed_on"].startswith(year))
    trend = [{"m": MONTHS_ES[i - 1], "n": monthly.get(i, 0)} for i in range(1, int(last_listed[5:7]) + 1)] if year else []
    ctry = Counter()
    for e in new:
        for c in (e["nationalities"] or e["countries"]):
            ctry[c] += 1
    out = {
        "list": "ONU",
        "available": True,
        "generated_at": _now(),
        "last_update": un["generated"] or last_listed,
        "stats": cl.un_stats(un),
        "regimes": Counter(e["regime"] for e in ents).most_common(),
        "new": {"date": last_listed, "title": f"Inclusiones del {last_listed}",
                "url": "https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list",
                "rows": [{"uid": e["ref"] or e["uid"], "name": e["name"], "type": e["type"],
                          "nationalities": e["nationalities"], "country": (e["countries"] or [""])[0],
                          "programs": e["regime"]} for e in new],
                "aliases": [{"uid": e["ref"] or e["uid"], "alt_uid": None, "alias": a["alias"], "quality": a["quality"],
                             "nationality": ", ".join(e["nationalities"])} for e in new for a in e["aliases"]]},
        "trend": {"year": year, "months": trend},
        "countries": _countries_block(ctry),
    }
    OUT_UN.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    return out


def build_all() -> None:
    build_ofac()
    build_un()


if __name__ == "__main__":
    o = build_ofac()
    u = build_un()
    print("OFAC new:", len(o["new"]["rows"]), "stats:", o["stats"], "| UN available:", u.get("available"))
