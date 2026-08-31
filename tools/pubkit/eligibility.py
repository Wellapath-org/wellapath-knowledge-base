"""Eligibility and activation semantics — the fail-closed core.

A port of `wellapath-backend/src/manifest/eligibility.ts` at the pinned commit
(`bbaeadd6075eb37fd51acbe04101f939e52c7d48`, contract 1.1.0). Five states, never synonyms:

    present                  — the descriptor exists and is structurally sound.
    published                — release status is `published`, with a publication date.
    approved                 — every required approval is explicitly `granted` with a decision
                               reference. Absent, pending, denied, unknown or malformed
                               approval data all mean NOT approved.
    active                   — activation is explicitly `active` AND explicitly authorized.
    eligible_for_environment — everything the environment requires holds at once.

The port matters more than it looks. If the Knowledge Base computed eligibility its own way,
a plan could report a candidate as blocked for one reason while the Backend blocks it for
another — or worse, report it as ready when the Backend would refuse it. Sharing the
implementation means a KB dry-run answers the same question the Backend will answer.
"""

import datetime
import re

from . import contract as c
from .reasons import reason

_SHA256_RE = re.compile(c.SHA256_PATTERN)


def _descriptor_path(descriptor):
    """The location label used in this descriptor's reasons.

    The Backend writes `artifact question_flow@1.1`; this writes `artifact question_flow v1.1`.
    The difference is cosmetic — reason *codes* are the contract, message text is not — and it
    is deliberate: `question_flow@1.1.approvals.clinical` is indistinguishable from an email
    address to a PHI scanner, and a repository-wide scan that reports eighteen false positives
    on every plan is a scan people learn to skim.
    """
    return "artifact %s v%s" % (descriptor.get("artifact_id"), descriptor.get("artifact_version"))


def _evaluate_approval_scope(approval, path, role):
    """Whether the decision an approval cites was actually scoped to artifact publication.

    New in contract 1.1.0. Re-checked here as well as in `manifest.py` on purpose: a descriptor
    evaluated in isolation must fail closed rather than inherit a guarantee from a validation
    pass that may never have run. An empty result means the scope is sound.
    """
    scope = approval.get("decision_scope")
    scope_path = "%s.decision_scope" % path

    if scope is None:
        return [
            reason(
                "APPROVAL_SCOPE_MISSING",
                scope_path,
                "%s approval cites a decision with no recorded scope; an unscoped decision is "
                "not an artifact-publication approval" % role,
            )
        ]
    if not isinstance(scope, list) or len(scope) == 0:
        return [
            reason(
                "APPROVAL_SCOPE_MISSING",
                scope_path,
                "%s approval declares a malformed scope; treated as no scope at all" % role,
            )
        ]
    unknown = [
        entry for entry in scope if not isinstance(entry, str) or entry not in c.APPROVAL_SCOPES
    ]
    if unknown:
        return [
            reason(
                "APPROVAL_SCOPE_UNKNOWN",
                scope_path,
                "%s approval declares unrecognised scope %s; unknown scope is never read as "
                "authorisation" % (role, ", ".join(str(entry) for entry in unknown)),
            )
        ]
    if c.ARTIFACT_APPROVAL_SLOT_SCOPE not in scope:
        return [
            reason(
                "APPROVAL_SCOPE_MISMATCH",
                scope_path,
                "%s approval cites a decision scoped to %s; that scope excludes %s, so it "
                "cannot stand as an artifact-publication approval"
                % (role, ", ".join(scope), c.ARTIFACT_APPROVAL_SLOT_SCOPE),
            )
        ]
    return []


def _parse_iso(value):
    """Parse an ISO-8601 UTC datetime to epoch seconds, or None when unparseable."""
    if not isinstance(value, str):
        return None
    text = value.rstrip("Z")
    for pattern in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.datetime.strptime(text, pattern)
        except ValueError:
            continue
        return parsed.replace(tzinfo=datetime.timezone.utc).timestamp()
    return None


