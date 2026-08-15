#!/usr/bin/env python3
"""Freeze the current artifact baseline into a machine-readable report.

    python3 tools/report_baseline.py            # write reports/baseline_freeze_v1.json
    python3 tools/report_baseline.py --check    # regenerate and diff, exit 1 on drift

Reads the frozen artifacts as bytes and reports what is there. It never
re-serializes, re-formats or rewrites a frozen artifact: the hashes below are
hashes of the files exactly as they sit in git.
"""

import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import (
    dump_report_bytes,
    file_size,
    load_json,
    repo_path,
    sha256_file,
    write_bytes,
)
from vocab.normalize import normalize_token_id

REPORT_PATH = repo_path("reports", "baseline_freeze_v1.json")

# The E9.1 frozen set, as declared in progress.md and served by the backend's
# GET /config. Listed explicitly so the report proves the repository state
# matches the declared freeze rather than assuming it.
FROZEN = [
    ("token_dictionary", "1.1", "token_dictionary.ng.v1.1.json"),
    ("knowledge_base", "2.4", "kb.ng.v2.4.json"),
    ("rules", "2.2", "rules.ng.v2.2.json"),
    ("facilities", "1.1", "facilities.ng.v1.1.json"),
]

CATEGORIES = [
    "symptom_tokens",
    "red_flag_tokens",
    "duration_tokens",
    "body_area_tokens",
    "demographic_tokens",
    "severity_tokens",
]

TOKEN_ID_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")

# Defects that already exist in the frozen baseline. They are recorded, not
# fixed: repairing any of them means changing a frozen clinical artifact or the
# vocabulary itself, which is out of scope for W2 Step 1 and needs clinical
# review. The reference check fails on anything NOT listed here, so a finding
# introduced by W2 still turns CI red.
KNOWN_BASELINE_FINDINGS = {
    "unresolved_token_references": {
        "pneumonia": "kb.ng.v2.4.json pneumonia_children.severity_levels IMCI tier key",
        "severe_pneumonia": "kb.ng.v2.4.json pneumonia_children.severity_levels IMCI tier key",
        "very_severe_disease": "kb.ng.v2.4.json pneumonia_children.severity_levels IMCI tier key",
    }
}

KNOWN_FINDING_NOTES = [
    "schema/kb_schema_v1.0.json lists no_pneumonia / pneumonia / severe_pneumonia / "
    "very_severe_disease as the valid IMCI severity_levels keys, while also stating that "
    "severity_levels keys must be values from severity_tokens. token_dictionary.ng.v1.1.json "
    "contains only 'no_pneumonia' of those four, so three IMCI tier keys used by the "
    "pneumonia_children condition do not resolve against the dictionary. The kb schema "
    "contradicts itself; this is a pre-existing documentation/vocabulary gap, not a W2 change.",
    "Behavioural impact assessed as none for scoring: severity_levels tier KEYS are labels for "
    "tiers, whereas scoring reads conditions[].symptoms[].token and red-flag evaluation reads "
    "rules[].token. No engine path resolves a tier key against the token dictionary.",
    "Resolution is a clinical/product decision — either add the three tokens to severity_tokens "
    "or correct schema/kb_schema_v1.0.json. Both are vocabulary or frozen-artifact changes and "
    "are explicitly out of scope for W2 Step 1. Raised as a follow-up in docs/I2_W2_VOCABULARY_FOUNDATION.md.",
]


def artifact_entry(artifact_id, expected_version, filename):
    path = repo_path(filename)
    exists = os.path.exists(path)
    entry = {
        "artifact_id": artifact_id,
        "file": filename,
        "exists": exists,
        "declared_version": expected_version,
    }
    if not exists:
        entry["error"] = "file not present in the repository"
        return entry
    obj = load_json(path)
    metadata = obj.get("_metadata", {})
    entry.update(
        {
            "internal_version": metadata.get("version"),
            "internal_version_matches_declared": metadata.get("version") == expected_version,
            "schema_version": metadata.get("schema_version"),
            "release_date": metadata.get("release_date"),
            "country": metadata.get("country"),
            "sha256": sha256_file(path),
            "bytes": file_size(path),
        }
    )
    return entry


