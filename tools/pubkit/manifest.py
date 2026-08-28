"""Structural validation of a candidate manifest.

A port of `wellapath-backend/src/manifest/validate.ts` at the pinned commit, plus a check the
Backend cannot perform: the *vendored schema* is run over the manifest too, so a document has
to satisfy both the published schema and the Backend's hand-written validator. The schema and
the validator are supposed to agree; running both means a disagreement surfaces here rather
than after a descriptor has already been handed over.

Everything fails closed. Unknown fields, unknown enum values, unknown manifest majors and
unknown required features are explicit rejections with a machine-readable reason — never
silently ignored, never defaulted. A manifest that does not validate must not be consulted for
eligibility at all.
"""

import re

from . import contract as c
from .origin import validate_artifact_url, validate_object_key
from .reasons import reason

_ARTIFACT_ID_RE = re.compile(c.ARTIFACT_ID_PATTERN)
_VERSION_RE = re.compile(c.VERSION_PATTERN)
_SEMVER_RE = re.compile(c.SEMVER_PATTERN)
_COUNTRY_RE = re.compile(c.COUNTRY_PATTERN)
_SHA256_RE = re.compile(c.SHA256_PATTERN)
_ISO_RE = re.compile(c.ISO_DATETIME_PATTERN)


def _is_object(value):
    return isinstance(value, dict)


