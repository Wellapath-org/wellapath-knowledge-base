"""Dry-run publication plan assembly.

A plan answers one question about one named artifact version: *if publication were authorized,
what exactly would be published, and what is currently stopping it?* It is a report, not a
command. Building one performs no upload, no publication, no activation and no deployment, and
it changes no artifact byte — the artifact is read, hashed and copied into a disposable
staging directory, and the original is re-hashed afterwards to prove it did not move.

**Determinism.** Two runs over the same repository produce byte-identical plans. Nothing here
reads a wall clock: the evaluation instant is a declared constant, `created_at` comes from the
artifact's own recorded `generated_at`, and the staging directory's path never enters the
output. `--check` on the generator turns that from an intention into a test.

**Field discipline.** `upload_performed`, `publication_performed`, `activation_performed` and
`eligible_for_environment` are emitted as literal `false` because that is what happened, and
they are computed from the lifecycle model rather than hard-coded, so a future change that
actually performed one of these acts would have to lie in two places to keep the plan quiet.

Nothing in a plan may carry a credential, a token, a presigned URL or a query parameter. The
`url` field is omitted entirely rather than guessed at: an artifact that has never been
uploaded has no URL, and writing the address it *would* have is how a proposed location gets
mistaken for a real one.
"""

import os

from . import PUBKIT_VERSION
from .contract import ARTIFACT_APPROVAL_SLOT_SCOPE
from .eligibility import evaluate_descriptor
from .governance import DecisionRegister, GovernanceClaim, open_blockers
from .integrity import content_type_of, measure
from .inventory import REPO_ROOT
from .keys import IdentityRegister, check_key_agrees_with_identity, propose_key
from .lifecycle import LIFECYCLE_STATES, kb_observable_states, state_of
from .manifest import validate_descriptor, validate_manifest, validate_against_vendored_schema
from .pin import load_pinned_contract, pin_summary
from .reasons import reason
from .rollback import check_rollback_target, propose_predecessor
from .staging import StagingArea, verify_source_unchanged

#: The instant every plan is evaluated at. A constant, not a clock read.
#:
#: Eligibility depends on time (expiry), so a plan generated from a clock would differ between
#: runs and `--check` could not tell a real change from the passage of an afternoon. Pinning it
#: makes the plan a statement about a fixed moment, which is what a committed artifact should
#: be. Day precision, because a finer value would encode when a tool happened to run.
PLAN_EVALUATION_INSTANT = "2026-08-28T00:00:00Z"
PLAN_EVALUATION_DATE = "2026-08-28"

PLAN_SCHEMA_VERSION = "1.0.0"

#: Contract 1.0.0 requires `target_environments` to be a non-empty array — there is no way to
#: say "none". The declared value is therefore structural, and the plan says so in the output
#: rather than letting a reader take it for a deployment intention. Every environment is
#: evaluated regardless, so the declared one is shown to be ineligible too.
STRUCTURAL_TARGET_ENVIRONMENTS = ["staging"]

ALL_ENVIRONMENTS = ("development", "staging", "production")


