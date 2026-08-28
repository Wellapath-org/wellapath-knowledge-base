#!/usr/bin/env python3
"""Record the exact bytes this step must not have touched.

    python3 tools/report_publication_freeze.py           # write
    python3 tools/report_publication_freeze.py --check    # fail if any frozen artifact moved

Writes `reports/publication_freeze_v1.json`.

The list is the one I3 Step 2 is required to prove unchanged: KB 2.4, rules 2.2, both token
dictionaries, both facilities artifacts, the Vocabulary 2.0 candidate, both Question Flow
candidates and their schemas, the candidate manifest, the live-question oracle, the case bank,
the known-findings registry, every IM-001 evidence and decision record, and every IM-003
record.

`--check` is the proof, and it is a strong one precisely because this report is generated: it
recomputes every digest from the bytes on disk and fails on any difference. It cannot be
satisfied by editing the report, because editing the report is itself a difference — the
committed copy would no longer match what the generator produces.

Standard library only, no network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import dump_report_bytes, repo_path, sha256_file, write_bytes

OUTPUT = repo_path("reports", "publication_freeze_v1.json")

FROZEN = {
    "clinical_artifacts": [
        "kb.ng.v2.4.json",
        "rules.ng.v2.2.json",
        "token_dictionary.ng.v1.0.json",
        "token_dictionary.ng.v1.1.json",
        "facilities.ng.v1.0.json",
        "facilities.ng.v1.1.json",
    ],
    "candidates": [
        "candidate/token_dictionary.ng.v2.0.json",
        "candidate/question_flow.ng.v1.0.json",
        "candidate/question_flow.ng.v1.1.json",
        "candidate/manifest.candidate.json",
        "candidate/CANDIDATE_STATUS.md",
    ],
    "schemas": [
        "schema/question_flow.v1.schema.json",
        "schema/question_flow.v1_1.schema.json",
        "schema/token_dictionary.v2.schema.json",
        "schema/token_dictionary_schema_v2.0.json",
        "schema/kb_schema_v1.0.json",
        "schema/rules_schema_v1.0.json",
    ],
    "oracle": [
        "testing/questions/fixtures/oracle/live_question_oracle_v1.json",
        "testing/questions/fixtures/oracle/live_question_oracle_v1.provenance.json",
        "testing/questions/fixtures/oracle/live_question_oracle_v1.harness.dart.txt",
    ],
    "case_bank_and_findings": [
        "testing/case_bank_v1.json",
        "testing/case_bank_results_v1.json",
        "testing/known_findings.json",
        "reports/case_bank_status_v1.json",
        "reports/case_findings_v1.json",
    ],
    "im001_records": [
        "reports/im001_option_order_decision_v1.json",
        "reports/im001_option_order_evidence_v1.json",
        "reports/im001_product_review_v1_1.json",
        "reports/im001_product_verdicts_v1.json",
        "review/im001_workbook_v1/im001_workbook_v1.json",
        "review/im001_workbook_v1/im001_decision_template_v1.json",
        "review/im001_workbook_v1/IM001_DECISION_WORKBOOK.md",
        "baseline/im001_reconciliation_v1/IM001_PRODUCT_DECISION_RECONCILIATION_2026-08-24.vendored.md",
        "docs/IM001_OPTION_ORDERING.md",
    ],
    "im003_records": [
        "reports/im003_decision_package_v1.json",
        "reports/im003_disposition_v1.json",
        "reports/im003_impact_analysis_v1.json",
        "reports/im003_mobile_measurement_v1.json",
        "reports/im003_safety_blockers_v1.json",
        "baseline/im003_decision_record_v1/IM003_SAFETY_REVIEW_DECISION_RECORD_2026-08-22.vendored.md",
        "baseline/im003_mobile_v1/im003_mobile_scoring_measurement_v1.vendored.json",
        "docs/IM003_DISPOSITION_RECORD.md",
        "docs/IM003_IMPACT_ANALYSIS.md",
        "docs/IM003_SB_001_ADJUDICATION.md",
    ],
}


def build():
    groups = {}
    total = 0
    missing = []

    for group in sorted(FROZEN):
        entries = []
        for relative in FROZEN[group]:
            path = repo_path(relative)
            if not os.path.exists(path):
                missing.append(relative)
                continue
            entries.append(
                {
                    "path": relative,
                    "sha256": sha256_file(path),
                    "byte_count": os.path.getsize(path),
                }
            )
            total += 1
        groups[group] = entries

    if missing:
        raise SystemExit(
            "frozen artifacts are missing from the repository: %s" % ", ".join(sorted(missing))
        )

    return {
        "_metadata": {
            "report_id": "publication_freeze",
            "version": "1",
            "phase": "I3 / Step 2",
            "generator": "tools/report_publication_freeze.py",
            "generator_version": "1.0.0",
            "note": "The exact bytes I3 Step 2 must not have touched. Regenerated and compared "
            "in --check mode, so a single changed byte in any listed file fails the run. The "
            "report cannot be fixed by editing it: an edited report no longer matches what the "
            "generator produces, which is the same failure.",
        },
        "rule": "The publication tooling reads these files, hashes them and copies them into a "
        "disposable staging directory. It has no code path that opens any of them for writing, "
        "and every packaging operation re-hashes the source afterwards to prove it did not.",
        "frozen_artifact_count": total,
        "groups": groups,
    }


def main(argv):
    check = "--check" in argv
    data = dump_report_bytes(build())
    relative = os.path.relpath(OUTPUT, repo_path())

    if check:
        if not os.path.exists(OUTPUT):
            print("MISSING %s" % relative)
            return 1
        with open(OUTPUT, "rb") as handle:
            committed = handle.read()
        if committed != data:
            print("DRIFT %s: a frozen artifact changed, or the report was edited by hand" % relative)
            return 1
        print("OK %s" % relative)
        return 0

    write_bytes(OUTPUT, data)
    print("wrote %s (%d bytes)" % (relative, len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
