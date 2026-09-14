#!/usr/bin/env python3
"""Tests for the GRID3-lineage Facilities 2.0 candidate.

    python3 testing/facilities_grid3/test_facilities_grid3.py [-v]

The tests that matter most guard what the pipeline refuses to do: read anything
but the permitted GRID3 source, invent a type, a phone, an opening hour or an
emergency capability, move a coordinate, or leave publication unblocked. Each
guard has a test that fails if it is removed, and the schema mutations prove
the schema is a gate rather than a description.
"""

import copy
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from facilities_grid3 import source as S  # noqa: E402
from build_facilities_grid3_candidate import (ATTRIBUTION_CITATION, TYPE_MAPPING_PROPOSAL,  # noqa: E402
                                              facility_id)
from vocab.artifact_io import load_json, sha256_file  # noqa: E402
from vocab.schema_check import validate as schema_validate  # noqa: E402


def repo(*parts):
    return os.path.join(ROOT, *parts)


CANDIDATE = load_json(repo("candidate", "facilities.ng.v2.0-grid3.json"))
META = CANDIDATE["_metadata"]
RECORDS = CANDIDATE["facilities"]
SCHEMA = load_json(repo("schema", "facilities_grid3.v2.schema.json"))
QUARANTINE = load_json(repo("reports", "facilities_grid3_quarantine_v1.json"))
ISOLATION = load_json(repo("reports", "facilities_grid3_isolation_v1.json"))
QUALITY = load_json(repo("reports", "facilities_grid3_quality_v1.json"))
MANIFEST = load_json(repo("candidate", "facilities_grid3.manifest.candidate.json"))
PROPOSAL = load_json(repo("proposals", "facilities_grid3", "type_mapping_proposal_v1.json"))


