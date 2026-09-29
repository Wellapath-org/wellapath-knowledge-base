#!/usr/bin/env python3
"""Generate representative path fixtures and invalid fixtures.

    python3 tools/build_question_fixtures.py            # write
    python3 tools/build_question_fixtures.py --check    # fail if stale

Path fixtures are computed by the reference implementation against the real
candidate, so they lock in current behaviour: a change to ordering, triggering
or truncation has to be deliberate, because it breaks a fixture.

Every input is synthetic and spec-derived. No real-user assessment is used, and
no clinically meaningful symptom combination is invented to pad coverage — each
scenario combines tokens that already exist and already trigger the questions
they trigger.

Invalid fixtures are the candidate with exactly one defect applied, each
targeting the specific validator check named in its `EXPECTED_FAILURE`.
"""

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from qflow.conditions import AssessmentState
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

import validate_question_flow as vqf

CANDIDATE = repo_path("candidate", "question_flow.ng.v1.0.json")
PATHS_DIR = repo_path("testing", "questions", "fixtures", "paths")
INVALID_DIR = repo_path("testing", "questions", "fixtures", "invalid")

# (name, description, state kwargs). Every token below is already a picker or
# trigger token in the candidate; nothing new is introduced.
SCENARIOS = [
    ("male_pregnancy_skipped", "Male path — the pregnancy question is not applicable and is never presented",
     {"sex": "male", "age_token": "adults", "tokens": ["headache"]}),
    ("female_pregnancy_applicable", "Female path — pregnancy applicable and answered yes",
     {"sex": "female", "age_token": "adults", "pregnancy": True, "tokens": ["headache"]}),
    ("female_pregnancy_not_applicable", "Female path — pregnancy applicable and answered no",
     {"sex": "female", "age_token": "adults", "pregnancy": False, "tokens": ["headache"]}),
    ("shortest_valid_path", "Single symptom with no authored follow-up — the default duration question only",
     {"sex": "male", "age_token": "adults", "tokens": ["boils"]}),
    ("longest_reachable_path", "Three clarifiers plus severity, duration and additional symptoms — truncation applies",
     {"sex": "female", "age_token": "adults", "pregnancy": False,
      "tokens": ["difficulty_breathing", "poor_feeding", "bleeding", "headache", "fever"]}),
    ("multiple_eligible_followups", "Two authored tokens both offering severity and duration",
     {"sex": "male", "age_token": "adults", "tokens": ["headache", "body_pain"]}),
    ("no_eligible_followup", "No symptom selected — no follow-up question is eligible",
     {"sex": "male", "age_token": "adults", "tokens": []}),
    ("branch_convergence", "Two different symptoms converging on the same duration question",
     {"sex": "male", "age_token": "adults", "tokens": ["fever", "chills"]}),
    ("global_red_flag_clarifier", "A near-miss token raises its clarifier",
     {"sex": "male", "age_token": "adults", "tokens": ["difficulty_breathing"]}),
    ("red_flag_already_selected", "The red flag itself is selected, so its clarifier is suppressed",
     {"sex": "male", "age_token": "adults",
      "tokens": ["difficulty_breathing", "breathlessness_at_rest"]}),
    ("condition_specific_context", "Chest indrawing — a paediatric severity token with an authored follow-up",
     {"sex": "male", "age_token": "children_under_5", "tokens": ["chest_indrawing_severe"]}),
    ("demographic_escalation_context", "Under-5 with fever — demographic token present alongside a follow-up",
     {"sex": "female", "age_token": "children_under_5", "pregnancy": False, "tokens": ["fever"]}),
    ("body_area_general", "General body area with a systemic symptom",
     {"sex": "male", "age_token": "adults", "body_area": "General", "tokens": ["weakness"]}),
    ("body_area_head", "Head body area",
     {"sex": "male", "age_token": "adults", "body_area": "Head", "tokens": ["headache"]}),
    ("body_area_chest", "Chest body area",
     {"sex": "male", "age_token": "adults", "body_area": "Chest", "tokens": ["cough"]}),
    ("body_area_abdomen", "Abdomen body area",
     {"sex": "male", "age_token": "adults", "body_area": "Abdomen", "tokens": ["vomiting"]}),
    ("body_area_skin", "Skin body area",
     {"sex": "male", "age_token": "adults", "body_area": "Skin symptoms", "tokens": ["swelling"]}),
    ("restored_offline_assessment", "State restored from disk mid-flow — eligibility recomputed from state alone",
     {"sex": "female", "age_token": "adults", "pregnancy": True,
      "tokens": ["fever", "vomiting"], "assessment_phase": "restored"}),
]

