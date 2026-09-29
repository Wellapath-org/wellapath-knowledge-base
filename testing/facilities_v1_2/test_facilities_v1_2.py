#!/usr/bin/env python3
"""facilities.ng.v1.2.json — the NHFR-free replacement for v1.1.

These assertions guard a licensing position and a clinical behaviour, so they
are deliberately literal.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def repo(*parts):
    return os.path.join(ROOT, *parts)


def load(name):
    with open(repo(name), encoding="utf-8") as handle:
        return json.load(handle)


PHONE = re.compile(r"\"[+]?0?[789][01][0-9]{8}\"")
EMAIL = re.compile(r"[A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

V12 = load("facilities.ng.v1.2.json")
V11 = load("facilities.ng.v1.1.json")
V10 = load("facilities.ng.v1.0.json")


def identity(records):
    return {
        r["facility_id"]: (r["name"], r["latitude"], r["longitude"], r["type"], r["state"])
        for r in records
    }


class NhfrRemovalTests(unittest.TestCase):
    def test_no_contact_value_survives_anywhere_in_the_artifact(self):
        blob = json.dumps(V12, ensure_ascii=False)
        self.assertEqual(PHONE.findall(blob), [])
        self.assertEqual(EMAIL.findall(blob), [])

    def test_every_phone_and_opening_hours_field_is_null(self):
        for record in V12["facilities"]:
            self.assertIsNone(record["phone"], record["facility_id"])
            self.assertIsNone(record["opening_hours"], record["facility_id"])

    def test_v1_1_carried_45_phones_and_v1_2_carries_none(self):
        """Pins the delta this artifact exists to make."""
        self.assertEqual(sum(1 for r in V11["facilities"] if r["phone"]), 45)
        self.assertEqual(sum(1 for r in V12["facilities"] if r["phone"]), 0)

    def test_no_unlicensed_source_is_declared(self):
        for source in V12["_metadata"]["sources"]:
            self.assertTrue(source["license"], source["name"])
            self.assertTrue(source["url"].startswith("https://"), source["name"])

    def test_the_hfr_enrichment_source_entry_is_gone(self):
        names = " ".join(s["name"] for s in V12["_metadata"]["sources"])
        self.assertNotIn("HFR", names)


class ContinuityTests(unittest.TestCase):
    def test_identities_and_coordinates_are_unchanged_from_v1_1(self):
        self.assertEqual(identity(V12["facilities"]), identity(V11["facilities"]))

    def test_the_record_set_is_exactly_v1_0s(self):
        self.assertEqual(identity(V12["facilities"]), identity(V10["facilities"]))

    def test_the_record_count_is_unchanged(self):
        self.assertEqual(len(V12["facilities"]), 5344)
        self.assertEqual(V12["_metadata"]["total_facilities"], 5344)

    def test_emergency_hospital_prioritisation_is_preserved(self):
        """The red-flag path depends on this ordering.

        emergency_capable is type == 'hospital' and has never meant verified
        emergency capability; it reaches no user-facing string. Losing it
        would silently stop floating hospitals on the highest-stakes journey.
        """
        capable = [r for r in V12["facilities"] if r["emergency_capable"] is True]
        self.assertEqual(len(capable), 924)
        for record in capable:
            self.assertEqual(record["type"], "hospital")

    def test_no_record_claims_verified_emergency_capability(self):
        blob = json.dumps(V12).lower()
        self.assertNotIn("verified", blob)


class LicenceDeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lic = V12["_metadata"]["licence"]

    def test_the_database_is_declared_under_odbl(self):
        self.assertEqual(self.lic["database_licence"], "ODbL-1.0")
        self.assertIn("opendatacommons.org/licenses/odbl/1-0/", self.lic["database_licence_url"])

    def test_it_is_declared_a_derivative_database(self):
        self.assertIn("Derivative Database", self.lic["database_licence_statement"])

    def test_the_licence_scope_excludes_application_code(self):
        self.assertIn("does not place", self.lic["scope"])
        self.assertIn("application source code", self.lic["scope"])

    def test_openstreetmap_contributors_are_credited(self):
        self.assertIn("© OpenStreetMap contributors", self.lic["attribution"])

    def test_grid3_and_cc_by_are_retained_alongside(self):
        joined = " ".join(self.lic["attribution"])
        self.assertIn("CIESIN", joined)
        self.assertIn("CC BY 4.0", joined)

    def test_the_hot_export_tool_is_acknowledged(self):
        joined = " ".join(self.lic["attribution"])
        self.assertIn("HOT Export Tool", joined)

    def test_every_attribution_url_is_https_and_present(self):
        urls = self.lic["attribution_urls"]
        for key in ("openstreetmap_copyright", "odbl", "cc_by_4_0",
                    "grid3_dataset", "hotosm_dataset"):
            self.assertIn(key, urls)
            self.assertTrue(urls[key].startswith("https://"), key)

    def test_modifications_are_stated(self):
        self.assertIn("modified from the originals", self.lic["modifications"])

    def test_no_endorsement_is_stated(self):
        self.assertIn("do not endorse", self.lic["no_endorsement"])

    def test_the_notice_and_the_artifact_agree(self):
        """§1: the public copy, licence declaration and attribution must agree."""
        with open(repo("DATA_SOURCES.md"), encoding="utf-8") as handle:
            notice = handle.read()
        self.assertIn("© OpenStreetMap contributors", notice)
        self.assertIn("Derivative Database", notice)
        self.assertIn(self.lic["attribution_urls"]["odbl"], notice)
        self.assertIn(self.lic["attribution_urls"]["cc_by_4_0"], notice)


class SupersessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sup = V12["_metadata"]["supersession"]

    def test_it_records_what_it_supersedes_and_why(self):
        self.assertEqual(self.sup["supersedes"], "1.1")
        self.assertIn("NHFR", self.sup["reason"])
        self.assertIn("reserves", self.sup["reason"])

    def test_it_does_not_describe_a_privacy_breach(self):
        blob = json.dumps(V12).lower()
        self.assertNotIn("breach", blob.replace("no personal-data breach was established", ""))
        self.assertIn("licensing and attribution gap", self.sup["not_a_privacy_incident"])

    def test_a_rollback_document_is_named_and_exists(self):
        self.assertTrue(os.path.exists(repo(self.sup["rollback"])), self.sup["rollback"])


class ReproducibilityTests(unittest.TestCase):
    def test_the_generator_reproduces_the_committed_bytes(self):
        result = subprocess.run(
            [sys.executable, repo("tools", "build_facilities_v1_2.py"), "--check"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_recorded_checksum_matches_the_file(self):
        with open(repo("facilities.ng.v1.2.json"), "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        with open(repo("docs", "FACILITIES_V1_2_ROLLBACK.md"), encoding="utf-8") as handle:
            self.assertIn(digest, handle.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
