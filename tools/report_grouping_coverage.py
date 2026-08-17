#!/usr/bin/env python3
"""Extend grouping parity beyond the captured oracle, honestly.

    python3 tools/report_grouping_coverage.py            # build
    python3 tools/report_grouping_coverage.py --check    # fail if stale

The oracle covers token subsets up to size 3. Users can select more. Capturing
real Dart output for larger subsets would mean adding a test to Mobile, which
this step is forbidden to do, so coverage is extended a different way:

  1. ``qflow.grouping.live_effective_questions`` is a transcription of
     ``QuestionEngine.generateQuestions``. It is first VALIDATED against all
     4,625 real captured cases — forward and reversed. Any mismatch fails this
     report outright.
  2. Only if it matches every real case is it used to extend comparison to
     subsets of size 4 and 5.

Stage 2 is therefore evidence from a MODEL that has been proven faithful on
4,625 real cases — not evidence from live output, and it is labelled as such
everywhere it appears. A transcription validated on 4,625 cases can still be
wrong on a case those 4,625 never exercised; the residual risk is stated rather
than rounded away.

Standard library only. No network.
"""

import argparse
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.dartparse import parse_all
from qflow.grouping import live_effective_questions, plan_grouped
from report_question_grouping_parity import identity_key, split_questions
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
    write_bytes,
)

CANDIDATE_PATH = repo_path("candidate", "question_flow.ng.v1.1.json")
ORACLE_PATH = repo_path("testing", "questions", "fixtures", "oracle",
                        "live_question_oracle_v1.json")
REPORT_PATH = repo_path("reports", "question_grouping_coverage_v1_1.json")
GENERATOR = "tools/report_grouping_coverage.py"

EXTENDED_SIZES = (4, 5)


def baseline_inputs():
    parsed = parse_all(repo_path())
    followup_map = {
        token: [
            {"type": entry["type"], "question_text": entry["question_text"],
             "options": list(entry["options"])}
            for entry in entries
        ]
        for token, entries in parsed["followup_question_map"]["entries"].items()
    }
    return followup_map, parsed["followup_question_map"]["default_question"], \
        parsed["red_flag_clarifiers"]


def live_shape(questions):
    return [
        (q["role"], q.get("red_flag_token"), q["question_text"], tuple(q["options"]))
        for q in questions
    ]


def validate_transcription(oracle, followup_map, default_question, clarifiers):
    """Stage 1. The transcription must reproduce every real captured case."""
    mismatches = []
    compared = 0
    for direction in ("forward", "reversed"):
        for case in oracle[direction]:
            compared += 1
            modelled = live_effective_questions(
                case["input_tokens"], followup_map, default_question, clarifiers)
            if live_shape(modelled) != live_shape(case["questions"]):
                if len(mismatches) < 20:
                    mismatches.append({
                        "direction": direction,
                        "input_tokens": case["input_tokens"],
                        "real": live_shape(case["questions"]),
                        "modelled": live_shape(modelled),
                    })
    return compared, mismatches


def extended_comparison(followup_map, default_question, clarifiers,
                        grouped, clarifier_questions, default, driving):
    """Stage 2. Sizes the oracle does not reach, using the validated model."""
    results = {}
    for size in EXTENDED_SIZES:
        counters = {
            "paths_compared": 0,
            "question_set_differences": 0,
            "option_set_differences": 0,
            "red_flag_effect_differences": 0,
            "truncation_count_differences": 0,
            "red_flag_questions_dropped": 0,
            "path_limit_exceeded": 0,
            "live_order_sensitive": 0,
            "candidate_order_independent": True,
        }
        failures = []
        for combination in itertools.combinations(driving, size):
            tokens = list(combination)
            modelled = live_effective_questions(
                tokens, followup_map, default_question, clarifiers)
            reversed_modelled = live_effective_questions(
                list(reversed(tokens)), followup_map, default_question, clarifiers)
            planned, dropped = plan_grouped(tokens, grouped, clarifier_questions, default)
            reversed_planned, _ = plan_grouped(
                list(reversed(tokens)), grouped, clarifier_questions, default)

            counters["paths_compared"] += 1
            if live_shape(modelled) != live_shape(reversed_modelled):
                counters["live_order_sensitive"] += 1
            if [identity_key(q) for q in planned] != [identity_key(q) for q in reversed_planned]:
                counters["candidate_order_independent"] = False

            diffs = {}
            live_identity = sorted((q["role"], q.get("red_flag_token")) for q in modelled)
            planned_identity = sorted(identity_key(q) for q in planned)
            if live_identity != planned_identity:
                counters["question_set_differences"] += 1
                diffs["question_set"] = {"live": live_identity, "candidate": planned_identity}

            live_red_flags = sorted(q["red_flag_token"] for q in modelled
                                    if q["role"] == "red_flag_clarifier")
            planned_red_flags = sorted(q["red_flag_token"] for q in planned
                                       if q["role"] == "red_flag_clarifier")
            if live_red_flags != planned_red_flags:
                counters["red_flag_effect_differences"] += 1
                diffs["red_flags"] = {"live": live_red_flags, "candidate": planned_red_flags}

            if any(d["role"] == "red_flag_clarifier" for d in dropped):
                counters["red_flag_questions_dropped"] += 1
                diffs["red_flag_dropped"] = True

            if len(modelled) != len(planned):
                counters["truncation_count_differences"] += 1
                diffs["truncation"] = {"live": len(modelled), "candidate": len(planned)}
            if len(planned) > 5:
                counters["path_limit_exceeded"] += 1

            if not diffs:
                continue
            # Option sets, only where both agree on what is asked.
            if "question_set" not in diffs:
                pass
            if len(failures) < 25:
                failures.append({"input_tokens": tokens, "differences": diffs})

        # Option comparison needs matching sets; run it separately so a set
        # difference cannot mask an option difference or vice versa.
        for combination in itertools.combinations(driving, size):
            tokens = list(combination)
            modelled = live_effective_questions(
                tokens, followup_map, default_question, clarifiers)
            planned, _ = plan_grouped(tokens, grouped, clarifier_questions, default)
            if len(modelled) != len(planned):
                continue
            for live_q, planned_q in zip(modelled, planned):
                if live_q["role"] != "additional_symptoms":
                    continue
                planned_labels = [o.split("::", 1)[1] for o in planned_q["options"]]
                if sorted(planned_labels) != sorted(live_q["options"]):
                    counters["option_set_differences"] += 1

        counters["failing_paths"] = failures
        results["size_%d" % size] = counters
    return results