# Edit scenarios: (name, description, before kwargs, after kwargs, invalidated).
EDIT_SCENARIOS = [
    ("edit_sex_female_to_male_clears_pregnancy",
     "Upstream edit: changing sex from female to male invalidates the pregnancy answer and its token",
     {"sex": "female", "age_token": "adults", "pregnancy": True, "tokens": ["headache"]},
     {"sex": "male", "age_token": "adults", "pregnancy": None, "tokens": ["headache"]},
     ["Q-demo-pregnancy"]),
    ("edit_removes_symptom_invalidates_followup",
     "Upstream edit: deselecting a symptom makes its follow-up questions ineligible and removes their derived tokens",
     {"sex": "male", "age_token": "adults", "tokens": ["headache", "fever"]},
     {"sex": "male", "age_token": "adults", "tokens": ["fever"]},
     ["Q-followup-headache-severity", "Q-followup-headache-duration",
      "Q-followup-headache-additional_symptoms"]),
    ("edit_removes_red_flag_trigger",
     "Upstream edit: deselecting the near-miss token retires its red-flag clarifier and any red flag it produced",
     {"sex": "male", "age_token": "adults", "tokens": ["difficulty_breathing"]},
     {"sex": "male", "age_token": "adults", "tokens": ["headache"]},
     ["Q-clarifier-breathlessness_at_rest"]),
]


def state_from(kwargs):
    return AssessmentState(**kwargs)


def path_for(artifact, state):
    followups = [q for q in artifact["questions"] if q["clinical_role"] not in
                 ("demographic", "body_area", "symptom_picker")]
    demographics = [q for q in artifact["questions"] if q["clinical_role"] in
                    ("demographic", "body_area", "symptom_picker")]
    demo_path = vqf.eligible(demographics, state)
    ordered = vqf.eligible(followups, state)
    kept = vqf.apply_truncation(ordered, artifact["path_controls"])
    return {
        "demographic_questions": [q["question_id"] for q in demo_path],
        "eligible_followups_before_truncation": [q["question_id"] for q in ordered],
        "presented_followups": [q["question_id"] for q in kept],
        "truncated": [q["question_id"] for q in ordered if q not in kept],
        "followup_count": len(kept),
        "total_questions": len(demo_path) + len(kept),
        "red_flag_questions": [
            q["question_id"] for q in kept if q["red_flag_evaluation"]["can_affect_red_flag"]
        ],
        "red_flag_evaluation_points": [
            q["question_id"] for q in kept
            if q["red_flag_evaluation"]["evaluate_after_answer"]
        ],
    }


def build_path_fixture(artifact):
    cases = []
    for name, description, kwargs in SCENARIOS:
        state = state_from(kwargs)
        cases.append({
            "fixture_id": name,
            "description": description,
            "input_state": {
                "sex": state.sex,
                "age_token": state.age_token,
                "pregnancy": state.pregnancy,
                "body_area": state.body_area,
                "tokens": sorted(state.tokens),
                "assessment_phase": state.assessment_phase,
            },
            "expected": path_for(artifact, state),
        })

    edits = []
    for name, description, before, after, invalidated in EDIT_SCENARIOS:
        before_state, after_state = state_from(before), state_from(after)
        before_path, after_path = path_for(artifact, before_state), path_for(artifact, after_state)
        edits.append({
            "fixture_id": name,
            "description": description,
            "before": {"tokens": sorted(before_state.tokens),
                       "sex": before_state.sex, "pregnancy": before_state.pregnancy,
                       "path": before_path},
            "after": {"tokens": sorted(after_state.tokens),
                      "sex": after_state.sex, "pregnancy": after_state.pregnancy,
                      "path": after_path},
            "expected_invalidated_questions": invalidated,
            "expected_no_longer_presented": sorted(
                set(before_path["presented_followups"]) - set(after_path["presented_followups"])
            ),
            "expected_newly_presented": sorted(
                set(after_path["presented_followups"]) - set(before_path["presented_followups"])
            ),
        })

    return {
        "fixture_id": "question_flow_paths",
        "fixture_version": "1",
        "generator": "tools/build_question_fixtures.py",
        "generator_version": QFLOW_TOOLING_VERSION,
        "synthetic": True,
        "note": "All inputs are synthetic and spec-derived. No real-user assessment data is used, and no new symptom combination is invented beyond tokens that already exist.",
        "artifact": {
            "file": "candidate/question_flow.ng.v1.0.json",
            "version": artifact["_metadata"]["version"],
            "sha256": sha256_file(CANDIDATE),
        },
        "lifecycle_states": {
            "assessment_completed": "every required, eligible question has an answer; the flow proceeds to scoring",
            "assessment_abandoned": "the user cancels; no result is produced and no state is retained",
            "assessment_interrupted_by_red_flag": "a red-flag-affecting answer fires a rule; branching stops and emergency presentation wins",
            "question_not_applicable": "trigger_condition is false — no answer state is stored at all",
            "optional_skipped": "an optional question with an explicit skip sentinel; no clinical token is produced",
            "required_unanswered": "a required question with no answer; the flow cannot advance past it",
            "invalidated_by_edit": "an upstream edit cleared the answer; the question returns to unanswered",
        },
        "cases": cases,
        "edit_cases": edits,
    }


