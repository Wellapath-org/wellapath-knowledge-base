#!/usr/bin/env python3
"""Run every I3 Step 2 publication check. One command, for CI and for release review.

    python3 tools/run_publication_checks.py

Exit code 0 means all of the following hold:

  * the pinned Backend contract is present, unchanged and fail-closed, and the Python mirror
    still agrees with the vendored schema;
  * every frozen clinical artifact, candidate, schema, oracle, case-bank file, known-findings
    registry, IM-001 record and IM-003 record is byte identical;
  * every generated file in this step is reproducible from its generator — the governance
    register, both dry-run plans, all four fixture sets, the receipt examples and the freeze
    report;
  * both dry-run plans satisfy the plan schema, validate against contract 1.1.0 by two
    independent routes that agree, carry real digests recomputed from real bytes, and carry no
    credential of any kind;
  * all 99 negative fixtures fail at their declared stage with their declared reason code;
  * all 7 mutation proofs bite;
  * the unit suite passes, including the guards that fail if the dry-run path attempts a
    socket, a subprocess or a write outside its staging directory.

The contract pin and the frozen-artifact check run **first**, before anything else. If the
contract has drifted, every later result was computed against the wrong rules; if a clinical
artifact has changed, that is the finding and no other result from the run is worth reading.

Standard library only, no arguments, no network.
"""

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    # Ordered deliberately: contract first, then bytes, then everything that depends on both.
    ("pinned Backend contract is unchanged and fail-closed", ["tools/verify_contract_pin.py"]),
    ("frozen artifacts are byte identical", ["tools/report_publication_freeze.py", "--check"]),
    ("governance register is reproducible", ["tools/build_governance_register.py", "--check"]),
    ("publication fixtures are reproducible", ["tools/build_publication_fixtures.py", "--check"]),
    ("dry-run plans are reproducible", ["tools/build_publication_plans.py", "--check"]),
    ("receipt examples are reproducible", ["tools/build_receipt_examples.py", "--check"]),
    ("dry-run plans are valid and leak nothing", ["tools/validate_publication_plan.py"]),
    ("every negative fixture fails at its declared stage and code",
     ["tools/validate_publication_fixtures.py", "--mutations"]),
    ("publication test suite", ["testing/publication/test_publication.py"]),
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
            print("=" * 78)
            print("FAILED: %s" % label)
            print("=" * 78)
            print(output)
        print("%d of %d checks FAILED" % (len(failures), len(STEPS)))
        return 1

    print("all %d publication checks passed" % len(STEPS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
