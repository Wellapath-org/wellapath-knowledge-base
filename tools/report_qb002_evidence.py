#!/usr/bin/env python3
"""Reproduce and document QB-002 — delayed red-flag evaluation.

    python3 tools/report_qb002_evidence.py            # write the report
    python3 tools/report_qb002_evidence.py --check    # fail if stale

QB-002: a red-flag clarifier answered "Yes" does not interrupt the assessment.
The answer sits in a local map until the LAST follow-up question is answered,
at which point `_commitAnswers()` runs and the engine finally sees it.

This traces the defect from the vendored Dart and simulates the delay for every
reachable clarifier path, so the finding is measured rather than asserted. It
modifies nothing in Mobile.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import MOBILE_SOURCE_COMMIT, QFLOW_TOOLING_VERSION
from qflow.conditions import AssessmentState
from qflow.dartparse import parse_all
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

import validate_question_flow as vqf

REPORT_PATH = repo_path("reports", "qb002_evidence_v1.json")
CANDIDATE = repo_path("candidate", "question_flow.ng.v1.0.json")


def simulate_delay(artifact, parsed):
    """For every clarifier, how many further questions can follow a 'Yes'?"""
    followups = [q for q in artifact["questions"] if q["clinical_role"] not in
                 ("demographic", "body_area", "symptom_picker")]
    controls = artifact["path_controls"]
    scenarios = []

    # A clarifier fires when a trigger token is selected. Pair each trigger with
    # authored follow-up tokens so ordinary questions queue behind it.
    authored = sorted(parsed["followup_question_map"]["entries"])
    for clarifier in parsed["red_flag_clarifiers"]:
        trigger = clarifier["trigger_tokens"][0]
        for companions in ([], authored[:1], authored[:2], authored[:3]):
            tokens = {trigger} | set(companions)
            ordered = vqf.eligible(followups, AssessmentState(tokens=tokens))
            kept = vqf.apply_truncation(ordered, controls)
            ids = [q["question_id"] for q in kept]
            qid = "Q-clarifier-%s" % clarifier["red_flag_token"]
            if qid not in ids:
                continue
            position = ids.index(qid)
            after = len(ids) - position - 1
            scenarios.append({
                "red_flag_token": clarifier["red_flag_token"],
                "trigger_token": trigger,
                "companion_tokens": sorted(companions),
                "presented_questions": ids,
                "clarifier_position_1_indexed": position + 1,
                "questions_presented_after_the_yes": after,
                "questions_after_ids": ids[position + 1:],
                "baseline_evaluated_at": "after question %d of %d (_commitAnswers)" % (len(ids), len(ids)),
                "contract_requires_evaluation_at": "immediately after question %d" % (position + 1),
                "delay_in_questions": after,
            })
    return scenarios


def build_report():
    parsed = parse_all(repo_path())
    artifact = load_json(CANDIDATE)
    scenarios = simulate_delay(artifact, parsed)
    worst = max((s["delay_in_questions"] for s in scenarios), default=0)

    return {
        "report_id": "qb002_evidence",
        "report_version": "1",
        "phase": "I2 / W3 Step 1A",
        "generator": "tools/report_qb002_evidence.py",
        "generator_version": QFLOW_TOOLING_VERSION,
        "defect": {
            "id": "QB-002",
            "severity": "high",
            "title": "A red-flag clarifier answered 'Yes' does not interrupt the assessment",
            "mobile_commit": MOBILE_SOURCE_COMMIT,
            "mobile_unmodified": True,
        },
        "reproduction": {
            "steps": [
                "Select a near-miss token that raises a clarifier — e.g. `difficulty_breathing`.",
                "Select at least one further symptom that authors its own follow-up questions, so ordinary questions queue behind the clarifier.",
                "Open the follow-up screen. The clarifier is presented FIRST (clarifiers sort ahead of severity/duration/additional).",
                "Answer 'Yes' — declaring the danger sign.",
                "Observe: the flow advances to the NEXT ORDINARY QUESTION. No interruption, no emergency screen.",
                "Continue answering until the last follow-up question.",
                "Only then does the engine see the red-flag token.",
            ],
            "observed": "The assessment continues normally after the danger sign is declared.",
            "expected_under_the_contract": "Branching stops immediately; emergency presentation wins.",
        },
        "code_trace": {
            "answer_capture": {
                "file": "baseline/questions_v1/followup_screen.vendored.dart",
                "symbol": "_answers",
                "line": 30,
                "code": "final Map<int, dynamic> _answers = {};",
                "note": "The answer is held in widget state, keyed by list index. Nothing clinical happens here.",
            },
            "advance": {
                "file": "baseline/questions_v1/followup_screen.vendored.dart",
                "symbol": "_onNext",
                "lines": "69-80",
                "code": "if (_currentQuestion < _questions.length - 1) { ...recordStepView(); setState(() => _currentQuestion += 1); } else { _commitAnswers(); Navigator.push(LoadingScreen) }",
                "note": "The ONLY branch that commits anything is the else — reached exclusively on the last question.",
            },
            "commit": {
                "file": "baseline/questions_v1/followup_screen.vendored.dart",
                "symbol": "_commitAnswers",
                "line": 90,
                "note": "Iterates every stored answer and, for a redFlagClarifier answered 'Yes', calls assessmentController.addSymptomToken(question.redFlagToken!). This is the first moment the red-flag token exists in assessment state.",
            },
            "evaluation": {
                "file": "wellapath-mobile lib/core/engine/red_flag_evaluator.dart",
                "symbol": "RedFlagEvaluator.evaluate",
                "note": "The only red-flag evaluation site in the app. It is reached via LoadingScreen -> EngineController.run, i.e. after the whole follow-up sequence.",
            },
        },
        "timing": {
            "when_commit_answers_occurs": "on _onNext from the LAST follow-up question, immediately before Navigator.push(LoadingScreen)",
            "when_the_evaluator_actually_runs": "inside EngineController.run, after LoadingScreen mounts — one navigation after the last answer",
            "worst_case_delay_in_questions": worst,
            "delay_unit": "ordinary follow-up questions presented after the danger sign was declared",
            "scenarios_measured": len(scenarios),
            "scenarios": scenarios,
        },
        "safety_analysis": {
            "can_scoring_override_the_eventual_red_flag": False,
            "why_not": [
                "RedFlagEvaluator.evaluate runs BEFORE ScoringEngine.score; when a global rule matches it returns proceedToScoring:false.",
                "ScoringEngine.score throws StateError if called with proceed_to_scoring false, so scoring cannot run on a red-flag path at all.",
                "UrgencyDeterminer checks redFlagResult.redFlagTriggered first (priority 1) and returns emergency with urgencySource 'global_red_flag' before any scoring-derived path is considered.",
                "Verified by the 239-case bank: 124/124 red-flag cases returned emergency with no ranked causes, and 0 safety-critical under-triage.",
            ],
            "actual_harm": "Not a wrong RESULT — the final urgency is correct. The harm is that a user who has declared a danger sign is asked further routine questions before being told to seek emergency care, and may abandon the assessment before reaching the result.",
            "under_triage_risk": "None from this defect on a completed assessment. The risk is abandonment before completion, which yields no advice at all.",
        },
        "earliest_safe_interception_point": {
            "point": "followup_screen.dart _onNext, in the `if (_currentQuestion < _questions.length - 1)` branch, BEFORE setState advances the index",
            "why_here": [
                "It is the first place the app knows an answer is final for the current question.",
                "It is inside the widget that owns both the answer map and the navigation, so no new plumbing is needed.",
                "It is before the step-view telemetry call, so an interrupted path emits no extra step event.",
            ],
            "required_shape": "Commit the current answer to AssessmentController, evaluate red flags, and only advance if none fired. If one fired, navigate to the emergency presentation instead of the next question.",
            "why_not_commit_answers": "_commitAnswers is only ever reached on the last question; correcting it there would not remove the delay.",
            "why_not_the_engine": "The engine already behaves correctly. The defect is in when the flow calls it, not in what it does.",
        },
        "scope": {
            "mobile_modified": False,
            "fix_included_here": False,
            "note": "This step records evidence only. The correction is the first Mobile W3 task — see mobile_handoff/question_flow_v1/IM002_SAFETY_FIX.md.",
        },
        "frozen_inputs": {
            "candidate_sha256": sha256_file(CANDIDATE),
            "baseline_freeze_sha256": sha256_file(repo_path("reports", "question_baseline_freeze_v1.json")),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = dump_report_bytes(build_report())
    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/qb002_evidence_v1.json is missing or stale")
            return 1
        print("OK   QB-002 evidence report is current")
        return 0

    write_bytes(REPORT_PATH, payload)
    report = build_report()
    print("wrote reports/qb002_evidence_v1.json")
    print("  scenarios measured: %d" % report["timing"]["scenarios_measured"])
    print("  worst-case delay:   %d ordinary questions after the danger sign"
          % report["timing"]["worst_case_delay_in_questions"])
    print("  scoring can override the red flag: %s"
          % report["safety_analysis"]["can_scoring_override_the_eventual_red_flag"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
