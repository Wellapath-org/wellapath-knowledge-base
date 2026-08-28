#!/usr/bin/env python3
"""Build the publication fixtures: cross-repository compatibility cases and KB-stage negatives.

    python3 tools/build_publication_fixtures.py           # write
    python3 tools/build_publication_fixtures.py --check    # fail if the committed copies differ

Writes:

    publication/fixtures/compat/kb_baseline.manifest.json
    publication/fixtures/compat/kb_blocked_candidates.manifest.json
    publication/fixtures/compat/negative_fixtures.compat.json
    publication/fixtures/negative/kb_stage_fixtures_v1.json

**The compat fixtures are written in the Backend's own fixture format** — the same `base` /
`target` / `context` / `cases` shape as `wellapath-backend/tests/fixtures/manifest/
negative-fixtures.json`, with the same `manifest_overrides`, `descriptor_overrides`,
`remove_descriptor_fields`, `other_descriptor_overrides`, `append_duplicate_of_target` and
`bytes_utf8` keys, and the same `stage` / `expected_code` vocabulary. That is deliberate: a
fixture set only proves two implementations agree if both can actually run it. These files are
data, not Python, and the Backend's existing runner can execute them unchanged.

**The baseline is synthetic on purpose, and obviously so.** Its `artifact_id` is
`fixture_artifact`, which is not and will never be a real artifact, while its hashes and byte
counts are the *real* digests of real repository files — so integrity cases are exercised
against bytes that actually exist rather than against invented digests. A baseline built on a
real artifact identity with approvals granted would be a file that reads like an approval
record, and this repository has enough of those to not want a convincing fake among them.

**`kb_blocked_candidates.manifest.json` is the real one.** It carries Vocabulary 2.0 and
Question Flow 1.1 with their true identities, their true hashes over the real candidate bytes,
and their true governance — which is to say, nothing granted and two blockers open. It is the
KB's counterpart to the Backend's `blocked-candidates.manifest.json`, which had to use
placeholder digests because the Backend has no access to these bytes.

Standard library only, no network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pubkit import inventory
from pubkit.plan import PLAN_EVALUATION_INSTANT
from vocab.artifact_io import dump_report_bytes, repo_path, write_bytes

COMPAT_DIR = repo_path("publication", "fixtures", "compat")
NEGATIVE_DIR = repo_path("publication", "fixtures", "negative")

FIXTURE_WARNING = (
    "SYNTHETIC FIXTURE — artifact_id 'fixture_artifact' is not a real artifact and never will "
    "be. Its governance fields are fixture values chosen so negative cases have something valid "
    "to break; they record no decision anyone made. Its sha256 and byte_count are the real "
    "digests of real repository files so integrity cases run against bytes that exist. This "
    "descriptor names no object, must never reach a live manifest, and grants nothing."
)


def _fixture_descriptor(version, entry, overrides=None):
    """A structurally valid, fully-approved descriptor for the synthetic fixture artifact."""
    descriptor = {
        "artifact_id": "fixture_artifact",
        "artifact_version": version,
        "schema_version": "wellapath.artifact/1",
        "content_type": "application/json",
        "sha256": entry["descriptor_sha256"],
        "byte_count": entry["byte_count"],
        "object_key": "fixture_artifact.ng.v%s.json" % version,
        "release_status": "published",
        "activation_status": "active",
        "activation_authorized": True,
        "activation_decision_ref": "FIXTURE-ACTIVATION-0001 (synthetic)",
        "target_environments": ["staging"],
        "publication_decision_ref": "FIXTURE-PUBLICATION-0001 (synthetic)",
        "approvals": {
            "product": {
                "required": True,
                "status": "granted",
                "decision_ref": "FIXTURE-PRODUCT-0001 (synthetic)",
                "approved_at": "2026-08-01T00:00:00Z",
            },
            "clinical": {
                "required": True,
                "status": "granted",
                "decision_ref": "FIXTURE-CLINICAL-0001 (synthetic)",
                "approved_at": "2026-08-01T00:00:00Z",
            },
        },
        "blockers": [],
        "predecessor": None,
        "rollback_target": None,
        "created_at": "2026-08-01T00:00:00Z",
        "published_at": "2026-08-01T00:00:00Z",
        "deprecated": False,
        "expires_at": None,
        "country": "ng",
        "references": [FIXTURE_WARNING, "bytes borrowed from %s" % entry["repository_path"]],
    }
    if overrides:
        descriptor.update(overrides)
    return descriptor


def build_baseline(entries):
    """A valid manifest: two versions of one synthetic artifact, the newer active."""
    older = inventory.find(entries, "token_dictionary", "1.0")
    newer = inventory.find(entries, "token_dictionary", "1.1")

    predecessor = _fixture_descriptor(
        "1.0",
        older,
        {
            "release_status": "deprecated",
            "activation_status": "inactive",
            "activation_authorized": False,
            "activation_decision_ref": None,
            "deprecated": True,
        },
    )
    current = _fixture_descriptor(
        "1.1",
        newer,
        {
            "predecessor": {"artifact_version": "1.0", "sha256": older["descriptor_sha256"]},
            "rollback_target": {"artifact_version": "1.0", "sha256": older["descriptor_sha256"]},
        },
    )

    return {
        "_fixture_warning": FIXTURE_WARNING,
        "manifest_version": "1.0.0",
        "generated_at": PLAN_EVALUATION_INSTANT,
        "artifacts": [predecessor, current],
    }


def build_blocked_candidates(entries):
    """The real blocked candidates, with real hashes and their true governance."""
    import json

    plans = {}
    for artifact_id, version in (("token_dictionary", "2.0"), ("question_flow", "1.1")):
        entry = inventory.find(entries, artifact_id, version)
        path = repo_path("publication", "plans", "%s.dryrun.json" % entry["object_key"][:-5])
        with open(path, "rb") as handle:
            plans[artifact_id] = json.loads(handle.read().decode("utf-8"))

    return {
        "_fixture_note": "The real Vocabulary 2.0 and Question Flow 1.1 candidates, with real "
        "sha256 digests over the real candidate bytes in this repository and their true "
        "governance state. Both are unpublished, inactive, unapproved and ineligible in every "
        "environment. This is the Knowledge Base counterpart to the Backend's "
        "tests/fixtures/manifest/blocked-candidates.manifest.json, which had to use placeholder "
        "digests because the Backend cannot see these bytes. Descriptors here name no uploaded "
        "object and must never be added to any live manifest.",
        "_descriptor_source": "Extracted verbatim from the committed dry-run plans under "
        "publication/plans/, so this fixture and those plans cannot disagree.",
        "manifest_version": "1.0.0",
        "generated_at": PLAN_EVALUATION_INSTANT,
        "artifacts": [
            plans["token_dictionary"]["descriptor"],
            plans["question_flow"]["descriptor"],
        ],
    }


def build_compat_negatives():
    """Negative cases in the Backend's fixture format, runnable by both repositories."""
    cases = [
        # --- manifest-level -----------------------------------------------------------------
        {
            "name": "unknown contract major is rejected",
            "stage": "validation",
            "expected_code": "MANIFEST_VERSION_UNSUPPORTED",
            "manifest_overrides": {"manifest_version": "2.0.0"},
        },
        {
            "name": "a non-semver manifest version is rejected",
            "stage": "validation",
            "expected_code": "MANIFEST_VERSION_UNSUPPORTED",
            "manifest_overrides": {"manifest_version": "1.0"},
        },
        {
            "name": "an unknown required feature is rejected, not ignored",
            "stage": "validation",
            "expected_code": "UNKNOWN_REQUIRED_FEATURE",
            "manifest_overrides": {"required_features": ["signed_manifests"]},
        },
        {
            "name": "an unknown top-level manifest field is rejected",
            "stage": "validation",
            "expected_code": "UNKNOWN_FIELD",
            "manifest_overrides": {"publication_mode": "automatic"},
        },
        # --- descriptor shape ----------------------------------------------------------------
        {
            "name": "an unknown descriptor field is rejected",
            "stage": "validation",
            "expected_code": "UNKNOWN_FIELD",
            "descriptor_overrides": {"auto_publish": True},
        },
        {
            "name": "a missing required descriptor field is rejected",
            "stage": "validation",
            "expected_code": "MISSING_REQUIRED_FIELD",
            "remove_descriptor_fields": ["byte_count"],
        },
        {
            "name": "an unsupported artifact schema is rejected",
            "stage": "validation",
            "expected_code": "UNSUPPORTED_ARTIFACT_SCHEMA",
            "descriptor_overrides": {"schema_version": "wellapath.artifact/2"},
        },
        {
            "name": "an incorrect content type is rejected",
            "stage": "validation",
            "expected_code": "CONTENT_TYPE_UNSUPPORTED",
            "descriptor_overrides": {"content_type": "application/octet-stream"},
        },
        {
            "name": "a malformed sha256 is rejected",
            "stage": "validation",
            "expected_code": "MALFORMED_FIELD",
            "descriptor_overrides": {"sha256": "07f935967acb1d5515cb53ffd1c8e39b"},
        },
        {
            "name": "activation authorization without a decision reference is rejected",
            "stage": "validation",
            "expected_code": "MALFORMED_FIELD",
            "descriptor_overrides": {"activation_authorized": True, "activation_decision_ref": None},
        },
        {
            "name": "a duplicate artifact identity is rejected",
            "stage": "validation",
            "expected_code": "DUPLICATE_IDENTITY",
            "append_duplicate_of_target": True,
        },
        # --- object keys and origins ----------------------------------------------------------
        {
            "name": "a mutable alias object key is rejected",
            "stage": "validation",
            "expected_code": "OBJECT_KEY_INVALID",
            "descriptor_overrides": {"object_key": "fixture_artifact.ng.latest.json"},
        },
        {
            "name": "a path-traversal object key is rejected",
            "stage": "validation",
            "expected_code": "OBJECT_KEY_INVALID",
            "descriptor_overrides": {"object_key": "../fixture_artifact.ng.v1.1.json"},
        },
        {
            "name": "an absolute-path object key is rejected",
            "stage": "validation",
            "expected_code": "OBJECT_KEY_INVALID",
            "descriptor_overrides": {"object_key": "/fixture_artifact.ng.v1.1.json"},
        },
        {
            "name": "an arbitrary external origin is rejected",
            "stage": "validation",
            "expected_code": "ORIGIN_NOT_APPROVED",
            "descriptor_overrides": {
                "url": "https://cdn.example.com/fixture_artifact.ng.v1.1.json"
            },
        },
        {
            "name": "a plain http origin is rejected",
            "stage": "validation",
            "expected_code": "ORIGIN_NOT_HTTPS",
            "descriptor_overrides": {
                "url": "http://pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev/fixture_artifact.ng.v1.1.json"
            },
        },
        {
            "name": "a url with embedded credentials is rejected",
            "stage": "validation",
            "expected_code": "ORIGIN_HAS_CREDENTIALS",
            "descriptor_overrides": {
                "url": "https://user:pass@pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev/fixture_artifact.ng.v1.1.json"
            },
        },
        {
            "name": "a url carrying a query-string secret is rejected",
            "stage": "validation",
            "expected_code": "ORIGIN_HAS_QUERY",
            "descriptor_overrides": {
                "url": "https://pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev/fixture_artifact.ng.v1.1.json?token=REDACTED"
            },
        },
        # --- lineage and rollback ----------------------------------------------------------------
        {
            "name": "a rollback target that resolves to no descriptor is rejected",
            "stage": "validation",
            "expected_code": "INVALID_ROLLBACK_TARGET",
            "descriptor_overrides": {
                "rollback_target": {
                    "artifact_version": "0.9",
                    "sha256": "sha256:" + "0" * 64,
                }
            },
        },
        {
            "name": "a rollback target with a mismatched hash is rejected",
            "stage": "validation",
            "expected_code": "INVALID_ROLLBACK_TARGET",
            "descriptor_overrides": {
                "rollback_target": {"artifact_version": "1.0", "sha256": "sha256:" + "1" * 64}
            },
        },
        {
            "name": "a self-referencing rollback target is rejected as a cycle",
            "stage": "validation",
            "expected_code": "RELATIONSHIP_CYCLE",
            "descriptor_overrides": {
                "rollback_target": {"artifact_version": "1.1", "sha256": "sha256:" + "2" * 64}
            },
        },
        {
            "name": "a predecessor/rollback relationship cycle is rejected",
            "stage": "validation",
            "expected_code": "RELATIONSHIP_CYCLE",
            "other_descriptor_overrides": {
                "predecessor": {"artifact_version": "1.1", "sha256": "sha256:" + "3" * 64}
            },
        },
        # --- governance ----------------------------------------------------------------------------
        {
            "name": "a missing clinical approval record is rejected",
            "stage": "validation",
            "expected_code": "APPROVAL_MISSING",
            "remove_descriptor_fields": ["approvals.clinical"],
        },
        {
            "name": "an unknown approval status is rejected, never coerced",
            "stage": "validation",
            "expected_code": "APPROVAL_STATUS_UNKNOWN",
            "descriptor_overrides": {"approvals": {"clinical": {"status": "auto_approved"}}},
        },
        {
            "name": "missing product approval denies eligibility",
            "stage": "eligibility",
            "expected_code": "APPROVAL_NOT_GRANTED",
            "descriptor_overrides": {
                "approvals": {"product": {"status": "pending", "decision_ref": None}}
            },
        },
        {
            "name": "a required clinical approval still pending denies eligibility",
            "stage": "eligibility",
            "expected_code": "APPROVAL_NOT_GRANTED",
            "descriptor_overrides": {
                "approvals": {"clinical": {"status": "pending", "decision_ref": None}}
            },
        },
        {
            "name": "product approval cannot substitute for clinical approval",
            "stage": "eligibility",
            "expected_code": "APPROVAL_NOT_GRANTED",
            "descriptor_overrides": {
                "approvals": {
                    "product": {
                        "status": "granted",
                        "decision_ref": "FIXTURE-PRODUCT-0001 (synthetic)",
                    },
                    "clinical": {"status": "pending", "decision_ref": None},
                }
            },
        },
        {
            "name": "a withdrawn approval denies eligibility",
            "stage": "eligibility",
            "expected_code": "APPROVAL_NOT_GRANTED",
            "descriptor_overrides": {
                "approvals": {"clinical": {"status": "denied", "decision_ref": None}}
            },
        },
        {
            "name": "an open safety blocker denies eligibility",
            "stage": "eligibility",
            "expected_code": "BLOCKER_UNRESOLVED",
            "descriptor_overrides": {
                "blockers": [{"id": "IM003-SB-001", "status": "open", "reference": "fixture"}]
            },
        },
        {
            "name": "missing publication denies eligibility even when activation is authorized",
            "stage": "eligibility",
            "expected_code": "NOT_PUBLISHED",
            "descriptor_overrides": {"release_status": "candidate", "published_at": None},
        },
        {
            "name": "missing activation authorization denies eligibility",
            "stage": "eligibility",
            "expected_code": "ACTIVATION_NOT_AUTHORIZED",
            "descriptor_overrides": {
                "activation_authorized": False,
                "activation_decision_ref": None,
            },
        },
        {
            "name": "an environment mismatch denies eligibility",
            "stage": "eligibility",
            "expected_code": "ENVIRONMENT_NOT_AUTHORIZED",
            "context_overrides": {"environment": "production"},
        },
        {
            "name": "an expired descriptor denies eligibility",
            "stage": "eligibility",
            "expected_code": "DESCRIPTOR_EXPIRED",
            "descriptor_overrides": {"expires_at": "2026-01-01T00:00:00Z"},
        },
        {
            "name": "a deprecated descriptor denies eligibility",
            "stage": "eligibility",
            "expected_code": "DESCRIPTOR_DEPRECATED",
            "descriptor_overrides": {"deprecated": True},
        },
        {
            "name": "an incompatible app build denies eligibility",
            "stage": "eligibility",
            "expected_code": "APP_BUILD_INCOMPATIBLE",
            "descriptor_overrides": {"min_app_build": 500},
        },
        {
            "name": "an unknown consumer build fails closed when a minimum is declared",
            "stage": "eligibility",
            "expected_code": "APP_BUILD_INCOMPATIBLE",
            "descriptor_overrides": {"min_app_build": 10},
            "context_overrides": {"app_build": None},
        },
        # --- selection: the state-collapse cases ---------------------------------------------------
        {
            "name": "published is not active: publication alone selects nothing",
            "stage": "selection",
            "expected_code": "NOT_ACTIVE",
            "descriptor_overrides": {"activation_status": "inactive"},
        },
        {
            "name": "candidate existence is never treated as eligibility",
            "stage": "selection",
            "expected_code": "NO_ACTIVE_ARTIFACT",
            "descriptor_overrides": {
                "release_status": "candidate",
                "published_at": None,
                "activation_status": "inactive",
                "activation_authorized": False,
                "activation_decision_ref": None,
            },
        },
        {
            "name": "two simultaneously active descriptors select nothing",
            "stage": "selection",
            "expected_code": "MULTIPLE_ACTIVE",
            "other_descriptor_overrides": {
                "release_status": "published",
                "published_at": "2026-08-01T00:00:00Z",
                "activation_status": "active",
                "activation_authorized": True,
                "activation_decision_ref": "FIXTURE-ACTIVATION-0002 (synthetic)",
                "deprecated": False,
            },
        },
        # --- integrity -------------------------------------------------------------------------------
        {
            "name": "bytes that do not hash to the declared sha256 are rejected",
            "stage": "integrity",
            "expected_code": "HASH_MISMATCH",
            "bytes_utf8": "{\"not\":\"the artifact\"}",
        },
        {
            "name": "bytes with the wrong byte count are rejected",
            "stage": "integrity",
            "expected_code": "BYTE_COUNT_MISMATCH",
            "bytes_utf8": "{\"not\":\"the artifact\"}",
        },
    ]

    return {
        "description": "Cross-repository negative fixtures for manifest contract 1.0.0, written "
        "in the Backend's own fixture format so both implementations can execute them "
        "unchanged. Each case mutates the valid baseline manifest and declares the stage it "
        "must fail at and the exact reason code it must fail for. A case that fails for a "
        "different reason is itself a failure: it means one of the two implementations is "
        "refusing the right things for the wrong reasons, which will diverge as soon as either "
        "side changes.",
        "contract_version": "1.0.0",
        "contract_schema_sha256": "66fa3a94f17c2765eb1eca29208d2494c4c1b7be57eae61856bdb34761082ce9",
        "authored_by": "wellapath-knowledge-base, I3 Step 2",
        "runner_knowledge_base": "tools/validate_publication_fixtures.py",
        "runner_backend": "the same shape as tests/unit/manifest-fixtures.test.ts consumes",
        "base": "kb_baseline.manifest.json",
        "target": {"artifact_id": "fixture_artifact", "artifact_version": "1.1"},
        "context": {"environment": "staging", "app_build": 100, "now": PLAN_EVALUATION_INSTANT},
        "cases": cases,
    }


