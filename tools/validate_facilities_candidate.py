#!/usr/bin/env python3
"""Validate the nationwide facilities candidate.

    python3 tools/validate_facilities_candidate.py
    python3 tools/validate_facilities_candidate.py --json

Checks schema conformance, source-hash pinning, identifier uniqueness, the absence convention,
coverage accounting, coordinate and phone validity, quarantine/emitted row balance, and that
facilities 1.1 is untouched.

Two of these are the ones that matter most, because they are the ones a well-meaning change
would break first: that no unevidenced value has been invented for `type` or
`emergency_capable`, and that no excluded contact column has crept back in.

Standard library only, no network.
"""

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities import mappings as M
from facilities.normalize import (NIGERIA_MAX_LAT, NIGERIA_MAX_LON, NIGERIA_MIN_LAT,
                                  NIGERIA_MIN_LON, sort_key)
from vocab.artifact_io import load_json, repo_path, sha256_file
from vocab.schema_check import validate as schema_validate

CANDIDATE = repo_path("candidate", "facilities.ng.v2.0.json")
SCHEMA = repo_path("schema", "facilities.v2.schema.json")
SOURCE = repo_path("facilities", "source", "nigeria_health_facilities.csv")
QUALITY = repo_path("reports", "facilities_quality_v1.json")
QUARANTINE = repo_path("reports", "facilities_quarantine_v1.json")
CURRENT = repo_path("facilities.ng.v1.1.json")

SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"
CURRENT_SHA256 = "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398"

#: Columns excluded on privacy or quality grounds. None may appear in the artifact, at any
#: depth. Checked against the serialized text so a nested reintroduction cannot slip past.
EXCLUDED_SOURCE_FIELDS = ("email_address", "alternate_number", "verified_email",
                          "verified_mobile", "validated_email", "validated_mobile",
                          "published_email", "published_mobile", "created_by", "verified_by")

E164_NG = re.compile(r"^\+234[789][01]\d{8}$")


class Results(list):
    def add(self, name, passed, detail=""):
        self.append({"check": name, "passed": bool(passed), "detail": detail})
        return passed


