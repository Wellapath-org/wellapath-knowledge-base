"""Contract pinning and drift detection.

The Knowledge Base validates descriptors offline against a *vendored* copy of the Backend
schema. That is only safe while the copy is provably the Backend's bytes, so every entry point
that reads the contract goes through `load_pinned_contract()`, which re-verifies the pin first
and raises otherwise. There is no "warn and continue" path: a drifted contract means the
descriptors this tooling would emit are validated against the wrong rules, and emitting them
anyway is worse than emitting nothing.

The pin record itself (`contracts/backend/PIN.json`) is hand-authored and never generated. The
merge commit and the retrieval timestamp are historical facts; a generator that recomputed
them would either invent them or churn on every run.
"""

import os
import re

from . import contract as contract_mirror
from .reasons import reason

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PIN_PATH = os.path.join(REPO_ROOT, "contracts", "backend", "PIN.json")
VENDORED_SCHEMA_PATH = os.path.join(REPO_ROOT, "contracts", "backend", "manifest.v1.schema.json")

#: Fields the pin must carry for the pin to mean anything. Absence is drift, not a default.
REQUIRED_PIN_FIELDS = (
    "pin_id",
    "pin_version",
    "backend",
    "contract",
    "vendored",
    "retrieval",
    "compatibility_policy",
    "representability",
)
REQUIRED_BACKEND_FIELDS = ("repository", "merge_commit", "source_path", "handoff_sha256")
REQUIRED_CONTRACT_FIELDS = ("contract_version", "supported_major", "schema_dialect", "schema_id")
REQUIRED_VENDORED_FIELDS = ("path", "sha256", "byte_count")
REQUIRED_RETRIEVAL_FIELDS = ("retrieved_at", "retrieved_from")
REQUIRED_POLICY_FIELDS = (
    "authority",
    "supported_majors",
    "on_major_unsupported",
    "on_vendored_hash_drift",
    "on_pin_hash_mismatch",
    "on_unrepresentable_rule",
    "on_kb_pass_backend_fail",
    "resolution_procedure",
)

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractPinError(Exception):
    """Raised when the pinned contract cannot be trusted. Never caught to continue."""

    def __init__(self, reasons):
        self.reasons = reasons
        super().__init__(
            "; ".join("%s at %s: %s" % (r["code"], r["path"], r["detail"]) for r in reasons)
        )


def _sha256_of_file(path):
    import hashlib

    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def check_pin(pin_path=PIN_PATH, schema_path=VENDORED_SCHEMA_PATH):
    """Return every reason the pin cannot be trusted. Empty means the contract is usable.

    Checks are exhaustive rather than short-circuiting wherever a later check is still
    meaningful, so a drift report names everything wrong in one pass.
    """
    import json

    reasons = []

    if not os.path.exists(pin_path):
        return [
            reason(
                "KB_CONTRACT_PIN_MISSING",
                _rel(pin_path),
                "the contract pin record is absent; the vendored schema cannot be trusted "
                "without it",
            )
        ]

    with open(pin_path, "rb") as handle:
        raw = handle.read()
    try:
        pin = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        return [
            reason("KB_CONTRACT_PIN_MALFORMED", _rel(pin_path), "pin is not valid JSON: %s" % error)
        ]
    if not isinstance(pin, dict):
        return [reason("KB_CONTRACT_PIN_MALFORMED", _rel(pin_path), "pin must be an object")]

    reasons.extend(_check_shape(pin, pin_path))
    if reasons:
        return reasons

    reasons.extend(_check_versions(pin, pin_path))
    reasons.extend(_check_vendored_bytes(pin, pin_path, schema_path))
    reasons.extend(_check_mirror_agrees(pin, schema_path))
    return reasons


def _rel(path):
    return os.path.relpath(path, REPO_ROOT)


