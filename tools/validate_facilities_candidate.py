#!/usr/bin/env python3
"""Validate the nationwide facilities candidate.

    python3 tools/validate_facilities_candidate.py
    python3 tools/validate_facilities_candidate.py --json

Checks schema conformance, source and reference-geometry pinning, identifier uniqueness, the
absence convention, coverage accounting, the coordinate-orientation rule (every emitted record
re-verified inside its state; every correction re-derived from its source values), the
deduplication rule, quarantine/emitted row balance, the candidate manifest, the source
authorization checklist, that the consumer documents cite the bytes that exist, that the
publication tooling still blocks activation, and that facilities 1.0 and 1.1 are untouched.

The checks that matter most are the ones a well-meaning change would break first: that no
unevidenced value has been invented for `type` or `emergency_capable`, that no coordinate was
exchanged without the strict rule, and that no excluded contact column has crept back in.

Standard library only, no network.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities import geometry as G
from facilities import mappings as M
from facilities.normalize import (NIGERIA_MAX_LAT, NIGERIA_MAX_LON, NIGERIA_MIN_LAT,
                                  NIGERIA_MIN_LON, duplicate_key, free_text, haversine_km,
                                  sort_key)
from vocab.artifact_io import load_json, repo_path, sha256_file
from vocab.schema_check import validate as schema_validate

CANDIDATE = repo_path("candidate", "facilities.ng.v2.0.json")
SCHEMA = repo_path("schema", "facilities.v2.schema.json")
SOURCE = repo_path("facilities", "source", "nigeria_health_facilities.csv")
QUALITY = repo_path("reports", "facilities_quality_v1.json")
QUARANTINE = repo_path("reports", "facilities_quarantine_v1.json")
AUDIT = repo_path("reports", "facilities_coordinate_audit_v1.json")
COMPAT = repo_path("reports", "facilities_mobile_compat_v1.json")
MANIFEST = repo_path("candidate", "facilities.manifest.candidate.json")
CHECKLIST = repo_path("facilities", "source", "nhf_authorization_checklist_v1.json")
PLAN = repo_path("publication", "plans", "facilities.ng.v2.0.dryrun.json")
CURRENT = repo_path("facilities.ng.v1.1.json")
CHANGELOG = repo_path("docs", "FACILITIES_2_0_CHANGELOG.md")
HANDOFF = repo_path("mobile_handoff", "facilities_v2", "README.md")

SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"
CURRENT_SHA256 = "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398"
V1_0_SHA256 = "1c7b939199ab4465156f4cb336910eea120fcaa70f8b1c0743fc9f7a7c03009e"

#: Columns excluded on privacy or quality grounds. None may appear in the artifact, at any
#: depth. Checked against the serialized text so a nested reintroduction cannot slip past.
EXCLUDED_SOURCE_FIELDS = ("email_address", "alternate_number", "verified_email",
                          "verified_mobile", "validated_email", "validated_mobile",
                          "published_email", "published_mobile", "created_by", "verified_by")

#: Key tokens that have no business in a facility directory. Matched on key tokens, not on
#: prose, so documentation that says "a user is shown" does not trip it and user_id does.
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

#: Phrases the Mobile handoff must state, verbatim, about null types and emergency ordering.
HANDOFF_CONTRACT_PHRASES = (
    "must not be filtered out",
    "never create an empty result list",
    "verified positive evidence",
    "Product/Clinical fallback decision",
)

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


def _median(values):
    values = sorted(values)
    return values[len(values) // 2]


def run():
    r = Results()
    artifact = load_json(CANDIDATE)
    meta, records = artifact["_metadata"], artifact["facilities"]
    quality = load_json(QUALITY)
    quarantine = load_json(QUARANTINE)
    audit = load_json(AUDIT)
    current = load_json(CURRENT)
    compat = load_json(COMPAT)
    checklist = load_json(CHECKLIST)
    geometry = G.StateGeometry.load()

    schema_errors = schema_validate(artifact, load_json(SCHEMA))
    r.add("candidate satisfies schema 2.0", not schema_errors, "; ".join(schema_errors[:3]))

    r.add("source bytes match the pinned digest", sha256_file(SOURCE) == SOURCE_SHA256,
          sha256_file(SOURCE))
    r.add("source digest recorded in the artifact matches the file",
          meta["source"]["sha256"] == SOURCE_SHA256)
    r.add("reference geometry (GRID3) matches its pinned digest and the artifact records it",
          sha256_file(G.GRID3_PATH) == G.GRID3_SHA256
          and meta["coordinate_remediation"]["reference_geometry"]["sha256"] == G.GRID3_SHA256)

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
    r.add("a null type is not a member of the declared vocabulary",
          None not in M.FACILITY_TYPES and "null" not in M.FACILITY_TYPES
          and all(f["type"] is None or f["type"] in M.FACILITY_TYPES for f in records))
    r.add("the declared type vocabulary matches the mapping module",
          meta["unresolved_fields"]["type_vocabulary"] == list(M.FACILITY_TYPES))
    r.add("emergency_capable is null on every record and no record is verified positive",
          all(f["emergency_capable"] is None for f in records)
          and not any(f["emergency_capable"] is True for f in records))
    r.add("the type mapping table is still empty", M.FACILITY_TYPE_FROM_LEVEL == {})
    r.add("no emergency-capability rule has been introduced", M.EMERGENCY_CAPABLE_RULE is None)
    r.add("every service flag is bound to exactly one documented source column",
          all(set(f["services"]) == set(M.SERVICES_SOURCE_COLUMNS) for f in records),
          "documented: %s" % sorted(M.SERVICES_SOURCE_COLUMNS))

    # --- privacy -----------------------------------------------------------------------------
    record_text = json.dumps(records)
    present = [c for c in EXCLUDED_SOURCE_FIELDS if '"%s"' % c in record_text]
    r.add("no excluded source contact/audit column appears in any record",
          not present, ", ".join(present))
    leaked = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", record_text)
    r.add("no email address appears in any record", not leaked, "%d found" % len(leaked))
    r.add("no URL appears in any record",
          not re.search(r"(?i)\b(?:https?://|www\.)", record_text))
    r.add("the metadata documents each excluded source column",
          all(c in json.dumps(meta["not_carried_from_source"])
              for c in ("email_address", "alternate_number")))
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

    # --- the coordinate-orientation rule, re-derived --------------------------------------------
    outside = []
    for f in records:
        given = geometry.membership(f["latitude"], f["longitude"], f["state"])
        if given == G.INSIDE_STRICT:
            continue
        exchanged = geometry.membership(f["longitude"], f["latitude"], f["state"])
        if given == G.INSIDE_MAJORITY and exchanged in (G.OUTSIDE, G.OUT_OF_BOX):
            continue
        outside.append("%s:%s/%s" % (f["facility_id"], given, exchanged))
    r.add("no accepted record lies outside its declared state under the geometry instrument",
          not outside, ", ".join(outside[:3]))

    corrected = [f for f in records if f["source_record"]["coordinate_transformation"] != "none"]
    strict_fail = []
    for f in corrected:
        s = f["source_record"]
        if s["coordinate_transformation"] != "swap_lat_lon":
            strict_fail.append(f["facility_id"] + ":unknown_transformation")
            continue
        if not (f["latitude"] == s["source_longitude"] and f["longitude"] == s["source_latitude"]):
            strict_fail.append(f["facility_id"] + ":values_not_exchanged")
            continue
        as_given = geometry.membership(s["source_latitude"], s["source_longitude"], f["state"])
        applied = geometry.membership(f["latitude"], f["longitude"], f["state"])
        if as_given not in (G.OUTSIDE, G.OUT_OF_BOX) or applied != G.INSIDE_STRICT:
            strict_fail.append("%s:%s->%s" % (f["facility_id"], as_given, applied))
    r.add("every coordinate correction satisfies the strict rule when re-derived from its source values",
          not strict_fail, ", ".join(strict_fail[:3]))
    r.add("every uncorrected record carries no source_latitude/source_longitude, every corrected one does",
          all((f["source_record"]["source_latitude"] is None) == (f["source_record"]["coordinate_transformation"] == "none")
              and (f["source_record"]["source_longitude"] is None) == (f["source_record"]["coordinate_transformation"] == "none")
              for f in records))
    audited = {c["source_id"]: c for c in audit["corrections"]}
    r.add("every correction in the artifact is listed in the audit with the same values",
          all(f["source_record"]["source_id"] in audited
              and audited[f["source_record"]["source_id"]]["latitude"] == f["latitude"]
              and audited[f["source_record"]["source_id"]]["source_latitude"] == f["source_record"]["source_latitude"]
              for f in corrected))
    r.add("transformations are fully counted and agree across artifact, audit and quality report",
          len(corrected) == meta["coordinate_remediation"]["records_corrected_in_artifact"]
          == audit["records_corrected_in_artifact"]
          and len(audit["corrections"]) == audit["outcomes"][G.ACCEPTED_AFTER_SWAP]
          == meta["coordinate_remediation"]["accepted_after_verified_swap"]
          == quality["coordinate_remediation"]["accepted_after_verified_swap"])
    ambiguous_rows = [q for q in quarantine["rows"] if q["reason_code"] == "coordinates_orientation_ambiguous"]
    r.add("every ambiguous orientation remains quarantined, none is emitted",
          len(ambiguous_rows) == meta["coordinate_remediation"]["quarantined_ambiguous"]
          == audit["outcomes"][G.QUARANTINED_AMBIGUOUS]
          and not ({q["source_id"] for q in ambiguous_rows} & set(source_ids)))
    invalid_rows = [q for q in quarantine["rows"] if q["reason_code"] == "coordinates_not_in_state"]
    r.add("every invalid orientation remains quarantined, none is emitted",
          len(invalid_rows) == meta["coordinate_remediation"]["quarantined_invalid"]
          and not ({q["source_id"] for q in invalid_rows} & set(source_ids)))
    r.add("the four orientation outcomes account for every orientable row",
          sum(audit["outcomes"][k] for k in (G.ACCEPTED_UNCHANGED, G.ACCEPTED_AFTER_SWAP,
                                             G.QUARANTINED_AMBIGUOUS, G.QUARANTINED_INVALID))
          + audit["outcomes"]["not_orientable_missing_or_zero"]
          + sum(quality["quarantine_reason_counts"].get(k, 0) for k in
                ("name_empty", "name_is_contact_detail", "state_absent", "state_unmapped", "lga_absent"))
          == quality["row_accounting"]["source_rows"])
    r.add("the geometry instrument moved or snapped nothing: every emitted pair is a source pair or its exchange",
          all(f["source_record"]["coordinate_transformation"] in ("none", "swap_lat_lon") for f in records))
    r.add("the instrument's calibration on GRID3 itself is recorded and sane",
          audit["calibration_on_grid3_itself"]["membership"].get(G.INSIDE_STRICT, 0)
          > 0.9 * audit["calibration_on_grid3_itself"]["points"]
          and audit["calibration_on_grid3_itself"]["membership"].get(G.OUTSIDE, 0)
          < 0.01 * audit["calibration_on_grid3_itself"]["points"])
    too_far = [f["facility_id"] for f in records
               if haversine_km(*M.STATE_REFERENCE_POINTS[f["state"]], f["latitude"], f["longitude"])
               > M.NOT_IN_STATE_KM]
    r.add("independent sanity: no emitted record is farther than %.0f km from its state's reference point" % M.NOT_IN_STATE_KM,
          not too_far, ", ".join(too_far[:3]))

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
          all(isinstance(v, bool) or v is None for f in records for v in f["services"].values()))
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
          quality["row_accounting"]["balances"], json.dumps(quality["row_accounting"]))
    r.add("quarantine report lists every quarantined row",
          len(quarantine["rows"]) == quality["row_accounting"]["quarantined"])
    r.add("every quarantined row carries a known reason code",
          all(q["reason_code"] in quarantine["reason_codes"] for q in quarantine["rows"]))
    r.add("no quarantined row is also emitted",
          not ({q["source_id"] for q in quarantine["rows"]} & set(source_ids)))
    r.add("total_facilities matches the record count", meta["total_facilities"] == len(records))
    r.add("the per-state coverage table reconciles to the row accounting",
          sum(e["source_rows"] for e in audit["coverage_by_state"])
          + sum(quality["quarantine_reason_counts"].get(k, 0) for k in
                ("name_empty", "name_is_contact_detail", "state_absent", "state_unmapped", "lga_absent"))
          == quality["row_accounting"]["source_rows"]
          and sum(e["candidate"] for e in audit["coverage_by_state"]) == len(records)
          and all(e["source_rows"] == e["accepted_unchanged"] + e["accepted_after_verified_swap"]
                  + e["quarantined_ambiguous"] + e["quarantined_invalid"]
                  + e["quarantined_missing_coordinates"] for e in audit["coverage_by_state"])
          and all(e["candidate"] == e["accepted_unchanged"] + e["accepted_after_verified_swap"]
                  - e["quarantined_duplicate"] for e in audit["coverage_by_state"]))

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
    r.add("states with no emitted records are disjoint from covered and absent states, named, and agreed with the quality report",
          not (set(emptied) & states) and not (set(emptied) & set(meta["states_absent"]))
          and all(s in meta["coverage_claim"] for s in emptied)
          and emptied == quality["coverage"]["states_in_source_with_no_emitted_records"])
    r.add("every state name is one of the 36 or the FCT",
          all(s in M.NIGERIA_STATES or s == M.FCT_NAME for s in states),
          ", ".join(sorted(s for s in states if s not in M.NIGERIA_STATES and s != M.FCT_NAME)))
    lost = sorted(set(current["_metadata"]["states_covered"]) - states)
    r.add("no facilities 1.1 state is absent from the candidate — or, if one is, it is a named blocking finding",
          all(s in meta["states_with_no_emitted_records"] for s in lost)
          and (not lost or any(f["severity"] == "blocking" and all(s in f["finding"] for s in lost)
                               for f in compat["blocking_findings"])),
          "lost: %s" % lost)
    r.add("the comparison report agrees that no facilities 1.1 state is lost",
          load_json(repo_path("reports", "facilities_comparison_v1.json"))["states_lost"] == lost)

    # --- ordering and status -------------------------------------------------------------------------
    r.add("records are in the canonical sort order", records == sorted(records, key=sort_key))
    r.add("release status is candidate_unapproved", meta["release_status"] == "candidate_unapproved")
    r.add("publication status is candidate_unapproved",
          meta["publication_status"] == "candidate_unapproved")
    r.add("may_publish is false", meta["may_publish"] is False)
    r.add("release_date is null", meta["release_date"] is None)
    r.add("licence is recorded as not established", meta["source"]["licence"] is None)

    # --- source authorization ---------------------------------------------------------------------------
    statuses = {item["id"]: item["status"] for item in checklist["items"]}
    r.add("every authorization checklist item carries a known status",
          all(s in checklist["_metadata"]["status_vocabulary"] for s in statuses.values()))
    r.add("all_satisfied in the checklist is derived, not asserted",
          checklist["all_satisfied"] == all(s == "satisfied" for s in statuses.values()))
    r.add("a satisfied checklist item cites evidence and a recorder",
          all(item["evidence"] and item["recorded_by"] and item["recorded_on"]
              for item in checklist["items"] if item["status"] == "satisfied"))
    r.add("may_publish stays false while any authorization item is unsatisfied",
          checklist["all_satisfied"] or meta["may_publish"] is False)
    r.add("the checklist binds to the pinned source",
          checklist["_metadata"]["applies_to"]["source_sha256"] == SOURCE_SHA256)

    # --- Mobile surface, contract and rollback ------------------------------------------------------------
    r.add("the ten facilities 1.1 fields are present on every record with consumer-readable types",
          all(field in f and isinstance(f[field], types)
              for f in records for field, types in MOBILE_SURFACE.items()))
    handoff_text = open(HANDOFF, encoding="utf-8").read() if os.path.exists(HANDOFF) else ""
    r.add("the Mobile handoff states the null-type and emergency-ordering contract",
          all(p in handoff_text for p in HANDOFF_CONTRACT_PHRASES),
          "missing: %s" % [p for p in HANDOFF_CONTRACT_PHRASES if p not in handoff_text])
    r.add("the artifact metadata states the same consumer contract",
          "must not be filtered out" in meta["unresolved_fields"]["consumer_contract"]
          and "empty result list" in meta["unresolved_fields"]["consumer_contract"])
    r.add("facilities 1.1 is byte identical", sha256_file(CURRENT) == CURRENT_SHA256, sha256_file(CURRENT))
    r.add("facilities 1.0 is byte identical",
          sha256_file(repo_path("facilities.ng.v1.0.json")) == V1_0_SHA256)
    r.add("the candidate is not at the repository root",
          not os.path.exists(repo_path("facilities.ng.v2.0.json")))

    # --- publication tooling still blocks -------------------------------------------------------------------
    plan = load_json(PLAN) if os.path.exists(PLAN) else None
    r.add("the dry-run plan describes the current bytes and performs nothing",
          plan is not None
          and plan["descriptor"]["sha256"] == "sha256:%s" % sha256_file(CANDIDATE)
          and all(v is False for k, v in plan["operations_performed"].items()
                  if k.endswith(("_performed", "_modified"))))
    r.add("the dry-run plan is ineligible everywhere and unauthorised for activation",
          plan is not None
          and plan["eligible_in_any_environment"] is False
          and plan["descriptor"]["activation_authorized"] is False
          and plan["descriptor"]["activation_status"] == "inactive"
          and plan["conclusion"]["publishable"] is False
          and plan["conclusion"]["activatable"] is False)

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
