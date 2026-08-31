#!/usr/bin/env python3
"""Run every nationwide-facilities check. One command, for CI and for review.

    python3 tools/run_facilities_checks.py

Exit code 0 means all of the following hold:

  * the source bytes are the pinned bytes;
  * the candidate, quality report and quarantine report are all reproducible from the
    generator — nothing was hand-edited;
  * the candidate satisfies schema 2.0, invents no value the source does not evidence, and
    carries no contact detail into any record;
  * every source row is either emitted or quarantined with a reason code;
  * the comparison and Mobile-compatibility reports are current;
  * facilities 1.0 and 1.1 are byte identical.

Standard library only, no arguments, no network.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    ("candidate and reports are reproducible",
     ["tools/build_facilities_candidate.py", "--check"]),
    ("comparison and Mobile reports are current",
     ["tools/report_facilities_comparison.py", "--check"]),
    ("candidate passes schema, safety and coverage validation",
     ["tools/validate_facilities_candidate.py"]),
    ("facilities test suite", ["testing/facilities/test_facilities.py"]),
]


def main():
    failures = []
    width = max(len(label) for label, _ in STEPS)
    for label, argv in STEPS:
        completed = subprocess.run(
            [sys.executable, "-W", "ignore::ResourceWarning"] + argv,
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        ok = completed.returncode == 0
        print("%-4s %s" % ("OK" if ok else "FAIL", label.ljust(width)))
        if not ok:
            failures.append((label, completed.stdout.decode("utf-8", "replace")))

    print("")
    if failures:
        for label, output in failures:
            print("=" * 72); print("FAILED: %s" % label); print("=" * 72); print(output)
        print("%d of %d checks FAILED" % (len(failures), len(STEPS)))
        return 1
    print("all %d facilities checks passed" % len(STEPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
