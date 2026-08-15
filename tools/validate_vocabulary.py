#!/usr/bin/env python3
"""Validate a schema 2.0 vocabulary artifact.

    python3 tools/validate_vocabulary.py                       # validate the candidate
    python3 tools/validate_vocabulary.py <path>                # validate any artifact
    python3 tools/validate_vocabulary.py <path> --json         # machine-readable output
    python3 tools/validate_vocabulary.py <path> --no-baseline  # skip baseline comparison
                                                               # (for synthetic fixtures)

Exit code 0 means every check passed. Any failure exits 1 and prints the
offending values — a validator that reports "invalid" without saying which
field is not usable in a release checklist.

The checks are grouped so a reader can see what is being guaranteed:
  A. schema conformance
  B. identity and uniqueness
  C. display and search metadata
  D. references and deprecation
  E. generation determinism and index integrity
  F. baseline preservation (no baseline token removed or altered)
  G. provenance and review honesty
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import dump_artifact_bytes, load_json, repo_path, sha256_bytes, sha256_file
from vocab.normalize import NORMALIZATION_VERSION, derive_label_from_token_id, normalize, normalize_token_id
from vocab.resolve import RESOLVER_VERSION, build_index
from vocab.schema_check import validate as schema_validate

SCHEMA_PATH = repo_path("schema", "token_dictionary.v2.schema.json")
DEFAULT_ARTIFACT = repo_path("candidate", "token_dictionary.ng.v2.0.json")
BASELINE_PATH = repo_path("token_dictionary.ng.v1.1.json")

CATEGORIES = [
    "symptom_tokens",
    "red_flag_tokens",
    "duration_tokens",
    "body_area_tokens",
    "demographic_tokens",
    "severity_tokens",
]

TOKEN_ID_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")


class Results(object):
    def __init__(self):
        self.checks = []

    def add(self, group, name, passed, detail=""):
        self.checks.append(
            {"group": group, "check": name, "passed": bool(passed), "detail": detail}
        )
        return bool(passed)

    @property
    def failures(self):
        return [c for c in self.checks if not c["passed"]]

    def summary(self):
        return {
            "total": len(self.checks),
            "passed": len(self.checks) - len(self.failures),
            "failed": len(self.failures),
            "all_passed": not self.failures,
        }


def _fmt(values, limit=12):
    values = list(values)
    if not values:
        return "none"
    shown = values[:limit]
    suffix = "" if len(values) <= limit else " (+%d more)" % (len(values) - limit)
    return ", ".join(str(v) for v in shown) + suffix


# --- A. schema conformance -----------------------------------------------------


def check_schema(results, artifact):
    schema = load_json(SCHEMA_PATH)
    errors = schema_validate(artifact, schema)
    results.add("A.schema", "conforms_to_token_dictionary_v2_schema", not errors, _fmt(errors, 20))
    return not errors


# --- B. identity and uniqueness ------------------------------------------------


def check_identity(results, artifact):
    tokens = artifact.get("tokens", [])
    ids = [entry["token_id"] for entry in tokens]

    results.add(
        "B.identity",
        "token_ids_match_stable_id_format",
        all(TOKEN_ID_RE.match(i) for i in ids),
        _fmt([i for i in ids if not TOKEN_ID_RE.match(i)]),
    )

    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    results.add("B.identity", "token_ids_are_unique", not duplicates, _fmt(duplicates))

    # tokens[] and the legacy arrays must describe exactly the same vocabulary.
    legacy_union = set()
    mismatched_category = []
    for category in CATEGORIES:
        members = artifact.get(category, [])
        legacy_union.update(members)
        member_set = set(members)
        for entry in tokens:
            if entry["category"] == category and entry["token_id"] not in member_set:
                mismatched_category.append("%s not in %s" % (entry["token_id"], category))

    results.add(
        "B.identity",
        "tokens_and_legacy_arrays_describe_the_same_set",
        set(ids) == legacy_union,
        "only_in_tokens=%s only_in_legacy=%s"
        % (_fmt(sorted(set(ids) - legacy_union)), _fmt(sorted(legacy_union - set(ids)))),
    )
    results.add(
        "B.identity",
        "each_entry_category_matches_its_legacy_array",
        not mismatched_category,
        _fmt(mismatched_category),
    )

    # Entry order must reproduce the legacy arrays exactly — consumers that read
    # the arrays and consumers that read tokens[] must see the same ordering.
    order_ok = True
    order_detail = []
    for category in CATEGORIES:
        from_tokens = [e["token_id"] for e in tokens if e["category"] == category]
        if from_tokens != list(artifact.get(category, [])):
            order_ok = False
            order_detail.append(category)
    results.add("B.identity", "entry_order_reproduces_legacy_array_order", order_ok, _fmt(order_detail))

    cross = sorted(
        t
        for t in legacy_union
        if sum(1 for c in CATEGORIES if t in artifact.get(c, [])) > 1
    )
    results.add("B.identity", "no_token_in_more_than_one_category", not cross, _fmt(cross))

    declared = artifact.get("_metadata", {}).get("total_tokens")
    results.add(
        "B.identity",
        "metadata_total_tokens_matches_entry_count",
        declared == len(tokens),
        "declared=%r counted=%d" % (declared, len(tokens)),
    )


# --- C. display and search metadata --------------------------------------------


def check_display_and_search(results, artifact):
    tokens = artifact.get("tokens", [])

    missing_label = [e["token_id"] for e in tokens if not e["display"]["canonical_label"].strip()]
    results.add("C.metadata", "canonical_label_present_on_every_entry", not missing_label, _fmt(missing_label))

    bad_whitespace = [
        e["token_id"]
        for e in tokens
        if e["display"]["canonical_label"] != e["display"]["canonical_label"].strip()
        or "\n" in e["display"]["canonical_label"]
        or "\t" in e["display"]["canonical_label"]
        or "  " in e["display"]["canonical_label"]
    ]
    results.add("C.metadata", "canonical_label_whitespace_is_clean", not bad_whitespace, _fmt(bad_whitespace))

    derived_mismatch = [
        e["token_id"]
        for e in tokens
        if e["display"]["label_source"] == "derived_from_token_id"
        and e["display"]["canonical_label"] != derive_label_from_token_id(e["token_id"])
    ]
    results.add(
        "C.metadata",
        "derived_labels_match_their_derivation",
        not derived_mismatch,
        _fmt(derived_mismatch),
    )

    unsafe_claim = [
        e["token_id"]
        for e in tokens
        if e["display"]["display_safe"] and e["display"]["label_review_status"] != "approved"
    ]
    results.add(
        "C.metadata",
        "display_safe_requires_an_approved_label",
        not unsafe_claim,
        _fmt(unsafe_claim),
    )

    approved_without_review = [
        e["token_id"]
        for e in tokens
        if e["display"]["label_review_status"] == "approved"
        and (e["review"]["clinical_reviewer"] is None or e["review"]["review_date"] is None)
    ]
    results.add(
        "C.metadata",
        "approved_labels_carry_reviewer_and_date",
        not approved_without_review,
        _fmt(approved_without_review),
    )

    bad_normalized = [
        e["token_id"]
        for e in tokens
        if e["search"]["normalized_form"] != normalize_token_id(e["token_id"])
    ]
    results.add(
        "C.metadata",
        "normalized_form_is_reproducible",
        not bad_normalized,
        _fmt(bad_normalized),
    )

    not_search_only = [e["token_id"] for e in tokens if e["search"]["search_only"] is not True]
    results.add(
        "C.metadata",
        "search_block_is_marked_search_only",
        not not_search_only,
        _fmt(not_search_only),
    )

    # Alias rules.
    alias_dupes_in_entry = []
    alias_equals_own_canonical = []
    alias_whitespace = []
    alias_unsorted = []
    alias_owner = {}
    for entry in tokens:
        aliases = entry["search"]["aliases"]
        normalized = [normalize(a) for a in aliases]
        if len(set(normalized)) != len(normalized):
            alias_dupes_in_entry.append(entry["token_id"])
        own = {entry["search"]["normalized_form"], normalize(entry["display"]["canonical_label"])}
        if own & set(normalized):
            alias_equals_own_canonical.append(entry["token_id"])
        for alias in aliases:
            if alias != alias.strip() or "\n" in alias or "\t" in alias or "  " in alias:
                alias_whitespace.append("%s:%r" % (entry["token_id"], alias))
        if aliases != sorted(aliases, key=lambda a: (normalize(a), a)):
            alias_unsorted.append(entry["token_id"])
        for alias, form in zip(aliases, normalized):
            alias_owner.setdefault(form, []).append(entry["token_id"])

    results.add(
        "C.metadata",
        "no_duplicate_alias_within_an_entry_after_normalization",
        not alias_dupes_in_entry,
        _fmt(alias_dupes_in_entry),
    )
    results.add(
        "C.metadata",
        "no_alias_equal_to_its_own_canonical_form",
        not alias_equals_own_canonical,
        _fmt(alias_equals_own_canonical),
    )
    results.add("C.metadata", "alias_whitespace_is_clean", not alias_whitespace, _fmt(alias_whitespace))
    results.add("C.metadata", "aliases_are_deterministically_sorted", not alias_unsorted, _fmt(alias_unsorted))

    # An alias colliding with a DIFFERENT token's canonical form is the
    # dangerous case: a user typing the canonical name of token A would get an
    # ambiguity involving token B. Permitted only when deliberate, so it is
    # surfaced loudly rather than silently accepted.
    canonical_forms = {e["search"]["normalized_form"]: e["token_id"] for e in tokens}
    shadowing = sorted(
        "%s shadows canonical %s" % (owner, canonical_forms[form])
        for form, owners in alias_owner.items()
        if form in canonical_forms
        for owner in owners
        if owner != canonical_forms[form]
    )
    results.add(
        "C.metadata",
        "no_alias_shadows_another_tokens_canonical_form",
        not shadowing,
        _fmt(shadowing),
    )


# --- D. references and deprecation ---------------------------------------------


def check_references(results, artifact):
    tokens = artifact.get("tokens", [])
    ids = {e["token_id"] for e in tokens}
    by_id = {e["token_id"]: e for e in tokens}

    body_area_ids = {b["body_area_id"] for b in artifact.get("body_areas", [])}
    group_ids = {g["complaint_group_id"] for g in artifact.get("complaint_groups", [])}
    severity_ids = set(artifact.get("severity_tokens", []))
    duration_ids = set(artifact.get("duration_tokens", []))

    results.add(
        "D.references",
        "body_areas_vocabulary_is_a_subset_of_body_area_tokens",
        body_area_ids <= set(artifact.get("body_area_tokens", [])),
        _fmt(sorted(body_area_ids - set(artifact.get("body_area_tokens", [])))),
    )

    def unresolved(field, valid):
        return sorted(
            "%s -> %s" % (e["token_id"], value)
            for e in tokens
            for value in e["associations"][field]
            if value not in valid
        )

    for field, valid, label in [
        ("body_areas", body_area_ids, "body_area"),
        ("complaint_groups", group_ids, "complaint_group"),
        ("severity_descriptors", severity_ids, "severity_descriptor"),
        ("duration_descriptors", duration_ids, "duration_descriptor"),
    ]:
        bad = unresolved(field, valid)
        results.add("D.references", "valid_%s_references" % label, not bad, _fmt(bad))

    canonical_bad = sorted(
        e["token_id"] for e in tokens if e["clinical_identity"]["canonical_token_id"] not in ids
    )
    results.add("D.references", "canonical_token_id_resolves", not canonical_bad, _fmt(canonical_bad))

    active_with_replacement = sorted(
        e["token_id"]
        for e in tokens
        if e["clinical_identity"]["status"] == "active"
        and e["clinical_identity"]["replaced_by"] is not None
    )
    deprecated_without_replacement = sorted(
        e["token_id"]
        for e in tokens
        if e["clinical_identity"]["status"] == "deprecated"
        and e["clinical_identity"]["replaced_by"] is None
    )
    results.add(
        "D.references",
        "active_tokens_have_no_replacement",
        not active_with_replacement,
        _fmt(active_with_replacement),
    )
    results.add(
        "D.references",
        "deprecated_tokens_name_a_replacement",
        not deprecated_without_replacement,
        _fmt(deprecated_without_replacement),
    )

    unresolved_replacement = sorted(
        "%s -> %s" % (e["token_id"], e["clinical_identity"]["replaced_by"])
        for e in tokens
        if e["clinical_identity"]["replaced_by"] is not None
        and e["clinical_identity"]["replaced_by"] not in ids
    )
    results.add(
        "D.references",
        "replacement_links_resolve",
        not unresolved_replacement,
        _fmt(unresolved_replacement),
    )

    cycles = []
    for start in tokens:
        seen = []
        current = start["token_id"]
        while current is not None and current in by_id:
            if current in seen:
                cycles.append(" -> ".join(seen + [current]))
                break
            seen.append(current)
            current = by_id[current]["clinical_identity"]["replaced_by"]
    results.add("D.references", "no_replacement_cycles", not cycles, _fmt(sorted(set(cycles))))


# --- E. generation determinism and index integrity -----------------------------


def check_generation(results, artifact, artifact_path):
    index = build_index(artifact)
    regenerated = index.normalized_forms()
    stored = artifact.get("search_index", {}).get("normalized_forms", {})
    results.add(
        "E.generation",
        "search_index_is_reproducible_from_tokens",
        regenerated == stored,
        "regenerated %d forms, stored %d" % (len(regenerated), len(stored)),
    )

    search_index = artifact.get("search_index", {})
    results.add(
        "E.generation",
        "search_index_declares_the_tooling_versions_that_built_it",
        search_index.get("normalization_version") == NORMALIZATION_VERSION
        and search_index.get("resolver_version") == RESOLVER_VERSION,
        "normalization=%r expected %r, resolver=%r expected %r"
        % (
            search_index.get("normalization_version"),
            NORMALIZATION_VERSION,
            search_index.get("resolver_version"),
            RESOLVER_VERSION,
        ),
    )

    metadata = artifact.get("_metadata", {})
    filename = os.path.basename(artifact_path)
    expected = "%s.%s.v%s.json" % (
        metadata.get("artifact_id"),
        metadata.get("country"),
        metadata.get("version"),
    )
    results.add(
        "E.generation",
        "filename_matches_internal_artifact_version",
        filename == expected,
        "file=%s expected=%s" % (filename, expected),
    )

    if os.path.exists(artifact_path):
        # Re-serializing the parsed artifact must reproduce the file on disk.
        # That proves the published bytes are canonical, so an independently
        # generated copy hashes identically — and it catches a hand-edit that
        # changed whitespace or key order without changing the data.
        with open(artifact_path, "rb") as handle:
            on_disk = handle.read()
        canonical = dump_artifact_bytes(artifact)
        results.add(
            "E.generation",
            "artifact_bytes_are_canonical_and_hash_reproducibly",
            canonical == on_disk,
            "on_disk sha256:%s canonical sha256:%s"
            % (sha256_bytes(on_disk), sha256_bytes(canonical)),
        )


# --- F. baseline preservation --------------------------------------------------


def check_baseline(results, artifact):
    baseline = load_json(BASELINE_PATH)
    ids = {e["token_id"] for e in artifact.get("tokens", [])}

    removed = []
    recategorized = []
    for category in CATEGORIES:
        for token in baseline.get(category, []):
            if token not in ids:
                removed.append(token)
            elif token not in artifact.get(category, []):
                recategorized.append(token)

    results.add("F.baseline", "no_baseline_token_removed", not removed, _fmt(removed))
    results.add(
        "F.baseline",
        "no_baseline_token_changed_category",
        not recategorized,
        _fmt(recategorized),
    )

    array_mismatch = [c for c in CATEGORIES if artifact.get(c) != baseline.get(c)]
    results.add(
        "F.baseline",
        "legacy_arrays_are_identical_to_the_baseline",
        not array_mismatch,
        _fmt(array_mismatch),
    )

    # "Meaning" of a baseline token, as far as the artifact can express it, is
    # its ID, its category, its position and whether the engine may score it.
    meaning_changed = sorted(
        e["token_id"]
        for e in artifact.get("tokens", [])
        if e["clinical_identity"]["canonical_token_id"] != e["token_id"]
        or e["clinical_identity"]["status"] != "active"
        or e["clinical_identity"]["scoring_eligible"] is not True
    )
    results.add(
        "F.baseline",
        "no_baseline_token_meaning_changed",
        not meaning_changed,
        _fmt(meaning_changed),
    )

    rollback = artifact.get("_metadata", {}).get("rollback_target", {})
    results.add(
        "F.baseline",
        "rollback_target_points_at_the_frozen_baseline",
        rollback.get("file") == "token_dictionary.ng.v1.1.json"
        and rollback.get("sha256") == sha256_file(BASELINE_PATH),
        json.dumps(rollback),
    )

    source = artifact.get("_metadata", {}).get("source_artifact", {})
    results.add(
        "F.baseline",
        "source_artifact_hash_matches_the_file_on_disk",
        source.get("sha256") == sha256_file(BASELINE_PATH),
        "declared=%r actual=%s" % (source.get("sha256"), sha256_file(BASELINE_PATH)),
    )


# --- G. provenance and review honesty ------------------------------------------


def check_provenance(results, artifact):
    tokens = artifact.get("tokens", [])
    metadata = artifact.get("_metadata", {})

    missing_provenance = sorted(
        e["token_id"] for e in tokens if not (e["review"]["provenance"] or "").strip()
    )
    results.add(
        "G.provenance",
        "every_entry_has_provenance",
        not missing_provenance,
        _fmt(missing_provenance),
    )

    half_reviewed = sorted(
        e["token_id"]
        for e in tokens
        if e["review"]["review_status"] == "reviewed"
        and (e["review"]["clinical_reviewer"] is None or e["review"]["review_date"] is None)
    )
    results.add(
        "G.provenance",
        "entry_review_claims_carry_reviewer_and_date",
        not half_reviewed,
        _fmt(half_reviewed),
    )

    review = metadata.get("clinical_review", {})
    claim_ok = review.get("status") != "reviewed" or all(
        review.get(field) for field in ("reviewer", "review_date", "evidence")
    )
    results.add(
        "G.provenance",
        "artifact_review_claim_is_backed_by_evidence",
        claim_ok,
        json.dumps(review),
    )

    results.add(
        "G.provenance",
        "artifact_carries_a_changelog_and_provenance",
        bool(metadata.get("changelog")) and bool(metadata.get("provenance")),
        "changelog=%d provenance=%d"
        % (len(metadata.get("changelog", [])), len(metadata.get("provenance", []))),
    )

    published_claim = metadata.get("release_status") == "published"
    results.add(
        "G.provenance",
        "publication_requires_a_completed_clinical_review",
        (not published_claim) or review.get("status") == "reviewed",
        "release_status=%r clinical_review.status=%r"
        % (metadata.get("release_status"), review.get("status")),
    )


def run(artifact_path, compare_baseline=True):
    results = Results()
    artifact = load_json(artifact_path)

    if check_schema(results, artifact):
        check_identity(results, artifact)
        check_display_and_search(results, artifact)
        check_references(results, artifact)
        check_generation(results, artifact, artifact_path)
        if compare_baseline:
            check_baseline(results, artifact)
        check_provenance(results, artifact)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", nargs="?", default=DEFAULT_ARTIFACT)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="skip baseline comparison — for synthetic schema fixtures that are not migrations",
    )
    args = parser.parse_args()

    results = run(args.artifact, compare_baseline=not args.no_baseline)
    summary = results.summary()

    if args.json:
        print(
            json.dumps(
                {
                    "report_id": "vocabulary_validation",
                    "generator": "tools/validate_vocabulary.py",
                    "generator_version": VOCAB_TOOLING_VERSION,
                    "artifact": os.path.relpath(args.artifact, repo_path()),
                    "artifact_sha256": sha256_file(args.artifact),
                    "baseline_comparison": not args.no_baseline,
                    "summary": summary,
                    "checks": results.checks,
                },
                indent=2,
            )
        )
    else:
        for check in results.checks:
            print(
                "%-4s %-8s %s%s"
                % (
                    "OK" if check["passed"] else "FAIL",
                    check["group"],
                    check["check"],
                    "" if check["passed"] else "  [%s]" % check["detail"],
                )
            )
        print(
            "\n%d checks, %d passed, %d failed"
            % (summary["total"], summary["passed"], summary["failed"])
        )

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
