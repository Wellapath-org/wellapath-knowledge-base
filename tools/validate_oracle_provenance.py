#!/usr/bin/env python3
"""Pin and re-verify the captured live-oracle fixture.

    python3 tools/validate_oracle_provenance.py            # verify + write record
    python3 tools/validate_oracle_provenance.py --check     # verify only, fail if stale

The oracle is the evidence everything else rests on, so it is treated as
immutable: this tool NEVER writes to the fixture. It writes a sidecar provenance
record and re-derives the fixture's structure from first principles.

The checks are deliberately independent of the capture harness. A fixture
assembled by hand rather than captured would have to reproduce the bounded
enumeration, the exact input ordering, the reversed-case selection rule, the
output field set and the role vocabulary — all of which are derived here, not
read from the fixture's own metadata.

Structural evidence is not the whole case. The other half is
`reports/question_grouping_coverage_v1_1.json` stage 1, where a separately
written transcription of `question_engine.dart` reproduces all 4,625 cases with
zero mismatches. Neither check alone is conclusive; together they are.

Standard library only. No network.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.grouping import MAX_FOLLOWUP_QUESTIONS, ROLE_ORDER, bounded_subsets
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
    write_bytes,
)

ORACLE_PATH = repo_path("testing", "questions", "fixtures", "oracle",
                        "live_question_oracle_v1.json")
HARNESS_PATH = repo_path("testing", "questions", "fixtures", "oracle",
                         "live_question_oracle_v1.harness.dart.txt")
RECORD_PATH = repo_path("testing", "questions", "fixtures", "oracle",
                        "live_question_oracle_v1.provenance.json")
GENERATOR = "tools/validate_oracle_provenance.py"

MOBILE_REPO = "Wellapath-org/wellapath-mobile"
MOBILE_COMMIT = "657739cc1745104dd1194a57ef14cc9793c9b98e"
SOURCE_SYMBOL = "QuestionEngine.generateQuestions"

#: The only fields a case may carry. An extra field means the capture recorded
#: something the contract does not describe — including, potentially, state the
#: engine does not read.
CASE_FIELDS = {"input_tokens", "questions"}
QUESTION_FIELDS = {"role", "question_text", "options", "red_flag_token"}

#: Field names that would indicate demographic or identifying state was
#: captured. generateQuestions reads none of these, so none may appear.
FORBIDDEN_FIELDS = {
    "sex", "age", "age_token", "pregnancy", "pregnant", "body_area",
    "medical_conditions", "patient", "patient_id", "user", "user_id",
    "device", "device_id", "session", "session_id", "timestamp", "name",
    "phone", "email", "location",
}


def check(oracle):
    errors = []
    metadata = oracle["_metadata"]

    # --- declared provenance ------------------------------------------------
    if metadata.get("source_repository") != MOBILE_REPO:
        errors.append("source_repository is %r, expected %r"
                      % (metadata.get("source_repository"), MOBILE_REPO))
    if metadata.get("source_commit") != MOBILE_COMMIT:
        errors.append("source_commit is %r, expected %r"
                      % (metadata.get("source_commit"), MOBILE_COMMIT))
    if metadata.get("source_symbol") != SOURCE_SYMBOL:
        errors.append("source_symbol is %r, expected %r"
                      % (metadata.get("source_symbol"), SOURCE_SYMBOL))

    driving = metadata.get("driving_tokens") or []
    if driving != sorted(driving):
        errors.append("driving_tokens are not sorted, so the enumeration order "
                      "below is not reproducible")
    if len(set(driving)) != len(driving):
        errors.append("driving_tokens contain duplicates")

    # --- enumeration re-derived, not read -----------------------------------
    expected_subsets = bounded_subsets(driving)
    forward = oracle["forward"]
    if len(forward) != len(expected_subsets):
        errors.append("forward has %d cases; the bounded enumeration over %d tokens "
                      "at size <= %s yields %d"
                      % (len(forward), len(driving),
                         metadata.get("max_tokens_per_combination"),
                         len(expected_subsets)))
    else:
        for index, (case, expected) in enumerate(zip(forward, expected_subsets)):
            if case["input_tokens"] != expected:
                errors.append("forward[%d] input is %r, the enumeration says %r"
                              % (index, case["input_tokens"], expected))
                break

    # Reversed cases are the same subsets with selection order reversed, sizes
    # 0 and 1 omitted because reversing them would duplicate a forward case.
    expected_reversed = [list(reversed(s)) for s in expected_subsets if len(s) > 1]
    reversed_cases = oracle["reversed"]
    if len(reversed_cases) != len(expected_reversed):
        errors.append("reversed has %d cases; the rule (same subsets, size > 1, "
                      "order reversed) yields %d"
                      % (len(reversed_cases), len(expected_reversed)))
    else:
        for index, (case, expected) in enumerate(zip(reversed_cases, expected_reversed)):
            if case["input_tokens"] != expected:
                errors.append("reversed[%d] input is %r, the rule says %r"
                              % (index, case["input_tokens"], expected))
                break

    if metadata.get("forward_cases") != len(forward):
        errors.append("declared forward_cases %r does not match the %d present"
                      % (metadata.get("forward_cases"), len(forward)))
    if metadata.get("reversed_cases") != len(reversed_cases):
        errors.append("declared reversed_cases %r does not match the %d present"
                      % (metadata.get("reversed_cases"), len(reversed_cases)))

    # --- shape, vocabulary and limits ---------------------------------------
    roles_seen, over_limit, unknown_tokens = set(), 0, set()
    driving_set = set(driving)
    for direction in ("forward", "reversed"):
        for case in oracle[direction]:
            extra = set(case) - CASE_FIELDS
            if extra:
                errors.append("%s case %r carries unexpected fields %s"
                              % (direction, case.get("input_tokens"), sorted(extra)))
                break
            unknown_tokens |= set(case["input_tokens"]) - driving_set
            if len(case["questions"]) > MAX_FOLLOWUP_QUESTIONS:
                over_limit += 1
            for question in case["questions"]:
                extra = set(question) - QUESTION_FIELDS
                if extra:
                    errors.append("a %s question carries unexpected fields %s"
                                  % (direction, sorted(extra)))
                    break
                roles_seen.add(question["role"])
                if question["role"] == "red_flag_clarifier":
                    if not question["red_flag_token"]:
                        errors.append("a clarifier carries no red_flag_token")
                        break
                elif question["red_flag_token"] is not None:
                    errors.append("a %s question carries a red_flag_token"
                                  % question["role"])
                    break

    if unknown_tokens:
        errors.append("cases reference tokens outside driving_tokens: %s"
                      % sorted(unknown_tokens))
    if over_limit:
        errors.append("%d captured cases exceed the live limit of %d questions"
                      % (over_limit, MAX_FOLLOWUP_QUESTIONS))
    unknown_roles = roles_seen - set(ROLE_ORDER)
    if unknown_roles:
        errors.append("captured roles outside the contract: %s" % sorted(unknown_roles))

    # --- no demographic or identifying state --------------------------------
    def scan(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.lower() in FORBIDDEN_FIELDS:
                    errors.append("%s.%s: the fixture records state "
                                  "generateQuestions does not read" % (path, key))
                scan(value, "%s.%s" % (path, key))
        elif isinstance(node, list):
            for item in node:
                scan(item, path)

    scan(oracle["forward"], "forward")
    scan(oracle["reversed"], "reversed")
    scan(oracle["_metadata"], "_metadata")

    return errors, sorted(roles_seen)


def build_record(oracle, errors, roles):
    payload = open(ORACLE_PATH, "rb").read()
    return {
        "_metadata": {
            "record_id": "live_question_oracle_provenance",
            "version": "1",
            "generator": GENERATOR,
            "description": (
                "Immutable provenance record for the captured live-oracle fixture. "
                "A SIDECAR: this tool never writes to the fixture, because editing "
                "captured evidence to describe itself would defeat the point of "
                "capturing it."
            ),
        },
        "fixture": {
            "path": "testing/questions/fixtures/oracle/live_question_oracle_v1.json",
            "sha256": sha256_bytes(payload),
            "bytes": len(payload),
            "forward_cases": len(oracle["forward"]),
            "reversed_cases": len(oracle["reversed"]),
            "total_cases": len(oracle["forward"]) + len(oracle["reversed"]),
        },
        "capture": {
            "evidence_class": "CAPTURED_DART",
            "source_repository": MOBILE_REPO,
            "source_commit": MOBILE_COMMIT,
            "source_symbol": SOURCE_SYMBOL,
            "harness": {
                "path": "testing/questions/fixtures/oracle/live_question_oracle_v1.harness.dart.txt",
                "sha256": sha256_file(HARNESS_PATH),
                "bytes": os.path.getsize(HARNESS_PATH),
                "status": "reproduction_harness_recorded_in_knowledge_base",
                "honest_limitation": (
                    "The capture used a TEMPORARY test placed in a wellapath-mobile "
                    "checkout and deleted afterwards. That test is committed nowhere. "
                    "The recorded harness performs the same capture and is NOT claimed "
                    "to be byte-identical to it. The fixture's authenticity therefore "
                    "rests on the two independent verifications below, not on this file."
                ),
            },
            "command": (
                "git -C wellapath-mobile checkout 657739cc1745104dd1194a57ef14cc9793c9b98e && "
                "cp <harness> test/question_flow/tmp_oracle_export_test.dart && "
                "flutter test test/question_flow/tmp_oracle_export_test.dart && "
                "rm test/question_flow/tmp_oracle_export_test.dart"
            ),
            "observed_output": "EXPORTED cases=2325 reversed=2300 tokens=24",
            "mobile_repository_effect": (
                "None. The capture imports the production QuestionEngine and calls it; "
                "it changes no source, asset or artifact, and the temporary test was "
                "removed. wellapath-mobile is unmodified by this step."
            ),
        },
        "structure": {
            "driving_tokens": oracle["_metadata"]["driving_tokens"],
            "driving_token_count": len(oracle["_metadata"]["driving_tokens"]),
            "max_tokens_per_combination": oracle["_metadata"]["max_tokens_per_combination"],
            "forward_input_ordering": (
                "Every subset of size 0..3 over the sorted driving tokens, in ascending "
                "index order: empty, singletons, pairs, triples. 1+24+276+2024 = 2325."
            ),
            "reversed_input_ordering": (
                "The same subsets with selection order reversed, sizes 0 and 1 omitted "
                "because reversing them duplicates a forward case. 2325-25 = 2300."
            ),
            "captured_output_fields": sorted(QUESTION_FIELDS),
            "captured_case_fields": sorted(CASE_FIELDS),
            "roles_observed": roles,
            "demographics_captured": "none",
            "demographics_rationale": (
                "generateQuestions takes only the selected symptom token list. Sex, age, "
                "pregnancy, medical conditions and body area are not read by it, so none "
                "is recorded. The fixture therefore contains no PHI — only question "
                "definitions and token identifiers already published in "
                "token_dictionary 1.1."
            ),
        },
        "verification": {
            "structural_checks_passed": not errors,
            "structural_errors": errors,
            "structural_basis": (
                "The enumeration, input ordering, reversed-case rule, field sets, role "
                "vocabulary and question limit are RE-DERIVED here and compared against "
                "the fixture; they are not read from the fixture's own metadata."
            ),
            "independent_corroboration": (
                "reports/question_grouping_coverage_v1_1.json stage 1 reproduces all "
                "4,625 cases from a separately written transcription of "
                "question_engine.dart with 0 mismatches."
            ),
        },
        "immutability": (
            "This fixture is frozen. Any change to its bytes changes the sha256 recorded "
            "here and fails tools/run_w3_grouping_checks.py. It may be replaced only by a "
            "fresh capture at a NEW Mobile commit, recorded as a new fixture version."
        ),
        "evidence_class_warning": (
            "Only these 4,625 cases are captured Dart output. The size 4-5 results in "
            "reports/question_grouping_coverage_v1_1.json are MODEL-DERIVED and must "
            "never be described as captured Mobile evidence."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    oracle = load_json(ORACLE_PATH)
    errors, roles = check(oracle)
    record = build_record(oracle, errors, roles)
    payload = dump_artifact_bytes(record)

    if errors:
        print("FAIL oracle provenance verification:")
        for error in errors:
            print("  - %s" % error)
        return 1

    if args.check:
        if not os.path.exists(RECORD_PATH) or open(RECORD_PATH, "rb").read() != payload:
            print("FAIL oracle provenance record is missing or stale")
            return 1
        print("OK   oracle provenance verified and pinned, fixture sha256:%s"
              % record["fixture"]["sha256"])
        return 0

    write_bytes(RECORD_PATH, payload)
    print("wrote testing/questions/fixtures/oracle/live_question_oracle_v1.provenance.json")
    print("  fixture sha256: %s" % record["fixture"]["sha256"])
    print("  fixture bytes:  %d" % record["fixture"]["bytes"])
    print("  cases:          %d forward + %d reversed = %d"
          % (record["fixture"]["forward_cases"], record["fixture"]["reversed_cases"],
             record["fixture"]["total_cases"]))
    print("  enumeration, ordering, fields, roles, limits: re-derived and matched")
    print("  demographics captured: none (generateQuestions reads none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
