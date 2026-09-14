#!/usr/bin/env python3
"""Run every GRID3-lineage facilities check. One command, for CI and for review.

    python3 tools/run_facilities_grid3_checks.py

Exit code 0 means all of the following hold:

  * the GRID3 source bytes are the pinned bytes, and the licence evidence,
    vendored legal code and attribution notice all agree with them;
  * the candidate, manifest, proposal and every report are byte-reproducible
    from the generator — nothing was hand-edited;
  * the candidate satisfies its schema, invents nothing, carries zero NHFR
    markers, and every record re-derives from the GRID3 CSV alone;
  * publication is blocked everywhere it is stated, and facilities 1.0/1.1 are
    byte-identical to their pins.

Standard library only, no arguments, no network.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    ("candidate, manifest, proposal and reports are reproducible",
     ["tools/build_facilities_grid3_candidate.py", "--check"]),
    ("candidate passes source, isolation, honesty and governance validation",
     ["tools/validate_facilities_grid3_candidate.py"]),
    ("GRID3 facilities test suite",
     ["testing/facilities_grid3/test_facilities_grid3.py"]),
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
    print("all %d GRID3 facilities checks passed" % len(STEPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