def _check_shape(pin, pin_path):
    reasons = []
    path = _rel(pin_path)

    for field in REQUIRED_PIN_FIELDS:
        if field not in pin:
            reasons.append(
                reason(
                    "KB_CONTRACT_PIN_MALFORMED",
                    "%s.%s" % (path, field),
                    "required pin field is absent",
                )
            )
    if reasons:
        return reasons

    groups = (
        ("backend", REQUIRED_BACKEND_FIELDS),
        ("contract", REQUIRED_CONTRACT_FIELDS),
        ("vendored", REQUIRED_VENDORED_FIELDS),
        ("retrieval", REQUIRED_RETRIEVAL_FIELDS),
        ("compatibility_policy", REQUIRED_POLICY_FIELDS),
    )
    for group, fields in groups:
        value = pin[group]
        if not isinstance(value, dict):
            reasons.append(
                reason("KB_CONTRACT_PIN_MALFORMED", "%s.%s" % (path, group), "must be an object")
            )
            continue
        for field in fields:
            if field not in value:
                reasons.append(
                    reason(
                        "KB_CONTRACT_PIN_MALFORMED",
                        "%s.%s.%s" % (path, group, field),
                        "required pin field is absent",
                    )
                )

    if not reasons:
        commit = pin["backend"]["merge_commit"]
        if not isinstance(commit, str) or not _COMMIT_RE.match(commit):
            reasons.append(
                reason(
                    "KB_CONTRACT_PIN_MALFORMED",
                    "%s.backend.merge_commit" % path,
                    "must be a full 40-character commit sha, got %r" % (commit,),
                )
            )
        for where, value in (
            ("backend.handoff_sha256", pin["backend"]["handoff_sha256"]),
            ("vendored.sha256", pin["vendored"]["sha256"]),
        ):
            if not isinstance(value, str) or not _SHA256_RE.match(value):
                reasons.append(
                    reason(
                        "KB_CONTRACT_PIN_MALFORMED",
                        "%s.%s" % (path, where),
                        "must be a bare 64-character lowercase sha256 hex digest",
                    )
                )
    return reasons


def _check_versions(pin, pin_path):
    reasons = []
    path = _rel(pin_path)
    declared = pin["contract"]["contract_version"]

    if declared != contract_mirror.MANIFEST_CONTRACT_VERSION:
        reasons.append(
            reason(
                "KB_CONTRACT_MAJOR_UNSUPPORTED",
                "%s.contract.contract_version" % path,
                "pin declares contract %s but this tooling mirrors %s"
                % (declared, contract_mirror.MANIFEST_CONTRACT_VERSION),
            )
        )

    supported = pin["contract"]["supported_major"]
    if supported != contract_mirror.SUPPORTED_MANIFEST_MAJOR:
        reasons.append(
            reason(
                "KB_CONTRACT_MAJOR_UNSUPPORTED",
                "%s.contract.supported_major" % path,
                "pin supports major %r; this tooling implements major %r"
                % (supported, contract_mirror.SUPPORTED_MANIFEST_MAJOR),
            )
        )

    majors = pin["compatibility_policy"]["supported_majors"]
    if not isinstance(majors, list) or contract_mirror.SUPPORTED_MANIFEST_MAJOR not in majors:
        reasons.append(
            reason(
                "KB_CONTRACT_MAJOR_UNSUPPORTED",
                "%s.compatibility_policy.supported_majors" % path,
                "policy does not list major %d as supported"
                % contract_mirror.SUPPORTED_MANIFEST_MAJOR,
            )
        )

    for field in (
        "on_major_unsupported",
        "on_vendored_hash_drift",
        "on_pin_hash_mismatch",
        "on_unrepresentable_rule",
        "on_kb_pass_backend_fail",
    ):
        if pin["compatibility_policy"][field] != "fail_closed":
            reasons.append(
                reason(
                    "KB_CONTRACT_PIN_MALFORMED",
                    "%s.compatibility_policy.%s" % (path, field),
                    "every contract-failure policy must be fail_closed, got %r"
                    % (pin["compatibility_policy"][field],),
                )
            )
    return reasons


