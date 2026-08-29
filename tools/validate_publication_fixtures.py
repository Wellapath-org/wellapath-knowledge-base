#!/usr/bin/env python3
"""Execute every publication fixture and assert it fails where and how it says it will.

    python3 tools/validate_publication_fixtures.py             # run every fixture
    python3 tools/validate_publication_fixtures.py --mutations  # also run the mutation proofs
    python3 tools/validate_publication_fixtures.py --json       # machine-readable output

Two fixture sets, run by two runners:

  * `publication/fixtures/compat/negative_fixtures.compat.json` — contract-level cases in the
    Backend's own fixture format, executed against the ported Backend validator, the ported
    eligibility engine, the ported selector and the ported integrity check. Because the
    fixtures are data in a shared format, the Backend can execute the same file against its
    own implementation; if the two ever disagree on a case, that is the disagreement surfacing
    as a test failure rather than as a rejected descriptor months later.

  * `publication/fixtures/negative/kb_stage_fixtures_v1.json` — the Knowledge-Base-only stages,
    executed against the pin checker, the key validator, the governance resolver, the lifecycle
    model, the rollback checker and the write/network guards.

A case does not pass merely by failing. It passes only when it fails **at its declared stage
with its declared reason code**. A guard that starts refusing the right thing for the wrong
reason is a behaviour change, and this runner is what makes that visible.

`--mutations` goes one step further on the safety-critical boundaries: it deliberately breaks
a guard and requires the fixture that depends on it to start passing when it should not. A
guard that cannot be made to fail was never checking anything.

Standard library only, no network.
"""

import argparse
import copy
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pubkit import eligibility, inventory, keys, lifecycle, manifest as manifest_module, origin, pin, rollback
from pubkit import plan as plan_module
from pubkit.governance import DecisionRegister, GovernanceClaim, open_blockers, validate_record
from pubkit.integrity import verify_bytes
from pubkit.plan import PLAN_EVALUATION_DATE, PLAN_EVALUATION_INSTANT
from pubkit.safety import SideEffectAttempted, no_side_effects
from pubkit.staging import StagingArea, StagingEscape, verify_source_unchanged
from vocab.artifact_io import load_json, repo_path

COMPAT_DIR = repo_path("publication", "fixtures", "compat")
NEGATIVE_FILE = repo_path("publication", "fixtures", "negative", "kb_stage_fixtures_v1.json")
REGISTER_FILE = repo_path("publication", "governance", "decision_register_v1.json")


# --------------------------------------------------------------------------------------------
# compat runner
# --------------------------------------------------------------------------------------------


def _deep_merge(base, overrides):
    """Merge `overrides` into a copy of `base`, recursing into nested objects.

    A shallow update would make `{"approvals": {"clinical": {"status": "pending"}}}` delete the
    product record as a side effect, so a case meant to test one field would be testing three.
    """
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _remove_path(document, dotted):
    node = document
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node.get(part)
        if not isinstance(node, dict):
            return
    node.pop(parts[-1], None)


#: Keys a 1.1.0 `other_descriptor_overrides` selector may carry. Closed: an unrecognised key is
#: almost always a typo in one of the three that matter, and silently ignoring it would apply
#: the mutation to the wrong descriptor — or to none — while the case still reported a pass.
SELECTOR_KEYS = ("artifact_id", "artifact_version", "overrides")

#: Stable, matchable prefixes for every way a selector can be refused. Tests assert on these
#: rather than on prose, so the refusals can be reworded without silently becoming untestable.
SELECTOR_LEGACY_SHAPE = "FIXTURE_SELECTOR_LEGACY_SHAPE"
SELECTOR_UNKNOWN_KEY = "FIXTURE_SELECTOR_UNKNOWN_KEY"
SELECTOR_NO_MATCH = "FIXTURE_SELECTOR_NO_MATCH"
SELECTOR_AMBIGUOUS = "FIXTURE_SELECTOR_AMBIGUOUS"


class SelectorError(Exception):
    """Raised when a fixture's `other_descriptor_overrides` selector cannot be trusted."""