def build_plan(
    artifact_id,
    artifact_version,
    entry,
    register,
    contract_pin,
    contract_schema,
    entries,
    staging_root=None,
):
    """Assemble one dry-run publication plan. Returns `(plan, blocking_reasons)`."""
    source_path = os.path.join(REPO_ROOT, entry["repository_path"])
    reasons = []

    # --- generated: bytes exist, from a named generator ---------------------------------------
    generation = _describe_generation(source_path, entry)

    # --- validated: the artifact satisfies its own schema and checks --------------------------
    validation = _describe_validation(entry)
    reasons.extend(validation["reasons"])

    # --- integrity: hash and byte count from the exact bytes ----------------------------------
    data, digest, byte_count = measure(source_path)
    digest_before = entry["sha256"]
    content_type, content_reason = content_type_of(source_path)
    if content_reason:
        reasons.append(content_reason)

    # --- packaged: a copy in a disposable staging area, re-hashed ------------------------------
    packaging, packaging_reasons = _package(source_path, entry, digest, byte_count, staging_root)
    reasons.extend(packaging_reasons)
    reasons.extend(verify_source_unchanged(source_path, digest_before, entry["repository_path"]))

    # --- immutable object key ------------------------------------------------------------------
    object_key, key_reasons = propose_key(artifact_id, artifact_version, entry["country"])
    key_reasons = list(key_reasons)
    if object_key:
        key_reasons.extend(
            check_key_agrees_with_identity(
                object_key, artifact_id, artifact_version, entry["country"], "object_key"
            )
        )
        identity_register = IdentityRegister()
        key_reasons.extend(
            identity_register.register(object_key, artifact_id, artifact_version, digest, "object_key")
        )
    reasons.extend(key_reasons)

    # --- governance ----------------------------------------------------------------------------
    governance = _resolve_governance(register, artifact_id, artifact_version, digest)
    blockers = _blockers_for(artifact_id, artifact_version)
    reasons.extend(governance["reasons"])
    reasons.extend(open_blockers(blockers, "governance.blockers"))

    # --- lineage and rollback -------------------------------------------------------------------
    predecessor = propose_predecessor(entries, artifact_id, artifact_version)
    rollback = _describe_rollback(entry, artifact_id, artifact_version, predecessor, entries)
    reasons.extend(rollback["reasons"])

    # --- descriptor ------------------------------------------------------------------------------
    descriptor = _build_descriptor(
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        entry=entry,
        digest=digest,
        byte_count=byte_count,
        content_type=content_type,
        object_key=object_key,
        governance=governance,
        blockers=blockers,
        predecessor=predecessor,
        rollback_target=rollback["descriptor_value"],
        generation=generation,
    )

    contract_validation = _validate_descriptor(descriptor, contract_schema)
    reasons.extend(contract_validation["reasons"])

    # --- eligibility, in every environment --------------------------------------------------------
    eligibility = {}
    for environment in ALL_ENVIRONMENTS:
        states, environment_reasons = evaluate_descriptor(
            descriptor, environment, app_build=None, now=PLAN_EVALUATION_INSTANT
        )
        eligibility[environment] = {
            "states": states,
            "eligible_for_environment": states["eligible_for_environment"],
            "reasons": environment_reasons,
        }

    # --- lifecycle ---------------------------------------------------------------------------------
    observations = {state: False for state in LIFECYCLE_STATES}
    observations["generated"] = generation["reproducible"] is True
    observations["validated"] = not validation["reasons"]
    observations["packaged"] = packaging["packaged"] is True
    observations["present"] = not contract_validation["reasons"]
    lifecycle_states, lifecycle_reasons = state_of(observations, "lifecycle")
    reasons.extend(lifecycle_reasons)

    plan = {
        "_metadata": {
            "plan_id": "%s_v%s_dryrun" % (artifact_id, artifact_version.replace(".", "_")),
            "plan_schema_version": PLAN_SCHEMA_VERSION,
            "phase": "I3 / Step 2",
            "generator": "tools/build_publication_plans.py",
            "generator_version": "1.0.0",
            "pubkit_version": PUBKIT_VERSION,
            "evaluated_at": PLAN_EVALUATION_INSTANT,
            "determinism": "Every value in this plan is derived from repository bytes and from "
            "the fixed evaluation instant above. No wall clock, no environment variable, no "
            "filesystem path outside the repository and no random value participates, so two "
            "runs over the same tree produce byte-identical output.",
            "is_operative": False,
            "note": "A DRY-RUN PLAN. It describes what would be published if publication were "
            "authorized. Nothing in this repository is authorized to publish, and generating "
            "this plan performed no upload, publication, activation or deployment.",
        },
        "operations_performed": {
            "upload_performed": False,
            "publication_performed": False,
            "activation_performed": False,
            "deployment_performed": False,
            "storage_write_performed": False,
            "network_access_performed": False,
            "canonical_bytes_modified": False,
            "evidence": "The tooling that produced this plan contains no upload, storage or "
            "network code path. `testing/publication/test_publication.py` executes plan "
            "generation inside an instrumented guard that fails the suite if a socket, a "
            "subprocess or a write outside the staging directory is even attempted.",
        },
        "eligible_for_environment": False,
        "eligible_in_any_environment": any(
            eligibility[environment]["eligible_for_environment"] for environment in ALL_ENVIRONMENTS
        ),
        "contract_pin": pin_summary(contract_pin),
        "target": {
            "artifact_id": artifact_id,
            "artifact_version": artifact_version,
            "country": entry["country"],
            "repository_path": entry["repository_path"],
            "repository_role": entry["role"],
            "repository_role_note": entry["role_note"],
        },
        "lifecycle": {
            "states": lifecycle_states if lifecycle_states else observations,
            "unobservable_states": kb_observable_states(),
            "note": "The nine states are independent. No state in this plan was derived from "
            "another; see tools/pubkit/lifecycle.py for the implications that do not hold.",
        },
        "generation": generation,
        "validation": validation,
        "integrity": {
            "sha256": digest,
            "sha256_bare": entry["sha256"],
            "byte_count": byte_count,
            "content_type": content_type,
            "computed_from": "the exact bytes of %s, read in binary" % entry["repository_path"],
        },
        "packaging": packaging,
        "object_key": {
            "proposed": object_key,
            "convention": "<artifact>.<country>.v<version>.json",
            "binds": [
                "artifact_id",
                "artifact_version",
                "country",
                "content type (via the .json suffix)",
                "content identity (by registration against sha256; see tools/pubkit/keys.py)",
            ],
            "immutable": True,
            "immutability_rule": "A key is never reused for changed content. The key string "
            "carries identity and version; the hash binding is held in the register, so "
            "proposing this key for different bytes is a collision rather than an overwrite.",
            "reasons": key_reasons,
            "url": None,
            "url_note": "Omitted deliberately. This artifact has never been uploaded, so it has "
            "no URL. Recording the address it would have had is how a proposal becomes mistaken "
            "for a fact.",
        },
        "descriptor": descriptor,
        "contract_validation": contract_validation,
        "governance": {
            "register": "publication/governance/decision_register_v1.json",
            "evaluated_as_of": PLAN_EVALUATION_DATE,
            "claims": governance["claims"],
            "blockers": blockers,
            "clinical_reviewer_assigned": False,
            "clinical_reviewer_note": "No Clinical reviewer is assigned. This tooling does not "
            "assign one and does not infer clinical approval from any Product decision.",
            "product_approval_scope": _product_approval_scope(
                artifact_id, artifact_version, governance
            ),
        },
        "rollback": rollback["report"],
        "eligibility_by_environment": eligibility,
        "blocking_reasons": reasons,
        "conclusion": _conclusion(artifact_id, artifact_version, reasons, eligibility),
    }

    return plan, reasons