def build_kb_negatives(entries):
    """Negative cases for the stages the Backend has no opinion on."""
    question_flow = inventory.find(entries, "question_flow", "1.1")

    cases = [
        # --- contract pinning ---------------------------------------------------------------
        {
            "name": "a missing contract pin refuses to validate anything",
            "stage": "contract_pin",
            "expected_code": "KB_CONTRACT_PIN_MISSING",
            "mutation": {"kind": "remove_pin"},
        },
        {
            "name": "a malformed contract pin is refused",
            "stage": "contract_pin",
            "expected_code": "KB_CONTRACT_PIN_MALFORMED",
            "mutation": {"kind": "pin_json", "text": "{ not json"},
        },
        {
            "name": "a pin missing a required field is refused",
            "stage": "contract_pin",
            "expected_code": "KB_CONTRACT_PIN_MALFORMED",
            "mutation": {"kind": "pin_remove_field", "field": "vendored"},
        },
        {
            "name": "backend schema hash drift is refused",
            "stage": "contract_pin",
            "expected_code": "KB_CONTRACT_SCHEMA_HASH_DRIFT",
            "mutation": {"kind": "schema_bytes_append", "text": "\n"},
        },
        {
            "name": "a vendored schema that no longer matches the mirror is refused",
            "stage": "contract_pin",
            "expected_code": "KB_CONTRACT_SCHEMA_HASH_DRIFT",
            "mutation": {"kind": "schema_add_release_status", "value": "auto_published"},
        },
        {
            "name": "an unsupported contract major is refused",
            "stage": "contract_pin",
            "expected_code": "KB_CONTRACT_MAJOR_UNSUPPORTED",
            "mutation": {"kind": "pin_set", "path": "contract.supported_major", "value": 2},
        },
        {
            "name": "a pin policy that is not fail-closed is refused",
            "stage": "contract_pin",
            "expected_code": "KB_CONTRACT_PIN_MALFORMED",
            "mutation": {
                "kind": "pin_set",
                "path": "compatibility_policy.on_vendored_hash_drift",
                "value": "warn",
            },
        },
        # --- generation and integrity ---------------------------------------------------------
        {
            "name": "a non-reproducible artifact generation is a failure, not a warning",
            "stage": "generation",
            "expected_code": "KB_GENERATION_NONDETERMINISTIC",
            "mutation": {"kind": "generator_check_fails"},
        },
        {
            "name": "an artifact that fails its own schema is refused",
            "stage": "artifact_schema",
            "expected_code": "KB_ARTIFACT_SCHEMA_INVALID",
            "mutation": {"kind": "unknown_artifact_id", "artifact_id": "unregistered_artifact"},
        },
        {
            "name": "a declared hash that does not match the bytes is refused",
            "stage": "integrity",
            "expected_code": "HASH_MISMATCH",
            "mutation": {"kind": "declare_sha256", "value": "sha256:" + "4" * 64},
        },
        {
            "name": "a declared byte count that does not match the bytes is refused",
            "stage": "integrity",
            "expected_code": "BYTE_COUNT_MISMATCH",
            "mutation": {"kind": "declare_byte_count", "value": 1},
        },
        {
            "name": "a file whose bytes are not JSON has no determinable content type",
            "stage": "integrity",
            "expected_code": "KB_CONTENT_TYPE_UNDETERMINED",
            "mutation": {"kind": "non_json_bytes"},
        },
        # --- object keys -------------------------------------------------------------------------
        {
            "name": "a mutable alias key is refused by name",
            "stage": "object_key",
            "expected_code": "KB_KEY_MUTABLE_ALIAS",
            "mutation": {"kind": "object_key", "value": "question_flow.ng.vlatest.json"},
        },
        {
            "name": "a path-traversal key is refused by name",
            "stage": "object_key",
            "expected_code": "KB_KEY_PATH_TRAVERSAL",
            "mutation": {"kind": "object_key", "value": "../question_flow.ng.v1.1.json"},
        },
        {
            "name": "an absolute-path key is refused by name",
            "stage": "object_key",
            "expected_code": "KB_KEY_ABSOLUTE_PATH",
            "mutation": {"kind": "object_key", "value": "/question_flow.ng.v1.1.json"},
        },
        {
            "name": "a key that is not already NFC-normalised ASCII is refused",
            "stage": "object_key",
            "expected_code": "KB_KEY_AMBIGUOUS_NORMALIZATION",
            "mutation": {"kind": "object_key", "value": "question_floẃ.ng.v1.1.json"},
        },
        {
            "name": "an unsafe character in a key is refused",
            "stage": "object_key",
            "expected_code": "KB_KEY_UNSAFE_CHARACTER",
            "mutation": {"kind": "object_key", "value": "question flow.ng.v1.1.json"},
        },
        {
            "name": "a key embedding a query secret is refused",
            "stage": "object_key",
            "expected_code": "KB_KEY_EMBEDS_SECRET",
            "mutation": {
                "kind": "object_key",
                "value": "question_flow.ng.v1.1.json?X-Amz-Signature=deadbeef",
            },
        },
        {
            "name": "a key naming a credential as a path segment is refused",
            "stage": "object_key",
            "expected_code": "KB_KEY_EMBEDS_SECRET",
            "mutation": {"kind": "object_key", "value": "question_flow.secret.ng.v1.1.json"},
        },
        {
            "name": "a key naming a different version than the descriptor is refused",
            "stage": "object_key",
            "expected_code": "KB_KEY_VERSION_DISAGREEMENT",
            "mutation": {"kind": "key_identity_mismatch", "value": "question_flow.ng.v1.0.json"},
        },
        {
            "name": "reusing one key for two identities is a collision",
            "stage": "object_key",
            "expected_code": "KB_KEY_IDENTITY_COLLISION",
            "mutation": {"kind": "register_two_identities_one_key"},
        },
        {
            "name": "rebinding a key to different bytes is refused as an overwrite",
            "stage": "object_key",
            "expected_code": "KB_KEY_OVERWRITE_DIFFERENT_BYTES",
            "mutation": {"kind": "register_two_digests_one_key"},
        },
        # --- governance ----------------------------------------------------------------------------
        {
            "name": "a prose-only approval with no hash-bound record resolves to nothing",
            "stage": "governance",
            "expected_code": "KB_DECISION_PROSE_ONLY",
            "mutation": {"kind": "record_drop_reference_hash"},
        },
        {
            "name": "an approval with no named reviewer is not an approval",
            "stage": "governance",
            "expected_code": "KB_DECISION_REVIEWER_MISSING",
            "mutation": {"kind": "record_set", "path": "reviewer.identity", "value": ""},
        },
        {
            "name": "an approval with no reviewer title is not an approval",
            "stage": "governance",
            "expected_code": "KB_DECISION_REVIEWER_MISSING",
            "mutation": {"kind": "record_set", "path": "reviewer.title", "value": ""},
        },
        {
            "name": "an unknown authority type is refused",
            "stage": "governance",
            "expected_code": "KB_DECISION_AUTHORITY_MISSING",
            "mutation": {"kind": "record_set", "path": "authority_type", "value": "senior"},
        },
        {
            "name": "an unknown decision status is never coerced",
            "stage": "governance",
            "expected_code": "KB_DECISION_STATUS_UNKNOWN",
            "mutation": {"kind": "record_set", "path": "status", "value": "probably_fine"},
        },
        {
            "name": "product authority cannot satisfy a clinical claim",
            "stage": "governance",
            "expected_code": "KB_DECISION_AUTHORITY_WRONG",
            "mutation": {"kind": "product_record_grants", "claim": "clinical_approval"},
        },
        {
            "name": "a decision that exists but is not approved grants nothing",
            "stage": "governance",
            "expected_code": "KB_DECISION_NOT_APPROVED",
            "mutation": {"kind": "granting_record_set", "path": "status", "value": "pending"},
        },
        {
            "name": "an approval bound to another artifact does not carry across",
            "stage": "governance",
            "expected_code": "KB_DECISION_ARTIFACT_MISMATCH",
            "mutation": {
                "kind": "record_set",
                "path": "subject.artifact_id",
                "value": "token_dictionary",
            },
        },
        {
            "name": "an approval bound to another version does not carry across",
            "stage": "governance",
            "expected_code": "KB_DECISION_VERSION_MISMATCH",
            "mutation": {"kind": "record_set", "path": "subject.artifact_version", "value": "1.0"},
        },
        {
            "name": "an approval bound to other bytes does not carry across a content change",
            "stage": "governance",
            "expected_code": "KB_DECISION_HASH_MISMATCH",
            "mutation": {
                "kind": "record_set",
                "path": "subject.artifact_sha256",
                "value": "sha256:" + "5" * 64,
            },
        },
        {
            "name": "a superseded approval grants nothing",
            "stage": "governance",
            "expected_code": "KB_DECISION_SUPERSEDED",
            "mutation": {
                "kind": "granting_record_set",
                "path": "supersession.superseded_by",
                "value": "IM001-ORD-GLOBAL-002",
            },
        },
        {
            "name": "a revoked approval grants nothing",
            "stage": "governance",
            "expected_code": "KB_DECISION_REVOKED",
            "mutation": {"kind": "granting_record_set", "path": "supersession.revoked", "value": True},
        },
        {
            "name": "an expired approval grants nothing",
            "stage": "governance",
            "expected_code": "KB_DECISION_EXPIRED",
            "mutation": {"kind": "granting_record_set", "path": "expires_at", "value": "2026-01-01"},
        },
        {
            "name": "a removed approval record leaves the claim unsupported",
            "stage": "governance",
            "expected_code": "KB_DECISION_RECORD_MISSING",
            "mutation": {"kind": "remove_all_records"},
        },
        {
            "name": "im_001_resolved is not activation authority",
            "stage": "governance",
            "expected_code": "KB_DECISION_SET_IS_NOT_AUTHORIZATION",
            "mutation": {"kind": "claim", "claim": "activation_authorization"},
        },
        {
            "name": "im_001_resolved is not publication authority",
            "stage": "governance",
            "expected_code": "KB_DECISION_SET_IS_NOT_AUTHORIZATION",
            "mutation": {"kind": "claim", "claim": "publication_authorization"},
        },
        {
            "name": "no publication authorization exists for the real candidates",
            "stage": "governance",
            "expected_code": "KB_PUBLICATION_AUTHORIZATION_MISSING",
            "mutation": {"kind": "plan_claim", "claim": "publication_authorization"},
        },
        {
            "name": "no activation authorization exists for the real candidates",
            "stage": "governance",
            "expected_code": "KB_ACTIVATION_AUTHORIZATION_MISSING",
            "mutation": {"kind": "plan_claim", "claim": "activation_authorization"},
        },
        {
            "name": "an open safety blocker refuses regardless of approvals",
            "stage": "governance",
            "expected_code": "KB_SAFETY_BLOCKER_OPEN",
            "mutation": {"kind": "open_blocker", "id": "IM003-SB-001"},
        },
        # --- lifecycle -------------------------------------------------------------------------------
        {
            "name": "generated is not validated",
            "stage": "lifecycle",
            "expected_code": "KB_STATE_COLLAPSE",
            "mutation": {"kind": "unobserved_state", "state": "validated"},
        },
        {
            "name": "packaged is not uploaded",
            "stage": "lifecycle",
            "expected_code": "KB_STATE_COLLAPSE",
            "mutation": {"kind": "assert_state", "state": "uploaded"},
        },
        {
            "name": "present is not published",
            "stage": "lifecycle",
            "expected_code": "KB_STATE_COLLAPSE",
            "mutation": {"kind": "assert_state", "state": "published"},
        },
        {
            "name": "published is not approved",
            "stage": "lifecycle",
            "expected_code": "KB_STATE_COLLAPSE",
            "mutation": {"kind": "assert_state", "state": "approved"},
        },
        {
            "name": "approved is not active",
            "stage": "lifecycle",
            "expected_code": "KB_STATE_COLLAPSE",
            "mutation": {"kind": "assert_state", "state": "active"},
        },
        {
            "name": "active is not eligible",
            "stage": "lifecycle",
            "expected_code": "KB_STATE_COLLAPSE",
            "mutation": {"kind": "assert_state", "state": "eligible_for_environment"},
        },
        {
            "name": "an unknown lifecycle value fails closed rather than resolving",
            "stage": "lifecycle",
            "expected_code": "KB_STATE_COLLAPSE",
            "mutation": {"kind": "unknown_state_value", "state": "approved", "value": None},
        },
        # --- rollback ---------------------------------------------------------------------------------
        {
            "name": "a version-only rollback target is unbound and refused",
            "stage": "rollback",
            "expected_code": "KB_ROLLBACK_UNBOUND_VERSION_ONLY",
            "mutation": {"kind": "rollback_target", "value": {"artifact_version": "1.0"}},
        },
        {
            "name": "a rollback target absent from the governed inventory is refused",
            "stage": "rollback",
            "expected_code": "KB_ROLLBACK_TARGET_NOT_IN_INVENTORY",
            "mutation": {
                "kind": "rollback_target",
                "value": {"artifact_version": "0.9", "sha256": "sha256:" + "6" * 64},
            },
        },
        {
            "name": "a rollback target whose hash does not match is refused",
            "stage": "rollback",
            "expected_code": "KB_ROLLBACK_HASH_MISMATCH",
            "mutation": {
                "kind": "rollback_target",
                "value": {"artifact_version": "1.0", "sha256": "sha256:" + "7" * 64},
            },
        },
        {
            "name": "a rollback target naming another artifact is refused",
            "stage": "rollback",
            "expected_code": "KB_ROLLBACK_CROSS_ARTIFACT",
            "mutation": {
                "kind": "rollback_target",
                "value": {
                    "artifact_id": "token_dictionary",
                    "artifact_version": "1.0",
                    "sha256": question_flow["descriptor_sha256"],
                },
            },
        },
        {
            "name": "a rollback target that is the descriptor itself is a cycle",
            "stage": "rollback",
            "expected_code": "KB_ROLLBACK_CYCLE",
            "mutation": {
                "kind": "rollback_target",
                "value": {
                    "artifact_version": "1.1",
                    "sha256": question_flow["descriptor_sha256"],
                },
            },
        },
        {
            "name": "a rollback across a content-schema boundary is refused",
            "stage": "rollback",
            "expected_code": "KB_ROLLBACK_SCHEMA_INCOMPATIBLE",
            "mutation": {"kind": "rollback_default_target"},
        },
        {
            "name": "a rollback to unauthorized content is refused pending an explicit policy",
            "stage": "rollback",
            "expected_code": "KB_ROLLBACK_TARGET_UNAUTHORIZED",
            "mutation": {"kind": "rollback_governance", "status": "revoked"},
        },
        # --- write and network safety --------------------------------------------------------------------
        {
            "name": "the dry-run path attempting a network connection fails the run",
            "stage": "write_safety",
            "expected_code": "KB_NETWORK_ATTEMPTED",
            "mutation": {"kind": "attempt_network"},
        },
        {
            "name": "the dry-run path attempting a subprocess fails the run",
            "stage": "write_safety",
            "expected_code": "KB_SUBPROCESS_ATTEMPTED",
            "mutation": {"kind": "attempt_subprocess"},
        },
        {
            "name": "a write outside the staging directory fails the run",
            "stage": "write_safety",
            "expected_code": "KB_STAGING_ESCAPE",
            "mutation": {"kind": "attempt_write_outside_staging"},
        },
        {
            "name": "a staging write escaping via traversal is refused",
            "stage": "write_safety",
            "expected_code": "KB_STAGING_ESCAPE",
            "mutation": {"kind": "staging_traversal", "name": "../escaped.json"},
        },
        {
            "name": "mutating a canonical artifact during a run is detected",
            "stage": "write_safety",
            "expected_code": "KB_CANONICAL_ARTIFACT_MUTATED",
            "mutation": {"kind": "canonical_mutation"},
        },
    ]

    return {
        "description": "Negative fixtures for the Knowledge-Base-only stages: contract pinning, "
        "artifact generation, object-key safety, governance evidence resolution, lifecycle "
        "state collapse, rollback binding, and write/network safety. The Backend contract has "
        "no opinion on any of these because they all happen before a manifest exists. Each "
        "case declares the stage it must fail at and the exact reason code it must fail for; "
        "the runner asserts both, so a guard that starts refusing for a different reason is a "
        "test failure rather than a silent change of meaning.",
        "runner": "tools/validate_publication_fixtures.py",
        "reason_code_namespace": "KB_* codes are Knowledge Base findings and are never written "
        "into a descriptor. Where a case expects a bare (non-KB_) code, that is the Backend's "
        "own code, used because the finding is genuinely the same one.",
        "cases": cases,
    }


