#!/usr/bin/env python3
"""Fail-closed validation of the SERVED projection of the GRID3 candidate.

    python3 tools/validate_facilities_grid3_served.py

The core proof is an independent reconstruction: this validator projects the
committed MASTER candidate's records with its own code (deliberately not the
generator's function), serializes them under the documented compact
convention, and requires the committed served artifact to match BYTE FOR BYTE.
On top of that it re-derives traceability from the GRID3 source CSV itself,
simulates the verified Mobile PR #79 parser's acceptance rules, scans for
NHFR markers and forbidden fields, and recomputes every figure in the size
report so a hand-edited number fails.

Standard library only, no network.
"""

import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities_grid3 import source as S
from build_facilities_grid3_candidate import (ATTRIBUTION_CITATION, CANDIDATE_PATH,
                                              GZIP_LEVEL, SERVED_PATH, SIZE_REPORT_PATH)
from vocab.artifact_io import load_json, repo_path, sha256_bytes, sha256_file
from vocab.schema_check import validate as schema_validate

SERVED_SCHEMA_PATH = repo_path("schema", "facilities_grid3_served.v2.schema.json")
V1_0_SHA256 = "1c7b939199ab4465156f4cb336910eea120fcaa70f8b1c0743fc9f7a7c03009e"

#: Keys that must not exist on any served record. The schema's
#: additionalProperties:false enforces this structurally; the byte scan below
#: enforces it against the committed bytes without trusting a JSON round-trip.
FORBIDDEN_RECORD_KEYS = ["phone", "opening_hours", "type", "emergency_capable",
                         "source_record", "facility_id", "lga", "country", "ward",
                         "services", "beds", "address"]

#: The verified Mobile PR #79 parser's per-record acceptance rules
#: (facilities_v2_parser.dart at wellapath-mobile 854377c0), transcribed.
def pr79_accepts(record):
    identifier = record.get("id")
    name = record.get("name")
    if not isinstance(identifier, str) or not identifier.strip():
        return False
    if not isinstance(name, str) or not name.strip():
        return False
    lat, lon = record.get("latitude"), record.get("longitude")
    for value in (lat, lon):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
    return -90 <= lat <= 90 and -180 <= lon <= 180


def reproject(master_record):
    """The validator's OWN projection of a master record — field selection
    only, values verbatim. Kept independent of the generator's function so a
    generator defect cannot validate itself."""
    return {
        "id": master_record["facility_id"],
        "name": master_record["name"],
        "state": master_record["state"],
        "city_area": master_record["city_area"],
        "latitude": master_record["latitude"],
        "longitude": master_record["longitude"],
    }


class Results:
    def __init__(self):
        self.checks = []

    def add(self, label, ok, detail=""):
        self.checks.append((label, bool(ok), detail))
        print("%-4s %s%s" % ("ok" if ok else "FAIL", label,
                             (" — " + str(detail)) if (detail and not ok) else ""))

    @property
    def failed(self):
        return [c for c in self.checks if not c[1]]