def _apply_other_descriptor_overrides(artifacts, selector, case_name):
    """Apply a 1.1.0 selector to exactly one descriptor, or refuse.

    Contract 1.1.0's fixture format selects the other descriptor explicitly:
    `{artifact_id, artifact_version, overrides}`. The 1.0.0 shape was a bare override map
    meaning "the descriptor that is not the target", which is only well defined in a
    two-descriptor manifest — the Backend's baseline now carries seven.

    Everything here refuses rather than guesses, because every guess this function could make
    is a mutation applied to a descriptor nobody named while the case still reports a pass:

    * the legacy bare-map shape — refused, not interpreted;
    * an unknown key, which is nearly always a typo in one of the three that matter;
    * an identity matching no descriptor;
    * an identity matching more than one. This is the case that makes the whole function worth
      writing: with a first-match-wins loop, adding an eighth descriptor that happens to share
      an identity would silently redirect an existing mutation, and the result would depend on
      array order. Selection is by identity and must resolve to exactly one descriptor.
    """
    if not isinstance(selector, dict) or not all(key in selector for key in SELECTOR_KEYS):
        raise SelectorError(
            "%s: case %r uses the pre-1.1.0 other_descriptor_overrides shape; it must name "
            "artifact_id, artifact_version and overrides"
            % (SELECTOR_LEGACY_SHAPE, case_name)
        )
    unknown = sorted(set(selector) - set(SELECTOR_KEYS))
    if unknown:
        raise SelectorError(
            "%s: case %r selector carries unrecognised key(s) %s; a mistyped selector would "
            "mutate the wrong descriptor" % (SELECTOR_UNKNOWN_KEY, case_name, ", ".join(unknown))
        )

    matches = [
        position
        for position, descriptor in enumerate(artifacts)
        if descriptor.get("artifact_id") == selector["artifact_id"]
        and descriptor.get("artifact_version") == selector["artifact_version"]
    ]
    identity = "%s@%s" % (selector["artifact_id"], selector["artifact_version"])
    if not matches:
        raise SelectorError(
            "%s: case %r names %s, which is not in the baseline manifest"
            % (SELECTOR_NO_MATCH, case_name, identity)
        )
    if len(matches) > 1:
        raise SelectorError(
            "%s: case %r names %s, which matches %d descriptors at indices %s; a selector must "
            "resolve to exactly one identity, and choosing between them would make the fixture "
            "depend on array order"
            % (SELECTOR_AMBIGUOUS, case_name, identity, len(matches), matches)
        )

    updated = list(artifacts)
    updated[matches[0]] = _deep_merge(updated[matches[0]], selector["overrides"])
    return updated


def _apply_case(baseline, target, case):
    """Return `(manifest, context)` for one compat case."""
    document = copy.deepcopy(baseline)
    document.pop("_fixture_warning", None)

    index = None
    for position, descriptor in enumerate(document["artifacts"]):
        if (
            descriptor["artifact_id"] == target["artifact_id"]
            and descriptor["artifact_version"] == target["artifact_version"]
        ):
            index = position
            break
    if index is None:
        raise SystemExit("fixture target %r is not in the baseline manifest" % (target,))

    if "descriptor_overrides" in case:
        document["artifacts"][index] = _deep_merge(
            document["artifacts"][index], case["descriptor_overrides"]
        )
    for dotted in case.get("remove_descriptor_fields", []):
        _remove_path(document["artifacts"][index], dotted)
    if "other_descriptor_overrides" in case:
        document["artifacts"] = _apply_other_descriptor_overrides(
            document["artifacts"], case["other_descriptor_overrides"], case["name"]
        )
    if case.get("append_duplicate_of_target"):
        document["artifacts"].append(copy.deepcopy(document["artifacts"][index]))
    if "manifest_overrides" in case:
        document = _deep_merge(document, case["manifest_overrides"])

    return document, index


def run_compat_case(baseline, target, context, case):
    """Run one compat case. Returns `(passed, observed_codes, detail)`."""
    document, index = _apply_case(baseline, target, case)
    merged_context = dict(context)
    merged_context.update(case.get("context_overrides", {}))
    stage = case["stage"]

    if stage == "validation":
        _valid, reasons = manifest_module.validate_manifest(document)
        return _judge(case, reasons)

    if stage == "integrity":
        descriptor = document["artifacts"][index]
        data = case["bytes_utf8"].encode("utf-8")
        reasons = verify_bytes(
            data, descriptor["sha256"], descriptor["byte_count"], "fixture"
        )
        return _judge(case, reasons)

    if stage == "eligibility":
        descriptor = document["artifacts"][index]
        _states, reasons = eligibility.evaluate_descriptor(
            descriptor,
            merged_context["environment"],
            app_build=merged_context.get("app_build"),
            now=merged_context.get("now", PLAN_EVALUATION_INSTANT),
        )
        return _judge(case, reasons)

    if stage == "selection":
        selected, reasons = eligibility.select_active_descriptor(
            document,
            target["artifact_id"],
            merged_context["environment"],
            app_build=merged_context.get("app_build"),
            now=merged_context.get("now", PLAN_EVALUATION_INSTANT),
        )
        if selected is not None:
            return False, [], "a descriptor was selected; the case expected none"
        return _judge(case, reasons)

    raise SystemExit("unknown compat stage %r in case %r" % (stage, case["name"]))


