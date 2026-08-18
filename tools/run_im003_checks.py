#!/usr/bin/env python3
"""Run every IM-003 check, and re-verify nothing clinical or runtime moved.

    python3 tools/run_im003_checks.py

One command, so "it all still passes" is a fact rather than a recollection.
Every generator runs in `--check` mode: a generator that no longer reproduces
its own output is a failure, not a warning.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import load_json, repo_path, sha256_file

STEPS = [
    ("IM-003 impact analysis is reproducible",
     ["tools/report_im003_impact.py", "--check"]),
    ("IM-003 decision package is reproducible",
     ["tools/build_im003_decision_package.py", "--check"]),
    ("IM-003 fail-closed guards pass", ["tools/validate_im003.py"]),
    ("every IM-003 invalid fixture is rejected by its intended check",
     ["tools/validate_im003.py", "--fixtures"]),
    ("W3 grouping suite still passes", ["tools/run_w3_grouping_checks.py"]),
    ("W2 suite still passes", ["tools/run_w2_checks.py"]),
    ("Mobile measurement reconciliation is current",
     ["tools/report_im003_mobile_measurement.py", "--check"]),
    ("IM-003 safety blockers are valid", ["tools/validate_im003_blockers.py"]),
    ("blocker validators bite (mutation proofs)",
     ["tools/validate_im003_blockers.py", "--mutations"]),
]


#: Everything this step must NOT have touched.
FROZEN = [
    "kb.ng.v2.4.json",
    "rules.ng.v2.2.json",
    "token_dictionary.ng.v1.1.json",
    "candidate/token_dictionary.ng.v2.0.json",
    "candidate/question_flow.ng.v1.0.json",
    "candidate/question_flow.ng.v1.1.json",
    "schema/question_flow.v1.schema.json",
    "schema/question_flow.v1_1.schema.json",
    "reports/im001_option_order_evidence_v1.json",
    "reports/im001_option_order_decision_v1.json",
    "reports/im001_product_review_v1_1.json",
    "testing/case_bank_v1.json",
    "testing/known_findings.json",
]

#: New artifacts this step adds, scanned for PHI-shaped content.
SCANNED = [
    "reports/im003_impact_analysis_v1.json",
    "reports/im003_decision_package_v1.json",
]

PHI_PATTERNS = [
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone number", re.compile(
        r"(?<![\dA-Fa-f])(?:\+\d{1,3}[ .-]?)?"
        r"(?:\(\d{2,4}\)[ .-]?|\d{2,4}[ .-])(?:\d[ .-]?){5,11}\d(?![\dA-Fa-f])")),
    ("date of birth", re.compile(
        r"(?:\bdate[_ ]of[_ ]birth\b|[\"']dob[\"']\s*[:=])", re.I)),
    ("patient identifier", re.compile(r"\b(?:patient_id|mrn)\b", re.I)),
    ("device or session id", re.compile(r"\b(?:device_id|session_id|imei)\b", re.I)),
]

#: Positive controls. Every one must be caught, or the scan is decorative.
PHI_CONTROLS = [
    ("email address", "reach ada@example.org"),
    ("phone number", "+234 803 123 4567"),
    ("date of birth", '{"dob": "1990-04-02"}'),
    ("patient identifier", '{"patient_id": 1}'),
    ("device or session id", '{"device_id": "x"}'),
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
            for line in result.stdout.strip().splitlines()[-10:]:
                print("       %s" % line)
    return failures


def check_frozen():
    """Nothing clinical or contractual may differ from git HEAD."""
    failures = []
    for relative in FROZEN:
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", relative],
            cwd=repo_path(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            failures.append("%s differs from git HEAD" % relative)
            print("FAIL %s" % relative)
        else:
            print("ok   %s (%s…)" % (relative, sha256_file(repo_path(relative))[:12]))
    return failures


def check_im003_still_deferred():
    """The candidate's own IM-003 record must remain deferred and blocking."""
    failures = []
    candidate = load_json(repo_path("candidate", "question_flow.ng.v1.1.json"))
    record = next(
        (m for m in candidate["_metadata"]["impedance_mismatches"]
         if m["id"] == "IM-003"), None)
    if record is None:
        failures.append("IM-003 is no longer disclosed in candidate 1.1")
    else:
        if "deferred" not in record["status"]:
            failures.append("IM-003 status is %r, not deferred" % record["status"])
            print("FAIL IM-003 status")
        elif not record["activation_blocker"]:
            failures.append("IM-003 is no longer an activation blocker")
            print("FAIL IM-003 activation_blocker")
        else:
            print("ok   IM-003 remains %s, activation blocker" % record["status"])
    for question in candidate["questions"]:
        if question.get("branch_conditions"):
            failures.append("%s declares branch_conditions — IM-003 data is "
                            "appearing in the candidate" % question["question_id"])
    if not failures:
        print("ok   no question declares branch_conditions")
    return failures


def check_content_safety():
    failures = []
    for label, sample in PHI_CONTROLS:
        caught = [name for name, pattern in PHI_PATTERNS if pattern.search(sample)]
        if label not in caught:
            failures.append("PHI control MISSED %s in %r" % (label, sample))
    hits = []
    for relative in SCANNED:
        text = open(repo_path(relative), encoding="utf-8").read()
        for label, pattern in PHI_PATTERNS:
            for match in pattern.finditer(text):
                hits.append("%s: %s -> %s" % (relative, label, match.group(0)[:60]))
    if hits:
        failures.extend(hits)
        print("FAIL content safety: %d hit(s)" % len(hits))
        for hit in hits[:5]:
            print("       %s" % hit)
    else:
        print("ok   content safety: %d files, 0 hits, %d/%d controls caught"
              % (len(SCANNED), len(PHI_CONTROLS), len(PHI_CONTROLS)))
    return failures


def main():
    print("— generators, validators and suites —")
    failures = run_steps()
    print("\n— frozen clinical and contract artifacts —")
    failures += check_frozen()
    print("\n— IM-003 remains deferred —")
    failures += check_im003_still_deferred()
    print("\n— content safety —")
    failures += check_content_safety()

    total = len(STEPS) + len(FROZEN) + 2
    print("\n%d check groups, %d failed" % (total, len(failures)))
    for failure in failures:
        print("  FAILED: %s" % failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
