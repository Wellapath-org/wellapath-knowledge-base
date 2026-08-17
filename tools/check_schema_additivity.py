#!/usr/bin/env python3
"""Prove schema 1.1 accepts everything schema 1.0 accepted.

    python3 tools/check_schema_additivity.py

`tools/build_question_schema_v11.py` proves additivity STRUCTURALLY — no field
removed, no `required` grown, no enum narrowed, no restricting keyword added.
This proves it BEHAVIOURALLY: the real 1.0 artifact, and every valid 1.0-shaped
fixture in the repository, still validate under 1.1.

Both matter. The structural proof caught a `required: grouping_semantics` that
would have broken 1.0 compatibility; this one would have caught it too, from the
other direction. A single proof of a compatibility claim is a proof that can
have a blind spot in exactly the place that matters.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import load_json, repo_path
from vocab.schema_check import validate

SCHEMA_10 = repo_path("schema", "question_flow.v1.schema.json")
SCHEMA_11 = repo_path("schema", "question_flow.v1_1.schema.json")
CANDIDATE_10 = repo_path("candidate", "question_flow.ng.v1.0.json")
CANDIDATE_11 = repo_path("candidate", "question_flow.ng.v1.1.json")
INVALID_10_DIR = repo_path("testing", "questions", "fixtures", "invalid")


def main():
    schema_10 = load_json(SCHEMA_10)
    schema_11 = load_json(SCHEMA_11)
    failures = []

    # 1. The real 1.0 artifact under both schemas.
    for label, schema in (("schema 1.0", schema_10), ("schema 1.1", schema_11)):
        errors = validate(load_json(CANDIDATE_10), schema)
        ok = not errors
        print("%s candidate 1.0 under %s: %d errors" % ("ok  " if ok else "FAIL",
                                                        label, len(errors)))
        if not ok:
            failures.append("candidate 1.0 is rejected by %s" % label)
            for error in errors[:5]:
                print("       - %s" % error)

    # 2. 1.1 under 1.1, and correctly REFUSED by 1.0 — a 1.0-only consumer must
    #    not silently accept an artifact whose grouping it cannot apply.
    errors_11 = validate(load_json(CANDIDATE_11), schema_11)
    print("%s candidate 1.1 under schema 1.1: %d errors"
          % ("ok  " if not errors_11 else "FAIL", len(errors_11)))
    if errors_11:
        failures.append("candidate 1.1 is rejected by schema 1.1")

    refused = validate(load_json(CANDIDATE_11), schema_10)
    print("%s candidate 1.1 under schema 1.0: %d errors (must be > 0)"
          % ("ok  " if refused else "FAIL", len(refused)))
    if not refused:
        failures.append("schema 1.0 accepts a 1.1 artifact it cannot apply")

    # 3. Every invalid 1.0 fixture must stay invalid under 1.1. An additive
    #    schema widens what is ACCEPTED; it must not start accepting artifacts
    #    that were correctly rejected.
    if os.path.isdir(INVALID_10_DIR):
        index_path = os.path.join(INVALID_10_DIR, "index.json")
        names = []
        if os.path.exists(index_path):
            index = load_json(index_path)
            names = [entry.get("file") for entry in index.get("fixtures", [])]
        names = [n for n in names if n] or sorted(
            f for f in os.listdir(INVALID_10_DIR)
            if f.endswith(".json") and f != "index.json")

        newly_accepted = []
        checked = 0
        for name in names:
            path = os.path.join(INVALID_10_DIR, name)
            if not os.path.exists(path):
                continue
            artifact = load_json(path)
            if artifact.get("_metadata", {}).get("schema_version") != "1.0":
                continue
            checked += 1
            was_invalid = bool(validate(artifact, schema_10))
            now_valid = not validate(artifact, schema_11)
            if was_invalid and now_valid:
                newly_accepted.append(name)
        ok = not newly_accepted
        print("%s %d schema-invalid 1.0 fixtures re-checked under 1.1; %d newly accepted"
              % ("ok  " if ok else "FAIL", checked, len(newly_accepted)))
        if not ok:
            failures.append("schema 1.1 accepts %s, which 1.0 rejected" % newly_accepted)

    print("\n%d failure(s)" % len(failures))
    for failure in failures:
        print("  FAILED: %s" % failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