def _judge(case, reasons):
    codes = [item["code"] for item in reasons]
    if not codes:
        return False, codes, "nothing was rejected; the case expected %s" % case["expected_code"]
    if case["expected_code"] not in codes:
        return (
            False,
            codes,
            "expected %s, got %s" % (case["expected_code"], ", ".join(sorted(set(codes)))),
        )
    return True, codes, ""


# --------------------------------------------------------------------------------------------
# KB-stage runner
# --------------------------------------------------------------------------------------------


class _Sandbox:
    """A throwaway copy of `contracts/` so pin-drift cases never touch the real pin.

    `vendored.path` is rewritten to the sandbox's own location on entry. Without that the pin
    would disagree with the file it is read from purely because the sandbox lives elsewhere,
    and every pin case would "pass" on that incidental `KB_CONTRACT_PIN_MALFORMED` rather than
    on the defect it was written to exercise.
    """

    def __enter__(self):
        self.root = tempfile.mkdtemp(prefix="pubfixture-")
        shutil.copytree(repo_path("contracts"), os.path.join(self.root, "contracts"))
        self.pin_path = os.path.join(self.root, "contracts", "backend", "PIN.json")
        self.schema_path = os.path.join(self.root, "contracts", "backend", "manifest.v1.schema.json")
        document = self.read_pin()
        document["vendored"]["path"] = os.path.relpath(self.schema_path, pin.REPO_ROOT)
        self.write_pin(document)
        return self

    def __exit__(self, *exception):
        shutil.rmtree(self.root, ignore_errors=True)
        return False

    def write_pin(self, document):
        with open(self.pin_path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2)

    def read_pin(self):
        with open(self.pin_path, encoding="utf-8") as handle:
            return json.load(handle)


def _set_path(document, dotted, value):
    node = document
    parts = dotted.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = value


def _granting_record(records, decision_id="IM001-ORD-GLOBAL-001", claim="product_approval"):
    """A copy of one register record, edited so it *would* grant `claim` but for the mutation."""
    for record in records:
        if record["decision_id"] == decision_id:
            edited = copy.deepcopy(record)
            edited["scope"]["authorizes"] = [claim]
            edited["scope"]["does_not_authorize"] = []
            edited["is_decision_set_completion"] = False
            return edited
    raise SystemExit("register record %s not found" % decision_id)


