#!/usr/bin/env python3
"""Report the Top-50 case-bank baseline status.

    python3 tools/report_case_bank_status.py            # write the report
    python3 tools/report_case_bank_status.py --check    # fail if the report is stale

The report deliberately keeps four things apart, because collapsing them is how
a missing regression gets mistaken for a passing one:

    harness_readiness           — does executable test machinery exist?
    case_data_availability      — do the approved cases exist, and where?
    clinical_approval           — has a clinician signed off on the cases?
    executable_regression_result — has the regression actually been run, and
                                   against which artifact versions?
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

REPORT_PATH = repo_path("reports", "case_bank_status_v1.json")
CASE_BANK_PATH = repo_path("testing", "case_bank_v1.json")
RESULTS_PATH = repo_path("testing", "case_bank_results_v1.json")


def build_report():
    present = os.path.exists(CASE_BANK_PATH)
    case_bank = load_json(CASE_BANK_PATH) if present else None
    metadata = (case_bank or {}).get("_metadata", {})
    cases = (case_bank or {}).get("cases", [])

    results_present = os.path.exists(RESULTS_PATH)
    results = load_json(RESULTS_PATH) if results_present else None
    run_metadata = (results or {}).get("run_metadata", {})
    as_shipped = (results or {}).get("as_shipped", {})
    run_summary = as_shipped.get("summary", {})

    by_source = collections.Counter(c.get("expected_urgency_source") for c in cases)

    return {
        "report_id": "case_bank_status",
        "report_version": "1",
        "phase": "I2 / W2 Step 1",
        "generator": "tools/report_case_bank_status.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "question_asked": (
            "The W2 brief records that case_bank_v1.json is absent from the mobile repository's "
            "default case-bank path, causing six Top-50 case-bank tests to skip. Does a canonical "
            "case bank exist, and where?"
        ),
        "discovery_result": {
            "outcome": "canonical_case_bank_found",
            "summary": (
                "The canonical Top-50 case bank exists and is committed in THIS repository at "
                "testing/case_bank_v1.json. It was never missing. What is missing is a copy at the "
                "mobile repository's default fixture path — this is a distribution gap between two "
                "repositories, not absent case data."
            ),
            "sources_searched": [
                "current repository working tree",
                "current repository git history, all branches (git log --all -- testing/case_bank_v1.json)",
                "tracked fixtures under testing/",
                "release artifacts at the repository root",
                "existing test definitions in the mobile repository, all branches",
                "project-provided source documents under source/",
            ],
            "git_provenance": [
                "ba7815e feat(testing): add E8.1 case bank - 234 scenarios across all 50 conditions (PR #13)",
                "7ea1724 fix(testing,rules): apply E8.1 engineering-lead corrections + retire dead rf_147 (PR #15)",
                "0d3a159 feat(kb): E8.2 headache token + kb.ng.v2.4.json (PR #18)",
                "c974100 test(e8.2): add three re-verified E3.5 pilot cases (CB_237-239) (PR #19)",
            ],
            "no_content_invented": True,
            "restoration_action": (
                "None needed in this repository — the file is already at its canonical path, "
                "unmodified. No case was reinterpreted, renumbered, added or 'improved'. The file "
                "is byte identical to the E9 freeze and is asserted as such by "
                "tools/check_compatibility.py."
            ),
        },
        "case_data_availability": {
            "status": "available",
            "canonical_path": "testing/case_bank_v1.json",
            "present": present,
            "version": metadata.get("version"),
            "phase": metadata.get("phase"),
            "sha256": sha256_file(CASE_BANK_PATH) if present else None,
            "bytes": os.path.getsize(CASE_BANK_PATH) if present else None,
            "total_cases": len(cases),
            "declared_total_cases": metadata.get("total_cases"),
            "count_matches_declaration": len(cases) == metadata.get("total_cases"),
            "safety_critical_cases": metadata.get("safety_critical_cases"),
            "conditions_covered": metadata.get("conditions_covered"),
            "global_red_flag_tokens_tested": metadata.get("global_red_flag_tokens_tested"),
            "expected_urgency_source_breakdown": dict(sorted(by_source.items(), key=lambda kv: str(kv[0]))),
            "built_from": metadata.get("built_from"),
            "valid_against_rules": metadata.get("valid_against_rules"),
            "expected_value_derivation": metadata.get("expected_value_derivation"),
        },
        "harness_readiness": {
            "status": "ready_but_not_wired",
            "owner": "mobile engineering",
            "harness_location": "wellapath-mobile test/engine/case_bank_validation_test.dart, with support code under test/engine/case_bank/",
            "harness_branches": ["develop", "feat/e8-case-bank-testing", "docs/i1-closure"],
            "default_case_bank_path": "test/fixtures/case_bank_v1.json",
            "override_mechanism": "--dart-define=CASE_BANK_PATH=<absolute path>",
            "skip_behaviour": (
                "Documented and intentional. The harness header states: 'Until then this file skips "
                "rather than fails - the harness's own behaviour is covered by "
                "case_bank_runner_test.dart, which does not need the bank.' The skip is therefore a "
                "correctly reported missing input, not a silent pass."
            ),
            "note": (
                "The default fixture path holds no file on any mobile branch inspected. Nothing in "
                "this repository can populate it: this repository cannot commit to the mobile "
                "repository. The exact copy command is in the Mobile handoff."
            ),
        },
        "clinical_approval": {
            "status": "not_evidenced_as_clinician_approved",
            "what_is_evidenced": [
                "Engineering-lead corrections were applied to the bank (commit 7ea1724, PR #15): red-flag cases' expected_top_condition set to null, 18 demographic cases moved to a demographic_escalation source, CB_159 reclassified to global_red_flag.",
                "Expected values are spec-derived from kb + rules + the Case-04 Option B escalation policy, deliberately independent of the engine (testing/build_case_bank.py header).",
                "CB_237-239 are described as 're-verified E3.5 pilot cases' (PR #19).",
            ],
            "what_is_not_evidenced": [
                "No named clinical reviewer is recorded in the case bank _metadata.",
                "No review date or approval record is recorded in the case bank _metadata.",
                "The case bank schema has no reviewer or approval field at all.",
            ],
            "conclusion": (
                "The bank is engineering-approved and spec-derived. It is NOT recorded as "
                "clinician-signed-off. This is stated rather than assumed; W2 adds no reviewer "
                "metadata, because inventing one would fabricate an approval."
            ),
            "required_input": "A named clinical reviewer and approval date for case bank v1.0, or an explicit decision that engineering-lead approval is the accepted bar for this artifact.",
        },
        "executable_regression_result": {
            "status": "stale_not_rerun",
            "last_recorded_run": {
                "results_file": "testing/case_bank_results_v1.json",
                "present": results_present,
                "phase": run_metadata.get("phase"),
                "artifacts": run_metadata.get("artifacts"),
                "wiring": run_metadata.get("wiring"),
                "total_cases": run_summary.get("total_cases"),
                "graded_cases": run_summary.get("graded_cases"),
                "observe_cases": run_summary.get("observe_cases"),
                "passed": run_summary.get("passed"),
                "failed": run_summary.get("failed"),
                "under_triage": run_summary.get("under_triage"),
                "over_triage": run_summary.get("over_triage"),
                "safety_critical_failures": run_summary.get("safety_critical_failures"),
            },
            "why_stale": [
                "The recorded run covers 234 cases; the committed bank now has 239 (CB_235-239 were added afterwards).",
                "The recorded run used knowledge_base 2.3; the frozen baseline is 2.4.",
                "A 239-case re-run against kb 2.4 was requested at E9 and is not recorded in this repository.",
            ],
            "w2_impact": (
                "The W2 candidate cannot regress clinical output through this bank, because it "
                "changes no clinical input: kb 2.4, rules 2.2 and the accepted token set are all "
                "byte identical, proven by tools/check_compatibility.py. But 'cannot regress by "
                "construction' is not the same as 'proven unchanged by execution', and this report "
                "does not claim the latter."
            ),
            "certification_status": "NOT CERTIFIED — existing Top-50 behaviour is proven unchanged structurally (byte identity of every clinical input), not by an executed 239-case run against kb 2.4.",
        },
        "blocked_items": [
            {
                "item": "Executed 239-case Top-50 regression against kb 2.4 / rules 2.2",
                "blocked_on": "mobile engineering — copy the canonical bank to test/fixtures/case_bank_v1.json (or pass CASE_BANK_PATH) and run the harness",
                "blocking_w2_step_1": False,
                "reason_not_blocking": "W2 Step 1 publishes nothing and changes no clinical input. The re-run is required before any vocabulary change that is classified beyond search-only metadata.",
            },
            {
                "item": "Clinical reviewer sign-off on case bank v1.0",
                "blocked_on": "clinical review",
                "blocking_w2_step_1": False,
            },
        ],
        "missing_content_manifest": {
            "applicable": False,
            "reason": "A missing-content manifest applies only when no canonical case bank exists. One exists, is complete against its own declared coverage, and is byte identical to the E9 freeze.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = dump_report_bytes(build_report())

    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/case_bank_status_v1.json is missing or stale")
            return 1
        print("OK   case bank status report is current")
        return 0

    write_bytes(REPORT_PATH, payload)
    print("wrote reports/case_bank_status_v1.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
