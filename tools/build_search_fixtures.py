#!/usr/bin/env python3
"""Generate the search-behaviour fixture package.

    python3 tools/build_search_fixtures.py            # write the fixtures
    python3 tools/build_search_fixtures.py --check    # fail if they are stale

Two fixture files are produced:

  testing/vocabulary/fixtures/search/search_cases_v1.json
      Queries against the REAL candidate vocabulary. Every query is built from
      vocabulary that already exists — a token ID, or a mechanical variation of
      one (case, whitespace, punctuation, Unicode). No clinically meaningful
      synonym is invented: a made-up mapping like "belly ache" -> abdominal_pain
      would be an unreviewed clinical claim dressed up as test coverage.

  testing/vocabulary/fixtures/search/ambiguity_cases_v1.json
      Queries against a clearly labelled SYNTHETIC vocabulary whose tokens are
      not clinical content. Real ambiguity cannot be demonstrated against the
      real vocabulary because it currently has zero label collisions and zero
      aliases — so the ambiguity contract is exercised against a fixture that
      is explicitly marked non-clinical and never enters a release artifact.

Expected values are computed by the reference resolver, which makes these
regression fixtures: they lock in current behaviour so a future change to
normalization or ordering has to be deliberate.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes
from vocab.normalize import NORMALIZATION_VERSION, normalize
from vocab.resolve import RESOLVER_VERSION, build_index

CANDIDATE = repo_path("candidate", "token_dictionary.ng.v2.0.json")
SEARCH_PATH = repo_path("testing", "vocabulary", "fixtures", "search", "search_cases_v1.json")
AMBIGUITY_PATH = repo_path("testing", "vocabulary", "fixtures", "search", "ambiguity_cases_v1.json")
SYNTHETIC_PATH = repo_path("testing", "vocabulary", "fixtures", "search", "synthetic_vocabulary_v1.json")


def real_queries():
    """Queries derived mechanically from existing vocabulary.

    Each entry is (query, why). The `why` string is what the fixture is
    actually testing, so a failure report says something useful.
    """
    return [
        ("chest_pain", "exact canonical: the stable token ID itself"),
        ("fever", "exact canonical: single-word token ID"),
        ("severe_malnutrition_sam", "exact canonical: token added in artifact version 1.1"),
        ("Chest Pain", "case + separator normalization of an existing token ID"),
        ("CHEST PAIN", "upper case normalization"),
        ("chest pain", "underscore-to-space normalization"),
        ("  chest   pain  ", "leading, trailing and repeated whitespace"),
        ("chest-pain", "ASCII hyphen folds to a space"),
        ("chest—pain", "em dash folds to a space"),
        ("chest–pain", "en dash folds to a space"),
        ("chest.pain", "a full stop not between digits folds to a space"),
        ("chest, pain", "comma not between digits folds to a space"),
        ("chest pain!", "trailing punctuation is dropped"),
        ("(chest pain)", "surrounding punctuation is dropped"),
        ("chest pain", "no-break space folds to an ASCII space"),
        ("chest​pain", "zero width space folds to a space separator"),
        ("﻿chest pain", "byte order mark is stripped"),
        ("ChEsT_pAiN", "mixed case on the ID form"),
        ("blood_in_stool", "exact canonical: multi-word token ID"),
        ("blood in stool", "normalized form of a multi-word token ID"),
        ("no fever", "negation is preserved and must NOT resolve to `fever`"),
        ("not fever", "negation variant must NOT resolve to `fever`"),
        ("fever and chills", "a multi-token phrase must NOT partially match a single token"),
        ("feve", "a prefix of a real token must NOT match — no fuzzy matching"),
        ("fevers", "a plural of a real token must NOT match — no stemming"),
        ("fver", "a typo must NOT match — no edit-distance matching"),
        ("chestpain", "removing the separator must NOT match — hyphens become spaces, not nothing"),
        ("", "empty query"),
        ("   ", "whitespace-only query"),
        ("!!!", "punctuation-only query"),
        ("zzzznotatoken", "unknown term"),
        ("38.5", "a decimal number survives normalization and matches nothing"),
        ("140/90", "a digit-internal solidus survives and matches nothing"),
        ("1,000", "a thousands separator is removed and matches nothing"),
    ]


def synthetic_vocabulary():
    """A deliberately non-clinical vocabulary for exercising ambiguity.

    Token IDs are nonsense words. Nothing here resembles a symptom, and the
    artifact carries loud markers so it can never be mistaken for release
    content.
    """
    def entry(token_id, category, label, aliases):
        return {
            "token_id": token_id,
            "category": category,
            "clinical_identity": {
                "canonical_token_id": token_id,
                "status": "active",
                "replaced_by": None,
                "scoring_eligible": True,
                "introduced_in_artifact_version": "1.0",
            },
            "display": {
                "canonical_label": label,
                "label_source": "clinically_approved",
                "label_review_status": "approved",
                "display_safe": True,
                "locale": "en-NG",
            },
            "search": {
                "normalized_form": normalize(token_id.replace("_", " ")),
                "aliases": sorted(aliases, key=lambda a: (normalize(a), a)),
                "search_only": True,
            },
            "associations": {
                "body_areas": [],
                "complaint_groups": [],
                "severity_descriptors": [],
                "duration_descriptors": [],
            },
            "review": {
                "review_status": "reviewed",
                "clinical_reviewer": "SYNTHETIC FIXTURE - NOT A REAL REVIEWER",
                "review_date": "2026-01-01",
                "provenance": "synthetic non-clinical schema fixture",
            },
        }

    tokens = [
        # Two tokens sharing one alias -> ambiguous on that alias.
        entry("zorble_alpha", "symptom_tokens", "Zorble alpha", ["shared quux"]),
        entry("zorble_beta", "symptom_tokens", "Zorble beta", ["shared quux", "beta only"]),
        # A token whose canonical label normalizes to another token's ID form.
        entry("plaxo_thing", "symptom_tokens", "Quibble widget", []),
        entry("quibble_widget", "red_flag_tokens", "Quibble widget", []),
        # An unambiguous alias.
        entry("frobnitz", "symptom_tokens", "Frobnitz", ["frob nitz", "FROBNITZ!"]),
    ]

    artifact = {
        "_metadata": {
            "artifact_id": "token_dictionary",
            "version": "0.0",
            "country": "ng",
            "schema_version": "2.0",
            "release_status": "candidate_unapproved",
            "release_date": None,
            "generated_at": "2026-08-14T00:00:00Z",
            "generator": "tools/build_search_fixtures.py",
            "generator_version": VOCAB_TOOLING_VERSION,
            "SYNTHETIC_FIXTURE": True,
            "WARNING": "SYNTHETIC NON-CLINICAL TEST FIXTURE. Token IDs are nonsense words. This file must never be published, uploaded to R2, referenced by a manifest, or used as a source of clinical vocabulary.",
            "description": "Synthetic vocabulary used only to exercise the ambiguity contract, which the real vocabulary cannot currently demonstrate (it has zero label collisions and zero aliases).",
            "source_artifact": {
                "artifact_id": "token_dictionary",
                "version": "0.0",
                "file": "none - synthetic",
                "sha256": "0" * 64,
            },
            "rollback_target": {
                "artifact_id": "token_dictionary",
                "version": "0.0",
                "file": "none - synthetic",
                "sha256": "0" * 64,
            },
            "compatible_consumers": {},
            "clinical_review": {
                "status": "not_reviewed",
                "reviewer": None,
                "review_date": None,
                "evidence": None,
            },
            "total_tokens": len(tokens),
            "changelog": ["Synthetic fixture. Not a release artifact."],
            "provenance": ["Generated by tools/build_search_fixtures.py. Contains no clinical content."],
        },
        "symptom_tokens": [t["token_id"] for t in tokens if t["category"] == "symptom_tokens"],
        "red_flag_tokens": [t["token_id"] for t in tokens if t["category"] == "red_flag_tokens"],
        "duration_tokens": [],
        "body_area_tokens": [],
        "demographic_tokens": [],
        "severity_tokens": [],
        "body_areas": [],
        "complaint_groups": [],
        "tokens": tokens,
    }
    index = build_index(artifact)
    artifact["search_index"] = {
        "normalization_version": NORMALIZATION_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "normalized_forms": index.normalized_forms(),
    }
    return artifact


def expectation(index, query, why):
    result = index.resolve(query)
    return {
        "query": query,
        "tests": why,
        "expected": {
            "status": result["status"],
            "query_normalized": result["query_normalized"],
            "resolved_token_id": result["resolved_token_id"],
            "scoring_eligible": result["scoring_eligible"],
            "candidate_token_ids": [c["token_id"] for c in result["candidates"]],
        },
    }


def build_search_fixture():
    candidate = load_json(CANDIDATE)
    index = build_index(candidate)
    return {
        "fixture_id": "vocabulary_search_cases",
        "fixture_version": "1",
        "generator": "tools/build_search_fixtures.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "synthetic": False,
        "vocabulary": {
            "file": "candidate/token_dictionary.ng.v2.0.json",
            "version": candidate["_metadata"]["version"],
            "sha256": sha256_file(CANDIDATE),
        },
        "normalization_version": NORMALIZATION_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "authoring_rule": "Every query is an existing token ID or a mechanical variation of one (case, whitespace, punctuation, Unicode). No clinically meaningful synonym mapping is invented to pad coverage.",
        "cases": [expectation(index, query, why) for query, why in real_queries()],
    }


def build_ambiguity_fixture():
    artifact = synthetic_vocabulary()
    index = build_index(artifact)
    queries = [
        ("shared quux", "exact alias shared by two tokens -> ambiguous, resolves to nothing"),
        ("SHARED  QUUX!", "the same collision reached through normalization"),
        ("beta only", "exact alias unique to one token -> exact_alias"),
        ("quibble widget", "one token's canonical label collides with another token's ID form -> ambiguous"),
        ("quibble_widget", "the exact token ID wins over the colliding label -> exact_canonical"),
        ("frobnitz", "exact canonical"),
        ("frob nitz", "exact alias"),
        ("FROBNITZ!", "exact alias reached byte-for-byte before normalization"),
        ("frobnitz!", "normalized alias match"),
        ("zorble_alpha", "exact canonical beats a shared alias"),
        ("nothing here", "no match"),
    ]
    return {
        "fixture_id": "vocabulary_ambiguity_cases",
        "fixture_version": "1",
        "generator": "tools/build_search_fixtures.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "synthetic": True,
        "WARNING": "Expectations are computed against a SYNTHETIC non-clinical vocabulary (synthetic_vocabulary_v1.json). No token here is clinical content.",
        "vocabulary": {"file": "testing/vocabulary/fixtures/search/synthetic_vocabulary_v1.json"},
        "normalization_version": NORMALIZATION_VERSION,
        "resolver_version": RESOLVER_VERSION,
        "cases": [expectation(index, query, why) for query, why in queries],
    }


def outputs():
    return [
        (SYNTHETIC_PATH, synthetic_vocabulary()),
        (SEARCH_PATH, build_search_fixture()),
        (AMBIGUITY_PATH, build_ambiguity_fixture()),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    for path, payload in outputs():
        data = dump_report_bytes(payload)
        relative = os.path.relpath(path, repo_path())
        if args.check:
            if not os.path.exists(path) or open(path, "rb").read() != data:
                print("FAIL %s is missing or stale" % relative)
                return 1
        else:
            write_bytes(path, data)
            print("wrote %s" % relative)

    if args.check:
        print("OK   search fixtures are current")
    return 0


if __name__ == "__main__":
    sys.exit(main())