def _check_vendored_bytes(pin, pin_path, schema_path):
    reasons = []
    path = _rel(pin_path)
    declared_path = pin["vendored"]["path"]

    if declared_path != _rel(schema_path):
        reasons.append(
            reason(
                "KB_CONTRACT_PIN_MALFORMED",
                "%s.vendored.path" % path,
                "pin names %r but the vendored schema is read from %r"
                % (declared_path, _rel(schema_path)),
            )
        )

    if not os.path.exists(schema_path):
        reasons.append(
            reason(
                "KB_CONTRACT_SCHEMA_HASH_DRIFT",
                _rel(schema_path),
                "the vendored Backend schema is absent",
            )
        )
        return reasons

    actual_hash = _sha256_of_file(schema_path)
    actual_bytes = os.path.getsize(schema_path)

    if actual_hash != pin["vendored"]["sha256"]:
        reasons.append(
            reason(
                "KB_CONTRACT_SCHEMA_HASH_DRIFT",
                _rel(schema_path),
                "vendored schema hashes to %s but the pin records %s; the vendored bytes are "
                "no longer the Backend's bytes" % (actual_hash, pin["vendored"]["sha256"]),
            )
        )
    if actual_bytes != pin["vendored"]["byte_count"]:
        reasons.append(
            reason(
                "KB_CONTRACT_SCHEMA_HASH_DRIFT",
                _rel(schema_path),
                "vendored schema is %d bytes but the pin records %d"
                % (actual_bytes, pin["vendored"]["byte_count"]),
            )
        )
    return reasons


def _check_mirror_agrees(pin, schema_path):
    """The Python mirror in `contract.py` must agree with the vendored schema it mirrors.

    Without this the mirror could quietly relax a rule — accept an extra descriptor key, an
    extra release status — while the schema hash stayed perfectly valid.
    """
    import json

    reasons = []
    path = _rel(schema_path)

    if not os.path.exists(schema_path):
        return reasons

    with open(schema_path, "rb") as handle:
        schema = json.loads(handle.read().decode("utf-8"))

    if schema.get("contract_version") != contract_mirror.MANIFEST_CONTRACT_VERSION:
        reasons.append(
            reason(
                "KB_CONTRACT_SCHEMA_HASH_DRIFT",
                "%s.contract_version" % path,
                "schema declares contract %r, mirror declares %r"
                % (schema.get("contract_version"), contract_mirror.MANIFEST_CONTRACT_VERSION),
            )
        )
    if schema.get("$schema") != pin["contract"]["schema_dialect"]:
        reasons.append(
            reason(
                "KB_CONTRACT_PIN_MALFORMED",
                "%s.$schema" % path,
                "schema dialect %r does not match the pinned dialect %r"
                % (schema.get("$schema"), pin["contract"]["schema_dialect"]),
            )
        )
    if schema.get("$id") != pin["contract"]["schema_id"]:
        reasons.append(
            reason(
                "KB_CONTRACT_PIN_MALFORMED",
                "%s.$id" % path,
                "schema id %r does not match the pinned id %r"
                % (schema.get("$id"), pin["contract"]["schema_id"]),
            )
        )

    descriptor = schema["definitions"]["artifact_descriptor"]
    reasons.extend(
        _compare_sets(
            "%s.definitions.artifact_descriptor.required" % path,
            "required descriptor keys",
            descriptor["required"],
            contract_mirror.REQUIRED_DESCRIPTOR_KEYS,
        )
    )
    reasons.extend(
        _compare_sets(
            "%s.definitions.artifact_descriptor.properties" % path,
            "declared descriptor keys",
            descriptor["properties"].keys(),
            contract_mirror.ALLOWED_DESCRIPTOR_KEYS,
        )
    )
    reasons.extend(
        _compare_sets(
            "%s.properties" % path,
            "manifest keys",
            schema["properties"].keys(),
            contract_mirror.ALLOWED_MANIFEST_KEYS,
        )
    )
    reasons.extend(
        _compare_sets(
            "%s.required" % path,
            "required manifest keys",
            schema["required"],
            contract_mirror.REQUIRED_MANIFEST_KEYS,
        )
    )

    enums = (
        ("release_status", contract_mirror.RELEASE_STATUSES),
        ("activation_status", contract_mirror.ACTIVATION_STATUSES),
        ("content_type", contract_mirror.SUPPORTED_CONTENT_TYPES),
        ("schema_version", contract_mirror.SUPPORTED_ARTIFACT_SCHEMAS),
    )
    for field, mirrored in enums:
        reasons.extend(
            _compare_sets(
                "%s.definitions.artifact_descriptor.properties.%s.enum" % (path, field),
                "%s values" % field,
                descriptor["properties"][field]["enum"],
                mirrored,
            )
        )
    reasons.extend(
        _compare_sets(
            "%s.definitions.artifact_descriptor.properties.target_environments" % path,
            "environments",
            descriptor["properties"]["target_environments"]["items"]["enum"],
            contract_mirror.ENVIRONMENTS,
        )
    )
    reasons.extend(
        _compare_sets(
            "%s.definitions.approval_record.properties.status.enum" % path,
            "approval statuses",
            schema["definitions"]["approval_record"]["properties"]["status"]["enum"],
            contract_mirror.APPROVAL_STATUSES,
        )
    )
    reasons.extend(
        _compare_sets(
            "%s.definitions.blocker_record.properties.status.enum" % path,
            "blocker statuses",
            schema["definitions"]["blocker_record"]["properties"]["status"]["enum"],
            contract_mirror.BLOCKER_STATUSES,
        )
    )

    patterns = (
        ("artifact_id", contract_mirror.ARTIFACT_ID_PATTERN),
        ("artifact_version", contract_mirror.VERSION_PATTERN),
        ("sha256", contract_mirror.SHA256_PATTERN),
        ("object_key", contract_mirror.OBJECT_KEY_PATTERN),
        ("country", contract_mirror.COUNTRY_PATTERN),
    )
    for field, mirrored in patterns:
        declared = descriptor["properties"][field].get("pattern")
        if declared != mirrored:
            reasons.append(
                reason(
                    "KB_CONTRACT_SCHEMA_HASH_DRIFT",
                    "%s.definitions.artifact_descriptor.properties.%s.pattern" % (path, field),
                    "schema pattern %r does not match the mirrored pattern %r"
                    % (declared, mirrored),
                )
            )
    return reasons