#: The Backend's blocked-candidates fixture, transcribed for the reconciliation probe.
#:
#: Only the two fields under examination are reproduced, not the whole descriptor: the point is
#: to evaluate *the KB's own descriptor* with the Backend's approval encoding substituted in, so
#: that the two differ in exactly one respect and the result is attributable to that respect.
#: Copying the Backend's entire descriptor would also import its synthetic hashes and its
#: `vocabulary` artifact id, and the comparison would no longer be controlled.
BACKEND_PRODUCT_ENCODING = {
    "source": "wellapath-backend tests/fixtures/manifest/blocked-candidates.manifest.json "
    "@ fc40ac3e7d59cfed8e2584b78136c9704f7ab8cd",
    "approvals_product": {
        "required": True,
        "status": "granted",
        "decision_ref": "IM-001 — Product decisions complete; activation remains unauthorized",
        "approved_at": None,
    },
}


def _evaluate_everywhere(descriptor, now):
    from pubkit import eligibility

    result = {}
    for environment in ("development", "staging", "production"):
        states, reasons = eligibility.evaluate_descriptor(descriptor, environment, now=now)
        result[environment] = {
            "approved": states["approved"],
            "active": states["active"],
            "eligible_for_environment": states["eligible_for_environment"],
            "reason_codes": sorted({item["code"] for item in reasons}),
        }
    return result


