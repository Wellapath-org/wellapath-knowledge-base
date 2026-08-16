#!/usr/bin/env python3
"""Project the current question flow into a candidate artifact.

    python3 tools/build_question_candidate.py            # build
    python3 tools/build_question_candidate.py --check    # fail if stale

Projection rules, all asserted by tests:

  * zero new clinically substantive questions — every question here exists in
    the vendored Dart today;
  * zero removed questions;
  * zero changed answer meanings — every answer's produced token is copied, not
    re-derived;
  * zero changed token effects;
  * zero changed red-flag effects;
  * ordering preserves the current emission order, with the one place the
    current implementation is non-deterministic replaced by a DECLARED
    deterministic tie-break (see `IMPEDANCE_MISMATCHES`).

Where behaviour lives in code and cannot be represented as data, the mismatch is
recorded rather than papered over, and the artifact does not claim parity it
does not have.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import MOBILE_SOURCE_COMMIT, MOBILE_SOURCE_REPO, QFLOW_TOOLING_VERSION
from qflow.conditions import CONDITION_LANGUAGE_VERSION, FIELDS, OPERATORS
from qflow.dartparse import BASELINE_DIR, VENDORED_FILES, parse_all
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
    write_bytes,
)

CANDIDATE_PATH = repo_path("candidate", "question_flow.ng.v1.0.json")
GENERATOR = "tools/build_question_candidate.py"
GENERATOR_VERSION = "1.0.0"
DEFAULT_GENERATED_AT = "2026-08-16T00:00:00Z"

ARTIFACT_ID = "question_flow"
CANDIDATE_VERSION = "1.0"
SCHEMA_VERSION = "1.0"

# Emission ranks, from question_engine.dart. Red-flag clarifiers first.
PRIORITY = {
    "red_flag_clarifier": 0,
    "severity": 10,
    "duration": 20,
    "additional_symptoms": 30,
}

IMPEDANCE_MISMATCHES = [
    {
        "id": "IM-001",
        "area": "question selection",
        "current_behaviour": "Severity and duration questions are chosen by `severityQuestion ??= question` while iterating the SELECTED symptom tokens, so which wording is asked depends on the order the user tapped symptoms.",
        "candidate_behaviour": "Selection is by a declared deterministic tie_break_key (the trigger token id, ascending), so the same symptom set always yields the same question regardless of selection order.",
        "is_behaviour_change": True,
        "clinically_substantive": False,
        "justification": "The competing questions differ only in wording ('How severe is your headache?' vs 'How severe is this pain?'). No token effect, weight, red flag or urgency differs. The current behaviour is non-deterministic in a way W3 explicitly forbids, and a tie with no declared resolution is a validation failure under this contract.",
        "requires_review": "product — wording selection only",
    },
    {
        "id": "IM-002",
        "area": "red-flag timing",
        "current_behaviour": "Answers are committed only after the LAST follow-up question, so a red-flag clarifier 'yes' does not interrupt; the red flag is evaluated once, in the engine, after every question has been shown.",
        "candidate_behaviour": "Every red-flag-affecting question declares evaluate_after_answer=true and blocks_next_question=true, requiring evaluation immediately after that answer.",
        "is_behaviour_change": True,
        "clinically_substantive": True,
        "justification": "This makes red-flag detection strictly EARLIER, never later. It cannot suppress a red flag that fires today; it can only fire the same red flag sooner. Implementing it is Mobile work in a later W3 step and is NOT done here.",
        "requires_review": "engineering lead — behaviour change in Mobile, clinically safe direction",
    },
    {
        "id": "IM-003",
        "area": "adaptive re-branching",
        "current_behaviour": "The question list is computed once from the pre-screen symptom set. Tokens added by an additionalSymptoms answer generate no further questions.",
        "candidate_behaviour": "trigger_condition is re-evaluated against current state, so a newly derived token can make a further question eligible.",
        "is_behaviour_change": True,
        "clinically_substantive": False,
        "justification": "Strictly additive: it can only ask MORE questions, never fewer, and the truncation limit still bounds the total. No existing question is removed or reworded.",
        "requires_review": "product — path length impact",
    },
    {
        "id": "IM-004",
        "area": "answer identity",
        "current_behaviour": "Answers are keyed by list index (Map<int, dynamic>), meaningful only against the exact list built at initState.",
        "candidate_behaviour": "Answers are keyed by stable question_id and answer_option_id.",
        "is_behaviour_change": False,
        "clinically_substantive": False,
        "justification": "A representation change with no user-visible effect. Required before answer editing can invalidate dependents safely.",
        "requires_review": "none",
    },
    {
        "id": "IM-005",
        "area": "truncation safety",
        "current_behaviour": "Truncation to 5 is applied to the whole list. No clarifier is dropped today only because there are 3 of them and they sort first.",
        "candidate_behaviour": "red_flag_questions_exempt_from_truncation is a schema constant `true`; a red-flag-affecting question is never dropped to satisfy a length limit.",
        "is_behaviour_change": False,
        "clinically_substantive": False,
        "justification": "Makes an incidental property structural. Same observable behaviour on today's data.",
        "requires_review": "none",
    },
    {
        "id": "IM-006",
        "area": "demographic screens",
        "current_behaviour": "Sex, age, pregnancy, medical conditions and body area are separate Flutter screens with hardcoded navigation, not entries in any question list.",
        "candidate_behaviour": "Represented as questions with trigger_condition and priority, so the whole flow is one ordered graph.",
        "is_behaviour_change": False,
        "clinically_substantive": False,
        "justification": "The pregnancy gate is projected exactly as implemented: {\"sex\": \"female\"}. Age and medical-condition token mappings are copied verbatim. Body area produces no token, as today.",
        "requires_review": "none",
    },
    {
        "id": "IM-007",
        "area": "skip",
        "current_behaviour": "No skip mechanism exists. Every presented question must be answered or the assessment cancelled.",
        "candidate_behaviour": "The schema supports `skippable`, but every projected question is `skippable: false` — the projection introduces no skip.",
        "is_behaviour_change": False,
        "clinically_substantive": False,
        "justification": "Capability without use. Making any question skippable is a separate, reviewed decision.",
        "requires_review": "product + clinical, per question, before any question is marked skippable",
    },
]


def token_universe():
    token_dictionary = load_json(repo_path("token_dictionary.ng.v1.1.json"))
    tokens = set()
    for category in [
        "symptom_tokens", "red_flag_tokens", "duration_tokens",
        "body_area_tokens", "demographic_tokens", "severity_tokens",
    ]:
        tokens.update(token_dictionary[category])
    return tokens


def clinical_roles():
    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))
    scoring = {s["token"] for c in kb["conditions"] for s in c["symptoms"]}
    red_flag = {r["token"] for r in rules["rules"]}
    red_flag |= {t for c in kb["conditions"] for t in c["red_flags"]}
    return scoring, red_flag


def make_option(question_id, local, label, tokens, value=None, skip=False):
    return {
        "answer_option_id": "%s::%s" % (question_id, local),
        "label": label,
        "produces_tokens": sorted(tokens),
        "is_skip_sentinel": skip,
        "value": value,
    }


def build_candidate(generated_at):
    parsed = parse_all(repo_path())
    fq = parsed["followup_question_map"]
    clarifiers = parsed["red_flag_clarifiers"]
    display = parsed["symptom_display"]
    controller = parsed["controller"]
    answers = parsed["answer_mappings"]
    engine = parsed["engine"]

    scoring_tokens, red_flag_tokens = clinical_roles()
    questions = []

    def add(question):
        produced = sorted({t for o in question["answer_options"] for t in o["produces_tokens"]})
        question["effects"] = {
            "produces_tokens": produced,
            "affects_scoring": bool(set(produced) & scoring_tokens),
            "affects_red_flags": bool(set(produced) & red_flag_tokens),
        }
        can_affect = question["effects"]["affects_red_flags"]
        question["red_flag_evaluation"] = {
            "can_affect_red_flag": can_affect,
            "evaluate_after_answer": can_affect,
            "blocks_next_question": can_affect,
        }
        question.setdefault("terminal", False)
        question.setdefault("branch_conditions", [])
        question.setdefault("invalidates_on_change", [])
        question["review"] = {
            "review_status": "not_reviewed",
            "clinical_reviewer": None,
            "review_date": None,
        }
        questions.append(question)

    # --- demographic questions, projected exactly as implemented -------------
    add({
        "question_id": "Q-demo-sex",
        "question_type": "single_select",
        "clinical_role": "demographic",
        "content_ref": {"content_id": "sex_screen.title", "source_text": "Sex", "content_approved": False},
        "answer_value_type": "option_id",
        "required": True,
        "skippable": False,
        "answer_options": [
            make_option("Q-demo-sex", "male", "male", [], value="male"),
            make_option("Q-demo-sex", "female", "female", [], value="female"),
        ],
        "trigger_condition": {"always": True},
        "priority": 100,
        "tie_break_key": "Q-demo-sex",
        "path_length_contribution": 1,
        # Changing sex away from female clears pregnancy today
        # (AssessmentController.setSex). Projected as an explicit dependency.
        "invalidates_on_change": ["Q-demo-pregnancy"],
        "provenance": "assessment_controller.dart setSex / sex_screen.dart",
    })
    add({
        "question_id": "Q-demo-age",
        "question_type": "single_select",
        "clinical_role": "demographic",
        "content_ref": {"content_id": "age_screen.title", "source_text": "Age range", "content_approved": False},
        "answer_value_type": "option_id",
        "required": True,
        "skippable": False,
        "answer_options": [
            make_option("Q-demo-age", token, label, [token], value=label)
            for label, token in controller["age_label_to_token"]
        ],
        "trigger_condition": {"always": True},
        "priority": 110,
        "tie_break_key": "Q-demo-age",
        "path_length_contribution": 1,
        "provenance": "assessment_controller.dart _ageTokenMap / age_screen.dart",
    })
    add({
        "question_id": "Q-demo-pregnancy",
        "question_type": "yes_no",
        "clinical_role": "demographic",
        "content_ref": {"content_id": "pregnancy_screen.title", "source_text": "Are you pregnant?", "content_approved": False},
        "answer_value_type": "boolean",
        "required": True,
        "skippable": False,
        "answer_options": [
            make_option("Q-demo-pregnancy", "yes", "Yes", ["pregnancy"], value=True),
            make_option("Q-demo-pregnancy", "no", "No", [], value=False),
        ],
        # Exactly the implemented gate: shouldShowPregnancyScreen => _sex == 'female'.
        "trigger_condition": {"sex": controller["pregnancy_shown_when_sex_equals"]},
        "priority": 120,
        "tie_break_key": "Q-demo-pregnancy",
        "path_length_contribution": 1,
        "provenance": "assessment_controller.dart shouldShowPregnancyScreen / pregnancy_screen.dart",
    })
    add({
        "question_id": "Q-demo-medical-conditions",
        "question_type": "multi_select",
        "clinical_role": "demographic",
        "content_ref": {"content_id": "medical_conditions_screen.title", "source_text": "Do you have any of these conditions?", "content_approved": False},
        "answer_value_type": "option_id_set",
        "required": False,
        "skippable": False,
        "answer_options": [
            make_option("Q-demo-medical-conditions", token, label, [token], value=label)
            for label, token in controller["medical_condition_label_to_token"]
        ],
        "trigger_condition": {"always": True},
        "priority": 130,
        "tie_break_key": "Q-demo-medical-conditions",
        "path_length_contribution": 1,
        "provenance": "assessment_controller.dart _medicalConditionTokenMap / medical_conditions_screen.dart",
    })
    add({
        "question_id": "Q-demo-body-area",
        "question_type": "single_select",
        "clinical_role": "body_area",
        "content_ref": {"content_id": "body_area_screen.title", "source_text": "Where is the problem?", "content_approved": False},
        "answer_value_type": "option_id",
        "required": True,
        "skippable": False,
        "answer_options": [
            make_option("Q-demo-body-area", "area_%d" % index, area, [], value=area)
            for index, area in enumerate(display["body_area_order"])
        ],
        "trigger_condition": {"always": True},
        "priority": 140,
        "tie_break_key": "Q-demo-body-area",
        "path_length_contribution": 1,
        "invalidates_on_change": ["Q-symptom-selection"],
        "provenance": "symptom_display_map.dart kBodyAreaSymptoms / body_area_screen.dart — filters the picker only, produces no token",
    })
    picker_tokens = sorted({tok for _, tok in display["display_label_to_token"]})
    add({
        "question_id": "Q-symptom-selection",
        "question_type": "multi_select",
        "clinical_role": "symptom_picker",
        "content_ref": {"content_id": "symptom_selection_screen.title", "source_text": "Select your symptoms", "content_approved": False},
        "answer_value_type": "option_id_set",
        "required": True,
        "skippable": False,
        # Option IDs are indexed, not token-named: the picker deliberately gives
        # two tokens a second synonymous label each ("Muscle pain" -> body_pain,
        # "Feeling sick or queasy" -> nausea), so a token-named ID would collide
        # and silently merge two distinct picker entries into one.
        "answer_options": [
            make_option("Q-symptom-selection", "opt_%03d" % index, label, [token], value=token)
            for index, (label, token) in enumerate(display["display_label_to_token"])
        ],
        "trigger_condition": {"always": True},
        "priority": 150,
        "tie_break_key": "Q-symptom-selection",
        "path_length_contribution": 1,
        "invalidates_on_change": ["<all follow-up questions>"],
        "provenance": "symptom_display_map.dart kSymptomDisplayMap / symptom_selection_screen.dart",
    })

    # --- red-flag clarifiers --------------------------------------------------
    for clarifier in sorted(clarifiers, key=lambda c: c["red_flag_token"]):
        qid = "Q-clarifier-%s" % clarifier["red_flag_token"]
        add({
            "question_id": qid,
            "question_type": "yes_no",
            "clinical_role": "red_flag_clarifier",
            "content_ref": {
                "content_id": "red_flag_clarifiers.%s" % clarifier["red_flag_token"],
                "source_text": clarifier["question_text"],
                "content_approved": False,
            },
            "answer_value_type": "option_id",
            "required": True,
            "skippable": False,
            "answer_options": [
                make_option(qid, "yes", "Yes", [clarifier["red_flag_token"]], value="Yes"),
                make_option(qid, "no", "No", [], value="No"),
            ],
            # Exactly the implemented predicate: any trigger token selected AND
            # the red flag itself not already selected.
            "trigger_condition": {
                "all": [
                    {"any": [{"token_present": t} for t in clarifier["trigger_tokens"]]},
                    {"token_absent": clarifier["red_flag_token"]},
                ]
            },
            "priority": PRIORITY["red_flag_clarifier"],
            "tie_break_key": clarifier["red_flag_token"],
            "path_length_contribution": 1,
            "provenance": "red_flag_clarifiers.dart kRedFlagClarifiers",
        })

    # --- token follow-ups -----------------------------------------------------
    severity_bands = answers["severity_bands"]
    duration_answers = answers["duration_answer_to_token"]

    for token in sorted(fq["entries"]):
        for entry in fq["entries"][token]:
            qtype = entry["type"]
            role = "additional_symptoms" if qtype == "additionalSymptoms" else qtype
            qid = "Q-followup-%s-%s" % (token, role)
            if qtype == "severity":
                options = [
                    make_option(qid, band["token"], band["token"], [band["token"]],
                                value=band["max_value"])
                    for band in severity_bands
                ]
                value_type, question_type = "option_id", "scale_select"
            elif qtype == "duration":
                options = [
                    make_option(qid, tok, label, [tok], value=label)
                    for label, tok in duration_answers
                ]
                value_type, question_type = "option_id", "single_select"
            else:
                options = [
                    make_option(qid, opt, opt, [opt], value=opt) for opt in entry["options"]
                ]
                value_type, question_type = "option_id_set", "multi_select"

            add({
                "question_id": qid,
                "question_type": question_type,
                "clinical_role": role,
                "content_ref": {
                    "content_id": "followup_question_map.%s.%s" % (token, role),
                    "source_text": entry["question_text"],
                    "content_approved": False,
                },
                "answer_value_type": value_type,
                "required": True,
                "skippable": False,
                "answer_options": options,
                "trigger_condition": {"token_present": token},
                "priority": PRIORITY[role],
                # IM-001: the declared deterministic tie-break replacing the
                # current selection-order dependence.
                "tie_break_key": token,
                "path_length_contribution": 1,
                "provenance": "followup_question_map.dart kFollowupQuestionMap[%r]" % token,
            })

    # --- default fallback -----------------------------------------------------
    default_qid = "Q-followup-default-duration"
    add({
        "question_id": default_qid,
        "question_type": "single_select",
        "clinical_role": "duration",
        "content_ref": {
            "content_id": "followup_question_map.default.duration",
            "source_text": fq["default_question"]["question_text"],
            "content_approved": False,
        },
        "answer_value_type": "option_id",
        "required": True,
        "skippable": False,
        "answer_options": [
            make_option(default_qid, tok, label, [tok], value=label)
            for label, tok in duration_answers
        ],
        # Fires when a symptom is selected that has no authored follow-up entry.
        "trigger_condition": {
            "all": [{"token_absent": token} for token in sorted(fq["entries"])]
        },
        "priority": PRIORITY["duration"] + 1,
        "tie_break_key": "zzz-default",
        "path_length_contribution": 1,
        "terminal": False,
        "provenance": "followup_question_map.dart kDefaultFollowupQuestion",
    })

    artifact = {
        "_metadata": {
            "artifact_id": ARTIFACT_ID,
            "version": CANDIDATE_VERSION,
            "schema_version": SCHEMA_VERSION,
            "country": "ng",
            "release_status": "candidate_unapproved",
            "release_date": None,
            "may_publish": False,
            "generated_at": generated_at,
            "generator": GENERATOR,
            "generator_version": GENERATOR_VERSION,
            "tooling_version": QFLOW_TOOLING_VERSION,
            "description": (
                "WellaPath Adaptive Question Flow CANDIDATE — the first versioned "
                "representation of a flow that currently exists only as Dart source. "
                "Not published, not clinically approved, not consumed by any build."
            ),
            "source": {
                "repository": MOBILE_SOURCE_REPO,
                "commit": MOBILE_SOURCE_COMMIT,
                "vendored_files": [
                    {"file": "%s/%s" % (BASELINE_DIR, name),
                     "sha256": sha256_file(repo_path(BASELINE_DIR, name))}
                    for name in VENDORED_FILES
                ],
            },
            "frozen_clinical_inputs": {
                "token_dictionary_v1_1": sha256_file(repo_path("token_dictionary.ng.v1.1.json")),
                "kb_v2_4": sha256_file(repo_path("kb.ng.v2.4.json")),
                "rules_v2_2": sha256_file(repo_path("rules.ng.v2.2.json")),
            },
            "vocabulary_2_0": {
                "used": False,
                "note": "W3 branching resolves canonical token IDs from token_dictionary 1.1 only. No alias, association or other Vocabulary 2.0 metadata participates in question eligibility.",
            },
            "clinical_review": {
                "status": "not_reviewed",
                "reviewer": None,
                "review_date": None,
                "evidence": None,
            },
            "impedance_mismatches": IMPEDANCE_MISMATCHES,
            "parity_claim": (
                "Behaviourally equivalent for question CONTENT, answer meaning and token "
                "effects. NOT identical for timing and determinism: see impedance_mismatches "
                "IM-001, IM-002 and IM-003, each of which is a deliberate, documented "
                "difference in a safe direction, not an accidental drift."
            ),
            "changelog": [
                "First versioned representation of the existing question flow.",
                "No question added, removed or reworded; no answer meaning or token effect changed.",
                "Declared deterministic tie-break replaces selection-order dependence (IM-001).",
                "Red-flag-affecting questions declare immediate evaluation (IM-002) — specified, not yet implemented in Mobile.",
                "Not published; may_publish is false and no clinical review is recorded.",
            ],
            "provenance": [
                "Projected from wellapath-mobile %s by %s." % (MOBILE_SOURCE_COMMIT, GENERATOR),
                "Every question, answer label and produced token is copied from the vendored Dart, not authored here.",
                "No PHI and no real-user assessment data: this artifact contains only question definitions and token identifiers already published in token_dictionary 1.1.",
            ],
        },
        "condition_language": {
            "version": CONDITION_LANGUAGE_VERSION,
            "operators": sorted(OPERATORS),
            "fields": sorted(FIELDS),
        },
        "path_controls": {
            "max_questions_per_assessment": len([q for q in questions if q["clinical_role"] in
                                                 ("demographic", "body_area", "symptom_picker")])
            + engine["max_followup_questions"],
            "max_followup_questions": engine["max_followup_questions"],
            "max_questions_per_complaint_path": None,
            "red_flag_questions_exempt_from_truncation": True,
            "truncation_allowed": True,
            "truncation_rule": (
                "After ordering, drop the lowest-priority questions until the follow-up count "
                "fits max_followup_questions. A question whose red_flag_evaluation."
                "can_affect_red_flag is true is never dropped; if red-flag questions alone "
                "exceed the limit, the limit yields and all of them are asked."
            ),
            "cycle_detection": "required",
            "repeated_question_prevention": "required",
            "thresholds_status": "measured_from_implementation",
            "proposed_options": [
                {"option": "keep_5", "max_followup_questions": 5,
                 "rationale": "Exactly today's implemented limit. Zero change."},
                {"option": "raise_to_7", "max_followup_questions": 7,
                 "rationale": "Absorbs IM-003 adaptive re-branching without truncating; 3 clarifiers + severity + duration + additional + 1 headroom."},
                {"option": "red_flag_exempt_only", "max_followup_questions": 5,
                 "rationale": "Keep 5 for ordinary questions, exempt red-flag questions entirely (already the schema constant)."},
            ],
            "final_threshold_status": "PENDING product and clinical approval — the values above are measured or proposed, not approved.",
        },
        "questions": questions,
    }
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    args = parser.parse_args()

    artifact = build_candidate(args.generated_at)
    payload = dump_artifact_bytes(artifact)

    if args.check:
        if not os.path.exists(CANDIDATE_PATH) or open(CANDIDATE_PATH, "rb").read() != payload:
            print("FAIL candidate/question_flow.ng.v1.0.json is missing or stale")
            return 1
        print("OK   question flow candidate is reproducible, sha256:%s" % sha256_bytes(payload))
        return 0

    write_bytes(CANDIDATE_PATH, payload)
    print("wrote candidate/question_flow.ng.v1.0.json")
    print("  questions:      %d" % len(artifact["questions"]))
    print("  answer options: %d" % sum(len(q["answer_options"]) for q in artifact["questions"]))
    print("  sha256:         %s" % sha256_bytes(payload))
    print("  release_status: %s | may_publish: %s"
          % (artifact["_metadata"]["release_status"], artifact["_metadata"]["may_publish"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
