#!/usr/bin/env python3
"""Prove the candidate vocabulary changes nothing for the frozen consumers.

    python3 tools/check_compatibility.py           # human-readable
    python3 tools/check_compatibility.py --json    # machine-readable
    python3 tools/check_compatibility.py --write   # also write reports/*.json

What this can and cannot prove, stated plainly:

  CAN prove, here, from artifact bytes:
    * every token ID kb 2.4 and rules 2.2 reference still resolves;
    * every red-flag and question-relevant reference still resolves;
    * kb 2.4, rules 2.2, facilities 1.1 and token_dictionary 1.1 are byte
      identical to the frozen baseline — no weight, rule or trigger moved,
      because no byte moved;
    * the exact key surface the shipped mobile engine reads from the token
      dictionary is unchanged.

  CANNOT prove here:
    * clinical output equivalence over the Top-50 case bank. Scoring runs
      on-device in Dart; this repository contains no engine and must not grow a
      second one, because a divergent reimplementation could certify a pass the
      real engine would fail. That regression runs in the mobile repository —
      see reports/case_bank_status_v1.json.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

CANDIDATE = repo_path("candidate", "token_dictionary.ng.v2.0.json")

# The E9.1 freeze, with the hashes recorded in progress.md, in the backend's
# docs/SECURITY_CHECKLIST.md and served by GET /config. Hard-coded so this check
# detects drift rather than re-deriving whatever happens to be on disk.
FROZEN_HASHES = {
    "token_dictionary.ng.v1.1.json": "0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019",
    "kb.ng.v2.4.json": "6c00d8257f8417e86bd5e237630bf8a4623ad72e2e46b1b071dd447c067cec2b",
    "rules.ng.v2.2.json": "1d27e854cba95b179577a88f92445400f494a7fe8e6a53a60fcaa98b3870d1c4",
    "facilities.ng.v1.1.json": "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398",
    "testing/case_bank_v1.json": "c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834",
}

# Measured from lib/core/engine/red_flag_evaluator.dart on the mobile `develop`
# branch: the shipped engine reads exactly these two keys of the token
# dictionary and nothing else.
MOBILE_TOKEN_DICTIONARY_SURFACE = ["symptom_tokens", "red_flag_tokens"]

CATEGORIES = [
    "symptom_tokens",
    "red_flag_tokens",
    "duration_tokens",
    "body_area_tokens",
    "demographic_tokens",
    "severity_tokens",
]

# Recorded in reports/baseline_freeze_v1.json — pre-existing, not W2's doing.
KNOWN_UNRESOLVED = {"pneumonia", "severe_pneumonia", "very_severe_disease"}


class Checks(object):
    def __init__(self):
        self.items = []

    def add(self, name, passed, detail=""):
        self.items.append({"check": name, "passed": bool(passed), "detail": detail})

    def summary(self):
        failed = [c for c in self.items if not c["passed"]]
        return {
            "total": len(self.items),
            "passed": len(self.items) - len(failed),
            "failed": len(failed),
            "all_passed": not failed,
        }


def candidate_token_ids(candidate):
    return {entry["token_id"] for entry in candidate["tokens"]}


def kb_references(kb):
    """Every token reference kb 2.4 makes, grouped by role."""
    refs = {
        "kb.symptoms": set(),
        "kb.red_flags": set(),
        "kb.severity_levels.value": set(),
        "kb.severity_levels.key": set(),
        "kb.demographic_modifiers": set(),
    }
    for condition in kb["conditions"]:
        for symptom in condition["symptoms"]:
            refs["kb.symptoms"].add(symptom["token"])
        for flag in condition["red_flags"]:
            refs["kb.red_flags"].add(flag)
        for tier, tokens in (condition.get("severity_levels") or {}).items():
            refs["kb.severity_levels.key"].add(tier)
            refs["kb.severity_levels.value"].update(tokens)
        for modifier in condition.get("demographic_modifiers", []):
            refs["kb.demographic_modifiers"].add(modifier["modifier"])
    return refs


def rules_references(rules):
    refs = {"rules.global": set(), "rules.condition_specific": set()}
    for rule in rules["rules"]:
        key = "rules.global" if rule["applies_to"] == ["all"] else "rules.condition_specific"
        refs[key].add(rule["token"])
    return refs


def question_references(case_bank):
    """Tokens the question/input flow actually feeds the engine.

    This repository owns no question definitions — the question flow lives in
    the mobile repository (lib/features/assessment). The closest artifact this
    repository does own is the case bank, whose `input_tokens` and
    `demographic_tokens` are exactly the token vocabulary an assessment submits.
    That is the surface checked here, and it is labelled for what it is rather
    than being presented as a question-definition check.
    """
    refs = {"question_flow.input_tokens": set(), "question_flow.demographic_tokens": set()}
    if case_bank is None:
        return refs
    for case in case_bank["cases"]:
        refs["question_flow.input_tokens"].update(case.get("input_tokens", []))
        refs["question_flow.demographic_tokens"].update(case.get("demographic_tokens", []))
    return refs


def build_report():
    checks = Checks()

    # --- frozen inputs are byte identical -------------------------------------
    byte_identity = {}
    for filename, expected in sorted(FROZEN_HASHES.items()):
        path = repo_path(filename)
        actual = sha256_file(path) if os.path.exists(path) else None
        byte_identity[filename] = {"expected": expected, "actual": actual, "match": actual == expected}
        checks.add(
            "frozen_artifact_byte_identical:%s" % filename,
            actual == expected,
            "expected %s got %s" % (expected, actual),
        )

    candidate = load_json(CANDIDATE)
    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))
    baseline = load_json(repo_path("token_dictionary.ng.v1.1.json"))
    case_bank_path = repo_path("testing", "case_bank_v1.json")
    case_bank = load_json(case_bank_path) if os.path.exists(case_bank_path) else None

    ids = candidate_token_ids(candidate)

    # --- every consumer reference still resolves -------------------------------
    resolution = {}
    all_refs = {}
    all_refs.update(kb_references(kb))
    all_refs.update(rules_references(rules))
    all_refs.update(question_references(case_bank))

    for role, tokens in sorted(all_refs.items()):
        unresolved = sorted(tokens - ids - KNOWN_UNRESOLVED)
        pre_existing = sorted(tokens & KNOWN_UNRESOLVED)
        resolution[role] = {
            "referenced": len(tokens),
            "resolved": len(tokens & ids),
            "unresolved_new": unresolved,
            "unresolved_pre_existing": pre_existing,
        }
        checks.add(
            "all_%s_references_resolve" % role.replace(".", "_"),
            not unresolved,
            "unresolved=%r" % unresolved,
        )

    # --- the candidate resolves exactly what the baseline resolved -------------
    baseline_ids = set()
    for category in CATEGORIES:
        baseline_ids.update(baseline.get(category, []))
    checks.add(
        "candidate_resolves_every_id_the_baseline_resolved",
        baseline_ids <= ids,
        "missing=%r" % sorted(baseline_ids - ids),
    )
    checks.add(
        "candidate_adds_no_new_token_ids",
        ids <= baseline_ids,
        "added=%r" % sorted(ids - baseline_ids),
    )

    # --- old-consumer surface --------------------------------------------------
    legacy_identical = {c: candidate.get(c) == baseline.get(c) for c in CATEGORIES}
    checks.add(
        "legacy_arrays_identical",
        all(legacy_identical.values()),
        "differing=%r" % [c for c, ok in legacy_identical.items() if not ok],
    )
    mobile_identical = {
        key: candidate.get(key) == baseline.get(key) for key in MOBILE_TOKEN_DICTIONARY_SURFACE
    }
    checks.add(
        "mobile_surface_identical",
        all(mobile_identical.values()),
        "the shipped engine reads only %s; both are unchanged"
        % ", ".join(MOBILE_TOKEN_DICTIONARY_SURFACE),
    )
    # The valid-input set the mobile red-flag evaluator builds from the two keys.
    baseline_valid = set(baseline["symptom_tokens"]) | set(baseline["red_flag_tokens"])
    candidate_valid = set(candidate["symptom_tokens"]) | set(candidate["red_flag_tokens"])
    checks.add(
        "mobile_valid_input_token_set_unchanged",
        baseline_valid == candidate_valid,
        "size %d -> %d" % (len(baseline_valid), len(candidate_valid)),
    )

    # --- nothing clinical moved ------------------------------------------------
    checks.add(
        "no_scoring_weight_changed",
        byte_identity["kb.ng.v2.4.json"]["match"],
        "kb.ng.v2.4.json is byte identical, so every symptoms[].weight and base_weight is unchanged",
    )
    checks.add(
        "no_red_flag_trigger_changed",
        byte_identity["rules.ng.v2.2.json"]["match"] and byte_identity["kb.ng.v2.4.json"]["match"],
        "rules.ng.v2.2.json and kb.ng.v2.4.json are byte identical, so every rule token, priority, override_urgency, applies_to scope and condition red_flags list is unchanged",
    )
    checks.add(
        "no_condition_ranking_changed_by_this_migration",
        byte_identity["kb.ng.v2.4.json"]["match"] and baseline_valid == candidate_valid,
        "ranking is a function of kb weights and the accepted input token set; both are unchanged",
    )
    checks.add(
        "no_question_behaviour_changed",
        baseline_valid == candidate_valid,
        "the question flow submits tokens from the same accepted set; this repository defines no question content",
    )

    # --- publication safety ----------------------------------------------------
    metadata = candidate["_metadata"]
    checks.add(
        "candidate_is_not_marked_published",
        metadata.get("release_status") != "published",
        "release_status=%r" % metadata.get("release_status"),
    )
    checks.add(
        "candidate_makes_no_clinical_approval_claim",
        metadata.get("clinical_review", {}).get("status") == "not_reviewed",
        json.dumps(metadata.get("clinical_review")),
    )
    checks.add(
        "candidate_is_not_at_the_published_artifact_location",
        not os.path.exists(repo_path("token_dictionary.ng.v2.0.json")),
        "repository root must not contain token_dictionary.ng.v2.0.json while the candidate is unapproved",
    )

    return {
        "report_id": "compatibility_check",
        "report_version": "1",
        "phase": "I2 / W2 Step 1",
        "generator": "tools/check_compatibility.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "candidate": {
            "file": "candidate/token_dictionary.ng.v2.0.json",
            "version": metadata.get("version"),
            "schema_version": metadata.get("schema_version"),
            "sha256": sha256_file(CANDIDATE),
            "release_status": metadata.get("release_status"),
        },
        "frozen_artifact_byte_identity": byte_identity,
        "consumer_reference_resolution": resolution,
        "old_consumer_compatibility": {
            "legacy_arrays_identical": legacy_identical,
            "mobile_read_surface": MOBILE_TOKEN_DICTIONARY_SURFACE,
            "mobile_surface_identical": mobile_identical,
            "mobile_valid_input_token_count": len(candidate_valid),
            "conclusion": (
                "The shipped mobile build can load the candidate with no code change. It decodes "
                "the artifact into a map and reads symptom_tokens and red_flag_tokens only; both "
                "are byte identical to 1.1, and every key schema 2.0 adds is simply never read."
            ),
        },
        "clinical_regression": {
            "executed_here": False,
            "reason": (
                "Scoring executes on-device in Dart. This repository holds no engine and must not "
                "grow a second implementation — a divergent reimplementation could certify a pass "
                "the real engine would fail."
            ),
            "where_it_runs": "wellapath-mobile test/engine/case_bank_validation_test.dart",
            "status": "see reports/case_bank_status_v1.json",
        },
        "summary": checks.summary(),
        "checks": checks.items,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true", help="write reports/compatibility_v1.json")
    args = parser.parse_args()

    report = build_report()

    if args.write:
        write_bytes(repo_path("reports", "compatibility_v1.json"), dump_report_bytes(report))
        print("wrote reports/compatibility_v1.json")

    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.write:
        for check in report["checks"]:
            print(
                "%-4s %s%s"
                % (
                    "OK" if check["passed"] else "FAIL",
                    check["check"],
                    "" if check["passed"] else "  [%s]" % check["detail"],
                )
            )
        summary = report["summary"]
        print("\n%d checks, %d passed, %d failed" % (summary["total"], summary["passed"], summary["failed"]))

    return 0 if report["summary"]["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
