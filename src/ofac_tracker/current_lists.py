"""Readers for the *current* sanctions lists (full snapshot, not just changes).

- OFAC SDN: SDN.CSV + ALT.CSV + ADD.CSV from the Sanctions List Service.
- UN Security Council Consolidated List: consolidated.xml.

Vessels are excluded from every count on the overview pages (and aircraft are
kept), mirroring the reporting convention used for these pages.
"""
from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from .geo import is_dominican

EXCLUDED_TYPES = {"vessel"}


def _clean(v: str) -> str:
    v = (v or "").strip()
    return "" if v == "-0-" else v


def _nationalities_from_remarks(remarks: str) -> list[str]:
    from .parse_actions import extract_nationalities
    return extract_nationalities(remarks or "")


# --------------------------------------------------------------------------- OFAC
def read_ofac(folder: Path) -> dict:
    """Return entries + aliases from an OFAC snapshot folder, vessels excluded."""
    entries: dict[str, dict] = {}
    with open(folder / "SDN.CSV", newline="", encoding="latin-1") as fh:
        for rec in csv.reader(fh):
            if len(rec) < 12 or not rec[0].strip().isdigit():
                continue
            etype = (_clean(rec[2]) or "entity").lower()
            if etype in EXCLUDED_TYPES:
                continue
            entries[rec[0].strip()] = {
                "uid": rec[0].strip(), "name": _clean(rec[1]), "type": etype,
                "programs": [p.strip(" []") for p in _clean(rec[3]).replace("] [", "|").split("|") if p.strip(" []")],
                "nationalities": _nationalities_from_remarks(_clean(rec[11])),
                "countries": [],
            }
    aliases: list[dict] = []
    alt = folder / "ALT.CSV"
    if alt.exists():
        with open(alt, newline="", encoding="latin-1") as fh:
            for rec in csv.reader(fh):
                if len(rec) >= 4 and rec[0].strip() in entries:
                    aliases.append({"uid": rec[0].strip(), "alt_uid": rec[1].strip(),
                                    "quality": _clean(rec[2]), "alias": _clean(rec[3])})
    add = folder / "ADD.CSV"
    if add.exists():
        with open(add, newline="", encoding="latin-1") as fh:
            for rec in csv.reader(fh):
                if len(rec) >= 5 and rec[0].strip() in entries:
                    c = _clean(rec[4])
                    if c and c not in entries[rec[0].strip()]["countries"]:
                        entries[rec[0].strip()]["countries"].append(c)
    return {"entries": entries, "aliases": aliases}


def ofac_stats(snap: dict) -> dict:
    ents = snap["entries"].values()
    dom = [e for e in ents if any(is_dominican(c) for c in e["nationalities"] + e["countries"])]
    return {
        "total_records": len(snap["entries"]),
        "total_aliases": len(snap["aliases"]),
        "dominicans": len(dom),
        "by_type": dict(Counter(e["type"] for e in ents)),
    }


# --------------------------------------------------------------------------- UN
def _txt(el, tag: str) -> str:
    x = el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def read_un(path: Path) -> dict:
    root = ET.parse(path).getroot()
    out = []
    for kind, tag, alias_tag, addr_tag in (("individual", "INDIVIDUAL", "INDIVIDUAL_ALIAS", "INDIVIDUAL_ADDRESS"),
                                            ("entity", "ENTITY", "ENTITY_ALIAS", "ENTITY_ADDRESS")):
        for el in root.iter(tag):
            name = " ".join(p for p in (_txt(el, t) for t in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")) if p)
            nats = [(v.text or "").strip() for n in el.findall("NATIONALITY") for v in n.findall("VALUE") if v.text]
            als = [{"alias": _txt(a, "ALIAS_NAME"), "quality": _txt(a, "QUALITY")}
                   for a in el.findall(alias_tag) if _txt(a, "ALIAS_NAME")]
            ctys = []
            for a in el.findall(addr_tag):
                c = _txt(a, "COUNTRY")
                if c and c not in ctys:
                    ctys.append(c)
            out.append({
                "uid": _txt(el, "DATAID"), "ref": _txt(el, "REFERENCE_NUMBER"), "name": name, "type": kind,
                "regime": _txt(el, "UN_LIST_TYPE"), "listed_on": _txt(el, "LISTED_ON")[:10],
                "nationalities": nats, "countries": ctys, "aliases": als,
            })
    generated = root.attrib.get("dateGenerated", "")[:10]
    return {"generated": generated, "entries": out}


def un_stats(un: dict) -> dict:
    ents = un["entries"]
    return {
        "total_records": len(ents),
        "total_aliases": sum(len(e["aliases"]) for e in ents),
        "dominicans": sum(1 for e in ents if any(is_dominican(c) for c in e["nationalities"] + e["countries"])),
        "by_type": dict(Counter(e["type"] for e in ents)),
    }


def name_key(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())
