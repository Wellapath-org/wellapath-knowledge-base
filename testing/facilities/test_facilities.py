#!/usr/bin/env python3
"""Tests for the nationwide facilities candidate.

    python3 testing/facilities/test_facilities.py [-v]

The tests that matter most are the ones guarding what the generator refuses to do. Anyone can
write a transformation that fills every field; the value here is that `type` and
`emergency_capable` stay null, that a coordinate pair is exchanged only under the strict
orientation rule and never invented, that a placeholder phone never becomes a real one, that a
personal email typed into an address field does not travel onward, and that the duplicate rule
collapses only what it says it does. Each of those has a test that fails if the guard is
removed.
"""

import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from facilities import geometry as G  # noqa: E402
from facilities import mappings as M  # noqa: E402
from facilities.normalize import (NIGERIA_MAX_LAT, NIGERIA_MAX_LON, NIGERIA_MIN_LAT,  # noqa: E402
                                  NIGERIA_MIN_LON, coordinate, duplicate_key, free_text,
                                  haversine_km, parse_coordinates, phone, sort_key,
                                  survivor_key, text, timestamp)
from vocab.artifact_io import load_json, sha256_file  # noqa: E402
from vocab.schema_check import validate as schema_validate  # noqa: E402


def repo(*parts):
    return os.path.join(ROOT, *parts)


CANDIDATE = load_json(repo("candidate", "facilities.ng.v2.0.json"))
RECORDS = CANDIDATE["facilities"]
META = CANDIDATE["_metadata"]
QUALITY = load_json(repo("reports", "facilities_quality_v1.json"))
QUARANTINE = load_json(repo("reports", "facilities_quarantine_v1.json"))
AUDIT = load_json(repo("reports", "facilities_coordinate_audit_v1.json"))
MANIFEST = load_json(repo("candidate", "facilities.manifest.candidate.json"))
CHECKLIST = load_json(repo("facilities", "source", "nhf_authorization_checklist_v1.json"))
GEOMETRY = G.StateGeometry.load()
SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"
CURRENT_SHA256 = "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398"
V1_0_SHA256 = "1c7b939199ab4465156f4cb336910eea120fcaa70f8b1c0743fc9f7a7c03009e"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CORRECTED = [r for r in RECORDS if r["source_record"]["coordinate_transformation"] != "none"]


class SourceIntegrityTests(unittest.TestCase):
    def test_source_bytes_match_the_pin(self):
        self.assertEqual(
            sha256_file(repo("facilities", "source", "nigeria_health_facilities.csv")),
            SOURCE_SHA256,
        )

    def test_the_reference_geometry_matches_its_pin(self):
        self.assertEqual(sha256_file(G.GRID3_PATH), G.GRID3_SHA256)
        self.assertEqual(META["coordinate_remediation"]["reference_geometry"]["sha256"], G.GRID3_SHA256)

    def test_the_artifact_records_the_source_it_was_built_from(self):
        self.assertEqual(META["source"]["sha256"], SOURCE_SHA256)
        self.assertEqual(META["source"]["byte_count"], 20913558)

    def test_source_drift_is_refused_rather_than_tolerated(self):
        import build_facilities_candidate as gen

        saved = gen.SOURCE_SHA256
        try:
            gen.SOURCE_SHA256 = "0" * 64
            with self.assertRaises(gen.SourceDrift):
                gen.read_source()
        finally:
            gen.SOURCE_SHA256 = saved

    def test_geometry_drift_is_refused_rather_than_tolerated(self):
        saved = G.GRID3_SHA256
        try:
            G.GRID3_SHA256 = "0" * 64
            with self.assertRaises(ValueError):
                G.StateGeometry.load()
        finally:
            G.GRID3_SHA256 = saved

    def test_provenance_records_what_is_not_established(self):
        p = load_json(repo("facilities", "source", "nhf_provenance_v1.json"))
        self.assertFalse(p["source_organization"]["established"])
        self.assertFalse(p["licence"]["established"])
        self.assertFalse(p["contact_fields_public_use"]["established"])
        self.assertIsNone(p["source_organization"]["recorded_name"])
        self.assertEqual(p["geographic_scope"]["states_absent"], ["Adamawa", "Kebbi", "Sokoto"])
        self.assertIn("coordinate_orientation", p["documentation"])

    def test_the_source_snapshot_instant_is_carried_without_a_zone_claim(self):
        self.assertEqual(META["source"]["snapshot_last_updated_at"], "2026-07-21T13:15:26")
        self.assertIsNone(META["source"]["snapshot_declared_version"])
        self.assertFalse(META["source"]["snapshot_last_updated_at"].endswith("Z"))