# --- invalid fixtures ---------------------------------------------------------


def _q(artifact, question_id):
    return next(q for q in artifact["questions"] if q["question_id"] == question_id)


def duplicate_question_id(a):
    a["questions"].append(copy.deepcopy(a["questions"][0]))
    return a, "B.identity:question_ids_are_unique"


def duplicate_answer_option_id(a):
    q = _q(a, "Q-demo-age")
    q["answer_options"].append(copy.deepcopy(q["answer_options"][0]))
    return a, "B.identity:answer_option_ids_are_globally_unique"


def unknown_next_question(a):
    _q(a, "Q-demo-age")["branch_conditions"] = [
        {"when": {"always": True}, "next_question_id": "Q-does-not-exist"}
    ]
    return a, "C.references:conditions_are_valid_and_resolve"


def unknown_token(a):
    _q(a, "Q-demo-age")["answer_options"][0]["produces_tokens"] = ["not_a_real_token"]
    return a, "C.references:produced_tokens_resolve_in_token_dictionary_1_1"


def invalid_condition_operator(a):
    _q(a, "Q-demo-age")["trigger_condition"] = {"matches_regex": "fever.*"}
    return a, "C.references:no_operator_used_outside_the_declared_language"


def condition_type_mismatch(a):
    # The JSON Schema constrains a condition's SHAPE (exactly one key); operand
    # types are the condition language's job, so this is caught there.
    _q(a, "Q-demo-age")["trigger_condition"] = {"token_present": 42}
    return a, "C.references:conditions_are_valid_and_resolve"


def branch_cycle(a):
    _q(a, "Q-demo-age")["branch_conditions"] = [
        {"when": {"always": True}, "next_question_id": "Q-demo-sex"}
    ]
    _q(a, "Q-demo-sex")["branch_conditions"] = [
        {"when": {"always": True}, "next_question_id": "Q-demo-age"}
    ]
    return a, "E.graph:no_branch_cycles"


def unreachable_question(a):
    _q(a, "Q-followup-headache-severity")["trigger_condition"] = {"never": True}
    return a, "E.graph:no_question_has_an_impossible_trigger"


def contradictory_condition(a):
    _q(a, "Q-followup-fever-duration")["trigger_condition"] = {
        "all": [{"token_present": "fever"}, {"token_absent": "fever"}]
    }
    return a, "E.graph:no_question_has_an_impossible_trigger"


def nondeterministic_priority_tie(a):
    _q(a, "Q-demo-age")["priority"] = _q(a, "Q-demo-sex")["priority"]
    _q(a, "Q-demo-age")["tie_break_key"] = _q(a, "Q-demo-sex")["tie_break_key"]
    _q(a, "Q-demo-age")["question_id"] = "Q-demo-sex"
    return a, "B.identity:question_ids_are_unique"


def required_question_silently_skippable(a):
    q = _q(a, "Q-demo-age")
    q["required"] = True
    q["skippable"] = True
    return a, "G.semantics:no_required_question_is_skippable"


def skip_sentinel_produces_token(a):
    q = _q(a, "Q-demo-medical-conditions")
    q["answer_options"].append({
        "answer_option_id": "Q-demo-medical-conditions::skipped",
        "label": "Skipped",
        "produces_tokens": ["smoker"],
        "is_skip_sentinel": True,
        "value": None,
    })
    return a, "G.semantics:no_skip_sentinel_produces_a_clinical_token"


def red_flag_question_not_evaluated_immediately(a):
    q = _q(a, "Q-clarifier-breathlessness_at_rest")
    q["red_flag_evaluation"]["evaluate_after_answer"] = False
    q["red_flag_evaluation"]["blocks_next_question"] = False
    return a, "F.paths:every_red_flag_affecting_question_evaluates_immediately"


def red_flag_impact_understated(a):
    _q(a, "Q-clarifier-abnormal_bleeding")["red_flag_evaluation"]["can_affect_red_flag"] = False
    return a, "F.paths:red_flag_effect_and_hook_agree"


def red_flag_question_behind_ordinary(a):
    _q(a, "Q-clarifier-breathlessness_at_rest")["priority"] = 999
    return a, "F.paths:red_flag_questions_never_queue_behind_ordinary_ones"


def red_flag_truncation_not_exempt(a):
    a["path_controls"]["red_flag_questions_exempt_from_truncation"] = False
    return a, "A.schema:conforms_to_question_flow_schema"