def main():
    r = Results()
    with open(SERVED_PATH, "rb") as handle:
        served_bytes = handle.read()
    served = json.loads(served_bytes)
    meta = served["_metadata"]
    records = served["facilities"]
    master = load_json(CANDIDATE_PATH)
    master_records = master["facilities"]

    # --- independent byte-for-byte reconstruction -------------------------------------------
    reconstructed = {
        "schema_version": "2.0",
        "_metadata": meta,
        "facilities": [reproject(m) for m in master_records],
    }
    reconstructed_bytes = json.dumps(
        reconstructed, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    r.add("served facilities are byte-identical to an independent reprojection of the master",
          reconstructed_bytes == served_bytes)
    r.add("served metadata binds the master by hash and count",
          meta["master_candidate"]["sha256"] == sha256_file(CANDIDATE_PATH)
          and meta["master_candidate"]["record_count"] == len(master_records)
          and meta["total_facilities"] == len(records))

    # --- schema and roles -------------------------------------------------------------------
    errors = schema_validate(served, load_json(SERVED_SCHEMA_PATH))
    r.add("served artifact satisfies the served schema", not errors, "; ".join(errors[:3]))
    r.add("three artifact roles are named apart (source / master audit / served)",
          meta["role"] == "served_projection"
          and master["_metadata"]["lineage"] == "grid3"
          and "source_record" in master_records[0])

    # --- completeness and identity ----------------------------------------------------------
    r.add("all master records appear exactly once (no loss, no duplicate ids)",
          len(records) == len(master_records) == 51022
          and len({rec["id"] for rec in records}) == len(records)
          and {rec["id"] for rec in records}
          == {m["facility_id"] for m in master_records})
    equal = sum(
        1 for rec, m in zip(records, master_records)
        if (rec["name"] == m["name"] and rec["state"] == m["state"]
            and rec["city_area"] == m["city_area"]
            and rec["latitude"] == m["latitude"] and rec["longitude"] == m["longitude"]))
    r.add("name, state, city_area and coordinates are value-identical to the master, in order",
          equal == len(records), equal)

    # --- traceability to the licensed source -------------------------------------------------
    rows = S.read_source()
    source_by_bare = {}
    for row in rows:
        gid = row["globalid"].strip()
        bare = (gid[5:] if gid.startswith("uuid:") else gid).lower()
        source_by_bare[bare] = row
    traced = 0
    for rec in records:
        row = source_by_bare.get(rec["id"][len("ng_g3_"):])
        if row is not None and rec["latitude"] == float(row["latitude"]) \
                and rec["longitude"] == float(row["longitude"]) \
                and rec["name"] == S.clean_text(row["facility_name"]):
            traced += 1
    r.add("every served id joins a distinct GRID3 source row with exact name and coordinates",
          traced == len(records) == len({rec["id"] for rec in records}), traced)

    # --- verified consumer contract ----------------------------------------------------------
    r.add("every record passes the verified PR #79 acceptance rules (0 would be rejected)",
          all(pr79_accepts(rec) for rec in records))
    r.add("no record carries any unconsumed key",
          all(set(rec) == {"id", "name", "state", "city_area", "latitude", "longitude"}
              for rec in records))
    # Scoped to the records: the metadata legitimately states country ONCE at
    # artifact level, which is exactly the once-not-per-record design.
    facilities_bytes = json.dumps(records, separators=(",", ":"),
                                  ensure_ascii=True).encode("utf-8")
    key_hits = {key: facilities_bytes.count(b'"%s":' % key.encode("utf-8"))
                for key in FORBIDDEN_RECORD_KEYS}
    r.add("forbidden field names do not occur anywhere in the served records",
          sum(key_hits.values()) == 0, {k: v for k, v in key_hits.items() if v})
    r.add("top-level schema_version is present for the parser and reads 2.0",
          served["schema_version"] == "2.0")

    # --- contamination -----------------------------------------------------------------------
    marker_hits = {m: served_bytes.count(m.encode("utf-8")) for m in S.NHFR_MARKER_STRINGS}
    r.add("served bytes carry zero NHFR markers",
          sum(marker_hits.values()) == 0, {k: v for k, v in marker_hits.items() if v})

    # --- attribution and governance ----------------------------------------------------------
    r.add("attribution citation, licence and modification disclosure travel with the artifact",
          meta["source"]["attribution_citation"] == ATTRIBUTION_CITATION
          and meta["source"]["licence"] == "CC BY 4.0"
          and meta["source"]["attribution_licence_url"]
          == "https://creativecommons.org/licenses/by/4.0"
          and len(meta["source"]["modifications_disclosed"]) > 0)
    r.add("served candidate is candidate_unapproved and may_publish false",
          meta["release_status"] == "candidate_unapproved"
          and meta["publication_status"] == "candidate_unapproved"
          and meta["may_publish"] is False and meta["release_date"] is None)
    manifest = load_json(repo_path("candidate", "facilities_grid3.manifest.candidate.json"))
    r.add("manifest's served block matches the bytes on disk and stays unpublishable",
          manifest["served_artifact"]["sha256"] == sha256_bytes(served_bytes)
          and manifest["served_artifact"]["bytes"] == len(served_bytes)
          and manifest["served_artifact"]["may_publish"] is False
          and manifest["candidate_artifact"]["role"] == "master_audit_candidate")

    # --- size report is generated, current and honest -----------------------------------------
    size_report = load_json(SIZE_REPORT_PATH)
    served_entry = size_report["artifacts"]["served_candidate"]
    r.add("size report matches recomputed raw, gzip and sha figures",
          served_entry["bytes"] == len(served_bytes)
          and served_entry["sha256"] == sha256_bytes(served_bytes)
          and served_entry["gzip_bytes"] == len(gzip.compress(served_bytes, GZIP_LEVEL))
          and size_report["_metadata"]["gzip_level"] == GZIP_LEVEL)
    r.add("size targets recorded truthfully",
          size_report["served_measurements"]["targets"]["raw_at_or_below_15mb"]
          == (len(served_bytes) <= 15 * 1024 * 1024)
          and size_report["served_measurements"]["targets"]["gzip_at_or_below_5mb"]
          == (len(gzip.compress(served_bytes, GZIP_LEVEL)) <= 5 * 1024 * 1024))

    # --- frozen artifacts ----------------------------------------------------------------------
    r.add("facilities 1.0 and 1.1 remain byte-identical to their pins",
          sha256_file(S.CURRENT_ARTIFACT_PATH) == S.CURRENT_ARTIFACT_SHA256
          and sha256_file(repo_path("facilities.ng.v1.0.json")) == V1_0_SHA256)

    print()
    if r.failed:
        print("%d of %d served-projection checks FAILED" % (len(r.failed), len(r.checks)))
        return 1
    print("all %d served-projection checks passed" % len(r.checks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