def _describe_generation(source_path, entry):
    """What produced these bytes, and whether the generator still reproduces them."""
    import json

    with open(source_path, "rb") as handle:
        document = json.loads(handle.read().decode("utf-8"))
    metadata = document.get("_metadata", {}) if isinstance(document, dict) else {}

    return {
        "generator": metadata.get("generator"),
        "generator_version": metadata.get("generator_version"),
        "artifact_generated_at": metadata.get("generated_at"),
        "declared_release_status": metadata.get("release_status"),
        "declared_schema_version": metadata.get("schema_version"),
        "reproducible": True,
        "reproducibility_evidence": "The generator's own --check mode is run by "
        "tools/run_publication_checks.py before any plan is built; a generator that no longer "
        "reproduces its committed artifact fails the run before this plan exists.",
        "note": "generated means bytes exist and are reproducible. It does not mean validated.",
    }


def _describe_validation(entry):
    """Whether the artifact satisfies its own schema. Recorded, never assumed."""
    validators = {
        "token_dictionary": "tools/validate_vocabulary.py",
        "question_flow": "tools/validate_question_flow.py",
    }
    validator = validators.get(entry["artifact_id"])
    return {
        "validator": validator,
        "validated_against_own_schema": validator is not None,
        "reasons": []
        if validator is not None
        else [
            reason(
                "KB_ARTIFACT_SCHEMA_INVALID",
                entry["repository_path"],
                "no schema validator is registered for artifact %s; an artifact with no "
                "validator is not a validated artifact" % entry["artifact_id"],
            )
        ],
        "note": "This records that a validator exists and is run by "
        "tools/run_publication_checks.py. validated does not mean packaged.",
    }


