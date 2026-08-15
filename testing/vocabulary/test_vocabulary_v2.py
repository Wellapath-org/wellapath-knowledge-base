#!/usr/bin/env python3
"""W2 Symptom Vocabulary 2.0 test suite.

    python3 testing/vocabulary/test_vocabulary_v2.py            # run everything
    python3 testing/vocabulary/test_vocabulary_v2.py -v         # verbose

Standard-library `unittest` only — this repository has no dependency manifest
and pytest is not installed. See tools/vocab/__init__.py.

Coverage maps to the W2 "Tests Required" list:

    NormalizationTests             normalization
    SchemaTests                    schema unit tests
    InvalidFixtureTests            invalid-fixture tests
    MigrationTests                 migration, deterministic generation, hash
                                   reproducibility, artifact byte identity
    TokenReferenceIntegrityTests   token-reference integrity, kb/rules/red-flag
                                   /question reference regression
    AmbiguityTests                 duplicate/ambiguity tests
    SearchFixtureTests             search behaviour, offline load
    OldConsumerCompatibilityTests  old-consumer compatibility
    VersionNegotiationTests        version negotiation
    PublicationSafetyTests         candidate is unpublished and unapproved
    NoPhiTests                     no PHI or real-user data
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from vocab.artifact_io import (  # noqa: E402
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
)
from vocab.normalize import (  # noqa: E402
    derive_label_from_token_id,
    normalize,
    normalize_token_id,
)
from vocab.resolve import build_index  # noqa: E402
from vocab.schema_check import validate as schema_validate  # noqa: E402

import build_vocabulary_v2  # noqa: E402
import check_compatibility  # noqa: E402
import validate_vocabulary  # noqa: E402

CANDIDATE_PATH = repo_path("candidate", "token_dictionary.ng.v2.0.json")
BASELINE_PATH = repo_path("token_dictionary.ng.v1.1.json")
SCHEMA_PATH = repo_path("schema", "token_dictionary.v2.schema.json")
FIXTURES = os.path.join(HERE, "fixtures")

CATEGORIES = [
    "symptom_tokens",
    "red_flag_tokens",
    "duration_tokens",
    "body_area_tokens",
    "demographic_tokens",
    "severity_tokens",
]

# The E9.1 freeze. Duplicated here on purpose: if tools/check_compatibility.py
# and this suite ever disagree about what the baseline is, that disagreement
# should be a test failure rather than a shared constant nobody re-derives.
FROZEN_HASHES = {
    "token_dictionary.ng.v1.1.json": "0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019",
    "kb.ng.v2.4.json": "6c00d8257f8417e86bd5e237630bf8a4623ad72e2e46b1b071dd447c067cec2b",
    "rules.ng.v2.2.json": "1d27e854cba95b179577a88f92445400f494a7fe8e6a53a60fcaa98b3870d1c4",
    "facilities.ng.v1.1.json": "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398",
    "testing/case_bank_v1.json": "c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834",
}

CANDIDATE = load_json(CANDIDATE_PATH)
BASELINE = load_json(BASELINE_PATH)
INDEX = build_index(CANDIDATE)


class NormalizationTests(unittest.TestCase):
    def test_case_folding(self):
        for query in ["FEVER", "Fever", "fEvEr"]:
            self.assertEqual(normalize(query), "fever")

    def test_whitespace(self):
        self.assertEqual(normalize("  chest   pain  "), "chest pain")
        self.assertEqual(normalize("chest\tpain"), "chest pain")
        self.assertEqual(normalize("chest\npain"), "chest pain")

    def test_unicode_spaces(self):
        for space in [" ", " ", "​", "　"]:
            self.assertEqual(normalize("chest%spain" % space), "chest pain")

    def test_bom_is_stripped(self):
        self.assertEqual(normalize("﻿fever"), "fever")

    def test_hyphens_become_spaces(self):
        for dash in ["-", "‐", "–", "—", "−"]:
            self.assertEqual(normalize("chest%spain" % dash), "chest pain")

    def test_hyphen_does_not_vanish(self):
        # Deleting the hyphen would give "chestpain", which matches nothing.
        self.assertNotEqual(normalize("chest-pain"), "chestpain")

    def test_apostrophes_are_deleted(self):
        for apostrophe in ["'", "’", "ʼ", "´"]:
            self.assertEqual(normalize("ludwig%ss angina" % apostrophe), "ludwigs angina")

    def test_punctuation_becomes_space(self):
        self.assertEqual(normalize("chest, pain!"), "chest pain")
        self.assertEqual(normalize("(chest) [pain]"), "chest pain")
        self.assertEqual(normalize("chest/pain"), "chest pain")

    def test_decimal_point_survives_between_digits(self):
        self.assertEqual(normalize("38.5 degrees"), "38.5 degrees")

    def test_full_stop_outside_digits_does_not_survive(self):
        self.assertEqual(normalize("chest.pain"), "chest pain")

    def test_solidus_survives_between_digits(self):
        self.assertEqual(normalize("140/90"), "140/90")

    def test_thousands_separator_is_removed(self):
        self.assertEqual(normalize("1,000 ml"), "1000 ml")

    def test_nfkc_folds_compatibility_forms(self):
        self.assertEqual(normalize("ＦＥＶＥＲ"), "fever")

    def test_clinically_meaningful_words_survive(self):
        for phrase in [
            "no fever",
            "not breathing",
            "without pain",
            "left arm",
            "right arm",
            "severe pain",
            "3 days",
            "pregnant",
            "2 years old",
        ]:
            self.assertEqual(normalize(phrase.upper()), phrase)

    def test_no_stemming_or_plural_folding(self):
        self.assertNotEqual(normalize("fevers"), normalize("fever"))
        self.assertNotEqual(normalize("coughing"), normalize("cough"))

    def test_diacritics_are_preserved(self):
        self.assertEqual(normalize("naïve"), "naïve")

    def test_is_idempotent(self):
        for entry in CANDIDATE["tokens"]:
            once = normalize(entry["token_id"])
            self.assertEqual(normalize(once), once)

    def test_is_pure(self):
        for _ in range(3):
            self.assertEqual(normalize("  Chest-Pain! "), "chest pain")

    def test_rejects_non_string(self):
        for value in [None, 1, [], {}]:
            with self.assertRaises(TypeError):
                normalize(value)

    def test_normalize_token_id(self):
        self.assertEqual(normalize_token_id("chest_pain"), "chest pain")
        self.assertEqual(normalize_token_id("fever"), "fever")

    def test_derive_label(self):
        self.assertEqual(derive_label_from_token_id("chest_pain"), "Chest pain")
        self.assertEqual(derive_label_from_token_id("uti"), "Uti")


class SchemaTests(unittest.TestCase):
    def test_candidate_conforms(self):
        self.assertEqual(schema_validate(CANDIDATE, load_json(SCHEMA_PATH)), [])

    def test_schema_is_parseable_and_declares_draft(self):
        schema = load_json(SCHEMA_PATH)
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_schema_requires_the_legacy_arrays(self):
        schema = load_json(SCHEMA_PATH)
        for category in CATEGORIES:
            self.assertIn(category, schema["required"])

    def test_validator_rejects_unsupported_keywords(self):
        from vocab.schema_check import UnsupportedKeyword

        with self.assertRaises(UnsupportedKeyword):
            schema_validate({}, {"unevaluatedProperties": False})


class InvalidFixtureTests(unittest.TestCase):
    """Each invalid fixture must trip the specific check it targets."""

    def test_every_fixture_fails_its_named_check(self):
        directory = os.path.join(FIXTURES, "invalid")
        index = load_json(os.path.join(directory, "index.json"))
        self.assertTrue(index["fixtures"], "no invalid fixtures found")
        for fixture in index["fixtures"]:
            with self.subTest(fixture=fixture["file"]):
                results = validate_vocabulary.run(
                    os.path.join(directory, fixture["file"]), compare_baseline=False
                )
                failed = {"%s:%s" % (c["group"], c["check"]) for c in results.checks if not c["passed"]}
                self.assertIn(fixture["expected_failing_check"], failed)

    def test_fixtures_are_labelled_synthetic(self):
        directory = os.path.join(FIXTURES, "invalid")
        index = load_json(os.path.join(directory, "index.json"))
        for fixture in index["fixtures"]:
            artifact = load_json(os.path.join(directory, fixture["file"]))
            self.assertTrue(artifact["_metadata"].get("SYNTHETIC_FIXTURE"))


class MigrationTests(unittest.TestCase):
    def test_downgrade_projection_is_byte_identical_to_the_baseline(self):
        projected = dump_artifact_bytes(build_vocabulary_v2.project_to_v1_1(CANDIDATE))
        with open(BASELINE_PATH, "rb") as handle:
            self.assertEqual(projected, handle.read())

    def test_every_baseline_token_is_present(self):
        ids = {e["token_id"] for e in CANDIDATE["tokens"]}
        for category in CATEGORIES:
            for token in BASELINE[category]:
                self.assertIn(token, ids)

    def test_no_token_added(self):
        baseline_ids = {t for c in CATEGORIES for t in BASELINE[c]}
        candidate_ids = {e["token_id"] for e in CANDIDATE["tokens"]}
        self.assertEqual(candidate_ids, baseline_ids)

    def test_token_count_is_unchanged(self):
        self.assertEqual(len(CANDIDATE["tokens"]), 295)
        self.assertEqual(CANDIDATE["_metadata"]["total_tokens"], 295)

    def test_category_membership_is_unchanged(self):
        for category in CATEGORIES:
            from_entries = [e["token_id"] for e in CANDIDATE["tokens"] if e["category"] == category]
            self.assertEqual(from_entries, BASELINE[category])

    def test_generation_is_deterministic(self):
        first = dump_artifact_bytes(build_vocabulary_v2.build_candidate("2026-08-14T00:00:00Z"))
        second = dump_artifact_bytes(build_vocabulary_v2.build_candidate("2026-08-14T00:00:00Z"))
        self.assertEqual(first, second)

    def test_committed_candidate_matches_a_fresh_build(self):
        rebuilt = dump_artifact_bytes(
            build_vocabulary_v2.build_candidate(build_vocabulary_v2.DEFAULT_GENERATED_AT)
        )
        with open(CANDIDATE_PATH, "rb") as handle:
            self.assertEqual(rebuilt, handle.read())

    def test_hash_is_reproducible(self):
        rebuilt = dump_artifact_bytes(
            build_vocabulary_v2.build_candidate(build_vocabulary_v2.DEFAULT_GENERATED_AT)
        )
        self.assertEqual(sha256_bytes(rebuilt), sha256_file(CANDIDATE_PATH))

    def test_no_metadata_invented(self):
        for entry in CANDIDATE["tokens"]:
            self.assertEqual(entry["search"]["aliases"], [])
            self.assertEqual(entry["associations"]["body_areas"], [])
            self.assertEqual(entry["associations"]["complaint_groups"], [])
            self.assertEqual(entry["associations"]["severity_descriptors"], [])
            self.assertEqual(entry["associations"]["duration_descriptors"], [])
            self.assertIsNone(entry["review"]["clinical_reviewer"])
            self.assertIsNone(entry["review"]["review_date"])
            self.assertEqual(entry["review"]["review_status"], "not_reviewed")

    def test_complaint_groups_is_empty(self):
        self.assertEqual(CANDIDATE["complaint_groups"], [])

    def test_labels_are_derived_and_not_display_safe(self):
        for entry in CANDIDATE["tokens"]:
            self.assertEqual(entry["display"]["label_source"], "derived_from_token_id")
            self.assertEqual(entry["display"]["label_review_status"], "unreviewed")
            self.assertFalse(entry["display"]["display_safe"])
            self.assertEqual(
                entry["display"]["canonical_label"], derive_label_from_token_id(entry["token_id"])
            )

    def test_frozen_artifacts_are_byte_identical(self):
        for filename, expected in FROZEN_HASHES.items():
            with self.subTest(artifact=filename):
                self.assertEqual(sha256_file(repo_path(filename)), expected)

    def test_validator_passes_on_the_candidate(self):
        results = validate_vocabulary.run(CANDIDATE_PATH)
        self.assertEqual([c["check"] for c in results.failures], [])


class TokenReferenceIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb = load_json(repo_path("kb.ng.v2.4.json"))
        cls.rules = load_json(repo_path("rules.ng.v2.2.json"))
        cls.case_bank = load_json(repo_path("testing", "case_bank_v1.json"))
        cls.ids = {e["token_id"] for e in CANDIDATE["tokens"]}

    def test_kb_symptom_tokens_resolve(self):
        for condition in self.kb["conditions"]:
            for symptom in condition["symptoms"]:
                self.assertIn(symptom["token"], self.ids, condition["condition_id"])

    def test_kb_red_flag_tokens_resolve(self):
        for condition in self.kb["conditions"]:
            for flag in condition["red_flags"]:
                self.assertIn(flag, self.ids, condition["condition_id"])

    def test_kb_demographic_modifiers_resolve(self):
        for condition in self.kb["conditions"]:
            for modifier in condition.get("demographic_modifiers", []):
                self.assertIn(modifier["modifier"], self.ids, condition["condition_id"])

    def test_rules_tokens_resolve(self):
        for rule in self.rules["rules"]:
            self.assertIn(rule["token"], self.ids, rule["rule_id"])

    def test_all_global_red_flag_rules_resolve(self):
        globals_ = [r for r in self.rules["rules"] if r["applies_to"] == ["all"]]
        self.assertEqual(len(globals_), 13)
        for rule in globals_:
            self.assertIn(rule["token"], self.ids, rule["rule_id"])

    def test_question_flow_input_tokens_resolve(self):
        for case in self.case_bank["cases"]:
            for token in case["input_tokens"] + case["demographic_tokens"]:
                self.assertIn(token, self.ids, case["case_id"])

    def test_compatibility_report_has_no_failures(self):
        report = check_compatibility.build_report()
        self.assertEqual([c["check"] for c in report["checks"] if not c["passed"]], [])


class AmbiguityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(FIXTURES, "search", "synthetic_vocabulary_v1.json")
        cls.synthetic = load_json(path)
        cls.index = build_index(cls.synthetic)

    def test_ambiguous_query_resolves_to_nothing(self):
        result = self.index.resolve("shared quux")
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["resolved_token_id"])

    def test_ambiguous_query_is_not_scoring_eligible(self):
        self.assertFalse(self.index.resolve("shared quux")["scoring_eligible"])

    def test_ambiguous_query_returns_every_candidate(self):
        result = self.index.resolve("shared quux")
        self.assertEqual(
            [c["token_id"] for c in result["candidates"]], ["zorble_alpha", "zorble_beta"]
        )

    def test_candidate_ordering_is_deterministic(self):
        first = [c["token_id"] for c in self.index.resolve("shared quux")["candidates"]]
        for _ in range(5):
            rebuilt = build_index(self.synthetic)
            self.assertEqual(
                [c["token_id"] for c in rebuilt.resolve("shared quux")["candidates"]], first
            )

    def test_exact_token_id_beats_a_colliding_label(self):
        result = self.index.resolve("quibble_widget")
        self.assertEqual(result["status"], "exact_canonical")
        self.assertEqual(result["resolved_token_id"], "quibble_widget")

    def test_label_collision_is_ambiguous(self):
        self.assertEqual(self.index.resolve("quibble widget")["status"], "ambiguous")

    def test_unique_alias_resolves(self):
        result = self.index.resolve("beta only")
        self.assertEqual(result["status"], "exact_alias")
        self.assertEqual(result["resolved_token_id"], "zorble_beta")

    def test_only_single_candidate_statuses_are_scoreable(self):
        for query in ["zorble_alpha", "beta only", "frobnitz!", "shared quux", "nothing here"]:
            result = self.index.resolve(query)
            self.assertEqual(
                result["scoring_eligible"], result["resolved_token_id"] is not None, query
            )

    def test_real_candidate_has_no_ambiguous_forms(self):
        multi = {
            form: ids
            for form, ids in CANDIDATE["search_index"]["normalized_forms"].items()
            if len(ids) > 1
        }
        self.assertEqual(multi, {})


class SearchFixtureTests(unittest.TestCase):
    def _run(self, filename, index):
        fixture = load_json(os.path.join(FIXTURES, "search", filename))
        for case in fixture["cases"]:
            with self.subTest(query=case["query"]):
                result = index.resolve(case["query"])
                expected = case["expected"]
                self.assertEqual(result["status"], expected["status"])
                self.assertEqual(result["query_normalized"], expected["query_normalized"])
                self.assertEqual(result["resolved_token_id"], expected["resolved_token_id"])
                self.assertEqual(result["scoring_eligible"], expected["scoring_eligible"])
                self.assertEqual(
                    [c["token_id"] for c in result["candidates"]], expected["candidate_token_ids"]
                )

    def test_search_cases(self):
        self._run("search_cases_v1.json", INDEX)

    def test_ambiguity_cases(self):
        synthetic = load_json(os.path.join(FIXTURES, "search", "synthetic_vocabulary_v1.json"))
        self._run("ambiguity_cases_v1.json", build_index(synthetic))

    def test_negation_never_resolves_to_the_bare_symptom(self):
        for query in ["no fever", "not fever", "without fever", "fever free"]:
            result = INDEX.resolve(query)
            self.assertNotEqual(result["resolved_token_id"], "fever", query)

    def test_no_fuzzy_matching(self):
        for query in ["feve", "fevar", "fevers", "ffever"]:
            self.assertEqual(INDEX.resolve(query)["status"], "no_match", query)

    def test_no_substring_matching(self):
        self.assertEqual(INDEX.resolve("i have a fever today")["status"], "no_match")

    def test_unknown_term(self):
        self.assertEqual(INDEX.resolve("zzzznotatoken")["status"], "no_match")

    def test_empty_and_whitespace(self):
        for query in ["", "   ", "\t", "!!!"]:
            result = INDEX.resolve(query)
            self.assertEqual(result["status"], "no_match")
            self.assertIsNone(result["resolved_token_id"])

    def test_every_token_id_resolves_to_itself(self):
        for entry in CANDIDATE["tokens"]:
            result = INDEX.resolve(entry["token_id"])
            self.assertEqual(result["status"], "exact_canonical")
            self.assertEqual(result["resolved_token_id"], entry["token_id"])

    def test_shipped_search_index_matches_the_resolver(self):
        self.assertEqual(INDEX.normalized_forms(), CANDIDATE["search_index"]["normalized_forms"])

    def test_offline_load_needs_only_the_artifact_file(self):
        """Resolution must work from the file alone — no network, no sidecar."""
        with open(CANDIDATE_PATH, "rb") as handle:
            artifact = json.loads(handle.read().decode("utf-8"))
        index = build_index(artifact)
        self.assertEqual(index.resolve("chest_pain")["resolved_token_id"], "chest_pain")

    def test_index_lookup_matches_resolver_for_every_shipped_form(self):
        for form, ids in CANDIDATE["search_index"]["normalized_forms"].items():
            result = INDEX.resolve(form)
            self.assertEqual([c["token_id"] for c in result["candidates"]], ids, form)


class OldConsumerCompatibilityTests(unittest.TestCase):
    """A schema 1.0 consumer must observe no change at all."""

    def test_legacy_arrays_are_byte_identical(self):
        for category in CATEGORIES:
            self.assertEqual(CANDIDATE[category], BASELINE[category], category)

    def test_mobile_read_surface_is_unchanged(self):
        # lib/core/engine/red_flag_evaluator.dart reads exactly these two keys.
        for key in ["symptom_tokens", "red_flag_tokens"]:
            self.assertEqual(CANDIDATE[key], BASELINE[key], key)

    def test_mobile_valid_input_token_set_is_unchanged(self):
        def valid(artifact):
            return set(artifact["symptom_tokens"]) | set(artifact["red_flag_tokens"])

        self.assertEqual(valid(CANDIDATE), valid(BASELINE))

    def test_simulated_old_consumer_reads_the_candidate(self):
        """Reproduces RedFlagEvaluator's token-set construction verbatim."""

        def build_valid_tokens(token_dictionary):
            valid = set()
            for key in ["symptom_tokens", "red_flag_tokens"]:
                value = token_dictionary.get(key)
                if isinstance(value, list):
                    valid.update(v for v in value if isinstance(v, str))
            return valid

        self.assertEqual(build_valid_tokens(CANDIDATE), build_valid_tokens(BASELINE))

    def test_old_consumer_ignores_new_keys_without_error(self):
        known = set(CATEGORIES) | {"_metadata"}
        new_keys = set(CANDIDATE) - known
        self.assertEqual(new_keys, {"tokens", "body_areas", "complaint_groups", "search_index"})

    def test_new_metadata_keys_do_not_disturb_the_legacy_metadata(self):
        self.assertEqual(CANDIDATE["_metadata"]["legacy_metadata"], BASELINE["_metadata"])