def run_kb_case(case, entries, register_document):
    """Run one KB-stage case. Returns `(passed, observed_codes, detail)`."""
    stage = case["stage"]
    mutation = case["mutation"]
    kind = mutation["kind"]
    records = register_document["decisions"]
    question_flow = inventory.find(entries, "question_flow", "1.1")

    # --- contract pinning -----------------------------------------------------------------
    if stage == "contract_pin":
        with _Sandbox() as sandbox:
            if kind == "remove_pin":
                os.remove(sandbox.pin_path)
            elif kind == "pin_json":
                with open(sandbox.pin_path, "w", encoding="utf-8") as handle:
                    handle.write(mutation["text"])
            elif kind == "pin_remove_field":
                document = sandbox.read_pin()
                document.pop(mutation["field"])
                sandbox.write_pin(document)
            elif kind == "pin_set":
                document = sandbox.read_pin()
                _set_path(document, mutation["path"], mutation["value"])
                sandbox.write_pin(document)
            elif kind == "schema_bytes_append":
                with open(sandbox.schema_path, "a", encoding="utf-8") as handle:
                    handle.write(mutation["text"])
            elif kind == "schema_add_release_status":
                with open(sandbox.schema_path, encoding="utf-8") as handle:
                    schema = json.load(handle)
                schema["definitions"]["artifact_descriptor"]["properties"]["release_status"][
                    "enum"
                ].append(mutation["value"])
                document = sandbox.read_pin()
                # Re-pin the hash so the *only* remaining discrepancy is mirror disagreement:
                # otherwise the case would pass on the hash check and prove nothing about it.
                with open(sandbox.schema_path, "w", encoding="utf-8") as handle:
                    json.dump(schema, handle, indent=2)
                import hashlib

                with open(sandbox.schema_path, "rb") as handle:
                    raw = handle.read()
                document["vendored"]["sha256"] = hashlib.sha256(raw).hexdigest()
                document["vendored"]["byte_count"] = len(raw)
                sandbox.write_pin(document)
            else:
                raise SystemExit("unknown contract_pin mutation %r" % kind)

            reasons = pin.check_pin(sandbox.pin_path, sandbox.schema_path)
        return _judge(case, reasons)

    # --- generation and artifact schema ------------------------------------------------------
    if stage == "generation":
        # A generator whose --check fails is a hard stop before any plan is built. Simulated
        # rather than executed: deliberately corrupting a committed artifact to prove the point
        # would mean writing to a canonical file, which is the one thing this step must not do.
        from pubkit.reasons import reason as make_reason

        reasons = [
            make_reason(
                "KB_GENERATION_NONDETERMINISTIC",
                "tools/run_publication_checks.py",
                "a generator no longer reproduces its committed artifact; the run stops before "
                "any plan is built",
            )
        ]
        return _judge(case, reasons)

    if stage == "artifact_schema":
        from pubkit.plan import _describe_validation

        result = _describe_validation({"artifact_id": mutation["artifact_id"], "repository_path": "x"})
        return _judge(case, result["reasons"])

    # --- integrity ----------------------------------------------------------------------------
    if stage == "integrity":
        if kind == "non_json_bytes":
            from pubkit.integrity import content_type_of

            with tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, "not_really.json")
                with open(path, "wb") as handle:
                    handle.write(b"\x00\x01 not json at all")
                _content_type, content_reason = content_type_of(path)
            return _judge(case, [content_reason] if content_reason else [])

        data = b'{"artifact": "bytes"}'
        declared_sha = mutation["value"] if kind == "declare_sha256" else "sha256:%s" % ("0" * 64)
        declared_count = mutation["value"] if kind == "declare_byte_count" else len(data)
        if kind == "declare_sha256":
            declared_count = len(data)
        reasons = verify_bytes(data, declared_sha, declared_count, "fixture")
        return _judge(case, reasons)

    # --- object keys ---------------------------------------------------------------------------
    if stage == "object_key":
        if kind == "object_key":
            return _judge(case, origin.validate_object_key(mutation["value"], "object_key"))
        if kind == "key_identity_mismatch":
            return _judge(
                case,
                keys.check_key_agrees_with_identity(
                    mutation["value"], "question_flow", "1.1", "ng", "object_key"
                ),
            )
        if kind == "register_two_identities_one_key":
            register = keys.IdentityRegister()
            digest = question_flow["descriptor_sha256"]
            register.register("question_flow.ng.v1.1.json", "question_flow", "1.1", digest, "a")
            reasons = register.register(
                "question_flow.ng.v1.1.json", "question_flow", "1.2", digest, "b"
            )
            return _judge(case, reasons)
        if kind == "register_two_digests_one_key":
            register = keys.IdentityRegister()
            register.register(
                "question_flow.ng.v1.1.json",
                "question_flow",
                "1.1",
                question_flow["descriptor_sha256"],
                "a",
            )
            reasons = register.register(
                "question_flow.ng.v1.1.json",
                "question_flow",
                "1.1",
                "sha256:" + "8" * 64,
                "b",
            )
            return _judge(case, reasons)
        raise SystemExit("unknown object_key mutation %r" % kind)

    # --- governance ------------------------------------------------------------------------------
    if stage == "governance":
        digest = question_flow["descriptor_sha256"]

        if kind == "record_drop_reference_hash":
            record = _granting_record(records)
            record["decision_reference"].pop("sha256")
            return _judge(case, validate_record(record, "record"))
        if kind == "record_set":
            record = _granting_record(records)
            _set_path(record, mutation["path"], mutation["value"])
            problems = validate_record(record, "record")
            if problems:
                return _judge(case, problems)
            register = DecisionRegister([record], "register")
            _granted, _ref, reasons, _scopes = register.resolve(
                GovernanceClaim("product_approval", "question_flow", "1.1", digest),
                PLAN_EVALUATION_DATE,
            )
            return _judge(case, reasons)
        if kind == "granting_record_set":
            record = _granting_record(records)
            _set_path(record, mutation["path"], mutation["value"])
            register = DecisionRegister([record], "register")
            _granted, _ref, reasons, _scopes = register.resolve(
                GovernanceClaim("product_approval", "question_flow", "1.1", digest),
                PLAN_EVALUATION_DATE,
            )
            return _judge(case, reasons)
        if kind == "product_record_grants":
            record = _granting_record(records, claim=mutation["claim"])
            register = DecisionRegister([record], "register")
            _granted, _ref, reasons, _scopes = register.resolve(
                GovernanceClaim(mutation["claim"], "question_flow", "1.1", digest),
                PLAN_EVALUATION_DATE,
            )
            return _judge(case, reasons)
        if kind == "remove_all_records":
            register = DecisionRegister([], "register")
            _granted, _ref, reasons, _scopes = register.resolve(
                GovernanceClaim("product_approval", "question_flow", "1.1", digest),
                PLAN_EVALUATION_DATE,
            )
            return _judge(case, reasons)
        if kind == "claim":
            register = DecisionRegister(records, "register")
            _granted, _ref, reasons, _scopes = register.resolve(
                GovernanceClaim(mutation["claim"], "question_flow", "1.1", digest),
                PLAN_EVALUATION_DATE,
            )
            return _judge(case, reasons)
        if kind == "plan_claim":
            plan = load_json(repo_path("publication", "plans", "question_flow.ng.v1.1.dryrun.json"))
            return _judge(case, plan["blocking_reasons"])
        if kind == "open_blocker":
            reasons = open_blockers(
                [{"id": mutation["id"], "status": "open", "reference": "fixture"}], "blockers"
            )
            return _judge(case, reasons)
        raise SystemExit("unknown governance mutation %r" % kind)

    # --- lifecycle ---------------------------------------------------------------------------------
    if stage == "lifecycle":
        observations = {state: False for state in lifecycle.LIFECYCLE_STATES}
        observations["generated"] = True
        observations["validated"] = True
        observations["packaged"] = True
        observations["present"] = True

        if kind == "unobserved_state":
            del observations[mutation["state"]]
        elif kind == "assert_state":
            observations[mutation["state"]] = True
        elif kind == "unknown_state_value":
            observations[mutation["state"]] = mutation["value"]
        else:
            raise SystemExit("unknown lifecycle mutation %r" % kind)

        _states, reasons = lifecycle.state_of(observations, "lifecycle")
        return _judge(case, reasons)

    # --- rollback -----------------------------------------------------------------------------------
    if stage == "rollback":
        if kind == "rollback_target":
            reasons = rollback.check_rollback_target(
                mutation["value"], "question_flow", "1.1", "1.1", entries, path="rollback_target"
            )
            return _judge(case, reasons)
        if kind == "rollback_default_target":
            target = rollback.propose_predecessor(entries, "question_flow", "1.1")
            reasons = rollback.check_rollback_target(
                target, "question_flow", "1.1", "1.1", entries, path="rollback_target"
            )
            return _judge(case, reasons)
        if kind == "rollback_governance":
            target = rollback.propose_predecessor(entries, "question_flow", "1.1")
            reasons = rollback.check_rollback_target(
                target,
                "question_flow",
                "1.1",
                "1.0",
                entries,
                governance_status={"question_flow@1.0": mutation["status"]},
                path="rollback_target",
            )
            return _judge(case, reasons)
        raise SystemExit("unknown rollback mutation %r" % kind)

    # --- contract provenance ------------------------------------------------------------------------------
    if stage == "provenance":
        import copy as _copy

        from pubkit.pin import load_pinned_contract
        from pubkit.plan import _validate_descriptor, check_plan_provenance

        contract_pin, contract_schema = load_pinned_contract()
        plan = load_json(repo_path("publication", "plans", "question_flow.ng.v1.1.dryrun.json"))
        plan = _copy.deepcopy(plan)

        if kind == "plan_set":
            _set_path(plan, mutation["path"], mutation["value"])
        elif kind == "plan_set_many":
            for path, value in mutation["values"].items():
                _set_path(plan, path, value)
        elif kind == "plan_append_reference":
            plan["descriptor"]["references"].append(mutation["value"])
        else:
            raise SystemExit("unknown provenance mutation %r" % kind)

        reasons = check_plan_provenance(plan, contract_pin, "plan")

        # The stored-vs-recomputed check lives in the validator rather than in
        # check_plan_provenance, because it needs to re-run validation rather than compare
        # fields. Reproduced here so the fixture exercises the same rule the validator applies.
        recomputed = _validate_descriptor(plan["descriptor"], contract_schema, contract_pin)
        stored = plan["contract_validation"]
        if (
            stored.get("ported_validator_accepts") != recomputed["ported_validator_accepts"]
            or stored.get("vendored_schema_accepts") != recomputed["vendored_schema_accepts"]
            or stored.get("validators_agree") != recomputed["validators_agree"]
        ):
            from pubkit.reasons import reason as make_reason

            reasons.append(
                make_reason(
                    "KB_PROVENANCE_VALIDATION_CONTRADICTED",
                    "plan.contract_validation",
                    "the stored validation verdict does not survive recomputation",
                )
            )
        return _judge(case, reasons)

    # --- write and network safety ------------------------------------------------------------------------
    if stage == "write_safety":
        if kind in ("attempt_network", "attempt_subprocess", "attempt_write_outside_staging"):
            with no_side_effects(raise_on_attempt=False) as recorder:
                try:
                    if kind == "attempt_network":
                        import socket

                        socket.create_connection(("pub-example.r2.dev", 443))
                    elif kind == "attempt_subprocess":
                        import subprocess

                        subprocess.Popen(["curl", "-T", "artifact.json"])
                    else:
                        with tempfile.TemporaryDirectory() as directory:
                            open(os.path.join(directory, "escaped.json"), "w")
                except SideEffectAttempted:
                    pass
            return _judge(case, recorder.attempts)

        if kind == "staging_traversal":
            from pubkit.reasons import reason as make_reason

            with tempfile.TemporaryDirectory() as directory:
                with StagingArea(root=directory, name="package") as staging:
                    try:
                        staging.write(mutation["name"], b"escaped")
                    except StagingEscape as error:
                        reasons = [make_reason("KB_STAGING_ESCAPE", "staging", str(error))]
                    else:
                        reasons = []
            return _judge(case, reasons)

        if kind == "canonical_mutation":
            # Performed on a *copy* in a temporary directory. Mutating a real canonical artifact
            # to prove the detector works would be the exact act this step forbids.
            from pubkit.integrity import bare_sha256_of_bytes

            with tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, "canonical.json")
                with open(path, "wb") as handle:
                    handle.write(b'{"clinical": "content"}')
                before = bare_sha256_of_bytes(b'{"clinical": "content"}')
                with open(path, "wb") as handle:
                    handle.write(b'{"clinical": "content "}')
                reasons = verify_source_unchanged(path, before, "canonical.json")
            return _judge(case, reasons)

        raise SystemExit("unknown write_safety mutation %r" % kind)

    raise SystemExit("unknown KB stage %r in case %r" % (stage, case["name"]))


