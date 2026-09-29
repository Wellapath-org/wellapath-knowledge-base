#!/usr/bin/env python3
"""Build facilities.ng.v1.2.json — v1.1 with the NHFR enrichment removed.

    python3 tools/build_facilities_v1_2.py            # write
    python3 tools/build_facilities_v1_2.py --check    # verify, write nothing

Why this artifact exists
------------------------
`facilities.ng.v1.1.json` is `facilities.ng.v1.0.json` plus 45 telephone
numbers taken from an NHFR export. NHFR publishes no licence and reserves all
rights, so those 45 values have no established redistribution basis. v1.2 is
v1.0's facility records — byte-identical in identity, coordinates, type and
state — carrying a corrected licence block.

Nothing is invented and nothing is dropped. The record set, the identifiers
and the coordinates are exactly v1.0's and therefore exactly v1.1's: only the
45 phone values and the metadata differ.

Licensing
---------
The record set is derived from GRID3 (CC BY 4.0) and HOTOSM/OpenStreetMap
(ODbL 1.0). 896 of the 5,344 records are OSM-derived, so the database is a
Derivative Database under ODbL 1.0 §1.0 and is offered under that licence,
with CC BY 4.0 attribution for the GRID3 portion carried alongside. See
DATA_SOURCES.md and docs/FACILITIES_ODBL_LINEAGE.md.
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "facilities.ng.v1.0.json")
SUPERSEDED = os.path.join(ROOT, "facilities.ng.v1.1.json")
OUT = os.path.join(ROOT, "facilities.ng.v1.2.json")

VERSION = "1.2"
RELEASE_DATE = "2026-09-29"

CONTACT_FIELDS = ("phone", "opening_hours")

LICENCE = {
    "database_licence": "ODbL-1.0",
    "database_licence_url": "https://opendatacommons.org/licenses/odbl/1-0/",
    "database_licence_statement": (
        "This facility database is offered under the Open Database License "
        "1.0. It is a Derivative Database under ODbL 1.0 section 1.0: "
        "OpenStreetMap records are modified and merged into it rather than "
        "included unaltered. The complete machine-readable database is this "
        "file, published at no charge."
    ),
    "scope": (
        "This licence covers the facility database only. It does not place "
        "the WellaPath application source code, the clinical engine or any "
        "other product code under ODbL."
    ),
    "attribution": [
        "© OpenStreetMap contributors",
        (
            "Center for Integrated Earth System Information (CIESIN), "
            "Columbia University (2024). GRID3 NGA Health Facilities v2.0. "
            "Licensed CC BY 4.0."
        ),
        (
            "Produced with the Humanitarian OpenStreetMap Team's HOT Export "
            "Tool, via the Humanitarian Data Exchange."
        ),
    ],
    "attribution_urls": {
        "openstreetmap_copyright": "https://www.openstreetmap.org/copyright",
        "odbl": "https://opendatacommons.org/licenses/odbl/1-0/",
        "cc_by_4_0": "https://creativecommons.org/licenses/by/4.0/",
        "grid3_dataset": (
            "https://data.grid3.org/datasets/"
            "GRID3::grid3-nga-health-facilities-/explore"
        ),
        "hotosm_dataset": (
            "https://data.humdata.org/dataset/hotosm_nga_health_facilities"
        ),
    },
    "modifications": (
        "WellaPath restricted the sources to Lagos, the FCT and Kano; "
        "normalised state names; mapped source facility types onto a "
        "five-value enumeration, excluding 746 unmappable records; validated "
        "coordinates against Nigeria's bounding box and rounded them to seven "
        "decimal places; title-cased names and collapsed internal whitespace; "
        "discarded 456 OpenStreetMap records as duplicates of GRID3 records; "
        "merged the remainder into one table with WellaPath identifiers; and "
        "derived emergency_capable from facility type. The data is modified "
        "from the originals."
    ),
    "no_endorsement": (
        "GRID3, CIESIN, Columbia University, the Humanitarian OpenStreetMap "
        "Team, OpenStreetMap contributors, the Government of Nigeria and the "
        "Federal Ministry of Health do not endorse WellaPath or this derived "
        "work."
    ),
}

SUPERSESSION = {
    "supersedes": "1.1",
    "reason": (
        "Version 1.1 carried 45 telephone numbers imported directly from a "
        "Nigeria Health Facility Registry export. NHFR publishes no licence "
        "and no terms of use, and its only public rights statement reserves "
        "all rights, so written redistribution permission for those values "
        "was never captured. They are removed here."
    ),
    "not_a_privacy_incident": (
        "No personal-data breach was established. The removed values carry no "
        "named individual, and the source export's officer-contact columns "
        "are empty on every row. The final classification is a public-source "
        "facility-data licensing and attribution gap."
    ),
    "records_changed": 0,
    "identities_preserved": True,
    "coordinates_preserved": True,
    "rollback": "docs/FACILITIES_V1_2_ROLLBACK.md",
}


def canonical_bytes(obj):
    """Stable serialisation, so the checksum is reproducible."""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False).encode("utf-8")


def build():
    with open(BASE, encoding="utf-8") as handle:
        base = json.load(handle)

    facilities = [dict(record) for record in base["facilities"]]

    # v1.0 already carries no contact value. Assert rather than assume: this
    # is the whole point of the artifact.
    for record in facilities:
        for field in CONTACT_FIELDS:
            if record.get(field) is not None:
                raise SystemExit(
                    "refusing to build: %s carries %s" % (record["facility_id"], field)
                )

    meta = dict(base["_metadata"])
    meta["version"] = VERSION
    meta["release_date"] = RELEASE_DATE
    meta["total_facilities"] = len(facilities)
    meta["licence"] = LICENCE
    meta["supersession"] = SUPERSESSION
    # v1.0's source list is already the two licensed sources and nothing else.
    meta["sources"] = base["_metadata"]["sources"]

    return {"_metadata": meta, "facilities": facilities}


def main():
    check = "--check" in sys.argv
    artifact = build()
    payload = canonical_bytes(artifact)
    digest = hashlib.sha256(payload).hexdigest()

    if check:
        if not os.path.exists(OUT):
            raise SystemExit("FAIL: %s does not exist" % OUT)
        with open(OUT, "rb") as handle:
            on_disk = handle.read()
        if on_disk != payload:
            raise SystemExit("FAIL: %s is not what the generator produces" % OUT)
        print("OK   facilities.ng.v1.2.json is reproducible")
        print("     sha256 %s" % digest)
        print("     bytes  %d" % len(payload))
        return

    with open(OUT, "wb") as handle:
        handle.write(payload)
    print("wrote  %s" % OUT)
    print("sha256 %s" % digest)
    print("bytes  %d" % len(payload))
    print("records %d" % len(artifact["facilities"]))


if __name__ == "__main__":
    main()
