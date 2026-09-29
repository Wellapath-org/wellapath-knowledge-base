#!/usr/bin/env python3
"""Migrate token_dictionary 1.1 to the schema 2.0 candidate artifact.

    python3 tools/build_vocabulary_v2.py                       # build the candidate
    python3 tools/build_vocabulary_v2.py --check               # fail if committed output is stale
    python3 tools/build_vocabulary_v2.py --generated-at <ts>   # pin the timestamp

Guarantees, each enforced by a test:

  * Lossless — every token ID, its category and its position survive. The
    downgrade projection (`project_to_v1_1`) rebuilds the source file from the
    new `tokens` array alone and must match token_dictionary.ng.v1.1.json byte
    for byte.
  * Deterministic — two runs with the same inputs and the same
    `--generated-at` produce identical bytes and therefore an identical SHA256.
  * Additive only — no field of the source is dropped, reordered or reworded.
  * Invents nothing — aliases, body-area associations, complaint groups,
    severity/duration descriptors and reviewer metadata are all left empty. No
    approved catalogue for any of them exists in this repository, and
    fabricating one would put unreviewed clinical content into an artifact.

The one derived value is `display.canonical_label`, produced mechanically from
the token ID. Every such label is stamped `label_source:
"derived_from_token_id"`, `label_review_status: "unreviewed"` and
`display_safe: false`, so no consumer may put it in front of a patient.
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
    write_bytes,
)
from vocab.normalize import NORMALIZATION_VERSION, derive_label_from_token_id, normalize_token_id
from vocab.resolve import RESOLVER_VERSION, build_index

GENERATOR = "tools/build_vocabulary_v2.py"
GENERATOR_VERSION = "1.0.0"

SOURCE_FILE = "token_dictionary.ng.v1.1.json"
PREVIOUS_FILE = "token_dictionary.ng.v1.0.json"
CANDIDATE_PATH = repo_path("candidate", "token_dictionary.ng.v2.0.json")

ARTIFACT_ID = "token_dictionary"
CANDIDATE_VERSION = "2.0"
SCHEMA_VERSION = "2.0"

# Fixed generation timestamp so the committed candidate is reproducible. Passing
# --generated-at overrides it; omitting it keeps the artifact byte-stable across
# rebuilds, which is what makes the hash meaningful.
DEFAULT_GENERATED_AT = "2026-08-14T00:00:00Z"

CATEGORIES = [
    "symptom_tokens",
    "red_flag_tokens",
    "duration_tokens",
    "body_area_tokens",
    "demographic_tokens",
    "severity_tokens",
]

CHANGELOG = [
    "Schema 2.0: added per-token entries under `tokens`, separating clinical identity from search and display metadata.",
    "Schema 2.0: added `body_areas` and `complaint_groups` controlled vocabularies. body_areas is derived from the existing body_area_tokens; complaint_groups is empty pending an approved catalogue.",
    "Schema 2.0: added `search_index.normalized_forms`, generated from `tokens` so every consumer resolves identically offline.",
    "Migration: all 295 token IDs from 1.1 preserved, in category and in order. No token renamed, merged, removed or deprecated.",
    "Migration: the six schema 1.0 token arrays are carried forward unchanged so schema 1.0 consumers keep working without a code change.",
    "Migration: no alias, body-area association, complaint group, severity descriptor, duration descriptor or reviewer value was invented. All are empty or null.",
    "Migration: `display.canonical_label` is mechanically derived from the token ID and marked unreviewed and not display-safe.",
    "Not published. release_status is candidate_unapproved and the live /config manifest is unchanged.",
]


def load_introduced_versions():
    """Determine which artifact version first carried each token.

    Derived by diffing the two published token dictionaries. Evidence-based —
    tokens present in 1.0 are stamped 1.0, tokens that first appear in 1.1 are
    stamped 1.1. Nothing is guessed.
    """
    previous_path = repo_path(PREVIOUS_FILE)
    if not os.path.exists(previous_path):
        raise SystemExit(
            "%s is required to derive introduced_in_artifact_version and is missing" % PREVIOUS_FILE
        )
    previous = load_json(previous_path)
    in_v1_0 = set()
    for category in CATEGORIES:
        in_v1_0.update(previous.get(category, []))
    return in_v1_0


def build_token_entry(token_id, category, in_v1_0, source_sha256):
    return {
        "token_id": token_id,
        "category": category,
        "clinical_identity": {
            "canonical_token_id": token_id,
            "status": "active",
            "replaced_by": None,
            "scoring_eligible": True,
            "introduced_in_artifact_version": "1.0" if token_id in in_v1_0 else "1.1",
        },
        "display": {
            "canonical_label": derive_label_from_token_id(token_id),
            "label_source": "derived_from_token_id",
            "label_review_status": "unreviewed",
            "display_safe": False,
            "locale": "en-NG",
        },
        "search": {
            "normalized_form": normalize_token_id(token_id),
            "aliases": [],
            "search_only": True,
        },
        "associations": {
            "body_areas": [],
            "complaint_groups": [],
            "severity_descriptors": [],
            "duration_descriptors": [],
        },
        "review": {
            "review_status": "not_reviewed",
            "clinical_reviewer": None,
            "review_date": None,
            "provenance": "migrated_from_%s (sha256:%s)" % (SOURCE_FILE, source_sha256[:16]),
        },
    }


def build_candidate(generated_at):
    source_path = repo_path(SOURCE_FILE)
    source = load_json(source_path)
    source_sha256 = sha256_file(source_path)
    in_v1_0 = load_introduced_versions()

    tokens = []
    for category in CATEGORIES:
        for token_id in source.get(category, []):
            tokens.append(build_token_entry(token_id, category, in_v1_0, source_sha256))

    body_areas = [
        {
            "body_area_id": token_id,
            "canonical_label": derive_label_from_token_id(token_id),
            "label_source": "derived_from_token_id",
            "display_safe": False,
        }
        for token_id in source.get("body_area_tokens", [])
    ]

    artifact = {
        "_metadata": {
            "artifact_id": ARTIFACT_ID,
            "version": CANDIDATE_VERSION,
            "country": source["_metadata"]["country"],
            "schema_version": SCHEMA_VERSION,
            "release_status": "candidate_unapproved",
            "release_date": None,
            "generated_at": generated_at,
            "generator": GENERATOR,
            "generator_version": GENERATOR_VERSION,
            "tooling_version": VOCAB_TOOLING_VERSION,
            "description": (
                "WellaPath Nigeria CDSS - Symptom Vocabulary 2.0 CANDIDATE. Lossless migration of "
                "token_dictionary 1.1 to schema 2.0. Not published, not clinically approved, not "
                "referenced by any live manifest."
            ),
            "source_artifact": {
                "artifact_id": ARTIFACT_ID,
                "version": source["_metadata"]["version"],
                "file": SOURCE_FILE,
                "sha256": source_sha256,
            },
            "rollback_target": {
                "artifact_id": ARTIFACT_ID,
                "version": source["_metadata"]["version"],
                "file": SOURCE_FILE,
                "sha256": source_sha256,
            },
            "compatible_consumers": {
                "knowledge_base": ["2.4"],
                "rules": ["2.2"],
            },
            "legacy_metadata": source["_metadata"],
            "clinical_review": {
                "status": "not_reviewed",
                "reviewer": None,
                "review_date": None,
                "evidence": None,
            },
            "total_tokens": len(tokens),
            "changelog": CHANGELOG,
            "provenance": [
                "Source: %s (sha256:%s), the artifact frozen for internal beta at E9.1."
                % (SOURCE_FILE, source_sha256),
                "introduced_in_artifact_version derived by diffing %s against %s."
                % (PREVIOUS_FILE, SOURCE_FILE),
                "No external vocabulary, alias list or clinical catalogue was consulted or imported.",
                "No PHI and no real-user assessment data is present: this artifact contains only "
                "token identifiers already published in %s." % SOURCE_FILE,
            ],
        },
    }

    # Legacy compatibility surface, carried through verbatim.
    for category in CATEGORIES:
        artifact[category] = list(source.get(category, []))

    artifact["body_areas"] = body_areas
    artifact["complaint_groups"] = []
    artifact["tokens"] = tokens

    index = build_index(artifact)
    artifact["search_index"] = {
        "normalization_version": NORMALIZATION_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "normalized_forms": index.normalized_forms(),
    }

    return artifact


def project_to_v1_1(candidate):
    """Rebuild the schema 1.0 source artifact from the candidate.

    The six token arrays are rebuilt from `tokens` — NOT copied from the
    candidate's own legacy arrays — so a passing comparison proves that
    `tokens` losslessly encodes the source. `_metadata` comes from the verbatim
    `legacy_metadata` block.
    """
    projected = {"_metadata": candidate["_metadata"]["legacy_metadata"]}
    for category in CATEGORIES:
        projected[category] = [
            entry["token_id"] for entry in candidate["tokens"] if entry["category"] == category
        ]
    return projected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed candidate is stale")
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    args = parser.parse_args()

    candidate = build_candidate(args.generated_at)
    payload = dump_artifact_bytes(candidate)

    # Losslessness is asserted at build time, not only in the test suite: a
    # candidate that fails the projection must never reach disk.
    projected = dump_artifact_bytes(project_to_v1_1(candidate))
    with open(repo_path(SOURCE_FILE), "rb") as handle:
        original = handle.read()
    if projected != original:
        print("FAIL downgrade projection does not reproduce %s byte for byte" % SOURCE_FILE)
        return 1

    if args.check:
        if not os.path.exists(CANDIDATE_PATH):
            print("FAIL candidate/token_dictionary.ng.v2.0.json is missing")
            return 1
        with open(CANDIDATE_PATH, "rb") as handle:
            committed = handle.read()
        if committed != payload:
            print(
                "FAIL candidate is stale — committed sha256:%s, rebuilt sha256:%s"
                % (sha256_bytes(committed), sha256_bytes(payload))
            )
            return 1
        print("OK   candidate is reproducible, sha256:%s" % sha256_bytes(payload))
        return 0

    write_bytes(CANDIDATE_PATH, payload)
    print("wrote candidate/token_dictionary.ng.v2.0.json")
    print("  tokens:  %d" % len(candidate["tokens"]))
    print("  bytes:   %d" % len(payload))
    print("  sha256:  %s" % sha256_bytes(payload))
    print("  status:  %s" % candidate["_metadata"]["release_status"])
    print("  lossless downgrade projection to %s: OK" % SOURCE_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
