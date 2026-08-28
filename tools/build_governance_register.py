#!/usr/bin/env python3
"""Build the publication governance register from this repository's authoritative records.

    python3 tools/build_governance_register.py           # write
    python3 tools/build_governance_register.py --check    # fail if the committed copy differs

Writes `publication/governance/decision_register_v1.json`.

The register is *derived*, never authored. Every decision record it contains is transcribed
from a decision file that already exists in this repository and is bound to that file by path
and sha256. That is the whole design: a generator that reads existing records can restate them
and can fail when they change, but it has no way to invent an approval that nobody gave. If a
record is not in the repository, it is not in the register, and the claim it would have
supported resolves to nothing.

Two absences are recorded as absences rather than filled in:

  * **No Clinical decision record exists**, because no Clinical reviewer is assigned. The
    register therefore contains no clinical record at all — not a pending one, not a
    placeholder. A clinical claim resolves to `KB_DECISION_RECORD_MISSING`, which is the
    truthful answer.
  * **No publication or activation authorization record exists** for any artifact. Same
    treatment, same reason.

Standard library only, no network, no arguments beyond `--check`.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pubkit.governance import DecisionRegister
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

OUTPUT = repo_path("publication", "governance", "decision_register_v1.json")

#: Authoritative sources. Each is hash-bound in the emitted register; if one of them changes,
#: the register changes, `--check` fails, and the change has to be looked at.
SOURCES = {
    "im001_order_decision": "reports/im001_option_order_decision_v1.json",
    "im001_product_review": "reports/im001_product_review_v1_1.json",
    "im001_verdicts": "reports/im001_product_verdicts_v1.json",
    "im003_disposition": "reports/im003_disposition_v1.json",
    "im003_blockers": "reports/im003_safety_blockers_v1.json",
    "candidate_question_flow_1_1": "candidate/question_flow.ng.v1.1.json",
    "candidate_token_dictionary_2_0": "candidate/token_dictionary.ng.v2.0.json",
}


def _source(name):
    return {"path": SOURCES[name], "sha256": sha256_file(repo_path(SOURCES[name]))}


def _artifact_digest(relative_path):
    return "sha256:%s" % sha256_file(repo_path(relative_path))


def build_records():
    """Transcribe every decision record this repository actually holds."""
    order = load_json(repo_path(SOURCES["im001_order_decision"]))
    decision = order["decision"]
    gate = order["im_001_gate"]
    disposition = load_json(repo_path(SOURCES["im003_disposition"]))

    question_flow_digest = _artifact_digest(SOURCES["candidate_question_flow_1_1"])

    records = []

    # --- IM-001 option-ordering rule ---------------------------------------------------------
    # A real, approved Product decision. What it approves is a display-ordering rule, and its
    # own `approval_does_not_authorize` list says publication and activation are not in it.
    # Transcribed with that scope intact rather than widened into "the artifact is approved".
    records.append(
        {
            "decision_id": decision["decision_id"],
            "authority_type": decision["reviewer_authority"],
            "reviewer": {
                "identity": decision["reviewer_identity"],
                "title": decision["reviewer_title"],
            },
            "decision_date": decision["review_date"],
            "status": "approved" if decision["status"] == "approved" else decision["status"],
            "subject": {
                "artifact_id": "question_flow",
                "artifact_version": "1.1",
                "artifact_sha256": question_flow_digest,
                "hash_binding": "bound",
            },
            "rationale": decision["rationale"],
            "decision_reference": _source("im001_order_decision"),
            "scope": {
                "authorizes": [],
                "does_not_authorize": [
                    "product_approval",
                    "clinical_approval",
                    "publication_authorization",
                    "activation_authorization",
                    "mobile_implementation_authorization",
                ],
                "authorizes_verbatim": decision["approval_authorizes"],
                "does_not_authorize_verbatim": decision["approval_does_not_authorize"],
                "note": "This decision approves a deterministic option-ordering rule. It is "
                "Product authority over display order and nothing else; its own record lists "
                "'publication of any candidate' and 'production or beta activation' among what "
                "it does not authorize. `authorizes` is empty because no publication-lifecycle "
                "claim is within its scope — not because the decision is weak or provisional.",
            },
            "supersession": {"superseded_by": None, "revoked": False, "revocation_reference": None},
            "expires_at": None,
            "is_decision_set_completion": False,
            "conditionality": {
                "clinical_review_required": decision["clinical_review_required"],
                "is_conditional": decision["clinical_review_required_is_conditional"],
                "condition": decision["clinical_review_condition"],
            },
        }
    )

    # --- IM-001 decision-set completion -------------------------------------------------------
    # `im_001_resolved: true` with its machine-readable scope, carried as a record so that a
    # claim resolving against it fails with KB_DECISION_SET_IS_NOT_AUTHORIZATION rather than
    # with a generic "not found" that hides what was actually consulted.
    scope = gate["im_001_resolved_scope"]
    records.append(
        {
            "decision_id": "IM001-DECISION-SET-COMPLETE",
            "authority_type": "product",
            "reviewer": {
                "identity": decision["reviewer_identity"],
                "title": decision["reviewer_title"],
            },
            "decision_date": decision["review_date"],
            "status": "approved",
            "subject": {
                "artifact_id": "question_flow",
                "artifact_version": "1.1",
                "artifact_sha256": question_flow_digest,
                "hash_binding": "bound",
            },
            "rationale": gate["note"],
            "decision_reference": _source("im001_order_decision"),
            "scope": {
                "authorizes": [],
                "does_not_authorize": [
                    "product_approval",
                    "clinical_approval",
                    "publication_authorization",
                    "activation_authorization",
                    "mobile_implementation_authorization",
                ],
                "means_only": scope["means_only"],
                "does_not_mean": scope["does_not_mean"],
                "note": scope["machine_note"],
            },
            "supersession": {"superseded_by": None, "revoked": False, "revocation_reference": None},
            "expires_at": None,
            "is_decision_set_completion": True,
            "decision_set": {
                "total_product_decisions_required": gate["total_product_decisions_required"],
                "wording_decisions_pending": gate["wording_decisions_pending"],
                "ordering_rule_decisions_pending": gate["ordering_rule_decisions_pending"],
                "im_001_resolved": gate["im_001_resolved"],
                "verdicts_reference": _source("im001_verdicts"),
                "reading_rule": "im_001_resolved reports that a backlog of Product display "
                "decisions is empty. A count reaching zero is not a permission. Any consumer "
                "reading the boolean MUST read this scope with it.",
            },
        }
    )

    # --- IM-003 Step 9 disposition -------------------------------------------------------------
    # A recorded Product disposition that authorizes nothing and, on its own record, states
    # clinical approval false and IM-003 disabled.
    classification = disposition["classification"]
    reviewer = disposition["reviewer_identity"]["product_reviewer"]
    records.append(
        {
            "decision_id": "IM003-DISPOSITION-001",
            "authority_type": disposition["reviewer_identity"]["effective_authority"],
            "reviewer": {"identity": reviewer["name"], "title": reviewer["title"]},
            "decision_date": reviewer["review_date"],
            "status": "approved",
            "subject": {
                "artifact_id": "question_flow",
                "artifact_version": "1.1",
                "artifact_sha256": question_flow_digest,
                "hash_binding": "bound",
            },
            "rationale": disposition["reviewer_identity"]["authority_rule"],
            "decision_reference": _source("im003_disposition"),
            "scope": {
                "authorizes": [],
                "does_not_authorize": [
                    "product_approval",
                    "clinical_approval",
                    "publication_authorization",
                    "activation_authorization",
                    "mobile_implementation_authorization",
                ],
                "note": "A recorded Product disposition of the IM-003 safety review. It records "
                "what Product decided; it grants no publication-lifecycle permission. The same "
                "record states clinical_approval false, IM-003 DISABLED, and Mobile PR #76 not "
                "merge-authorized.",
            },
            "supersession": {"superseded_by": None, "revoked": False, "revocation_reference": None},
            "expires_at": None,
            "is_decision_set_completion": False,
            "recorded_state": {
                "im003": classification["im003"],
                "im003_sb_001": classification["im003_sb_001"],
                "clinical_rule": classification["clinical_rule"],
                "clinical_approval": classification["clinical_approval"],
                "mobile_pr_76_merge_authorization": classification["mobile_pr_76_merge_authorization"],
                "external_beta": classification["external_beta"],
                "production": classification["production"],
                "product_decisions_are_clinical_decisions": disposition[
                    "product_decisions_are_clinical_decisions"
                ],
            },
        }
    )

    return records


def build_blockers():
    """Open blockers, transcribed from the records that declare them."""
    order = load_json(repo_path(SOURCES["im001_order_decision"]))
    blockers_report = load_json(repo_path(SOURCES["im003_blockers"]))
    disposition = load_json(repo_path(SOURCES["im003_disposition"]))

    entries = []

    for blocker_id in order["im_001_gate"]["clinical_flags_open"]:
        entries.append(
            {
                "id": blocker_id,
                "status": "open",
                "applies_to": [{"artifact_id": "question_flow", "artifact_version": "1.1"}],
                "reference": "Open Clinical flag raised during IM-001 Product review "
                "(fast_breathing_child.severity, IM001-D018/D027). Requires Clinical review "
                "before any activation decision involving that question. No Clinical reviewer "
                "is assigned.",
                "authority_to_resolve": "clinical",
                "source": _source("im001_order_decision"),
            }
        )

    for blocker in blockers_report["blockers"]:
        entries.append(
            {
                "id": blocker["blocker_id"],
                "status": "open" if blocker["status"].startswith("open") else blocker["status"],
                "status_verbatim": blocker["status"],
                "applies_to": [{"artifact_id": "question_flow", "artifact_version": "1.1"}],
                "reference": blocker["title"],
                "authority_to_resolve": "clinical_and_product",
                "source": _source("im003_blockers"),
                "recorded_state": {
                    "clinical_approval": blocker["clinical_approval"],
                    "product_approval": blocker["product_approval"],
                    "im003_activation_authorized": blocker["im003_activation_authorized"],
                    "external_beta_approval": blocker["external_beta_approval"],
                    "production_approval": blocker["production_approval"],
                },
            }
        )

    entries.sort(key=lambda entry: entry["id"])

    # Cross-check against the disposition record so a blocker silently closing in one place
    # while staying open in another is a generation failure rather than a quiet divergence.
    if disposition["classification"]["im003_sb_001"] != "OPEN":
        raise SystemExit(
            "IM003-SB-001 is no longer OPEN in %s; the register must not be regenerated until "
            "that change has been reviewed." % SOURCES["im003_disposition"]
        )

    return entries


def build_governance_state():
    """Recorded governance facts that are not themselves decisions."""
    disposition = load_json(repo_path(SOURCES["im003_disposition"]))
    identity = disposition["reviewer_identity"]

    return {
        "clinical_reviewer": {
            "assigned": identity["named_qualified_clinical_reviewer"],
            "reviewer": identity["clinical_reviewer"],
            "status": identity["clinical_reviewer_status"],
            "product_reviewer_is_qualified_clinical_reviewer": identity[
                "product_reviewer_is_qualified_clinical_reviewer"
            ],
            "authority_rule": identity["authority_rule"],
            "consequence": "No Clinical decision record can exist while no Clinical reviewer is "
            "assigned. This tooling therefore holds no clinical record, assigns no reviewer, "
            "and resolves every clinical claim to KB_DECISION_RECORD_MISSING.",
            "source": _source("im003_disposition"),
        },
        "publication_authorization": {
            "granted": False,
            "record": None,
            "note": "No publication authorization record exists for any artifact in this "
            "repository. Absence is recorded as absence.",
        },
        "activation_authorization": {
            "granted": False,
            "record": None,
            "note": "No activation authorization record exists for any artifact in this "
            "repository. Absence is recorded as absence.",
        },
        "mobile_implementation_authorization": {
            "granted": False,
            "record": None,
            "note": "Not authorized. Mobile PR #76 remains unauthorized to merge; this tooling "
            "instructs Mobile to implement nothing.",
        },
    }


def build():
    records = build_records()
    document = {
        "_metadata": {
            "register_id": "publication_decision_register",
            "version": "1",
            "phase": "I3 / Step 2",
            "generator": "tools/build_governance_register.py",
            "generator_version": "1.0.0",
            "authoritative": False,
            "note": "A derived transcription of decision records that already exist in this "
            "repository, each bound to its source by path and sha256. The sources are "
            "authoritative; this file is a machine-readable index of them and adds no "
            "decision of its own.",
            "sources": {name: _source(name) for name in sorted(SOURCES)},
        },
        "governance_state": build_governance_state(),
        "decisions": records,
        "blockers": build_blockers(),
    }

    # A register that cannot be loaded by the resolver is a generation failure, not something
    # to discover later at plan time.
    register = DecisionRegister(records, "publication/governance/decision_register_v1.json")
    if register.invalid:
        lines = []
        for _record, path, problems in register.invalid:
            for problem in problems:
                lines.append("  %s at %s: %s" % (problem["code"], problem["path"], problem["detail"]))
        raise SystemExit("generated register contains unusable decision records:\n" + "\n".join(lines))

    return document


def main(argv):
    check = "--check" in argv
    document = build()
    data = dump_report_bytes(document)

    if check:
        if not os.path.exists(OUTPUT):
            print("MISSING %s" % os.path.relpath(OUTPUT, repo_path()))
            return 1
        with open(OUTPUT, "rb") as handle:
            committed = handle.read()
        if committed != data:
            print("DRIFT %s is not reproducible from its generator" % os.path.relpath(OUTPUT, repo_path()))
            return 1
        print("OK %s" % os.path.relpath(OUTPUT, repo_path()))
        return 0

    write_bytes(OUTPUT, data)
    print("wrote %s (%d bytes)" % (os.path.relpath(OUTPUT, repo_path()), len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