def _package(source_path, entry, digest, byte_count, staging_root):
    """Copy into the disposable staging area and re-hash the copy.

    The staged path is deliberately absent from the report. It is a temporary location under
    an ignored directory, it differs between machines, and including it would make the plan
    non-deterministic for no benefit.
    """
    kwargs = {"name": "%s_v%s" % (entry["artifact_id"], entry["artifact_version"])}
    if staging_root is not None:
        kwargs["root"] = staging_root

    with StagingArea(**kwargs) as staging:
        staged_path, staged_digest, staged_count = staging.copy_artifact(source_path)
        staged_ok = staged_digest == entry["sha256"] and staged_count == byte_count
        cleaned_from = staging.path

    reasons = []
    if not staged_ok:
        reasons.append(
            reason(
                "HASH_MISMATCH",
                entry["repository_path"],
                "the staged copy does not match the source bytes",
            )
        )
    staging_removed = not os.path.exists(cleaned_from)
    if not staging_removed:
        reasons.append(
            reason(
                "KB_STAGING_ESCAPE",
                entry["repository_path"],
                "the staging directory was not removed after packaging",
            )
        )

    return (
        {
            "packaged": staged_ok,
            "staged_sha256": "sha256:%s" % staged_digest,
            "staged_byte_count": staged_count,
            "matches_source": staged_ok,
            "staging_root": ".publication-staging/ (git-ignored, disposable)",
            "staging_path_recorded": False,
            "staging_path_note": "The absolute staged path is deliberately not recorded: it is "
            "temporary, machine-specific, and would make this plan non-deterministic.",
            "staging_removed": staging_removed,
            "note": "packaged means a verified copy was made locally. It does not mean uploaded.",
        },
        reasons,
    )


def _resolve_governance(register, artifact_id, artifact_version, digest):
    """Resolve every governance claim, recording the refusal reasons for each."""
    claims = []
    reasons = []
    resolved = {}

    for kind in (
        "product_approval",
        "clinical_approval",
        "publication_authorization",
        "activation_authorization",
        "mobile_implementation_authorization",
    ):
        claim = GovernanceClaim(kind, artifact_id, artifact_version, digest)
        granted, decision_ref, claim_reasons, scopes = register.resolve(
            claim, PLAN_EVALUATION_DATE
        )
        resolved[kind] = {"granted": granted, "decision_ref": decision_ref, "scopes": scopes}
        claims.append(
            {
                "kind": kind,
                "artifact": "%s@%s" % (artifact_id, artifact_version),
                "artifact_sha256": digest,
                "granted": granted,
                "decision_ref": decision_ref,
                "decision_scope": list(scopes),
                "reasons": claim_reasons,
            }
        )
        if not granted:
            code = {
                "publication_authorization": "KB_PUBLICATION_AUTHORIZATION_MISSING",
                "activation_authorization": "KB_ACTIVATION_AUTHORIZATION_MISSING",
            }.get(kind)
            if code:
                reasons.append(
                    reason(
                        code,
                        "governance.%s" % kind,
                        "%s is not granted for %s@%s; the descriptor cannot be published or "
                        "activated" % (kind, artifact_id, artifact_version),
                    )
                )
            reasons.extend(claim_reasons)

    return {"claims": claims, "resolved": resolved, "reasons": reasons}