class PermittedSourceTests(unittest.TestCase):
    def test_source_bytes_match_the_pin(self):
        self.assertEqual(sha256_file(S.GRID3_PATH), S.GRID3_SHA256)

    def test_source_drift_is_refused(self):
        saved = S.GRID3_SHA256
        try:
            S.GRID3_SHA256 = "0" * 64
            with self.assertRaises(S.SourceDrift):
                S.read_source()
        finally:
            S.GRID3_SHA256 = saved

    def test_licence_evidence_exists_and_pins_the_source_and_legalcode(self):
        evidence = load_json(repo("facilities", "source", "grid3_licence_evidence_v1.json"))
        self.assertEqual(evidence["source_file"]["sha256"], S.GRID3_SHA256)
        self.assertEqual(evidence["licence"]["name"],
                         "Creative Commons Attribution 4.0 International (CC BY 4.0)")
        self.assertIn("adapt the work", evidence["licence"]["licence_statement_verbatim"])
        self.assertEqual(sha256_file(repo("facilities", "source", "CC-BY-4.0.legalcode.txt")),
                         evidence["licence"]["legal_code_vendored"]["sha256"])

    def test_the_candidate_states_its_licence_and_snapshot(self):
        self.assertEqual(META["source"]["licence"], "CC BY 4.0")
        self.assertEqual(META["source"]["snapshot_declared_version"], "2.0")
        self.assertEqual(META["source"]["snapshot_last_updated_at"], "2024-11-11")

    def test_attribution_notice_is_present_and_exact(self):
        with open(repo("facilities", "ATTRIBUTION_GRID3.md"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(ATTRIBUTION_CITATION, text)
        self.assertIn("https://creativecommons.org/licenses/by/4.0", text)
        self.assertIn("Modifications were made", text)
        self.assertEqual(META["source"]["attribution"]["citation"], ATTRIBUTION_CITATION)
        self.assertTrue(META["source"]["attribution"]["required"])


class IsolationTests(unittest.TestCase):
    def test_the_input_door_refuses_every_forbidden_source(self):
        for path in S.FORBIDDEN_SOURCES:
            with self.assertRaises(S.ForbiddenInput):
                S.open_input(repo(*path.split("/")))

    def test_no_forbidden_source_is_a_permitted_input(self):
        allowed = set(S.ALLOWED_INPUTS)
        for path in S.FORBIDDEN_SOURCES:
            self.assertNotIn(repo(*path.split("/")), allowed)

    def test_the_candidate_bytes_carry_zero_nhfr_markers(self):
        with open(repo("candidate", "facilities.ng.v2.0-grid3.json"), "rb") as handle:
            data = handle.read()
        for marker in S.NHFR_MARKER_STRINGS:
            self.assertEqual(data.count(marker.encode("utf-8")), 0, marker)

    def test_the_isolation_report_recorded_a_clean_scan(self):
        self.assertEqual(ISOLATION["nhfr_marker_scan"]["total_hits"], 0)
        self.assertEqual(ISOLATION["structural_facts"]["phone_values_non_null"], 0)

    def test_every_record_traces_to_grid3(self):
        rows = {row["globalid"].strip(): row for row in S.read_source()}
        for rec in RECORDS[:: 500] + RECORDS[-1:]:
            row = rows[rec["source_record"]["source_globalid"]]
            self.assertEqual(rec["latitude"], float(row["latitude"]))
            self.assertEqual(rec["longitude"], float(row["longitude"]))
            self.assertEqual(rec["name"], S.clean_text(row["facility_name"]))
            self.assertEqual(rec["facility_id"], facility_id(row["globalid"].strip()))

    def test_facility_ids_are_grid3_shaped_and_unique(self):
        ids = [rec["facility_id"] for rec in RECORDS]
        self.assertEqual(len(ids), len(set(ids)))
        for one in ids[:: 1000]:
            self.assertRegex(one, r"^ng_g3_[0-9a-f-]{36}$")

    def test_uuid_prefix_is_stripped_never_duplicated(self):
        self.assertEqual(facility_id("uuid:AB12cd34-0000-1111-2222-333344445555"),
                         "ng_g3_ab12cd34-0000-1111-2222-333344445555")
        self.assertEqual(facility_id("ab12cd34-0000-1111-2222-333344445555"),
                         "ng_g3_ab12cd34-0000-1111-2222-333344445555")


class NothingInventedTests(unittest.TestCase):
    def test_type_is_null_everywhere(self):
        self.assertTrue(all(rec["type"] is None for rec in RECORDS))

    def test_phone_and_opening_hours_are_null_everywhere(self):
        self.assertTrue(all(rec["phone"] is None for rec in RECORDS))
        self.assertTrue(all(rec["opening_hours"] is None for rec in RECORDS))

    def test_emergency_capable_is_never_invented(self):
        self.assertTrue(all(rec["emergency_capable"] is None for rec in RECORDS))

    def test_services_claim_nothing(self):
        for rec in RECORDS[:: 500]:
            self.assertEqual(set(rec["services"]),
                             {"onsite_laboratory", "onsite_imaging", "onsite_pharmacy",
                              "mortuary", "ambulance"})
            self.assertTrue(all(v is None for v in rec["services"].values()))

    def test_no_coordinate_was_transformed(self):
        self.assertTrue(all(rec["source_record"]["coordinate_transformation"] == "none"
                            for rec in RECORDS))

    def test_unknown_is_the_source_speaking_not_absence(self):
        counts = QUALITY["distributions"]["facility_level"]
        self.assertEqual(counts.get("unknown"), 334)
        self.assertNotIn("Unknown", counts)
        self.assertNotIn("None", counts)


class QuarantineTests(unittest.TestCase):
    def test_accounting_sums(self):
        self.assertEqual(QUARANTINE["source_rows"], S.GRID3_ROWS)
        self.assertEqual(QUARANTINE["emitted"] + QUARANTINE["quarantined"], S.GRID3_ROWS)
        self.assertEqual(QUARANTINE["emitted"], len(RECORDS))

    def test_invalid_coordinates_would_be_quarantined(self):
        self.assertEqual(S.parse_coordinates({"latitude": "0", "longitude": "0"}),
                         (None, "null_island"))
        self.assertEqual(S.parse_coordinates({"latitude": "52.5", "longitude": "13.4"}),
                         (None, "out_of_bounds"))
        self.assertEqual(S.parse_coordinates({"latitude": "", "longitude": "7.1"}),
                         (None, "coordinate_unparseable"))
        self.assertEqual(S.parse_coordinates({"latitude": "9.05", "longitude": "7.49"}),
                         ((9.05, 7.49), None))

    def test_state_position_anomaly_would_be_quarantined(self):
        cluster = [(6.5 + i * 0.001, 3.3 + i * 0.001, "Lagos") for i in range(12)]
        # A point deep in the Lagos cluster but declared Borno, with no Borno
        # facility within 50 km, must be flagged; the same point declared Lagos
        # must not be.
        instrument = S.StateConsistency(cluster + [(6.5005, 3.3005, "Borno")])
        self.assertFalse(instrument.is_consistent(len(cluster)))
        instrument2 = S.StateConsistency(cluster + [(6.5005, 3.3005, "Lagos")])
        self.assertTrue(instrument2.is_consistent(len(cluster)))


class CoverageTests(unittest.TestCase):
    def test_all_37_states_are_covered(self):
        self.assertEqual(META["states_covered"], S.CANONICAL_STATES)
        self.assertEqual(META["states_absent"], [])
        self.assertEqual(META["states_with_no_emitted_records"], [])
        self.assertEqual(QUALITY["coverage"]["states_covered"], 37)

    def test_the_three_nhfr_missing_states_are_present_here(self):
        per_state = QUALITY["coverage"]["per_state_counts"]
        self.assertEqual(per_state["Adamawa"], 1561)
        self.assertEqual(per_state["Kebbi"], 1207)
        self.assertEqual(per_state["Sokoto"], 937)

    def test_reported_per_state_counts_sum_to_the_total(self):
        self.assertEqual(sum(QUALITY["coverage"]["per_state_counts"].values()),
                         META["total_facilities"])

    def test_fct_is_normalized(self):
        self.assertIn("FCT", QUALITY["coverage"]["per_state_counts"])
        self.assertNotIn("Fct", QUALITY["coverage"]["per_state_counts"])


class SchemaGateTests(unittest.TestCase):
    def test_the_candidate_satisfies_the_schema(self):
        self.assertEqual(schema_validate(CANDIDATE, SCHEMA), [])

    def _mutated(self, mutate):
        clone = {"_metadata": copy.deepcopy(META),
                 "facilities": [copy.deepcopy(RECORDS[0])]}
        mutate(clone)
        return schema_validate(clone, SCHEMA)

    def test_schema_rejects_a_populated_type(self):
        errors = self._mutated(lambda c: c["facilities"][0].__setitem__("type", "hospital"))
        self.assertTrue(errors)

    def test_schema_rejects_a_populated_phone(self):
        errors = self._mutated(lambda c: c["facilities"][0].__setitem__("phone", "+2348031234567"))
        self.assertTrue(errors)

    def test_schema_rejects_a_populated_emergency_capable(self):
        errors = self._mutated(lambda c: c["facilities"][0].__setitem__("emergency_capable", True))
        self.assertTrue(errors)

    def test_schema_rejects_a_coordinate_swap(self):
        errors = self._mutated(lambda c: c["facilities"][0]["source_record"].__setitem__(
            "coordinate_transformation", "swap_lat_lon"))
        self.assertTrue(errors)

    def test_schema_rejects_publication(self):
        errors = self._mutated(lambda c: c["_metadata"].__setitem__("may_publish", True))
        self.assertTrue(errors)
        errors = self._mutated(lambda c: c["_metadata"].__setitem__(
            "release_status", "approved"))
        self.assertTrue(errors)

    def test_schema_rejects_an_nhfr_lineage_claim(self):
        errors = self._mutated(lambda c: c["_metadata"].__setitem__("lineage", "nhfr"))
        self.assertTrue(errors)


class GovernanceTests(unittest.TestCase):
    def test_publication_is_blocked_everywhere_it_is_stated(self):
        self.assertEqual(META["release_status"], "candidate_unapproved")
        self.assertEqual(META["publication_status"], "candidate_unapproved")
        self.assertIs(META["may_publish"], False)
        self.assertIs(MANIFEST["IS_LIVE_MANIFEST"], False)
        self.assertIs(MANIFEST["candidate_artifact"]["may_publish"], False)
        gates = MANIFEST["publication_gates"]
        self.assertTrue(all(v is False for k, v in gates.items()
                            if k != "source_licensing_established"))
        self.assertIs(gates["source_licensing_established"], True)

    def test_frozen_artifacts_are_byte_identical(self):
        self.assertEqual(sha256_file(repo("facilities.ng.v1.1.json")),
                         "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398")
        self.assertEqual(sha256_file(repo("facilities.ng.v1.0.json")),
                         "1c7b939199ab4465156f4cb336910eea120fcaa70f8b1c0743fc9f7a7c03009e")

    def test_the_manifest_binds_rollback_to_1_1(self):
        self.assertEqual(MANIFEST["rollback"]["target_file"], "facilities.ng.v1.1.json")
        self.assertEqual(MANIFEST["rollback"]["target_sha256"],
                         sha256_file(repo("facilities.ng.v1.1.json")))

    def test_the_type_mapping_is_proposed_not_applied(self):
        self.assertEqual(PROPOSAL["_metadata"]["status"], "PENDING_PRODUCT_REVIEW")
        self.assertIs(PROPOSAL["_metadata"]["applied"], False)
        self.assertEqual(PROPOSAL["decision"]["status"], "pending")
        self.assertIsNone(PROPOSAL["decision"]["reviewer"])
        self.assertEqual({entry["source_value"] for entry in TYPE_MAPPING_PROPOSAL},
                         set(PROPOSAL["source_value_inventory"]))

    def test_no_type_is_proposed_for_the_sources_unknown(self):
        entry = next(e for e in PROPOSAL["mapping"] if e["source_value"] == "unknown")
        self.assertIsNone(entry["proposed_type"])


SERVED = load_json(repo("candidate", "facilities.ng.v2.0-grid3.served.json"))
SERVED_META = SERVED["_metadata"]
SERVED_RECORDS = SERVED["facilities"]
SERVED_SCHEMA = load_json(repo("schema", "facilities_grid3_served.v2.schema.json"))
SIZE_REPORT = load_json(repo("reports", "facilities_grid3_size_v1.json"))


class ServedProjectionTests(unittest.TestCase):
    """The compact served candidate: a field selection of the master, never a
    change of values, never a channel for the fields awaiting decisions."""

    def test_all_51022_records_appear_exactly_once(self):
        self.assertEqual(len(SERVED_RECORDS), 51022)
        ids = [rec["id"] for rec in SERVED_RECORDS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {m["facility_id"] for m in RECORDS})

    def test_values_are_identical_to_the_master_in_order(self):
        for rec, m in zip(SERVED_RECORDS, RECORDS):
            self.assertEqual(rec["id"], m["facility_id"])
            self.assertEqual(rec["name"], m["name"])
            self.assertEqual(rec["state"], m["state"])
            self.assertEqual(rec["city_area"], m["city_area"])
            self.assertEqual(rec["latitude"], m["latitude"])
            self.assertEqual(rec["longitude"], m["longitude"])

    def test_served_records_carry_only_the_consumed_keys(self):
        wanted = {"id", "name", "state", "city_area", "latitude", "longitude"}
        for rec in SERVED_RECORDS[:: 500]:
            self.assertEqual(set(rec), wanted)

    def test_no_source_record_or_forbidden_field_reaches_the_wire(self):
        facilities_bytes = json.dumps(SERVED_RECORDS, separators=(",", ":"),
                                      ensure_ascii=True).encode("utf-8")
        for key in ("source_record", "phone", "opening_hours", "type",
                    "emergency_capable", "facility_id", "nhfr_uid", "ward"):
            self.assertEqual(facilities_bytes.count(b'"%s":' % key.encode()), 0, key)

    def test_no_nhfr_marker_in_served_bytes(self):
        with open(repo("candidate", "facilities.ng.v2.0-grid3.served.json"), "rb") as handle:
            data = handle.read()
        for marker in S.NHFR_MARKER_STRINGS:
            self.assertEqual(data.count(marker.encode("utf-8")), 0, marker)

    def test_served_traceability_to_the_source(self):
        rows = {}
        for row in S.read_source():
            gid = row["globalid"].strip()
            rows[(gid[5:] if gid.startswith("uuid:") else gid).lower()] = row
        for rec in SERVED_RECORDS[:: 500] + SERVED_RECORDS[-1:]:
            row = rows[rec["id"][len("ng_g3_"):]]
            self.assertEqual(rec["latitude"], float(row["latitude"]))
            self.assertEqual(rec["longitude"], float(row["longitude"]))
            self.assertEqual(rec["name"], S.clean_text(row["facility_name"]))

    def test_served_artifact_satisfies_its_schema(self):
        self.assertEqual(schema_validate(SERVED, SERVED_SCHEMA), [])

    def _mutated(self, mutate):
        clone = {"schema_version": "2.0",
                 "_metadata": copy.deepcopy(SERVED_META),
                 "facilities": [copy.deepcopy(SERVED_RECORDS[0])]}
        mutate(clone)
        return schema_validate(clone, SERVED_SCHEMA)

    def test_served_schema_rejects_the_decision_gated_fields_even_as_null(self):
        for key, value in (("type", None), ("type", "hospital"),
                           ("emergency_capable", None), ("emergency_capable", True),
                           ("phone", "+2348031234567"), ("opening_hours", "24_hours"),
                           ("source_record", {})):
            errors = self._mutated(lambda c, k=key, v=value: c["facilities"][0].__setitem__(k, v))
            self.assertTrue(errors, key)

    def test_served_schema_rejects_publication_and_role_drift(self):
        self.assertTrue(self._mutated(lambda c: c["_metadata"].__setitem__("may_publish", True)))
        self.assertTrue(self._mutated(lambda c: c["_metadata"].__setitem__(
            "release_status", "approved")))
        self.assertTrue(self._mutated(lambda c: c["_metadata"].__setitem__("role", "master")))
        self.assertTrue(self._mutated(lambda c: c.__setitem__("schema_version", "1.0")))

    def test_every_record_passes_the_verified_pr79_acceptance_rules(self):
        from validate_facilities_grid3_served import pr79_accepts
        self.assertTrue(all(pr79_accepts(rec) for rec in SERVED_RECORDS))

    def test_attribution_travels_with_the_served_artifact(self):
        source = SERVED_META["source"]
        self.assertEqual(source["attribution_citation"], ATTRIBUTION_CITATION)
        self.assertEqual(source["licence"], "CC BY 4.0")
        self.assertEqual(source["attribution_licence_url"],
                         "https://creativecommons.org/licenses/by/4.0")
        self.assertIn("Modifications by WellaPath", source["modifications_disclosed"])

    def test_served_publication_is_blocked(self):
        self.assertEqual(SERVED_META["release_status"], "candidate_unapproved")
        self.assertEqual(SERVED_META["publication_status"], "candidate_unapproved")
        self.assertIs(SERVED_META["may_publish"], False)
        self.assertIs(MANIFEST["served_artifact"]["may_publish"], False)

    def test_served_serialization_is_compact_canonical(self):
        with open(repo("candidate", "facilities.ng.v2.0-grid3.served.json"), "rb") as handle:
            data = handle.read()
        self.assertEqual(data, json.dumps(json.loads(data), separators=(",", ":"),
                                          ensure_ascii=True).encode("utf-8"))
        self.assertNotIn(b"\n", data)

    def test_size_report_is_generated_and_truthful(self):
        import gzip as gzip_module
        with open(repo("candidate", "facilities.ng.v2.0-grid3.served.json"), "rb") as handle:
            data = handle.read()
        entry = SIZE_REPORT["artifacts"]["served_candidate"]
        self.assertEqual(entry["bytes"], len(data))
        self.assertEqual(entry["gzip_bytes"], len(gzip_module.compress(data, 9)))
        self.assertEqual(SIZE_REPORT["_metadata"]["gzip_level"], 9)
        self.assertEqual(sum(v["records"] for v in
                             SIZE_REPORT["per_state_served_bytes"].values()), 51022)

    def test_master_is_not_the_distribution_artifact(self):
        self.assertEqual(MANIFEST["candidate_artifact"]["role"], "master_audit_candidate")
        self.assertIn("NOT designated for mobile distribution",
                      MANIFEST["artifact_roles"]["master_audit_candidate"])
        self.assertEqual(SERVED_META["master_candidate"]["path"],
                         "candidate/facilities.ng.v2.0-grid3.json")


class DeterminismTests(unittest.TestCase):
    def test_regeneration_is_byte_identical(self):
        import build_facilities_grid3_candidate as gen
        outputs = gen.build()
        for path, data in outputs.items():
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), data, path)

    def test_generated_at_is_a_constant_not_a_clock(self):
        import build_facilities_grid3_candidate as gen
        self.assertEqual(gen.GENERATED_AT, "2026-09-14T00:00:00Z")
        self.assertEqual(META["generated_at"], gen.GENERATED_AT)

    def test_serialization_is_canonical(self):
        with open(repo("candidate", "facilities.ng.v2.0-grid3.json"), "rb") as handle:
            data = handle.read()
        self.assertEqual(data, json.dumps(json.loads(data), indent=2,
                                          ensure_ascii=True).encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
