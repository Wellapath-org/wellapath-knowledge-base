#!/usr/bin/env python3
"""Tests for the nationwide facilities candidate.

    python3 testing/facilities/test_facilities.py [-v]

The tests that matter most are the ones guarding what the generator refuses to do. Anyone can
write a transformation that fills every field; the value here is that `type` and
`emergency_capable` stay null, that a coordinate pair is never silently swapped or invented,
that a placeholder phone never becomes a real one, that a personal email typed into an address
field does not travel onward, and that the duplicate rule collapses only what it says it does.
Each of those has a test that fails if the guard is removed.
"""

import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from facilities import mappings as M  # noqa: E402
from facilities.normalize import (NIGERIA_MAX_LAT, NIGERIA_MAX_LON, NIGERIA_MIN_LAT,  # noqa: E402
                                  NIGERIA_MIN_LON, coordinate, coordinate_vs_state,
                                  duplicate_key, free_text, haversine_km, phone, sort_key,
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
MANIFEST = load_json(repo("candidate", "facilities.manifest.candidate.json"))
SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"
CURRENT_SHA256 = "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class SourceIntegrityTests(unittest.TestCase):
    def test_source_bytes_match_the_pin(self):
        self.assertEqual(
            sha256_file(repo("facilities", "source", "nigeria_health_facilities.csv")),
            SOURCE_SHA256,
        )

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

    def test_provenance_records_what_is_not_established(self):
        p = load_json(repo("facilities", "source", "nhf_provenance_v1.json"))
        self.assertFalse(p["source_organization"]["established"])
        self.assertFalse(p["licence"]["established"])
        self.assertFalse(p["contact_fields_public_use"]["established"])
        self.assertIsNone(p["source_organization"]["recorded_name"])
        self.assertEqual(p["geographic_scope"]["states_absent"], ["Adamawa", "Kebbi", "Sokoto"])

    def test_the_source_snapshot_instant_is_carried_without_a_zone_claim(self):
        self.assertEqual(META["source"]["snapshot_last_updated_at"], "2026-07-21T13:15:26")
        self.assertIsNone(META["source"]["snapshot_declared_version"])
        self.assertFalse(META["source"]["snapshot_last_updated_at"].endswith("Z"))


class DeterminismTests(unittest.TestCase):
    def test_regeneration_is_byte_identical(self):
        import build_facilities_candidate as gen
        from vocab.artifact_io import dump_artifact_bytes, dump_report_bytes

        artifact, quality, quarantine = gen.build()
        with open(repo("candidate", "facilities.ng.v2.0.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_artifact_bytes(artifact))
        with open(repo("reports", "facilities_quality_v1.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_report_bytes(quality))
        with open(repo("reports", "facilities_quarantine_v1.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_report_bytes(quarantine))

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
        self.assertEqual(META["generated_at"], "2026-09-14T00:00:00Z")


class SchemaTests(unittest.TestCase):
    def test_candidate_satisfies_its_schema(self):
        errors = schema_validate(CANDIDATE, load_json(repo("schema", "facilities.v2.schema.json")))
        self.assertEqual(errors, [], errors[:3])

    def test_schema_pins_the_unevidenced_fields_to_null(self):
        schema = load_json(repo("schema", "facilities.v2.schema.json"))
        props = schema["$defs"]["facility"]["properties"]
        self.assertEqual(props["type"]["type"], "null")
        self.assertEqual(props["emergency_capable"]["type"], "null")

    def test_schema_pins_coordinates_non_null(self):
        props = load_json(repo("schema", "facilities.v2.schema.json"))["$defs"]["facility"]["properties"]
        self.assertEqual(props["latitude"]["type"], "number")
        self.assertEqual(props["longitude"]["type"], "number")

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

    def test_schema_rejects_a_null_coordinate(self):
        broken = json.loads(json.dumps({"_metadata": META, "facilities": RECORDS[:1]}))
        broken["facilities"][0]["latitude"] = None
        errors = schema_validate(broken, load_json(repo("schema", "facilities.v2.schema.json")))
        self.assertTrue(any("latitude" in e for e in errors), errors[:3])


class NothingInventedTests(unittest.TestCase):
    """The guards. Each of these fails the moment someone fills a field the source cannot fill."""

    def test_type_is_null_everywhere(self):
        self.assertTrue(all(r["type"] is None for r in RECORDS))
        self.assertEqual(M.FACILITY_TYPE_FROM_LEVEL, {})

    def test_the_type_vocabulary_is_declared_but_not_applied(self):
        self.assertEqual(META["unresolved_fields"]["type_vocabulary"], list(M.FACILITY_TYPES))
        self.assertIn("other", M.FACILITY_TYPES)
        self.assertEqual(QUALITY["categorical_counts"]["type"], {"null": len(RECORDS)})

    def test_emergency_capable_is_null_everywhere(self):
        self.assertTrue(all(r["emergency_capable"] is None for r in RECORDS))
        self.assertIsNone(M.EMERGENCY_CAPABLE_RULE)

    def test_service_flags_are_bound_to_source_columns_and_nothing_else(self):
        for r in RECORDS:
            self.assertEqual(set(r["services"]), set(M.SERVICES_SOURCE_COLUMNS))
        self.assertNotIn("emergency", " ".join(M.SERVICES_SOURCE_COLUMNS))

    def test_a_suspected_swapped_coordinate_is_never_swapped(self):
        # Lagos is 6.45N 3.36E. Given the other way round it is implausible, and the fix is
        # to refuse it, not to guess which of the two fields the source got wrong.
        lon, lat, reason = coordinate("6.45744", "3.36831")
        self.assertIsNone(lon)
        self.assertIsNone(lat)
        self.assertEqual(reason, "coordinates_swapped_suspected")
        self.assertIn("coordinates_swapped_suspected", QUARANTINE["by_reason"])

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
        self.assertIn("unknown", statuses)   # the source explicitly said Unknown
        self.assertIn(None, statuses)        # the source said nothing at all
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


class CoordinatePolicyTests(unittest.TestCase):
    def test_every_emitted_record_has_both_coordinates(self):
        for r in RECORDS:
            self.assertIsNotNone(r["latitude"], r["facility_id"])
            self.assertIsNotNone(r["longitude"], r["facility_id"])

    def test_rows_without_coordinates_are_quarantined_with_their_reason(self):
        self.assertEqual(QUARANTINE["by_reason"]["coordinates_absent"], 524)
        self.assertIn("coordinates_absent", QUARANTINE["reason_codes"])
        self.assertEqual(QUALITY["missingness_rates"]["coordinates"]["count"], 0)

    def test_coordinates_absent_is_not_reported_as_an_absence_in_emitted_records(self):
        self.assertNotIn("coordinates_absent", META["absence_counts"])

    def test_emitted_coordinates_are_inside_nigeria(self):
        for r in RECORDS:
            self.assertTrue(NIGERIA_MIN_LAT <= r["latitude"] <= NIGERIA_MAX_LAT)
            self.assertTrue(NIGERIA_MIN_LON <= r["longitude"] <= NIGERIA_MAX_LON)

    def test_lgas_lost_to_the_policy_are_named_not_hidden(self):
        lost = QUALITY["coverage"]["lgas_lost_to_quarantine"]
        self.assertIn("Borno / Ngala", lost)
        self.assertIn("Kano / Ajingi", lost)
        self.assertEqual(len(lost), 230)


class StateInstrumentTests(unittest.TestCase):
    """The per-state yardstick sees the transposition the bounding box cannot. It refuses;
    it never exchanges. Each of these fails if it starts correcting, or stops seeing."""

    KANO = M.STATE_REFERENCE_POINTS["Kano"]
    LAGOS = M.STATE_REFERENCE_POINTS["Lagos"]
    ARGS = (M.SWAP_MIN_DISTANCE_KM, M.SWAP_FACTOR, M.NOT_IN_STATE_KM)

    def test_a_northern_transposition_inside_the_box_is_refused_not_exchanged(self):
        # Kano city is 12.0N 8.5E. Written the other way round it is still inside Nigeria —
        # the box accepts it — and 500 km away. The state yardstick refuses it.
        lon, lat, box_reason = coordinate("12.0022", "8.5920")   # source has lon=12.0, lat=8.59
        self.assertIsNone(box_reason)
        given, transposed, reason = coordinate_vs_state(lon, lat, *self.KANO, *self.ARGS)
        self.assertEqual(reason, "coordinates_swapped_suspected_by_state")
        self.assertGreater(given, 400)
        self.assertLess(transposed, 50)

    def test_a_genuine_point_is_kept(self):
        given, transposed, reason = coordinate_vs_state(3.3515, 6.6018, *self.LAGOS, *self.ARGS)
        self.assertIsNone(reason)
        self.assertLess(given, 50)

    def test_a_point_far_under_both_readings_is_refused_as_not_in_state(self):
        # 12.0N 8.5E claimed as Lagos: 700 km away as given and transposed alike.
        _, _, reason = coordinate_vs_state(8.5, 12.0, *self.LAGOS, *self.ARGS)
        self.assertEqual(reason, "coordinates_not_in_state")

    def test_a_point_near_the_diagonal_is_not_refused(self):
        # Bauchi's reference is 10.5N 9.8E; a point 60 km away transposes to 60 km away too.
        la, lo = M.STATE_REFERENCE_POINTS["Bauchi"]
        _, _, reason = coordinate_vs_state(lo + 0.3, la + 0.3, la, lo, *self.ARGS)
        self.assertIsNone(reason)

    def test_the_reference_table_is_complete_and_cross_checked_against_1_1(self):
        self.assertEqual(set(M.STATE_REFERENCE_POINTS), set(M.NIGERIA_STATES) | {M.FCT_NAME})
        current = load_json(repo("facilities.ng.v1.1.json"))["facilities"]
        for state in ("Lagos", "FCT", "Kano"):
            lats = sorted(f["latitude"] for f in current if f["state"] == state)
            lons = sorted(f["longitude"] for f in current if f["state"] == state)
            distance = haversine_km(lats[len(lats) // 2], lons[len(lons) // 2],
                                    *M.STATE_REFERENCE_POINTS[state])
            self.assertLess(distance, 50, state)

    def test_the_transposition_is_refused_at_scale_and_nothing_was_exchanged(self):
        self.assertEqual(QUARANTINE["by_reason"]["coordinates_swapped_suspected_by_state"], 9911)
        self.assertEqual(QUARANTINE["by_reason"]["coordinates_not_in_state"], 81)
        self.assertEqual(META["coordinate_reference"]["records_moved_or_exchanged"], 0)
        for r in RECORDS:
            _, _, reason = coordinate_vs_state(r["longitude"], r["latitude"],
                                               *M.STATE_REFERENCE_POINTS[r["state"]], *self.ARGS)
            self.assertIsNone(reason, r["facility_id"])

    def test_emptied_states_are_named_in_three_places(self):
        emptied = ["FCT", "Kano", "Katsina", "Kwara", "Niger", "Taraba", "Zamfara"]
        self.assertEqual(META["states_with_no_emitted_records"], emptied)
        self.assertEqual(QUALITY["coverage"]["states_in_source_with_no_emitted_records"], emptied)
        for state in emptied:
            self.assertIn(state, META["coverage_claim"])
            self.assertNotIn(state, META["states_covered"])
            self.assertNotIn(state, META["states_absent"])

    def test_the_evidence_table_reads_kano_as_transposed_and_lagos_as_consistent(self):
        by_state = {e["state"]: e for e in QUALITY["source_evidence"]["coordinate_consistency_by_state"]}
        self.assertEqual(by_state["Kano"]["reading"], "predominantly transposed in the source")
        self.assertEqual(by_state["Kano"]["emitted"], 0)
        self.assertEqual(by_state["Lagos"]["reading"], "consistent with the state")
        self.assertLess(by_state["Lagos"]["median_km_from_reference_as_given"], 50)

    def test_the_quarantine_detail_carries_both_distances_and_no_coordinates(self):
        rows = [q for q in QUARANTINE["rows"] if q["reason_code"] == "coordinates_swapped_suspected_by_state"]
        self.assertTrue(rows)
        for q in rows[:50]:
            self.assertIn("transposed; refused, not exchanged", q["detail"])
            self.assertNotRegex(q["detail"], r"\d+\.\d{4,}")   # no coordinate values reproduced


class DeduplicationTests(unittest.TestCase):
    def _record(self, uid, sid, name="Mercy Hospital", lon=7.0, lat=5.0, phone_=None):
        return {"name": name, "state": "Abia", "city_area": "Aba North", "longitude": lon,
                "latitude": lat, "phone": phone_, "facility_id": "ng_nhf_%s" % sid,
                "source_record": {"source_unique_id": uid, "source_id": sid}}

    def test_the_rule_is_exact_and_documented(self):
        self.assertEqual(META["deduplication"]["rule_id"], "exact_match_v1")
        self.assertIs(META["deduplication"]["values_merged"], False)
        self.assertEqual(META["deduplication"]["rows_removed"], 62)
        self.assertEqual(META["deduplication"]["groups_collapsed"], 62)
        self.assertEqual(QUALITY["duplicates"]["exact_duplicates_resolved"]["group_sizes"],
                         {"2": 62})

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
            # The survivor keeps its own phone; nothing is merged from the loser.
            self.assertEqual(survivors[0]["phone"], "+2348000000002")

    def test_near_duplicates_are_not_collapsed(self):
        import build_facilities_candidate as gen

        same_name_other_point = self._record("01/01/1/2/2/0011", "7", lon=7.001)
        same_point_other_name = self._record("01/01/1/2/2/0012", "8", name="Mercy Pharmacy")
        base = self._record("01/01/1/2/2/0009", "5")
        survivors, dedup = gen.deduplicate([base, same_name_other_point, same_point_other_name])
        self.assertEqual(len(survivors), 3)
        self.assertEqual(dedup["rows_removed"], 0)

    def test_every_removed_row_names_a_survivor_in_the_candidate(self):
        ids = {r["facility_id"] for r in RECORDS}
        removed = [q for q in QUARANTINE["rows"] if q["reason_code"] == "duplicate_exact_match"]
        self.assertEqual(len(removed), 62)
        for q in removed:
            self.assertIn(q["survivor_facility_id"], ids)
            self.assertNotIn("ng_nhf_%s" % q["source_id"], ids)

    def test_looser_duplicates_are_counted_not_merged(self):
        remaining = QUALITY["duplicates"]["remaining_candidates"]
        self.assertGreater(remaining["same_name_state_lga_groups"], 0)
        self.assertIn("not resolved", remaining["note"])


class NormalizationTests(unittest.TestCase):
    def test_unicode_and_whitespace_are_normalised(self):
        self.assertEqual(text("  Sauki  Clinic \t"), "Sauki Clinic")
        self.assertEqual(text("Café"), text("Café"))

    def test_casing_is_preserved_not_rewritten(self):
        self.assertEqual(text("PHC OGBA"), "PHC OGBA")
        self.assertTrue(any(r["name"].isupper() for r in RECORDS))

    def test_placeholder_tokens_become_absent(self):
        for token in ("Nil", "NIL", "nill", "N/A", "-", "0", "none", ""):
            self.assertIsNone(text(token), token)

    def test_phone_normalisation_accepts_the_forms_the_source_uses(self):
        for raw in ("8060823195", "08060823195", "+2348060823195", "234 806 082 3195"):
            self.assertEqual(phone(raw)[0], "+2348060823195", raw)

    def test_phone_rejects_non_nigerian_mobiles(self):
        for raw in ("+14155552671", "012345678", "1", "abc"):
            self.assertIsNone(phone(raw)[0], raw)

    def test_coordinates_outside_nigeria_are_refused(self):
        self.assertEqual(coordinate("100", "100")[2], "coordinates_out_of_bounds")
        self.assertEqual(coordinate("0", "0")[2], "coordinates_null_island")
        self.assertEqual(coordinate("", "")[2], "coordinates_absent")
        self.assertEqual(coordinate("7.1", "")[2], "coordinates_unparseable")

    def test_contact_details_in_free_text_are_removed(self):
        self.assertEqual(free_text("mussdoctor71@gmail.com"),
                         (None, "contact_detail_in_free_text_field"))
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
        # The one source row with a personal email in its address is now refused earlier, by
        # the coordinate instrument, so the scrub has nothing to count in this build. The
        # guard itself must still be there for the day a kept row carries one.
        self.assertEqual(free_text("someone@example.com"), (None, "contact_detail_in_free_text_field"))
        self.assertEqual(EMAIL.findall(json.dumps(QUARANTINE)), [])

    def test_excluded_source_columns_appear_in_no_record(self):
        text_ = json.dumps(RECORDS)
        for column in ("email_address", "alternate_number", "verified_email", "published_mobile",
                       "created_by", "verified_by"):
            self.assertNotIn('"%s"' % column, text_, column)

    def test_the_exclusions_are_documented(self):
        documented = json.dumps(META["not_carried_from_source"])
        self.assertIn("email_address", documented)
        self.assertIn("alternate_number", documented)

    def test_no_user_health_search_or_location_history_key_exists(self):
        import validate_facilities_candidate as v

        keys = v._keys(CANDIDATE, set())
        offending = [k for k in keys if set(k.lower().split("_")) & v.PROHIBITED_KEY_TOKENS]
        self.assertEqual(offending, [])
        # And the guard itself catches what it is for.
        self.assertTrue({"user", "id"} & v.PROHIBITED_KEY_TOKENS)

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
        self.assertEqual(
            QUALITY["row_accounting"]["source_rows"],
            QUALITY["row_accounting"]["emitted"] + QUALITY["row_accounting"]["quarantined"],
        )
        self.assertEqual(QUALITY["row_accounting"]["source_rows"], 31390)
        self.assertEqual(QUALITY["row_accounting"]["emitted"], len(RECORDS))

    def test_quarantine_is_deterministic_and_reasoned(self):
        rows = QUARANTINE["rows"]
        self.assertEqual(rows, sorted(rows, key=lambda q: (q["reason_code"], q["source_line"])))
        for row in rows:
            self.assertIn(row["reason_code"], QUARANTINE["reason_codes"])

    def test_the_quarantine_report_does_not_republish_sensitive_values(self):
        self.assertEqual(EMAIL.findall(json.dumps(QUARANTINE)), [])

    def test_no_record_has_one_coordinate_without_the_other(self):
        for r in RECORDS:
            self.assertEqual(r["latitude"] is None, r["longitude"] is None)

    def test_no_empty_names(self):
        self.assertTrue(all(r["name"].strip() for r in RECORDS))

    def test_source_record_carries_provenance_and_admin_ids(self):
        for r in RECORDS:
            s = r["source_record"]
            self.assertTrue(s["state_id"].isdigit())
            self.assertTrue(s["lga_id"].isdigit())
            self.assertTrue(s["ward_id"] is None or s["ward_id"].isdigit())
            self.assertTrue(s["source_updated_at"] is None
                            or re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", s["source_updated_at"]))


class CoverageTests(unittest.TestCase):
    def test_the_absent_states_are_named(self):
        self.assertEqual(META["states_absent"], ["Adamawa", "Kebbi", "Sokoto"])

    def test_the_artifact_does_not_claim_nationwide_coverage(self):
        self.assertIn("NOT nationwide", META["coverage_claim"])

    def test_states_covered_matches_the_records(self):
        self.assertEqual(sorted({r["state"] for r in RECORDS}), META["states_covered"])

    def test_every_state_is_a_real_nigerian_state(self):
        for state in {r["state"] for r in RECORDS}:
            self.assertTrue(state in M.NIGERIA_STATES or state == M.FCT_NAME, state)

    def test_the_akwa_ibom_spelling_variant_is_normalised(self):
        self.assertIn("Akwa Ibom", META["states_covered"])
        self.assertNotIn("Akwa-Ibom", META["states_covered"])

    def test_every_record_has_a_state_and_an_lga(self):
        for r in RECORDS:
            self.assertTrue(r["state"].strip())
            self.assertTrue(r["city_area"].strip())
            self.assertEqual(r["lga"], r["city_area"])

    def test_lga_coverage_is_reported_against_the_national_total(self):
        self.assertEqual(QUALITY["coverage"]["lga_names_expected_nationally"], 774)
        self.assertLess(QUALITY["coverage"]["lga_names_distinct"], 774)

    def test_lga_id_is_name_scoped_and_said_so(self):
        spanning = QUALITY["source_evidence"]["lga_ids_spanning_multiple_states"]
        names = {e["lga_name"] for e in spanning}
        for homonym in ("Nasarawa", "Obi", "Ifelodun", "Irepodun", "Surulere", "Bassa"):
            self.assertIn(homonym, names)
        self.assertTrue(any("lga_id" in line for line in QUALITY["known_limitations"]))
        # (state, city_area) is unambiguous even where lga_id is not.
        pairs = {}
        for r in RECORDS:
            pairs.setdefault((r["state"], r["city_area"]), set()).add(r["source_record"]["lga_id"])
        self.assertTrue(all(len(v) == 1 for v in pairs.values()))

    def test_the_mislabelled_enugu_rows_did_not_reach_the_candidate(self):
        for lga in ("Arochukwu", "Umuahia North", "Umuahia South", "Ohafia", "Isuikwuato"):
            self.assertFalse(any(r["state"] == "Enugu" and r["city_area"] == lga for r in RECORDS))


class MobileCompatibilityTests(unittest.TestCase):
    """Measured against a port of the real consumer, not asserted."""

    COMPAT = load_json(repo("reports", "facilities_mobile_compat_v1.json"))

    def test_every_field_mobile_reads_is_present_on_every_record(self):
        self.assertTrue(self.COMPAT["required_field_presence"]["all_present_in_candidate"])
        for field in self.COMPAT["required_field_presence"]["fields"]:
            self.assertTrue(all(field in r for r in RECORDS), field)

    def test_the_type_gap_and_the_lost_states_are_reported_as_blocking(self):
        blocking = [f["finding"] for f in self.COMPAT["blocking_findings"] if f["severity"] == "blocking"]
        self.assertEqual(len(blocking), 2)
        self.assertTrue(any("type is null" in f for f in blocking))
        self.assertTrue(any("FCT and Kano" in f for f in blocking))

    def test_by_location_returns_nothing_in_the_lost_states(self):
        for key in ("Kano / Ajingi", "FCT / Abuja Municipal Area Council"):
            for urgency, counts in self.COMPAT["by_location_probe_results"][key].items():
                self.assertEqual(counts["candidate"], 0, "%s %s" % (key, urgency))

    def test_non_emergency_queries_return_nothing_and_that_is_recorded(self):
        for probe in self.COMPAT["nearby_probe_results"].values():
            for urgency in ("urgent", "non_urgent", "self_care"):
                self.assertTrue(probe[urgency]["candidate_returns_nothing"])

    def test_emergency_queries_still_return_results(self):
        for probe in self.COMPAT["nearby_probe_results"].values():
            self.assertGreater(probe["emergency"]["candidate_results"], 0)

    def test_the_verdict_is_not_compatible(self):
        self.assertIn("NOT COMPATIBLE", self.COMPAT["verdict"])

    def test_mobile_repository_was_not_modified(self):
        self.assertFalse(self.COMPAT["_metadata"]["mobile_repository_modified"])

    def test_the_null_coordinate_path_is_never_exercised(self):
        self.assertEqual(self.COMPAT["type_and_null_handling"]["candidate_records_without_coordinates"], 0)


class ComparisonTests(unittest.TestCase):
    COMPARE = load_json(repo("reports", "facilities_comparison_v1.json"))

    def test_the_states_lost_against_1_1_are_named_everywhere(self):
        self.assertEqual(self.COMPARE["states_lost"], ["FCT", "Kano"])
        for state in self.COMPARE["states_lost"]:
            self.assertIn(state, META["states_with_no_emitted_records"])

    def test_the_comparison_proposes_rather_than_merges(self):
        self.assertIn("NOT applied", self.COMPARE["duplicate_consolidation_proposals"]["rule"])
        self.assertTrue(
            any("Do not merge" in p for p in self.COMPARE["reconciliation_proposals"])
        )

    def test_record_and_size_change_are_quantified(self):
        self.assertEqual(self.COMPARE["record_counts"]["facilities_1_1"], 5344)
        self.assertEqual(self.COMPARE["record_counts"]["candidate"], len(RECORDS))
        self.assertGreater(self.COMPARE["file_size"]["multiplier"], 1)

    def test_the_quality_report_states_the_material_differences(self):
        diff = QUALITY["differences_from_facilities_1_1"]
        self.assertEqual(diff["records"]["facilities_1_1"], 5344)
        self.assertEqual(diff["fields_null_on_every_candidate_record_but_populated_in_1_1"],
                         ["type", "emergency_capable"])


class ManifestTests(unittest.TestCase):
    def test_the_manifest_is_not_live_and_grants_nothing(self):
        self.assertIs(MANIFEST["IS_LIVE_MANIFEST"], False)
        self.assertIs(MANIFEST["candidate_artifact"]["may_publish"], False)
        self.assertIs(MANIFEST["candidate_artifact"]["uploaded_to_r2"], False)
        self.assertTrue(all(v is False for v in MANIFEST["publication_gates"].values()))

    def test_the_manifest_describes_the_bytes_on_disk(self):
        path = repo("candidate", "facilities.ng.v2.0.json")
        self.assertEqual(MANIFEST["candidate_artifact"]["sha256"], sha256_file(path))
        self.assertEqual(MANIFEST["candidate_artifact"]["bytes"], os.path.getsize(path))
        self.assertEqual(MANIFEST["candidate_artifact"]["record_count"], len(RECORDS))
        self.assertEqual(MANIFEST["candidate_artifact"]["generated_at"], META["generated_at"])
        self.assertEqual(MANIFEST["source"]["sha256"], SOURCE_SHA256)

    def test_the_manifest_binds_rollback_to_1_1_by_hash(self):
        self.assertEqual(MANIFEST["rollback"]["target_file"], "facilities.ng.v1.1.json")
        self.assertEqual(MANIFEST["rollback"]["target_sha256"], CURRENT_SHA256)
        self.assertIs(MANIFEST["rollback"]["target_untouched_by_this_work"], True)

    def test_the_manifest_is_reproducible(self):
        import build_facilities_manifest as gen
        from vocab.artifact_io import dump_report_bytes

        with open(repo("candidate", "facilities.manifest.candidate.json"), "rb") as handle:
            self.assertEqual(handle.read(), dump_report_bytes(gen.build()))


class DocumentationTests(unittest.TestCase):
    """The consumer documents must describe the bytes that exist, not an earlier build."""

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
        self.assertIn("NOT COMPATIBLE", text_)

    def test_the_handoff_states_the_known_limitations_that_matter_to_product(self):
        text_ = self._text("mobile_handoff", "facilities_v2", "README.md")
        for phrase in ("Adamawa, Kebbi", "not established", "tel:", "lga_id", "13.8×",
                       "FCT and Kano", "wrong way round"):
            self.assertIn(phrase, text_, phrase)

    def test_the_dart_types_fail_closed_on_unknown_enums(self):
        text_ = self._text("mobile_handoff", "facilities_v2", "facility_types.dart")
        self.assertIn("return null;", text_)
        self.assertIn("Never by lgaId alone", text_)
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

    def test_the_dry_run_plan_performs_nothing(self):
        operations = self.PLAN["operations_performed"]
        for flag in ("upload_performed", "publication_performed", "activation_performed",
                     "deployment_performed"):
            self.assertIs(operations[flag], False, flag)

    def test_the_dry_run_plan_describes_the_current_bytes(self):
        self.assertEqual(self.PLAN["descriptor"]["sha256"],
                         "sha256:%s" % sha256_file(repo("candidate", "facilities.ng.v2.0.json")))

    def test_the_plan_is_not_published_active_or_eligible(self):
        states = self.PLAN["lifecycle"]["states"]
        self.assertIs(states["published"], False)
        self.assertIs(states["active"], False)
        self.assertIs(self.PLAN["eligible_in_any_environment"], False)

    def test_no_approval_or_authorization_is_recorded(self):
        descriptor = self.PLAN["descriptor"]
        for role in ("product", "clinical"):
            self.assertEqual(descriptor["approvals"][role]["status"], "pending")
        self.assertIs(descriptor["activation_authorized"], False)
        self.assertIsNone(descriptor["publication_decision_ref"])

    def test_the_candidate_is_not_at_the_published_root(self):
        self.assertFalse(os.path.exists(repo("facilities.ng.v2.0.json")))


class FrozenArtifactTests(unittest.TestCase):
    def test_facilities_1_1_is_byte_identical(self):
        self.assertEqual(sha256_file(repo("facilities.ng.v1.1.json")), CURRENT_SHA256)

    def test_facilities_1_0_is_byte_identical(self):
        self.assertEqual(
            sha256_file(repo("facilities.ng.v1.0.json")),
            "1c7b939199ab4465156f4cb336910eea120fcaa70f8b1c0743fc9f7a7c03009e",
        )

    def test_building_the_candidate_touches_no_frozen_artifact(self):
        import build_facilities_candidate as gen

        before = sha256_file(repo("facilities.ng.v1.1.json"))
        gen.build()
        self.assertEqual(sha256_file(repo("facilities.ng.v1.1.json")), before)


class OfflineSafetyTests(unittest.TestCase):
    def test_the_generator_performs_no_network_or_stray_write(self):
        import tempfile

        from pubkit.safety import SideEffectAttempted, no_side_effects  # noqa: F401

        import build_facilities_candidate as gen

        with tempfile.TemporaryDirectory() as directory:
            with no_side_effects(allowed_write_roots=(directory,), raise_on_attempt=True) as guard:
                gen.build()   # builds in memory; writing is a separate step
            self.assertEqual(guard.attempts, [])

    def test_the_generators_import_no_cloud_sdk_or_http_client(self):
        for name in ("build_facilities_candidate.py", "build_facilities_manifest.py",
                     "report_facilities_comparison.py", "validate_facilities_candidate.py"):
            with open(os.path.join(ROOT, "tools", name), encoding="utf-8") as handle:
                source = handle.read()
            for banned in ("import requests", "import urllib.request", "boto3", "urlopen", "httpx"):
                self.assertNotIn(banned, source, "%s: %s" % (name, banned))


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
