#!/usr/bin/env python3
"""Validate the proposed known-findings registry.

    python3 tools/validate_known_findings.py            # human-readable
    python3 tools/validate_known_findings.py --json     # machine-readable

The registry is a record of reality, so the thing worth validating is that it
still describes reality. This checks:

  * the registry names the authoritative fixture, by hash;
  * every registered case actually exists in that fixture;
  * the registry's `expected_output` matches what the fixture really asserts —
    a registry that misquotes the case bank is worse than none;
  * the registry's `observed_output` matches what the evidence model computes,
    so the pinned observation cannot silently drift from the artifacts;
  * no entry claims clinical authority or clinical approval it does not have;
  * no entry is a disguised waiver — every one keeps a real decision open;
  * the runner contract still forbids reporting a registered case as passed.

It deliberately does NOT make CB_211 pass. Nothing here changes a test outcome.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import load_json, repo_path, sha256_file

import report_case_findings

REGISTRY_PATH = repo_path("testing", "known_findings.json")
CASE_BANK_PATH = repo_path("testing", "case_bank_v1.json")

REQUIRED_ENTRY_FIELDS = [
    "case_id", "fixture_version", "fixture_sha256", "classification",
    "classification_authority", "classification_is_clinical_approval",
    "input", "expected_output", "observed_output", "safety_impact",
    "product_reachability", "decision_status", "owner", "resolution_options",
    "evidence_references", "review_trigger",
]

FORBIDDEN_IN_RUNNER_CONTRACT = [
    "report a registered case as `passed`",
    "count a registered case toward the pass total",
    "silently downgrade a failure to a warning",
]


def check(results, name, passed, detail=""):
    results.append({"check": name, "passed": bool(passed), "detail": detail})


def run():
    results = []
    registry = load_json(REGISTRY_PATH)
    bank = load_json(CASE_BANK_PATH)
    cases = {c["case_id"]: c for c in bank["cases"]}

    fixture = registry["authoritative_fixture"]
    actual_hash = sha256_file(CASE_BANK_PATH)
    check(
        results,
        "registry_names_the_authoritative_fixture_hash",
        fixture["sha256"] == actual_hash,
        "registry=%s actual=%s" % (fixture["sha256"], actual_hash),
    )
    check(
        results,
        "registry_fixture_case_count_matches",
        fixture["total_cases"] == len(bank["cases"]),
        "registry=%s actual=%d" % (fixture["total_cases"], len(bank["cases"])),
    )

    # The evidence model recomputes observed behaviour from the artifacts.
    evidence = {f["case_id"]: f for f in report_case_findings.build_report()["findings"]}

    for entry in registry["findings"]:
        case_id = entry["case_id"]
        prefix = "entry[%s]" % case_id

        missing = [f for f in REQUIRED_ENTRY_FIELDS if f not in entry]
        check(results, "%s_has_all_required_fields" % prefix, not missing, "missing=%r" % missing)

        case = cases.get(case_id)
        check(results, "%s_case_exists_in_fixture" % prefix, case is not None, case_id)
        if case is None:
            continue

        check(
            results,
            "%s_fixture_hash_matches_registry_header" % prefix,
            entry["fixture_sha256"] == fixture["sha256"],
            entry["fixture_sha256"],
        )

        # The registry must quote the case bank accurately.
        expected = entry["expected_output"]
        check(
            results,
            "%s_expected_output_matches_the_case_bank" % prefix,
            expected["urgency"] == case["expected_urgency"]
            and expected["urgency_source"] == case["expected_urgency_source"]
            and expected["top_condition"] == case["expected_top_condition"],
            "registry=%r bank=(%r, %r, %r)"
            % (expected, case["expected_urgency"], case["expected_urgency_source"],
               case["expected_top_condition"]),
        )
        check(
            results,
            "%s_input_matches_the_case_bank" % prefix,
            entry["input"]["symptom_tokens"] == case["input_tokens"]
            and entry["input"]["demographic_tokens"] == case["demographic_tokens"]
            and entry["input"]["season"] == case["season"],
            "registry=%r" % entry["input"],
        )

        # The pinned observation must still be what the artifacts produce.
        model = evidence.get(case_id)
        observed = entry["observed_output"]
        if model is not None:
            check(
                results,
                "%s_observed_output_matches_the_evidence_model" % prefix,
                observed["urgency"] == model["model_result"]["urgency"]
                and observed["urgency_source"] == model["model_result"]["urgency_source"]
                and observed["top_condition"] == model["model_result"]["top_condition"],
                "registry=%r model=%r" % (observed, model["model_result"]),
            )
            check(
                results,
                "%s_observed_output_matches_the_mobile_run" % prefix,
                observed["urgency"] == model["mobile_actual"]["urgency"]
                and observed["urgency_source"] == model["mobile_actual"]["urgency_source"]
                and observed["top_condition"] == model["mobile_actual"]["top_condition"],
                "registry=%r mobile=%r" % (observed, model["mobile_actual"]),
            )
            check(
                results,
                "%s_registry_and_bank_genuinely_disagree" % prefix,
                (observed["urgency"] != expected["urgency"])
                or (observed["urgency_source"] != expected["urgency_source"]),
                "an entry whose observed output equals its expectation is not a finding — remove it",
            )

        # Honesty constraints.
        check(
            results,
            "%s_makes_no_clinical_approval_claim" % prefix,
            entry["classification_is_clinical_approval"] is False,
            str(entry["classification_is_clinical_approval"]),
        )
        check(
            results,
            "%s_classification_authority_is_not_clinical" % prefix,
            entry["classification_authority"] != "clinical",
            entry["classification_authority"],
        )
        check(
            results,
            "%s_decision_remains_open" % prefix,
            str(entry["decision_status"]).startswith("open"),
            "a resolved entry should be removed and the underlying issue fixed: %s"
            % entry["decision_status"],
        )
        check(
            results,
            "%s_has_a_review_trigger_with_an_expiry" % prefix,
            bool(entry["review_trigger"].get("expires_at_milestone")),
            json.dumps(entry["review_trigger"].get("expires_at_milestone")),
        )
        check(
            results,
            "%s_cites_evidence" % prefix,
            len(entry["evidence_references"]) >= 3,
            "%d references" % len(entry["evidence_references"]),
        )
        check(
            results,
            "%s_is_not_marked_safety_critical" % prefix,
            entry["safety_impact"]["safety_critical"] is False
            and entry["safety_impact"]["triage_direction"] != "under_triage",
            "a safety-critical or under-triage finding must never be registered — it must be fixed",
        )

    contract = registry["runner_contract"]
    for forbidden in FORBIDDEN_IN_RUNNER_CONTRACT:
        check(
            results,
            "runner_contract_forbids: %s" % forbidden,
            forbidden in contract["must_not"],
            "missing from must_not",
        )
    check(
        results,
        "runner_contract_requires_execution",
        any("execute" in m for m in contract["must"]),
        "the registry must never permit skipping a case",
    )
    check(
        results,
        "runner_contract_fails_on_deviation",
        any("fail the run if any observed field differs" in m for m in contract["must"]),
        "the registry must fail closed on any deviation",
    )
    check(
        results,
        "registry_is_marked_not_wired",
        "not_yet_wired" in registry["_metadata"],
        "the proposal must state that it is not wired into a runner",
    )

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = run()
    failed = [r for r in results if not r["passed"]]
    summary = {
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "all_passed": not failed,
    }

    if args.json:
        print(json.dumps({
            "report_id": "known_findings_validation",
            "generator": "tools/validate_known_findings.py",
            "generator_version": VOCAB_TOOLING_VERSION,
            "summary": summary,
            "checks": results,
        }, indent=2))
    else:
        for r in results:
            print("%-4s %s%s" % ("OK" if r["passed"] else "FAIL", r["check"],
                                 "" if r["passed"] else "  [%s]" % r["detail"]))
        print("\n%d checks, %d passed, %d failed" % (summary["total"], summary["passed"], summary["failed"]))

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
