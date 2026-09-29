#!/usr/bin/env python3
"""Generate authoritative path fixtures for candidate 1.1.

    python3 tools/build_grouping_path_fixtures.py            # write
    python3 tools/build_grouping_path_fixtures.py --check    # fail if stale

These are what Mobile asserts against. Every case carries the expected presented
questions AND, where the scenario falls inside the captured oracle, the real
live-engine output alongside it — so a consumer test cannot pass by agreeing
with a Python model that has drifted from the app.

A scenario the oracle does not contain is marked
``live_evidence: "not_captured"`` rather than being given a modelled expectation
dressed up as live output.

Every input is synthetic and spec-derived: real tokens, no invented symptom, no
real-user assessment data.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.grouping import plan_grouped
from report_question_grouping_parity import planned_option_labels, split_questions
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
FIXTURE_PATH = repo_path("testing", "questions", "fixtures", "paths",
                         "grouping_path_fixtures_v1_1.json")
GENERATOR = "tools/build_grouping_path_fixtures.py"

SCENARIOS = [
    ("no_symptom_selected",
     "Nothing selected — no follow-up question at all. Candidate 1.0 wrongly asked the default duration question here.",
     []),
    ("single_token_all_three_roles",
     "One token offering severity, duration and additional symptoms — one question each, not one per role per token",
     ["headache"]),
    ("two_tokens_one_severity_question",
     "Two tokens both offering severity — the group presents ONE severity question, worded from the lower source_order_index",
     ["headache", "body_pain"]),
    ("three_tokens_option_union",
     "Three tokens contributing additional-symptom options — the presented options are the union of the triggered sources only",
     ["cough", "fever", "headache"]),
    ("token_without_severity_entry",
     "A token offering duration and additional symptoms but no severity — no severity question is presented",
     ["fever"]),
    ("mapped_token_without_duration_entry",
     "chest_indrawing_severe has no duration entry; alone it triggers neither a grouped duration nor the fallback",
     ["chest_indrawing_severe"]),
    ("unmapped_token_uses_default_duration",
     "A selectable token with no authored follow-up — the default duration question fires",
     ["boils"]),
    ("duration_less_mapped_token_plus_unmapped",
     "The GF-006 case: a mapped token with no duration entry plus an unmapped one. Live asks the default duration; candidate 1.0 did not.",
     ["chest_indrawing_severe", "boils"]),
    ("unmapped_token_suppressed_by_grouped_duration",
     "An unmapped token alongside a duration-bearing token — the grouped duration wins and the fallback stays silent",
     ["boils", "fever"]),
    ("single_clarifier",
     "A near-miss token raises its clarifier; the clarifier is never grouped",
     ["difficulty_breathing"]),
    ("clarifier_suppressed_when_red_flag_selected",
     "The red-flag token itself is selected, so its clarifier is suppressed",
     ["difficulty_breathing", "breathlessness_at_rest"]),
    ("two_clarifiers_declaration_order",
     "Two clarifiers present. Emission order is kRedFlagClarifiers declaration order, NOT alphabetical by red-flag token (GF-008).",
     ["difficulty_breathing", "bleeding"]),
    ("three_clarifiers_at_the_limit",
     "All three clarifiers plus grouped follow-ups — truncation applies, and no clarifier is dropped",
     ["difficulty_breathing", "poor_feeding", "bleeding", "headache", "fever"]),
    ("clarifiers_plus_all_three_groups",
     "Two clarifiers plus severity, duration and additional symptoms — exactly the limit of 5",
     ["difficulty_breathing", "bleeding", "headache"]),
    ("order_sensitive_baseline",
     "A selection where the live engine's wording depends on tap order. The candidate is stable; this fixture pins WHICH wording it picks.",
     ["abdominal_cramps", "body_pain", "cough"]),
    ("maximum_option_union",
     "Three additional-symptom sources with overlapping options — the union de-duplicates by option id",
     ["fever", "nausea", "vomiting"]),
]


def presented(candidate, tokens):
    """Returns (dropped_red_flag_ids, presented_questions, truncated_ids).

    The dropped-red-flag list is COMPUTED, not asserted empty. It is empty by
    construction in `plan_grouped`, but a fixture that hard-codes the answer
    proves nothing about the code that produced it.
    """
    grouped, clarifiers, default = split_questions(candidate)
    by_id = {q["question_id"]: q for q in candidate["questions"]}
    kept, dropped = plan_grouped(tokens, grouped, clarifiers, default)
    dropped_red_flags = [
        d["question_id"] for d in dropped if d["role"] == "red_flag_clarifier"
    ]
    return dropped_red_flags, [
        {
            "question_id": question["question_id"],
            "clinical_role": question["role"],
            "question_text": question["question_text"],
            "representative_source": question.get("representative_source"),
            "contributing_sources": question.get("contributing_sources"),
            "presented_option_labels": planned_option_labels(question, by_id),
            "red_flag_token": question["red_flag_token"],
        }
        for question in kept
    ], [d["question_id"] for d in dropped]


def build():
    candidate = load_json(CANDIDATE_PATH)
    oracle = load_json(ORACLE_PATH)
    live_by_key = {
        tuple(sorted(case["input_tokens"])): case["questions"]
        for case in oracle["forward"]
    }

    cases = []
    for fixture_id, description, tokens in SCENARIOS:
        dropped_red_flags, questions, dropped = presented(candidate, tokens)
        key = tuple(sorted(tokens))
        live = live_by_key.get(key)
        case = {
            "fixture_id": fixture_id,
            "description": description,
            "selected_tokens": sorted(tokens),
            "expected": {
                "presented_questions": questions,
                "presented_count": len(questions),
                "truncated_question_ids": dropped,
                "red_flag_questions_dropped": dropped_red_flags,
            },
        }
        if live is None:
            case["live_evidence"] = "not_captured"
            case["live_evidence_note"] = (
                "This token set is outside the captured oracle (it mixes driving tokens "
                "with picker tokens the oracle does not enumerate). The expectation is "
                "model-derived and is NOT presented as live output."
            )
        else:
            case["live_evidence"] = "captured"
            case["live_questions"] = [
                {"clinical_role": q["role"], "question_text": q["question_text"],
                 "options": q["options"], "red_flag_token": q["red_flag_token"]}
                for q in live
            ]
        cases.append(case)

    captured = sum(1 for c in cases if c["live_evidence"] == "captured")
    return {
        "_metadata": {
            "fixture_id": "question_grouping_paths",
            "fixture_version": "1.1",
            "generator": GENERATOR,
            "synthetic": True,
            "note": (
                "All inputs are synthetic and spec-derived. No real-user assessment "
                "data is used and no symptom combination is invented beyond tokens "
                "that already exist in the picker."
            ),
            "artifact": {
                "file": "candidate/question_flow.ng.v1.1.json",
                "version": candidate["_metadata"]["version"],
                "schema_version": candidate["_metadata"]["schema_version"],
                "sha256": sha256_file(CANDIDATE_PATH),
            },
            "oracle": {
                "file": "testing/questions/fixtures/oracle/live_question_oracle_v1.json",
                "sha256": sha256_file(ORACLE_PATH),
                "source_commit": oracle["_metadata"]["source_commit"],
            },
            "case_count": len(cases),
            "cases_with_captured_live_output": captured,
            "cases_without_captured_live_output": len(cases) - captured,
            "how_to_use": (
                "A Mobile test must assert `expected.presented_questions` exactly. Where "
                "`live_evidence` is `captured`, it must ALSO assert that the live "
                "questions listed agree on role, red-flag token and option labels — a "
                "consumer that only agrees with the model proves nothing."
            ),
        },
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    fixtures = build()
    payload = dump_artifact_bytes(fixtures)

    if args.check:
        if not os.path.exists(FIXTURE_PATH) or open(FIXTURE_PATH, "rb").read() != payload:
            print("FAIL grouping path fixtures are missing or stale")
            return 1
        print("OK   grouping path fixtures are reproducible, sha256:%s" % sha256_bytes(payload))
        return 0

    write_bytes(FIXTURE_PATH, payload)
    metadata = fixtures["_metadata"]
    print("wrote testing/questions/fixtures/paths/grouping_path_fixtures_v1_1.json")
    print("  cases:                    %d" % metadata["case_count"])
    print("  with captured live output: %d" % metadata["cases_with_captured_live_output"])
    print("  model-derived only:        %d" % metadata["cases_without_captured_live_output"])
    print("  sha256:                    %s" % sha256_bytes(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