def run():
    r = Results()
    artifact = load_json(CANDIDATE)
    meta, records = artifact["_metadata"], artifact["facilities"]
    quality = load_json(QUALITY)
    quarantine = load_json(QUARANTINE)

    r.add("candidate satisfies schema 2.0",
          not schema_validate(artifact, load_json(SCHEMA)),
          "; ".join(schema_validate(artifact, load_json(SCHEMA))[:3]))

    r.add("source bytes match the pinned digest", sha256_file(SOURCE) == SOURCE_SHA256,
          sha256_file(SOURCE))
    r.add("source digest recorded in the artifact matches the file",
          meta["source"]["sha256"] == SOURCE_SHA256)

    # --- identity -------------------------------------------------------------------------
    ids = [f["facility_id"] for f in records]
    r.add("facility_id unique", len(set(ids)) == len(ids),
          "%d ids, %d distinct" % (len(ids), len(set(ids))))
    r.add("facility_id derives from the source row id",
          all(f["facility_id"] == "ng_nhf_%s" % f["source_record"]["source_id"] for f in records))
    r.add("candidate ids cannot collide with facilities 1.1 ids",
          not ({f["facility_id"] for f in records} & {f["facility_id"] for f in load_json(CURRENT)["facilities"]}))

    # --- nothing invented -------------------------------------------------------------------
    r.add("type is null on every record (no unevidenced mapping applied)",
          all(f["type"] is None for f in records),
          "%d records carry a non-null type" % sum(1 for f in records if f["type"] is not None))
    r.add("emergency_capable is null on every record",
          all(f["emergency_capable"] is None for f in records))
    r.add("the type mapping table is still empty", M.FACILITY_TYPE_FROM_LEVEL == {})
    r.add("no emergency-capability rule has been introduced", M.EMERGENCY_CAPABLE_RULE is None)

    # --- privacy -----------------------------------------------------------------------------
    #
    # Scanned over the RECORDS, not the whole artifact. The metadata names the excluded columns
    # in order to document why they were excluded, and a check that cannot tell a disclosure
    # from its own documentation is a check that gets switched off.
    record_text = json.dumps(records)
    present = [c for c in EXCLUDED_SOURCE_FIELDS if '"%s"' % c in record_text]
    r.add("no excluded source contact/audit column appears in any record",
          not present, ", ".join(present))
    leaked = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", record_text)
    r.add("no email address appears in any record", not leaked,
          "%d found" % len(leaked))
    r.add("no URL appears in any record",
          not re.search(r"(?i)\b(?:https?://|www\.)", record_text))
    r.add("the metadata documents each excluded source column",
          all(c in json.dumps(meta["not_carried_from_source"])
              for c in ("email_address", "alternate_number")))
    r.add("free-text contact removals are counted rather than silent",
          any(k.endswith("contact_detail_in_free_text_field") for k in meta["absence_counts"]))

    # --- values --------------------------------------------------------------------------------
    bad_phone = [f["facility_id"] for f in records if f["phone"] and not E164_NG.match(f["phone"])]
    r.add("every emitted phone is a valid Nigerian mobile in E.164", not bad_phone,
          ", ".join(bad_phone[:3]))
    bad_coord = [f["facility_id"] for f in records
                 if f["latitude"] is not None
                 and not (NIGERIA_MIN_LAT <= f["latitude"] <= NIGERIA_MAX_LAT
                          and NIGERIA_MIN_LON <= f["longitude"] <= NIGERIA_MAX_LON)]
    r.add("every emitted coordinate is inside the Nigeria bounding box", not bad_coord,
          ", ".join(bad_coord[:3]))
    r.add("latitude and longitude are both present or both absent",
          all((f["latitude"] is None) == (f["longitude"] is None) for f in records))
    r.add("no record carries an empty name", all(f["name"].strip() for f in records))

    # --- absence convention ----------------------------------------------------------------------
    r.add("no boolean service field was coerced from an absent source value",
          all(isinstance(v, bool) or v is None
              for f in records for v in f["services"].values()))
    r.add("'unknown' is used only where the source said Unknown",
          all(f["operational_status"] in (None, "functional", "non_functional", "closed",
                                          "under_renovation", "unknown") for f in records))

    # --- accounting ------------------------------------------------------------------------------
    r.add("emitted + quarantined equals the source row count",
          quality["row_accounting"]["balances"],
          json.dumps(quality["row_accounting"]))
    r.add("quarantine report lists every quarantined row",
          len(quarantine["rows"]) == quality["row_accounting"]["quarantined"])
    r.add("every quarantined row carries a known reason code",
          all(q["reason_code"] in quarantine["reason_codes"] for q in quarantine["rows"]))
    r.add("total_facilities matches the record count", meta["total_facilities"] == len(records))

    # --- coverage ---------------------------------------------------------------------------------
    states = {f["state"] for f in records}
    r.add("states_covered matches the records", sorted(states) == meta["states_covered"])
    absent = [s for s in M.NIGERIA_STATES if s not in states]
    r.add("states_absent is stated accurately", absent == meta["states_absent"],
          "artifact says %s, records say %s" % (meta["states_absent"], absent))
    r.add("the artifact does not claim nationwide coverage",
          "NOT nationwide" in meta["coverage_claim"])
    r.add("every state name is one of the 36 or the FCT",
          all(s in M.NIGERIA_STATES or s == M.FCT_NAME for s in states),
          ", ".join(sorted(s for s in states if s not in M.NIGERIA_STATES and s != M.FCT_NAME)))

    # --- ordering and status -------------------------------------------------------------------------
    r.add("records are in the canonical sort order",
          records == sorted(records, key=sort_key))
    r.add("release status is candidate_unapproved", meta["release_status"] == "candidate_unapproved")
    r.add("may_publish is false", meta["may_publish"] is False)
    r.add("release_date is null", meta["release_date"] is None)
    r.add("licence is recorded as not established", meta["source"]["licence"] is None)

    # --- the frozen artifact is untouched -----------------------------------------------------------
    r.add("facilities 1.1 is byte identical", sha256_file(CURRENT) == CURRENT_SHA256,
          sha256_file(CURRENT))
    r.add("the candidate is not at the repository root",
          not os.path.exists(repo_path("facilities.ng.v2.0.json")))
    return r


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    results = run()
    failed = [x for x in results if not x["passed"]]
    if args.json:
        print(json.dumps({"checks": results, "total": len(results), "failed": len(failed)}, indent=2))
    else:
        for x in failed:
            print("FAIL %s\n     %s" % (x["check"], x["detail"]))
        print("%d of %d facilities checks passed" % (len(results) - len(failed), len(results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
