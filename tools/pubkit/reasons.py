"""Machine-readable reason codes, in two deliberately separate namespaces.

`BACKEND_REASON_CODES` is the Backend contract's own closed set, copied verbatim from
`src/manifest/contract.ts` at the pinned commit. Anything the Knowledge Base says *about a
descriptor or manifest* uses one of these, so a rejection here means the same thing it would
mean in the Backend.

`KB_REASON_CODES` covers stages the Backend has no opinion on because they happen before a
manifest exists at all: pin drift, non-reproducible generation, canonical mutation, staging
escape, attempted network or storage writes, and governance-evidence resolution against this
repository's decision records. These are Knowledge Base findings and are never written into a
descriptor — a descriptor carrying one would be a descriptor the Backend cannot parse.

The two sets are asserted disjoint at import. A code that drifted into both would let a
KB-only failure masquerade as a contract rejection, which is exactly the collapse this step
exists to prevent.
"""

#: Verbatim from wellapath-backend src/manifest/contract.ts REASON_CODES at
#: bbaeadd6075eb37fd51acbe04101f939e52c7d48 (contract 1.1.0). Order preserved so drift is a
#: visible diff. The three APPROVAL_SCOPE_* codes are new in 1.1.0 and appear in the Backend's
#: own position, immediately after APPROVAL_STATUS_UNKNOWN.
BACKEND_REASON_CODES = (
    "MANIFEST_MALFORMED",
    "MANIFEST_VERSION_UNSUPPORTED",
    "UNKNOWN_REQUIRED_FEATURE",
    "UNKNOWN_FIELD",
    "MISSING_REQUIRED_FIELD",
    "MALFORMED_FIELD",
    "UNSUPPORTED_ARTIFACT_SCHEMA",
    "CONTENT_TYPE_UNSUPPORTED",
    "OBJECT_KEY_INVALID",
    "ORIGIN_NOT_APPROVED",
    "ORIGIN_NOT_HTTPS",
    "ORIGIN_HAS_CREDENTIALS",
    "ORIGIN_HAS_QUERY",
    "DUPLICATE_IDENTITY",
    "RELATIONSHIP_CYCLE",
    "INVALID_ROLLBACK_TARGET",
    "APPROVAL_STATUS_UNKNOWN",
    "APPROVAL_SCOPE_MISSING",
    "APPROVAL_SCOPE_UNKNOWN",
    "APPROVAL_SCOPE_MISMATCH",
    "HASH_MISMATCH",
    "BYTE_COUNT_MISMATCH",
    "NOT_PUBLISHED",
    "APPROVAL_MISSING",
    "APPROVAL_NOT_GRANTED",
    "BLOCKER_UNRESOLVED",
    "ACTIVATION_NOT_AUTHORIZED",
    "NOT_ACTIVE",
    "ENVIRONMENT_NOT_AUTHORIZED",
    "APP_BUILD_INCOMPATIBLE",
    "DESCRIPTOR_EXPIRED",
    "DESCRIPTOR_DEPRECATED",
    "NO_ACTIVE_ARTIFACT",
    "MULTIPLE_ACTIVE",
    "DOWNGRADE_NOT_AUTHORIZED",
)