def evaluate_descriptor(descriptor, environment, app_build=None, now=None):
    """Evaluate one descriptor's five states against an environment.

    Governance data is re-checked defensively even for a descriptor that already passed
    structural validation, so a malformed descriptor evaluated in isolation still fails closed
    rather than passing by omission.

    Returns `(states, reasons)`.
    """
    reasons = []
    path = _descriptor_path(descriptor)

    present = (
        isinstance(descriptor.get("artifact_id"), str)
        and isinstance(descriptor.get("artifact_version"), str)
        and isinstance(descriptor.get("sha256"), str)
        and bool(_SHA256_RE.match(descriptor.get("sha256") or ""))
        and isinstance(descriptor.get("byte_count"), int)
        and not isinstance(descriptor.get("byte_count"), bool)
        and descriptor.get("byte_count", 0) > 0
    )
    if not present:
        reasons.append(
            reason("MALFORMED_FIELD", path, "descriptor lacks sound identity or integrity metadata")
        )

    published_at = descriptor.get("published_at")
    published = (
        descriptor.get("release_status") == "published"
        and isinstance(published_at, str)
        and len(published_at) > 0
    )
    if not published:
        reasons.append(
            reason(
                "NOT_PUBLISHED",
                path,
                "release status is %s; only an explicitly published artifact can be distributed"
                % (descriptor.get("release_status"),),
            )
        )

    approved = True
    approvals = descriptor.get("approvals")
    if not isinstance(approvals, dict):
        approved = False
        reasons.append(
            reason(
                "APPROVAL_MISSING",
                "%s.approvals" % path,
                "approvals are absent; absence means not approved",
            )
        )
    else:
        for role in c.APPROVAL_ROLES:
            approval = approvals.get(role)
            if not isinstance(approval, dict):
                approved = False
                reasons.append(
                    reason(
                        "APPROVAL_MISSING",
                        "%s.approvals.%s" % (path, role),
                        "%s approval record is absent; absence means not approved" % role,
                    )
                )
                continue
            required = approval.get("required")
            if required is False:
                # Explicitly not required — every other value is fail-closed below.
                continue
            if required is not True:
                approved = False
                reasons.append(
                    reason(
                        "APPROVAL_MISSING",
                        "%s.approvals.%s.required" % (path, role),
                        "approval requirement is not explicitly declared; treated as not approved",
                    )
                )
                continue
            status = approval.get("status")
            if status not in c.APPROVAL_STATUSES:
                approved = False
                reasons.append(
                    reason(
                        "APPROVAL_STATUS_UNKNOWN",
                        "%s.approvals.%s.status" % (path, role),
                        "unknown approval status %r; treated as not approved" % (status,),
                    )
                )
                continue
            decision_ref = approval.get("decision_ref")
            if status != "granted" or not isinstance(decision_ref, str) or decision_ref.strip() == "":
                approved = False
                reasons.append(
                    reason(
                        "APPROVAL_NOT_GRANTED",
                        "%s.approvals.%s" % (path, role),
                        "%s approval is required but not explicitly granted with a decision "
                        "reference" % role,
                    )
                )
                continue
            # The approval claims to be granted. It only counts if the decision it cites was
            # actually scoped to artifact publication — a decision taken for some other
            # purpose, however complete and however senior its author, authorises nothing here.
            scope_reasons = _evaluate_approval_scope(
                approval, "%s.approvals.%s" % (path, role), role
            )
            if scope_reasons:
                approved = False
                reasons.extend(scope_reasons)

    blockers_resolved = True
    blockers = descriptor.get("blockers")
    if not isinstance(blockers, list):
        blockers_resolved = False
        reasons.append(
            reason("BLOCKER_UNRESOLVED", "%s.blockers" % path, "blocker list is malformed; treated as blocked")
        )
    else:
        for blocker in blockers:
            status = blocker.get("status") if isinstance(blocker, dict) else None
            if status != "resolved":
                blockers_resolved = False
                reasons.append(
                    reason(
                        "BLOCKER_UNRESOLVED",
                        "%s.blockers" % path,
                        "blocker %s is %s"
                        % (blocker.get("id") if isinstance(blocker, dict) else blocker, status),
                    )
                )

    activation_ref = descriptor.get("activation_decision_ref")
    activation_authorized = (
        descriptor.get("activation_authorized") is True
        and isinstance(activation_ref, str)
        and activation_ref.strip() != ""
    )
    if not activation_authorized:
        reasons.append(
            reason(
                "ACTIVATION_NOT_AUTHORIZED",
                path,
                "activation is not explicitly authorized with a decision reference",
            )
        )

    active = descriptor.get("activation_status") == "active" and activation_authorized

    environments = descriptor.get("target_environments")
    environment_authorized = isinstance(environments, list) and environment in environments
    if not environment_authorized:
        reasons.append(
            reason("ENVIRONMENT_NOT_AUTHORIZED", path, "descriptor does not target environment %s" % environment)
        )

    now_epoch = _parse_iso(now) if isinstance(now, str) else now
    if now_epoch is None:
        raise ValueError(
            "eligibility requires an explicit `now`; a wall-clock default would make the "
            "result of a dry run depend on when it was run"
        )

    not_expired = True
    expires_at = descriptor.get("expires_at")
    if expires_at is not None:
        expiry = _parse_iso(expires_at)
        not_expired = expiry is not None and expiry > now_epoch
        if not not_expired:
            reasons.append(reason("DESCRIPTOR_EXPIRED", path, "descriptor expired at %s" % expires_at))

    not_deprecated = descriptor.get("deprecated") is False and descriptor.get("release_status") != "deprecated"
    if not not_deprecated:
        reasons.append(
            reason("DESCRIPTOR_DEPRECATED", path, "deprecated artifacts are not eligible for distribution")
        )

    app_compatible = True
    if "min_app_build" in descriptor:
        # No known consumer build is itself an incompatibility: fail closed.
        app_compatible = app_build is not None and app_build >= descriptor["min_app_build"]
        if not app_compatible:
            reasons.append(
                reason(
                    "APP_BUILD_INCOMPATIBLE",
                    path,
                    "descriptor requires app build >= %s, consumer build is %s"
                    % (descriptor["min_app_build"], app_build),
                )
            )

    eligible = (
        present
        and published
        and approved
        and blockers_resolved
        and activation_authorized
        and environment_authorized
        and not_expired
        and not_deprecated
        and app_compatible
    )

    states = {
        "present": present,
        "published": published,
        "approved": approved,
        "active": active,
        "eligible_for_environment": eligible,
    }
    return states, reasons


