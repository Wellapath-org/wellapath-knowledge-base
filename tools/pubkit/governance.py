"""Governance evidence resolution.

Every approval or authorization this tooling reports must resolve to an *authoritative decision
record*. A decision record is a structured object binding, at minimum:

    decision_id            stable, quotable identifier
    authority_type         product | clinical | engineering_lead | founder | none
    reviewer               identity AND title — an unnamed approver is not an approver
    decision_date          when the decision was taken
    status                 explicit; unknown is never coerced
    subject                artifact id AND version, plus artifact hash where applicable
    rationale              why, or a resolvable decision reference
    decision_reference     path and sha256 of the record this transcribes
    scope                  what it authorizes and what it explicitly does not
    supersession           superseded_by / revoked / revocation_reference

Prose is not evidence. A sentence in a markdown file saying an artifact was approved resolves
to nothing here: `decision_reference` must name a file and its hash, and `scope` must name the
act being claimed. That is the difference between a record and a recollection.

The resolver is fail-closed in the strong sense — it does not have a "probably fine" branch.
Absent, null, malformed, unknown, expired, revoked, superseded, wrongly-scoped or
wrongly-authorised evidence all produce the same outcome as no evidence at all: the claim is
refused, with a reason code naming exactly which rule refused it.

Two substitutions are called out by name because they are the ones that would actually happen:

  * **Product approval standing in for Clinical approval.** The named Product reviewer holds
    Product authority only. `reports/im003_disposition_v1.json` records this explicitly, no
    Clinical reviewer is assigned, and no amount of Product sign-off changes that.
  * **A completed decision set standing in for an authorization.** `im_001_resolved: true`
    means every Product display decision in the IM-001 set has been recorded. It is a
    statement about a backlog, not a permission, and the record itself carries a
    machine-readable scope saying so.
"""

import datetime
import re

from .reasons import reason

#: Kinds of claim this resolver can be asked about.
CLAIM_KINDS = (
    "product_approval",
    "clinical_approval",
    "publication_authorization",
    "activation_authorization",
    "mobile_implementation_authorization",
)

#: The authority that, and only that, can satisfy each claim.
REQUIRED_AUTHORITY = {
    "product_approval": ("product",),
    "clinical_approval": ("clinical",),
    "publication_authorization": ("engineering_lead", "founder"),
    "activation_authorization": ("engineering_lead", "founder"),
    "mobile_implementation_authorization": ("engineering_lead", "founder"),
}

KNOWN_AUTHORITIES = ("product", "clinical", "engineering_lead", "founder", "none")

#: Explicit statuses. Anything else is `KB_DECISION_STATUS_UNKNOWN` — never coerced to a
#: neighbouring value, never defaulted to pending, never assumed benign.
KNOWN_STATUSES = ("approved", "denied", "pending", "withdrawn", "not_required")

#: Contract 1.1.0 approval scopes, mirrored so a record cannot declare a scope the contract
#: does not define. Imported rather than restated to keep one definition.
from .contract import APPROVAL_SCOPES, ARTIFACT_APPROVAL_SLOT_SCOPE  # noqa: E402

