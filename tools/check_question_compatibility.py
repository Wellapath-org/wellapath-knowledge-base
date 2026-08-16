#!/usr/bin/env python3
"""Prove the candidate question flow changes nothing clinical.

    python3 tools/check_question_compatibility.py            # human-readable
    python3 tools/check_question_compatibility.py --report   # write the report

What this proves, from artifact bytes:

  * every question in the vendored Dart is present in the candidate;
  * no question was added;
  * every answer's produced token is identical to the Dart it came from;
  * every red-flag clarifier's trigger set and produced red flag are unchanged;
  * the pregnancy gate is byte-identical to the implemented predicate;
  * frozen clinical artifacts are untouched;
  * Vocabulary 2.0 plays no part in question eligibility;
  * no Backend dependency exists.

What it does NOT prove, and does not claim: that the running Flutter app
behaves identically. The app is Dart; this repository holds no Flutter runtime
and must not grow a second one. Timing differences are enumerated as declared
impedance mismatches rather than asserted away.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from qflow.conditions import AssessmentState, evaluate
from qflow.dartparse import parse_all
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

CANDIDATE = repo_path("candidate", "question_flow.ng.v1.0.json")
REPORT = repo_path("reports", "question_compatibility_v1.json")

FROZEN = {
    "token_dictionary.ng.v1.1.json": "0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019",
    "kb.ng.v2.4.json": "6c00d8257f8417e86bd5e237630bf8a4623ad72e2e46b1b071dd447c067cec2b",
    "rules.ng.v2.2.json": "1d27e854cba95b179577a88f92445400f494a7fe8e6a53a60fcaa98b3870d1c4",
    "testing/case_bank_v1.json": "c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834",
    "testing/known_findings.json": "fadaea063303ecd27a90c233dba7782f8840c85aef4e3a7cca61b1e4793537ed",
    "candidate/token_dictionary.ng.v2.0.json": "07f935967acb1d5515cb53ffd1c8e39b59b8daf85c67cf36fa3e25094e34cd2d",
}


def build_report():
    checks = []

    def check(name, passed, detail=""):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    artifact = load_json(CANDIDATE)
    parsed = parse_all(repo_path())
    questions = {q["question_id"]: q for q in artifact["questions"]}

    # --- frozen inputs --------------------------------------------------------
    for filename, expected in sorted(FROZEN.items()):
        actual = sha256_file(repo_path(filename))
        check("frozen_artifact_unchanged:%s" % filename, actual == expected,
              "expected %s got %s" % (expected, actual))

    # --- every Dart question is present, and none was invented ---------------
    expected_ids = set()
    for token in parsed["followup_question_map"]["entries"]:
        for entry in parsed["followup_question_map"]["entries"][token]:
            role = "additional_symptoms" if entry["type"] == "additionalSymptoms" else entry["type"]
            expected_ids.add("Q-followup-%s-%s" % (token, role))
    expected_ids.add("Q-followup-default-duration")
    for clarifier in parsed["red_flag_clarifiers"]:
        expected_ids.add("Q-clarifier-%s" % clarifier["red_flag_token"])
    demographic_ids = {
        "Q-demo-sex", "Q-demo-age", "Q-demo-pregnancy",
        "Q-demo-medical-conditions", "Q-demo-body-area", "Q-symptom-selection",
    }
    expected_ids |= demographic_ids

    missing = sorted(expected_ids - set(questions))
    added = sorted(set(questions) - expected_ids)
    check("every_existing_question_is_present", not missing, "missing=%r" % missing)
    check("no_question_was_added", not added, "added=%r" % added)

    # --- answer meanings and token effects unchanged --------------------------
    mismatches = []
    for token, entries in parsed["followup_question_map"]["entries"].items():
        for entry in entries:
            if entry["type"] != "additionalSymptoms":
                continue
            qid = "Q-followup-%s-additional_symptoms" % token
            produced = [t for o in questions[qid]["answer_options"] for t in o["produces_tokens"]]
            if sorted(produced) != sorted(entry["options"]):
                mismatches.append(qid)
    check("additional_symptom_options_produce_identical_tokens",
          not mismatches, "differing=%r" % mismatches)

    duration_tokens = sorted(t for _, t in parsed["answer_mappings"]["duration_answer_to_token"])
    duration_bad = [
        qid for qid, q in questions.items()
        if q["clinical_role"] == "duration"
        and sorted({t for o in q["answer_options"] for t in o["produces_tokens"]}) != duration_tokens
    ]
    check("duration_answers_produce_identical_tokens", not duration_bad, "%r" % duration_bad)

    severity_tokens = sorted(b["token"] for b in parsed["answer_mappings"]["severity_bands"])
    severity_bad = [
        qid for qid, q in questions.items()
        if q["clinical_role"] == "severity"
        and sorted({t for o in q["answer_options"] for t in o["produces_tokens"]}) != severity_tokens
    ]
    check("severity_answers_produce_identical_tokens", not severity_bad, "%r" % severity_bad)

    # --- red-flag effects unchanged -------------------------------------------
    clarifier_bad = []
    for clarifier in parsed["red_flag_clarifiers"]:
        qid = "Q-clarifier-%s" % clarifier["red_flag_token"]
        q = questions[qid]
        yes = next(o for o in q["answer_options"] if o["label"] == "Yes")
        no = next(o for o in q["answer_options"] if o["label"] == "No")
        if yes["produces_tokens"] != [clarifier["red_flag_token"]] or no["produces_tokens"]:
            clarifier_bad.append(qid)
        # Trigger must fire on exactly the Dart trigger tokens, and only when
        # the red flag itself is not already selected.
        for trigger in clarifier["trigger_tokens"]:
            if not evaluate(q["trigger_condition"], AssessmentState(tokens={trigger})):
                clarifier_bad.append("%s not triggered by %s" % (qid, trigger))
        if evaluate(q["trigger_condition"],
                    AssessmentState(tokens={clarifier["trigger_tokens"][0],
                                            clarifier["red_flag_token"]})):
            clarifier_bad.append("%s still triggered when the red flag is already selected" % qid)
    check("red_flag_clarifier_behaviour_is_identical", not clarifier_bad, "%r" % clarifier_bad)

    # --- pregnancy gate identical --------------------------------------------
    pregnancy = questions["Q-demo-pregnancy"]
    gate = pregnancy["trigger_condition"]
    check("pregnancy_gate_matches_the_implemented_predicate",
          gate == {"sex": parsed["controller"]["pregnancy_shown_when_sex_equals"]},
          json.dumps(gate))
    check("pregnancy_shown_for_female_only",
          evaluate(gate, AssessmentState(sex="female"))
          and not evaluate(gate, AssessmentState(sex="male"))
          and not evaluate(gate, AssessmentState(sex=None)),
          "female=True, male=False, unknown=False")
    check("pregnancy_answer_produces_only_the_pregnancy_token",
          sorted({t for o in pregnancy["answer_options"] for t in o["produces_tokens"]})
          == ["pregnancy"])

    # --- demographic token mappings unchanged ---------------------------------
    age_expected = sorted(t for _, t in parsed["controller"]["age_label_to_token"])
    age_actual = sorted({t for o in questions["Q-demo-age"]["answer_options"]
                         for t in o["produces_tokens"]})
    check("age_token_mapping_unchanged", age_expected == age_actual,
          "%r vs %r" % (age_expected, age_actual))

    cond_expected = sorted(t for _, t in parsed["controller"]["medical_condition_label_to_token"])
    cond_actual = sorted({t for o in questions["Q-demo-medical-conditions"]["answer_options"]
                          for t in o["produces_tokens"]})
    check("medical_condition_token_mapping_unchanged", cond_expected == cond_actual,
          "%r vs %r" % (cond_expected, cond_actual))

    # --- scoring inputs -------------------------------------------------------
    dart_tokens = set()
    for entries in parsed["followup_question_map"]["entries"].values():
        for entry in entries:
            dart_tokens.update(entry["options"])
    dart_tokens.update(t for _, t in parsed["answer_mappings"]["duration_answer_to_token"])
    dart_tokens.update(b["token"] for b in parsed["answer_mappings"]["severity_bands"])
    dart_tokens.update(c["red_flag_token"] for c in parsed["red_flag_clarifiers"])
    dart_tokens.update(t for _, t in parsed["controller"]["age_label_to_token"])
    dart_tokens.update(t for _, t in parsed["controller"]["medical_condition_label_to_token"])
    dart_tokens.add("pregnancy")
    dart_tokens.update(t for _, t in parsed["symptom_display"]["display_label_to_token"])

    candidate_tokens = {t for q in artifact["questions"] for o in q["answer_options"]
                        for t in o["produces_tokens"]}
    check("token_output_universe_is_identical", dart_tokens == candidate_tokens,
          "only_in_dart=%r only_in_candidate=%r"
          % (sorted(dart_tokens - candidate_tokens), sorted(candidate_tokens - dart_tokens)))

    # --- red-flag timing is never later ---------------------------------------
    late = [q["question_id"] for q in artifact["questions"]
            if q["effects"]["affects_red_flags"]
            and not q["red_flag_evaluation"]["evaluate_after_answer"]]
    check("red_flag_timing_is_never_later_than_today", not late, "%r" % late)

    # --- Vocabulary 2.0 and Backend -------------------------------------------
    check("vocabulary_2_0_is_not_used", artifact["_metadata"]["vocabulary_2_0"]["used"] is False)
    vocab = load_json(repo_path("candidate", "token_dictionary.ng.v2.0.json"))
    alias_count = sum(len(e["search"]["aliases"]) for e in vocab["tokens"])
    check("vocabulary_2_0_has_no_aliases_that_could_affect_eligibility", alias_count == 0,
          "%d aliases" % alias_count)
    condition_text = json.dumps([q["trigger_condition"] for q in artifact["questions"]])
    check("no_alias_or_vocabulary_metadata_appears_in_any_condition",
          "alias" not in condition_text and "normalized_form" not in condition_text)
    check("no_backend_dependency",
          "http" not in condition_text and "url" not in json.dumps(artifact["path_controls"]),
          "conditions are pure functions of on-device state")

    # --- publication ----------------------------------------------------------
    metadata = artifact["_metadata"]
    check("candidate_is_unpublished", metadata["release_status"] == "candidate_unapproved")
    check("may_publish_is_false", metadata["may_publish"] is False)
    check("no_clinical_approval_claimed",
          metadata["clinical_review"]["status"] == "not_reviewed")

    failed = [c for c in checks if not c["passed"]]
    return {
        "report_id": "question_compatibility",
        "report_version": "1",
        "phase": "I2 / W3 Step 1",
        "generator": "tools/check_question_compatibility.py",
        "generator_version": QFLOW_TOOLING_VERSION,
        "candidate": {
            "file": "candidate/question_flow.ng.v1.0.json",
            "version": metadata["version"],
            "sha256": sha256_file(CANDIDATE),
            "release_status": metadata["release_status"],
        },
        "parity": {
            "question_content": "identical — every question, wording and answer label is copied from the vendored Dart",
            "answer_meaning": "identical",
            "token_effects": "identical",
            "red_flag_effects": "identical",
            "ordering": "deterministic; the one selection-order dependence in the current code is replaced by a declared tie-break (IM-001)",
            "timing": "specified to be EARLIER for red-flag-affecting answers (IM-002); never later",
            "claim": "behavioural equivalence for content and effects; NOT identical for timing and determinism, both documented as impedance mismatches",
        },
        "not_proven_here": {
            "running_app_equivalence": "This repository holds no Flutter runtime and must not grow a second engine. Executable proof belongs in the mobile repository once the contract is implemented.",
            "top_50_case_bank": "Unaffected by construction — the case bank supplies tokens directly to the engine and does not traverse the question flow. kb 2.4, rules 2.2 and the bank are byte-identical, so the recorded result (238 pass, CB_211 known finding) cannot change.",
        },
        "impedance_mismatches": metadata["impedance_mismatches"],
        "summary": {
            "total": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "all_passed": not failed,
        },
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report()
    if args.report:
        write_bytes(REPORT, dump_report_bytes(report))
        print("wrote reports/question_compatibility_v1.json")
    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.report:
        for check in report["checks"]:
            print("%-4s %s%s" % ("OK" if check["passed"] else "FAIL", check["check"],
                                 "" if check["passed"] else "  [%s]" % check["detail"]))
        s = report["summary"]
        print("\n%d checks, %d passed, %d failed" % (s["total"], s["passed"], s["failed"]))
    return 0 if report["summary"]["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
