import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ofac_tracker import current_lists as cl  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def test_ofac_snapshot_excludes_vessels():
    snap = cl.read_ofac(FIX / "ofac")
    st = cl.ofac_stats(snap)
    assert st["total_records"] == 3            # vessel 307 excluded
    assert st["total_aliases"] == 3            # vessel alias excluded
    assert st["dominicans"] == 1
    assert st["by_type"] == {"entity": 2, "individual": 1}
    assert snap["entries"]["306"]["nationalities"] == ["Dominican Republic", "Spain"]


def test_un_xml():
    un = cl.read_un(FIX / "un" / "consolidated.xml")
    st = cl.un_stats(un)
    assert un["generated"] == "2026-10-20"
    assert st["total_records"] == 3 and st["total_aliases"] == 2 and st["dominicans"] == 1
    new = [e for e in un["entries"] if e["listed_on"] == "2026-10-15"]
    assert {e["name"] for e in new} == {"JOHN DOE", "ACME TRADING"}
    assert new[0]["regime"] == "DPRK"