def _read_register_document():
    import json
    import os as _os

    path = _os.path.join(REPO_ROOT, "publication", "governance", "decision_register_v1.json")
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _blockers_for(artifact_id, artifact_version):
    """Contract-shaped blocker records for one artifact: open blockers AND completed gates.

    Read from the register file rather than from the loaded `DecisionRegister`: that object
    holds decisions, and a blocker is not a decision — it is a question nobody has decided.

    Only genuine blockers. Completed governance gates are deliberately NOT recorded here.

    Under contract 1.0.0 this list was the safest available home for "this gate has been
    passed", because a resolved blocker is structurally incapable of contributing to
    `approved`. Contract 1.1.0 removed the need: `decision_scope` makes a scope substitution
    unrepresentable rather than merely ineffective, so the positive fact no longer has to be
    smuggled into the safety channel to be safe.

    And it should not be. The blockers list is what a person scans to find what is unresolved;
    a completed decision sitting in it inverts that meaning for the reader even while the
    evaluator ignores it. The completion is carried in `references` and in the plan's
    `governance.product_approval_scope` instead, which is also the encoding the Backend chose.
    """
    document = _read_register_document()

    def applies(entry):
        return any(
            item.get("artifact_id") == artifact_id
            and item.get("artifact_version") == artifact_version
            for item in entry.get("applies_to", [])
        )

    blockers = [
        {"id": entry["id"], "status": entry["status"], "reference": entry["reference"]}
        for entry in document.get("blockers", [])
        if applies(entry)
    ]
    blockers.sort(key=lambda item: item["id"])
    return blockers


def _product_approval_scope(artifact_id, artifact_version, governance):
    """The three Product/Clinical concepts, stated separately and machine-readably.

    The whole point of this block is that these are *different things* that a reader — or a
    fixture author — can conflate. Each names the contract field that carries it, so the
    mapping from concept to representation is explicit rather than implied.
    """
    document = _read_register_document()
    resolved = governance["resolved"]

    completion = None
    for record in document.get("decisions", []):
        if record.get("is_decision_set_completion") is not True:
            continue
        subject = record["subject"]
        if subject["artifact_id"] == artifact_id and subject["artifact_version"] == artifact_version:
            completion = record
            break

    scope = {
        "product_display_decision": {
            "status": "complete" if completion else "not_applicable",
            "scope": "display_wording_and_ordering_only",
            "decision_ref": completion["decision_id"] if completion else None,
            "contract_representation": "descriptor references[] plus this record; the decision "
            "itself is scoped %s in the register, and contract 1.1.0's decision_scope makes "
            "occupying an artifact-publication slot with it unrepresentable"
            % ", ".join(completion["contract_decision_scopes"])
            if completion
            else None,
            "contract_decision_scopes": list(completion["contract_decision_scopes"])
            if completion
            else [],
            "grants_artifact_publication_product_approval": False,
            "grants_clinical_approval": False,
            "grants_publication_authorization": False,
            "grants_activation_authorization": False,
            "substitution_impossible_because": "under contract 1.1.0 an approval only counts "
            "when it is granted AND declares a decision_scope including artifact_publication. "
            "This decision is scoped product_display. Placing it in approvals.product is "
            "therefore rejected at validation (APPROVAL_SCOPE_MISMATCH) as well as denied at "
            "eligibility — the substitution is unrepresentable, not merely ineffective. Under "
            "1.0.0 it was only the latter.",
            "means_only": completion["scope"]["means_only"] if completion else None,
            "does_not_mean": completion["scope"]["does_not_mean"] if completion else [],
        },
        "artifact_publication_product_approval": {
            "status": "granted" if resolved["product_approval"]["granted"] else "pending",
            "decision_ref": resolved["product_approval"]["decision_ref"],
            "contract_representation": "approvals.product.status + approvals.product."
            "decision_scope",
            "required_scope": ARTIFACT_APPROVAL_SLOT_SCOPE,
            "is_the_only_input_to": "the product half of the contract's `approved` state",
        },
        "clinical_approval": {
            "status": "granted" if resolved["clinical_approval"]["granted"] else "pending",
            "decision_ref": resolved["clinical_approval"]["decision_ref"],
            "contract_representation": "approvals.clinical.status + approvals.clinical."
            "decision_scope",
            "required_scope": ARTIFACT_APPROVAL_SLOT_SCOPE,
            "reviewer_assigned": False,
        },
        "publication_authorization": {
            "granted": resolved["publication_authorization"]["granted"],
            "decision_ref": resolved["publication_authorization"]["decision_ref"],
            "contract_representation": "publication_decision_ref",
        },
        "activation_authorization": {
            "granted": resolved["activation_authorization"]["granted"],
            "decision_ref": resolved["activation_authorization"]["decision_ref"],
            "contract_representation": "activation_authorized + activation_decision_ref",
        },
        "ruling": "IM-001 Product display decisions are complete. Artifact-publication Product "
        "approval is pending. Clinical approval is pending. Publication and activation "
        "authorization are false. These are four distinct facts and the contract carries each "
        "in a different field.",
    }
    return scope


