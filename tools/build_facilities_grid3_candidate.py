#!/usr/bin/env python3
"""Build the GRID3-only Facilities 2.0 candidate and every report it owes.

    python3 tools/build_facilities_grid3_candidate.py            # write everything
    python3 tools/build_facilities_grid3_candidate.py --check     # fail if anything is stale

Outputs (all deterministic, byte-reproducible):

  candidate/facilities.ng.v2.0-grid3.json               INTERNAL AUDIT/MASTER candidate
  candidate/facilities.ng.v2.0-grid3.served.json        COMPACT SERVED candidate (projection)
  candidate/facilities_grid3.manifest.candidate.json    proposed manifest, NOT live
  reports/facilities_grid3_quality_v1.json              data-quality report
  reports/facilities_grid3_quarantine_v1.json           every refused row, with reason
  reports/facilities_grid3_comparison_v1.json           against active facilities 1.1
  reports/facilities_grid3_isolation_v1.json            source-isolation proof
  reports/facilities_grid3_size_v1.json                 served size measurements
  proposals/facilities_grid3/type_mapping_proposal_v1.json  FAC-D001 input, NOT applied

Three artifacts, three roles, never confused: the SOURCE is the licensed GRID3
CSV; the MASTER is the full audit candidate with per-record source_record
traceability; the SERVED candidate is the master projected onto exactly the
fields the Mobile PR #79 parser consumes (verified at wellapath-mobile
854377c0), serialized compactly for distribution. Neither candidate may be
published: both carry candidate_unapproved / may_publish false.

The sole data source is the hash-pinned GRID3 CSV. facilities.ng.v1.1.json is
read for the COMPARISON REPORT only and contributes no value to the candidate.
The NHFR internal export and everything derived from it are forbidden inputs;
tools/facilities_grid3/source.py whitelists what may be opened, and the
isolation report scans the emitted bytes for NHFR markers.

Standard library only, no network.
"""

import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities_grid3 import source as S
from vocab.artifact_io import (dump_artifact_bytes, dump_report_bytes, load_json,
                               repo_path, sha256_bytes, sha256_file, write_bytes)

FACILITIES_GRID3_TOOLING_VERSION = "1.0.0"
GENERATED_AT = "2026-09-14T00:00:00Z"

CANDIDATE_PATH = repo_path("candidate", "facilities.ng.v2.0-grid3.json")
SERVED_PATH = repo_path("candidate", "facilities.ng.v2.0-grid3.served.json")
SIZE_REPORT_PATH = repo_path("reports", "facilities_grid3_size_v1.json")
MANIFEST_PATH = repo_path("candidate", "facilities_grid3.manifest.candidate.json")

#: Mobile PR #79 head this projection's parser facts were verified against.
MOBILE_PR79_COMMIT = "854377c0170836e98f418fb4805bdb18ae78845d"

#: Fixed, documented gzip level for every size measurement in this pipeline.
GZIP_LEVEL = 9
QUALITY_PATH = repo_path("reports", "facilities_grid3_quality_v1.json")
QUARANTINE_PATH = repo_path("reports", "facilities_grid3_quarantine_v1.json")
COMPARISON_PATH = repo_path("reports", "facilities_grid3_comparison_v1.json")
ISOLATION_PATH = repo_path("reports", "facilities_grid3_isolation_v1.json")
PROPOSAL_PATH = repo_path("proposals", "facilities_grid3", "type_mapping_proposal_v1.json")

ATTRIBUTION_CITATION = (
    "Center for Integrated Earth System Information (CIESIN), Columbia University 2024. "
    "GRID3 NGA - Health Facilities v2.0. New York: GRID3. https://doi.org/10.7916/kv1n-0743. "
    "Accessed 20 July 2026."
)
MODIFICATIONS_DISCLOSED = (
    "Modifications by WellaPath: field projection into the schema-2.0 consumer contract; "
    "text normalization (NFC, control characters removed, whitespace collapsed); state-name "
    "normalization ('Fct' -> 'FCT'); ownership_type token normalization; explicit source "
    "'Unknown' carried as the string 'unknown'; exact-duplicate policy and quarantine policy "
    "as recorded in _metadata. No coordinate was moved, swapped, snapped or invented; no "
    "value was added from any other source."
)

