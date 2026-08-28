"""The Backend manifest contract, mirrored at the pinned commit.

Every constant here is copied from `wellapath-backend/src/manifest/contract.ts` at
`fc40ac3e7d59cfed8e2584b78136c9704f7ab8cd` (contract 1.0.0). This module is a *mirror*, not a
design: the Backend repository is the authority and nothing here may extend, reorder or
loosen what it declares.

`tools/verify_contract_pin.py` cross-checks this mirror against the vendored schema bytes, so
a constant that drifts from the schema is a CI failure rather than a divergence nobody notices
until a descriptor is rejected in production.
"""

MANIFEST_CONTRACT_VERSION = "1.0.0"
SUPPORTED_MANIFEST_MAJOR = 1

#: Empty on purpose, exactly as the Backend declares it. A manifest requesting any feature is
#: asking for behaviour that does not exist; fail-closed means rejecting it, not ignoring it.
SUPPORTED_MANIFEST_FEATURES = ()

SUPPORTED_ARTIFACT_SCHEMAS = ("wellapath.artifact/1",)
SUPPORTED_CONTENT_TYPES = ("application/json",)

ENVIRONMENTS = ("development", "staging", "production")
RELEASE_STATUSES = ("draft", "candidate", "published", "deprecated")
ACTIVATION_STATUSES = ("inactive", "active")
APPROVAL_STATUSES = ("granted", "denied", "pending", "not_required")
BLOCKER_STATUSES = ("open", "resolved")

APPROVAL_ROLES = ("product", "clinical")

REQUIRED_DESCRIPTOR_KEYS = (
    "artifact_id",
    "artifact_version",
    "schema_version",
    "content_type",
    "sha256",
    "byte_count",
    "object_key",
    "release_status",
    "activation_status",
    "activation_authorized",
    "activation_decision_ref",
    "target_environments",
    "publication_decision_ref",
    "approvals",
    "blockers",
    "predecessor",
    "rollback_target",
    "created_at",
    "published_at",
    "deprecated",
    "expires_at",
    "country",
)

OPTIONAL_DESCRIPTOR_KEYS = ("url", "min_app_build", "references")

ALLOWED_DESCRIPTOR_KEYS = REQUIRED_DESCRIPTOR_KEYS + OPTIONAL_DESCRIPTOR_KEYS

ALLOWED_MANIFEST_KEYS = ("manifest_version", "generated_at", "required_features", "artifacts")
REQUIRED_MANIFEST_KEYS = ("manifest_version", "generated_at", "artifacts")

APPROVAL_RECORD_KEYS = ("required", "status", "decision_ref", "approved_at")
BLOCKER_RECORD_KEYS = ("id", "status", "reference")
VERSION_REF_KEYS = ("artifact_version", "sha256")

# --- patterns, copied from the Backend's own regexes ---------------------------------------

ARTIFACT_ID_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
VERSION_PATTERN = r"^\d+(\.\d+){0,3}$"
SEMVER_PATTERN = r"^(\d+)\.(\d+)\.(\d+)$"
COUNTRY_PATTERN = r"^[a-z]{2}$"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
OBJECT_KEY_PATTERN = r"^[a-z0-9_]+\.[a-z]{2}\.v\d+(\.\d+)*\.json$"

#: The Backend's own `ISO_DATETIME_PATTERN`: UTC `Z` only, no numeric offsets. The KB emits
#: nothing else, so a plan cannot produce a timestamp the Backend would call malformed.
ISO_DATETIME_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"

#: From `src/manifest/origin.ts`. Already public in the Backend repository (tests, docs,
#: `.env.example`); listing it exposes nothing new and it is not a credential.
APPROVED_ARTIFACT_ORIGINS = ("https://pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev",)

#: Keywords the vendored draft-07 schema uses that the KB's dependency-free validator has no
#: assertion for. Annotations only — see `tools/vocab/schema_check.py`.
SCHEMA_ANNOTATION_KEYWORDS = frozenset(["definitions", "contract_version"])