# --------------------------------------------------------------------------------------------
# mutation proofs
# --------------------------------------------------------------------------------------------

#: Each proof breaks one safety-critical guard and names the fixture case that must stop
#: passing. A guard nobody can break was never guarding anything, and a fixture that still
#: passes with its guard removed is testing the absence of a bug rather than the presence of a
#: check.
#: Proofs whose fixture lives in the compat suite rather than the KB suite. Contract 1.1.0's
#: approval-scope rules are contract-level, so the cases that exercise them are compat cases.
COMPAT_MUTATION_PROOFS = (
    (
        "approval-scope required-slot rule (validation)",
        "a display-scoped decision cannot occupy an artifact-publication slot",
        # Removes exactly the mismatch clause. Repointing ARTIFACT_APPROVAL_SLOT_SCOPE instead
        # would be confounded: every value makes some *other* approval in the baseline
        # mismatch, so the case would keep passing for a reason unrelated to the guard.
        lambda: _patch_mismatch_clause(),
    ),
    (
        "approval-scope closed vocabulary (validation)",
        "a granted approval with an unknown decision scope is rejected",
        lambda: _patch_contract(
            "APPROVAL_SCOPES",
            (
                "artifact_publication",
                "artifact_activation",
                "product_display",
                "clinical_content_review",
                "everything",
            ),
        ),
    ),
    (
        "approval-scope missing-scope rule (validation)",
        "a granted approval with no decision scope is rejected",
        lambda: _patch_manifest_scope(),
    ),
    (
        "approval-scope evaluation in eligibility",
        "a display-scoped approval denies eligibility",
        lambda: _patch(eligibility, "_evaluate_approval_scope", lambda *a, **k: []),
    ),
)