def token_stats(token_dictionary):
    by_category = {c: list(token_dictionary.get(c, [])) for c in CATEGORIES}
    occurrences = collections.Counter()
    for tokens in by_category.values():
        occurrences.update(tokens)

    all_tokens = sorted(occurrences)
    normalized = collections.defaultdict(list)
    for token in all_tokens:
        normalized[normalize_token_id(token)].append(token)

    return {
        "token_count": len(all_tokens),
        "sum_of_category_lengths": sum(len(v) for v in by_category.values()),
        "counts_by_category": {c: len(v) for c, v in by_category.items()},
        "declared_counts_by_category": {
            c: token_dictionary.get("_metadata", {}).get(c + "_count") for c in CATEGORIES
        },
        "declared_total_tokens": token_dictionary.get("_metadata", {}).get("total_tokens"),
        "token_id_format": "lowercase_snake_case, ASCII, ^[a-z][a-z0-9]*(_[a-z0-9]+)*$",
        "token_id_format_violations": [t for t in all_tokens if not TOKEN_ID_RE.match(t)],
        "duplicate_tokens_within_a_category": sorted(
            t for c in CATEGORIES for t, n in collections.Counter(by_category[c]).items() if n > 1
        ),
        "tokens_in_more_than_one_category": sorted(t for t, n in occurrences.items() if n > 1),
        "duplicate_normalized_labels": {
            form: tokens for form, tokens in sorted(normalized.items()) if len(tokens) > 1
        },
        "all_tokens": all_tokens,
    }


def reference_scan(token_dictionary, kb, rules, case_bank):
    known = set()
    for category in CATEGORIES:
        known.update(token_dictionary.get(category, []))

    references = collections.defaultdict(set)

    def note(token, kind):
        references[token].add(kind)

    for condition in kb.get("conditions", []):
        for symptom in condition.get("symptoms", []):
            note(symptom["token"], "kb.symptoms")
        for flag in condition.get("red_flags", []):
            note(flag, "kb.red_flags")
        for tier, tokens in (condition.get("severity_levels") or {}).items():
            note(tier, "kb.severity_levels.key")
            for token in tokens:
                note(token, "kb.severity_levels.value")
        for modifier in condition.get("demographic_modifiers", []):
            note(modifier["modifier"], "kb.demographic_modifiers")

    for rule in rules.get("rules", []):
        note(rule["token"], "rules.token")

    if case_bank is not None:
        for case in case_bank.get("cases", []):
            for token in case.get("input_tokens", []):
                note(token, "case_bank.input_tokens")
            for token in case.get("demographic_tokens", []):
                note(token, "case_bank.demographic_tokens")

    referenced = {t for t in references if t in known}
    unresolved = sorted(t for t in references if t not in known)
    clinical_kinds = ("kb.", "rules.")
    clinically_referenced = {
        t
        for t in referenced
        if any(kind.startswith(clinical_kinds) for kind in references[t])
    }

    return {
        "referenced_token_count": len(referenced),
        "orphan_token_count": len(known - referenced),
        "orphan_tokens": sorted(known - referenced),
        "tokens_with_no_kb_or_rules_consumer_count": len(known - clinically_referenced),
        "unresolved_token_reference_count": len(unresolved),
        "unresolved_token_references": {
            token: sorted(references[token]) for token in unresolved
        },
    }


