#!/usr/bin/env python3
"""W3 Adaptive Question Flow test suite.

    python3 testing/questions/test_question_flow.py

Standard-library unittest only. Covers the W3 "Tests Required" list:
frozen-baseline hashes, schema, condition language, deterministic ordering,
cycle/reachability, path enumeration and length, skip semantics, answer-edit
invalidation, offline restoration, red-flag precedence and timing, token-output
parity, current-flow compatibility, valid and invalid fixtures, publication
fail-closed, deterministic generation and a PHI scan.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from qflow.conditions import (  # noqa: E402
    AssessmentState,
    ConditionError,
    FIELDS,
    OPERATORS,
    evaluate,
    is_never_satisfiable,
    validate as validate_condition,
)
from qflow.dartparse import BASELINE_DIR, VENDORED_FILES, parse_all  # noqa: E402
from vocab.artifact_io import (  # noqa: E402
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
)

import build_question_candidate as bqc  # noqa: E402
import build_question_fixtures as bqf  # noqa: E402
import check_question_compatibility as cqc  # noqa: E402
import report_qb002_evidence as rqe  # noqa: E402
import report_question_baseline as rqb  # noqa: E402
import validate_question_flow as vqf  # noqa: E402

CANDIDATE_PATH = repo_path("candidate", "question_flow.ng.v1.0.json")
CANDIDATE = load_json(CANDIDATE_PATH)
PARSED = parse_all(repo_path())
FIXTURES = os.path.join(HERE, "fixtures")

FROZEN = {
    "token_dictionary.ng.v1.1.json": "0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019",
    "kb.ng.v2.4.json": "6c00d8257f8417e86bd5e237630bf8a4623ad72e2e46b1b071dd447c067cec2b",
    "rules.ng.v2.2.json": "1d27e854cba95b179577a88f92445400f494a7fe8e6a53a60fcaa98b3870d1c4",
    "testing/case_bank_v1.json": "c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834",
    "testing/known_findings.json": "fadaea063303ecd27a90c233dba7782f8840c85aef4e3a7cca61b1e4793537ed",
    "candidate/token_dictionary.ng.v2.0.json": "07f935967acb1d5515cb53ffd1c8e39b59b8daf85c67cf36fa3e25094e34cd2d",
}


class FrozenBaselineTests(unittest.TestCase):
    def test_frozen_clinical_artifacts_unchanged(self):
        for filename, expected in FROZEN.items():
            with self.subTest(artifact=filename):
                self.assertEqual(sha256_file(repo_path(filename)), expected)

    def test_vendored_sources_are_all_present(self):
        for name in VENDORED_FILES:
            self.assertTrue(os.path.exists(repo_path(BASELINE_DIR, name)), name)

    def test_baseline_report_records_every_vendored_hash(self):
        report = rqb.build_report()
        recorded = {f["vendored_file"]: f["sha256"] for f in report["sources"]["files"]}
        for name in VENDORED_FILES:
            self.assertEqual(recorded[name], sha256_file(repo_path(BASELINE_DIR, name)))

    def test_baseline_records_that_no_question_artifact_exists(self):
        report = rqb.build_report()
        self.assertFalse(report["architecture_finding"]["question_artifact_exists"])

    def test_baseline_records_known_defects(self):
        report = rqb.build_report()
        ids = {d["id"] for d in report["known_defects_and_inconsistencies"]}
        # The red-flag timing gap must never quietly disappear from the record.
        self.assertIn("QB-002", ids)


class ConditionLanguageTests(unittest.TestCase):
    def test_all_and_any_empty_semantics(self):
        state = AssessmentState()
        self.assertTrue(evaluate({"all": []}, state))
        self.assertFalse(evaluate({"any": []}, state))

    def test_token_present_and_absent(self):
        state = AssessmentState(tokens={"fever"})
        self.assertTrue(evaluate({"token_present": "fever"}, state))
        self.assertFalse(evaluate({"token_present": "cough"}, state))
        self.assertTrue(evaluate({"token_absent": "cough"}, state))
        self.assertFalse(evaluate({"token_absent": "fever"}, state))

    def test_not_all_any_nesting(self):
        state = AssessmentState(tokens={"fever", "chills"})
        self.assertTrue(evaluate(
            {"all": [{"token_present": "fever"},
                     {"not": {"token_present": "cough"}},
                     {"any": [{"token_present": "chills"}, {"token_present": "x"}]}]}, state))

    def test_equals_and_one_of(self):
        state = AssessmentState(sex="female", body_area="Chest")
        self.assertTrue(evaluate({"equals": {"field": "sex", "value": "female"}}, state))
        self.assertTrue(evaluate({"one_of": {"field": "body_area", "values": ["Chest", "Head"]}}, state))
        self.assertFalse(evaluate({"one_of": {"field": "body_area", "values": ["Head"]}}, state))

    def test_prior_answer_equals(self):
        state = AssessmentState(answers={"Q-demo-sex": "Q-demo-sex::female"})
        self.assertTrue(evaluate(
            {"prior_answer_equals": {"question_id": "Q-demo-sex",
                                     "answer_option_id": "Q-demo-sex::female"}}, state))
        self.assertFalse(evaluate(
            {"prior_answer_equals": {"question_id": "Q-demo-sex",
                                     "answer_option_id": "Q-demo-sex::male"}}, state))

    def test_sex_and_pregnancy(self):
        self.assertTrue(evaluate({"sex": "female"}, AssessmentState(sex="female")))
        self.assertFalse(evaluate({"sex": "female"}, AssessmentState(sex="male")))
        self.assertTrue(evaluate({"pregnancy": True}, AssessmentState(pregnancy=True)))
        self.assertTrue(evaluate({"pregnancy": False}, AssessmentState(pregnancy=False)))

    def test_unknown_sex_and_pregnancy_fail_closed(self):
        """An unknown answer satisfies neither branch — it is not 'no'."""
        self.assertFalse(evaluate({"sex": "female"}, AssessmentState(sex=None)))
        self.assertFalse(evaluate({"pregnancy": True}, AssessmentState(pregnancy=None)))
        self.assertFalse(evaluate({"pregnancy": False}, AssessmentState(pregnancy=None)))

    def test_age_range(self):
        self.assertTrue(evaluate({"age_range": {"max_years": 5}}, AssessmentState(age_years=3)))
        self.assertFalse(evaluate({"age_range": {"max_years": 5}}, AssessmentState(age_years=9)))
        self.assertTrue(evaluate({"age_range": {"min_years": 18, "max_years": 40}},
                                 AssessmentState(age_years=30)))

    def test_unknown_age_fails_closed(self):
        self.assertFalse(evaluate({"age_range": {"max_years": 5}}, AssessmentState()))

    def test_always_and_never(self):
        self.assertTrue(evaluate({"always": True}, AssessmentState()))
        self.assertFalse(evaluate({"never": True}, AssessmentState()))

    def test_unknown_operator_is_rejected(self):
        for bad in [{"matches_regex": "x"}, {"score_above": 5}, {"fuzzy": "fever"}]:
            with self.assertRaises(ConditionError):
                evaluate(bad, AssessmentState())

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(ConditionError):
            evaluate({"equals": {"field": "diagnosis", "value": "malaria"}}, AssessmentState())

    def test_multiple_operator_keys_rejected(self):
        with self.assertRaises(ConditionError):
            evaluate({"token_present": "fever", "token_absent": "cough"}, AssessmentState())

    def test_operand_type_errors_rejected(self):
        with self.assertRaises(ConditionError):
            evaluate({"token_present": 42}, AssessmentState())
        with self.assertRaises(ConditionError):
            evaluate({"pregnancy": "yes"}, AssessmentState())
        with self.assertRaises(ConditionError):
            evaluate({"sex": "other"}, AssessmentState())

    def test_evaluation_is_deterministic_and_pure(self):
        condition = {"all": [{"token_present": "fever"}, {"sex": "female"}]}
        state = AssessmentState(tokens={"fever"}, sex="female")
        self.assertEqual([evaluate(condition, state) for _ in range(10)], [True] * 10)

    def test_validate_reports_unknown_token(self):
        errors = validate_condition({"token_present": "nope"}, known_tokens={"fever"})
        self.assertTrue(errors)

    def test_is_never_satisfiable(self):
        self.assertTrue(is_never_satisfiable({"never": True}))
        self.assertTrue(is_never_satisfiable(
            {"all": [{"token_present": "fever"}, {"token_absent": "fever"}]}))
        self.assertFalse(is_never_satisfiable({"token_present": "fever"}))

    def test_declared_operator_set_matches_the_artifact(self):
        self.assertEqual(set(CANDIDATE["condition_language"]["operators"]), set(OPERATORS))
        self.assertEqual(set(CANDIDATE["condition_language"]["fields"]), set(FIELDS))

    def test_no_free_text_or_regex_operator_exists(self):
        for forbidden in ("regex", "matches", "contains", "like", "similarity", "score"):
            self.assertNotIn(forbidden, OPERATORS)


class SchemaAndValidationTests(unittest.TestCase):
    def test_candidate_passes_every_validator(self):
        results, _, _ = vqf.run(CANDIDATE_PATH)
        self.assertEqual([c["check"] for c in results.failures], [])

    def test_compatibility_has_no_failures(self):
        report = cqc.build_report()
        self.assertEqual([c["check"] for c in report["checks"] if not c["passed"]], [])

    def test_every_invalid_fixture_fails_its_named_check(self):
        directory = os.path.join(FIXTURES, "invalid")
        index = load_json(os.path.join(directory, "index.json"))
        self.assertTrue(index["fixtures"])
        for fixture in index["fixtures"]:
            with self.subTest(fixture=fixture["file"]):
                results, _, _ = vqf.run(os.path.join(directory, fixture["file"]))
                failed = {"%s:%s" % (c["group"], c["check"]) for c in results.checks
                          if not c["passed"]}
                self.assertIn(fixture["expected_failing_check"], failed)

    def test_invalid_fixtures_are_labelled_synthetic(self):
        directory = os.path.join(FIXTURES, "invalid")
        for fixture in load_json(os.path.join(directory, "index.json"))["fixtures"]:
            artifact = load_json(os.path.join(directory, fixture["file"]))
            self.assertTrue(artifact["_metadata"].get("SYNTHETIC_FIXTURE"))


class DeterminismTests(unittest.TestCase):
    def test_generation_is_deterministic(self):
        first = dump_artifact_bytes(bqc.build_candidate(bqc.DEFAULT_GENERATED_AT))
        second = dump_artifact_bytes(bqc.build_candidate(bqc.DEFAULT_GENERATED_AT))
        self.assertEqual(first, second)

    def test_committed_candidate_matches_a_fresh_build(self):
        rebuilt = dump_artifact_bytes(bqc.build_candidate(bqc.DEFAULT_GENERATED_AT))
        with open(CANDIDATE_PATH, "rb") as handle:
            self.assertEqual(rebuilt, handle.read())

    def test_hash_is_reproducible(self):
        rebuilt = dump_artifact_bytes(bqc.build_candidate(bqc.DEFAULT_GENERATED_AT))
        self.assertEqual(sha256_bytes(rebuilt), sha256_file(CANDIDATE_PATH))

    def test_ordering_never_depends_on_list_order(self):
        forward = sorted(CANDIDATE["questions"], key=vqf.order_key)
        backward = sorted(list(reversed(CANDIDATE["questions"])), key=vqf.order_key)
        self.assertEqual([q["question_id"] for q in forward],
                         [q["question_id"] for q in backward])

    def test_every_question_declares_a_tie_break(self):
        for q in CANDIDATE["questions"]:
            self.assertTrue(q.get("tie_break_key"), q["question_id"])

    def test_order_keys_are_unique(self):
        keys = [vqf.order_key(q) for q in CANDIDATE["questions"]]
        self.assertEqual(len(keys), len(set(keys)))

    def test_eligibility_is_stable_across_repeated_evaluation(self):
        state = AssessmentState(tokens={"headache", "fever"}, sex="male")
        first = [q["question_id"] for q in vqf.eligible(CANDIDATE["questions"], state)]
        for _ in range(5):
            self.assertEqual(
                [q["question_id"] for q in vqf.eligible(CANDIDATE["questions"], state)], first)


class GraphAndPathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = vqf.analyse_graph(CANDIDATE)

    def test_no_unreachable_question(self):
        self.assertEqual(self.analysis["unreachable_questions"], [])

    def test_no_dead_answer_option(self):
        self.assertEqual(self.analysis["dead_answer_options"], [])

    def test_no_path_exceeds_the_limit_except_via_red_flag_exemption(self):
        self.assertEqual(self.analysis["paths_exceeding_followup_limit"], [])

    def test_no_red_flag_question_is_ever_truncated(self):
        self.assertEqual(self.analysis["paths_where_a_red_flag_question_was_dropped"], [])

    def test_red_flag_questions_never_queue_behind_ordinary_ones(self):
        self.assertEqual(
            self.analysis["paths_with_a_red_flag_question_behind_an_ordinary_one"], [])

    def test_path_length_stays_within_the_measured_limit(self):
        lengths = self.analysis["path_lengths"]
        self.assertLessEqual(lengths["max"], lengths["limit"])

    def test_exploration_bound_is_declared_honestly(self):
        exploration = self.analysis["exploration"]
        self.assertFalse(exploration["exhaustive_over_full_state_space"])
        self.assertTrue(exploration["uncovered_state_space"])
        self.assertGreater(exploration["combinations_explored"], 100)

    def test_no_cycle_in_the_branch_graph(self):
        results, _, _ = vqf.run(CANDIDATE_PATH)
        cycle_check = [c for c in results.checks if c["check"] == "no_branch_cycles"]
        self.assertTrue(cycle_check and cycle_check[0]["passed"])


class RedFlagPrecedenceTests(unittest.TestCase):
    def test_every_red_flag_affecting_question_evaluates_immediately(self):
        for q in CANDIDATE["questions"]:
            if q["effects"]["affects_red_flags"]:
                self.assertTrue(q["red_flag_evaluation"]["evaluate_after_answer"], q["question_id"])
                self.assertTrue(q["red_flag_evaluation"]["blocks_next_question"], q["question_id"])

    def test_red_flag_hook_and_effect_agree(self):
        for q in CANDIDATE["questions"]:
            self.assertEqual(q["effects"]["affects_red_flags"],
                             q["red_flag_evaluation"]["can_affect_red_flag"], q["question_id"])

    def test_red_flag_questions_sort_first(self):
        state = AssessmentState(tokens={"difficulty_breathing", "headache", "fever"})
        ordered = vqf.eligible(CANDIDATE["questions"], state)
        followups = [q for q in ordered if q["clinical_role"] not in
                     ("demographic", "body_area", "symptom_picker")]
        seen_ordinary = False
        for q in followups:
            if q["red_flag_evaluation"]["can_affect_red_flag"]:
                self.assertFalse(seen_ordinary, "%s queued behind an ordinary question"
                                 % q["question_id"])
            else:
                seen_ordinary = True

    def test_truncation_exemption_is_a_schema_constant(self):
        self.assertIs(CANDIDATE["path_controls"]["red_flag_questions_exempt_from_truncation"], True)

    def test_clarifier_is_suppressed_when_the_red_flag_is_already_selected(self):
        for clarifier in PARSED["red_flag_clarifiers"]:
            q = next(x for x in CANDIDATE["questions"]
                     if x["question_id"] == "Q-clarifier-%s" % clarifier["red_flag_token"])
            state = AssessmentState(tokens={clarifier["trigger_tokens"][0],
                                            clarifier["red_flag_token"]})
            self.assertFalse(evaluate(q["trigger_condition"], state))

    def test_only_yes_produces_the_red_flag_token(self):
        for clarifier in PARSED["red_flag_clarifiers"]:
            q = next(x for x in CANDIDATE["questions"]
                     if x["question_id"] == "Q-clarifier-%s" % clarifier["red_flag_token"])
            yes = next(o for o in q["answer_options"] if o["label"] == "Yes")
            no = next(o for o in q["answer_options"] if o["label"] == "No")
            self.assertEqual(yes["produces_tokens"], [clarifier["red_flag_token"]])
            self.assertEqual(no["produces_tokens"], [])


class SkipSemanticsTests(unittest.TestCase):
    def test_no_required_question_is_skippable(self):
        for q in CANDIDATE["questions"]:
            if q["required"]:
                self.assertFalse(q["skippable"], q["question_id"])

    def test_no_skip_sentinel_produces_a_token(self):
        for q in CANDIDATE["questions"]:
            for option in q["answer_options"]:
                if option["is_skip_sentinel"]:
                    self.assertEqual(option["produces_tokens"], [], option["answer_option_id"])

    def test_projection_introduces_no_skip(self):
        """The schema supports skipping; the projection uses none."""
        self.assertTrue(all(not q["skippable"] for q in CANDIDATE["questions"]))
        self.assertTrue(all(not o["is_skip_sentinel"]
                            for q in CANDIDATE["questions"] for o in q["answer_options"]))

    def test_skip_states_are_distinct_from_answers(self):
        lifecycle = load_json(
            os.path.join(FIXTURES, "paths", "path_fixtures_v1.json"))["lifecycle_states"]
        for state in ["question_not_applicable", "optional_skipped", "required_unanswered",
                      "invalidated_by_edit", "assessment_abandoned",
                      "assessment_interrupted_by_red_flag", "assessment_completed"]:
            self.assertIn(state, lifecycle)


class AnswerEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_json(os.path.join(FIXTURES, "paths", "path_fixtures_v1.json"))

    def test_edit_fixtures_reproduce(self):
        for case in self.fixture["edit_cases"]:
            with self.subTest(fixture=case["fixture_id"]):
                after = AssessmentState(
                    tokens=case["after"]["tokens"], sex=case["after"]["sex"],
                    pregnancy=case["after"]["pregnancy"])
                self.assertEqual(bqf.path_for(CANDIDATE, after), case["after"]["path"])

    def test_changing_sex_invalidates_pregnancy(self):
        sex = next(q for q in CANDIDATE["questions"] if q["question_id"] == "Q-demo-sex")
        self.assertIn("Q-demo-pregnancy", sex["invalidates_on_change"])

    def test_pregnancy_question_disappears_for_male(self):
        pregnancy = next(q for q in CANDIDATE["questions"]
                         if q["question_id"] == "Q-demo-pregnancy")
        self.assertTrue(evaluate(pregnancy["trigger_condition"], AssessmentState(sex="female")))
        self.assertFalse(evaluate(pregnancy["trigger_condition"], AssessmentState(sex="male")))

    def test_removing_a_symptom_retires_its_followups(self):
        before = AssessmentState(tokens={"headache", "fever"})
        after = AssessmentState(tokens={"fever"})
        before_ids = {q["question_id"] for q in vqf.eligible(CANDIDATE["questions"], before)}
        after_ids = {q["question_id"] for q in vqf.eligible(CANDIDATE["questions"], after)}
        retired = before_ids - after_ids
        self.assertTrue(retired)
        self.assertTrue(all("headache" in q for q in retired), retired)

    def test_invalidation_targets_all_resolve(self):
        ids = {q["question_id"] for q in CANDIDATE["questions"]}
        for q in CANDIDATE["questions"]:
            for target in q["invalidates_on_change"]:
                if not target.startswith("<"):
                    self.assertIn(target, ids, "%s -> %s" % (q["question_id"], target))

    def test_no_question_invalidates_itself(self):
        for q in CANDIDATE["questions"]:
            self.assertNotIn(q["question_id"], q["invalidates_on_change"])

    def test_recomputation_after_edit_is_idempotent(self):
        """Re-running invalidation must converge, not oscillate."""
        state = AssessmentState(tokens={"fever"})
        first = bqf.path_for(CANDIDATE, state)
        for _ in range(5):
            self.assertEqual(bqf.path_for(CANDIDATE, state), first)


class PathFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = load_json(os.path.join(FIXTURES, "paths", "path_fixtures_v1.json"))

    def test_every_path_fixture_reproduces(self):
        for case in self.fixture["cases"]:
            with self.subTest(fixture=case["fixture_id"]):
                state = AssessmentState(
                    tokens=case["input_state"]["tokens"],
                    sex=case["input_state"]["sex"],
                    age_token=case["input_state"]["age_token"],
                    pregnancy=case["input_state"]["pregnancy"],
                    body_area=case["input_state"]["body_area"],
                    assessment_phase=case["input_state"]["assessment_phase"])
                self.assertEqual(bqf.path_for(CANDIDATE, state), case["expected"])

    def test_male_path_never_presents_pregnancy(self):
        case = next(c for c in self.fixture["cases"] if c["fixture_id"] == "male_pregnancy_skipped")
        self.assertNotIn("Q-demo-pregnancy", case["expected"]["demographic_questions"])

    def test_female_path_presents_pregnancy(self):
        case = next(c for c in self.fixture["cases"]
                    if c["fixture_id"] == "female_pregnancy_applicable")
        self.assertIn("Q-demo-pregnancy", case["expected"]["demographic_questions"])

    def test_offline_restoration_needs_only_state(self):
        """Eligibility must be a function of state alone — no session, no network."""
        with open(CANDIDATE_PATH, "rb") as handle:
            artifact = json.loads(handle.read().decode("utf-8"))
        state = AssessmentState(tokens={"fever", "vomiting"}, sex="female", pregnancy=True,
                                assessment_phase="restored")
        restored = bqf.path_for(artifact, state)
        fresh = bqf.path_for(artifact, AssessmentState(
            tokens={"fever", "vomiting"}, sex="female", pregnancy=True))
        self.assertEqual(restored["presented_followups"], fresh["presented_followups"])

    def test_shortest_and_longest_paths_are_bounded(self):
        limit = CANDIDATE["path_controls"]["max_followup_questions"]
        for case in self.fixture["cases"]:
            self.assertLessEqual(case["expected"]["followup_count"], limit, case["fixture_id"])


class TokenParityTests(unittest.TestCase):
    def test_no_question_was_added_or_removed(self):
        report = cqc.build_report()
        for name in ("every_existing_question_is_present", "no_question_was_added"):
            check = next(c for c in report["checks"] if c["check"] == name)
            self.assertTrue(check["passed"], check["detail"])

    def test_token_output_universe_is_identical(self):
        report = cqc.build_report()
        check = next(c for c in report["checks"]
                     if c["check"] == "token_output_universe_is_identical")
        self.assertTrue(check["passed"], check["detail"])

    def test_every_produced_token_resolves_in_token_dictionary_1_1(self):
        known = vqf.token_universe()
        for q in CANDIDATE["questions"]:
            for option in q["answer_options"]:
                for token in option["produces_tokens"]:
                    self.assertIn(token, known, option["answer_option_id"])


class PublicationSafetyTests(unittest.TestCase):
    def test_release_status_is_candidate_unapproved(self):
        self.assertEqual(CANDIDATE["_metadata"]["release_status"], "candidate_unapproved")

    def test_may_publish_is_false(self):
        self.assertIs(CANDIDATE["_metadata"]["may_publish"], False)

    def test_no_clinical_review_claimed(self):
        review = CANDIDATE["_metadata"]["clinical_review"]
        self.assertEqual(review["status"], "not_reviewed")
        self.assertIsNone(review["reviewer"])
        self.assertIsNone(review["evidence"])

    def test_no_question_content_is_marked_approved(self):
        for q in CANDIDATE["questions"]:
            self.assertFalse(q["content_ref"]["content_approved"], q["question_id"])

    def test_candidate_is_not_at_the_published_location(self):
        self.assertFalse(os.path.exists(repo_path("question_flow.ng.v1.0.json")))

    def test_vocabulary_2_0_is_declared_unused(self):
        self.assertIs(CANDIDATE["_metadata"]["vocabulary_2_0"]["used"], False)

    def test_path_thresholds_are_not_claimed_as_approved(self):
        controls = CANDIDATE["path_controls"]
        self.assertEqual(controls["thresholds_status"], "measured_from_implementation")
        self.assertIn("PENDING", controls["final_threshold_status"])

    def test_impedance_mismatches_are_recorded_not_hidden(self):
        mismatches = CANDIDATE["_metadata"]["impedance_mismatches"]
        self.assertEqual(len(mismatches), 7)
        ids = {m["id"] for m in mismatches}
        self.assertIn("IM-002", ids)  # the red-flag timing gap
        for mismatch in mismatches:
            self.assertIn("why_it_exists", mismatch)
            self.assertIn("required_review", mismatch)
            self.assertIn("classification", mismatch)
            self.assertIn("activation_blocker", mismatch)

    def test_parity_claim_does_not_overstate(self):
        claim = CANDIDATE["_metadata"]["parity_claim"]
        self.assertIn("NOT identical", claim)


class ImpedanceDisclosureTests(unittest.TestCase):
    """All seven mismatches disclosed, classified and disposed."""

    MISMATCHES = CANDIDATE["_metadata"]["impedance_mismatches"]

    def test_all_seven_are_enumerated(self):
        self.assertEqual([m["id"] for m in self.MISMATCHES],
                         ["IM-001", "IM-002", "IM-003", "IM-004", "IM-005", "IM-006", "IM-007"])

    def test_declared_count_matches(self):
        self.assertEqual(CANDIDATE["_metadata"]["impedance_mismatch_count"], len(self.MISMATCHES))

    def test_every_mismatch_is_fully_classified(self):
        keys = {"deterministic_only", "safety_affecting", "clinical_content_affecting",
                "path_affecting", "state_model_affecting", "artifact_model_only"}
        for m in self.MISMATCHES:
            self.assertEqual(set(m["classification"]), keys, m["id"])

    def test_no_mismatch_changes_clinical_content(self):
        """The stop condition. Content must be identical."""
        for m in self.MISMATCHES:
            self.assertFalse(m["classification"]["clinical_content_affecting"], m["id"])

    def test_every_mismatch_cites_a_baseline_source(self):
        for m in self.MISMATCHES:
            self.assertTrue(m["source"]["baseline"], m["id"])

    def test_every_mismatch_has_a_status_and_review(self):
        for m in self.MISMATCHES:
            self.assertTrue(m["status"], m["id"])
            self.assertTrue(m["required_review"], m["id"])
            self.assertIn("activation_blocker", m)

    def test_im_003_discloses_its_scoring_input_effect(self):
        """IM-003 can change which symptoms a user declares. Say so."""
        im003 = next(m for m in self.MISMATCHES if m["id"] == "IM-003")
        self.assertTrue(im003["classification"]["path_affecting"])
        self.assertIn("INDIRECTLY YES", str(im003["changes_token_output"]))
        self.assertTrue(im003["activation_blocker"])
        self.assertTrue(str(im003["status"]).startswith("deferred"))

    def test_im_003_cannot_raise_a_new_red_flag_clarifier(self):
        """Verified from the source, not asserted."""
        im003 = next(m for m in self.MISMATCHES if m["id"] == "IM-003")
        self.assertIn("NO", str(im003["changes_red_flag_content"]))
        triggers = {t for c in PARSED["red_flag_clarifiers"] for t in c["trigger_tokens"]}
        options = {opt for entries in PARSED["followup_question_map"]["entries"].values()
                   for e in entries if e["type"] == "additionalSymptoms" for opt in e["options"]}
        self.assertEqual(triggers & options, set())

    def test_im_002_is_the_only_safety_affecting_behaviour_change(self):
        changing = [m["id"] for m in self.MISMATCHES
                    if m["classification"]["safety_affecting"] and m["changes_production_behaviour"]]
        self.assertEqual(changing, ["IM-002"])


class EngineeringDispositionTests(unittest.TestCase):
    DISPOSITIONS = CANDIDATE["_metadata"]["engineering_dispositions"]

    def test_all_required_dispositions_recorded(self):
        for name in ["im_001_deterministic_ordering", "im_002_immediate_red_flag_evaluation",
                     "path_length_limit", "skip_behaviour", "distribution_model",
                     "question_wording", "im_003_adaptive_re_branching"]:
            self.assertIn(name, self.DISPOSITIONS["decisions"], name)

    def test_every_disposition_states_what_it_does_not_authorize(self):
        for name, decision in self.DISPOSITIONS["decisions"].items():
            self.assertTrue(decision.get("does_not_authorize"), name)

    def test_dispositions_are_engineering_authority_only(self):
        self.assertEqual(self.DISPOSITIONS["authority"], "engineering")
        self.assertIs(self.DISPOSITIONS["is_clinical_approval"], False)
        self.assertIs(self.DISPOSITIONS["is_product_approval"], False)

    def test_activation_remains_prohibited(self):
        activation = self.DISPOSITIONS["activation"]
        for gate in ("production", "public_beta", "external_beta",
                     "clinical_approval", "product_approval"):
            self.assertIs(activation[gate], False, gate)
        self.assertIs(activation["internal_engineering_evaluation"], True)

    def test_path_limit_fixed_at_5_everywhere(self):
        self.assertEqual(self.DISPOSITIONS["decisions"]["path_length_limit"]["value"], 5)
        self.assertEqual(CANDIDATE["path_controls"]["max_followup_questions"], 5)

    def test_distribution_is_internal_only(self):
        d = self.DISPOSITIONS["decisions"]["distribution_model"]
        for gate in ("backend_distribution", "config_entry", "r2_upload", "live_manifest_entry"):
            self.assertIs(d[gate], False, gate)

    def test_im_002_requires_evaluation_before_scoring(self):
        points = self.DISPOSITIONS["decisions"]["im_002_immediate_red_flag_evaluation"]["requires_evaluation"]
        self.assertEqual(len(points), 5)
        self.assertTrue(any("before scoring" in p for p in points))

    def test_wording_preserved_without_approval(self):
        self.assertIs(
            self.DISPOSITIONS["decisions"]["question_wording"]["content_approved"], False)


class QB002EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = rqe.build_report()

    def test_the_defect_reproduces(self):
        self.assertGreater(self.report["timing"]["worst_case_delay_in_questions"], 0)
        self.assertGreater(self.report["timing"]["scenarios_measured"], 0)

    def test_scoring_can_never_override_the_eventual_red_flag(self):
        self.assertIs(
            self.report["safety_analysis"]["can_scoring_override_the_eventual_red_flag"], False)

    def test_mobile_was_not_modified(self):
        self.assertIs(self.report["defect"]["mobile_unmodified"], True)
        self.assertIs(self.report["scope"]["mobile_modified"], False)
        self.assertIs(self.report["scope"]["fix_included_here"], False)

    def test_every_scenario_names_the_questions_asked_after_the_danger_sign(self):
        for scenario in self.report["timing"]["scenarios"]:
            self.assertEqual(len(scenario["questions_after_ids"]),
                             scenario["questions_presented_after_the_yes"])

    def test_interception_point_is_before_the_step_event(self):
        point = self.report["earliest_safe_interception_point"]
        self.assertIn("_onNext", point["point"])
        self.assertTrue(any("telemetry" in w or "step event" in w for w in point["why_here"]))


class PrivacyTests(unittest.TestCase):
    FORBIDDEN_KEYS = [
        "name", "first_name", "last_name", "dob", "date_of_birth", "phone", "email",
        "address", "patient", "user_id", "device_id", "session", "session_id",
        "assessment_id", "latitude", "longitude", "nin", "bvn", "msisdn", "ip",
    ]

    def test_no_phi_shaped_keys(self):
        found = []

        def walk(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key.lower() in self.FORBIDDEN_KEYS:
                        found.append("%s.%s" % (path, key))
                    walk(value, "%s.%s" % (path, key))
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, "%s[%d]" % (path, index))

        walk(CANDIDATE, "$")
        self.assertEqual(found, [])

    def test_no_free_text_answer_type_exists(self):
        for q in CANDIDATE["questions"]:
            self.assertIn(q["answer_value_type"], ("option_id", "option_id_set", "boolean"))

    def test_every_answer_is_an_enumerated_option(self):
        for q in CANDIDATE["questions"]:
            self.assertGreaterEqual(len(q["answer_options"]), 1, q["question_id"])

    def test_artifact_contains_no_real_user_data(self):
        """Only question definitions and already-published token identifiers."""
        known = vqf.token_universe()
        for q in CANDIDATE["questions"]:
            for option in q["answer_options"]:
                self.assertTrue(set(option["produces_tokens"]) <= known)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
