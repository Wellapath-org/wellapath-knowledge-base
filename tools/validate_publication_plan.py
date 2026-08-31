#!/usr/bin/env python3
"""Validate the committed dry-run publication plans.

    python3 tools/validate_publication_plan.py
    python3 tools/validate_publication_plan.py --json

Checks, for every plan under `publication/plans/`:

  * it satisfies `schema/publication_plan.v1.schema.json`, whose safety-critical fields are
    pinned by `const` — so a plan claiming an upload, a publication, an activation, eligibility
    or a granted approval fails here rather than being read as a report of one;
  * its descriptor satisfies contract 1.1.0 by both routes, and the two routes agree;
  * its integrity fields are the real digest and byte count of the artifact it names, recomputed
    from the bytes on disk rather than trusted from the plan;
  * its object key is safe, immutable, and encodes the identity it claims;
  * every governance claim it makes is refused, and refused with a reason;
  * it is ineligible in every environment, not only the one it targets;
  * it carries no credential, token, presigned URL or query parameter anywhere in its text;
  * its blocking reasons all carry known reason codes.

It then PHI-scans the whole `publication/` and `contracts/` trees. Those are committed JSON
that this step introduced, and `tools/verify_no_clinical_change.py` does not cover them — it
scans the trees the W3 question work produced. Rather than widen that tool's scan (and its
report) from here, this one imports its pattern list, so there is a single definition of what
counts as PHI and the two scans cannot drift apart.

Standard library only, no network.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pubkit import inventory
from pubkit.integrity import measure
from pubkit.keys import check_key_agrees_with_identity
from pubkit.manifest import validate_against_vendored_schema, validate_manifest
from pubkit.origin import validate_object_key
from pubkit.pin import load_pinned_contract
from pubkit.plan import _validate_descriptor, check_plan_provenance
from pubkit.reasons import reason
from pubkit.reasons import ALL_REASON_CODES
from verify_no_clinical_change import PHI_PATTERNS
from vocab.artifact_io import load_json, repo_path
from vocab.schema_check import validate as schema_validate

PLAN_DIR = repo_path("publication", "plans")
PLAN_SCHEMA = repo_path("schema", "publication_plan.v1.schema.json")

#: Patterns that must never appear anywhere in a plan's serialized text. Deliberately broad —
#: a false positive here costs a rename, a false negative costs a leaked credential.
SECRET_PATTERNS = (
    (r"(?i)\bAKIA[0-9A-Z]{16}\b", "an AWS-style access key id"),
    (r"(?i)\bx-amz-(signature|credential|security-token)\b", "a presigned-URL parameter"),
    (r"(?i)\b(aws_secret_access_key|r2_secret|secret_access_key)\b", "a secret key name"),
    (r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}", "a bearer token"),
    (r"(?i)\bghp_[A-Za-z0-9]{20,}", "a GitHub token"),
    (r"https://[^\"\s]*\?[^\"\s]*", "a URL carrying a query string"),
    (r"https://[^\"\s/]*:[^\"\s/@]*@", "a URL embedding credentials"),
)


class _Result(list):
    def add(self, name, passed, detail=""):
        self.append({"check": name, "passed": bool(passed), "detail": detail})
        return passed


RECONCILIATION = repo_path(
    "publication", "fixtures", "compat", "approval_scope_reconciliation_v2.json"
)

#: v1 is history, not a current claim. It records a defect that genuinely existed at Backend
#: fc40ac3e, the Backend cites it by hash, and it is never regenerated.
RECONCILIATION_V1 = repo_path(
    "publication", "fixtures", "compat", "approval_scope_reconciliation_v1.json"
)
RECONCILIATION_V1_SHA256 = "36efa4e908df42b99463c8fe809e11e83e740d20b205f1358c51d17622e194ee"

#: The I3 Step 2A approval-scope ruling, restated as the claims the record must compute true.
#: Kept here rather than only in the record so the check cannot be satisfied by a record that
#: quietly stopped making one of them.
REQUIRED_RECONCILIATION_CLAIMS = (
    "backend_fixture_product_approval_is_now_pending",
    "knowledge_base_product_approval_is_pending",
    "im_001_completion_is_scoped_traceability_only",
    "im_001_completion_is_not_in_the_safety_blocker_channel",
    "prior_substitution_defect_no_longer_reproduces",
    "lifting_clinical_and_blocker_conditions_produces_no_approval",
    "both_encodings_ineligible_in_every_environment",
    "both_encodings_are_now_byte_identical_in_the_product_slot",
)


def validate_approval_scope_reconciliation():
    """Check the approval-scope reconciliation record and re-derive its central claim.

    The record is generated, so it is checked here rather than trusted: the substitution probe
    is re-run from the committed descriptors so that "no evaluator can substitute completion for
    approval" is a measurement taken at check time, not a value someone wrote down.
    """
    from pubkit import eligibility

    results = _Result()

    if not os.path.exists(RECONCILIATION):
        results.add("approval-scope reconciliation record exists", False, "record is absent")
        return results

    record = load_json(RECONCILIATION)
    relative = os.path.relpath(RECONCILIATION, repo_path())

    claims = record.get("claims", {})
    missing = [name for name in REQUIRED_RECONCILIATION_CLAIMS if name not in claims]
    results.add(
        "%s: states every required claim" % relative, not missing, ", ".join(missing)
    )
    failed = [name for name in REQUIRED_RECONCILIATION_CLAIMS if claims.get(name) is not True]
    results.add("%s: every required claim holds" % relative, not failed, ", ".join(failed))

    results.add(
        "%s: records how the prior defect was resolved" % relative,
        record.get("outcome", {}).get("v2_verdict") == "resolved_by_backend",
        str(record.get("outcome", {}).get("v2_verdict")),
    )
    results.add(
        "%s: binds the Backend commit and schema it was evaluated against" % relative,
        record["backend_binding"]["commit"] == "bbaeadd6075eb37fd51acbe04101f939e52c7d48"
        and record["backend_binding"]["schema_sha256"]
        == "948299bc1ca87592e372d4ce889bdd2424a6cfc3d34c7660453dfe7d60d5038a"
        and record["backend_binding"]["schema_byte_count"] == 7806,
    )

    # v1 must still be exactly the bytes the Backend cites. History is preserved, not rewritten.
    if not os.path.exists(RECONCILIATION_V1):
        results.add("the v1 reconciliation record is preserved", False, "record is absent")
    else:
        import hashlib

        with open(RECONCILIATION_V1, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        results.add(
            "the v1 reconciliation record is preserved byte-for-byte",
            digest == RECONCILIATION_V1_SHA256,
            "%s (expected %s)" % (digest, RECONCILIATION_V1_SHA256),
        )

    # Re-derive the substitution-impossibility claim rather than reading it.
    plan = load_json(repo_path("publication", "plans", "question_flow.ng.v1.1.dryrun.json"))
    descriptor = json.loads(json.dumps(plan["descriptor"]))
    descriptor["approvals"]["clinical"] = {
        "required": True, "status": "granted", "decision_ref": "PROBE", "approved_at": None,
    }
    descriptor["blockers"] = [
        {"id": blocker["id"], "status": "resolved", "reference": blocker.get("reference", "")}
        for blocker in descriptor["blockers"]
    ]
    descriptor["release_status"] = "published"
    descriptor["published_at"] = "2026-09-01T00:00:00Z"
    descriptor["activation_status"] = "active"
    descriptor["activation_authorized"] = True
    descriptor["activation_decision_ref"] = "PROBE"
    states, _reasons = eligibility.evaluate_descriptor(
        descriptor, "staging", now=plan["_metadata"]["evaluated_at"]
    )
    results.add(
        "%s: completion cannot substitute for approval (re-derived at check time)" % relative,
        states["approved"] is False and states["eligible_for_environment"] is False,
        "approved=%s eligible=%s" % (states["approved"], states["eligible_for_environment"]),
    )

    # And the historical defective encoding is now rejected at validation, not merely denied.
    replayed = json.loads(json.dumps(plan["descriptor"]))
    replayed["approvals"]["product"] = {
        "required": True,
        "status": "granted",
        "decision_ref": "IM-001 — Product decisions complete; activation remains unauthorized",
        "approved_at": None,
    }
    wrapper = {
        "manifest_version": "1.1.0",
        "generated_at": plan["_metadata"]["evaluated_at"],
        "artifacts": [replayed],
    }
    replay_valid, replay_reasons = validate_manifest(wrapper)
    results.add(
        "%s: the historical defective encoding is now unrepresentable, not merely ineffective"
        % relative,
        replay_valid is False
        and "APPROVAL_SCOPE_MISSING" in [item["code"] for item in replay_reasons],
        "valid=%s codes=%s" % (replay_valid, sorted({r["code"] for r in replay_reasons})),
    )

    # The completed gate must be present, resolved, and must not be in the open set.
    for plan_name in ("question_flow.ng.v1.1.dryrun.json",):
        target = load_json(repo_path("publication", "plans", plan_name))
        blockers = {b["id"]: b["status"] for b in target["descriptor"]["blockers"]}
        # Under 1.1.0 the completed decision is carried in references and in the scope record,
        # not in the blockers list. The blockers list is the safety channel; a completed
        # decision sitting in it inverts its meaning for anyone scanning for what is unresolved.
        results.add(
            "%s: no completed decision is recorded in the safety-blocker channel" % plan_name,
            "IM001-PRODUCT-DISPLAY-DECISIONS" not in blockers
            and all(status == "open" for status in blockers.values()),
            ", ".join("%s=%s" % item for item in sorted(blockers.items())),
        )
        target_scope = target["governance"]["product_approval_scope"]["product_display_decision"]
        results.add(
            "%s: the completed display decision is still recorded, scoped and non-granting"
            % plan_name,
            target_scope["status"] == "complete"
            and target_scope["contract_decision_scopes"] == ["product_display"]
            and target_scope["grants_artifact_publication_product_approval"] is False,
        )
        results.add(
            "%s: the open blocker set is unchanged by the gate" % plan_name,
            {k for k, v in blockers.items() if v == "open"}
            == {"IM001-CLIN-FLAG-001", "IM003-SB-001"},
        )
        results.add(
            "%s: artifact-publication Product approval is still pending" % plan_name,
            target["descriptor"]["approvals"]["product"]["status"] == "pending"
            and target["descriptor"]["approvals"]["product"]["decision_ref"] is None,
        )

    return results


#: Trees this step introduced, scanned with the same PHI patterns the W3 content-safety scan
#: uses. `.md` is included: documentation quotes decision rationale out of clinical records.
CONTENT_SAFETY_TREES = (("publication", (".json", ".md")), ("contracts", (".json", ".md")))

#: The one reviewed exception, matched exactly rather than by file or by pattern.
#:
#: `negative_fixtures.compat.json` contains a URL with `user:pass@` because it is the fixture
#: that proves a credential-bearing URL is REJECTED — the string is the test input for
#: `ORIGIN_HAS_CREDENTIALS`, and no URL can demonstrate that case without containing an `@`.
#: The credentials are the literal words "user" and "pass". Excluding the whole file would
#: stop scanning ~12KB of fixtures to silence one known string; excluding the string keeps
#: everything else scanned and keeps the exception visible.
ALLOWED_MATCHES = {
    (
        "publication/fixtures/compat/negative_fixtures.compat.json",
        "email address",
        "pass@pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev",
    ): "the ORIGIN_HAS_CREDENTIALS negative fixture; literal placeholder credentials in a "
    "case that asserts such URLs are refused",
}


#: Files permitted to name a contract version other than the active pin, each for a stated
#: reason. Everything else in the publication tooling describes the contract in force, and
#: naming a superseded one there is how "validated against 1.0.0" survived the 1.1.0 re-pin.
CONTRACT_NARRATIVE_EXEMPT = {
    "contracts/backend/PIN.json": "records the superseded version it replaced, by design",
    "contracts/backend/legacy/README.md": "describes the legacy material it sits beside",
    "contracts/backend/legacy/manifest.v1.0.0.schema.json": "is the legacy contract",
    "publication/fixtures/compat/legacy_contract_compatibility_v1.json":
        "is the backward-compatibility evidence, which must name 1.0.0 to test it",
    "publication/fixtures/compat/approval_scope_reconciliation_v1.json":
        "is the preserved historical record, bound to the superseded contract",
    "publication/fixtures/compat/approval_scope_reconciliation_v2.json":
        "cites the superseded contract to show the defect it closed",
    "publication/fixtures/negative/kb_stage_fixtures_v1.json":
        "injects superseded values deliberately, as negative test inputs",
    "docs/PUBLICATION_LIFECYCLE.md": "narrates the re-pin and what preceded it",
    "backend_handoff/publication_tooling_v1/README.md": "narrates the re-pin and what preceded it",
    "publication/README.md": "narrates the re-pin and what preceded it",
    "tools/README.md": "narrates the re-pin and what preceded it",
    "tools/pubkit/reasons.py": "documents the codes added by the version that superseded it",
    "tools/pubkit/plan.py": "names the superseded contract in the comment explaining this rule",
    "tools/pubkit/pin.py": "explains the supersession policy",
    "tools/pubkit/contract.py": "records which version the mirror was re-pinned from",
    "tools/pubkit/eligibility.py": "records which version the port was re-pinned from",
    "tools/build_publication_fixtures.py": "constructs the legacy and historical fixtures",
    "tools/validate_publication_plan.py": "is this checker, which names what it forbids",
    "testing/publication/test_publication.py": "asserts on superseded values by name",
    ".github/workflows/i3-publication-tooling.yml": "hash-checks the legacy schema",
}

#: Trees whose prose describes the contract currently in force.
CONTRACT_NARRATIVE_TREES = ("publication", "contracts", "tools/pubkit", "schema")


def scan_contract_narrative(contract_pin):
    """No active file may describe a contract version other than the one pinned.

    Cross-field checks catch a stale *value*; this catches a stale *sentence*. Eight of them
    survived the 1.1.0 re-pin — docstrings and descriptions still saying "contract 1.0.0" in
    code that had just been re-pinned — and none of the structural checks could see them,
    because prose is not a field.
    """
    import re

    results = _Result()
    active = contract_pin["contract"]["contract_version"]
    pattern = re.compile(r"contract[_ ]?(?:version)?\W{0,12}(\d+\.\d+\.\d+)")
    offenders = []
    scanned = 0

    # An exemption names one exact file, and that file must exist. Without this the list
    # accumulates entries for paths that are gone, and a later file created at one of those
    # paths inherits an exemption nobody granted it — which is how a rename silently converts
    # active material into exempt material.
    absent = sorted(path for path in CONTRACT_NARRATIVE_EXEMPT if not os.path.exists(repo_path(path)))
    results.add(
        "every narrative exemption names a file that exists",
        not absent,
        "stale exemption(s): %s" % ", ".join(absent),
    )
    shaped = sorted(
        path for path in CONTRACT_NARRATIVE_EXEMPT
        if path.endswith("/") or any(ch in path for ch in "*?[")
    )
    results.add(
        "every narrative exemption is a single exact path, not a pattern",
        not shaped,
        ", ".join(shaped),
    )

    for tree in CONTRACT_NARRATIVE_TREES:
        root = repo_path(tree)
        if not os.path.isdir(root):
            continue
        for directory, _sub, names in os.walk(root):
            for name in sorted(names):
                if not name.endswith((".py", ".json", ".md", ".yml")):
                    continue
                path = os.path.join(directory, name)
                relative = os.path.relpath(path, repo_path()).replace(os.sep, "/")
                if relative in CONTRACT_NARRATIVE_EXEMPT:
                    continue
                scanned += 1
                with open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
                for found in set(pattern.findall(text)):
                    if found != active:
                        offenders.append("%s names contract %s" % (relative, found))

    results.add(
        "no active file describes a contract other than the pinned %s (%d scanned, %d exempt)"
        % (active, scanned, len(CONTRACT_NARRATIVE_EXEMPT)),
        not offenders,
        "; ".join(offenders[:6]),
    )
    return results


def scan_content_safety():
    """PHI-scan the trees this step introduced. A hit is a failure, not a warning."""
    results = _Result()
    hits = []
    scanned = 0
    allowed = []

    for tree, suffixes in CONTENT_SAFETY_TREES:
        root = repo_path(tree)
        if not os.path.isdir(root):
            continue
        for directory, _subdirectories, names in os.walk(root):
            for name in sorted(names):
                if not name.endswith(suffixes):
                    continue
                path = os.path.join(directory, name)
                relative = os.path.relpath(path, repo_path()).replace(os.sep, "/")
                scanned += 1
                with open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
                for label, pattern in PHI_PATTERNS:
                    for match in pattern.finditer(text):
                        key = (relative, label, match.group(0))
                        if key in ALLOWED_MATCHES:
                            allowed.append(key)
                            continue
                        hits.append("%s: %s -> %s" % (relative, label, match.group(0)))

    results.add(
        "publication/ and contracts/ contain no PHI-shaped content (%d files scanned, %d "
        "reviewed exceptions)" % (scanned, len(allowed)),
        not hits,
        "; ".join(hits[:6]),
    )
    results.add(
        "the content-safety scan actually looked at something",
        scanned >= 10,
        "%d files scanned" % scanned,
    )
    return results


def validate_plan(path, entries, schema, contract_schema, contract_pin):
    results = _Result()
    relative = os.path.relpath(path, repo_path())
    plan = load_json(path)

    with open(path, "rb") as handle:
        raw_text = handle.read().decode("utf-8")

    # --- plan schema ------------------------------------------------------------------------
    errors = schema_validate(plan, schema)
    results.add("%s: satisfies the publication plan schema" % relative, not errors, "; ".join(errors[:4]))

    # --- descriptor against the contract, both routes -----------------------------------------
    descriptor = plan["descriptor"]
    wrapper = {
        "manifest_version": "1.0.0",
        "generated_at": plan["_metadata"]["evaluated_at"],
        "artifacts": [descriptor],
    }
    ported_valid, ported_reasons = validate_manifest(wrapper)
    schema_reasons = validate_against_vendored_schema(wrapper, contract_schema)
    results.add(
        "%s: descriptor is accepted by the ported Backend validator" % relative,
        ported_valid,
        "; ".join("%s %s" % (r["code"], r["path"]) for r in ported_reasons[:4]),
    )
    results.add(
        "%s: descriptor is accepted by the vendored Backend schema" % relative,
        not schema_reasons,
        "; ".join(r["detail"] for r in schema_reasons[:4]),
    )
    results.add(
        "%s: both contract routes agree" % relative,
        ported_valid == (not schema_reasons) and plan["contract_validation"]["validators_agree"],
    )

    # --- integrity, recomputed rather than trusted ----------------------------------------------
    entry = inventory.find(entries, plan["target"]["artifact_id"], plan["target"]["artifact_version"])
    if entry is None:
        results.add("%s: names a governed artifact" % relative, False, "artifact not in inventory")
    else:
        _data, digest, byte_count = measure(os.path.join(inventory.REPO_ROOT, entry["repository_path"]))
        results.add(
            "%s: declared sha256 is the real digest of the artifact bytes" % relative,
            plan["integrity"]["sha256"] == digest == descriptor["sha256"],
            "plan %s, recomputed %s" % (plan["integrity"]["sha256"], digest),
        )
        results.add(
            "%s: declared byte_count is the real size of the artifact bytes" % relative,
            plan["integrity"]["byte_count"] == byte_count == descriptor["byte_count"],
            "plan %s, recomputed %s" % (plan["integrity"]["byte_count"], byte_count),
        )
        results.add(
            "%s: content type was determined from the bytes" % relative,
            plan["integrity"]["content_type"] == "application/json",
        )

    # --- object key ------------------------------------------------------------------------------
    key = plan["object_key"]["proposed"]
    key_reasons = validate_object_key(key, "object_key") + check_key_agrees_with_identity(
        key,
        plan["target"]["artifact_id"],
        plan["target"]["artifact_version"],
        plan["target"]["country"],
        "object_key",
    )
    results.add(
        "%s: object key is safe, immutable and encodes its identity" % relative,
        not key_reasons,
        "; ".join(r["code"] for r in key_reasons),
    )
    results.add("%s: object key equals the descriptor's" % relative, key == descriptor["object_key"])

    # --- governance ---------------------------------------------------------------------------------
    claims = plan["governance"]["claims"]
    results.add(
        "%s: every governance claim is refused" % relative,
        all(claim["granted"] is False for claim in claims),
    )
    results.add(
        "%s: every refused claim carries at least one reason" % relative,
        all(claim["reasons"] for claim in claims),
    )
    results.add(
        "%s: no clinical reviewer is assigned or inferred" % relative,
        plan["governance"]["clinical_reviewer_assigned"] is False
        and all(
            claim["decision_ref"] is None
            for claim in claims
            if claim["kind"] == "clinical_approval"
        ),
    )

    # --- lifecycle and eligibility ------------------------------------------------------------------
    states = plan["lifecycle"]["states"]
    results.add(
        "%s: no externally-established lifecycle state is asserted" % relative,
        all(
            states[state] is False
            for state in ("uploaded", "published", "approved", "active", "eligible_for_environment")
        ),
    )
    results.add(
        "%s: ineligible in every environment, not only the targeted one" % relative,
        all(
            plan["eligibility_by_environment"][environment]["eligible_for_environment"] is False
            for environment in ("development", "staging", "production")
        ),
    )
    results.add(
        "%s: performed no upload, publication, activation or deployment" % relative,
        all(
            plan["operations_performed"][flag] is False
            for flag in (
                "upload_performed",
                "publication_performed",
                "activation_performed",
                "deployment_performed",
                "storage_write_performed",
                "network_access_performed",
                "canonical_bytes_modified",
            )
        ),
    )

    # --- contract provenance --------------------------------------------------------------------
    #
    # Checked against the LIVE pin, not against the plan's own copy of it. A plan that was
    # regenerated before a re-pin will still be internally consistent and completely stale, and
    # only a comparison with the pin as it stands now can tell the difference.
    provenance = check_plan_provenance(plan, contract_pin, relative)
    results.add(
        "%s: contract provenance agrees with the active pin" % relative,
        not provenance,
        "; ".join("%s %s" % (item["code"], item["path"]) for item in provenance[:4]),
    )

    # The stored validation verdict must survive being recomputed. Reading it back would only
    # confirm that the file says what the file says.
    recomputed = _validate_descriptor(descriptor, contract_schema, contract_pin)
    stored = (
        plan["contract_validation"]["ported_validator_accepts"],
        plan["contract_validation"]["vendored_schema_accepts"],
        plan["contract_validation"]["validators_agree"],
    )
    fresh = (
        recomputed["ported_validator_accepts"],
        recomputed["vendored_schema_accepts"],
        recomputed["validators_agree"],
    )
    if stored != fresh:
        results.append(
            {
                "check": "%s: stored validation result matches a fresh recomputation" % relative,
                "passed": False,
                "detail": "%s stored %s, recomputed %s"
                % (reason("KB_PROVENANCE_VALIDATION_CONTRADICTED", relative, "")["code"],
                   stored, fresh),
            }
        )
    else:
        results.add("%s: stored validation result matches a fresh recomputation" % relative, True)

    # --- reason codes -------------------------------------------------------------------------------
    unknown = sorted(
        {
            item["code"]
            for item in plan["blocking_reasons"]
            if item["code"] not in ALL_REASON_CODES
        }
    )
    results.add(
        "%s: every blocking reason carries a known reason code" % relative,
        not unknown,
        ", ".join(unknown),
    )

    # --- secrets ---------------------------------------------------------------------------------------
    found = []
    for pattern, description in SECRET_PATTERNS:
        if re.search(pattern, raw_text):
            found.append(description)
    results.add(
        "%s: contains no credential, token, presigned URL or query parameter" % relative,
        not found,
        "; ".join(found),
    )

    return results


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    contract_pin, contract_schema = load_pinned_contract()
    schema = load_json(PLAN_SCHEMA)
    entries = inventory.discover()

    if not os.path.isdir(PLAN_DIR):
        print("no plans directory at %s" % os.path.relpath(PLAN_DIR, repo_path()))
        return 1

    plans = sorted(name for name in os.listdir(PLAN_DIR) if name.endswith(".dryrun.json"))
    if not plans:
        print("no dry-run plans found; expected at least the two blocked candidates")
        return 1

    results = []
    for name in plans:
        results.extend(
            validate_plan(
                os.path.join(PLAN_DIR, name), entries, schema, contract_schema, contract_pin
            )
        )
    results.extend(scan_contract_narrative(contract_pin))
    results.extend(validate_approval_scope_reconciliation())
    results.extend(scan_content_safety())

    failed = [item for item in results if not item["passed"]]

    if args.json:
        print(json.dumps({"checks": results, "total": len(results), "failed": len(failed)}, indent=2))
    else:
        for item in failed:
            print("FAIL %s\n     %s" % (item["check"], item["detail"]))
        print("%d of %d plan checks passed across %d plans" % (len(results) - len(failed), len(results), len(plans)))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
