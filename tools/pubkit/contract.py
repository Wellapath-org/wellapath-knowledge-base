"""The Backend manifest contract, mirrored at the pinned commit.

Every constant here is copied from `wellapath-backend/src/manifest/contract.ts` at
`bbaeadd6075eb37fd51acbe04101f939e52c7d48` (contract 1.1.0). This module is a *mirror*, not a
design: the Backend repository is the authority and nothing here may extend, reorder or
loosen what it declares.

Re-pinned from 1.0.0 in I3 Step 2C. 1.1.0 adds the optional approval field `decision_scope` and
tightens one previously unsafe claim: a `granted` approval declaring no `artifact_publication`
scope no longer counts.

`tools/verify_contract_pin.py` cross-checks this mirror against the vendored schema bytes, so
a constant that drifts from the schema is a CI failure rather than a divergence nobody notices
until a descriptor is rejected in production.
"""

MANIFEST_CONTRACT_VERSION = "1.1.0"
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

#: What a cited decision actually authorized. New in 1.1.0.
#:
#: A decision's scope is what its deciding authority actually decided — it is not implied by
#: who took the decision, nor by the decision being complete. A finished Product decision about
#: how a question is worded and ordered is scoped `product_display`; that authorizes exactly
#: that, and never authorized publishing an artifact.
APPROVAL_SCOPES = (
    "artifact_publication",
    "artifact_activation",
    "product_display",
    "clinical_content_review",
)

#: The scope BOTH approval slots on a descriptor demand.
#:
#: `approvals.product` and `approvals.clinical` are artifact-publication approval slots. A
#: decision whose declared scope does not include this cannot occupy either of them, whatever
#: its status says and whichever authority took it.
ARTIFACT_APPROVAL_SLOT_SCOPE = "artifact_publication"

REQUIRED_APPROVAL_KEYS = ("required", "status", "decision_ref", "approved_at")

#: `decision_scope` is structurally optional but semantically mandatory for a granted approval:
#: an approval that is not granted claims nothing and so needs no scope, and demanding one
#: there would invalidate sound descriptors while protecting nothing.
OPTIONAL_APPROVAL_KEYS = ("decision_scope",)

ALLOWED_APPROVAL_KEYS = REQUIRED_APPROVAL_KEYS + OPTIONAL_APPROVAL_KEYS

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