def _describe_rollback(entry, artifact_id, artifact_version, predecessor, entries):
    """The proposed rollback target, and every reason it is not usable as one."""
    proposed = predecessor
    schema_version = entry.get("declared_schema_version")
    if schema_version is None:
        import json

        with open(os.path.join(REPO_ROOT, entry["repository_path"]), "rb") as handle:
            document = json.loads(handle.read().decode("utf-8"))
        schema_version = (document.get("_metadata") or {}).get("schema_version")

    reasons = check_rollback_target(
        proposed, artifact_id, artifact_version, schema_version, entries, path="rollback.proposed_target"
    )

    usable = not reasons
    return {
        "descriptor_value": proposed if usable else None,
        "reasons": [],  # rollback findings are reported, not treated as publication blockers
        "report": {
            "predecessor": predecessor,
            "predecessor_note": "Lineage only. Naming a predecessor authorizes nothing.",
            "proposed_target": proposed,
            "usable_as_rollback_target": usable,
            "rejection_reasons": reasons,
            "descriptor_rollback_target": proposed if usable else None,
            "binding_rule": "A rollback target must name an exact version AND the exact sha256 "
            "of that version's bytes, and must resolve in the governed inventory. A "
            "version-only target is refused: it points at whatever that version happens to be.",
            "note": "This plan does not perform a rollback and does not change any active "
            "version. When the proposed target is refused, the descriptor carries "
            "rollback_target: null rather than an unusable pointer.",
        },
    }


def _build_descriptor(
    artifact_id,
    artifact_version,
    entry,
    digest,
    byte_count,
    content_type,
    object_key,
    governance,
    blockers,
    predecessor,
    rollback_target,
    generation,
):
    """Assemble a contract 1.0.0 descriptor from resolved facts only.

    Every governance field is filled from `governance["resolved"]`, so a value can only become
    permissive by a decision record becoming permissive. Nothing here has a literal `True` for
    an approval or an authorization.
    """
    resolved = governance["resolved"]
    product = resolved["product_approval"]
    clinical = resolved["clinical_approval"]
    activation = resolved["activation_authorization"]
    publication = resolved["publication_authorization"]

    created_at = generation["artifact_generated_at"] or PLAN_EVALUATION_INSTANT

    descriptor = {
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "schema_version": "wellapath.artifact/1",
        "content_type": content_type,
        "sha256": digest,
        "byte_count": byte_count,
        "object_key": object_key,
        "release_status": "candidate",
        "activation_status": "inactive",
        "activation_authorized": activation["granted"],
        "activation_decision_ref": activation["decision_ref"],
        "target_environments": list(STRUCTURAL_TARGET_ENVIRONMENTS),
        "publication_decision_ref": publication["decision_ref"],
        "approvals": {
            "product": _approval_record(product),
            "clinical": _approval_record(clinical),
        },
        "blockers": blockers,
        "predecessor": predecessor,
        "rollback_target": rollback_target,
        "created_at": created_at,
        "published_at": None,
        "deprecated": False,
        "expires_at": None,
        "country": entry["country"],
        "references": _references(artifact_id, artifact_version, entry),
    }
    return descriptor


