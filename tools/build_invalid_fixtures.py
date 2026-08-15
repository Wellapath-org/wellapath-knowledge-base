#!/usr/bin/env python3
"""Generate invalid-artifact fixtures, one defect each.

    python3 tools/build_invalid_fixtures.py            # write the fixtures
    python3 tools/build_invalid_fixtures.py --check    # fail if they are stale

Each fixture is the synthetic non-clinical vocabulary with exactly one mutation
applied, so a test that expects a specific validator check to fail is really
testing that check and not some incidental breakage. Building them from the
synthetic base (5 nonsense tokens) rather than the real 295-token candidate
keeps them small, readable in a diff, and impossible to mistake for clinical
content.

Every fixture carries `_metadata.SYNTHETIC_FIXTURE: true` and an
`_metadata.EXPECTED_FAILURE` naming the validator check it must trip.
"""

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import dump_report_bytes, repo_path, write_bytes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_search_fixtures import synthetic_vocabulary  # noqa: E402

FIXTURE_DIR = repo_path("testing", "vocabulary", "fixtures", "invalid")


def base():
    return copy.deepcopy(synthetic_vocabulary())


def _entry(artifact, token_id):
    return next(e for e in artifact["tokens"] if e["token_id"] == token_id)


def duplicate_token_id():
    # The duplicate is added to tokens[] only, NOT to the legacy array. The
    # legacy arrays already carry uniqueItems in the JSON Schema, so duplicating
    # there would trip the schema layer and never exercise the identity check.
    # tokens[] has no such schema-level guard, which is precisely why
    # B.identity:token_ids_are_unique exists.
    artifact = base()
    artifact["tokens"].append(copy.deepcopy(_entry(artifact, "frobnitz")))
    artifact["_metadata"]["total_tokens"] = len(artifact["tokens"])
    return artifact, "B.identity:token_ids_are_unique"


def malformed_token_id():
    artifact = base()
    entry = _entry(artifact, "frobnitz")
    entry["token_id"] = "Frobnitz-Bad ID"
    entry["clinical_identity"]["canonical_token_id"] = "Frobnitz-Bad ID"
    artifact["symptom_tokens"] = [
        "Frobnitz-Bad ID" if t == "frobnitz" else t for t in artifact["symptom_tokens"]
    ]
    return artifact, "A.schema:conforms_to_token_dictionary_v2_schema"


def missing_canonical_label():
    artifact = base()
    _entry(artifact, "frobnitz")["display"]["canonical_label"] = ""
    return artifact, "A.schema:conforms_to_token_dictionary_v2_schema"


def alias_equals_own_canonical():
    artifact = base()
    entry = _entry(artifact, "frobnitz")
    entry["search"]["aliases"] = sorted(entry["search"]["aliases"] + ["Frobnitz"])
    return artifact, "C.metadata:no_alias_equal_to_its_own_canonical_form"


def duplicate_alias_within_entry():
    artifact = base()
    entry = _entry(artifact, "frobnitz")
    entry["search"]["aliases"] = ["frob nitz", "FROB  NITZ"]
    return artifact, "C.metadata:no_duplicate_alias_within_an_entry_after_normalization"


def alias_shadows_another_canonical():
    artifact = base()
    _entry(artifact, "frobnitz")["search"]["aliases"] = ["zorble alpha"]
    return artifact, "C.metadata:no_alias_shadows_another_tokens_canonical_form"


def unresolvable_body_area():
    artifact = base()
    _entry(artifact, "frobnitz")["associations"]["body_areas"] = ["not_a_body_area"]
    return artifact, "D.references:valid_body_area_references"


def unresolvable_complaint_group():
    artifact = base()
    _entry(artifact, "frobnitz")["associations"]["complaint_groups"] = ["not_a_group"]
    return artifact, "D.references:valid_complaint_group_references"


def deprecated_without_replacement():
    artifact = base()
    _entry(artifact, "frobnitz")["clinical_identity"]["status"] = "deprecated"
    return artifact, "D.references:deprecated_tokens_name_a_replacement"


def replacement_cycle():
    artifact = base()
    alpha = _entry(artifact, "zorble_alpha")
    beta = _entry(artifact, "zorble_beta")
    alpha["clinical_identity"]["status"] = "deprecated"
    alpha["clinical_identity"]["replaced_by"] = "zorble_beta"
    beta["clinical_identity"]["status"] = "deprecated"
    beta["clinical_identity"]["replaced_by"] = "zorble_alpha"
    return artifact, "D.references:no_replacement_cycles"


def unresolvable_replacement():
    artifact = base()
    entry = _entry(artifact, "frobnitz")
    entry["clinical_identity"]["status"] = "deprecated"
    entry["clinical_identity"]["replaced_by"] = "does_not_exist"
    return artifact, "D.references:replacement_links_resolve"


def stale_search_index():
    artifact = base()
    artifact["search_index"]["normalized_forms"]["frobnitz"] = ["zorble_alpha"]
    return artifact, "E.generation:search_index_is_reproducible_from_tokens"


