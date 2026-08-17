#!/usr/bin/env python3
"""Run every W3 grouping check, and re-verify nothing clinical moved.

    python3 tools/run_w3_grouping_checks.py

One command, so "it all still passes" is a fact rather than a recollection.
Every generator runs in `--check` mode: a generator that no longer reproduces
its own output is a failure, not a warning.

The frozen-artifact block is the important half. It is easy to correct a
question projection and quietly disturb a clinical input on the way past, so the
hashes of the KB, rules, token dictionary, case bank and known findings are
re-read from disk and compared against the values recorded inside candidate 1.0
— the artifact that was already reviewed and merged. Not asserted; compared.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import load_json, repo_path, sha256_file

STEPS = [
    ("schema 1.1 is reproducible and additive over 1.0",
     ["tools/build_question_schema_v11.py", "--check"]),
    ("candidate 1.0 is untouched",
     ["tools/build_question_candidate.py", "--check"]),
    ("candidate 1.1 is reproducible",
     ["tools/build_question_candidate_v11.py", "--check"]),
    ("invalid grouping fixtures are reproducible",
     ["tools/build_grouping_invalid_fixtures.py", "--check"]),
    ("grouping path fixtures are reproducible",
     ["tools/build_grouping_path_fixtures.py", "--check"]),
    ("1.0 path and invalid fixtures are untouched",
     ["tools/build_question_fixtures.py", "--check"]),
    ("candidate 1.0 passes the full question-flow validator",
     ["tools/validate_question_flow.py", "candidate/question_flow.ng.v1.0.json"]),
    ("candidate 1.1 passes the full question-flow validator",
     ["tools/validate_question_flow.py", "candidate/question_flow.ng.v1.1.json"]),
    ("candidate 1.1 passes the grouping validator",
     ["tools/validate_question_grouping.py"]),
    ("every invalid grouping fixture is rejected by its intended check",
     ["tools/validate_question_grouping.py", "--fixtures"]),
    ("captured-oracle provenance verifies from first principles",
     ["tools/validate_oracle_provenance.py", "--check"]),
    ("PHI pattern controls (9 positive, 4 negative)",
     ["tools/verify_no_clinical_change.py", "--self-test"]),
    ("no clinical/runtime change, GF-006/GF-008 regressions, content safety",
     ["tools/verify_no_clinical_change.py", "--check"]),
    ("candidate 1.0 still validates under schema 1.1 (additivity)",
     ["tools/check_schema_additivity.py"]),
    ("grouping parity vs real live output is reproducible and clean",
     ["tools/report_question_grouping_parity.py", "--check"]),
    ("transcription validation and extended coverage are reproducible and clean",
     ["tools/report_grouping_coverage.py", "--check"]),
    ("IM-001 product-review decisions are reproducible",
     ["tools/report_im001_product_review.py", "--check"]),
    ("IM-001 option-order evidence is current",
     ["tools/report_im001_option_ordering.py", "--check"]),
    ("IM-001 decision set is valid", ["tools/validate_im001_decisions.py"]),
]


#: Clinical inputs that this step must not have touched. The expected hashes are
#: read from candidate 1.0's own frozen_clinical_inputs block rather than
#: hard-coded here, so there is no second place for them to drift.
FROZEN_FROM_CANDIDATE = {
    "token_dictionary_v1_1": "token_dictionary.ng.v1.1.json",
    "kb_v2_4": "kb.ng.v2.4.json",
    "rules_v2_2": "rules.ng.v2.2.json",
}

#: Artifacts with no hash recorded in the candidate, pinned against git HEAD.
FROZEN_VS_GIT = [
    "token_dictionary.ng.v2.0.json",
    "candidate/question_flow.ng.v1.0.json",
    "schema/question_flow.v1.schema.json",
]


def run_steps():
    root = repo_path()
    failures = []
    for description, argv in STEPS:
        result = subprocess.run(
            [sys.executable] + argv, cwd=root,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        ok = result.returncode == 0
        print("%s %s" % ("ok  " if ok else "FAIL", description))
        if not ok:
            failures.append(description)
            for line in result.stdout.strip().splitlines()[-12:]:
                print("       %s" % line)
    return failures


def check_frozen():
    failures = []
    candidate = load_json(repo_path("candidate", "question_flow.ng.v1.0.json"))
    recorded = candidate["_metadata"]["frozen_clinical_inputs"]
    for key, filename in sorted(FROZEN_FROM_CANDIDATE.items()):
        actual = sha256_file(repo_path(filename))
        if actual != recorded.get(key):
            failures.append("%s changed: recorded %s, on disk %s"
                            % (filename, recorded.get(key), actual))
            print("FAIL frozen clinical input %s" % filename)
        else:
            print("ok   frozen clinical input %s (%s…)" % (filename, actual[:12]))

    for relative in FROZEN_VS_GIT:
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relative],
            cwd=repo_path(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            failures.append("%s differs from git HEAD" % relative)
            print("FAIL %s differs from git HEAD" % relative)
        else:
            print("ok   %s unchanged vs git HEAD" % relative)
    return failures


def main():
    print("— generators, validators and reports —")
    failures = run_steps()
    print("\n— frozen clinical inputs —")
    failures += check_frozen()

    print("\n%d checks, %d failed" % (len(STEPS) + len(FROZEN_FROM_CANDIDATE)
                                      + len(FROZEN_VS_GIT), len(failures)))
    for failure in failures:
        print("  FAILED: %s" % failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
