#!/usr/bin/env python3
"""Attribution must stay reachable and complete.

CC BY 4.0 and ODbL 1.0 both make attribution a licence condition, so these
assertions guard a legal obligation, not a documentation preference. They are
deliberately literal: each checks for a specific string a reader or a licensor
would look for.
"""

import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def repo(*parts):
    return os.path.join(ROOT, *parts)


class DataSourcesNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = repo("DATA_SOURCES.md")
        with open(cls.path, encoding="utf-8") as handle:
            cls.text = handle.read()

    def test_the_notice_exists_at_the_repository_root(self):
        self.assertTrue(os.path.exists(self.path), "DATA_SOURCES.md must be at the root")

    def test_openstreetmap_contributors_are_credited_in_the_required_form(self):
        self.assertIn("© OpenStreetMap contributors", self.text)

    def test_both_licences_are_named_with_their_urls(self):
        self.assertIn("CC BY 4.0", self.text)
        self.assertIn("https://creativecommons.org/licenses/by/4.0/", self.text)
        self.assertIn("ODbL", self.text)
        self.assertIn("https://opendatacommons.org/licenses/odbl/1-0/", self.text)

    def test_both_source_datasets_are_linked(self):
        self.assertIn("data.grid3.org", self.text)
        self.assertIn("data.humdata.org/dataset/hotosm_nga_health_facilities", self.text)
        self.assertIn("openstreetmap.org/copyright", self.text)

    def test_the_grid3_citation_names_its_producer(self):
        self.assertIn("CIESIN", self.text)
        self.assertIn("Columbia University", self.text)

    def test_modification_is_disclosed(self):
        self.assertRegex(self.text, r"(?i)modif")

    def test_non_endorsement_is_stated(self):
        self.assertRegex(self.text, r"(?i)do not endorse")

    def test_the_share_alike_position_is_declared(self):
        self.assertIn("Derivative Database", self.text)


class ArtifactMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(repo("facilities.ng.v1.1.json"), encoding="utf-8") as handle:
            cls.meta = json.load(handle)["_metadata"]

    def test_the_two_licensed_sources_are_recorded_with_licence_and_url(self):
        by_licence = {s["license"]: s for s in self.meta["sources"] if s["license"]}
        self.assertIn("CC BY 4.0", by_licence)
        self.assertIn("ODbL", by_licence)
        for source in by_licence.values():
            self.assertTrue(source["url"].startswith("https://"), source["url"])

    def test_the_unlicensed_source_is_declared_rather_than_hidden(self):
        """The artifact carries 45 NHFR-derived phone numbers.

        NHFR publishes no licence and reserves all rights, so this entry
        honestly records url=None and license=None. The assertion pins that:
        it fails if the gap is quietly papered over with a fabricated licence,
        and it fails if a *second* unlicensed source appears.
        """
        unlicensed = [s for s in self.meta["sources"] if not s["license"]]
        self.assertEqual(len(unlicensed), 1, "expected exactly one unlicensed source")
        self.assertIn("HFR", unlicensed[0]["name"])
        self.assertIsNone(unlicensed[0]["url"])

    def test_the_notice_discloses_the_unlicensed_material(self):
        with open(repo("DATA_SOURCES.md"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("NHFR", text)
        self.assertIn("45", text)

    def test_the_notice_and_the_artifact_agree_on_the_licensed_sources(self):
        with open(repo("DATA_SOURCES.md"), encoding="utf-8") as handle:
            text = handle.read()
        for source in self.meta["sources"]:
            if not source["url"]:
                continue
            host = re.sub(r"^https://([^/]+)/.*$", r"\1", source["url"])
            self.assertIn(host, text, "%s is in the artifact but not the notice" % host)


class LineageRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(repo("docs", "FACILITIES_ODBL_LINEAGE.md"), encoding="utf-8") as handle:
            cls.text = handle.read()

    def test_the_osm_contribution_is_quantified(self):
        self.assertIn("896", self.text)
        self.assertIn("5,344", self.text)

    def test_the_odbl_classification_is_stated_and_reasoned(self):
        self.assertIn("Derivative Database", self.text)
        self.assertIn("Collective Database", self.text)
        self.assertIn("Produced Work", self.text)

    def test_both_options_and_a_recommendation_are_recorded(self):
        self.assertIn("Option 1", self.text)
        self.assertIn("Option 2", self.text)
        self.assertRegex(self.text, r"(?i)## Recommendation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