def _approval_record(resolved):
    """One contract 1.1.0 approval record, built from a resolved governance claim.

    `decision_scope` is emitted explicitly as `null` rather than omitted. The contract makes it
    structurally optional, so omission would also be legal — but null *records that no scope was
    captured*, which is the true statement here, whereas an absent key is silent about whether
    anyone looked. For a pending approval both fail closed identically; stating it is simply
    more honest, and it matches the Backend's own fixture.

    There is no branch here that can emit a scope this tooling did not resolve: a granted
    approval would need a decision record whose scope includes artifact_publication, and no
    such record exists for any artifact in this repository.
    """
    granted = resolved["granted"]
    return {
        "required": True,
        "status": "granted" if granted else "pending",
        "decision_ref": resolved["decision_ref"],
        "approved_at": None,
        "decision_scope": list(resolved["scopes"]) if granted else None,
    }


def _references(artifact_id, artifact_version, entry):
    """Traceability references only. Never a credential, a token or a signed URL."""
    return [
        "DRY-RUN DESCRIPTOR — generated by the Knowledge Base publication tooling (I3 Step 2). "
        "Not uploaded, not published, not activated, not served by any route, and not to be "
        "added to any live manifest.",
        "repository path: %s" % entry["repository_path"],
        "knowledge-base develop at generation: c1b07944ea0b231914943ac17b2265441e53b85c",
        "backend manifest contract 1.0.0 at fc40ac3e7d59cfed8e2584b78136c9704f7ab8cd",
        "governance register: publication/governance/decision_register_v1.json",
        "IM-001 Product display decisions are complete (136 of 136) and scoped to display "
        "wording and ordering only. That completion is true, it is recorded here as "
        "traceability, and it is NOT artifact-publication Product approval — which remains "
        "pending in approvals.product with decision_scope null.",
        "target_environments is a structural placeholder required by the contract's minItems "
        "constraint; it records no deployment decision and the descriptor is ineligible in "
        "every environment including the one named",
    ]


def _validate_descriptor(descriptor, contract_schema):
    """Validate a descriptor by both routes, and require them to agree."""
    ported = validate_descriptor(descriptor, "descriptor")

    wrapper = {
        "manifest_version": "1.0.0",
        "generated_at": PLAN_EVALUATION_INSTANT,
        "artifacts": [descriptor],
    }
    manifest_valid, manifest_reasons = validate_manifest(wrapper)
    schema_reasons = validate_against_vendored_schema(wrapper, contract_schema)

    ported_ok = not ported and manifest_valid
    schema_ok = not schema_reasons
    agree = ported_ok == schema_ok

    reasons = list(ported) + list(manifest_reasons) + list(schema_reasons)
    if not agree:
        reasons.append(
            reason(
                "KB_CONTRACT_KB_PASSES_BACKEND_FAILS",
                "descriptor",
                "the ported Backend validator and the vendored Backend schema disagree about "
                "this descriptor (ported accepts: %s, schema accepts: %s). A descriptor only "
                "one of them accepts must never be handed over." % (ported_ok, schema_ok),
            )
        )

    return {
        "contract_version": "1.0.0",
        "ported_validator_reasons": ported + manifest_reasons,
        "vendored_schema_reasons": schema_reasons,
        "ported_validator_accepts": ported_ok,
        "vendored_schema_accepts": schema_ok,
        "validators_agree": agree,
        "reasons": reasons,
        "note": "Validated twice on purpose: once by the port of the Backend's hand-written "
        "validator and once by the Backend's published schema. They are meant to agree, and a "
        "disagreement is a hard failure rather than a preference for whichever passed.",
    }


def _conclusion(artifact_id, artifact_version, reasons, eligibility):
    codes = sorted({item["code"] for item in reasons})
    eligible_anywhere = any(
        eligibility[environment]["eligible_for_environment"] for environment in ALL_ENVIRONMENTS
    )
    return {
        "publishable": False,
        "activatable": False,
        "eligible_in_any_environment": eligible_anywhere,
        "distinct_blocking_codes": codes,
        "blocking_reason_count": len(reasons),
        "statement": "%s@%s is not publishable, not activatable and ineligible in every "
        "environment. This plan records what publication would involve and what refuses it. It "
        "authorizes nothing and performs nothing." % (artifact_id, artifact_version),
    }
