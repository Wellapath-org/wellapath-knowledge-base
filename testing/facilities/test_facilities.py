#!/usr/bin/env python3
"""Tests for the nationwide facilities candidate.

    python3 testing/facilities/test_facilities.py [-v]

The tests that matter most are the ones guarding what the generator refuses to do. Anyone can
write a transformation that fills every field; the value here is that `type` and
`emergency_capable` stay null, that a coordinate pair is never silently swapped, that a
placeholder phone never becomes a real one, and that a personal email typed into an address
field does not travel onward. Each of those has a test that fails if the guard is removed.
"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from facilities import mappings as M  # noqa: E402
from facilities.normalize import (NIGERIA_MAX_LAT, NIGERIA_MAX_LON, NIGERIA_MIN_LAT,  # noqa: E402
                                  NIGERIA_MIN_LON, coordinate, free_text, phone, sort_key, text)
from vocab.artifact_io import load_json, sha256_file  # noqa: E402
from vocab.schema_check import validate as schema_validate  # noqa: E402


def repo(*parts):
    return os.path.join(ROOT, *parts)


CANDIDATE = load_json(repo("candidate", "facilities.ng.v2.0.json"))
RECORDS = CANDIDATE["facilities"]
META = CANDIDATE["_metadata"]
QUALITY = load_json(repo("reports", "facilities_quality_v1.json"))
QUARANTINE = load_json(repo("reports", "facilities_quarantine_v1.json"))
SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"


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
        self.assertEqual(META["generated_at"], "2026-08-31T00:00:00Z")


class SchemaTests(unittest.TestCase):
    def test_candidate_satisfies_its_schema(self):
        errors = schema_validate(CANDIDATE, load_json(repo("schema", "facilities.v2.schema.json")))
        self.assertEqual(errors, [], errors[:3])

    def test_schema_pins_the_unevidenced_fields_to_null(self):
        schema = load_json(repo("schema", "facilities.v2.schema.json"))
        props = schema["$defs"]["facility"]["properties"]
        self.assertEqual(props["type"]["type"], "null")
        self.assertEqual(props["emergency_capable"]["type"], "null")

    def test_schema_pins_candidate_status(self):
        meta = load_json(repo("schema", "facilities.v2.schema.json"))["properties"]["_metadata"]
        self.assertEqual(meta["properties"]["release_status"]["const"], "candidate_unapproved")
        self.assertEqual(meta["properties"]["may_publish"]["const"], False)


class NothingInventedTests(unittest.TestCase):
    """The guards. Each of these fails the moment someone fills a field the source cannot fill."""

    def test_type_is_null_everywhere(self):
        self.assertTrue(all(r["type"] is None for r in RECORDS))
        self.assertEqual(M.FACILITY_TYPE_FROM_LEVEL, {})

    def test_emergency_capable_is_null_everywhere(self):
        self.assertTrue(all(r["emergency_capable"] is None for r in RECORDS))
        self.assertIsNone(M.EMERGENCY_CAPABLE_RULE)

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


class NormalizationTests(unittest.TestCase):
    def test_unicode_and_whitespace_are_normalised(self):
        self.assertEqual(text("  Sauki  Clinic \t"), "Sauki Clinic")
        self.assertEqual(text("Café"), text("Café"))

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

    def test_contact_details_in_free_text_are_removed(self):
        self.assertEqual(free_text("mussdoctor71@gmail.com"),
                         (None, "contact_detail_in_free_text_field"))
        self.assertEqual(free_text("http://www.example.com"), (None, "url_in_free_text_field"))
        self.assertEqual(free_text("1B Faulks Road")[0], "1B Faulks Road")


class PrivacyTests(unittest.TestCase):
    def test_no_email_address_survives_into_any_record(self):
        import re

        self.assertEqual(
            re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", json.dumps(RECORDS)), []
        )

    def test_the_one_leaked_address_was_caught_and_counted(self):
        self.assertEqual(META["absence_counts"]["address_contact_detail_in_free_text_field"], 1)

    def test_excluded_source_columns_appear_in_no_record(self):
        text_ = json.dumps(RECORDS)
        for column in ("email_address", "alternate_number", "verified_email", "published_mobile",
                       "created_by", "verified_by"):
            self.assertNotIn('"%s"' % column, text_, column)

    def test_the_exclusions_are_documented(self):
        documented = json.dumps(META["not_carried_from_source"])
        self.assertIn("email_address", documented)
        self.assertIn("alternate_number", documented)


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

    def test_quarantine_is_deterministic_and_reasoned(self):
        rows = QUARANTINE["rows"]
        self.assertEqual(rows, sorted(rows, key=lambda q: (q["reason_code"], q["source_line"])))
        for row in rows:
            self.assertIn(row["reason_code"], QUARANTINE["reason_codes"])

    def test_the_quarantine_report_does_not_republish_sensitive_values(self):
        import re

        self.assertEqual(
            re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", json.dumps(QUARANTINE)),
            [],
        )

    def test_emitted_coordinates_are_inside_nigeria(self):
        for r in RECORDS:
            if r["latitude"] is not None:
                self.assertTrue(NIGERIA_MIN_LAT <= r["latitude"] <= NIGERIA_MAX_LAT)
                self.assertTrue(NIGERIA_MIN_LON <= r["longitude"] <= NIGERIA_MAX_LON)

    def test_no_record_has_one_coordinate_without_the_other(self):
        for r in RECORDS:
            self.assertEqual(r["latitude"] is None, r["longitude"] is None)

    def test_no_empty_names(self):
        self.assertTrue(all(r["name"].strip() for r in RECORDS))


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


class MobileCompatibilityTests(unittest.TestCase):
    """Measured against a port of the real consumer, not asserted."""

    COMPAT = load_json(repo("reports", "facilities_mobile_compat_v1.json"))

    def test_every_field_mobile_reads_is_present_on_every_record(self):
        self.assertTrue(self.COMPAT["required_field_presence"]["all_present_in_candidate"])
        for field in self.COMPAT["required_field_presence"]["fields"]:
            self.assertTrue(all(field in r for r in RECORDS), field)

    def test_the_type_gap_is_reported_as_blocking(self):
        blocking = [f for f in self.COMPAT["blocking_findings"] if f["severity"] == "blocking"]
        self.assertEqual(len(blocking), 1)
        self.assertIn("type is null", blocking[0]["finding"])

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


class ComparisonTests(unittest.TestCase):
    COMPARE = load_json(repo("reports", "facilities_comparison_v1.json"))

    def test_no_state_present_in_1_1_was_lost(self):
        self.assertEqual(self.COMPARE["states_lost"], [])

    def test_the_comparison_proposes_rather_than_merges(self):
        self.assertIn("NOT applied", self.COMPARE["duplicate_consolidation_proposals"]["rule"])
        self.assertTrue(
            any("Do not merge" in p for p in self.COMPARE["reconciliation_proposals"])
        )

    def test_record_and_size_change_are_quantified(self):
        self.assertEqual(self.COMPARE["record_counts"]["facilities_1_1"], 5344)
        self.assertEqual(self.COMPARE["record_counts"]["candidate"], len(RECORDS))
        self.assertGreater(self.COMPARE["file_size"]["multiplier"], 1)


class CandidateStatusTests(unittest.TestCase):
    PLAN = load_json(repo("publication", "plans", "facilities.ng.v2.0.dryrun.json"))

    def test_the_artifact_is_an_unapproved_candidate(self):
        self.assertEqual(META["release_status"], "candidate_unapproved")
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
        self.assertEqual(
            sha256_file(repo("facilities.ng.v1.1.json")),
            "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398",
        )

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

        from pubkit.safety import SideEffectAttempted, no_side_effects

        import build_facilities_candidate as gen

        with tempfile.TemporaryDirectory() as directory:
            with no_side_effects(allowed_write_roots=(directory,), raise_on_attempt=True) as guard:
                gen.build()   # builds in memory; writing is a separate step
            self.assertEqual(guard.attempts, [])

    def test_the_generator_imports_no_cloud_sdk_or_http_client(self):
        with open(os.path.join(ROOT, "tools", "build_facilities_candidate.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        for banned in ("import requests", "import urllib.request", "boto3", "urlopen", "httpx"):
            self.assertNotIn(banned, source, banned)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