#: FAC-D001 input. Deterministic, reviewable, NOT applied: every emitted record
#: has type null regardless of this table. Prior art: the same mapping shipped
#: inside facilities 1.0/1.1 via facilities/source/build_e5.py (GRID3_TYPE_MAP),
#: so approving it would make 2.0 consistent with what 1.1 already does.
TYPE_MAPPING_PROPOSAL = [
    {"source_value": "General Hospital", "proposed_type": "hospital",
     "basis": "The source value names a hospital. E5 precedent: mapped to hospital in facilities 1.0/1.1."},
    {"source_value": "Teaching/Tertiary Hospital", "proposed_type": "hospital",
     "basis": "The source value names a hospital. E5 precedent: mapped to hospital in facilities 1.0/1.1."},
    {"source_value": "Specialized Hospital", "proposed_type": "hospital",
     "basis": "The source value names a hospital. E5 precedent: mapped to hospital in facilities 1.0/1.1."},
    {"source_value": "Primary Health Center", "proposed_type": "health_centre",
     "basis": "Primary-care facility. E5 precedent: mapped to health_centre in facilities 1.0/1.1."},
    {"source_value": "Primary Health Clinic", "proposed_type": "health_centre",
     "basis": "E5 precedent mapped this to health_centre alongside Primary Health Center. The word 'Clinic' "
              "makes 'clinic' arguable; flagged for explicit Product choice rather than silently inheriting "
              "the precedent.", "flag": "product_choice_health_centre_vs_clinic"},
    {"source_value": "Health Post", "proposed_type": "health_centre",
     "basis": "Smallest primary-care tier. E5 precedent: mapped to health_centre in facilities 1.0/1.1."},
    {"source_value": "unknown", "proposed_type": None,
     "basis": "The source explicitly recorded Unknown. No mapping is proposed; the record's type stays null."},
]


def dump_compact_bytes(obj):
    """Compact canonical JSON: no whitespace, ensure_ascii, no trailing newline.

    The served artifact's sha256 — the value a manifest would pin and the
    Mobile loader would verify — is over exactly these bytes. gzip at
    GZIP_LEVEL is a measurement, never the delivery representation: the
    verified PR #79 loader hashes the raw body.
    """
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def project_served_record(record):
    """One master record -> its served projection. Field set VERIFIED against
    the Mobile PR #79 parser (see the served schema's description): id, name
    and coordinates are required by the parser; state and city_area feed the
    state/LGA/manual search; every omitted optional key parses as null; any
    other key would ride along as opaque per-record memory. Values are carried
    verbatim — this function may select fields, never change one.
    """
    return {
        "id": record["facility_id"],
        "name": record["name"],
        "state": record["state"],
        "city_area": record["city_area"],
        "latitude": record["latitude"],
        "longitude": record["longitude"],
    }


def canonical_state(raw):
    cleaned = S.clean_text(raw)
    return S.STATE_NORMALIZATION.get(cleaned, cleaned)


def facility_id(globalid):
    bare = globalid[5:] if globalid.startswith("uuid:") else globalid
    return "ng_g3_" + bare.lower()