def _compare_sets(path, label, schema_values, mirrored_values):
    schema_set = set(schema_values)
    mirror_set = set(mirrored_values)
    if schema_set == mirror_set:
        return []
    missing = sorted(schema_set - mirror_set)
    extra = sorted(mirror_set - schema_set)
    detail = "%s disagree between the vendored schema and the Python mirror" % label
    if missing:
        detail += "; in schema but not mirrored: %s" % ", ".join(missing)
    if extra:
        detail += "; mirrored but not in schema: %s" % ", ".join(extra)
    return [reason("KB_CONTRACT_SCHEMA_HASH_DRIFT", path, detail)]


def load_pin(pin_path=PIN_PATH, schema_path=VENDORED_SCHEMA_PATH):
    """Return the verified pin record, or raise `ContractPinError`."""
    import json

    reasons = check_pin(pin_path, schema_path)
    if reasons:
        raise ContractPinError(reasons)
    with open(pin_path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def load_pinned_contract(pin_path=PIN_PATH, schema_path=VENDORED_SCHEMA_PATH):
    """Return `(pin_record, schema_object)` after proving the pin holds.

    This is the only supported way to read the contract. Reading the vendored file directly
    would skip drift detection, which is the whole point of vendoring it.
    """
    import json

    pin = load_pin(pin_path, schema_path)
    with open(schema_path, "rb") as handle:
        schema = json.loads(handle.read().decode("utf-8"))
    return pin, schema


def pin_summary(pin):
    """The subset of the pin worth restating inside a generated plan."""
    return {
        "backend_repository": pin["backend"]["repository"],
        "backend_merge_commit": pin["backend"]["merge_commit"],
        "contract_version": pin["contract"]["contract_version"],
        "supported_major": pin["contract"]["supported_major"],
        "schema_source_path": pin["backend"]["source_path"],
        "schema_sha256": pin["vendored"]["sha256"],
        "schema_byte_count": pin["vendored"]["byte_count"],
        "vendored_path": pin["vendored"]["path"],
        "handoff_sha256": pin["backend"]["handoff_sha256"],
        "retrieved_at": pin["retrieval"]["retrieved_at"],
        "compatibility_policy": "fail_closed on pin drift, schema hash drift, unsupported "
        "major, unrepresentable rule, or KB-accepts/Backend-rejects disagreement",
    }