def _lift_unrelated_conditions(descriptor):
    """Grant everything EXCEPT product approval, so `approved` depends only on the product half.

    This is the controlled experiment. As shipped, both encodings are ineligible — but for the
    Backend's, that is because clinical is pending and two blockers are open, not because its
    product field is right. Lifting those unrelated conditions is what separates "refused for
    the correct reason" from "refused by something else that happens to be in the way".
    """
    import copy

    lifted = copy.deepcopy(descriptor)
    lifted["approvals"]["clinical"] = {
        "required": True,
        "status": "granted",
        "decision_ref": "HYPOTHETICAL — used only to isolate the product half of the probe",
        "approved_at": "2026-09-01T00:00:00Z",
    }
    lifted["blockers"] = [
        {"id": blocker["id"], "status": "resolved", "reference": blocker.get("reference", "")}
        for blocker in lifted["blockers"]
    ]
    lifted["release_status"] = "published"
    lifted["published_at"] = "2026-09-01T00:00:00Z"
    lifted["activation_status"] = "active"
    lifted["activation_authorized"] = True
    lifted["activation_decision_ref"] = "HYPOTHETICAL — probe only"
    return lifted


def build_approval_scope_reconciliation(entries):
    """A machine-readable reconciliation of the two Product concepts. Every claim is computed."""
    import copy
    import json

    plan = None
    with open(repo_path("publication", "plans", "question_flow.ng.v1.1.dryrun.json"), "rb") as handle:
        plan = json.loads(handle.read().decode("utf-8"))

    kb_descriptor = plan["descriptor"]
    backend_descriptor = copy.deepcopy(kb_descriptor)
    backend_descriptor["approvals"]["product"] = copy.deepcopy(
        BACKEND_PRODUCT_ENCODING["approvals_product"]
    )

    now = PLAN_EVALUATION_INSTANT
    kb_shipped = _evaluate_everywhere(kb_descriptor, now)
    backend_shipped = _evaluate_everywhere(backend_descriptor, now)
    kb_probe = _evaluate_everywhere(_lift_unrelated_conditions(kb_descriptor), now)
    backend_probe = _evaluate_everywhere(_lift_unrelated_conditions(backend_descriptor), now)

    scope = plan["governance"]["product_approval_scope"]
    gate = [b for b in kb_descriptor["blockers"] if b["id"] == "IM001-PRODUCT-DISPLAY-DECISIONS"]

    claims = {
        "im_001_display_decision_completion_remains_true": scope["product_display_decision"][
            "status"
        ]
        == "complete"
        and len(gate) == 1
        and gate[0]["status"] == "resolved",
        "artifact_publication_product_approval_remains_pending": (
            scope["artifact_publication_product_approval"]["status"] == "pending"
            and kb_descriptor["approvals"]["product"]["status"] == "pending"
            and kb_descriptor["approvals"]["product"]["decision_ref"] is None
        ),
        "clinical_approval_remains_pending": kb_descriptor["approvals"]["clinical"]["status"]
        == "pending",
        "both_representations_are_ineligible_in_every_environment": all(
            result[environment]["eligible_for_environment"] is False
            for result in (kb_shipped, backend_shipped)
            for environment in result
        ),
        "no_evaluator_can_substitute_completion_for_approval": (
            # The KB encoding keeps `approved` false even with every unrelated condition
            # granted, because completion lives in a field that can only ever deny.
            all(kb_probe[e]["approved"] is False for e in kb_probe)
            and all(kb_probe[e]["eligible_for_environment"] is False for e in kb_probe)
        ),
        "backend_encoding_substitutes_completion_for_approval": (
            # ... whereas the Backend encoding does become approved, on the strength of a
            # display-wording decision. That is the defect.
            any(backend_probe[e]["approved"] is True for e in backend_probe)
        ),
    }

    return {
        "_metadata": {
            "record_id": "approval_scope_reconciliation",
            "version": "1",
            "phase": "I3 / Step 2A",
            "generator": "tools/build_publication_fixtures.py",
            "generator_version": "1.0.0",
            "evaluated_at": now,
            "evaluator": "tools/pubkit/eligibility.py — a port of the Backend's "
            "src/manifest/eligibility.ts at fc40ac3e7d59cfed8e2584b78136c9704f7ab8cd",
            "note": "Every claim below is COMPUTED by running the contract's own eligibility "
            "semantics over both encodings, not asserted in prose.",
        },
        "ruling": {
            "product_display_decision": {
                "status": "complete",
                "scope": "display_wording_and_ordering_only",
            },
            "artifact_publication_product_approval": {"status": "pending"},
            "clinical_approval": {"status": "pending"},
            "publication_authorization": False,
            "activation_authorization": False,
            "source": "The recorded IM-001 decision explicitly excludes publication and "
            "activation. Decision-set completion is not artifact approval.",
        },
        "contract_can_express_the_distinction": True,
        "contract_representation": {
            "artifact_publication_product_approval": "approvals.product.status — the only input "
            "to the product half of `approved`",
            "clinical_approval": "approvals.clinical.status",
            "product_display_decision": "a blocker_record with status 'resolved' "
            "(IM001-PRODUCT-DISPLAY-DECISIONS)",
            "why_a_resolved_blocker": "evaluateDescriptor computes `approved` exclusively from "
            "`approvals`, and reads `blockers` in a loop whose only effect is to set "
            "blockersResolved = false. A resolved blocker is therefore structurally incapable "
            "of granting approval — the safety is in the contract's shape, not in a convention "
            "anyone has to remember.",
            "publication_authorization": "publication_decision_ref",
            "activation_authorization": "activation_authorized + activation_decision_ref",
        },
        "encodings_compared": {
            "knowledge_base": {
                "approvals_product": kb_descriptor["approvals"]["product"],
                "display_decision_gate": gate[0] if gate else None,
                "as_shipped": kb_shipped,
                "with_unrelated_conditions_lifted": kb_probe,
            },
            "backend_fixture": {
                "source": BACKEND_PRODUCT_ENCODING["source"],
                "approvals_product": BACKEND_PRODUCT_ENCODING["approvals_product"],
                "display_decision_gate": None,
                "as_shipped": backend_shipped,
                "with_unrelated_conditions_lifted": backend_probe,
            },
        },
        "claims": claims,
        "verdict": {
            "backend_granted_product_is": "fixture_defect",
            "reasoning": "The decision_ref text describes decision-set completion — the scoped "
            "IM-001 display decision — but it is placed in approvals.product, which contract "
            "1.0.0 defines as artifact-level Product approval and which evaluateDescriptor "
            "reads to compute `approved`. As shipped the descriptor is ineligible, but only "
            "because clinical approval is pending and two blockers are open. Lift those "
            "unrelated conditions and it becomes approved and eligible on the strength of a "
            "display-wording decision. A field that is safe only while something else happens "
            "to be blocking is not scoped correctly; it is a latent defect.",
            "knowledge_base_action": "None. The KB does not weaken to match. It keeps "
            "approvals.product pending and carries the completed display decision as a "
            "resolved gate.",
            "backend_follow_up_required": "The Backend fixture should set "
            "approvals.product.status to 'pending' and, if it wishes to record the IM-001 "
            "display-decision completion, carry it as a resolved blocker_record. This task does "
            "not modify the Backend repository.",
            "blocking_this_merge": False,
            "why_not_blocking": "The defect is in a Backend test fixture, not in the contract "
            "and not in the KB tooling. The contract can express the distinction, the KB "
            "descriptor validates against contract 1.0.0, and both encodings are ineligible as "
            "shipped.",
        },
    }