#: Knowledge-Base-side codes. Everything here is a finding about *preparing* an artifact,
#: which is a question the Backend contract does not ask.
KB_REASON_CODES = (
    # --- contract pinning -----------------------------------------------------------------
    "KB_CONTRACT_PIN_MISSING",
    "KB_CONTRACT_PIN_MALFORMED",
    "KB_CONTRACT_SCHEMA_HASH_DRIFT",
    "KB_CONTRACT_MAJOR_UNSUPPORTED",
    "KB_CONTRACT_RULE_UNREPRESENTABLE",
    "KB_CONTRACT_KB_PASSES_BACKEND_FAILS",
    # --- contract provenance inside a generated plan --------------------------------------
    #
    # A plan records which contract it was built and validated against. Those records are
    # copied into several fields, and a copy that falls out of step with the pin is worse than
    # no copy at all: it reads as provenance while naming a contract nobody used.
    "KB_PROVENANCE_VERSION_MISMATCH",
    "KB_PROVENANCE_COMMIT_MISMATCH",
    "KB_PROVENANCE_SCHEMA_HASH_MISMATCH",
    "KB_PROVENANCE_SCHEMA_BYTES_MISMATCH",
    "KB_PROVENANCE_LEGACY_REFERENCE",
    "KB_PROVENANCE_VALIDATED_AGAINST_NON_PIN",
    "KB_PROVENANCE_STALE_PLAN",
    "KB_PROVENANCE_VALIDATION_CONTRADICTED",

    # --- generation and integrity ---------------------------------------------------------
    "KB_ARTIFACT_NOT_FOUND",
    "KB_ARTIFACT_SCHEMA_INVALID",
    "KB_GENERATION_NONDETERMINISTIC",
    "KB_CANONICAL_ARTIFACT_MUTATED",
    "KB_CONTENT_TYPE_UNDETERMINED",
    # --- object keys ----------------------------------------------------------------------
    "KB_KEY_MUTABLE_ALIAS",
    "KB_KEY_PATH_TRAVERSAL",
    "KB_KEY_ABSOLUTE_PATH",
    "KB_KEY_AMBIGUOUS_NORMALIZATION",
    "KB_KEY_UNSAFE_CHARACTER",
    "KB_KEY_VERSION_DISAGREEMENT",
    "KB_KEY_IDENTITY_COLLISION",
    "KB_KEY_OVERWRITE_DIFFERENT_BYTES",
    "KB_KEY_EMBEDS_SECRET",
    # --- governance evidence --------------------------------------------------------------
    "KB_DECISION_RECORD_MISSING",
    "KB_DECISION_RECORD_MALFORMED",
    "KB_DECISION_ID_MISSING",
    "KB_DECISION_AUTHORITY_MISSING",
    "KB_DECISION_AUTHORITY_WRONG",
    "KB_DECISION_REVIEWER_MISSING",
    "KB_DECISION_DATE_MISSING",
    "KB_DECISION_STATUS_UNKNOWN",
    "KB_DECISION_NOT_APPROVED",
    "KB_DECISION_SCOPE_MISSING",
    "KB_DECISION_SCOPE_EXCEEDED",
    "KB_DECISION_ARTIFACT_MISMATCH",
    "KB_DECISION_VERSION_MISMATCH",
    "KB_DECISION_HASH_MISMATCH",
    "KB_DECISION_SUPERSEDED",
    "KB_DECISION_REVOKED",
    "KB_DECISION_EXPIRED",
    "KB_DECISION_PROSE_ONLY",
    "KB_DECISION_SET_IS_NOT_AUTHORIZATION",
    "KB_PUBLICATION_AUTHORIZATION_MISSING",
    "KB_ACTIVATION_AUTHORIZATION_MISSING",
    "KB_SAFETY_BLOCKER_OPEN",
    # --- lifecycle state collapse ---------------------------------------------------------
    "KB_STATE_COLLAPSE",
    # --- rollback -------------------------------------------------------------------------
    "KB_ROLLBACK_UNBOUND_VERSION_ONLY",
    "KB_ROLLBACK_TARGET_NOT_IN_INVENTORY",
    "KB_ROLLBACK_HASH_MISMATCH",
    "KB_ROLLBACK_CROSS_ARTIFACT",
    "KB_ROLLBACK_CYCLE",
    "KB_ROLLBACK_SCHEMA_INCOMPATIBLE",
    "KB_ROLLBACK_TARGET_UNAUTHORIZED",
    # --- write and network safety ---------------------------------------------------------
    "KB_STAGING_ESCAPE",
    "KB_NETWORK_ATTEMPTED",
    "KB_SUBPROCESS_ATTEMPTED",
    "KB_STORAGE_WRITE_ATTEMPTED",
    "KB_SECRET_IN_OUTPUT",
)

ALL_REASON_CODES = BACKEND_REASON_CODES + KB_REASON_CODES

_overlap = set(BACKEND_REASON_CODES) & set(KB_REASON_CODES)
if _overlap:  # pragma: no cover - structural invariant, asserted at import
    raise AssertionError(
        "backend and KB reason-code namespaces overlap: %s" % ", ".join(sorted(_overlap))
    )
del _overlap


class ReasonError(Exception):
    """Raised when a reason is constructed with a code outside both namespaces."""


def reason(code, path, detail):
    """Build one machine-readable reason.

    `code` must be a known code. An unknown code raises rather than being passed through: a
    typo in a rejection reason is a silently weakened guard, because nothing downstream can
    match on a code that does not exist.
    """
    if code not in ALL_REASON_CODES:
        raise ReasonError("unknown reason code %r" % (code,))
    return {"code": code, "path": path, "detail": detail}


def codes_of(reasons):
    """The ordered list of codes in a reason list, for assertions and reports."""
    return [item["code"] for item in reasons]


def is_backend_code(code):
    return code in BACKEND_REASON_CODES