def _is_iso_datetime(value):
    if not isinstance(value, str) or not _ISO_RE.match(value):
        return False
    # The Backend additionally requires Date.parse to succeed, which rejects impossible dates
    # that still match the shape (month 13, day 32). datetime does the same job here.
    import datetime

    try:
        datetime.datetime.strptime(value.split(".")[0].rstrip("Z"), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return False
    return True


def _missing(path, key):
    return reason("MISSING_REQUIRED_FIELD", "%s.%s" % (path, key), "required field %s is absent" % key)


def _malformed(path, detail):
    return reason("MALFORMED_FIELD", path, detail)


def _validate_version_ref(value, path):
    if value is None:
        return []
    if not _is_object(value):
        return [_malformed(path, "must be null or an object")]

    reasons = []
    for key in value:
        if key not in c.VERSION_REF_KEYS:
            reasons.append(reason("UNKNOWN_FIELD", "%s.%s" % (path, key), "unknown field"))
    version = value.get("artifact_version")
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        reasons.append(_malformed("%s.artifact_version" % path, "must be a dotted numeric version string"))
    digest = value.get("sha256")
    if not isinstance(digest, str) or not _SHA256_RE.match(digest):
        reasons.append(_malformed("%s.sha256" % path, "must be a sha256:<64 hex> digest"))
    return reasons


def _validate_approval(value, path):
    if not _is_object(value):
        return [reason("APPROVAL_MISSING", path, "approval record is absent or malformed")]

    reasons = []
    for key in value:
        if key not in c.APPROVAL_RECORD_KEYS:
            reasons.append(reason("UNKNOWN_FIELD", "%s.%s" % (path, key), "unknown field"))
    for key in c.APPROVAL_RECORD_KEYS:
        if key not in value:
            reasons.append(_missing(path, key))

    if "required" in value and not isinstance(value["required"], bool):
        reasons.append(_malformed("%s.required" % path, "must be a boolean"))
    if "status" in value:
        status = value["status"]
        if not isinstance(status, str) or status not in c.APPROVAL_STATUSES:
            reasons.append(
                reason(
                    "APPROVAL_STATUS_UNKNOWN",
                    "%s.status" % path,
                    "approval status %r is not a known status" % (status,),
                )
            )
        elif status == "granted" and value.get("decision_ref", "missing") is None:
            reasons.append(_malformed("%s.decision_ref" % path, "a granted approval must cite a decision"))
    if "decision_ref" in value and value["decision_ref"] is not None:
        ref = value["decision_ref"]
        if not isinstance(ref, str) or ref.strip() == "":
            reasons.append(_malformed("%s.decision_ref" % path, "must be null or a non-empty string"))
    if "approved_at" in value and value["approved_at"] is not None:
        if not _is_iso_datetime(value["approved_at"]):
            reasons.append(_malformed("%s.approved_at" % path, "must be null or an ISO-8601 UTC datetime"))
    return reasons


def _validate_blockers(value, path):
    if not isinstance(value, list):
        return [_malformed(path, "must be an array")]

    reasons = []
    for index, blocker in enumerate(value):
        blocker_path = "%s[%d]" % (path, index)
        if not _is_object(blocker):
            reasons.append(_malformed(blocker_path, "must be an object"))
            continue
        for key in blocker:
            if key not in c.BLOCKER_RECORD_KEYS:
                reasons.append(reason("UNKNOWN_FIELD", "%s.%s" % (blocker_path, key), "unknown field"))
        if not isinstance(blocker.get("id"), str) or blocker.get("id", "").strip() == "":
            reasons.append(_malformed("%s.id" % blocker_path, "must be a non-empty string"))
        status = blocker.get("status")
        if not isinstance(status, str) or status not in c.BLOCKER_STATUSES:
            reasons.append(_malformed("%s.status" % blocker_path, "must be open or resolved"))
        if "reference" in blocker and not isinstance(blocker["reference"], str):
            reasons.append(_malformed("%s.reference" % blocker_path, "must be a string when present"))
    return reasons


def validate_descriptor(value, path):
    """Every reason one descriptor is unusable. Empty means it is structurally sound."""
    if not _is_object(value):
        return [_malformed(path, "artifact descriptor must be an object")]

    reasons = []

    for key in value:
        if key not in c.ALLOWED_DESCRIPTOR_KEYS:
            reasons.append(reason("UNKNOWN_FIELD", "%s.%s" % (path, key), "unknown field"))
    for key in c.REQUIRED_DESCRIPTOR_KEYS:
        if key not in value:
            reasons.append(_missing(path, key))

    if "artifact_id" in value:
        if not isinstance(value["artifact_id"], str) or not _ARTIFACT_ID_RE.match(value["artifact_id"]):
            reasons.append(_malformed("%s.artifact_id" % path, "must be a stable snake_case identifier"))
    if "artifact_version" in value:
        if not isinstance(value["artifact_version"], str) or not _VERSION_RE.match(value["artifact_version"]):
            reasons.append(_malformed("%s.artifact_version" % path, "must be a dotted numeric version string"))
    if "schema_version" in value:
        if not isinstance(value["schema_version"], str):
            reasons.append(_malformed("%s.schema_version" % path, "must be a string"))
        elif value["schema_version"] not in c.SUPPORTED_ARTIFACT_SCHEMAS:
            reasons.append(
                reason(
                    "UNSUPPORTED_ARTIFACT_SCHEMA",
                    "%s.schema_version" % path,
                    "artifact schema %s is not supported" % value["schema_version"],
                )
            )
    if "content_type" in value:
        if not isinstance(value["content_type"], str) or value["content_type"] not in c.SUPPORTED_CONTENT_TYPES:
            reasons.append(
                reason(
                    "CONTENT_TYPE_UNSUPPORTED",
                    "%s.content_type" % path,
                    "content type %r is not an expected artifact type" % (value.get("content_type"),),
                )
            )
    if "sha256" in value:
        if not isinstance(value["sha256"], str) or not _SHA256_RE.match(value["sha256"]):
            reasons.append(_malformed("%s.sha256" % path, "must be a sha256:<64 hex> digest"))
    if "byte_count" in value:
        count = value["byte_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            reasons.append(_malformed("%s.byte_count" % path, "must be a positive integer"))
    if "object_key" in value:
        if not isinstance(value["object_key"], str):
            reasons.append(_malformed("%s.object_key" % path, "must be a string"))
        else:
            reasons.extend(validate_object_key(value["object_key"], "%s.object_key" % path))
            if "url" in value:
                reasons.extend(validate_artifact_url(value["url"], value["object_key"], "%s.url" % path))
    if "release_status" in value:
        status = value["release_status"]
        if not isinstance(status, str) or status not in c.RELEASE_STATUSES:
            reasons.append(_malformed("%s.release_status" % path, "must be a known release status"))
        elif status == "published" and value.get("published_at", "missing") is None:
            reasons.append(_malformed("%s.published_at" % path, "a published artifact must carry a date"))
    if "activation_status" in value:
        status = value["activation_status"]
        if not isinstance(status, str) or status not in c.ACTIVATION_STATUSES:
            reasons.append(_malformed("%s.activation_status" % path, "must be inactive or active"))
    if "activation_authorized" in value:
        authorized = value["activation_authorized"]
        if not isinstance(authorized, bool):
            reasons.append(_malformed("%s.activation_authorized" % path, "must be a boolean"))
        elif authorized is True and value.get("activation_decision_ref", "missing") is None:
            reasons.append(_malformed("%s.activation_decision_ref" % path, "authorization must cite a decision"))
    if "activation_decision_ref" in value:
        ref = value["activation_decision_ref"]
        if ref is not None and not isinstance(ref, str):
            reasons.append(_malformed("%s.activation_decision_ref" % path, "must be null or a string"))
    if "target_environments" in value:
        environments = value["target_environments"]
        if not isinstance(environments, list) or len(environments) == 0:
            reasons.append(_malformed("%s.target_environments" % path, "must be a non-empty array"))
        else:
            for index, environment in enumerate(environments):
                if not isinstance(environment, str) or environment not in c.ENVIRONMENTS:
                    reasons.append(
                        _malformed("%s.target_environments[%d]" % (path, index), "unknown environment name")
                    )
            if len(set(map(repr, environments))) != len(environments):
                reasons.append(_malformed("%s.target_environments" % path, "environments must be unique"))
    if "min_app_build" in value:
        build = value["min_app_build"]
        if isinstance(build, bool) or not isinstance(build, int) or build < 1:
            reasons.append(_malformed("%s.min_app_build" % path, "must be a positive integer when present"))
    if "publication_decision_ref" in value:
        ref = value["publication_decision_ref"]
        if ref is not None and not isinstance(ref, str):
            reasons.append(_malformed("%s.publication_decision_ref" % path, "must be null or a string"))
    if "approvals" in value:
        approvals = value["approvals"]
        if not _is_object(approvals):
            reasons.append(
                reason(
                    "APPROVAL_MISSING",
                    "%s.approvals" % path,
                    "approvals must be an object with product and clinical records",
                )
            )
        else:
            for key in approvals:
                if key not in c.APPROVAL_ROLES:
                    reasons.append(reason("UNKNOWN_FIELD", "%s.approvals.%s" % (path, key), "unknown field"))
            for role in c.APPROVAL_ROLES:
                if role not in approvals:
                    reasons.append(
                        reason(
                            "APPROVAL_MISSING",
                            "%s.approvals.%s" % (path, role),
                            "%s approval record is absent" % role,
                        )
                    )
                else:
                    reasons.extend(_validate_approval(approvals[role], "%s.approvals.%s" % (path, role)))
    if "blockers" in value:
        reasons.extend(_validate_blockers(value["blockers"], "%s.blockers" % path))
    if "predecessor" in value:
        reasons.extend(_validate_version_ref(value["predecessor"], "%s.predecessor" % path))
    if "rollback_target" in value:
        reasons.extend(_validate_version_ref(value["rollback_target"], "%s.rollback_target" % path))
    if "created_at" in value and not _is_iso_datetime(value["created_at"]):
        reasons.append(_malformed("%s.created_at" % path, "must be an ISO-8601 UTC datetime"))
    if "published_at" in value and value["published_at"] is not None:
        if not _is_iso_datetime(value["published_at"]):
            reasons.append(_malformed("%s.published_at" % path, "must be null or an ISO-8601 UTC datetime"))
    if "deprecated" in value and not isinstance(value["deprecated"], bool):
        reasons.append(_malformed("%s.deprecated" % path, "must be a boolean"))
    if "expires_at" in value and value["expires_at"] is not None:
        if not _is_iso_datetime(value["expires_at"]):
            reasons.append(_malformed("%s.expires_at" % path, "must be null or an ISO-8601 UTC datetime"))
    if "country" in value:
        if not isinstance(value["country"], str) or not _COUNTRY_RE.match(value["country"]):
            reasons.append(_malformed("%s.country" % path, "must be a two-letter lowercase country code"))
    if "references" in value:
        refs = value["references"]
        if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
            reasons.append(_malformed("%s.references" % path, "must be an array of strings when present"))

    return reasons


def _find_relationship_cycles(manifest):
    """Cycles in predecessor / rollback relationships within one artifact line."""
    reasons = []
    by_id = {}

    for descriptor in manifest["artifacts"]:
        versions = by_id.setdefault(descriptor["artifact_id"], {})
        targets = []
        if descriptor.get("predecessor"):
            targets.append(descriptor["predecessor"]["artifact_version"])
        if descriptor.get("rollback_target"):
            targets.append(descriptor["rollback_target"]["artifact_version"])
        versions[descriptor["artifact_version"]] = targets

    for artifact_id in by_id:
        versions = by_id[artifact_id]
        visiting = set()
        done = set()

        def visit(version, trail):
            if version in done:
                return
            if version in visiting:
                reasons.append(
                    reason(
                        "RELATIONSHIP_CYCLE",
                        "artifacts(%s)" % artifact_id,
                        "predecessor/rollback relationship cycle: %s" % " -> ".join(trail + [version]),
                    )
                )
                return
            visiting.add(version)
            for target in versions.get(version, []):
                if target in versions:
                    visit(target, trail + [version])
            visiting.discard(version)
            done.add(version)

        for version in list(versions):
            visit(version, [])

    return reasons


def _validate_rollback_targets(manifest):
    """Rollback targets are operational pointers and must resolve, exactly, inside the manifest."""
    reasons = []

    for index, descriptor in enumerate(manifest["artifacts"]):
        target = descriptor.get("rollback_target")
        if target is None:
            continue

        path = "artifacts[%d].rollback_target" % index
        if (
            target["artifact_version"] == descriptor["artifact_version"]
            or target["sha256"] == descriptor["sha256"]
        ):
            reasons.append(
                reason("RELATIONSHIP_CYCLE", path, "rollback target references the descriptor itself")
            )
            continue

        resolved = None
        for candidate in manifest["artifacts"]:
            if (
                candidate["artifact_id"] == descriptor["artifact_id"]
                and candidate["artifact_version"] == target["artifact_version"]
            ):
                resolved = candidate
                break

        if resolved is None:
            reasons.append(
                reason(
                    "INVALID_ROLLBACK_TARGET",
                    path,
                    "no descriptor for %s@%s exists in the manifest"
                    % (descriptor["artifact_id"], target["artifact_version"]),
                )
            )
        elif resolved["sha256"] != target["sha256"]:
            reasons.append(
                reason(
                    "INVALID_ROLLBACK_TARGET",
                    path,
                    "rollback target sha256 does not match the referenced descriptor",
                )
            )

    return reasons


def validate_manifest(value):
    """Validate a parsed JSON document as a candidate manifest.

    Returns `(valid, reasons)`. The manifest is usable only when `valid` is true; a rejected
    manifest must not be consulted for eligibility.
    """
    if not _is_object(value):
        return False, [reason("MANIFEST_MALFORMED", "$", "manifest must be an object")]

    reasons = []
    for key in value:
        if key not in c.ALLOWED_MANIFEST_KEYS:
            reasons.append(reason("UNKNOWN_FIELD", "$.%s" % key, "unknown field"))
    for key in c.REQUIRED_MANIFEST_KEYS:
        if key not in value:
            reasons.append(_missing("$", key))

    if "manifest_version" in value:
        version = value["manifest_version"]
        match = _SEMVER_RE.match(version) if isinstance(version, str) else None
        if match is None:
            reasons.append(
                reason(
                    "MANIFEST_VERSION_UNSUPPORTED",
                    "$.manifest_version",
                    "manifest version %r is not a semantic version" % (version,),
                )
            )
        elif int(match.group(1)) != c.SUPPORTED_MANIFEST_MAJOR:
            reasons.append(
                reason(
                    "MANIFEST_VERSION_UNSUPPORTED",
                    "$.manifest_version",
                    "manifest major %s is not supported (supported: %d)"
                    % (match.group(1), c.SUPPORTED_MANIFEST_MAJOR),
                )
            )
    if "generated_at" in value and not _is_iso_datetime(value["generated_at"]):
        reasons.append(_malformed("$.generated_at", "must be an ISO-8601 UTC datetime"))
    if "required_features" in value:
        features = value["required_features"]
        if not isinstance(features, list) or any(not isinstance(item, str) for item in features):
            reasons.append(_malformed("$.required_features", "must be an array of strings when present"))
        else:
            for feature in features:
                if feature not in c.SUPPORTED_MANIFEST_FEATURES:
                    reasons.append(
                        reason(
                            "UNKNOWN_REQUIRED_FEATURE",
                            "$.required_features",
                            "required feature %s is not supported by this implementation" % feature,
                        )
                    )

    if "artifacts" in value:
        artifacts = value["artifacts"]
        if not isinstance(artifacts, list):
            reasons.append(_malformed("$.artifacts", "must be an array"))
        else:
            for index, descriptor in enumerate(artifacts):
                reasons.extend(validate_descriptor(descriptor, "artifacts[%d]" % index))

            seen = {}
            for index, descriptor in enumerate(artifacts):
                if not _is_object(descriptor):
                    continue
                identity = "%s@%s" % (descriptor.get("artifact_id"), descriptor.get("artifact_version"))
                if identity in seen:
                    reasons.append(
                        reason(
                            "DUPLICATE_IDENTITY",
                            "artifacts[%d]" % index,
                            "duplicate identity %s (first declared at artifacts[%d])" % (identity, seen[identity]),
                        )
                    )
                else:
                    seen[identity] = index

    # Relationship checks only make sense on a structurally sound manifest.
    if not reasons:
        reasons.extend(_find_relationship_cycles(value))
        reasons.extend(_validate_rollback_targets(value))

    return (not reasons), reasons


def validate_against_vendored_schema(value, schema):
    """Run the vendored Backend schema over a manifest, alongside the ported validator.

    The schema and the Backend's own validator are meant to agree, and the Backend has a test
    asserting they do. Running both here means that if they ever stop agreeing, the KB finds
    out at generation time instead of shipping a descriptor one of them would reject.
    """
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from vocab.schema_check import validate as schema_validate

    errors = schema_validate(value, schema, extra_keywords=c.SCHEMA_ANNOTATION_KEYWORDS)
    return [reason("MANIFEST_MALFORMED", "$", "vendored schema: %s" % message) for message in errors]