REQUIRED_RECORD_FIELDS = (
    "decision_id",
    "authority_type",
    "reviewer",
    "decision_date",
    "status",
    "subject",
    "rationale",
    "decision_reference",
    "scope",
    "supersession",
    "contract_decision_scopes",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class GovernanceClaim:
    """One question put to the resolver: may X be asserted about this exact artifact?"""

    def __init__(self, kind, artifact_id, artifact_version, artifact_sha256=None):
        if kind not in CLAIM_KINDS:
            raise ValueError("unknown governance claim kind %r" % (kind,))
        self.kind = kind
        self.artifact_id = artifact_id
        self.artifact_version = artifact_version
        self.artifact_sha256 = artifact_sha256

    @property
    def identity(self):
        return "%s@%s" % (self.artifact_id, self.artifact_version)

    def __repr__(self):  # pragma: no cover - diagnostics only
        return "GovernanceClaim(%s for %s)" % (self.kind, self.identity)


def validate_record(record, path):
    """Every reason a decision record is not usable as evidence.

    Runs before any matching, so a malformed record can never satisfy a claim by accident.
    """
    reasons = []

    if not isinstance(record, dict):
        return [reason("KB_DECISION_RECORD_MALFORMED", path, "decision record must be an object")]

    for field in REQUIRED_RECORD_FIELDS:
        if field not in record:
            reasons.append(
                reason(
                    "KB_DECISION_RECORD_MALFORMED",
                    "%s.%s" % (path, field),
                    "required decision-record field is absent; a record missing %s cannot bind "
                    "an approval to anything" % field,
                )
            )
    if reasons:
        return reasons

    decision_id = record["decision_id"]
    if not isinstance(decision_id, str) or decision_id.strip() == "":
        reasons.append(
            reason("KB_DECISION_ID_MISSING", "%s.decision_id" % path, "a decision needs a stable, quotable id")
        )

    authority = record["authority_type"]
    if authority not in KNOWN_AUTHORITIES:
        reasons.append(
            reason(
                "KB_DECISION_AUTHORITY_MISSING",
                "%s.authority_type" % path,
                "authority %r is not one of %s" % (authority, ", ".join(KNOWN_AUTHORITIES)),
            )
        )

    reviewer = record["reviewer"]
    if not isinstance(reviewer, dict):
        reasons.append(reason("KB_DECISION_REVIEWER_MISSING", "%s.reviewer" % path, "reviewer must be an object"))
    else:
        for field in ("identity", "title"):
            value = reviewer.get(field)
            if not isinstance(value, str) or value.strip() == "":
                reasons.append(
                    reason(
                        "KB_DECISION_REVIEWER_MISSING",
                        "%s.reviewer.%s" % (path, field),
                        "an approval with no reviewer %s is not an approval" % field,
                    )
                )

    if not isinstance(record["decision_date"], str) or not _DATE_RE.match(record["decision_date"]):
        reasons.append(
            reason("KB_DECISION_DATE_MISSING", "%s.decision_date" % path, "decision_date must be YYYY-MM-DD")
        )

    if record["status"] not in KNOWN_STATUSES:
        reasons.append(
            reason(
                "KB_DECISION_STATUS_UNKNOWN",
                "%s.status" % path,
                "status %r is not an explicit known status; an unrecognised status is never "
                "coerced to a neighbouring one" % (record["status"],),
            )
        )

    subject = record["subject"]
    if not isinstance(subject, dict):
        reasons.append(reason("KB_DECISION_RECORD_MALFORMED", "%s.subject" % path, "subject must be an object"))
    else:
        for field in ("artifact_id", "artifact_version", "artifact_sha256", "hash_binding"):
            if field not in subject:
                reasons.append(
                    reason(
                        "KB_DECISION_RECORD_MALFORMED",
                        "%s.subject.%s" % (path, field),
                        "subject must state %s explicitly" % field,
                    )
                )
        if subject.get("hash_binding") not in ("bound", "not_applicable"):
            reasons.append(
                reason(
                    "KB_DECISION_RECORD_MALFORMED",
                    "%s.subject.hash_binding" % path,
                    "hash_binding must be 'bound' or an explicit 'not_applicable'; silence "
                    "about whether a decision is hash-bound is not an answer",
                )
            )
        elif subject.get("hash_binding") == "bound":
            digest = subject.get("artifact_sha256")
            if not isinstance(digest, str) or not _SHA256_RE.match(digest):
                reasons.append(
                    reason(
                        "KB_DECISION_HASH_MISMATCH",
                        "%s.subject.artifact_sha256" % path,
                        "a hash-bound decision must carry a sha256:<64 hex> digest",
                    )
                )

    rationale = record["rationale"]
    if not isinstance(rationale, str) or rationale.strip() == "":
        reasons.append(
            reason("KB_DECISION_RECORD_MALFORMED", "%s.rationale" % path, "a decision must state its rationale")
        )

    ref = record["decision_reference"]
    if not isinstance(ref, dict) or not isinstance(ref.get("path"), str) or ref.get("path", "").strip() == "":
        reasons.append(
            reason(
                "KB_DECISION_PROSE_ONLY",
                "%s.decision_reference" % path,
                "a decision must name the record it transcribes; an approval asserted only in "
                "prose resolves to nothing",
            )
        )
    elif not isinstance(ref.get("sha256"), str) or not re.match(r"^[0-9a-f]{64}$", ref.get("sha256", "")):
        reasons.append(
            reason(
                "KB_DECISION_PROSE_ONLY",
                "%s.decision_reference.sha256" % path,
                "the referenced record must be bound by hash; an unbound path is a pointer to "
                "whatever that file says today",
            )
        )

    scope = record["scope"]
    if not isinstance(scope, dict):
        reasons.append(reason("KB_DECISION_SCOPE_MISSING", "%s.scope" % path, "scope must be an object"))
    else:
        for field in ("authorizes", "does_not_authorize"):
            value = scope.get(field)
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                reasons.append(
                    reason(
                        "KB_DECISION_SCOPE_MISSING",
                        "%s.scope.%s" % (path, field),
                        "scope.%s must be an explicit list of strings" % field,
                    )
                )
        if isinstance(scope.get("authorizes"), list) and not scope["authorizes"]:
            # An empty authorizes list is legitimate — it is how a record says "this decides
            # something but permits nothing" — so it is not an error. It simply satisfies no
            # claim, which the matcher handles.
            pass

    supersession = record["supersession"]
    if not isinstance(supersession, dict):
        reasons.append(
            reason("KB_DECISION_RECORD_MALFORMED", "%s.supersession" % path, "supersession must be an object")
        )
    else:
        for field in ("superseded_by", "revoked", "revocation_reference"):
            if field not in supersession:
                reasons.append(
                    reason(
                        "KB_DECISION_RECORD_MALFORMED",
                        "%s.supersession.%s" % (path, field),
                        "supersession must state %s explicitly, even as null/false" % field,
                    )
                )
        if "revoked" in supersession and not isinstance(supersession["revoked"], bool):
            reasons.append(
                reason(
                    "KB_DECISION_RECORD_MALFORMED",
                    "%s.supersession.revoked" % path,
                    "revoked must be a boolean; anything else is unknown, which fails closed",
                )
            )

    scopes = record["contract_decision_scopes"]
    if not isinstance(scopes, list):
        reasons.append(
            reason(
                "KB_DECISION_SCOPE_MISSING",
                "%s.contract_decision_scopes" % path,
                "a record must state, in the contract's own scope vocabulary, what its decision "
                "actually authorized — even when the answer is an empty list",
            )
        )
    else:
        for entry in scopes:
            if entry not in APPROVAL_SCOPES:
                reasons.append(
                    reason(
                        "KB_DECISION_SCOPE_MISSING",
                        "%s.contract_decision_scopes" % path,
                        "%r is not a contract 1.1.0 approval scope; unknown scope is never read "
                        "as authorisation" % (entry,),
                    )
                )

    if "expires_at" in record and record["expires_at"] is not None:
        if not isinstance(record["expires_at"], str) or not _DATE_RE.match(record["expires_at"]):
            reasons.append(
                reason("KB_DECISION_RECORD_MALFORMED", "%s.expires_at" % path, "expires_at must be null or YYYY-MM-DD")
            )

    return reasons


class DecisionRegister:
    """A validated set of decision records, queried by claim.

    Records are validated on load. An invalid record is *retained with its reasons* rather than
    dropped, so a claim that would have matched it reports "the evidence exists but is
    unusable, here is why" instead of the much less helpful "no evidence found".
    """

    def __init__(self, records, source_path="governance"):
        self.source_path = source_path
        self.records = []
        self.invalid = []
        for index, record in enumerate(records):
            path = "%s[%d]" % (source_path, index)
            problems = validate_record(record, path)
            if problems:
                self.invalid.append((record, path, problems))
            else:
                self.records.append((record, path))

    @classmethod
    def from_file(cls, path):
        """Load a register, labelling it by its repository-relative path.

        The label is derived rather than passed in on purpose: it appears inside the reason
        paths that end up in committed dry-run plans, so a caller free to choose it could make
        two runs of the same generator produce different plan bytes.
        """
        import json
        import os

        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(path, "rb") as handle:
            document = json.loads(handle.read().decode("utf-8"))
        label = os.path.relpath(os.path.abspath(path), repo_root).replace(os.sep, "/")
        return cls(document["decisions"], label)

    def resolve(self, claim, as_of):
        """Resolve one claim. Returns `(granted, decision_ref_or_None, reasons, scopes)`.

        `scopes` is the contract 1.1.0 `decision_scope` the granting record actually carried,
        or `()` when nothing was granted. It is read from the record rather than assumed from
        the claim: a claim being granted says which *slot* was filled, and the scope says what
        the decision behind it authorised. Those are the two things contract 1.1.0 exists to
        keep apart.

        `granted` is True only when a single valid, in-scope, correctly-authorised, unexpired,
        unrevoked, unsuperseded, correctly-bound record with status `approved` matches. Every
        other outcome is False with reasons.
        """
        reasons = []
        matched = []

        for record, path in self.records:
            subject = record["subject"]
            if subject["artifact_id"] != claim.artifact_id:
                # Silently skipping a record for an unrelated artifact is right; silently
                # skipping one that claims to authorize this very act is how an approval gets
                # reused across artifacts by whoever reads the register next.
                if claim.kind in record["scope"].get("authorizes", []):
                    reasons.append(
                        reason(
                            "KB_DECISION_ARTIFACT_MISMATCH",
                            path,
                            "%s authorises %s but for artifact %s, not %s"
                            % (
                                record["decision_id"],
                                claim.kind,
                                subject["artifact_id"],
                                claim.artifact_id,
                            ),
                        )
                    )
                continue
            if subject["artifact_version"] != claim.artifact_version:
                # A record for another version of the same artifact is a near-miss worth
                # reporting: silently ignoring it is how an approval gets reused across
                # versions by whoever reads the register next.
                if claim.kind in record["scope"].get("authorizes", []):
                    reasons.append(
                        reason(
                            "KB_DECISION_VERSION_MISMATCH",
                            path,
                            "%s authorises %s but for %s@%s, not %s"
                            % (record["decision_id"], claim.kind, subject["artifact_id"],
                               subject["artifact_version"], claim.identity),
                        )
                    )
                continue
            matched.append((record, path))

        for record, path in self.invalid:
            subject = record.get("subject") if isinstance(record, dict) else None
            if isinstance(subject, dict) and subject.get("artifact_id") == claim.artifact_id:
                reasons.append(
                    reason(
                        "KB_DECISION_RECORD_MALFORMED",
                        path,
                        "a decision record naming %s is unusable as evidence; it cannot support "
                        "any claim" % claim.artifact_id,
                    )
                )

        if not matched:
            reasons.append(
                reason(
                    "KB_DECISION_RECORD_MISSING",
                    "%s(%s)" % (self.source_path, claim.identity),
                    "no decision record binds %s to %s; absence of evidence is refusal, not "
                    "permission" % (claim.kind, claim.identity),
                )
            )
            return False, None, reasons, ()

        granting = []
        for record, path in matched:
            record_reasons = self._evaluate(record, path, claim, as_of)
            if record_reasons:
                reasons.extend(record_reasons)
            else:
                granting.append(record)

        if not granting:
            return False, None, reasons, ()

        if len(granting) > 1:
            reasons.append(
                reason(
                    "KB_DECISION_RECORD_MALFORMED",
                    "%s(%s)" % (self.source_path, claim.identity),
                    "%d records claim to grant %s for %s; refusing to choose between competing "
                    "authorities" % (len(granting), claim.kind, claim.identity),
                )
            )
            return False, None, reasons, ()

        record = granting[0]
        return (
            True,
            "%s (%s)" % (record["decision_id"], record["decision_reference"]["path"]),
            reasons,
            tuple(record["contract_decision_scopes"]),
        )

    def _evaluate(self, record, path, claim, as_of):
        """Every reason this record does not grant this claim."""
        reasons = []
        decision_id = record["decision_id"]

        required = REQUIRED_AUTHORITY[claim.kind]
        if record["authority_type"] not in required:
            reasons.append(
                reason(
                    "KB_DECISION_AUTHORITY_WRONG",
                    "%s.authority_type" % path,
                    "%s carries %s authority; %s requires %s. Authority does not transfer: a "
                    "%s decision is not a %s decision however senior the reviewer"
                    % (decision_id, record["authority_type"], claim.kind, " or ".join(required),
                       record["authority_type"], claim.kind.replace("_", " ")),
                )
            )

        if record["status"] != "approved":
            # A record whose status is known but not "approved" is a decision that exists and
            # says no (or not yet). Reporting that as a *missing* record would be wrong twice
            # over: it hides that somebody decided, and it sends a reader looking for a record
            # that is right there.
            reasons.append(
                reason(
                    "KB_DECISION_STATUS_UNKNOWN"
                    if record["status"] not in KNOWN_STATUSES
                    else "KB_DECISION_NOT_APPROVED",
                    "%s.status" % path,
                    "%s has status %r; only an explicit 'approved' grants anything"
                    % (decision_id, record["status"]),
                )
            )

        supersession = record["supersession"]
        if supersession.get("superseded_by"):
            reasons.append(
                reason(
                    "KB_DECISION_SUPERSEDED",
                    "%s.supersession.superseded_by" % path,
                    "%s was superseded by %s and no longer grants anything"
                    % (decision_id, supersession["superseded_by"]),
                )
            )
        if supersession.get("revoked") is True:
            reasons.append(
                reason(
                    "KB_DECISION_REVOKED",
                    "%s.supersession.revoked" % path,
                    "%s was revoked (%s)" % (decision_id, supersession.get("revocation_reference")),
                )
            )

        expires_at = record.get("expires_at")
        if expires_at is not None and _date(expires_at) <= _date(as_of):
            reasons.append(
                reason(
                    "KB_DECISION_EXPIRED",
                    "%s.expires_at" % path,
                    "%s expired on %s, evaluated as of %s" % (decision_id, expires_at, as_of),
                )
            )

        subject = record["subject"]
        if subject["hash_binding"] == "bound":
            if claim.artifact_sha256 is None:
                reasons.append(
                    reason(
                        "KB_DECISION_HASH_MISMATCH",
                        "%s.subject.artifact_sha256" % path,
                        "%s is bound to exact bytes but the claim supplies no artifact hash to "
                        "check against" % decision_id,
                    )
                )
            elif subject["artifact_sha256"] != claim.artifact_sha256:
                reasons.append(
                    reason(
                        "KB_DECISION_HASH_MISMATCH",
                        "%s.subject.artifact_sha256" % path,
                        "%s approves bytes %s; the artifact is %s. An approval does not carry "
                        "across a content change"
                        % (decision_id, subject["artifact_sha256"], claim.artifact_sha256),
                    )
                )

        scope = record["scope"]
        in_scope = claim.kind in scope.get("authorizes", [])
        explicitly_excluded = claim.kind in scope.get("does_not_authorize", [])

        if record.get("is_decision_set_completion") is True and not in_scope:
            # A record that says "this set of decisions is complete" is refused with its own
            # code whichever way its scope is written. Reporting a generic scope failure here
            # would hide the specific confusion this code exists to name: a decision *count*
            # reaching zero being read as a permission.
            reasons.append(
                reason(
                    "KB_DECISION_SET_IS_NOT_AUTHORIZATION",
                    "%s.scope" % path,
                    "%s records the completion of a decision set, not a grant of %s. %s"
                    % (
                        decision_id,
                        claim.kind,
                        scope.get("note", "A completed decision set authorizes nothing."),
                    ),
                )
            )
        elif explicitly_excluded:
            reasons.append(
                reason(
                    "KB_DECISION_SCOPE_EXCEEDED",
                    "%s.scope.does_not_authorize" % path,
                    "%s explicitly does not authorize %s" % (decision_id, claim.kind),
                )
            )
        elif not in_scope:
            reasons.append(
                reason(
                    "KB_DECISION_SCOPE_MISSING",
                    "%s.scope.authorizes" % path,
                    "%s does not list %s among what it authorizes; a decision grants exactly "
                    "what it says and nothing adjacent" % (decision_id, claim.kind),
                )
            )

        return reasons


def _date(value):
    return datetime.datetime.strptime(value, "%Y-%m-%d").date()


def open_blockers(blockers, path="blockers"):
    """Reasons drawn from unresolved safety blockers. Any status but `resolved` blocks."""
    reasons = []
    for blocker in blockers:
        if blocker.get("status") != "resolved":
            reasons.append(
                reason(
                    "KB_SAFETY_BLOCKER_OPEN",
                    path,
                    "%s is %s (%s); an open safety blocker refuses publication and activation "
                    "regardless of any approval"
                    % (blocker.get("id"), blocker.get("status"), blocker.get("reference", "no reference")),
                )
            )
    return reasons
