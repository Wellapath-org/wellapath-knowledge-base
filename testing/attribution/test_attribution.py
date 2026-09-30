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
        with open(repo("facilities.ng.v1.2.json"), encoding="utf-8") as handle:
            cls.meta = json.load(handle)["_metadata"]

    def test_the_two_licensed_sources_are_recorded_with_licence_and_url(self):
        by_licence = {s["license"]: s for s in self.meta["sources"] if s["license"]}
        self.assertIn("CC BY 4.0", by_licence)
        self.assertIn("ODbL", by_licence)
        for source in by_licence.values():
            self.assertTrue(source["url"].startswith("https://"), source["url"])

    def test_no_unlicensed_source_remains(self):
        """v1.1 declared one source with a null licence: 45 NHFR-derived
        telephone numbers, redistributed without established permission.

        v1.2 removed them, so every declared source now carries a licence.
        This assertion is the guard against that regressing — it fails the
        moment any source appears without one, which is how the original gap
        would return.
        """
        unlicensed = [s for s in self.meta["sources"] if not s["license"]]
        self.assertEqual(unlicensed, [], "every declared source must carry a licence")
        self.assertEqual(len(self.meta["sources"]), 2)

    def test_the_notice_still_records_the_superseded_material(self):
        """The history must stay legible after the file is gone.

        v1.1 and its 45 NHFR-derived numbers are retired, but a reader has to
        be able to find out that they existed and why they were withdrawn.
        """
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
