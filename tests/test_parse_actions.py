import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ofac_tracker.parse_actions import parse_body  # noqa: E402
from ofac_tracker.programs import family, primary_family  # noqa: E402
from ofac_tracker.snapshot_diff import diff  # noqa: E402

BODY = (
    "Specially Designated Nationals List Update "
    "The following individuals have been added to OFAC's SDN List: "
    "DOE, John (a.k.a. DOE, Johnny), Panama City, Panama; DOB 01 Jan 1970; nationality Panama; "
    "Gender Male (individual) [IRAN-EO13902] (Linked To: ACME LTD). "
    "SMITH, Ana, Caracas, Venezuela; DOB 02 Feb 1980; citizen Venezuela (individual) [VENEZUELA-EO13850]. "
    "The following entities have been added to OFAC's SDN List: "
    "ACME LTD, 2 Main Road, Singapore 159086, Singapore; Organization Type: Trade [IRAN-EO13902]. "
    "The following deletions have been made to OFAC's SDN List: "
    "OLD CORP, Moscow, Russia [RUSSIA-EO14024]. "
    "The following entries have been changed on OFAC's SDN List: "
    "SHIP ONE (IMO 1234567) Vessel Type Tanker; Flag Iran (vessel) [IRAN] -to- "
    "SHIP ONE (IMO 1234567) Vessel Type Tanker; Flag Panama (vessel) [IRAN] [SDGT]. "
    "Unrelated Administrative List Changes: None"
)


def test_sections_and_actions():
    ch = parse_body(BODY)
    assert [c.action for c in ch] == ["added", "added", "added", "removed", "updated"]
    assert all(c.list_name == "SDN" for c in ch)


def test_fields():
    ch = parse_body(BODY)
    assert ch[0].name == "DOE, John"
    assert ch[0].country == "Panama"
    assert ch[0].entity_type == "individual"
    assert ch[1].country == "Venezuela"
    assert ch[2].entity_type == "entity" and ch[2].country == "Singapore"
    assert ch[3].country == "Russia"
    # updates take the NEW version of the entry
    assert ch[4].entity_type == "vessel" and ch[4].country == "Panama"
    assert ch[4].programs == ["IRAN", "SDGT"]


def test_program_families():
    assert family("RUSSIA-EO14024") == "Russia / Ukraine"
    assert family("ILLICIT-DRUGS-EO14059") == "Counter Narcotics"
    assert family("BPI-SUDAN-14098") == "Sudan / South Sudan"
    assert primary_family(["IFSR", "SDGT"]) == "Counter Terrorism"


def test_snapshot_diff():
    prev = {"1": {"name": "A", "sdn_type": "entity", "program": "X", "remarks": ""},
            "2": {"name": "B", "sdn_type": "entity", "program": "X", "remarks": ""}}
    curr = {"2": {"name": "B2", "sdn_type": "entity", "program": "X", "remarks": ""},
            "3": {"name": "C", "sdn_type": "entity", "program": "Y", "remarks": ""}}
    ev = {e["action"]: e for e in diff(prev, curr)}
    assert set(ev) == {"added", "removed", "updated"}
    assert ev["updated"]["changed_fields"] == "name"
