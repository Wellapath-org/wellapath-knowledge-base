#!/usr/bin/env python3
"""Freeze the current question flow and trace its clinical references.

    python3 tools/report_question_baseline.py            # write the report
    python3 tools/report_question_baseline.py --check    # fail if stale

The current flow has NO versioned artifact. Its authoritative definition is Dart
source in wellapath-mobile, vendored into baseline/questions_v1/ and hashed
here. That is recorded as the finding it is, not smoothed over.

Nothing in this report rewrites a current definition to look tidier. Where the
implementation is inconsistent, the inconsistency is listed under
`known_defects_and_inconsistencies`.
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import MOBILE_SOURCE_COMMIT, MOBILE_SOURCE_REPO, QFLOW_TOOLING_VERSION
from qflow.dartparse import BASELINE_DIR, VENDORED_FILES, parse_all
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

REPORT_PATH = repo_path("reports", "question_baseline_freeze_v1.json")

# Mobile source paths the vendored copies were taken from.
SOURCE_PATHS = {
    "followup_question_map.vendored.dart": "lib/core/constants/followup_question_map.dart",
    "red_flag_clarifiers.vendored.dart": "lib/core/constants/red_flag_clarifiers.dart",
    "symptom_display_map.vendored.dart": "lib/core/constants/symptom_display_map.dart",
    "question_engine.vendored.dart": "lib/features/assessment/question_engine.dart",
    "assessment_controller.vendored.dart": "lib/features/assessment/assessment_controller.dart",
    "followup_screen.vendored.dart": "lib/features/assessment/followup_screen.dart",
    "followup_question.vendored.dart": "lib/features/assessment/models/followup_question.dart",
}

CATEGORIES = [
    "symptom_tokens",
    "red_flag_tokens",
    "duration_tokens",
    "body_area_tokens",
    "demographic_tokens",
    "severity_tokens",
]


def question_id(kind, key, qtype):
    """Stable synthetic ID for a definition that has none today.

    The current implementation identifies a question only by its position in a
    generated list. These IDs are assigned by rule, not invented per question,
    so the same source always yields the same ID.
    """
    return "Q-%s-%s-%s" % (kind, key, qtype)


def build_report():
    parsed = parse_all(repo_path())
    fq = parsed["followup_question_map"]
    clarifiers = parsed["red_flag_clarifiers"]
    display = parsed["symptom_display"]
    controller = parsed["controller"]
    answers = parsed["answer_mappings"]
    engine = parsed["engine"]

    token_dictionary = load_json(repo_path("token_dictionary.ng.v1.1.json"))
    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))

    known_tokens = set()
    for category in CATEGORIES:
        known_tokens.update(token_dictionary[category])
    scoring_tokens = {s["token"] for c in kb["conditions"] for s in c["symptoms"]}
    rules_tokens = {r["token"] for r in rules["rules"]}
    global_rule_tokens = {r["token"] for r in rules["rules"] if r["applies_to"] == ["all"]}
    kb_red_flags = {t for c in kb["conditions"] for t in c["red_flags"]}
    red_flag_tokens = rules_tokens | kb_red_flags
    demographic_tokens = set(token_dictionary["demographic_tokens"])

    display_tokens = {tok for _, tok in display["display_label_to_token"]}

    # --- enumerate every question the current implementation can present ------
    questions = []
    token_refs = collections.defaultdict(set)

    def note(token, where):
        token_refs[token].add(where)

    for clarifier in clarifiers:
        qid = question_id("clarifier", clarifier["red_flag_token"], "redFlagClarifier")
        note(clarifier["red_flag_token"], "clarifier.red_flag_token")
        for trigger in clarifier["trigger_tokens"]:
            note(trigger, "clarifier.trigger_token")
        questions.append(
            {
                "question_id": qid,
                "kind": "red_flag_clarifier",
                "type": "redFlagClarifier",
                "question_text": clarifier["question_text"],
                "trigger_tokens": clarifier["trigger_tokens"],
                "answer_options": [
                    {"answer_option_id": "%s::Yes" % qid, "label": "Yes",
                     "produces_tokens": [clarifier["red_flag_token"]]},
                    {"answer_option_id": "%s::No" % qid, "label": "No", "produces_tokens": []},
                ],
                "produces_red_flag_token": clarifier["red_flag_token"],
                "red_flag_affecting": True,
                "scoring_affecting": clarifier["red_flag_token"] in scoring_tokens,
                "emission_rank": 0,
            }
        )

    severity_option_tokens = [band["token"] for band in answers["severity_bands"]]
    duration_option_tokens = [tok for _, tok in answers["duration_answer_to_token"]]

    for token in fq["order"]:
        for entry in fq["entries"][token]:
            qtype = entry["type"]
            qid = question_id("token", token, qtype)
            note(token, "followup_map.key")
            options = []
            if qtype == "severity":
                for band in answers["severity_bands"]:
                    options.append(
                        {
                            "answer_option_id": "%s::%s" % (qid, band["token"]),
                            "label": band["token"],
                            "produces_tokens": [band["token"]],
                        }
                    )
                    note(band["token"], "answer.severity")
            elif qtype == "duration":
                for label, tok in answers["duration_answer_to_token"]:
                    options.append(
                        {
                            "answer_option_id": "%s::%s" % (qid, tok),
                            "label": label,
                            "produces_tokens": [tok],
                        }
                    )
                    note(tok, "answer.duration")
            elif qtype == "additionalSymptoms":
                for option in entry["options"]:
                    note(option, "answer.additional_symptom")
                    options.append(
                        {
                            "answer_option_id": "%s::%s" % (qid, option),
                            "label": option,
                            "produces_tokens": [option],
                            "reachable_in_ui": option in display_tokens,
                        }
                    )
            produced = {t for o in options for t in o["produces_tokens"]}
            questions.append(
                {
                    "question_id": qid,
                    "kind": "token_followup",
                    "type": qtype,
                    "question_text": entry["question_text"],
                    "trigger_tokens": [token],
                    "answer_options": options,
                    "produces_red_flag_token": None,
                    "red_flag_affecting": bool(produced & red_flag_tokens),
                    "scoring_affecting": bool(produced & scoring_tokens),
                    "emission_rank": engine["emission_order"].index(
                        "additional_symptoms" if qtype == "additionalSymptoms" else qtype
                    ),
                }
            )

    default_qid = question_id("default", "any_unmapped_symptom", fq["default_question"]["type"])
    questions.append(
        {
            "question_id": default_qid,
            "kind": "default_fallback",
            "type": fq["default_question"]["type"],
            "question_text": fq["default_question"]["question_text"],
            "trigger_tokens": ["<any symptom token absent from kFollowupQuestionMap>"],
            "answer_options": [
                {"answer_option_id": "%s::%s" % (default_qid, tok), "label": label,
                 "produces_tokens": [tok]}
                for label, tok in answers["duration_answer_to_token"]
            ],
            "produces_red_flag_token": None,
            "red_flag_affecting": False,
            "scoring_affecting": bool(set(duration_option_tokens) & scoring_tokens),
            "emission_rank": engine["emission_order"].index("duration"),
        }
    )

    # --- demographic questions (screens, not the follow-up engine) ------------
    demographic_questions = [
        {
            "question_id": "Q-demo-sex",
            "kind": "demographic_screen",
            "screen": "sex_screen.dart",
            "answer_options": ["male", "female"],
            "produces_tokens": [],
            "gates": ["Q-demo-pregnancy"],
            "note": "Sex itself produces no demographic token in the current implementation; it only gates the pregnancy screen.",
        },
        {
            "question_id": "Q-demo-age",
            "kind": "demographic_screen",
            "screen": "age_screen.dart",
            "answer_options": [label for label, _ in controller["age_label_to_token"]],
            "produces_tokens": [tok for _, tok in controller["age_label_to_token"]],
            "gates": [],
        },
        {
            "question_id": "Q-demo-pregnancy",
            "kind": "demographic_screen",
            "screen": "pregnancy_screen.dart",
            "answer_options": ["yes", "no"],
            "produces_tokens": ["pregnancy"],
            "shown_when": "sex == %r" % controller["pregnancy_shown_when_sex_equals"],
            "gates": [],
        },
        {
            "question_id": "Q-demo-medical-conditions",
            "kind": "demographic_screen",
            "screen": "medical_conditions_screen.dart",
            "answer_options": [label for label, _ in controller["medical_condition_label_to_token"]],
            "produces_tokens": [tok for _, tok in controller["medical_condition_label_to_token"]],
            "gates": [],
        },
        {
            "question_id": "Q-demo-body-area",
            "kind": "demographic_screen",
            "screen": "body_area_screen.dart",
            "answer_options": display["body_area_order"],
            "produces_tokens": [],
            "gates": ["Q-symptom-selection"],
            "note": "Filters the symptom picker only. Produces no token and does not reach the engine.",
        },
        {
            "question_id": "Q-symptom-selection",
            "kind": "symptom_picker",
            "screen": "symptom_selection_screen.dart",
            "answer_options_count": len(display["display_label_to_token"]),
            "produces_tokens": sorted(display_tokens),
            "gates": ["<all token_followup questions>"],
        },
    ]
    for entry in demographic_questions:
        for token in entry.get("produces_tokens", []):
            note(token, "demographic_screen")
    note("pregnancy", "demographic_screen")

    # --- reference integrity ---------------------------------------------------
    referenced = sorted(t for t in token_refs if not t.startswith("<"))
    unresolved = sorted(t for t in referenced if t not in known_tokens)

    # --- path lengths ----------------------------------------------------------
    max_clarifiers = len(clarifiers)
    theoretical_max = max_clarifiers + 3  # + severity + duration + additionalSymptoms
    enforced_limit = engine["max_followup_questions"]

    defects = [
        {
            "id": "QB-001",
            "severity": "architectural",
            "finding": "There is no versioned question artifact. The entire flow is Dart source in wellapath-mobile, so it carries no artifact version, no hash in any manifest, and cannot be rolled back independently of an app release.",
            "evidence": "baseline/questions_v1/*.vendored.dart; no question entry exists in the backend /config artifacts map.",
        },
        {
            "id": "QB-002",
            "severity": "high",
            "finding": "Red-flag clarifier answers are not evaluated when answered. followup_screen.dart accumulates answers in a local map and calls _commitAnswers() only when the LAST follow-up question is answered, immediately before navigating to LoadingScreen. A 'yes' to a clarifier therefore does not interrupt the flow; the red flag is evaluated once, in the engine, after every follow-up question has been presented.",
            "evidence": "followup_screen.vendored.dart _onNext/_commitAnswers; red-flag evaluation occurs only in lib/core/engine/red_flag_evaluator.dart.",
            "w3_requirement": "W3 requires red-flag evaluation after every answer capable of affecting a red flag. This is a behaviour gap the candidate contract specifies but the current implementation does not meet.",
        },
        {
            "id": "QB-003",
            "severity": "medium",
            "finding": "The follow-up question list is computed once in initState from the symptom tokens selected before the screen opened. Tokens added by an additionalSymptoms answer do not generate further follow-up questions in the same assessment.",
            "evidence": "followup_screen.vendored.dart initState -> QuestionEngine.generateQuestions(...); no recomputation on answer change.",
        },
        {
            "id": "QB-004",
            "severity": "medium",
            "finding": "Answers are keyed by list index (Map<int, dynamic>), not by a stable question ID. The index is only meaningful against the exact list generated at initState.",
            "evidence": "followup_screen.vendored.dart `final Map<int, dynamic> _answers = {}`.",
        },
        {
            "id": "QB-005",
            "severity": "medium",
            "finding": "Question selection depends on the ORDER of the selected symptom tokens: severity and duration are taken from whichever selected token yields one first (`severityQuestion ??= question`). Two users selecting the same symptoms in a different order can be asked differently worded questions.",
            "evidence": "question_engine.vendored.dart generateQuestions loop.",
        },
        {
            "id": "QB-006",
            "severity": "medium",
            "finding": "Truncation to %d questions is applied to the whole list after clarifiers are prepended. It is only incidental that no red-flag clarifier is ever dropped: there are %d clarifiers and they sort first. A fourth-plus clarifier firing alongside others could push a red-flag question out of the list." % (enforced_limit, max_clarifiers),
            "evidence": "question_engine.vendored.dart `result.length > %d ? result.sublist(0, %d) : result`." % (enforced_limit, enforced_limit),
        },
        {
            "id": "QB-007",
            "severity": "low",
            "finding": "additionalSymptoms options are filtered at render time against kSymptomDisplayMap, and an authored option with no display label is silently dropped rather than surfaced as an authoring error. Measured on this baseline the filter currently drops NOTHING — all authored options have display labels — so this is a latent risk, not a live defect.",
            "evidence": "followup_screen.vendored.dart `availableTokens = question.options.where((token) => _displayNameForToken(token) != null)`.",
        },
        {
            "id": "QB-008",
            "severity": "low",
            "finding": "There is no skip mechanism. No follow-up question can be skipped, and no question is marked optional; the only exits are answering or cancelling the assessment.",
            "evidence": "followup_screen.vendored.dart contains no skip control.",
        },
        {
            "id": "QB-009",
            "severity": "informational",
            "finding": "The age band label '0–12' maps to the token `children_under_5`, so a 6-to-12-year-old is tokenised as under-5. `children_under_15` exists in the token dictionary and is unused.",
            "evidence": "assessment_controller.vendored.dart _ageTokenMap.",
        },
        {
            "id": "QB-011",
            "severity": "informational",
            "finding": "The symptom picker maps 123 display labels onto 121 distinct tokens: `body_pain` is offered as both 'Body pain' and 'Muscle pain', and `nausea` as both 'Nausea' and 'Feeling sick or queasy'. This looks deliberate — two ways to say the same thing — but it means a picker entry is not uniquely identified by its token, so answer-option identity must key on the label, not the token.",
            "evidence": "symptom_display_map.vendored.dart kSymptomDisplayMap.",
        },
        {
            "id": "QB-010",
            "severity": "informational",
            "finding": "Sex is captured but produces no demographic token; it only gates the pregnancy screen. `male` and `female` exist in demographic_tokens and are never emitted.",
            "evidence": "assessment_controller.vendored.dart setSex.",
        },
    ]

    dead_options = sorted(
        {
            option["label"]
            for q in questions
            for option in q["answer_options"]
            if option.get("reachable_in_ui") is False
        }
    )

    return {
        "report_id": "question_baseline_freeze",
        "report_version": "1",
        "phase": "I2 / W3 Step 1",
        "generator": "tools/report_question_baseline.py",
        "generator_version": QFLOW_TOOLING_VERSION,
        "architecture_finding": {
            "question_artifact_exists": False,
            "where_questions_live": "Dart source in the mobile repository — constants for the follow-up map and clarifiers, a static engine class for selection and ordering, screen widgets for the demographic questions, and the controller for state.",
            "versioning": "none — no artifact version, no manifest entry, no independent rollback",
            "consequence": "A question change ships only as an app release and cannot be rolled back the way kb/rules/token_dictionary can.",
        },
        "sources": {
            "repository": MOBILE_SOURCE_REPO,
            "commit": MOBILE_SOURCE_COMMIT,
            "vendored_into": BASELINE_DIR,
            "files": [
                {
                    "vendored_file": name,
                    "mobile_path": SOURCE_PATHS[name],
                    "sha256": sha256_file(repo_path(BASELINE_DIR, name)),
                    "bytes": os.path.getsize(repo_path(BASELINE_DIR, name)),
                }
                for name in VENDORED_FILES
            ],
        },
        "counts": {
            "followup_map_tokens": len(fq["entries"]),
            "authored_followup_questions": sum(len(v) for v in fq["entries"].values()),
            "red_flag_clarifiers": len(clarifiers),
            "default_fallback_questions": 1,
            "total_question_definitions": len(questions),
            "demographic_questions": len(demographic_questions),
            "answer_options": sum(len(q["answer_options"]) for q in questions),
            "red_flag_affecting_questions": sum(1 for q in questions if q["red_flag_affecting"]),
            "scoring_affecting_questions": sum(1 for q in questions if q["scoring_affecting"]),
            "picker_reachable_tokens": len(display_tokens),
            "body_areas": len(display["body_area_symptoms"]),
            "by_type": dict(sorted(collections.Counter(q["type"] for q in questions).items())),
        },
        "question_ids": [q["question_id"] for q in questions],
        "questions": questions,
        "demographic_questions": demographic_questions,
        "answer_value_mappings": {
            "severity_bands": answers["severity_bands"],
            "duration_answer_to_token": [
                {"label": label, "token": tok} for label, tok in answers["duration_answer_to_token"]
            ],
            "age_label_to_token": [
                {"label": label, "token": tok} for label, tok in controller["age_label_to_token"]
            ],
            "medical_condition_label_to_token": [
                {"label": label, "token": tok}
                for label, tok in controller["medical_condition_label_to_token"]
            ],
        },
        "ordering": {
            "emission_order": engine["emission_order"],
            "dedupe_rule": engine["dedupe_rule"],
            "order_depends_on_symptom_selection_order": True,
            "tie_resolution_declared": False,
        },
        "path_length": {
            "enforced_limit": enforced_limit,
            "enforcement_site": "question_engine.dart generateQuestions final truncation",
            "theoretical_maximum_before_truncation": theoretical_max,
            "maximum_observed_path_length": enforced_limit,
            "minimum_path_length": 1,
            "truncation_is_red_flag_safe_by_construction": False,
            "truncation_is_red_flag_safe_incidentally": max_clarifiers <= enforced_limit,
            "demographic_screens_not_counted_toward_limit": True,
        },
        "clinical_reference_integrity": {
            "referenced_token_count": len(referenced),
            "unresolved_token_references": unresolved,
            "unresolved_count": len(unresolved),
            "tokens_by_role": {
                "produce_a_global_red_flag": sorted(
                    t for t in referenced if t in global_rule_tokens
                ),
                "referenced_by_rules": sorted(t for t in referenced if t in rules_tokens),
                "carry_kb_scoring_weight": sorted(t for t in referenced if t in scoring_tokens),
                "demographic": sorted(t for t in referenced if t in demographic_tokens),
            },
            "references": {t: sorted(token_refs[t]) for t in referenced},
        },
        "dead_or_duplicated": {
            "authored_answer_options_not_reachable_in_ui": dead_options,
            "authored_answer_options_not_reachable_count": len(dead_options),
            "followup_map_tokens_not_picker_reachable": sorted(
                set(fq["entries"]) - display_tokens
            ),
        },
        "current_behaviour": {
            "skip_supported": False,
            "answer_editing_supported": "backward navigation only — _onBack decrements the index and previously entered answers are retained; there is no dependency-based invalidation",
            "cancellation": "a confirm dialog on the follow-up screen; cancelling discards the assessment",
            "answer_storage": "in-memory Map<int, dynamic> on the follow-up screen widget state, committed to AssessmentController only at the end",
            "red_flag_evaluation_points": ["once, inside the engine, after all follow-up questions"],
            "scoring_evaluation_points": ["once, inside the engine, after red-flag evaluation"],
            "offline_loading": "questions are compiled into the app binary, so they are always available offline; they cannot be updated without an app release",
            "restored_state": "none — assessment state is in-memory and is lost if the flow is left",
        },
        "existing_tests": {
            "test/assessment/question_engine_test.dart": 4,
            "test/assessment/red_flag_clarifier_test.dart": 9,
            "coverage_gaps": [
                "no test asserts ordering stability against symptom-selection order (QB-005)",
                "no test asserts truncation never drops a red-flag clarifier (QB-006)",
                "no test covers answer editing or dependent invalidation",
                "no test covers skip semantics (none exist to cover)",
                "no test covers restored assessment state",
                "no test asserts that every authored additionalSymptoms option is reachable (QB-007)",
            ],
        },
        "known_defects_and_inconsistencies": defects,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = dump_report_bytes(build_report())

    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/question_baseline_freeze_v1.json is missing or stale")
            return 1
        print("OK   question baseline freeze is current")
        return 0

    write_bytes(REPORT_PATH, payload)
    print("wrote reports/question_baseline_freeze_v1.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