def tokens_disagree_with_legacy_arrays():
    artifact = base()
    artifact["symptom_tokens"] = [t for t in artifact["symptom_tokens"] if t != "frobnitz"]
    return artifact, "B.identity:tokens_and_legacy_arrays_describe_the_same_set"


def legacy_order_changed():
    artifact = base()
    artifact["symptom_tokens"] = list(reversed(artifact["symptom_tokens"]))
    return artifact, "B.identity:entry_order_reproduces_legacy_array_order"


def display_safe_without_approval():
    artifact = base()
    entry = _entry(artifact, "frobnitz")
    entry["display"]["label_review_status"] = "unreviewed"
    entry["display"]["display_safe"] = True
    return artifact, "C.metadata:display_safe_requires_an_approved_label"


def review_claim_without_evidence():
    artifact = base()
    artifact["_metadata"]["clinical_review"] = {
        "status": "reviewed",
        "reviewer": None,
        "review_date": None,
        "evidence": None,
    }
    return artifact, "G.provenance:artifact_review_claim_is_backed_by_evidence"


def published_without_review():
    artifact = base()
    artifact["_metadata"]["release_status"] = "published"
    return artifact, "G.provenance:publication_requires_a_completed_clinical_review"


def missing_provenance():
    artifact = base()
    _entry(artifact, "frobnitz")["review"]["provenance"] = "   "
    return artifact, "G.provenance:every_entry_has_provenance"


def unknown_top_level_key():
    artifact = base()
    artifact["surprise_key"] = {"unexpected": True}
    return artifact, "A.schema:conforms_to_token_dictionary_v2_schema"


def wrong_schema_version():
    artifact = base()
    artifact["_metadata"]["schema_version"] = "1.0"
    return artifact, "A.schema:conforms_to_token_dictionary_v2_schema"


def search_not_marked_search_only():
    artifact = base()
    _entry(artifact, "frobnitz")["search"]["search_only"] = False
    return artifact, "A.schema:conforms_to_token_dictionary_v2_schema"


FIXTURES = [
    ("duplicate_token_id", duplicate_token_id),
    ("malformed_token_id", malformed_token_id),
    ("missing_canonical_label", missing_canonical_label),
    ("alias_equals_own_canonical", alias_equals_own_canonical),
    ("duplicate_alias_within_entry", duplicate_alias_within_entry),
    ("alias_shadows_another_canonical", alias_shadows_another_canonical),
    ("unresolvable_body_area", unresolvable_body_area),
    ("unresolvable_complaint_group", unresolvable_complaint_group),
    ("deprecated_without_replacement", deprecated_without_replacement),
    ("replacement_cycle", replacement_cycle),
    ("unresolvable_replacement", unresolvable_replacement),
    ("stale_search_index", stale_search_index),
    ("tokens_disagree_with_legacy_arrays", tokens_disagree_with_legacy_arrays),
    ("legacy_order_changed", legacy_order_changed),
    ("display_safe_without_approval", display_safe_without_approval),
    ("review_claim_without_evidence", review_claim_without_evidence),
    ("published_without_review", published_without_review),
    ("missing_provenance", missing_provenance),
    ("unknown_top_level_key", unknown_top_level_key),
    ("wrong_schema_version", wrong_schema_version),
    ("search_not_marked_search_only", search_not_marked_search_only),
]


def build():
    built = []
    for name, factory in FIXTURES:
        artifact, expected_check = factory()
        artifact["_metadata"]["EXPECTED_FAILURE"] = expected_check
        artifact["_metadata"]["FIXTURE_NAME"] = name
        built.append((os.path.join(FIXTURE_DIR, "%s.json" % name), artifact, expected_check))
    return built


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    index = {
        "fixture_id": "vocabulary_invalid_fixtures",
        "fixture_version": "1",
        "synthetic": True,
        "WARNING": "SYNTHETIC NON-CLINICAL FIXTURES. Each file is the synthetic vocabulary with exactly one defect. None may be published or used as a source of vocabulary.",
        "fixtures": [
            {"file": "%s.json" % name, "expected_failing_check": factory()[1]}
            for name, factory in FIXTURES
        ],
    }

    targets = [(os.path.join(FIXTURE_DIR, "index.json"), index)]
    targets += [(path, artifact) for path, artifact, _ in build()]

    for path, payload in targets:
        data = dump_report_bytes(payload)
        relative = os.path.relpath(path, repo_path())
        if args.check:
            if not os.path.exists(path) or open(path, "rb").read() != data:
                print("FAIL %s is missing or stale" % relative)
                return 1
        else:
            write_bytes(path, data)

    if args.check:
        print("OK   invalid fixtures are current (%d)" % len(FIXTURES))
    else:
        print("wrote %d invalid fixtures to %s" % (len(FIXTURES), os.path.relpath(FIXTURE_DIR, repo_path())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
