"""End-to-end daily pipeline.

    python -m ofac_tracker.pipeline            # fetch new OFAC actions + snapshot + rebuild
    python -m ofac_tracker.pipeline --offline  # rebuild from data already on disk

Steps
1. Incrementally scrape new "Sanctions List Updates" from OFAC Recent Actions.
2. Download today's official SDN.CSV/ADD.CSV snapshot and diff it with the previous one.
3. Rebuild the SQLite model, Power BI CSV exports and the dashboard JSON.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import build, snapshot_diff, sources

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS = ROOT / "data" / "snapshots"
DIFF_LOG = ROOT / "data" / "snapshot_changes.csv"


def run_snapshot_diff() -> int:
    today = sources.download_snapshot(SNAPSHOTS)
    days = sorted(p for p in SNAPSHOTS.iterdir() if p.is_dir())
    if len(days) < 2:
        print("First snapshot stored; diff will start on the next run.")
        return 0
    prev, curr = days[-2], days[-1]
    events = snapshot_diff.diff(snapshot_diff.read_sdn(prev), snapshot_diff.read_sdn(curr))
    new_file = not DIFF_LOG.exists()
    with open(DIFF_LOG, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["snapshot_date", "previous_snapshot", "action", "ent_num", "name",
                        "sdn_type", "programs", "country", "changed_fields"])
        for e in events:
            w.writerow([curr.name, prev.name, e["action"], e["ent_num"], e["name"], e["sdn_type"],
                        "|".join(snapshot_diff.programs_of(e)), e.get("country", ""),
                        e.get("changed_fields", "")])
    # keep only the 2 most recent full snapshots in the repo (history lives in the diff log)
    for old in days[:-2]:
        for f in old.iterdir():
            f.unlink()
        old.rmdir()
    print(f"Snapshot diff {prev.name} -> {curr.name}: {len(events)} changes")
    return len(events)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="skip downloads, rebuild only")
    args = ap.parse_args(argv)

    if not args.offline:
        n = sources.update_raw_actions(build.RAW)
        print(f"New OFAC list-update actions: {n}")
        try:
            run_snapshot_diff()
        except Exception as exc:  # snapshot is a complement; never block the build
            print(f"WARNING snapshot step failed: {exc}", file=sys.stderr)

    summary = build.build()
    build.render_dashboards()
    print(json.dumps(summary["coverage"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
