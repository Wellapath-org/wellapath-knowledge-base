#!/usr/bin/env python3
"""Classify a vocabulary diff by clinical safety, and decide publication eligibility.

    python3 tools/classify_vocabulary_diff.py                       # baseline 1.1 vs candidate
    python3 tools/classify_vocabulary_diff.py <old> <new>           # any two artifacts
    python3 tools/classify_vocabulary_diff.py --write               # write the reports
    python3 tools/classify_vocabulary_diff.py --check               # fail if reports are stale

Every difference is assigned exactly one class. The class decides who has to
approve it:

    search_only_metadata      — aliases, normalized forms, the search index.
                                Data-engineer merge. No clinical review.
    display_only_metadata     — labels, display_safe, locale, body-area and
                                complaint-group display text.
                                Product review. No clinical review.
    clinical_token_identity   — a token ID added, removed, recategorized,
                                repointed, or its scoring eligibility changed.
                                BLOCKS publication. Clinical review required.
    red_flag_affecting        — a change touching a token that rules or a kb
                                red_flags list depends on.
                                BLOCKS publication. Clinical review required.
    scoring_rule_affecting    — a change touching a token carrying a kb symptom
                                weight.
                                BLOCKS publication. Clinical review required.
    question_flow_affecting   — a change to the set of tokens an assessment may
                                submit.
                                BLOCKS publication. Clinical + Product review.
    deprecation_removal       — a token deprecated or removed.
                                BLOCKS publication. Clinical review required.

The blocking classes are not advisory. `publication_eligible` is false whenever
any of them is present, and CI asserts it.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

BASELINE = repo_path("token_dictionary.ng.v1.1.json")
CANDIDATE = repo_path("candidate", "token_dictionary.ng.v2.0.json")
DIFF_REPORT = repo_path("reports", "baseline_diff_v1.json")
MIGRATION_REPORT = repo_path("reports", "migration_report_v1.json")

CATEGORIES = [
    "symptom_tokens",
    "red_flag_tokens",
    "duration_tokens",
    "body_area_tokens",
    "demographic_tokens",
    "severity_tokens",
]

SEARCH_ONLY = "search_only_metadata"
DISPLAY_ONLY = "display_only_metadata"
TOKEN_IDENTITY = "clinical_token_identity"
RED_FLAG = "red_flag_affecting"
SCORING = "scoring_rule_affecting"
QUESTION_FLOW = "question_flow_affecting"
DEPRECATION = "deprecation_removal"

BLOCKING = frozenset([TOKEN_IDENTITY, RED_FLAG, SCORING, QUESTION_FLOW, DEPRECATION])

REQUIRED_APPROVAL = {
    SEARCH_ONLY: "data engineering merge",
    DISPLAY_ONLY: "product review",
    TOKEN_IDENTITY: "clinical review + engineering lead",
    RED_FLAG: "clinical review + engineering lead",
    SCORING: "clinical review + engineering lead",
    QUESTION_FLOW: "clinical review + product review",
    DEPRECATION: "clinical review + engineering lead",
}


def token_sets(artifact):
    """Token IDs by category, handling both schema 1.0 and 2.0 artifacts."""
    return {category: list(artifact.get(category, [])) for category in CATEGORIES}


def entries_by_id(artifact):
    return {e["token_id"]: e for e in artifact.get("tokens", [])}


def clinical_roles(kb, rules):
    """Which tokens carry scoring weight, and which drive red flags."""
    scoring = set()
    red_flag = set()
    for condition in kb["conditions"]:
        for symptom in condition["symptoms"]:
            scoring.add(symptom["token"])
        red_flag.update(condition["red_flags"])
    for rule in rules["rules"]:
        red_flag.add(rule["token"])
    return scoring, red_flag


def classify(old, new):
    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))
    scoring_tokens, red_flag_tokens = clinical_roles(kb, rules)

    old_by_category = token_sets(old)
    new_by_category = token_sets(new)
    old_ids = {t for v in old_by_category.values() for t in v}
    new_ids = {t for v in new_by_category.values() for t in v}

    findings = []

    def finding(cls, description, tokens=None, detail=None):
        findings.append(
            {
                "classification": cls,
                "blocks_publication": cls in BLOCKING,
                "required_approval": REQUIRED_APPROVAL[cls],
                "description": description,
                "tokens": sorted(tokens or []),
                "detail": detail,
            }
        )

    def escalate(cls, tokens):
        """A token-identity change inherits the strongest role the token plays."""
        classes = {cls}
        if tokens & red_flag_tokens:
            classes.add(RED_FLAG)
        if tokens & scoring_tokens:
            classes.add(SCORING)
        return classes

    # --- token set changes -----------------------------------------------------
    added = new_ids - old_ids
    removed = old_ids - new_ids

    if added:
        for cls in escalate(TOKEN_IDENTITY, added):
            finding(cls, "Token IDs added to the vocabulary.", added)
        finding(QUESTION_FLOW, "The set of tokens an assessment may submit grew.", added)
    if removed:
        for cls in escalate(DEPRECATION, removed):
            finding(cls, "Token IDs removed from the vocabulary.", removed)
        finding(QUESTION_FLOW, "The set of tokens an assessment may submit shrank.", removed)

    recategorized = set()
    for category in CATEGORIES:
        moved = (set(old_by_category[category]) & new_ids) - set(new_by_category[category])
        recategorized |= moved
    if recategorized:
        for cls in escalate(TOKEN_IDENTITY, recategorized):
            finding(cls, "Tokens changed category.", recategorized)

    reordered = [
        category
        for category in CATEGORIES
        if [t for t in old_by_category[category] if t in new_ids]
        != [t for t in new_by_category[category] if t in old_ids]
    ]
    if reordered:
        finding(
            TOKEN_IDENTITY,
            "Legacy array ordering changed. Ordering is part of the schema 1.0 compatibility surface.",
            detail={"categories": reordered},
        )

    # --- per-entry changes (only meaningful when both sides are schema 2.0) ----
    old_entries = entries_by_id(old)
    new_entries = entries_by_id(new)
    shared = sorted(set(old_entries) & set(new_entries))

    if shared:
        identity_changed = set()
        deprecated = set()
        display_changed = set()
        search_changed = set()
        association_changed = set()

        for token_id in shared:
            before, after = old_entries[token_id], new_entries[token_id]
            if before["clinical_identity"] != after["clinical_identity"]:
                if (
                    before["clinical_identity"]["status"] != "deprecated"
                    and after["clinical_identity"]["status"] == "deprecated"
                ):
                    deprecated.add(token_id)
                else:
                    identity_changed.add(token_id)
            if before["display"] != after["display"]:
                display_changed.add(token_id)
            if before["search"] != after["search"]:
                search_changed.add(token_id)
            if before["associations"] != after["associations"]:
                association_changed.add(token_id)

        if identity_changed:
            for cls in escalate(TOKEN_IDENTITY, identity_changed):
                finding(cls, "clinical_identity changed on existing tokens.", identity_changed)
        if deprecated:
            for cls in escalate(DEPRECATION, deprecated):
                finding(cls, "Tokens deprecated.", deprecated)
        if display_changed:
            finding(DISPLAY_ONLY, "Display metadata changed.", display_changed)
        if search_changed:
            finding(SEARCH_ONLY, "Search metadata changed (aliases / normalized form).", search_changed)
        if association_changed:
            finding(
                SEARCH_ONLY,
                "Association metadata changed (body areas, complaint groups, severity/duration descriptors). "
                "Search and input filtering only — no scoring effect at schema 2.0.",
                association_changed,
            )

    # --- structural additions --------------------------------------------------
    new_top_level = sorted(set(new) - set(old))
    if new_top_level:
        finding(
            SEARCH_ONLY,
            "New top-level keys added. Schema 1.0 consumers never read them.",
            detail={"keys": new_top_level},
        )

    present = sorted({f["classification"] for f in findings})
    blocking = sorted({c for c in present if c in BLOCKING})

    return {
        "classifications_present": present,
        "blocking_classifications": blocking,
        "publication_eligible": not blocking,
        "findings": findings,
        "token_counts": {
            "old": len(old_ids),
            "new": len(new_ids),
            "added": len(added),
            "removed": len(removed),
            "unchanged": len(old_ids & new_ids),
        },
    }


def build_reports(old_path, new_path):
    old = load_json(old_path)
    new = load_json(new_path)
    result = classify(old, new)

    old_meta = old.get("_metadata", {})
    new_meta = new.get("_metadata", {})

    common = {
        "generator": "tools/classify_vocabulary_diff.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "phase": "I2 / W2 Step 1",
        "from": {
            "file": os.path.relpath(old_path, repo_path()),
            "version": old_meta.get("version"),
            "schema_version": old_meta.get("schema_version"),
            "sha256": sha256_file(old_path),
        },
        "to": {
            "file": os.path.relpath(new_path, repo_path()),
            "version": new_meta.get("version"),
            "schema_version": new_meta.get("schema_version"),
            "sha256": sha256_file(new_path),
            "release_status": new_meta.get("release_status"),
        },
    }

    # `publication_eligible` answers exactly one question: does the diff contain
    # a change class that requires clinical review? A clean classification is
    # necessary for publication and nowhere near sufficient, so the decision is
    # spelled out rather than left to be inferred from a single boolean.
    publication_decision = {
        "classification_gate_passed": result["publication_eligible"],
        "other_gates": {
            "clinical_review_of_schema_2_0": new_meta.get("clinical_review", {}).get("status")
            == "reviewed",
            "engineering_lead_approval": False,
            "release_status_is_approved": new_meta.get("release_status")
            in ("approved_unpublished", "published"),
            "top50_regression_executed_against_kb_2_4": False,
        },
        "may_publish": False,
        "why_not": [
            "The classification gate passing means only that this diff contains no change "
            "requiring clinical review. It is not an approval to publish.",
            "release_status is candidate_unapproved and clinical_review.status is not_reviewed.",
            "No engineering-lead approval is recorded.",
            "The 239-case Top-50 regression has not been re-run against kb 2.4 — see "
            "reports/case_bank_status_v1.json.",
            "W2 Step 1 explicitly does not publish. The live /config manifest is unchanged.",
        ],
    }

    diff_report = dict(common)
    diff_report.update(
        {
            "report_id": "baseline_diff",
            "report_version": "1",
            "publication_decision": publication_decision,
            "classification_scheme": {
                cls: {"blocks_publication": cls in BLOCKING, "required_approval": REQUIRED_APPROVAL[cls]}
                for cls in [
                    SEARCH_ONLY,
                    DISPLAY_ONLY,
                    TOKEN_IDENTITY,
                    RED_FLAG,
                    SCORING,
                    QUESTION_FLOW,
                    DEPRECATION,
                ]
            },
            "result": result,
        }
    )

    migration_report = dict(common)
    migration_report.update(
        {
            "report_id": "migration_report",
            "report_version": "1",
            "method": {
                "generator": "tools/build_vocabulary_v2.py",
                "deterministic": True,
                "determinism_basis": "Fixed generation timestamp, no randomness or clock reads, stable iteration order over the source arrays, canonical JSON serialization (indent=2, ensure_ascii, no trailing newline).",
                "lossless_proof": "tools/build_vocabulary_v2.py project_to_v1_1() rebuilds the six token arrays from the new tokens[] entries alone and reproduces token_dictionary.ng.v1.1.json byte for byte. Asserted at build time and again in testing/vocabulary/test_vocabulary_v2.py.",
                "derived_values": [
                    "display.canonical_label — mechanically derived from the token ID, stamped derived_from_token_id / unreviewed / display_safe:false.",
                    "search.normalized_form — normalize(token_id with underscores as spaces).",
                    "clinical_identity.introduced_in_artifact_version — derived by diffing token_dictionary.ng.v1.0.json against v1.1.",
                    "body_areas — derived from the existing body_area_tokens array.",
                    "search_index.normalized_forms — generated from tokens[].",
                ],
                "left_empty_deliberately": [
                    "search.aliases — no approved alias catalogue exists in this repository.",
                    "associations.body_areas — the candidate source (PR #9 symptom_display_body_area_map) is unmerged and not clinically approved.",
                    "associations.complaint_groups — no approved grouping catalogue exists.",
                    "associations.severity_descriptors / duration_descriptors — no approved applicability matrix exists.",
                    "review.clinical_reviewer / review_date — no review has occurred; populating these would fabricate an approval.",
                ],
            },
            "preserved": {
                "token_ids": "all",
                "canonical_labels": "n/a — schema 1.0 carried no labels; every label in the candidate is newly derived and marked unreviewed",
                "clinical_meaning": "unchanged — every entry is active, scoring_eligible and self-canonical",
                "rule_references": "unchanged — rules.ng.v2.2.json untouched, all 75 rule tokens resolve",
                "red_flag_references": "unchanged — kb red_flags lists untouched, all resolve",
                "question_references": "unchanged — the accepted input token set is byte identical",
                "ordering": "unchanged — legacy arrays byte identical, tokens[] reproduces their order",
            },
            "result": result,
        }
    )

    return diff_report, migration_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old", nargs="?", default=BASELINE)
    parser.add_argument("new", nargs="?", default=CANDIDATE)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    diff_report, migration_report = build_reports(args.old, args.new)
    outputs = [(DIFF_REPORT, diff_report), (MIGRATION_REPORT, migration_report)]

    if args.check:
        for path, report in outputs:
            payload = dump_report_bytes(report)
            if not os.path.exists(path) or open(path, "rb").read() != payload:
                print("FAIL %s is missing or stale" % os.path.relpath(path, repo_path()))
                return 1
        print("OK   migration and baseline-diff reports are current")
        return 0

    if args.write:
        for path, report in outputs:
            write_bytes(path, dump_report_bytes(report))
            print("wrote %s" % os.path.relpath(path, repo_path()))
        return 0

    result = diff_report["result"]
    print("classifications: %s" % (", ".join(result["classifications_present"]) or "none"))
    print("blocking:        %s" % (", ".join(result["blocking_classifications"]) or "none"))
    print("classification gate passed: %s" % result["publication_eligible"])
    print("MAY PUBLISH:     %s" % diff_report["publication_decision"]["may_publish"])
    print("")
    for item in result["findings"]:
        print(
            "  [%s] %s%s"
            % (
                "BLOCKS" if item["blocks_publication"] else "  ok  ",
                item["classification"],
                " — %d token(s)" % len(item["tokens"]) if item["tokens"] else "",
            )
        )
        print("           %s" % item["description"])
    print("\ntoken counts: %s" % json.dumps(result["token_counts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