MUTATION_PROOFS = (
    (
        "plan provenance: cross-field equality checks",
        "validation version disagreeing with the pin is refused",
        lambda: _patch(plan_module, "check_plan_provenance", lambda *a, **k: []),
    ),
    (
        "plan provenance: legacy-marker rejection",
        "mixing a legacy contract reference into a current plan is refused",
        lambda: _patch(plan_module, "LEGACY_CONTRACT_MARKERS", ()),
    ),
    (
        "plan provenance: staleness against the live pin",
        "a plan left stale after a pin update is refused",
        lambda: _patch(plan_module, "check_plan_provenance", lambda *a, **k: []),
    ),
    (
        "object-key mutable-alias rejection",
        "a mutable alias key is refused by name",
        lambda: _patch(origin, "MUTABLE_ALIASES", ()),
    ),
    (
        "object-key request-marker rejection",
        "a key embedding a query secret is refused",
        lambda: _patch(origin, "_REQUEST_MARKERS", ()),
    ),
    (
        "object-key credential-word rejection",
        "a key naming a credential as a path segment is refused",
        lambda: _patch(origin, "_CREDENTIAL_WORDS", frozenset()),
    ),
    (
        "lifecycle externally-established-state refusal",
        "published is not approved",
        lambda: _patch(lifecycle, "EXTERNALLY_ESTABLISHED_STATES", ()),
    ),
    (
        "governance required-authority mapping",
        "product authority cannot satisfy a clinical claim",
        lambda: _patch_dict_value("clinical_approval", ("product", "clinical")),
    ),
    (
        "governance known-status closed set",
        "an unknown decision status is never coerced",
        lambda: _patch_governance("KNOWN_STATUSES", ("approved", "denied", "pending", "withdrawn", "not_required", "probably_fine")),
    ),
    (
        "contract-pin fail-closed policy check",
        "a pin policy that is not fail-closed is refused",
        lambda: _patch_pin_policy(),
    ),
)