def build():
    rows = S.read_source()

    quarantined = []
    prepared = []
    for row in rows:
        objectid = row["OBJECTID"].strip()
        name = S.clean_text(row["facility_name"])
        state = canonical_state(row["state"])
        lga = S.clean_text(row["lga"])
        if not name:
            quarantined.append({"source_objectid": objectid, "reason": "invalid_name"})
            continue
        if state not in S.CANONICAL_STATES:
            quarantined.append({"source_objectid": objectid, "reason": "unknown_state",
                                "state_as_given": row["state"]})
            continue
        if not lga:
            quarantined.append({"source_objectid": objectid, "reason": "invalid_lga"})
            continue
        coords, refusal = S.parse_coordinates(row)
        if refusal:
            quarantined.append({"source_objectid": objectid, "reason": refusal,
                                "latitude_as_given": row["latitude"],
                                "longitude_as_given": row["longitude"]})
            continue
        prepared.append((row, objectid, name, state, lga, coords))

    # State-position consistency: conservative anomaly quarantine, never a relabel.
    instrument = S.StateConsistency([(c[0], c[1], state)
                                     for _r, _o, _n, state, _l, c in prepared])
    surviving = []
    for index, entry in enumerate(prepared):
        if instrument.is_consistent(index):
            surviving.append(entry)
        else:
            row, objectid, name, state, lga, coords = entry
            quarantined.append({
                "source_objectid": objectid, "reason": "state_position_mismatch",
                "state_as_given": state, "latitude": coords[0], "longitude": coords[1],
                "note": "Declared state and position disagree under %s; the row is held, "
                        "not relabelled and not moved." % S.StateConsistency.RULE_ID,
            })

    # Exact duplicates: same normalized name, state, LGA and exact coordinate
    # strings collapse to the smallest OBJECTID. No values are merged.
    groups = {}
    for entry in surviving:
        row, objectid, name, state, lga, coords = entry
        key = (name.casefold(), state, lga.casefold(),
               row["latitude"].strip(), row["longitude"].strip())
        groups.setdefault(key, []).append(entry)
    emitted_entries = []
    duplicate_rows_removed = []
    duplicate_groups_collapsed = 0
    for key in groups:
        members = sorted(groups[key], key=lambda e: int(e[1]))
        emitted_entries.append(members[0])
        if len(members) > 1:
            duplicate_groups_collapsed += 1
        for row, objectid, _n, _s, _l, _c in members[1:]:
            duplicate_rows_removed.append({"source_objectid": objectid,
                                           "reason": "exact_duplicate_removed",
                                           "survivor_objectid": members[0][1]})
    quarantined.extend(duplicate_rows_removed)

    # Near-duplicates: same name+state+LGA with different coordinates. Proposed
    # for review, never merged — two clinics may legitimately share a name.
    near = {}
    for row, objectid, name, state, lga, _c in emitted_entries:
        near.setdefault((name.casefold(), state, lga.casefold()), []).append(objectid)
    near_duplicate_groups = sorted(
        ({"name_state_lga": [k[0], k[1], k[2]], "source_objectids": sorted(v, key=int)}
         for k, v in near.items() if len(v) > 1),
        key=lambda g: g["source_objectids"][0].zfill(8))

    records = []
    for row, objectid, name, state, lga, coords in emitted_entries:
        level = S.clean_text(row["facility_level"])
        ownership = S.clean_text(row["ownership"])
        option = S.clean_text(row["facility_level_option"])
        records.append({
            "facility_id": facility_id(row["globalid"].strip()),
            "name": name,
            "type": None,
            "state": state,
            "city_area": lga,
            "latitude": coords[0],
            "longitude": coords[1],
            "phone": None,
            "opening_hours": None,
            "emergency_capable": None,
            "lga": lga,
            "ward": S.clean_text(row["ward"]),
            "address": None,
            "facility_level": "unknown" if level == "Unknown" else level,
            "ownership": "unknown" if ownership == "Unknown" else ownership,
            "ownership_type": S.OWNERSHIP_TYPE_MAP[S.clean_text(row["ownership_type"])],
            "operational_status": None,
            "registration_status": None,
            "license_status": None,
            "beds": None,
            "services": {"onsite_laboratory": None, "onsite_imaging": None,
                         "onsite_pharmacy": None, "mortuary": None, "ambulance": None},
            "source_record": {
                "source_objectid": objectid,
                "source_globalid": row["globalid"].strip(),
                "nhfr_uid": row["nhfr_uid"].strip() or None,
                "nhfr_facility_code": row["nhfr_facility_code"].strip() or None,
                "facility_level_option": "unknown" if option == "Unknown" else option,
                "facility_name_source": row["facility_name_source"].strip(),
                "geocoordinates_source": row["geocoordinates_source"].strip(),
                "lga_name_disagreement": row["lga_name_disagreement"].strip() == "1",
                "ward_name_disagreement": row["ward_name_disagreement"].strip() == "1",
                "source_last_updated": row["last_updated"].strip(),
                "coordinate_transformation": "none",
            },
        })

    records.sort(key=lambda r: (r["state"], r["lga"].casefold(),
                                r["name"].casefold(), r["facility_id"]))

    state_counts = {}
    for record in records:
        state_counts[record["state"]] = state_counts.get(record["state"], 0) + 1

    def distribution(field, from_source_record=False):
        counts = {}
        for record in records:
            value = (record["source_record"][field] if from_source_record
                     else record[field])
            counts[str(value)] = counts.get(str(value), 0) + 1
        return {k: counts[k] for k in sorted(counts)}

    absence_counts = {
        "type_null": len(records),
        "phone_null": len(records),
        "opening_hours_null": len(records),
        "emergency_capable_null": len(records),
        "address_null": len(records),
        "operational_status_null": len(records),
        "registration_status_null": len(records),
        "license_status_null": len(records),
        "beds_null": len(records),
        "services_all_null": len(records),
        "ward_null": sum(1 for r in records if r["ward"] is None),
        "nhfr_uid_null": sum(1 for r in records if r["source_record"]["nhfr_uid"] is None),
        "facility_level_unknown": sum(1 for r in records if r["facility_level"] == "unknown"),
        "ownership_unknown": sum(1 for r in records if r["ownership"] == "unknown"),
        "ownership_type_unknown": sum(1 for r in records if r["ownership_type"] == "unknown"),
    }

    metadata = {
        "artifact_id": "facilities",
        "lineage": "grid3",
        "version": "2.0",
        "schema_version": "2.0",
        "country": "ng",
        "release_status": "candidate_unapproved",
        "publication_status": "candidate_unapproved",
        "release_date": None,
        "may_publish": False,
        "generated_at": GENERATED_AT,
        "generator": "tools/build_facilities_grid3_candidate.py",
        "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
        "total_facilities": len(records),
        "states_covered": [s for s in S.CANONICAL_STATES if s in state_counts],
        "states_absent": [],
        "states_with_no_emitted_records": [s for s in S.CANONICAL_STATES
                                           if s not in state_counts],
        "coverage_claim": "All 36 states and the FCT, from the source's own rows; "
                          "per-state counts in reports/facilities_grid3_quality_v1.json.",
        "source": {
            "name": "GRID3 NGA - Health Facilities v2.0",
            "path": "facilities/source/GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv",
            "sha256": S.GRID3_SHA256,
            "byte_count": 13613859,
            "organization": "Center for Integrated Earth System Information (CIESIN), Columbia University",
            "publisher": "GRID3",
            "copyright": "Copyright 2024. The Trustees of Columbia University in the City of New York.",
            "licence": "CC BY 4.0",
            "licence_evidence": "facilities/source/grid3_licence_evidence_v1.json",
            "attribution": {
                "required": True,
                "citation": ATTRIBUTION_CITATION,
                "notice_file": "facilities/ATTRIBUTION_GRID3.md",
                "modifications_disclosed": MODIFICATIONS_DISCLOSED,
            },
            "doi": "https://doi.org/10.7916/kv1n-0743",
            "landing_page": "https://data.grid3.org/maps/GRID3::grid3-nga-health-facilities-v2-0",
            "snapshot_declared_version": "2.0",
            "snapshot_last_updated_at": "2024-11-11",
            "acquisition_commit": "29307a99e930774597ad5b6fcf342e053dd6eb84",
            "access_date_bound": "Downloaded no later than 2026-07-20, the commit instant of "
                                 "the source CSV; no earlier download record exists.",
        },
        "source_isolation": {
            "permitted_inputs": [
                {"path": "facilities/source/GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv",
                 "sha256": S.GRID3_SHA256, "role": "sole data source"},
                {"path": "facilities.ng.v1.1.json", "sha256": S.CURRENT_ARTIFACT_SHA256,
                 "role": "comparison baseline (report only; contributes no value to the candidate)"},
            ],
            "forbidden_sources": list(S.FORBIDDEN_SOURCES),
            "report": "reports/facilities_grid3_isolation_v1.json",
        },
        "deduplication": {
            "rule_id": "exact_match_v1",
            "key": "(normalized name, state, LGA, latitude-as-written, longitude-as-written)",
            "survivor": "smallest source OBJECTID; no values merged from removed rows",
            "values_merged": False,
            "groups_collapsed": duplicate_groups_collapsed,
            "rows_removed": len(duplicate_rows_removed),
            "near_duplicates_proposed_not_merged": len(near_duplicate_groups),
        },
        "coordinate_policy": {
            "rule": "GRID3 coordinates are accepted exactly as published, or the row is "
                    "quarantined. Nothing is swapped, snapped, moved or fabricated; the "
                    "source documents no correction and none is applied.",
            "transformation": "none",
            "state_consistency_check": "%s: quarantine (never relabel) when none of the 10 "
                                       "nearest facilities shares the declared state AND the "
                                       "nearest same-state facility is over 50 km away."
                                       % S.StateConsistency.RULE_ID,
            "quarantine_report": "reports/facilities_grid3_quarantine_v1.json",
        },
        "unresolved_fields": {
            "type": "Null on every record. The facility_level_option -> type mapping is "
                    "proposed in the FAC-D001 package and is NOT applied without Product "
                    "approval.",
            "emergency_capable": "Null on every record. GRID3 records no emergency "
                                 "capability and none is inferred (FAC-D002).",
            "type_vocabulary": ["hospital", "clinic", "health_centre", "pharmacy",
                                "laboratory", "other"],
            "type_mapping_proposal": "proposals/facilities_grid3/type_mapping_proposal_v1.json",
            "consumer_contract": "A null type is not a vocabulary member: never filter it "
                                 "out, never render an empty result list because of it. "
                                 "Prioritisation may apply only to emergency_capable == true, "
                                 "of which there are none.",
        },
        "absence_convention": {
            "null": "the source has no such column, or the field was blank",
            "unknown": "the source explicitly recorded Unknown — a different statement",
            "never": "absent represented as false, zero or an invented value",
        },
        "not_carried_from_source": {
            "x_y": "The export's duplicate geometry columns; identical to longitude/latitude.",
            "country_iso": "Constant Nigeria/NGA on every row; the artifact's country field "
                           "already states it.",
        },
        "absence_counts": absence_counts,
        "unmapped_source_values": {},
    }

    candidate = {"_metadata": metadata, "facilities": records}
    candidate_bytes = dump_artifact_bytes(candidate)

    # ---- isolation report ---------------------------------------------------------------
    marker_scan = {}
    for marker in S.NHFR_MARKER_STRINGS:
        marker_scan[marker] = candidate_bytes.count(marker.encode("utf-8"))
    isolation = {
        "_metadata": {
            "report_id": "facilities_grid3_isolation",
            "version": "1",
            "generator": "tools/build_facilities_grid3_candidate.py",
            "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
            "note": "Proof that the GRID3-lineage candidate is sourced from the GRID3 CSV "
                    "alone. The generator can only open whitelisted inputs "
                    "(tools/facilities_grid3/source.py ALLOWED_INPUTS); this report scans "
                    "the emitted bytes for NHFR markers; and "
                    "tools/validate_facilities_grid3_candidate.py independently re-derives "
                    "every record's values from the GRID3 CSV and re-runs this scan, so the "
                    "proof does not rest on the generator auditing itself.",
        },
        "permitted_inputs": metadata["source_isolation"]["permitted_inputs"],
        "forbidden_sources": list(S.FORBIDDEN_SOURCES),
        "forbidden_source_policy": "None of these paths is opened by the pipeline; the "
                                   "whitelist refuses them structurally. None is committed "
                                   "on this branch.",
        "nhfr_marker_scan": {
            "scanned_bytes": len(candidate_bytes),
            "markers": marker_scan,
            "total_hits": sum(marker_scan.values()),
        },
        "structural_facts": {
            "records": len(records),
            "phone_values_non_null": 0,
            "opening_hours_values_non_null": 0,
            "coordinate_transformations_other_than_none": 0,
            "facility_ids_not_ng_g3": 0,
            "note": "The zeros are computed from the records list at build time and "
                    "re-computed by the validator from the committed bytes.",
        },
        "nhfr_uid_clarification": "source_record.nhfr_uid and nhfr_facility_code are "
                                  "columns OF THE GRID3 FILE — the publisher's own "
                                  "cross-reference to the national registry, licensed "
                                  "CC BY 4.0 with the rest of the file. Their presence is "
                                  "not NHFR-export contamination; nothing was read from "
                                  "any NHFR export.",
    }

    # ---- quarantine report --------------------------------------------------------------
    reason_counts = {}
    for entry in quarantined:
        reason_counts[entry["reason"]] = reason_counts.get(entry["reason"], 0) + 1
    quarantine = {
        "_metadata": {
            "report_id": "facilities_grid3_quarantine",
            "version": "1",
            "generator": "tools/build_facilities_grid3_candidate.py",
            "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
            "note": "Every source row not emitted, each with its reason. "
                    "source_rows == emitted + quarantined, checked by the validator.",
        },
        "source_rows": S.GRID3_ROWS,
        "emitted": len(records),
        "quarantined": len(quarantined),
        "by_reason": {k: reason_counts[k] for k in sorted(reason_counts)},
        "rows": sorted(quarantined, key=lambda e: int(e["source_objectid"])),
    }

    # ---- quality report -----------------------------------------------------------------
    lga_pairs = sorted({(r["state"], r["lga"]) for r in records})
    quality = {
        "_metadata": {
            "report_id": "facilities_grid3_quality",
            "version": "1",
            "generator": "tools/build_facilities_grid3_candidate.py",
            "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
        },
        "coverage": {
            "states_covered": len(state_counts),
            "per_state_counts": {k: state_counts[k] for k in sorted(state_counts)},
            "distinct_state_lga_pairs": len(lga_pairs),
            "note": "Nigeria has 774 LGAs; the source's LGA naming is not asserted to be "
                    "the statutory list. (state, lga) is the search key, exactly as in the "
                    "sibling lineage.",
        },
        "identifiers": {
            "facility_ids_distinct": len({r["facility_id"] for r in records}),
            "source_objectids_distinct": len({r["source_record"]["source_objectid"]
                                              for r in records}),
            "source_globalids_distinct": len({r["source_record"]["source_globalid"]
                                              for r in records}),
            "nhfr_uid_present": sum(1 for r in records
                                    if r["source_record"]["nhfr_uid"] is not None),
        },
        "distributions": {
            "facility_level": distribution("facility_level"),
            "facility_level_option": distribution("facility_level_option", True),
            "ownership": distribution("ownership"),
            "ownership_type": distribution("ownership_type"),
            "facility_name_source": distribution("facility_name_source", True),
            "geocoordinates_source": distribution("geocoordinates_source", True),
        },
        "snapshot_consistency": {
            "last_updated_values": distribution("source_last_updated", True),
            "expectation": "a single constant value, 2024-11-11",
        },
        "near_duplicates": {
            "rule": "same normalized name, state and LGA with differing coordinates; "
                    "proposed for review, never merged (FAC-D006)",
            "groups": len(near_duplicate_groups),
            "rows_involved": sum(len(g["source_objectids"]) for g in near_duplicate_groups),
            "listing": near_duplicate_groups,
        },
        "artifact_size": {
            "bytes": len(candidate_bytes),
            "gzip_bytes": len(gzip.compress(candidate_bytes, 9)),
            "records": len(records),
            "facilities_1_1_bytes": 1695844,
            "note": "Low-end mobile implication: the candidate is roughly an order of "
                    "magnitude larger than 1.1. Mobile guidance in "
                    "mobile_handoff/facilities_grid3_v2/README.md; gzip is the transfer "
                    "bound, bytes the on-device bound.",
        },
    }

    # ---- comparison report (reads 1.1; contributes nothing to the candidate) -------------
    current = load_json(S.CURRENT_ARTIFACT_PATH)
    current_records = current["facilities"]
    current_by_state = {}
    for record in current_records:
        current_by_state[record["state"]] = current_by_state.get(record["state"], 0) + 1
    current_names = {(record["name"].casefold(), record["state"])
                     for record in current_records}
    candidate_names = {(r["name"].casefold(), r["state"]) for r in records}
    comparison = {
        "_metadata": {
            "report_id": "facilities_grid3_comparison",
            "version": "1",
            "generator": "tools/build_facilities_grid3_candidate.py",
            "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
            "baseline": {"path": "facilities.ng.v1.1.json",
                         "sha256": S.CURRENT_ARTIFACT_SHA256},
            "note": "facilities 1.1 stays the active artifact until every approval exists. "
                    "This report informs the changelog; no value from 1.1 enters the "
                    "candidate.",
        },
        "records": {"facilities_1_1": len(current_records), "candidate": len(records)},
        "per_state_1_1": {k: current_by_state[k] for k in sorted(current_by_state)},
        "per_state_candidate_for_1_1_states": {
            k: state_counts.get(k, 0) for k in sorted(current_by_state)},
        "name_state_exact_overlap": len(current_names & candidate_names),
        "fields_1_1_has_that_candidate_lacks": {
            "type": "1.1 carries a mapped type; the candidate's is null pending FAC-D001.",
            "emergency_capable": "1.1 derives it from type; the candidate's is null (FAC-D002).",
            "phone": "1.1 carries phones including 45 hand-verified Lagos numbers; the "
                     "candidate carries none (FAC-D003) — GRID3 publishes no contact data, "
                     "and this lineage adds nothing from any other source.",
            "opening_hours": "1.1 carries opening hours for some records; the candidate "
                             "carries none (FAC-D003).",
        },
        "coverage_1_1_lacks": "34 of the candidate's 37 states have no 1.1 records at all; "
                              "1.1 covers Lagos, FCT and Kano only.",
    }

    # ---- FAC-D001 proposal ---------------------------------------------------------------
    option_counts = distribution("facility_level_option", True)
    proposal = {
        "_metadata": {
            "proposal_id": "facilities_grid3_type_mapping",
            "version": "1",
            "generator": "tools/build_facilities_grid3_candidate.py",
            "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
            "status": "PENDING_PRODUCT_REVIEW",
            "applied": False,
            "note": "Deterministic mapping table for FAC-D001. NOT applied: every candidate "
                    "record's type is null, enforced by schema const and validators. "
                    "Approval means regenerating the candidate with the approved table, "
                    "never editing the artifact.",
        },
        "target_vocabulary": ["hospital", "clinic", "health_centre", "pharmacy",
                              "laboratory", "other"],
        "source_value_inventory": option_counts,
        "mapping": TYPE_MAPPING_PROPOSAL,
        "coverage_if_approved": {
            "records_mapped": sum(count for value, count in option_counts.items()
                                  if value != "unknown"),
            "records_left_null": option_counts.get("unknown", 0),
        },
        "decision": {"status": "pending", "reviewer_role": "Product", "reviewer": None,
                     "decided_on": None, "rationale": None},
    }

    # ---- served projection ----------------------------------------------------------------
    digest = sha256_bytes(candidate_bytes)
    served_records = [project_served_record(record) for record in records]
    served = {
        "schema_version": "2.0",
        "_metadata": {
            "artifact_id": "facilities",
            "lineage": "grid3",
            "role": "served_projection",
            "version": "2.0",
            "schema_version": "2.0",
            "country": "ng",
            "release_status": "candidate_unapproved",
            "publication_status": "candidate_unapproved",
            "release_date": None,
            "may_publish": False,
            "generated_at": GENERATED_AT,
            "generator": "tools/build_facilities_grid3_candidate.py",
            "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
            "total_facilities": len(served_records),
            "master_candidate": {
                "path": "candidate/facilities.ng.v2.0-grid3.json",
                "sha256": digest,
                "record_count": len(records),
                "projection": "Field selection only, values verbatim: served id = master "
                              "facility_id (= ng_g3_ + GRID3 globalid, the record-level "
                              "source reference); name, state, city_area, latitude, "
                              "longitude byte-equal to the master. Full provenance, "
                              "source_record traceability and the isolation proof live "
                              "with the master and its reports, once, not per record.",
            },
            "source": {
                "name": "GRID3 NGA - Health Facilities v2.0",
                "sha256": S.GRID3_SHA256,
                "licence": "CC BY 4.0",
                "licence_evidence": "facilities/source/grid3_licence_evidence_v1.json",
                "attribution_citation": ATTRIBUTION_CITATION,
                "attribution_licence_url": "https://creativecommons.org/licenses/by/4.0",
                "modifications_disclosed": MODIFICATIONS_DISCLOSED,
                "doi": "https://doi.org/10.7916/kv1n-0743",
                "snapshot_last_updated_at": "2024-11-11",
            },
            "consumer_contract": "Verified against Mobile PR #79 at wellapath-mobile %s "
                                 "(facilities_v2_parser.dart): records are consumed via "
                                 "{id, name, latitude, longitude, type, emergency_capable, "
                                 "state, lga, city_area, phone, opening_hours}; an ABSENT "
                                 "optional key parses identically to null, so type stays "
                                 "unspecified (never filtered out), emergency_capable stays "
                                 "unknown (never true), and phone/opening_hours stay null. "
                                 "Unconsumed keys are retained per record in memory, which "
                                 "is why this projection carries none." % MOBILE_PR79_COMMIT,
            "serialization": "Compact canonical JSON (json.dumps separators=(',',':'), "
                             "ensure_ascii, UTF-8, no trailing newline). A manifest pins "
                             "sha256 over exactly these raw bytes; gzip level %d is a "
                             "measurement, not the delivery representation." % GZIP_LEVEL,
        },
        "facilities": served_records,
    }
    served_bytes = dump_compact_bytes(served)
    served_digest = sha256_bytes(served_bytes)
    served_gzip = len(gzip.compress(served_bytes, GZIP_LEVEL))

    # ---- size report ----------------------------------------------------------------------
    per_state_bytes = {}
    for record in served_records:
        entry = per_state_bytes.setdefault(record["state"], {"records": 0, "raw_bytes": 0})
        entry["records"] += 1
        entry["raw_bytes"] += len(dump_compact_bytes(record)) + 1  # +1 for the list comma
    master_gzip = len(gzip.compress(candidate_bytes, GZIP_LEVEL))
    v1_1_bytes = 1695844
    size_report = {
        "_metadata": {
            "report_id": "facilities_grid3_size",
            "version": "1",
            "generator": "tools/build_facilities_grid3_candidate.py",
            "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
            "gzip_level": GZIP_LEVEL,
            "note": "Every number here is computed at build time from the emitted bytes; "
                    "the --check mode regenerates and byte-compares this report, so a "
                    "hand-edited figure fails the run.",
        },
        "artifacts": {
            "source_csv": {"path": "facilities/source/GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv",
                           "bytes": 13613859},
            "master_audit_candidate": {"path": "candidate/facilities.ng.v2.0-grid3.json",
                                       "bytes": len(candidate_bytes),
                                       "gzip_bytes": master_gzip,
                                       "role": "internal audit/master — NOT for mobile distribution"},
            "served_candidate": {"path": "candidate/facilities.ng.v2.0-grid3.served.json",
                                 "sha256": served_digest,
                                 "bytes": len(served_bytes),
                                 "gzip_bytes": served_gzip,
                                 "records": len(served_records),
                                 "role": "compact distribution shape (still candidate_unapproved)"},
            "facilities_1_1_active": {"path": "facilities.ng.v1.1.json", "bytes": v1_1_bytes},
        },
        "served_measurements": {
            "bytes_per_record": round(len(served_bytes) / len(served_records), 1),
            "reduction_vs_master_audit": "%.1f%%" % (100.0 * (1 - len(served_bytes) / len(candidate_bytes))),
            "size_vs_v1_1": "%.1fx the active 1.1 artifact for %.1fx the records and %.1fx the states"
                            % (len(served_bytes) / v1_1_bytes,
                               len(served_records) / 5344.0, 37 / 3.0),
            "targets": {
                "raw_at_or_below_15mb": len(served_bytes) <= 15 * 1024 * 1024,
                "gzip_at_or_below_5mb": served_gzip <= 5 * 1024 * 1024,
            },
            "parser_storage_implications": "The verified PR #79 parser materialises every "
                                           "record as a Dart object with no opaque leftovers "
                                           "(the projection carries only consumed keys), so "
                                           "in-memory cost tracks record count, not master "
                                           "size. The raw bytes are the parse/storage bound "
                                           "on device; gzip is the transfer bound.",
        },
        "per_state_served_bytes": {state: per_state_bytes[state]
                                   for state in sorted(per_state_bytes)},
    }

    # ---- manifest -------------------------------------------------------------------------
    manifest = {
        "manifest_id": "facilities_grid3_v2_candidate",
        "manifest_version": "1",
        "generator": "tools/build_facilities_grid3_candidate.py",
        "generator_version": FACILITIES_GRID3_TOOLING_VERSION,
        "IS_LIVE_MANIFEST": False,
        "WARNING": "This is a PROPOSED manifest block for a CANDIDATE artifact. It is not "
                   "served by any endpoint. The live manifest is GET /config in "
                   "wellapath-backend and is UNCHANGED. Source licensing is established for "
                   "this lineage (CC BY 4.0, evidence in-repo), but licensing clearance is "
                   "not Product, Clinical or Engineering approval. Do not wire this block.",
        "artifact_roles": {
            "source": "facilities/source/GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv "
                      "— the licensed GRID3 CSV, hash-pinned, never served",
            "master_audit_candidate": "candidate/facilities.ng.v2.0-grid3.json — full "
                                      "per-record provenance and traceability; internal "
                                      "only, NOT designated for mobile distribution",
            "served_candidate": "candidate/facilities.ng.v2.0-grid3.served.json — the "
                                "compact projection a manifest would point Mobile at, once "
                                "(and only once) every approval exists",
        },
        "candidate_artifact": {
            "path": "candidate/facilities.ng.v2.0-grid3.json",
            "lineage": "grid3",
            "role": "master_audit_candidate",
            "sha256": digest,
            "bytes": len(candidate_bytes),
            "record_count": len(records),
            "may_publish": False,
            "release_status": "candidate_unapproved",
        },
        "served_artifact": {
            "path": "candidate/facilities.ng.v2.0-grid3.served.json",
            "lineage": "grid3",
            "role": "served_candidate",
            "sha256": served_digest,
            "bytes": len(served_bytes),
            "gzip_bytes_level_%d" % GZIP_LEVEL: served_gzip,
            "record_count": len(served_records),
            "may_publish": False,
            "release_status": "candidate_unapproved",
            "consumer_verified_against": "wellapath-mobile %s (Mobile PR #79)" % MOBILE_PR79_COMMIT,
            "hash_contract": "sha256 over the raw compact JSON bytes, matching the PR #79 "
                             "loader's raw-body verification; gzip is a measurement only",
        },
        "source_licensing": {
            "licence": "CC BY 4.0",
            "evidence": "facilities/source/grid3_licence_evidence_v1.json",
            "attribution_notice": "facilities/ATTRIBUTION_GRID3.md",
            "attribution_must_ship_with": "artifact metadata (present) and the consuming "
                                          "app UI (Mobile handoff requirement)",
        },
        "publication_gates": {
            "source_licensing_established": True,
            "fac_d001_type_mapping_approved": False,
            "fac_d002_emergency_fallback_approved": False,
            "fac_d003_absent_contact_fields_accepted": False,
            "fac_d004_grid3_coordinates_accepted": False,
            "fac_d005_quarantine_policy_accepted": False,
            "fac_d006_duplicate_policy_accepted": False,
            "mobile_compatibility_remeasured": False,
            "engineering_approval": False,
            "product_approval": False,
            "clinical_approval": False,
            "may_publish": False,
        },
        "rollback": {
            "target_file": "facilities.ng.v1.1.json",
            "target_sha256": S.CURRENT_ARTIFACT_SHA256,
            "target_bytes": 1695844,
            "note": "facilities 1.1 is the active artifact and remains so; activation of "
                    "this candidate would carry this block as its rollback contract.",
        },
        "reports": {
            "quality": "reports/facilities_grid3_quality_v1.json",
            "quarantine": "reports/facilities_grid3_quarantine_v1.json",
            "comparison": "reports/facilities_grid3_comparison_v1.json",
            "isolation": "reports/facilities_grid3_isolation_v1.json",
            "type_mapping_proposal": "proposals/facilities_grid3/type_mapping_proposal_v1.json",
        },
    }

    outputs = {
        CANDIDATE_PATH: candidate_bytes,
        SERVED_PATH: served_bytes,
        SIZE_REPORT_PATH: dump_report_bytes(size_report),
        ISOLATION_PATH: dump_report_bytes(isolation),
        QUARANTINE_PATH: dump_report_bytes(quarantine),
        QUALITY_PATH: dump_report_bytes(quality),
        COMPARISON_PATH: dump_report_bytes(comparison),
        PROPOSAL_PATH: dump_report_bytes(proposal),
        MANIFEST_PATH: dump_report_bytes(manifest),
    }
    return outputs


def main(argv):
    check = "--check" in argv
    outputs = build()
    stale = []
    for path, data in outputs.items():
        relative = os.path.relpath(path, repo_path())
        if check:
            if not os.path.exists(path):
                stale.append("MISSING " + relative)
                continue
            with open(path, "rb") as handle:
                if handle.read() != data:
                    stale.append("DRIFT " + relative)
        else:
            write_bytes(path, data)
            print("wrote %s (%d bytes)" % (relative, len(data)))
    if check:
        if stale:
            print("\n".join(stale))
            return 1
        print("OK all %d GRID3 candidate outputs are current" % len(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