def select_active_descriptor(manifest, artifact_id, environment, app_build=None, now=None):
    """Select the distributable descriptor for one artifact line, or nothing.

    A descriptor is selected only when it is active AND eligible. When none qualifies the
    result is explicitly empty — a candidate is NEVER promoted to fill the gap, however valid
    it looks. Two simultaneously active descriptors are a governance fault, not a choice.

    Returns `(selected_or_None, reasons)`.
    """
    line = [d for d in manifest["artifacts"] if d.get("artifact_id") == artifact_id]
    reasons = []
    qualified = []

    for descriptor in line:
        states, evaluation_reasons = evaluate_descriptor(descriptor, environment, app_build, now)
        if not (states["active"] and states["eligible_for_environment"]):
            if states["eligible_for_environment"] and not states["active"]:
                reasons.append(
                    reason(
                        "NOT_ACTIVE",
                        _descriptor_path(descriptor),
                        "eligible but not activated; publication alone does not activate",
                    )
                )
            reasons.extend(evaluation_reasons)
            continue
        qualified.append(descriptor)

    if not qualified:
        reasons.append(
            reason(
                "NO_ACTIVE_ARTIFACT",
                "artifacts(%s)" % artifact_id,
                "no active, eligible descriptor exists; a candidate is never selected implicitly",
            )
        )
        return None, reasons
    if len(qualified) > 1:
        reasons.append(
            reason(
                "MULTIPLE_ACTIVE",
                "artifacts(%s)" % artifact_id,
                "%d descriptors are simultaneously active; refusing to choose" % len(qualified),
            )
        )
        return None, reasons

    return qualified[0], []


def compare_versions(left, right):
    """Numeric, segment-wise comparison of dotted versions ('2.4' < '2.10')."""
    left_parts = [int(part) for part in left.split(".")]
    right_parts = [int(part) for part in right.split(".")]
    for index in range(max(len(left_parts), len(right_parts))):
        a = left_parts[index] if index < len(left_parts) else 0
        b = right_parts[index] if index < len(right_parts) else 0
        if a != b:
            return -1 if a < b else 1
    return 0


def authorize_transition(current, proposed):
    """Authorize a move from the currently active descriptor to a proposed one.

    A downgrade is permitted only when the current descriptor's own `rollback_target` names the
    proposed version AND hash — rollback is an explicit, version/hash-bound act, never an
    implicit fallback.
    """
    if current["artifact_id"] != proposed["artifact_id"]:
        return [
            reason(
                "MALFORMED_FIELD",
                _descriptor_path(proposed),
                "transition across different artifact identities is meaningless",
            )
        ]

    if compare_versions(proposed["artifact_version"], current["artifact_version"]) >= 0:
        return []

    target = current.get("rollback_target")
    if (
        target is not None
        and target["artifact_version"] == proposed["artifact_version"]
        and target["sha256"] == proposed["sha256"]
    ):
        return []

    return [
        reason(
            "DOWNGRADE_NOT_AUTHORIZED",
            _descriptor_path(proposed),
            "downgrade refused: the active descriptor declares no rollback target bound to this "
            "exact version and hash",
        )
    ]
