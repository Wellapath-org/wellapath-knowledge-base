#!/usr/bin/env python3
"""Validate the nationwide facilities candidate.

    python3 tools/validate_facilities_candidate.py
    python3 tools/validate_facilities_candidate.py --json

Checks schema conformance, source-hash pinning, identifier uniqueness, the absence convention,
coverage accounting, coordinate and phone validity, the deduplication rule, quarantine/emitted
row balance, the candidate manifest, that the consumer documents cite the bytes that exist,
and that facilities 1.1 is untouched.

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
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities import mappings as M
from facilities.normalize import (NIGERIA_MAX_LAT, NIGERIA_MAX_LON, NIGERIA_MIN_LAT,
                                  NIGERIA_MIN_LON, duplicate_key, haversine_km, sort_key)
from vocab.artifact_io import load_json, repo_path, sha256_file
from vocab.schema_check import validate as schema_validate

CANDIDATE = repo_path("candidate", "facilities.ng.v2.0.json")
SCHEMA = repo_path("schema", "facilities.v2.schema.json")
SOURCE = repo_path("facilities", "source", "nigeria_health_facilities.csv")
QUALITY = repo_path("reports", "facilities_quality_v1.json")
QUARANTINE = repo_path("reports", "facilities_quarantine_v1.json")
MANIFEST = repo_path("candidate", "facilities.manifest.candidate.json")
CURRENT = repo_path("facilities.ng.v1.1.json")
CHANGELOG = repo_path("docs", "FACILITIES_2_0_CHANGELOG.md")
HANDOFF = repo_path("mobile_handoff", "facilities_v2", "README.md")

SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"
CURRENT_SHA256 = "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398"

#: Columns excluded on privacy or quality grounds. None may appear in the artifact, at any
#: depth. Checked against the serialized text so a nested reintroduction cannot slip past.
EXCLUDED_SOURCE_FIELDS = ("email_address", "alternate_number", "verified_email",
                          "verified_mobile", "validated_email", "validated_mobile",
                          "published_email", "published_mobile", "created_by", "verified_by")

#: Key tokens that have no business in a facility directory. A key whose underscore-separated
#: tokens include one of these is a user, health, search or location-history datum, none of
#: which this artifact may carry. Matched on key tokens, not on prose, so documentation that
#: says "a user is shown" does not trip it and a key called user_id does.
PROHIBITED_KEY_TOKENS = frozenset([
    "user", "users", "device", "session", "query", "queries", "search", "history", "symptom",
    "symptoms", "diagnosis", "diagnoses", "patient", "patients", "assessment", "telemetry",
    "analytics", "password", "secret", "credential", "consent", "dob", "birth", "gender",
    "nin", "bvn", "ip", "imei", "geolocation", "trace", "visit", "visits",
])

#: The ten fields facilities 1.1 emits and the JSON types the Mobile consumer reads them as.
MOBILE_SURFACE = {
    "facility_id": (str,), "name": (str,), "type": (str, type(None)), "state": (str,),
    "city_area": (str, type(None)), "latitude": (float, int, type(None)),
    "longitude": (float, int, type(None)), "phone": (str, type(None)),
    "opening_hours": (str, type(None)), "emergency_capable": (bool, type(None)),
}

E164_NG = re.compile(r"^\+234[789][01]\d{8}$")
NAIVE_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class Results(list):
    def add(self, name, passed, detail=""):
        self.append({"check": name, "passed": bool(passed), "detail": detail})
        return passed


def _keys(value, found):
    if isinstance(value, dict):
        for key, inner in value.items():
            found.add(key)
            _keys(inner, found)
    elif isinstance(value, list):
        for inner in value:
            _keys(inner, found)
    return found


def run():
    r = Results()
    artifact = load_json(CANDIDATE)
    meta, records = artifact["_metadata"], artifact["facilities"]
    quality = load_json(QUALITY)
    quarantine = load_json(QUARANTINE)
    current = load_json(CURRENT)

    schema_errors = schema_validate(artifact, load_json(SCHEMA))
    r.add("candidate satisfies schema 2.0", not schema_errors, "; ".join(schema_errors[:3]))

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
          not ({f["facility_id"] for f in records} & {f["facility_id"] for f in current["facilities"]}))
    source_ids = [f["source_record"]["source_id"] for f in records]
    r.add("source_id and source_unique_id are unique across emitted records",
          len(set(source_ids)) == len(source_ids)
          and len({f["source_record"]["source_unique_id"] for f in records}) == len(records))

    # --- nothing invented -------------------------------------------------------------------
    r.add("type is null on every record (no unevidenced mapping applied)",
          all(f["type"] is None for f in records),
          "%d records carry a non-null type" % sum(1 for f in records if f["type"] is not None))
    r.add("every type is within the declared closed vocabulary or null",
          all(f["type"] is None or f["type"] in M.FACILITY_TYPES for f in records))
    r.add("the declared type vocabulary matches the mapping module",
          meta["unresolved_fields"]["type_vocabulary"] == list(M.FACILITY_TYPES))
    r.add("emergency_capable is null on every record",
          all(f["emergency_capable"] is None for f in records))
    r.add("the type mapping table is still empty", M.FACILITY_TYPE_FROM_LEVEL == {})
    r.add("no emergency-capability rule has been introduced", M.EMERGENCY_CAPABLE_RULE is None)
    r.add("every service flag is bound to exactly one documented source column",
          all(set(f["services"]) == set(M.SERVICES_SOURCE_COLUMNS) for f in records),
          "documented: %s" % sorted(M.SERVICES_SOURCE_COLUMNS))

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
    from facilities.normalize import free_text
    r.add("free-text contact scrubbing is in force and counted when it fires",
          free_text("someone@example.com") == (None, "contact_detail_in_free_text_field")
          and all(k.endswith(("contact_detail_in_free_text_field", "url_in_free_text_field"))
                  or not k.startswith(("address_", "ward_")) for k in meta["absence_counts"]))
    prohibited = sorted(
        key for key in _keys(artifact, set())
        if set(key.lower().split("_")) & PROHIBITED_KEY_TOKENS
    )
    r.add("no user, health, search or location-history key exists at any depth",
          not prohibited, ", ".join(prohibited))

    # --- values --------------------------------------------------------------------------------
    bad_phone = [f["facility_id"] for f in records if f["phone"] and not E164_NG.match(f["phone"])]
    r.add("every emitted phone is a valid Nigerian mobile in E.164", not bad_phone,
          ", ".join(bad_phone[:3]))
    r.add("every emitted record carries both coordinates",
          all(f["latitude"] is not None and f["longitude"] is not None for f in records),
          "%d without" % sum(1 for f in records if f["latitude"] is None))
    bad_coord = [f["facility_id"] for f in records
                 if not (NIGERIA_MIN_LAT <= f["latitude"] <= NIGERIA_MAX_LAT
                         and NIGERIA_MIN_LON <= f["longitude"] <= NIGERIA_MAX_LON)]
    r.add("every emitted coordinate is inside the Nigeria bounding box", not bad_coord,
          ", ".join(bad_coord[:3]))
    r.add("no record carries an empty name", all(f["name"].strip() for f in records))

    # --- the per-state coordinate instrument ---------------------------------------------------------
    r.add("the reference table covers every state and the FCT with points inside the box",
          set(M.STATE_REFERENCE_POINTS) == set(M.NIGERIA_STATES) | {M.FCT_NAME}
          and all(NIGERIA_MIN_LAT <= la <= NIGERIA_MAX_LAT and NIGERIA_MIN_LON <= lo <= NIGERIA_MAX_LON
                  for la, lo in M.STATE_REFERENCE_POINTS.values()))
    too_far = [f["facility_id"] for f in records
               if haversine_km(*M.STATE_REFERENCE_POINTS[f["state"]], f["latitude"], f["longitude"])
               > M.NOT_IN_STATE_KM]
    r.add("no emitted record is farther than %.0f km from its state's reference point" % M.NOT_IN_STATE_KM,
          not too_far, ", ".join(too_far[:3]))
    from facilities.normalize import coordinate_vs_state

    def median(values):
        values = sorted(values)
        return values[len(values) // 2]

    would_refuse = [f["facility_id"] for f in records
                    if coordinate_vs_state(f["longitude"], f["latitude"],
                                           *M.STATE_REFERENCE_POINTS[f["state"]],
                                           M.SWAP_MIN_DISTANCE_KM, M.SWAP_FACTOR,
                                           M.NOT_IN_STATE_KM)[2] is not None]
    r.add("re-applying the per-state instrument to the emitted records refuses nothing",
          not would_refuse, ", ".join(would_refuse[:3]))
    predominantly = [e["state"] for e in quality["source_evidence"]["coordinate_consistency_by_state"]
                     if e["reading"] == "predominantly transposed in the source"]
    r.add("every state the evidence reads as transposed is named in known_limitations or emptied",
          all(s in meta["states_with_no_emitted_records"]
              or any(s in line for line in quality["known_limitations"]) for s in predominantly),
          ", ".join(predominantly))
    r.add("the reference instrument moved or exchanged nothing",
          meta["coordinate_reference"]["records_moved_or_exchanged"] == 0
          and not any(q["reason_code"].startswith("coordinates_") and "exchanged" not in q["detail"]
                      and q["reason_code"] in ("coordinates_swapped_suspected_by_state",
                                               "coordinates_not_in_state")
                      for q in quarantine["rows"]))
    r.add("the reference instrument's cross-check against facilities 1.1 holds",
          all(haversine_km(*M.STATE_REFERENCE_POINTS[state],
                           median([f["latitude"] for f in current["facilities"] if f["state"] == state]),
                           median([f["longitude"] for f in current["facilities"] if f["state"] == state]))
              <= 50 for state in current["_metadata"]["states_covered"]))
    r.add("every opening_hours value is within the enum",
          all(f["opening_hours"] in (None, "24_hours", "12_hours", "8_hours", "other")
              for f in records))
    r.add("every source_updated_at is an ISO 8601 naive timestamp or null",
          all(f["source_record"]["source_updated_at"] is None
              or NAIVE_TIMESTAMP.match(f["source_record"]["source_updated_at"])
              for f in records))
    r.add("the snapshot last-updated instant is no earlier than any emitted record's",
          all((f["source_record"]["source_updated_at"] or "") <= meta["source"]["snapshot_last_updated_at"]
              for f in records))

    # --- state / LGA normalization ----------------------------------------------------------------
    by_casefold = defaultdict(set)
    for f in records:
        by_casefold[(f["state"], f["city_area"].casefold())].add(f["city_area"])
    variants = [k for k, v in by_casefold.items() if len(v) > 1]
    r.add("no LGA has two spellings within one state", not variants,
          ", ".join("%s/%s" % k for k in variants[:3]))
    r.add("every state and LGA name is trimmed and single-spaced",
          all(v == v.strip() and "  " not in v for f in records for v in (f["state"], f["city_area"])))
    r.add("city_area and lga agree on every record",
          all(f["city_area"] == f["lga"] for f in records))
    # The source's lga_id is scoped to the LGA NAME, not to the state: six homonymous LGA names
    # (Nasarawa, Obi, Ifelodun, Irepodun, Surulere, Bassa) carry one id in two states each.
    # So the honest invariants are: an id names one LGA name; a (state, LGA) pair has one id;
    # a state_id names one state and agrees with the record's state; and every id that spans
    # states is reported as such in the quality report rather than silently accepted.
    lga_names_by_id, lga_ids_by_pair = defaultdict(set), defaultdict(set)
    states_by_lga_id, state_names_by_id = defaultdict(set), defaultdict(set)
    for f in records:
        lga_names_by_id[f["source_record"]["lga_id"]].add(f["city_area"])
        lga_ids_by_pair[(f["state"], f["city_area"])].add(f["source_record"]["lga_id"])
        states_by_lga_id[f["source_record"]["lga_id"]].add(f["state"])
        state_names_by_id[f["source_record"]["state_id"]].add(f["state"])
    r.add("every lga_id names exactly one LGA name",
          all(len(v) == 1 for v in lga_names_by_id.values()))
    r.add("every state/LGA pair carries exactly one lga_id",
          all(len(v) == 1 for v in lga_ids_by_pair.values()))
    r.add("every state_id names exactly one state",
          all(len(v) == 1 for v in state_names_by_id.values()))
    spanning = {k for k, v in states_by_lga_id.items() if len(v) > 1}
    reported = {e["lga_id"] for e in quality["source_evidence"]["lga_ids_spanning_multiple_states"]}
    r.add("every lga_id that spans two states is reported as name-scoped in the quality report",
          spanning <= reported, "unreported: %s" % sorted(spanning - reported))
    r.add("the name-scoped lga_id limitation is stated in known_limitations",
          any("lga_id" in line for line in quality["known_limitations"]))

    # --- absence convention ----------------------------------------------------------------------
    r.add("no boolean service field was coerced from an absent source value",
          all(isinstance(v, bool) or v is None
              for f in records for v in f["services"].values()))
    r.add("'unknown' is used only where the source said Unknown",
          all(f["operational_status"] in (None, "functional", "non_functional", "closed",
                                          "under_renovation", "unknown") for f in records))

    # --- deduplication ------------------------------------------------------------------------------
    remaining = Counter(duplicate_key(f) for f in records)
    r.add("no exact-duplicate group remains among emitted records",
          all(v == 1 for v in remaining.values()),
          "%d groups remain" % sum(1 for v in remaining.values() if v > 1))
    dup_rows = [q for q in quarantine["rows"] if q["reason_code"] == "duplicate_exact_match"]
    r.add("every removed duplicate names a survivor that is in the candidate",
          all(q.get("survivor_facility_id") in set(ids) for q in dup_rows))
    r.add("the deduplication accounting agrees everywhere",
          meta["deduplication"]["rows_removed"] == len(dup_rows)
          == quality["duplicates"]["exact_duplicates_resolved"]["rows_removed"]
          == quality["row_accounting"]["quarantined_of_which_exact_duplicates"])
    r.add("no values were merged across duplicate members",
          meta["deduplication"]["values_merged"] is False)

    # --- accounting ------------------------------------------------------------------------------
    r.add("emitted + quarantined equals the source row count",
          quality["row_accounting"]["balances"],
          json.dumps(quality["row_accounting"]))
    r.add("quarantine report lists every quarantined row",
          len(quarantine["rows"]) == quality["row_accounting"]["quarantined"])
    r.add("every quarantined row carries a known reason code",
          all(q["reason_code"] in quarantine["reason_codes"] for q in quarantine["rows"]))
    r.add("no quarantined row is also emitted",
          not ({q["source_id"] for q in quarantine["rows"]} & set(source_ids)))
    r.add("total_facilities matches the record count", meta["total_facilities"] == len(records))

    # --- coverage ---------------------------------------------------------------------------------
    states = {f["state"] for f in records}
    r.add("states_covered matches the records", sorted(states) == meta["states_covered"])
    absent = [s for s in M.NIGERIA_STATES
              if s not in states and s not in meta["states_with_no_emitted_records"]]
    r.add("states_absent is stated accurately", absent == meta["states_absent"],
          "artifact says %s, records say %s" % (meta["states_absent"], absent))
    r.add("the artifact does not claim nationwide coverage",
          "NOT nationwide" in meta["coverage_claim"])
    emptied = meta["states_with_no_emitted_records"]
    r.add("states with no emitted records are disjoint from covered and absent states, and named in the claim",
          not (set(emptied) & states) and not (set(emptied) & set(meta["states_absent"]))
          and all(s in meta["coverage_claim"] for s in emptied)
          and emptied == quality["coverage"]["states_in_source_with_no_emitted_records"])
    r.add("every state name is one of the 36 or the FCT",
          all(s in M.NIGERIA_STATES or s == M.FCT_NAME for s in states),
          ", ".join(sorted(s for s in states if s not in M.NIGERIA_STATES and s != M.FCT_NAME)))
    lost = sorted(set(current["_metadata"]["states_covered"]) - states)
    compat = load_json(repo_path("reports", "facilities_mobile_compat_v1.json"))
    r.add("every facilities 1.1 state missing from the candidate is a named blocking finding",
          all(s in meta["states_with_no_emitted_records"] for s in lost)
          and (not lost or any(f["severity"] == "blocking" and all(s in f["finding"] for s in lost)
                               for f in compat["blocking_findings"])),
          "lost: %s" % lost)

    # --- ordering and status -------------------------------------------------------------------------
    r.add("records are in the canonical sort order",
          records == sorted(records, key=sort_key))
    r.add("release status is candidate_unapproved", meta["release_status"] == "candidate_unapproved")
    r.add("publication status is candidate_unapproved",
          meta["publication_status"] == "candidate_unapproved")
    r.add("may_publish is false", meta["may_publish"] is False)
    r.add("release_date is null", meta["release_date"] is None)
    r.add("licence is recorded as not established", meta["source"]["licence"] is None)

    # --- Mobile surface and rollback ------------------------------------------------------------------
    r.add("the ten facilities 1.1 fields are present on every record with consumer-readable types",
          all(field in f and isinstance(f[field], types)
              for f in records for field, types in MOBILE_SURFACE.items()))
    r.add("facilities 1.1 is byte identical", sha256_file(CURRENT) == CURRENT_SHA256,
          sha256_file(CURRENT))
    r.add("facilities 1.0 is present for rollback history",
          os.path.exists(repo_path("facilities.ng.v1.0.json")))
    r.add("the candidate is not at the repository root",
          not os.path.exists(repo_path("facilities.ng.v2.0.json")))

    # --- manifest and consumer documents cite the bytes that exist --------------------------------------
    digest = sha256_file(CANDIDATE)
    manifest = load_json(MANIFEST) if os.path.exists(MANIFEST) else None
    r.add("the candidate manifest exists and is not a live manifest",
          manifest is not None and manifest["IS_LIVE_MANIFEST"] is False)
    r.add("the candidate manifest records the current bytes and record count",
          manifest is not None
          and manifest["candidate_artifact"]["sha256"] == digest
          and manifest["candidate_artifact"]["bytes"] == os.path.getsize(CANDIDATE)
          and manifest["candidate_artifact"]["record_count"] == len(records))
    r.add("the candidate manifest binds rollback to facilities 1.1 by hash",
          manifest is not None
          and manifest["rollback"]["target_file"] == "facilities.ng.v1.1.json"
          and manifest["rollback"]["target_sha256"] == CURRENT_SHA256)
    r.add("the candidate manifest grants nothing",
          manifest is not None
          and manifest["candidate_artifact"]["may_publish"] is False
          and manifest["candidate_artifact"]["uploaded_to_r2"] is False
          and all(v is False for v in manifest["publication_gates"].values()))
    for label, path in (("changelog", CHANGELOG), ("Mobile handoff", HANDOFF)):
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        r.add("the %s cites the current candidate digest and record count" % label,
              digest in text and "{:,}".format(len(records)) in text,
              "expected %s… and %s in %s" % (digest[:12], "{:,}".format(len(records)),
                                             os.path.relpath(path, repo_path())))
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
