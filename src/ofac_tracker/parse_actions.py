"""Parse the free-text body of an OFAC "Recent Action" into structured list changes.

OFAC publishes every sanctions-list update as a web page whose body contains
sections such as:

    The following individuals have been added to OFAC's SDN List:
    DOE, John, Caracas, Venezuela; DOB 01 Jan 1970; nationality Venezuela; ... (individual) [VENEZUELA-EO13850].
    ...
    The following deletions have been made to OFAC's SDN List:
    ...
    The following entries have been changed on OFAC's SDN List:
    OLD ENTRY -to- NEW ENTRY

This module turns that text into one record per affected list entry.
Only public, already-published OFAC data is processed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

SECTION_RE = re.compile(
    r"The following (?P<what>[^:]{0,120}?)\s+(?:has|have)\s+been\s+(?P<verb>[^:]{0,160}?):",
    re.IGNORECASE,
)
END_MARKERS = re.compile(r"Unrelated Administrative List Changes", re.IGNORECASE)
TAG_RE = re.compile(r"\[([A-Z0-9][A-Z0-9 \-_.]*?)\]")
ENTRY_SPLIT_RE = re.compile(r"(?<=[\]\)])\.\s*(?=[A-Z0-9\"'À-ɏ])")
TYPE_RE = re.compile(r"\((individual|vessel|aircraft)\)", re.IGNORECASE)

# Program tags that are qualifiers rather than sanctions programs.
NON_PROGRAM_TAGS = {"IFSR", "FSE-IR", "FSE-SY"}


@dataclass
class ListChange:
    action: str          # added | removed | updated
    list_name: str       # SDN | NON-SDN
    entity_type: str     # individual | entity | vessel | aircraft
    name: str
    programs: list[str] = field(default_factory=list)
    country: str = "Unknown"
    aliases: list[str] = field(default_factory=list)
    linked_to: list[str] = field(default_factory=list)
    entry_text: str = ""     # OFAC's published entry text (new version for updates)
    nationalities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("programs", "aliases", "linked_to", "nationalities"):
            d[k] = "|".join(getattr(self, k))
        return d


AKA_RE = re.compile(r"\b[af]\.k\.a\.,?\s+\"?([^;()\"]+)")
LINKED_RE = re.compile(r"Linked To:\s*([^;)]+)")


def extract_aliases(entry: str) -> list[str]:
    out = []
    for a in AKA_RE.findall(entry):
        a = a.strip(" ,")
        if a and a not in out:
            out.append(a)
    return out


def extract_linked(entry: str) -> list[str]:
    out = []
    for a in LINKED_RE.findall(entry):
        a = a.strip(" ,")
        if a and a not in out:
            out.append(a)
    return out


def classify_action(text: str) -> str | None:
    t = text.lower()
    if "delet" in t or "remov" in t:
        return "removed"
    if "updat" in t or "chang" in t or "amend" in t:
        return "updated"
    if "add" in t or "designat" in t:
        return "added"
    return None


def classify_list(verb_text: str) -> str:
    t = verb_text.upper()
    if "SDN LIST" in t and "NON-SDN" not in t:
        return "SDN"
    return "NON-SDN"


def _strip_parens(s: str) -> str:
    s = TAG_RE.sub("", s)
    # remove nested parenthetical groups such as (a.k.a. ...) or (Chinese Simplified: ...)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\([^()]*\)", "", s)
    return s


VESSEL_HEAD_RE = re.compile(
    r"^(?P<name>[A-Z0-9][A-Z0-9 .'\-&/]*?)\s+(?P<vtype>[A-Z][a-z][A-Za-z/ \-]*?(?:Vessel|Tanker|Carrier|Cargo|Tug|Ship|Container Ship|Yacht))\s+(?P<flag>[A-Z][A-Za-z .'\-]*?) flag$"
)


def _vessel_head(entry: str):
    head = _strip_parens(entry).split(";")[0].strip()
    return VESSEL_HEAD_RE.match(head)


def extract_name(entry: str) -> str:
    vm = _vessel_head(entry)
    if vm:
        return vm.group("name").strip()
    head = _strip_parens(entry)
    head = head.split(";")[0]
    parts = [p.strip() for p in head.split(",") if p.strip()]
    if not parts:
        return entry[:80].strip()
    # Individuals: "LAST, First, City, Country" -> "LAST, First"
    if TYPE_RE.search(entry) and TYPE_RE.search(entry).group(1).lower() == "individual" and len(parts) > 1:
        return f"{parts[0]}, {parts[1]}"
    return parts[0]


# OFAC writes some countries "inverted" with a comma ("Korea, North").
INVERTED = {
    ("Korea", "North"): "North Korea", ("Korea", "South"): "South Korea",
    ("Congo", "Democratic Republic of the"): "Democratic Republic of the Congo",
    ("Congo", "Republic of the"): "Republic of the Congo",
    ("Virgin Islands", "British"): "British Virgin Islands", ("Virgin Islands", "U.S."): "U.S. Virgin Islands",
    ("Gambia", "The"): "The Gambia", ("Bahamas", "The"): "Bahamas", ("Man", "Isle of"): "Isle of Man",
    ("Micronesia", "Federated States of"): "Micronesia",
}
_COUNTRY_RE = r"([A-Z][A-Za-z .'\-]+?(?:, (?:North|South|The|British|U\.S\.|Isle of|Democratic Republic of the|Republic of the|Federated States of))?)"


def _fix_country(c: str) -> str:
    c = c.strip()
    if ", " in c:
        a, b = c.split(", ", 1)
        return INVERTED.get((a, b), c)
    return c


def extract_nationalities(entry: str) -> list[str]:
    out = []
    for m in re.finditer(r"\b(?:alt\. )?(?:nationality|citizen) " + _COUNTRY_RE + r"\.?(?:;|\)|\s*$)", entry):
        c = _fix_country(m.group(1).rstrip("."))
        if c not in out:
            out.append(c)
    return out


def extract_country(entry: str, entity_type: str) -> str:
    m = re.search(r"(?<!alt\. )\bnationality " + _COUNTRY_RE + r"(?:;|\)|$)", entry)
    if m:
        return _fix_country(m.group(1))
    m = re.search(r"(?<!alt\. )\bcitizen " + _COUNTRY_RE + r"(?:;|\)|$)", entry)
    if m:
        return _fix_country(m.group(1))
    if entity_type == "vessel":
        vm = _vessel_head(entry)
        if vm and vm.group("flag").strip().lower() not in {"unknown", "none identified"}:
            return vm.group("flag").strip()
        m = re.search(r"\b(?:Vessel )?Flag ([A-Z][A-Za-z .'\-]+?)(?:\s*\(|;|$)", entry)
        if m and m.group(1).strip().lower() not in {"unknown", "none identified"}:
            return m.group(1).strip()
    head = _strip_parens(entry).split(";")[0]
    parts = [p.strip() for p in head.split(",") if p.strip()]
    name_parts = 2 if entity_type == "individual" else 1   # "LAST, First" vs "COMPANY"
    if len(parts) > name_parts + 1 and (parts[-2], parts[-1]) in INVERTED:
        return INVERTED[(parts[-2], parts[-1])]
    if len(parts) > name_parts:
        cand = parts[-1]
        cand = re.sub(r"\s+\d[\w\- ]*$", "", cand).strip()  # drop trailing postal codes
        if cand and len(cand) <= 40 and not any(ch.isdigit() for ch in cand) and cand[0].isupper():
            return cand
    return "Unknown"


def extract_programs(entry: str) -> list[str]:
    tags = []
    for t in TAG_RE.findall(entry):
        t = t.strip()
        if t and t not in NON_PROGRAM_TAGS and t not in tags:
            tags.append(t)
    return tags


def split_entries(section_text: str) -> list[str]:
    parts = ENTRY_SPLIT_RE.split(section_text.strip())
    out = []
    for p in parts:
        p = p.strip().rstrip(".")
        # Entries always carry at least one program tag or a type marker.
        if TAG_RE.search(p) or TYPE_RE.search(p):
            out.append(p)
    return out


def parse_entry(raw: str, action: str, list_name: str) -> ListChange:
    entry = raw
    if action == "updated" and " -to- " in raw:
        entry = raw.split(" -to- ", 1)[1]
    tm = TYPE_RE.search(entry)
    etype = tm.group(1).lower() if tm else "entity"
    return ListChange(
        action=action,
        list_name=list_name,
        entity_type=etype,
        name=extract_name(entry),
        programs=extract_programs(entry),
        country=extract_country(entry, etype),
        aliases=extract_aliases(entry),
        nationalities=extract_nationalities(entry),
        linked_to=extract_linked(entry),
        entry_text=entry.strip(),
    )


def parse_body(body: str) -> list[ListChange]:
    body = re.sub(r"\s+", " ", body or "")
    end = END_MARKERS.search(body)
    if end:
        body = body[: end.start()]
    matches = list(SECTION_RE.finditer(body))
    changes: list[ListChange] = []
    for i, m in enumerate(matches):
        header = m.group(0)
        action = classify_action(m.group("what") + " " + m.group("verb"))
        if action is None:
            continue
        list_name = classify_list(m.group("verb"))
        start = m.end()
        stop = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section = body[start:stop]
        for raw in split_entries(section):
            changes.append(parse_entry(raw, action, list_name))
    return changes
