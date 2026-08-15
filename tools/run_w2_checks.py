#!/usr/bin/env python3
"""Run every W2 vocabulary check. One command, for CI and for release review.

    python3 tools/run_w2_checks.py

Exit code 0 means all of the following hold:

  * the frozen artifacts are byte identical to the E9.1 baseline;
  * every committed report, fixture and generated artifact is reproducible
    from its generator (nothing was hand-edited);
  * the candidate conforms to schema 2.0 and passes all 45 validators;
  * every kb 2.4, rules 2.2 and question-flow token reference resolves;
  * the diff against the baseline contains no change class requiring clinical
    review;
  * the candidate is still unpublished and makes no approval claim;
  * the full test suite passes.

Standard library only, no arguments, no network.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    ("baseline freeze report is current", ["tools/report_baseline.py", "--check"]),
    ("token reference graph is current", ["tools/report_token_references.py", "--check"]),
    ("case bank status report is current", ["tools/report_case_bank_status.py", "--check"]),
    ("candidate artifact is reproducible", ["tools/build_vocabulary_v2.py", "--check"]),
    ("candidate manifest is current", ["tools/build_candidate_manifest.py", "--check"]),
    ("search fixtures are current", ["tools/build_search_fixtures.py", "--check"]),
    ("invalid fixtures are current", ["tools/build_invalid_fixtures.py", "--check"]),
    ("migration and diff reports are current", ["tools/classify_vocabulary_diff.py", "--check"]),
    ("candidate passes schema and content validation", ["tools/validate_vocabulary.py"]),
    ("frozen consumers remain compatible", ["tools/check_compatibility.py"]),
    ("test suite", ["testing/vocabulary/test_vocabulary_v2.py"]),
]


def main():
    failures = []
    width = max(len(label) for label, _ in STEPS)

    for label, argv in STEPS:
        completed = subprocess.run(
            [sys.executable, "-W", "ignore::ResourceWarning"] + argv,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        ok = completed.returncode == 0
        print("%-4s %s" % ("OK" if ok else "FAIL", label.ljust(width)))
        if not ok:
            failures.append((label, completed.stdout.decode("utf-8", "replace")))

    print("")
    if failures:
        for label, output in failures:
            print("=" * 72)
            print("FAILED: %s" % label)
            print("=" * 72)
            print(output)
        print("%d of %d checks FAILED" % (len(failures), len(STEPS)))
        return 1

    print("all %d W2 checks passed" % len(STEPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