class VersionNegotiationTests(unittest.TestCase):
    def test_candidate_declares_schema_2_0(self):
        self.assertEqual(CANDIDATE["_metadata"]["schema_version"], "2.0")

    def test_candidate_declares_artifact_version_2_0(self):
        self.assertEqual(CANDIDATE["_metadata"]["version"], "2.0")

    def test_artifact_id_is_unchanged(self):
        self.assertEqual(CANDIDATE["_metadata"]["artifact_id"], BASELINE["_metadata"]["artifact_id"])

    def test_filename_encodes_the_version(self):
        self.assertEqual(os.path.basename(CANDIDATE_PATH), "token_dictionary.ng.v2.0.json")

    def test_rollback_target_is_the_frozen_baseline(self):
        rollback = CANDIDATE["_metadata"]["rollback_target"]
        self.assertEqual(rollback["version"], "1.1")
        self.assertEqual(rollback["file"], "token_dictionary.ng.v1.1.json")
        self.assertEqual(rollback["sha256"], FROZEN_HASHES["token_dictionary.ng.v1.1.json"])

    def test_source_artifact_hash_matches_the_baseline_on_disk(self):
        self.assertEqual(
            CANDIDATE["_metadata"]["source_artifact"]["sha256"], sha256_file(BASELINE_PATH)
        )

    def test_compatible_consumers_names_the_frozen_versions(self):
        compatible = CANDIDATE["_metadata"]["compatible_consumers"]
        self.assertEqual(compatible["knowledge_base"], ["2.4"])
        self.assertEqual(compatible["rules"], ["2.2"])

    def test_version_is_a_strict_increase_over_the_baseline(self):
        def parts(value):
            return tuple(int(p) for p in value.split("."))

        self.assertGreater(parts(CANDIDATE["_metadata"]["version"]), parts(BASELINE["_metadata"]["version"]))


