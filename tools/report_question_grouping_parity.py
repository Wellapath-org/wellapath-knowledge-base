#!/usr/bin/env python3
"""Compare candidate 1.1 against real live-engine output, path by path.

    python3 tools/report_question_grouping_parity.py            # build report
    python3 tools/report_question_grouping_parity.py --check    # fail if stale

The comparison target is ``testing/questions/fixtures/oracle/`` — the ACTUAL
output of ``QuestionEngine.generateQuestions`` captured by running the real Dart
code, not a Python opinion about what it does. A reimplementation compared
against itself proves nothing.

Comparison keys are declared here rather than chosen to flatter the result:

  * QUESTION SET — the multiset of ``(clinical_role, red_flag_token)``. This is
    WHICH question is asked. Wording is compared separately, because on
    order-sensitive paths the baseline has two different answers and no single
    projection can match both.
  * WORDING — ``question_text`` per position, reported against forward-order
    live output AND reversed-order live output, both published.
  * OPTIONS — compared only for the roles whose live ``FollowupQuestion``
    actually carries options (additional_symptoms, red_flag_clarifier). Severity
    and duration carry an empty list in the Dart model; their answers come from
    the severity slider and duration chips, so there is nothing to compare and
    claiming a match would be a fabricated one.
  * TOKENS — the set of tokens any answer on this path could produce.
  * RED FLAGS — the set of red-flag tokens whose clarifier is asked.
  * TRUNCATION — the presented count, and whether the surviving set differs.

Standard library only. No network.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import MOBILE_SOURCE_COMMIT
from qflow.grouping import MAX_FOLLOWUP_QUESTIONS, bounded_subsets, plan_grouped
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
REPORT_PATH = repo_path("reports", "question_grouping_parity_v1_1.json")
GENERATOR = "tools/report_question_grouping_parity.py"

#: Roles whose live FollowupQuestion carries a populated `options` list.
ROLES_WITH_COMPARABLE_OPTIONS = ("additional_symptoms", "red_flag_clarifier")


def split_questions(candidate):
    grouped, clarifiers, default = [], [], None
    for question in candidate["questions"]:
        if "grouping" in question:
            grouped.append(question)
        elif question["clinical_role"] == "red_flag_clarifier":
            clarifiers.append(question)
        elif question["question_id"] == "Q-followup-default-duration":
            default = question
    if default is None:
        raise SystemExit("candidate has no default-duration question")
    return grouped, clarifiers, default


def identity_key(question):
    """WHICH question, independent of how it is worded."""
    return (question["role"], question.get("red_flag_token"))


def live_option_labels(question):
    return list(question["options"])


def planned_option_labels(question, by_id):
    """Presented labels, read from the artifact.

    Deliberately NOT derived by splitting the option id: a clarifier's id local
    part is `yes`/`no` while its label is `Yes`/`No`, and an earlier revision of
    this comparator reported 1,249 false option differences by assuming the two
    were the same string.
    """
    labels = {
        option["answer_option_id"]: option["label"]
        for option in by_id[question["question_id"]]["answer_options"]
    }
    return [labels[option] for option in question["options"]]


def planned_tokens(question, by_id):
    source = by_id[question["question_id"]]
    presented = set(question["options"])
    return {
        token
        for option in source["answer_options"]
        if option["answer_option_id"] in presented
        for token in option["produces_tokens"]
    }


def live_tokens(question):
    if question["role"] == "red_flag_clarifier":
        # The Yes branch produces the red-flag token; No produces nothing.
        return {question["red_flag_token"]}
    if question["role"] == "additional_symptoms":
        return set(question["options"])
    # Severity and duration produce tokens through the slider and chips, which
    # the Dart FollowupQuestion does not carry. Not comparable here.
    return None


def compare(case, candidate, grouped, clarifiers, default, by_id):
    live = case["questions"]
    planned, dropped = plan_grouped(case["input_tokens"], grouped, clarifiers, default)

    diffs = {}

    live_identity = sorted(
        (q["role"], q.get("red_flag_token")) for q in live
    )
    planned_identity = sorted(identity_key(q) for q in planned)
    if live_identity != planned_identity:
        diffs["question_set"] = {
            "live": live_identity,
            "candidate": planned_identity,
            "only_live": [k for k in live_identity if k not in planned_identity],
            "only_candidate": [k for k in planned_identity if k not in live_identity],
        }

    live_order = [(q["role"], q.get("red_flag_token")) for q in live]
    planned_order = [identity_key(q) for q in planned]
    if live_order != planned_order and "question_set" not in diffs:
        diffs["question_order"] = {"live": live_order, "candidate": planned_order}

    # Wording, positionally, only where the sets already agree.
    if "question_set" not in diffs and "question_order" not in diffs:
        wording = [
            {"role": lq["role"], "live": lq["question_text"],
             "candidate": pq["question_text"]}
            for lq, pq in zip(live, planned)
            if lq["question_text"] != pq["question_text"]
        ]
        if wording:
            diffs["wording"] = wording

        options = []
        tokens = []
        for lq, pq in zip(live, planned):
            if lq["role"] in ROLES_WITH_COMPARABLE_OPTIONS:
                live_labels = live_option_labels(lq)
                planned_labels = planned_option_labels(pq, by_id)
                if sorted(live_labels) != sorted(planned_labels):
                    options.append({"role": lq["role"], "live": live_labels,
                                    "candidate": planned_labels,
                                    "difference": "set"})
                elif live_labels != planned_labels:
                    options.append({"role": lq["role"], "live": live_labels,
                                    "candidate": planned_labels,
                                    "difference": "order_only"})
            expected = live_tokens(lq)
            if expected is not None:
                actual = planned_tokens(pq, by_id)
                if expected != actual:
                    tokens.append({"role": lq["role"],
                                   "live": sorted(expected),
                                   "candidate": sorted(actual)})
        if options:
            diffs["options"] = options
        if tokens:
            diffs["tokens"] = tokens

    live_red_flags = sorted(q["red_flag_token"] for q in live
                            if q["role"] == "red_flag_clarifier")
    planned_red_flags = sorted(q["red_flag_token"] for q in planned
                               if q["role"] == "red_flag_clarifier")
    if live_red_flags != planned_red_flags:
        diffs["red_flags"] = {"live": live_red_flags, "candidate": planned_red_flags}

    dropped_red_flags = [d for d in dropped if d["role"] == "red_flag_clarifier"]
    if dropped_red_flags:
        diffs["red_flag_dropped"] = [d["question_id"] for d in dropped_red_flags]

    if len(live) != len(planned):
        diffs["truncation_count"] = {"live": len(live), "candidate": len(planned)}
    if len(planned) > MAX_FOLLOWUP_QUESTIONS:
        diffs["path_limit_exceeded"] = len(planned)

    return planned, dropped, diffs


def build_report():
    candidate = load_json(CANDIDATE_PATH)
    oracle = load_json(ORACLE_PATH)
    grouped, clarifiers, default = split_questions(candidate)
    by_id = {q["question_id"]: q for q in candidate["questions"]}

    driving = oracle["_metadata"]["driving_tokens"]
    expected_paths = bounded_subsets(driving)
    if len(expected_paths) != len(oracle["forward"]):
        raise SystemExit("oracle path count %d does not match the bounded set %d"
                         % (len(oracle["forward"]), len(expected_paths)))

    counters = {
        "paths_compared": 0,
        "identical": 0,
        "question_set_differences": 0,
        "question_order_differences": 0,
        "wording_differences": 0,
        "option_set_differences": 0,
        "option_order_differences": 0,
        "token_effect_differences": 0,
        "red_flag_effect_differences": 0,
        "red_flag_questions_dropped": 0,
        "truncation_count_differences": 0,
        "path_limit_exceeded": 0,
    }
    failures = []
    forward_plans = {}
    forward_live = {}

    for case in oracle["forward"]:
        key = tuple(sorted(case["input_tokens"]))
        planned, _dropped, diffs = compare(case, candidate, grouped, clarifiers,
                                           default, by_id)
        forward_plans[key] = ([identity_key(q) for q in planned],
                              [q["question_text"] for q in planned],
                              [q["options"] for q in planned])
        forward_live[key] = [q["question_text"] for q in case["questions"]]

        counters["paths_compared"] += 1
        if not diffs:
            counters["identical"] += 1
        else:
            if "question_set" in diffs:
                counters["question_set_differences"] += 1
            if "question_order" in diffs:
                counters["question_order_differences"] += 1
            if "wording" in diffs:
                counters["wording_differences"] += 1
            for entry in diffs.get("options", []):
                if entry["difference"] == "set":
                    counters["option_set_differences"] += 1
                else:
                    counters["option_order_differences"] += 1
            if "tokens" in diffs:
                counters["token_effect_differences"] += 1
            if "red_flags" in diffs:
                counters["red_flag_effect_differences"] += 1
            if "red_flag_dropped" in diffs:
                counters["red_flag_questions_dropped"] += 1
            if "truncation_count" in diffs:
                counters["truncation_count_differences"] += 1
            if "path_limit_exceeded" in diffs:
                counters["path_limit_exceeded"] += 1
            if len(failures) < 50:
                failures.append({"input_tokens": case["input_tokens"],
                                 "differences": diffs})

    # Reversed selection order: the live engine changes its answer, the
    # candidate must not. Both facts are counted.
    reversed_counters = {
        "paths_compared": 0,
        "live_disagrees_with_itself": 0,
        "candidate_unstable": 0,
        "candidate_matches_reversed_live_wording": 0,
        "candidate_matches_forward_live_wording_only": 0,
    }
    instability = []
    for case in oracle["reversed"]:
        key = tuple(sorted(case["input_tokens"]))
        if key not in forward_plans:
            raise SystemExit("reversed case %r has no forward counterpart" % (key,))
        planned, _dropped, _diffs = compare(case, candidate, grouped, clarifiers,
                                            default, by_id)
        expected_identity, expected_wording, expected_options = forward_plans[key]
        actual_identity = [identity_key(q) for q in planned]
        actual_wording = [q["question_text"] for q in planned]
        actual_options = [q["options"] for q in planned]

        reversed_counters["paths_compared"] += 1
        if (actual_identity, actual_wording, actual_options) != (
                expected_identity, expected_wording, expected_options):
            reversed_counters["candidate_unstable"] += 1
            if len(instability) < 20:
                instability.append(case["input_tokens"])

        # Two separate facts, measured separately.
        reversed_live_wording = [q["question_text"] for q in case["questions"]]
        if reversed_live_wording != forward_live[key]:
            reversed_counters["live_disagrees_with_itself"] += 1
        if reversed_live_wording == expected_wording:
            reversed_counters["candidate_matches_reversed_live_wording"] += 1
        else:
            reversed_counters["candidate_matches_forward_live_wording_only"] += 1

    targets = {
        "zero_question_set_differences": counters["question_set_differences"] == 0,
        "zero_option_set_differences": counters["option_set_differences"] == 0,
        "zero_token_effect_differences": counters["token_effect_differences"] == 0,
        "zero_red_flag_effect_differences": counters["red_flag_effect_differences"] == 0,
        "zero_truncation_set_differences": counters["truncation_count_differences"] == 0,
        "zero_red_flag_questions_dropped": counters["red_flag_questions_dropped"] == 0,
        "path_limit_never_exceeded": counters["path_limit_exceeded"] == 0,
        "candidate_order_independent": reversed_counters["candidate_unstable"] == 0,
    }

    return {
        "_metadata": {
            "report_id": "question_grouping_parity",
            "version": "1.1",
            "generator": GENERATOR,
            "description": (
                "Path-by-path comparison of candidate 1.1 against real live-engine "
                "output. Every target below is COMPUTED from the comparison, never "
                "asserted."
            ),
            "candidate": {
                "path": "candidate/question_flow.ng.v1.1.json",
                "sha256": sha256_file(CANDIDATE_PATH),
                "version": candidate["_metadata"]["version"],
                "schema_version": candidate["_metadata"]["schema_version"],
            },
            "oracle": {
                "path": "testing/questions/fixtures/oracle/live_question_oracle_v1.json",
                "sha256": sha256_file(ORACLE_PATH),
                "source_commit": oracle["_metadata"]["source_commit"],
                "source_symbol": oracle["_metadata"]["source_symbol"],
                "captured_by": "running the real Dart implementation, not a reimplementation",
            },
            "mobile_source_commit": MOBILE_SOURCE_COMMIT,
            "comparison_keys": {
                "question_set": "multiset of (clinical_role, red_flag_token)",
                "wording": "question_text, positionally, reported separately",
                "options": "labels, for roles whose live FollowupQuestion carries options: %s"
                           % ", ".join(ROLES_WITH_COMPARABLE_OPTIONS),
                "options_not_compared": (
                    "severity and duration carry an empty options list in the live Dart "
                    "model — their answers come from the severity slider and duration "
                    "chips. There is nothing to compare, and no match is claimed."
                ),
                "tokens": "set of tokens any presented answer could produce",
                "red_flags": "set of red-flag tokens whose clarifier is presented",
            },
        },
        "bounded_path_set": {
            "driving_tokens": driving,
            "max_tokens_per_combination": oracle["_metadata"]["max_tokens_per_combination"],
            "forward_paths": len(oracle["forward"]),
            "reversed_paths": len(oracle["reversed"]),
        },
        "forward": counters,
        "reversed": reversed_counters,
        "targets": targets,
        "all_targets_met": all(targets.values()),
        "failing_paths": failures,
        "failing_path_sample_truncated_at": 50,
        "candidate_instability_sample": instability,
        "coverage_limits": [
            "Token subsets are bounded at size 3 over the 24 driving tokens (2,325 paths). Larger selections are representable in the app and are NOT covered here.",
            "The 24 driving tokens are those that reach a follow-up question or a clarifier trigger. The other 97 picker tokens exercise only the default-duration fallback, which IS covered.",
            "Demographic gating (sex, age, pregnancy) does not affect follow-up selection in the live engine and is not varied here.",
            "Answer VALUES are not varied: the live engine computes the question set before any follow-up answer exists. IM-003 would change that, and is not implemented.",
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
            print("FAIL reports/question_grouping_parity_v1_1.json is missing or stale")
            return 1
        print("OK   grouping parity report is reproducible, sha256:%s" % sha256_bytes(payload))
        return 0 if report["all_targets_met"] else 2

    write_bytes(REPORT_PATH, payload)
    forward = report["forward"]
    print("wrote reports/question_grouping_parity_v1_1.json")
    print("  paths compared:            %d" % forward["paths_compared"])
    print("  identical:                 %d" % forward["identical"])
    print("  question-set differences:  %d" % forward["question_set_differences"])
    print("  question-order differences:%d" % forward["question_order_differences"])
    print("  wording differences:       %d" % forward["wording_differences"])
    print("  option-set differences:    %d" % forward["option_set_differences"])
    print("  option-order differences:  %d" % forward["option_order_differences"])
    print("  token-effect differences:  %d" % forward["token_effect_differences"])
    print("  red-flag differences:      %d" % forward["red_flag_effect_differences"])
    print("  red-flag dropped:          %d" % forward["red_flag_questions_dropped"])
    print("  truncation differences:    %d" % forward["truncation_count_differences"])
    print("  path limit exceeded:       %d" % forward["path_limit_exceeded"])
    print("  reversed: live disagrees with itself on %d paths; candidate unstable on %d"
          % (report["reversed"]["live_disagrees_with_itself"],
             report["reversed"]["candidate_unstable"]))
    print("  ALL TARGETS MET:           %s" % report["all_targets_met"])
    if not report["all_targets_met"]:
        for name, met in sorted(report["targets"].items()):
            if not met:
                print("    UNMET: %s" % name)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
