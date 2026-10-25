"""Group OFAC program tags into readable program families for reporting."""
from __future__ import annotations

RULES: list[tuple[tuple[str, ...], str]] = [
    (("RUSSIA", "UKRAINE", "CAATSA - RUSSIA", "PEESA", "MAGNIT"), "Russia / Ukraine"),
    (("BELARUS",), "Belarus"),
    (("IRAN", "IRGC", "IFCA", "HRIT-IR", "CAATSA - IRAN", "ISA"), "Iran"),
    (("NPWMD", "NONPRO"), "Non-Proliferation"),
    (("SDGT", "FTO", "SDT"), "Counter Terrorism"),
    (("ILLICIT-DRUGS", "SDNTK", "SDNT"), "Counter Narcotics"),
    (("TCO",), "Transnational Crime"),
    (("CYBER",), "Cyber"),
    (("GLOMAG",), "Global Magnitsky"),
    (("VENEZUELA",), "Venezuela"),
    (("CUBA",), "Cuba"),
    (("DPRK", "NKSPEA"), "North Korea"),
    (("SYRIA", "PAARSSR", "HRIT-SY"), "Syria"),
    (("BURMA",), "Burma"),
    (("NICARAGUA",), "Nicaragua"),
    (("SUDAN", "DARFUR", "SOUTH SUDAN"), "Sudan / South Sudan"),
    (("YEMEN",), "Yemen"),
    (("LEBANON", "HIZBALLAH"), "Lebanon / Hizballah"),
    (("IRAQ",), "Iraq"),
    (("BALKANS", "WESTERN BALKANS"), "Western Balkans"),
    (("DRCONGO", "CAR", "MALI", "SOMALIA", "LIBYA", "ETHIOPIA", "ZIMBABWE", "BURUNDI"), "Africa (other)"),
    (("HK-EO", "HKAA", "CMIC", "PAIPA", "UHRPA"), "China / Hong Kong"),
    (("WEST-BANK", "MIDDLE-EAST"), "Middle East (other)"),
    (("HOSTAGES",), "Hostage-taking"),
    (("ICC",), "ICC"),
    (("ELECTION", "SANCTIONS-EO13848"), "Election Interference"),
]


def family(tag: str) -> str:
    t = tag.upper().strip()
    if t.startswith("BPI-"):
        t = t[4:]
    for prefixes, name in RULES:
        if any(t == p or t.startswith(p + "-") or t.startswith(p) for p in prefixes):
            return name
    return "Other"


def primary_family(tags: list[str]) -> str:
    fams = [family(t) for t in tags]
    for f in fams:
        if f != "Other":
            return f
    return fams[0] if fams else "Unspecified"