class PublicationSafetyTests(unittest.TestCase):
    def test_release_status_is_candidate_unapproved(self):
        self.assertEqual(CANDIDATE["_metadata"]["release_status"], "candidate_unapproved")

    def test_no_clinical_approval_is_claimed(self):
        review = CANDIDATE["_metadata"]["clinical_review"]
        self.assertEqual(review["status"], "not_reviewed")
        self.assertIsNone(review["reviewer"])
        self.assertIsNone(review["review_date"])
        self.assertIsNone(review["evidence"])

    def test_release_date_is_null(self):
        self.assertIsNone(CANDIDATE["_metadata"]["release_date"])

    def test_candidate_is_not_at_the_published_location(self):
        self.assertFalse(os.path.exists(repo_path("token_dictionary.ng.v2.0.json")))

    def test_candidate_lives_under_the_candidate_directory(self):
        self.assertTrue(CANDIDATE_PATH.startswith(repo_path("candidate")))

    def test_diff_classification_reports_no_blocking_change(self):
        import classify_vocabulary_diff

        result = classify_vocabulary_diff.classify(BASELINE, CANDIDATE)
        self.assertEqual(result["blocking_classifications"], [])
        self.assertEqual(result["classifications_present"], ["search_only_metadata"])

    def test_diff_report_still_refuses_publication(self):
        import classify_vocabulary_diff

        diff_report, _ = classify_vocabulary_diff.build_reports(BASELINE_PATH, CANDIDATE_PATH)
        self.assertFalse(diff_report["publication_decision"]["may_publish"])


class NoPhiTests(unittest.TestCase):
    """No PHI and no real-user assessment data may enter the candidate."""

    FORBIDDEN_KEYS = [
        "name", "first_name", "last_name", "dob", "date_of_birth", "phone",
        "email", "address", "patient", "user_id", "device_id", "session",
        "assessment_id", "latitude", "longitude", "nin", "bvn",
    ]

    def test_no_phi_shaped_keys_anywhere(self):
        found = []

        def walk(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key.lower() in self.FORBIDDEN_KEYS:
                        found.append("%s.%s" % (path, key))
                    walk(value, "%s.%s" % (path, key))
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    walk(item, "%s[%d]" % (path, i))

        walk(CANDIDATE, "$")
        self.assertEqual(found, [])

    def test_candidate_contains_only_baseline_token_identifiers(self):
        baseline_ids = {t for c in CATEGORIES for t in BASELINE[c]}
        self.assertEqual({e["token_id"] for e in CANDIDATE["tokens"]}, baseline_ids)

    def test_no_free_text_user_input_field_exists(self):
        for entry in CANDIDATE["tokens"]:
            self.assertEqual(
                set(entry), {"token_id", "category", "clinical_identity", "display", "search", "associations", "review"}
            )


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
