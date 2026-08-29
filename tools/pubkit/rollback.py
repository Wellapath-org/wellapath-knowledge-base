"""Rollback preparation.

A rollback target is an *operational pointer*: at the moment it is used, something will serve
the bytes it names. So it has to be bound tightly enough that there is no room to interpret it
— an exact version AND the exact sha256 of that version's bytes, resolvable in the governed
inventory today.

The Backend already refuses a downgrade with no version-and-hash-bound `rollback_target`
(`authorizeTransition`) and refuses a target that does not resolve inside the manifest
(`validateRollbackTargets`). This module is what runs *before* a descriptor is written: it
checks the proposal against this repository's real inventory, so a target that cannot possibly
resolve is caught while it is still an idea rather than after it has been handed over.

Nothing here changes an active version, and nothing here reads or writes an artifact's bytes
beyond hashing what is already on disk.
"""

from .eligibility import compare_versions
from .inventory import find
from .reasons import reason

#: Rolling back to content whose approval has lapsed is not automatically wrong — the whole
#: point of a rollback is often to return to something that was superseded. But it is not
#: automatically right either, and contract 1.1.0 defines no policy for it. Until one exists,
#: the answer is refusal with a named reason rather than a guess in either direction.
UNAUTHORIZED_TARGET_POLICY = (
    "Contract 1.0.0 defines no policy for rolling back to content whose approval has expired, "
    "been revoked or been superseded. This tooling therefore refuses it. A future explicit "
    "policy may permit it; inventing one here would be inventing governance."
)


def check_rollback_target(
    target,
    descriptor_artifact_id,
    descriptor_version,
    descriptor_schema_version,
    entries,
    governance_status=None,
    path="rollback_target",
):
    """Every reason a proposed rollback target is unusable.

    `target` is `None` (no rollback proposed — always fine) or a `{artifact_version, sha256}`
    version ref. `governance_status` optionally maps `"artifact_id@version"` to one of
    `"authorized"`, `"expired"`, `"revoked"`, `"superseded"` or `"unknown"`; anything but
    `"authorized"` is refused under the policy above.
    """
    if target is None:
        return []

    reasons = []

    if not isinstance(target, dict):
        return [reason("KB_ROLLBACK_UNBOUND_VERSION_ONLY", path, "rollback target must be an object")]

    version = target.get("artifact_version")
    digest = target.get("sha256")

    if version is None:
        return [
            reason(
                "KB_ROLLBACK_UNBOUND_VERSION_ONLY",
                "%s.artifact_version" % path,
                "a rollback target must name a version",
            )
        ]
    if digest is None or digest == "":
        return [
            reason(
                "KB_ROLLBACK_UNBOUND_VERSION_ONLY",
                "%s.sha256" % path,
                "rollback target names version %s but no hash; a version-only target points at "
                "whatever that version happens to be, which is exactly what immutability is "
                "supposed to rule out" % version,
            )
        ]

    if "artifact_id" in target and target["artifact_id"] != descriptor_artifact_id:
        reasons.append(
            reason(
                "KB_ROLLBACK_CROSS_ARTIFACT",
                "%s.artifact_id" % path,
                "rollback target names artifact %s while the descriptor is %s; rollback moves "
                "an artifact line backwards, it does not swap one artifact for another"
                % (target["artifact_id"], descriptor_artifact_id),
            )
        )

    if version == descriptor_version:
        reasons.append(
            reason(
                "KB_ROLLBACK_CYCLE",
                path,
                "rollback target is the descriptor's own version %s" % version,
            )
        )
    elif compare_versions(version, descriptor_version) > 0:
        reasons.append(
            reason(
                "KB_ROLLBACK_CYCLE",
                path,
                "rollback target %s is ahead of the descriptor version %s; that is a forward "
                "transition wearing a rollback's name" % (version, descriptor_version),
            )
        )

    entry = find(entries, descriptor_artifact_id, version)
    if entry is None:
        reasons.append(
            reason(
                "KB_ROLLBACK_TARGET_NOT_IN_INVENTORY",
                path,
                "no governed artifact %s@%s exists in this repository; a rollback target that "
                "is not addressable is not a target" % (descriptor_artifact_id, version),
            )
        )
        return reasons

    if entry["descriptor_sha256"] != digest:
        reasons.append(
            reason(
                "KB_ROLLBACK_HASH_MISMATCH",
                "%s.sha256" % path,
                "rollback target declares %s but %s hashes to %s"
                % (digest, entry["repository_path"], entry["descriptor_sha256"]),
            )
        )

    target_schema = _schema_version_of(entry)
    if target_schema is not None and descriptor_schema_version is not None:
        if target_schema != descriptor_schema_version:
            reasons.append(
                reason(
                    "KB_ROLLBACK_SCHEMA_INCOMPATIBLE",
                    path,
                    "rollback target declares content schema %r while the descriptor declares "
                    "%r; a consumer that upgraded its parser cannot read the older shape"
                    % (target_schema, descriptor_schema_version),
                )
            )

    if governance_status is not None:
        identity = "%s@%s" % (descriptor_artifact_id, version)
        status = governance_status.get(identity, "unknown")
        if status != "authorized":
            reasons.append(
                reason(
                    "KB_ROLLBACK_TARGET_UNAUTHORIZED",
                    path,
                    "rollback target %s is %s. %s" % (identity, status, UNAUTHORIZED_TARGET_POLICY),
                )
            )

    return reasons


def _schema_version_of(entry):
    """The artifact's own declared content-schema version, when it declares one.

    This is the artifact's internal `schema_version` (`2.0`, `1.1`), not the manifest contract's
    `schema_version` field, which is always `wellapath.artifact/1`. Conflating the two is easy
    and would make every rollback look compatible.
    """
    import json
    import os

    from .inventory import REPO_ROOT

    path = os.path.join(REPO_ROOT, entry["repository_path"])
    try:
        with open(path, "rb") as handle:
            document = json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    metadata = document.get("_metadata")
    if isinstance(metadata, dict) and "schema_version" in metadata:
        return metadata["schema_version"]
    if "schema_version" in document:
        return document["schema_version"]
    return None


def propose_predecessor(entries, artifact_id, artifact_version):
    """The immediately preceding governed version of an artifact line, as a bound version ref.

    Returns `None` when there is no earlier version. A predecessor is a lineage statement, not
    a rollback authorization: naming one grants nothing.
    """
    line = [
        entry
        for entry in entries
        if entry["artifact_id"] == artifact_id
        and compare_versions(entry["artifact_version"], artifact_version) < 0
    ]
    if not line:
        return None
    line.sort(key=lambda entry: [int(part) for part in entry["artifact_version"].split(".")])
    previous = line[-1]
    return {
        "artifact_version": previous["artifact_version"],
        "sha256": previous["descriptor_sha256"],
    }