OUTPUTS = (
    (COMPAT_DIR, "kb_baseline.manifest.json", "baseline"),
    (COMPAT_DIR, "kb_blocked_candidates.manifest.json", "blocked"),
    (COMPAT_DIR, "negative_fixtures.compat.json", "compat_negatives"),
    (NEGATIVE_DIR, "kb_stage_fixtures_v1.json", "kb_negatives"),
    (COMPAT_DIR, "approval_scope_reconciliation_v1.json", "approval_scope"),
)


def main(argv):
    check = "--check" in argv
    entries = inventory.discover()

    documents = {
        "baseline": build_baseline(entries),
        "blocked": build_blocked_candidates(entries),
        "compat_negatives": build_compat_negatives(),
        "kb_negatives": build_kb_negatives(entries),
        "approval_scope": build_approval_scope_reconciliation(entries),
    }

    failures = 0
    for directory, filename, key in OUTPUTS:
        data = dump_report_bytes(documents[key])
        path = os.path.join(directory, filename)
        relative = os.path.relpath(path, repo_path())
        if check:
            if not os.path.exists(path):
                print("MISSING %s" % relative)
                failures += 1
                continue
            with open(path, "rb") as handle:
                committed = handle.read()
            if committed != data:
                print("DRIFT %s is not reproducible from its generator" % relative)
                failures += 1
            else:
                print("OK %s" % relative)
        else:
            write_bytes(path, data)
            print("wrote %s (%d bytes)" % (relative, len(data)))

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