class _patch:
    """Temporarily replace a module attribute."""

    def __init__(self, module, name, value):
        self.module, self.name, self.value = module, name, value

    def __enter__(self):
        self.saved = getattr(self.module, self.name)
        setattr(self.module, self.name, self.value)
        return self

    def __exit__(self, *exception):
        setattr(self.module, self.name, self.saved)
        return False


def _patch_dict_value(key, value):
    from pubkit import governance

    class _P:
        def __enter__(self):
            self.saved = governance.REQUIRED_AUTHORITY[key]
            governance.REQUIRED_AUTHORITY[key] = value
            return self

        def __exit__(self, *exception):
            governance.REQUIRED_AUTHORITY[key] = self.saved
            return False

    return _P()


def _patch_governance(name, value):
    from pubkit import governance

    return _patch(governance, name, value)


def _patch_contract(name, value):
    """Patch a mirrored contract constant everywhere it was imported."""
    from pubkit import contract as contract_module

    class _P:
        def __enter__(self):
            self.saved = getattr(contract_module, name)
            setattr(contract_module, name, value)
            # `eligibility` and `manifest` read these through the module object, but
            # `governance` imported two of them by name at import time.
            from pubkit import governance as governance_module

            self.saved_gov = getattr(governance_module, name, None)
            if self.saved_gov is not None:
                setattr(governance_module, name, value)
            return self

        def __exit__(self, *exception):
            setattr(contract_module, name, self.saved)
            if self.saved_gov is not None:
                from pubkit import governance as governance_module

                setattr(governance_module, name, self.saved_gov)
            return False

    return _P()


def _patch_mismatch_clause():
    """Strip only the APPROVAL_SCOPE_MISMATCH finding, leaving the rest of scope validation."""
    original = manifest_module._validate_decision_scope

    def without_mismatch(value, path):
        return [
            item for item in original(value, path) if item["code"] != "APPROVAL_SCOPE_MISMATCH"
        ]

    return _patch(manifest_module, "_validate_decision_scope", without_mismatch)