class DeterminismTests(unittest.TestCase):
    def test_regeneration_is_byte_identical(self):
        import build_facilities_candidate as gen
        from vocab.artifact_io import dump_artifact_bytes, dump_report_bytes

        artifact, quality, quarantine, audit = gen.build()
        with open(repo("candidate", "facilities.ng.v2.0.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_artifact_bytes(artifact))
        with open(repo("reports", "facilities_quality_v1.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_report_bytes(quality))
        with open(repo("reports", "facilities_quarantine_v1.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_report_bytes(quarantine))
        with open(repo("reports", "facilities_coordinate_audit_v1.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_report_bytes(audit))

    def test_records_are_in_the_canonical_order(self):
        self.assertEqual(RECORDS, sorted(RECORDS, key=sort_key))

    def test_the_sort_key_is_total(self):
        keys = [sort_key(r) for r in RECORDS]
        self.assertEqual(len(set(keys)), len(keys))

    def test_serialization_is_canonical(self):
        from vocab.artifact_io import dump_artifact_bytes

        with open(repo("candidate", "facilities.ng.v2.0.json"), "rb") as handle:
            committed = handle.read()
        self.assertEqual(committed, dump_artifact_bytes(CANDIDATE))
        self.assertFalse(committed.endswith(b"\n"))

    def test_generated_at_is_a_constant_not_a_clock(self):
        self.assertEqual(META["generated_at"], "2026-09-14T12:00:00Z")

    def test_the_geometry_query_is_order_independent(self):
        # The same query against an index built from reversed input must answer identically.
        reversed_geometry = G.StateGeometry(list(reversed(GEOMETRY.points)), GEOMETRY.unparseable_rows)
        for r in RECORDS[::500]:
            self.assertEqual(GEOMETRY.nearest(r["latitude"], r["longitude"]),
                             reversed_geometry.nearest(r["latitude"], r["longitude"]))


class SchemaTests(unittest.TestCase):
    def test_candidate_satisfies_its_schema(self):
        errors = schema_validate(CANDIDATE, load_json(repo("schema", "facilities.v2.schema.json")))
        self.assertEqual(errors, [], errors[:3])

    def test_schema_pins_the_unevidenced_fields_to_null(self):
        schema = load_json(repo("schema", "facilities.v2.schema.json"))
        props = schema["$defs"]["facility"]["properties"]
        self.assertEqual(props["type"]["type"], "null")
        self.assertEqual(props["emergency_capable"]["type"], "null")

    def test_schema_pins_coordinates_non_null_and_the_transformation_enum(self):
        props = load_json(repo("schema", "facilities.v2.schema.json"))["$defs"]["facility"]["properties"]
        self.assertEqual(props["latitude"]["type"], "number")
        self.assertEqual(props["longitude"]["type"], "number")
        self.assertEqual(props["source_record"]["properties"]["coordinate_transformation"]["enum"],
                         ["none", "swap_lat_lon"])

    def test_schema_pins_candidate_status_under_both_names(self):
        meta = load_json(repo("schema", "facilities.v2.schema.json"))["properties"]["_metadata"]
        self.assertEqual(meta["properties"]["release_status"]["const"], "candidate_unapproved")
        self.assertEqual(meta["properties"]["publication_status"]["const"], "candidate_unapproved")
        self.assertEqual(meta["properties"]["may_publish"]["const"], False)

    def test_schema_rejects_a_populated_type(self):
        broken = json.loads(json.dumps({"_metadata": META, "facilities": RECORDS[:1]}))
        broken["facilities"][0]["type"] = "hospital"
        errors = schema_validate(broken, load_json(repo("schema", "facilities.v2.schema.json")))
        self.assertTrue(any("type" in e for e in errors), errors[:3])

    def test_schema_rejects_a_null_coordinate_and_an_unknown_transformation(self):
        schema = load_json(repo("schema", "facilities.v2.schema.json"))
        broken = json.loads(json.dumps({"_metadata": META, "facilities": RECORDS[:1]}))
        broken["facilities"][0]["latitude"] = None
        self.assertTrue(any("latitude" in e for e in schema_validate(broken, schema)))
        broken = json.loads(json.dumps({"_metadata": META, "facilities": RECORDS[:1]}))
        broken["facilities"][0]["source_record"]["coordinate_transformation"] = "snapped"
        self.assertTrue(any("coordinate_transformation" in e for e in schema_validate(broken, schema)))


class NothingInventedTests(unittest.TestCase):
    """The guards. Each of these fails the moment someone fills a field the source cannot fill."""

    def test_type_is_null_everywhere(self):
        self.assertTrue(all(r["type"] is None for r in RECORDS))
        self.assertEqual(M.FACILITY_TYPE_FROM_LEVEL, {})

    def test_a_null_type_cannot_be_mistaken_for_a_supported_category(self):
        self.assertNotIn(None, M.FACILITY_TYPES)
        self.assertNotIn("null", M.FACILITY_TYPES)
        self.assertNotIn("unknown", M.FACILITY_TYPES)
        self.assertEqual(META["unresolved_fields"]["type_vocabulary"], list(M.FACILITY_TYPES))
        self.assertEqual(QUALITY["categorical_counts"]["type"], {"null": len(RECORDS)})
        # The consumer contract is stated in the artifact itself, not only in a document.
        self.assertIn("must not be filtered out", META["unresolved_fields"]["consumer_contract"])
        self.assertIn("empty result list", META["unresolved_fields"]["consumer_contract"])

    def test_emergency_capable_is_null_everywhere_and_no_record_is_verified_positive(self):
        self.assertTrue(all(r["emergency_capable"] is None for r in RECORDS))
        self.assertFalse(any(r["emergency_capable"] is True for r in RECORDS))
        self.assertIsNone(M.EMERGENCY_CAPABLE_RULE)

    def test_service_flags_are_bound_to_source_columns_and_nothing_else(self):
        for r in RECORDS:
            self.assertEqual(set(r["services"]), set(M.SERVICES_SOURCE_COLUMNS))
        self.assertNotIn("emergency", " ".join(M.SERVICES_SOURCE_COLUMNS))

    def test_placeholder_phones_never_become_real_numbers(self):
        for junk in ("0", "8000000000", "99999999999", "1111111111", "0000000000"):
            value, reason = phone(junk)
            self.assertIsNone(value, junk)
            self.assertIsNotNone(reason, junk)

    def test_no_absent_value_became_false_or_zero(self):
        for r in RECORDS:
            for v in r["services"].values():
                self.assertIn(v, (True, False, None))
            self.assertTrue(r["beds"] is None or r["beds"] >= 0)

    def test_missing_and_unknown_are_different(self):
        statuses = {r["operational_status"] for r in RECORDS}
        self.assertIn("unknown", statuses)
        self.assertIn(None, statuses)
        self.assertIn("null", META["absence_convention"])

    def test_unmapped_values_are_reported_not_guessed(self):
        unmapped = META["unmapped_source_values"]
        self.assertIn("operational_hours", unmapped)
        self.assertIn("124_Hours", unmapped["operational_hours"])
        self.assertNotIn("124_hours", {r["opening_hours"] for r in RECORDS})

    def test_facility_type_id_is_evidence_not_a_mapping(self):
        crosstab = QUALITY["source_evidence"]["facility_type_id_by_level_and_ownership"]
        self.assertTrue(crosstab)
        self.assertNotIn("facility_type_id", json.dumps(RECORDS))


class CoordinateOrientationTests(unittest.TestCase):
    """The remediation rule. It exchanges under one strict condition and never otherwise."""

    KANO_TRANSPOSED = (8.5920, 12.0022)   # Kano city written the wrong way round
    LAGOS = (6.6018, 3.3515)

    def test_a_northern_transposition_inside_the_box_is_corrected_under_the_strict_rule(self):
        outcome, evidence, given, exchanged = GEOMETRY.orientation(*self.KANO_TRANSPOSED, "Kano")
        self.assertEqual(outcome, G.ACCEPTED_AFTER_SWAP)
        self.assertIn(given, (G.OUTSIDE, G.OUT_OF_BOX))
        self.assertEqual(exchanged, G.INSIDE_STRICT)

    def test_a_genuine_point_is_accepted_unchanged(self):
        outcome, evidence, given, _ = GEOMETRY.orientation(*self.LAGOS, "Lagos")
        self.assertEqual(outcome, G.ACCEPTED_UNCHANGED)
        self.assertEqual(given, G.INSIDE_STRICT)

    def test_a_point_outside_its_state_both_ways_is_invalid(self):
        # Kano city, as given AND exchanged, is nowhere near Lagos.
        outcome, evidence, _, _ = GEOMETRY.orientation(12.0022, 8.5920, "Lagos")
        self.assertEqual(outcome, G.QUARANTINED_INVALID)

    def test_both_orientations_plausible_is_ambiguous_not_a_guess(self):
        # A point on the diagonal is its own transpose: both readings are inside the state.
        la, lo = M.STATE_REFERENCE_POINTS["Nasarawa"]
        near = GEOMETRY.nearest(la, lo, k=1)
        self.assertTrue(near)
        # Find an emitted Nasarawa record and use a symmetric point near it.
        for r in RECORDS:
            if r["state"] == "Nasarawa":
                mid = (r["latitude"] + r["longitude"]) / 2
                outcome, evidence, given, exchanged = GEOMETRY.orientation(mid, mid, "Nasarawa")
                if given == G.INSIDE_STRICT:
                    self.assertEqual(outcome, G.ACCEPTED_UNCHANGED)   # the source's reading stands
                else:
                    self.assertIn(outcome, (G.QUARANTINED_AMBIGUOUS, G.QUARANTINED_INVALID))
                break

    def test_the_membership_words_are_the_only_words(self):
        for r in RECORDS[::300]:
            self.assertIn(GEOMETRY.membership(r["latitude"], r["longitude"], r["state"]),
                          (G.INSIDE_STRICT, G.INSIDE_MAJORITY, G.OUTSIDE, G.UNCERTAIN))
        self.assertEqual(GEOMETRY.membership(20.0, 20.0, "Lagos"), G.OUT_OF_BOX)

    def test_no_accepted_record_lies_outside_its_declared_state(self):
        # Full re-verification is in the validator; a fixed stride here keeps the suite fast.
        for r in RECORDS[::25]:
            given = GEOMETRY.membership(r["latitude"], r["longitude"], r["state"])
            if given == G.INSIDE_STRICT:
                continue
            exchanged = GEOMETRY.membership(r["longitude"], r["latitude"], r["state"])
            self.assertEqual(given, G.INSIDE_MAJORITY, r["facility_id"])
            self.assertIn(exchanged, (G.OUTSIDE, G.OUT_OF_BOX), r["facility_id"])

    def test_every_correction_satisfies_the_strict_swap_rule(self):
        self.assertTrue(CORRECTED)
        for r in CORRECTED:
            s = r["source_record"]
            self.assertEqual(s["coordinate_transformation"], "swap_lat_lon")
            self.assertEqual((r["latitude"], r["longitude"]), (s["source_longitude"], s["source_latitude"]))
        for r in CORRECTED[::25]:
            s = r["source_record"]
            self.assertIn(GEOMETRY.membership(s["source_latitude"], s["source_longitude"], r["state"]),
                          (G.OUTSIDE, G.OUT_OF_BOX), r["facility_id"])
            self.assertEqual(GEOMETRY.membership(r["latitude"], r["longitude"], r["state"]),
                             G.INSIDE_STRICT, r["facility_id"])

    def test_uncorrected_records_carry_no_source_pair_and_corrected_ones_keep_it(self):
        for r in RECORDS:
            s = r["source_record"]
            if s["coordinate_transformation"] == "none":
                self.assertIsNone(s["source_latitude"]); self.assertIsNone(s["source_longitude"])
            else:
                self.assertIsNotNone(s["source_latitude"]); self.assertIsNotNone(s["source_longitude"])

    def test_ambiguous_coordinates_remain_quarantined(self):
        ambiguous = [q for q in QUARANTINE["rows"] if q["reason_code"] == "coordinates_orientation_ambiguous"]
        self.assertEqual(len(ambiguous), 1442)
        self.assertEqual(META["coordinate_remediation"]["quarantined_ambiguous"], 1442)
        self.assertEqual(AUDIT["outcomes"][G.QUARANTINED_AMBIGUOUS], 1442)
        emitted = {r["source_record"]["source_id"] for r in RECORDS}
        self.assertFalse({q["source_id"] for q in ambiguous} & emitted)
        for q in ambiguous[:20]:
            self.assertIn("as_given", q); self.assertIn("exchanged", q)

    def test_invalid_coordinates_remain_quarantined(self):
        invalid = [q for q in QUARANTINE["rows"] if q["reason_code"] == "coordinates_not_in_state"]
        self.assertEqual(len(invalid), 67)
        self.assertEqual(META["coordinate_remediation"]["quarantined_invalid"], 67)

    def test_transformations_are_fully_counted(self):
        self.assertEqual(AUDIT["outcomes"][G.ACCEPTED_UNCHANGED], 18210)
        self.assertEqual(AUDIT["outcomes"][G.ACCEPTED_AFTER_SWAP], 11141)
        self.assertEqual(len(AUDIT["corrections"]), 11141)
        self.assertEqual(len(CORRECTED), 10862)
        self.assertEqual(META["coordinate_remediation"]["records_corrected_in_artifact"], 10862)
        self.assertEqual(AUDIT["records_corrected_in_artifact"], 10862)
        # Every orientable row landed in exactly one of the four outcomes.
        self.assertEqual(sum(AUDIT["outcomes"][k] for k in (
            G.ACCEPTED_UNCHANGED, G.ACCEPTED_AFTER_SWAP, G.QUARANTINED_AMBIGUOUS, G.QUARANTINED_INVALID))
            + AUDIT["outcomes"]["not_orientable_missing_or_zero"] + 1,   # + the one empty-name row
            QUALITY["row_accounting"]["source_rows"])

    def test_every_correction_in_the_artifact_is_in_the_audit_with_its_source_values(self):
        audited = {c["source_id"]: c for c in AUDIT["corrections"]}
        for r in CORRECTED:
            c = audited[r["source_record"]["source_id"]]
            self.assertEqual(c["source_latitude"], r["source_record"]["source_latitude"])
            self.assertEqual(c["latitude"], r["latitude"])
            self.assertEqual(c["evidence"], "as_given_outside_exchanged_inside_strict")

    def test_the_rule_moved_nothing_it_did_not_exchange(self):
        self.assertEqual(META["coordinate_remediation"]["rule_id"], G.RULE_ID)
        self.assertTrue(all(r["source_record"]["coordinate_transformation"] in ("none", "swap_lat_lon")
                            for r in RECORDS))
        self.assertNotIn("snap", json.dumps(AUDIT["algorithm"]))

    def test_the_calibration_and_corroboration_are_recorded(self):
        cal = AUDIT["calibration_on_grid3_itself"]
        self.assertGreater(cal["membership"][G.INSIDE_STRICT], 0.9 * cal["points"])
        corr = AUDIT["grid3_record_level_corroboration"]["by_outcome"][G.ACCEPTED_AFTER_SWAP]
        self.assertGreater(corr["grid3_same_facility_within_20km_of_emitted_pair"],
                           100 * corr["grid3_same_facility_within_20km_of_other_pair"])

    def test_the_bounding_box_refusal_is_no_longer_a_silent_reason(self):
        # coordinate() still refuses a southern transposition on its own; the pipeline now
        # asks the orientation rule instead, so the old reason codes must not appear.
        self.assertEqual(coordinate("6.45744", "3.36831")[2], "coordinates_swapped_suspected")
        self.assertNotIn("coordinates_swapped_suspected", QUARANTINE["by_reason"])
        self.assertNotIn("coordinates_swapped_suspected_by_state", QUARANTINE["by_reason"])
        self.assertEqual(parse_coordinates("6.45744", "3.36831")[2], None)
        self.assertEqual(parse_coordinates("", "")[2], "coordinates_absent")
        self.assertEqual(parse_coordinates("0", "0")[2], "coordinates_null_island")


class CoveragePreservationTests(unittest.TestCase):
    COMPARE = load_json(repo("reports", "facilities_comparison_v1.json"))
    COMPAT = load_json(repo("reports", "facilities_mobile_compat_v1.json"))

    def test_no_facilities_1_1_state_disappears(self):
        self.assertEqual(self.COMPARE["states_lost"], [])
        self.assertEqual(META["states_with_no_emitted_records"], [])
        self.assertEqual(QUALITY["differences_from_facilities_1_1"]["states_in_1_1_absent_from_candidate"], [])

    def test_a_lost_1_1_state_would_be_a_blocking_failure(self):
        import report_facilities_comparison as cmp

        current = {"facilities": [{"facility_id": "ng_abj_001", "name": "A", "type": "hospital",
                                   "state": "FCT", "city_area": "X", "latitude": 9.0, "longitude": 7.3,
                                   "phone": None, "opening_hours": None, "emergency_capable": True}]}
        candidate = {"facilities": [dict(RECORDS[0], state="Lagos")]}
        report = cmp.mobile_compat(current, candidate)
        blocking = [f for f in report["blocking_findings"] if f["severity"] == "blocking"]
        self.assertTrue(any("FCT" in f["finding"] for f in blocking))

    def test_the_previously_empty_states_are_recovered(self):
        by_state = {e["state"]: e for e in AUDIT["coverage_by_state"]}
        for state, minimum in (("FCT", 600), ("Kano", 1200), ("Katsina", 400), ("Kwara", 700),
                               ("Niger", 650), ("Taraba", 900), ("Zamfara", 170)):
            self.assertGreaterEqual(by_state[state]["candidate"], minimum, state)
            self.assertEqual(by_state[state]["candidate_without_correction"], 0, state)
        self.assertEqual(by_state["FCT"]["candidate"], 632)
        self.assertEqual(by_state["Kano"]["candidate"], 1293)

    def test_the_coverage_table_covers_every_state_and_reconciles(self):
        table = AUDIT["coverage_by_state"]
        self.assertEqual([e["state"] for e in table], sorted(set(M.NIGERIA_STATES) | {M.FCT_NAME}))
        self.assertEqual(sum(e["candidate"] for e in table), len(RECORDS))
        for e in table:
            self.assertEqual(e["source_rows"], e["accepted_unchanged"] + e["accepted_after_verified_swap"]
                             + e["quarantined_ambiguous"] + e["quarantined_invalid"]
                             + e["quarantined_missing_coordinates"], e["state"])
            self.assertEqual(e["candidate"], e["accepted_unchanged"] + e["accepted_after_verified_swap"]
                             - e["quarantined_duplicate"], e["state"])

    def test_by_location_queries_return_results_in_fct_and_kano(self):
        for key in ("Kano / Ajingi", "FCT / Abuja Municipal Area Council"):
            self.assertGreater(self.COMPAT["by_location_probe_results"][key]["emergency"]["candidate"], 0)

    def test_option_b_overlay_is_quantified_and_not_applied(self):
        overlay = self.COMPARE["option_b_overlay_analysis"]
        self.assertFalse(any(v["overlay_needed_for_coverage"] for v in overlay["by_1_1_state"].values()))
        self.assertIn("Not applied", overlay["conclusion"])
        self.assertEqual(set(overlay["by_1_1_state"]), {"Lagos", "FCT", "Kano"})

    def test_the_states_absent_from_the_source_are_named(self):
        self.assertEqual(META["states_absent"], ["Adamawa", "Kebbi", "Sokoto"])
        self.assertIn("NOT nationwide", META["coverage_claim"])


class DeduplicationTests(unittest.TestCase):
    def _record(self, uid, sid, name="Mercy Hospital", lon=7.0, lat=5.0, phone_=None):
        return {"name": name, "state": "Abia", "city_area": "Aba North", "longitude": lon,
                "latitude": lat, "phone": phone_, "facility_id": "ng_nhf_%s" % sid,
                "source_record": {"source_unique_id": uid, "source_id": sid}}

    def test_the_rule_is_exact_and_documented(self):
        self.assertEqual(META["deduplication"]["rule_id"], "exact_match_v1")
        self.assertIs(META["deduplication"]["values_merged"], False)
        self.assertEqual(META["deduplication"]["rows_removed"], 323)
        self.assertEqual(META["deduplication"]["groups_collapsed"], 322)

    def test_no_exact_duplicate_remains(self):
        keys = [duplicate_key(r) for r in RECORDS]
        self.assertEqual(len(set(keys)), len(keys))

    def test_survivor_is_the_smallest_registry_id_regardless_of_input_order(self):
        import build_facilities_candidate as gen

        a = self._record("01/01/1/2/2/0010", "9", phone_="+2348000000001")
        b = self._record("01/01/1/2/2/0009", "5", phone_="+2348000000002")
        for order in ((a, b), (b, a)):
            survivors, dedup = gen.deduplicate(list(order))
            self.assertEqual([s["source_record"]["source_id"] for s in survivors], ["5"])
            self.assertEqual(dedup["rows_removed"], 1)
            self.assertEqual(survivors[0]["phone"], "+2348000000002")

    def test_near_duplicates_are_not_collapsed(self):
        import build_facilities_candidate as gen

        base = self._record("01/01/1/2/2/0009", "5")
        survivors, dedup = gen.deduplicate([
            base, self._record("01/01/1/2/2/0011", "7", lon=7.001),
            self._record("01/01/1/2/2/0012", "8", name="Mercy Pharmacy")])
        self.assertEqual(len(survivors), 3)
        self.assertEqual(dedup["rows_removed"], 0)

    def test_every_removed_row_names_a_survivor_in_the_candidate(self):
        ids = {r["facility_id"] for r in RECORDS}
        removed = [q for q in QUARANTINE["rows"] if q["reason_code"] == "duplicate_exact_match"]
        self.assertEqual(len(removed), 323)
        for q in removed:
            self.assertIn(q["survivor_facility_id"], ids)
            self.assertNotIn("ng_nhf_%s" % q["source_id"], ids)


class NormalizationTests(unittest.TestCase):
    def test_unicode_and_whitespace_are_normalised(self):
        self.assertEqual(text("  Sauki  Clinic \t"), "Sauki Clinic")
        self.assertEqual(text("Café"), text("Café"))

    def test_casing_is_preserved_not_rewritten(self):
        self.assertEqual(text("PHC OGBA"), "PHC OGBA")

    def test_placeholder_tokens_become_absent(self):
        for token in ("Nil", "NIL", "nill", "N/A", "-", "0", "none", ""):
            self.assertIsNone(text(token), token)

    def test_phone_normalisation_accepts_the_forms_the_source_uses(self):
        for raw in ("8060823195", "08060823195", "+2348060823195", "234 806 082 3195"):
            self.assertEqual(phone(raw)[0], "+2348060823195", raw)

    def test_phone_rejects_non_nigerian_mobiles(self):
        for raw in ("+14155552671", "012345678", "1", "abc"):
            self.assertIsNone(phone(raw)[0], raw)

    def test_contact_details_in_free_text_are_removed(self):
        self.assertEqual(free_text("mussdoctor71@gmail.com"), (None, "contact_detail_in_free_text_field"))
        self.assertEqual(free_text("http://www.example.com"), (None, "url_in_free_text_field"))
        self.assertEqual(free_text("1B Faulks Road")[0], "1B Faulks Road")

    def test_source_timestamps_become_iso_8601_without_a_zone(self):
        self.assertEqual(timestamp("2026-06-08 11:13:17"), ("2026-06-08T11:13:17", None))
        self.assertEqual(timestamp(""), (None, "timestamp_absent"))
        self.assertEqual(timestamp("8 June 2026"), (None, "timestamp_unparseable"))

    def test_the_survivor_key_is_total_over_the_candidate(self):
        keys = [survivor_key(r) for r in RECORDS]
        self.assertEqual(len(set(keys)), len(keys))


class PrivacyTests(unittest.TestCase):
    def test_no_email_address_survives_into_any_record(self):
        self.assertEqual(EMAIL.findall(json.dumps(RECORDS)), [])

    def test_the_free_text_scrub_is_in_force(self):
        self.assertEqual(free_text("someone@example.com"), (None, "contact_detail_in_free_text_field"))
        self.assertEqual(EMAIL.findall(json.dumps(QUARANTINE)), [])
        self.assertEqual(EMAIL.findall(json.dumps(AUDIT)), [])

    def test_excluded_source_columns_appear_in_no_record(self):
        text_ = json.dumps(RECORDS)
        for column in ("email_address", "alternate_number", "verified_email", "published_mobile",
                       "created_by", "verified_by"):
            self.assertNotIn('"%s"' % column, text_, column)

    def test_no_user_health_search_or_location_history_key_exists(self):
        import validate_facilities_candidate as v

        keys = v._keys(CANDIDATE, set())
        self.assertEqual([k for k in keys if set(k.lower().split("_")) & v.PROHIBITED_KEY_TOKENS], [])

    def test_the_artifact_carries_only_facility_attributes(self):
        allowed = {"facility_id", "name", "type", "state", "city_area", "latitude", "longitude",
                   "phone", "opening_hours", "emergency_capable", "lga", "ward", "address",
                   "facility_level", "ownership", "ownership_type", "operational_status",
                   "registration_status", "license_status", "beds", "services", "source_record"}
        for r in RECORDS:
            self.assertEqual(set(r), allowed)


class IntegrityTests(unittest.TestCase):
    def test_facility_ids_are_unique(self):
        ids = [r["facility_id"] for r in RECORDS]
        self.assertEqual(len(set(ids)), len(ids))

    def test_candidate_ids_cannot_collide_with_facilities_1_1(self):
        old = {r["facility_id"] for r in load_json(repo("facilities.ng.v1.1.json"))["facilities"]}
        self.assertEqual(old & {r["facility_id"] for r in RECORDS}, set())

    def test_every_row_is_either_emitted_or_quarantined(self):
        self.assertTrue(QUALITY["row_accounting"]["balances"])
        self.assertEqual(QUALITY["row_accounting"]["source_rows"], 31390)
        self.assertEqual(QUALITY["row_accounting"]["emitted"], len(RECORDS))
        self.assertEqual(len(RECORDS), 29028)

    def test_quarantine_is_deterministic_and_reasoned(self):
        rows = QUARANTINE["rows"]
        self.assertEqual(rows, sorted(rows, key=lambda q: (q["reason_code"], q["source_line"])))
        for row in rows:
            self.assertIn(row["reason_code"], QUARANTINE["reason_codes"])

    def test_emitted_coordinates_are_inside_nigeria(self):
        for r in RECORDS:
            self.assertTrue(NIGERIA_MIN_LAT <= r["latitude"] <= NIGERIA_MAX_LAT)
            self.assertTrue(NIGERIA_MIN_LON <= r["longitude"] <= NIGERIA_MAX_LON)

    def test_rows_without_coordinates_are_quarantined_with_their_reason(self):
        self.assertEqual(QUARANTINE["by_reason"]["coordinates_absent"], 524)
        self.assertEqual(QUALITY["missingness_rates"]["coordinates"]["count"], 0)

    def test_no_empty_names(self):
        self.assertTrue(all(r["name"].strip() for r in RECORDS))

    def test_lga_id_is_name_scoped_and_said_so(self):
        names = {e["lga_name"] for e in QUALITY["source_evidence"]["lga_ids_spanning_multiple_states"]}
        for homonym in ("Nasarawa", "Obi", "Ifelodun", "Irepodun", "Surulere", "Bassa"):
            self.assertIn(homonym, names)
        pairs = {}
        for r in RECORDS:
            pairs.setdefault((r["state"], r["city_area"]), set()).add(r["source_record"]["lga_id"])
        self.assertTrue(all(len(v) == 1 for v in pairs.values()))


class MobileCompatibilityTests(unittest.TestCase):
    """Measured against a port of the real consumer, not asserted."""

    COMPAT = load_json(repo("reports", "facilities_mobile_compat_v1.json"))

    def test_every_field_mobile_reads_is_present_on_every_record(self):
        self.assertTrue(self.COMPAT["required_field_presence"]["all_present_in_candidate"])

    def test_the_type_gap_is_the_only_blocking_finding(self):
        blocking = [f["finding"] for f in self.COMPAT["blocking_findings"] if f["severity"] == "blocking"]
        self.assertEqual(len(blocking), 1)
        self.assertIn("type is null", blocking[0])

    def test_non_emergency_queries_return_nothing_in_the_current_build_and_that_is_recorded(self):
        for probe in self.COMPAT["nearby_probe_results"].values():
            for urgency in ("urgent", "non_urgent", "self_care"):
                self.assertTrue(probe[urgency]["candidate_returns_nothing"])
        self.assertIn("must not be filtered out", self.COMPAT["type_and_null_handling"]["mobile_null_type_handling"])

    def test_emergency_queries_still_return_results(self):
        for probe in self.COMPAT["nearby_probe_results"].values():
            self.assertGreater(probe["emergency"]["candidate_results"], 0)

    def test_the_verdict_is_not_compatible(self):
        self.assertIn("NOT COMPATIBLE", self.COMPAT["verdict"])

    def test_mobile_repository_was_not_modified(self):
        self.assertFalse(self.COMPAT["_metadata"]["mobile_repository_modified"])


class SourceAuthorizationTests(unittest.TestCase):
    def test_every_item_is_missing_and_may_publish_is_false(self):
        self.assertEqual({i["status"] for i in CHECKLIST["items"]}, {"missing"})
        self.assertIs(CHECKLIST["all_satisfied"], False)
        self.assertIs(META["may_publish"], False)
        self.assertEqual(len(CHECKLIST["items"]), 9)

    def test_the_checklist_binds_to_the_pinned_source(self):
        self.assertEqual(CHECKLIST["_metadata"]["applies_to"]["source_sha256"], SOURCE_SHA256)

    def test_the_manifest_reports_the_missing_items(self):
        self.assertEqual(MANIFEST["source_authorization"]["items_missing"],
                         sorted(i["id"] for i in CHECKLIST["items"]))
        self.assertIs(MANIFEST["publication_gates"]["source_authorization_checklist_satisfied"], False)


class ManifestTests(unittest.TestCase):
    def test_the_manifest_is_not_live_and_grants_nothing(self):
        self.assertIs(MANIFEST["IS_LIVE_MANIFEST"], False)
        self.assertIs(MANIFEST["candidate_artifact"]["may_publish"], False)
        self.assertTrue(all(v is False for v in MANIFEST["publication_gates"].values()))

    def test_the_manifest_describes_the_bytes_on_disk(self):
        path = repo("candidate", "facilities.ng.v2.0.json")
        self.assertEqual(MANIFEST["candidate_artifact"]["sha256"], sha256_file(path))
        self.assertEqual(MANIFEST["candidate_artifact"]["bytes"], os.path.getsize(path))
        self.assertEqual(MANIFEST["candidate_artifact"]["record_count"], len(RECORDS))
        self.assertEqual(MANIFEST["pipeline_accounting"]["coordinate_remediation"]["accepted_after_verified_swap"], 11141)

    def test_the_manifest_binds_rollback_to_1_1_by_hash(self):
        self.assertEqual(MANIFEST["rollback"]["target_file"], "facilities.ng.v1.1.json")
        self.assertEqual(MANIFEST["rollback"]["target_sha256"], CURRENT_SHA256)

    def test_the_manifest_is_reproducible(self):
        import build_facilities_manifest as gen
        from vocab.artifact_io import dump_report_bytes

        with open(repo("candidate", "facilities.manifest.candidate.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_report_bytes(gen.build()))


class DocumentationTests(unittest.TestCase):
    DIGEST = sha256_file(repo("candidate", "facilities.ng.v2.0.json"))

    def _text(self, *parts):
        with open(repo(*parts), encoding="utf-8") as handle:
            return handle.read()

    def test_the_changelog_cites_the_current_candidate(self):
        text_ = self._text("docs", "FACILITIES_2_0_CHANGELOG.md")
        self.assertIn(self.DIGEST, text_)
        self.assertIn("{:,}".format(len(RECORDS)), text_)
        self.assertIn(CURRENT_SHA256, text_)

    def test_the_mobile_handoff_cites_the_current_candidate_and_every_field(self):
        text_ = self._text("mobile_handoff", "facilities_v2", "README.md")
        self.assertIn(self.DIGEST, text_)
        self.assertIn("{:,}".format(len(RECORDS)), text_)
        for field in RECORDS[0]:
            self.assertIn("`%s`" % field, text_, field)
        for field in RECORDS[0]["source_record"]:
            self.assertIn("`source_record.%s`" % field, text_, field)

    def test_the_handoff_states_the_null_type_and_emergency_contract(self):
        text_ = self._text("mobile_handoff", "facilities_v2", "README.md")
        for phrase in ("must not be filtered out", "never create an empty result list",
                       "verified positive evidence", "Product/Clinical fallback decision",
                       "Adamawa, Kebbi", "not established", "tel:", "lga_id", "swap_lat_lon"):
            self.assertIn(phrase, text_, phrase)

    def test_the_remediation_study_and_decision_documents_exist_and_cite_the_counts(self):
        study = self._text("docs", "FACILITIES_COORDINATE_REMEDIATION.md")
        for token in ("18,210", "11,141", "1,442", "67", G.RULE_ID, "Option C"):
            self.assertIn(token, study, token)
        decisions = self._text("docs", "FACILITIES_DECISIONS_REQUIRED.md")
        self.assertIn("FAC-D001", decisions)
        checklist_doc = self._text("docs", "FACILITIES_SOURCE_AUTHORIZATION_CHECKLIST.md")
        for item in CHECKLIST["items"]:
            self.assertIn(item["id"], checklist_doc)

    def test_the_dart_types_fail_closed_on_unknown_enums(self):
        text_ = self._text("mobile_handoff", "facilities_v2", "facility_types.dart")
        self.assertIn("return null;", text_)
        self.assertIn("CANDIDATE", text_)


class CandidateStatusTests(unittest.TestCase):
    PLAN = load_json(repo("publication", "plans", "facilities.ng.v2.0.dryrun.json"))

    def test_the_artifact_is_an_unapproved_candidate(self):
        self.assertEqual(META["release_status"], "candidate_unapproved")
        self.assertEqual(META["publication_status"], "candidate_unapproved")
        self.assertIs(META["may_publish"], False)
        self.assertIsNone(META["release_date"])

    def test_licence_is_recorded_as_not_established(self):
        self.assertIsNone(META["source"]["licence"])
        self.assertIsNone(META["source"]["organization"])

    def test_the_publication_tooling_still_blocks_activation(self):
        operations = self.PLAN["operations_performed"]
        for flag in ("upload_performed", "publication_performed", "activation_performed",
                     "deployment_performed"):
            self.assertIs(operations[flag], False, flag)
        self.assertIs(self.PLAN["eligible_in_any_environment"], False)
        self.assertIs(self.PLAN["descriptor"]["activation_authorized"], False)
        self.assertEqual(self.PLAN["descriptor"]["activation_status"], "inactive")
        self.assertIs(self.PLAN["conclusion"]["publishable"], False)
        self.assertIs(self.PLAN["conclusion"]["activatable"], False)
        for role in ("product", "clinical"):
            self.assertEqual(self.PLAN["descriptor"]["approvals"][role]["status"], "pending")

    def test_the_dry_run_plan_describes_the_current_bytes(self):
        self.assertEqual(self.PLAN["descriptor"]["sha256"],
                         "sha256:%s" % sha256_file(repo("candidate", "facilities.ng.v2.0.json")))

    def test_the_candidate_is_not_at_the_published_root(self):
        self.assertFalse(os.path.exists(repo("facilities.ng.v2.0.json")))


class FrozenArtifactTests(unittest.TestCase):
    def test_facilities_1_1_is_byte_identical(self):
        self.assertEqual(sha256_file(repo("facilities.ng.v1.1.json")), CURRENT_SHA256)

    def test_facilities_1_0_is_byte_identical(self):
        self.assertEqual(sha256_file(repo("facilities.ng.v1.0.json")), V1_0_SHA256)

    def test_building_the_candidate_touches_no_frozen_artifact(self):
        import build_facilities_candidate as gen

        before = (sha256_file(repo("facilities.ng.v1.1.json")), sha256_file(repo("facilities.ng.v1.0.json")))
        gen.build()
        self.assertEqual((sha256_file(repo("facilities.ng.v1.1.json")),
                          sha256_file(repo("facilities.ng.v1.0.json"))), before)


class OfflineSafetyTests(unittest.TestCase):
    def test_the_generator_performs_no_network_or_stray_write(self):
        import tempfile

        from pubkit.safety import no_side_effects

        import build_facilities_candidate as gen

        with tempfile.TemporaryDirectory() as directory:
            with no_side_effects(allowed_write_roots=(directory,), raise_on_attempt=True) as guard:
                gen.build()
            self.assertEqual(guard.attempts, [])

    def test_the_generators_import_no_cloud_sdk_or_http_client(self):
        for name in ("build_facilities_candidate.py", "build_facilities_manifest.py",
                     "report_facilities_comparison.py", "validate_facilities_candidate.py",
                     os.path.join("facilities", "geometry.py")):
            with open(os.path.join(ROOT, "tools", name), encoding="utf-8") as handle:
                source = handle.read()
            for banned in ("import requests", "import urllib.request", "boto3", "urlopen", "httpx"):
                self.assertNotIn(banned, source, "%s: %s" % (name, banned))


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