def build_report():
    candidate = load_json(CANDIDATE_PATH)
    oracle = load_json(ORACLE_PATH)
    followup_map, default_question, clarifiers = baseline_inputs()
    grouped, clarifier_questions, default = split_questions(candidate)
    driving = oracle["_metadata"]["driving_tokens"]

    compared, mismatches = validate_transcription(
        oracle, followup_map, default_question, clarifiers)
    transcription_faithful = not mismatches

    extended = None
    if transcription_faithful:
        extended = extended_comparison(
            followup_map, default_question, clarifiers,
            grouped, clarifier_questions, default, driving)

    extended_clean = transcription_faithful and all(
        counters["question_set_differences"] == 0
        and counters["option_set_differences"] == 0
        and counters["red_flag_effect_differences"] == 0
        and counters["truncation_count_differences"] == 0
        and counters["red_flag_questions_dropped"] == 0
        and counters["path_limit_exceeded"] == 0
        and counters["candidate_order_independent"]
        for counters in (extended or {}).values()
    )

    return {
        "_metadata": {
            "report_id": "question_grouping_coverage",
            "version": "1.1",
            "generator": GENERATOR,
            "description": (
                "Two-stage coverage extension. Stage 1 validates the Python "
                "transcription of the live engine against every real captured case. "
                "Stage 2 uses it — and only if stage 1 is clean — to reach subset "
                "sizes the oracle does not contain."
            ),
            "candidate_sha256": sha256_file(CANDIDATE_PATH),
            "oracle_sha256": sha256_file(ORACLE_PATH),
            "evidence_strength": {
                "stage_1": "REAL. Output of the live Dart implementation.",
                "stage_2": (
                    "MODEL-DERIVED. A transcription validated on %d real cases, applied "
                    "to subsets the oracle does not contain. Weaker evidence than stage "
                    "1 and labelled as such wherever it is cited." % compared
                ),
            },
        },
        "stage_1_transcription_validation": {
            "real_cases_compared": compared,
            "mismatches": len(mismatches),
            "faithful": transcription_faithful,
            "mismatch_sample": mismatches,
            "note": (
                "Compares role, red-flag token, question text and option list, "
                "positionally, in both selection directions. A single mismatch blocks "
                "stage 2 entirely."
            ),
        },
        "stage_2_extended_sizes": extended,
        "stage_2_ran": transcription_faithful,
        "all_clean": extended_clean,
        "residual_risk": [
            "Stage 2 is not live output. A transcription that matches 4,625 real cases can still diverge on behaviour none of them exercises.",
            "Subsets above size 5 are not covered at either stage.",
            "The 24 driving tokens are those reaching a follow-up or clarifier trigger; combinations mixing them with the other 97 picker tokens are covered only at sizes <= 3, via the oracle.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report = build_report()
    payload = dump_artifact_bytes(report)

    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/question_grouping_coverage_v1_1.json is missing or stale")
            return 1
        print("OK   grouping coverage report is reproducible, sha256:%s" % sha256_bytes(payload))
        return 0 if report["all_clean"] else 2

    write_bytes(REPORT_PATH, payload)
    stage1 = report["stage_1_transcription_validation"]
    print("wrote reports/question_grouping_coverage_v1_1.json")
    print("  stage 1: %d real cases compared, %d mismatches, faithful=%s"
          % (stage1["real_cases_compared"], stage1["mismatches"], stage1["faithful"]))
    if not stage1["faithful"]:
        print("  stage 2 SKIPPED — the transcription is not faithful, so it may not be used")
        return 2
    for size, counters in sorted((report["stage_2_extended_sizes"] or {}).items()):
        print("  %s: %d paths | set diffs %d | option diffs %d | red-flag diffs %d | "
              "truncation diffs %d | live order-sensitive %d | candidate stable %s"
              % (size, counters["paths_compared"], counters["question_set_differences"],
                 counters["option_set_differences"], counters["red_flag_effect_differences"],
                 counters["truncation_count_differences"], counters["live_order_sensitive"],
                 counters["candidate_order_independent"]))
    print("  ALL CLEAN: %s" % report["all_clean"])
    return 0 if report["all_clean"] else 2


if __name__ == "__main__":
    sys.exit(main())