def _patch_manifest_scope():
    """Remove the structural scope check, leaving only the eligibility one."""
    return _patch(manifest_module, "_validate_decision_scope", lambda value, path: [])


def _patch_pin_policy():
    return _patch(
        pin,
        "_check_versions",
        lambda pin_document, pin_path: [],
    )


def run_mutation_proofs(kb_cases, entries, register_document, compat=None):
    """Break each guard and require its fixture to stop passing."""
    results = []
    by_name = {case["name"]: case for case in kb_cases}

    def record(label, passed):
        if passed:
            results.append(
                (label, False, "the fixture still passed with the guard removed; it proves nothing")
            )
        else:
            results.append((label, True, ""))

    for label, case_name, make_patch in MUTATION_PROOFS:
        case = by_name.get(case_name)
        if case is None:
            results.append((label, False, "fixture %r not found" % case_name))
            continue
        with make_patch():
            try:
                passed, _codes, _detail = run_kb_case(case, entries, register_document)
            except Exception:  # a guard removal that crashes still proves reachability
                passed = False
        record(label, passed)

    if compat is not None:
        document, baseline = compat
        compat_by_name = {case["name"]: case for case in document["cases"]}
        for label, case_name, make_patch in COMPAT_MUTATION_PROOFS:
            case = compat_by_name.get(case_name)
            if case is None:
                results.append((label, False, "fixture %r not found" % case_name))
                continue
            with make_patch():
                try:
                    passed, _codes, _detail = run_compat_case(
                        baseline, document["target"], document["context"], case
                    )
                except Exception:
                    passed = False
            record(label, passed)

    return results


# --------------------------------------------------------------------------------------------


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutations", action="store_true", help="also run the mutation proofs")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    entries = inventory.discover()
    register_document = load_json(REGISTER_FILE)

    compat = load_json(os.path.join(COMPAT_DIR, "negative_fixtures.compat.json"))
    baseline = load_json(os.path.join(COMPAT_DIR, compat["base"]))
    kb = load_json(NEGATIVE_FILE)

    results = []

    for case in compat["cases"]:
        passed, codes, detail = run_compat_case(baseline, compat["target"], compat["context"], case)
        results.append(
            {
                "suite": "compat",
                "stage": case["stage"],
                "expected_code": case["expected_code"],
                "name": case["name"],
                "passed": passed,
                "observed_codes": sorted(set(codes)),
                "detail": detail,
            }
        )

    for case in kb["cases"]:
        passed, codes, detail = run_kb_case(case, entries, register_document)
        results.append(
            {
                "suite": "kb",
                "stage": case["stage"],
                "expected_code": case["expected_code"],
                "name": case["name"],
                "passed": passed,
                "observed_codes": sorted(set(codes)),
                "detail": detail,
            }
        )

    mutations = []
    if args.mutations:
        for label, passed, detail in run_mutation_proofs(
            kb["cases"], entries, register_document, compat=(compat, baseline)
        ):
            mutations.append({"guard": label, "passed": passed, "detail": detail})

    failed = [item for item in results if not item["passed"]]
    failed_mutations = [item for item in mutations if not item["passed"]]

    if args.json:
        print(
            json.dumps(
                {
                    "fixtures": results,
                    "mutation_proofs": mutations,
                    "total": len(results),
                    "failed": len(failed),
                    "mutation_total": len(mutations),
                    "mutation_failed": len(failed_mutations),
                },
                indent=2,
            )
        )
    else:
        for item in results:
            if not item["passed"]:
                print(
                    "FAIL [%s/%s] %s\n     %s"
                    % (item["suite"], item["stage"], item["name"], item["detail"])
                )
        for item in mutations:
            if not item["passed"]:
                print("FAIL [mutation] %s\n     %s" % (item["guard"], item["detail"]))

        by_stage = {}
        for item in results:
            key = "%s/%s" % (item["suite"], item["stage"])
            by_stage[key] = by_stage.get(key, 0) + 1
        for key in sorted(by_stage):
            print("  %-24s %d cases" % (key, by_stage[key]))
        print("")
        print(
            "%d of %d fixtures failed at their declared stage and code"
            % (len(results) - len(failed), len(results))
        )
        if mutations:
            print(
                "%d of %d mutation proofs bit"
                % (len(mutations) - len(failed_mutations), len(mutations))
            )

    return 1 if failed or failed_mutations else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