def build_report():
    artifacts = [artifact_entry(*spec) for spec in FROZEN]
    token_dictionary = load_json(repo_path("token_dictionary.ng.v1.1.json"))
    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))

    case_bank_path = repo_path("testing", "case_bank_v1.json")
    case_bank_present = os.path.exists(case_bank_path)
    case_bank = load_json(case_bank_path) if case_bank_present else None

    validation = []

    def check(name, passed, detail):
        validation.append({"check": name, "passed": bool(passed), "detail": detail})

    for entry in artifacts:
        check(
            "artifact_present:%s" % entry["artifact_id"],
            entry.get("exists"),
            entry.get("error", entry.get("file")),
        )
        if entry.get("exists"):
            check(
                "internal_version_matches_filename:%s" % entry["artifact_id"],
                entry.get("internal_version_matches_declared"),
                "_metadata.version=%r declared=%r"
                % (entry.get("internal_version"), entry["declared_version"]),
            )

    stats = token_stats(token_dictionary)
    references = reference_scan(token_dictionary, kb, rules, case_bank)

    check(
        "token_count_matches_declared_total",
        stats["token_count"] == stats["declared_total_tokens"],
        "counted=%d declared=%d" % (stats["token_count"], stats["declared_total_tokens"]),
    )
    check(
        "category_counts_match_declared",
        stats["counts_by_category"] == stats["declared_counts_by_category"],
        "counted=%r declared=%r"
        % (stats["counts_by_category"], stats["declared_counts_by_category"]),
    )
    check(
        "no_token_id_format_violations",
        not stats["token_id_format_violations"],
        stats["token_id_format_violations"],
    )
    check(
        "no_cross_category_duplicate_tokens",
        not stats["tokens_in_more_than_one_category"],
        stats["tokens_in_more_than_one_category"],
    )
    known_unresolved = set(KNOWN_BASELINE_FINDINGS["unresolved_token_references"])
    new_unresolved = sorted(set(references["unresolved_token_references"]) - known_unresolved)
    check(
        "no_new_unresolved_token_references",
        not new_unresolved,
        "new=%r known_pre_existing=%d" % (new_unresolved, len(known_unresolved)),
    )
    check(
        "known_baseline_findings_still_accurate",
        known_unresolved.issubset(set(references["unresolved_token_references"])),
        "a recorded pre-existing finding no longer reproduces; update KNOWN_BASELINE_FINDINGS",
    )
    check(
        "kb_declares_token_dictionary_1_1",
        kb.get("_metadata", {}).get("token_dictionary_version") == "1.1",
        kb.get("_metadata", {}).get("token_dictionary_version"),
    )

    return {
        "report_id": "baseline_freeze",
        "report_version": "1",
        "phase": "I2 / W2 Step 1",
        "generator": "tools/report_baseline.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "purpose": "Freeze the pre-W2 artifact baseline. Hashes are of the files exactly as committed; no frozen artifact is re-serialized or rewritten.",
        "artifacts": artifacts,
        "token_dictionary_baseline": stats,
        "reference_integrity": references,
        "current_schema_identifiers": {
            "token_dictionary": {
                "schema_version": token_dictionary.get("_metadata", {}).get("schema_version"),
                "schema_file": None,
                "note": "schema 1.0 for the token dictionary was never written down as a file; it is implicit in the artifact shape and in the two schema files that reference it.",
            },
            "knowledge_base": {
                "schema_version": kb.get("_metadata", {}).get("schema_version"),
                "schema_file": "schema/kb_schema_v1.0.json",
            },
            "rules": {
                "schema_version": rules.get("_metadata", {}).get("schema_version"),
                "schema_file": "schema/rules_schema_v1.0.json",
            },
            "facilities": {
                "schema_version": None,
                "schema_file": "facilities/facility_schema_v1.0.md",
                "note": "prose schema; facilities artifacts carry no _metadata.schema_version.",
            },
            "case_bank": {
                "schema_version": None,
                "schema_file": "testing/README.md",
                "note": "prose schema documented in the testing README; the artifact carries _metadata.version only.",
            },
        },
        "case_bank_availability": {
            "canonical_path": "testing/case_bank_v1.json",
            "present_in_this_repository": case_bank_present,
            "version": (case_bank or {}).get("_metadata", {}).get("version"),
            "total_cases": len((case_bank or {}).get("cases", [])),
            "sha256": sha256_file(case_bank_path) if case_bank_present else None,
            "detail": "See reports/case_bank_status_v1.json for the full discovery result, harness readiness and clinical-approval state.",
        },
        "known_baseline_findings": {
            "unresolved_token_references": KNOWN_BASELINE_FINDINGS["unresolved_token_references"],
            "count": len(KNOWN_BASELINE_FINDINGS["unresolved_token_references"]),
            "introduced_by_w2": False,
            "fixed_by_w2": False,
            "notes": KNOWN_FINDING_NOTES,
        },
        "validation_results": {
            "checks": validation,
            "passed": sum(1 for c in validation if c["passed"]),
            "failed": sum(1 for c in validation if not c["passed"]),
            "all_passed": all(c["passed"] for c in validation),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed report is stale")
    args = parser.parse_args()

    payload = dump_report_bytes(build_report())

    if args.check:
        if not os.path.exists(REPORT_PATH):
            print("FAIL reports/baseline_freeze_v1.json is missing")
            return 1
        with open(REPORT_PATH, "rb") as handle:
            if handle.read() != payload:
                print("FAIL reports/baseline_freeze_v1.json is stale — re-run tools/report_baseline.py")
                return 1
        print("OK   baseline freeze report is current")
        return 0

    write_bytes(REPORT_PATH, payload)
    print("wrote reports/baseline_freeze_v1.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
