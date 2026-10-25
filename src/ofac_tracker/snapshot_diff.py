"""Diff two daily SDN.CSV snapshots by OFAC's stable entity number (ent_num).

Produces added / removed / updated events, where "updated" means any tracked
attribute (name, type, programs, remarks) changed between the two snapshots.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

SDN_COLS = ["ent_num", "name", "sdn_type", "program", "title", "call_sign", "vess_type",
            "tonnage", "grt", "vess_flag", "vess_owner", "remarks"]
ADD_COLS = ["ent_num", "add_num", "address", "city", "country", "add_remarks"]
TRACKED = ["name", "sdn_type", "program", "remarks"]


def _clean(v: str) -> str:
    v = (v or "").strip()
    return "" if v == "-0-" else v


def read_sdn(folder: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with open(folder / "SDN.CSV", newline="", encoding="latin-1") as fh:
        for rec in csv.reader(fh):
            if len(rec) < len(SDN_COLS) or not rec[0].strip().isdigit():
                continue
            row = {k: _clean(v) for k, v in zip(SDN_COLS, rec)}
            rows[row["ent_num"]] = row
    countries: dict[str, str] = {}
    add = folder / "ADD.CSV"
    if add.exists():
        with open(add, newline="", encoding="latin-1") as fh:
            for rec in csv.reader(fh):
                if len(rec) >= 5 and rec[0].strip().isdigit():
                    c = _clean(rec[4])
                    if c and rec[0] not in countries:
                        countries[rec[0]] = c
    for k, r in rows.items():
        r["country"] = countries.get(k, "Unknown")
        r["sdn_type"] = (r["sdn_type"] or "entity").lower()
    return rows


def _fingerprint(row: dict) -> str:
    return hashlib.sha1("||".join(row.get(k, "") for k in TRACKED).encode()).hexdigest()


def diff(prev: dict[str, dict], curr: dict[str, dict]) -> list[dict]:
    events = []
    for k in curr.keys() - prev.keys():
        events.append({"action": "added", **curr[k]})
    for k in prev.keys() - curr.keys():
        events.append({"action": "removed", **prev[k]})
    for k in curr.keys() & prev.keys():
        if _fingerprint(curr[k]) != _fingerprint(prev[k]):
            changed = [c for c in TRACKED if curr[k].get(c) != prev[k].get(c)]
            events.append({"action": "updated", "changed_fields": "|".join(changed), **curr[k]})
    return events


def programs_of(row: dict) -> list[str]:
    raw = row.get("program", "")
    return [p.strip(" []") for p in raw.replace("] [", "|").split("|") if p.strip(" []")]