def path_limit_starves_ordinary_questions(a):
    # A limit this low leaves no room after the protected red-flag questions,
    # so ordinary questions become unreachable on every explored path.
    #
    # Note on `no_explored_path_exceeds_the_followup_limit`: today's truncation
    # cannot violate it except through the red-flag exemption, which is correct
    # behaviour rather than a defect. The check is retained as a guard against a
    # future truncation implementation that stops enforcing the limit, and is
    # deliberately not paired with a fixture that would have to fake a defect to
    # trip it.
    a["path_controls"]["max_followup_questions"] = 1
    return a, "E.graph:no_unreachable_question"


def invalid_edit_dependency(a):
    _q(a, "Q-demo-sex")["invalidates_on_change"] = ["Q-nope"]
    return a, "C.references:invalidation_targets_resolve"


def self_invalidating_question(a):
    _q(a, "Q-demo-sex")["invalidates_on_change"] = ["Q-demo-sex"]
    return a, "G.semantics:no_question_invalidates_itself"


def candidate_marked_publishable(a):
    a["_metadata"]["may_publish"] = True
    return a, "H.publication:may_publish_is_false_without_review"


def published_without_clinical_review(a):
    a["_metadata"]["release_status"] = "published"
    return a, "H.publication:release_status_is_not_published"


def content_marked_approved_without_review(a):
    _q(a, "Q-demo-age")["content_ref"]["content_approved"] = True
    return a, "H.publication:no_question_content_is_marked_approved"


def vocabulary_2_0_activated(a):
    a["_metadata"]["vocabulary_2_0"]["used"] = True
    return a, "H.publication:vocabulary_2_0_is_declared_unused"


INVALID = [
    ("duplicate_question_id", duplicate_question_id),
    ("duplicate_answer_option_id", duplicate_answer_option_id),
    ("unknown_next_question", unknown_next_question),
    ("unknown_token", unknown_token),
    ("invalid_condition_operator", invalid_condition_operator),
    ("condition_type_mismatch", condition_type_mismatch),
    ("branch_cycle", branch_cycle),
    ("unreachable_question", unreachable_question),
    ("contradictory_condition", contradictory_condition),
    ("nondeterministic_priority_tie", nondeterministic_priority_tie),
    ("required_question_silently_skippable", required_question_silently_skippable),
    ("skip_sentinel_produces_token", skip_sentinel_produces_token),
    ("red_flag_question_not_evaluated_immediately", red_flag_question_not_evaluated_immediately),
    ("red_flag_impact_understated", red_flag_impact_understated),
    ("red_flag_question_behind_ordinary", red_flag_question_behind_ordinary),
    ("red_flag_truncation_not_exempt", red_flag_truncation_not_exempt),
    ("path_limit_starves_ordinary_questions", path_limit_starves_ordinary_questions),
    ("invalid_edit_dependency", invalid_edit_dependency),
    ("self_invalidating_question", self_invalidating_question),
    ("candidate_marked_publishable", candidate_marked_publishable),
    ("published_without_clinical_review", published_without_clinical_review),
    ("content_marked_approved_without_review", content_marked_approved_without_review),
    ("vocabulary_2_0_activated", vocabulary_2_0_activated),
]


def outputs():
    artifact = load_json(CANDIDATE)
    files = [(os.path.join(PATHS_DIR, "path_fixtures_v1.json"), build_path_fixture(artifact))]

    index = {"fixture_id": "question_flow_invalid_fixtures", "fixture_version": "1",
             "synthetic": True,
             "note": "Each file is the candidate with exactly one defect. None may be published or used as a source of question content.",
             "fixtures": []}
    for name, factory in INVALID:
        mutated, expected = factory(copy.deepcopy(artifact))
        mutated["_metadata"]["SYNTHETIC_FIXTURE"] = True
        mutated["_metadata"]["FIXTURE_NAME"] = name
        mutated["_metadata"]["EXPECTED_FAILURE"] = expected
        files.append((os.path.join(INVALID_DIR, "%s.json" % name), mutated))
        index["fixtures"].append({"file": "%s.json" % name, "expected_failing_check": expected})
    files.append((os.path.join(INVALID_DIR, "index.json"), index))
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    for path, payload in outputs():
        data = dump_report_bytes(payload)
        relative = os.path.relpath(path, repo_path())
        if args.check:
            if not os.path.exists(path) or open(path, "rb").read() != data:
                print("FAIL %s is missing or stale" % relative)
                return 1
        else:
            write_bytes(path, data)

    if args.check:
        print("OK   question fixtures are current")
    else:
        print("wrote %d path scenarios, %d edit scenarios, %d invalid fixtures"
              % (len(SCENARIOS), len(EDIT_SCENARIOS), len(INVALID)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
