#!/usr/bin/env python3
"""Record the I2/W3 Step 9 Product disposition and open clinical requirements.

    python3 tools/report_im003_disposition.py            # write
    python3 tools/report_im003_disposition.py --check    # fail if stale

Source: the vendored human decision record of 22 August 2026
(baseline/im003_decision_record_v1/). Step 9A supplied the authoritative
reviewer record: Product reviewer Ayodele John Oluwaseyi (Co-Founder & CEO,
WellaPath), review date 2026-08-22. The record's combined source wording
("Clinical Reviewer + Product Lead") is retained only as a faithful record of
the source text and is superseded: NO Clinical reviewer participated or is
assigned. Effective authority is PRODUCT, every disposition is a Product
disposition, and nothing here is clinical approval.

The tool refuses to write at all if the live governance state contradicts the
required classification: IM003-SB-001 must be open, D004 pending, and the
blocker's authorization gates false.

Output: reports/im003_disposition_v1.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

VENDORED = repo_path("baseline", "im003_decision_record_v1",
                     "IM003_SAFETY_REVIEW_DECISION_RECORD_2026-08-22.vendored.md")
REPORT = repo_path("reports", "im003_disposition_v1.json")
BLOCKERS = repo_path("reports", "im003_safety_blockers_v1.json")
PACKAGE = repo_path("reports", "im003_decision_package_v1.json")
MEASUREMENT = repo_path("reports", "im003_mobile_measurement_v1.json")

KB_BASELINE_COMMIT = "83cd52583a14ec9fb656fae6be18ec0df3877a70"
MOBILE_PR_76_HEAD = "13be0d4937b1c49d6a49ddf096c5d5b6a47c2091"

# The provisional safety invariant, verbatim in meaning from the record.
INVARIANT = ("For IM-003, adding evidence must not lower the assessment's "
             "established urgency solely as a consequence of condition "
             "re-ranking.")


def build():
    blockers = load_json(BLOCKERS)
    blocker = next(b for b in blockers["blockers"] if b["blocker_id"] == "IM003-SB-001")
    package = load_json(PACKAGE)
    measurement = load_json(MEASUREMENT)

    def find_decisions(node):
        if isinstance(node, dict):
            if isinstance(node.get("decisions"), list):
                return node["decisions"]
            for value in node.values():
                found = find_decisions(value)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = find_decisions(item)
                if found:
                    return found
        return None

    d004 = next(d for d in find_decisions(package) if "D004" in d["decision_id"])

    # Refuse to write against a contradictory governance state.
    preconditions = {
        "blocker_open": str(blocker["status"]).startswith("open"),
        "d004_pending": d004["status"] == "pending",
        "pr76_not_merge_authorized":
            blocker["mobile_pr_76_merge_authorized_by_this_record"] is False,
        "im003_activation_not_authorized":
            blocker["im003_activation_authorized"] is False,
    }

    report = {
        "_metadata": {
            "artifact": "im003_disposition_v1",
            "phase": "I2/W3 Step 9",
            "generated_by": "tools/report_im003_disposition.py",
            "tooling_version": QFLOW_TOOLING_VERSION,
            "source_record": {
                "title": "I2/W3 IM-003 Safety Review — Decision Record",
                "review_date": "2026-08-22",
                "path": os.path.relpath(VENDORED, repo_path()),
                "sha256": sha256_file(VENDORED),
                "provenance": "supplied_as_chat_text_by_engineering_lead_in_step9_brief",
                "transcription_note": (
                    "No file artifact existed; the vendored file is the "
                    "authoritative transcription. The decision-summary table "
                    "was re-flowed from garbled paste formatting; no wording "
                    "was altered."),
            },
            "kb_baseline_commit": KB_BASELINE_COMMIT,
            "mobile_pr_76": {
                "repository": "Wellapath-org/wellapath-mobile",
                "pull_request": 76,
                "head": MOBILE_PR_76_HEAD,
                "state_required": "OPEN_UNMERGED",
                "merge_authorized": False,
            },
            "what_this_is_not": [
                "This is not clinical approval: the record names no qualified "
                "Clinical reviewer accepting that responsibility.",
                "This is not a resolution of IM003-SB-001.",
                "This is not approval of D004 or any IM-003 decision.",
                "This is not selection of a replacement urgency algorithm.",
                "This is not activation of IM-003 in any environment where a "
                "user could rely on its urgency result.",
            ],
        },

        # --- reviewer identity (Step 9A authoritative record) -----------------
        "reviewer_identity": {
            "product_reviewer": {
                "name": "Ayodele John Oluwaseyi",
                "title": "Co-Founder & CEO, WellaPath",
                "role": "Product reviewer",
                "review_date": "2026-08-22",
            },
            "product_reviewer_is_qualified_clinical_reviewer": False,
            "clinical_reviewer": None,
            "clinical_reviewer_status": "not_assigned",
            "named_qualified_clinical_reviewer": False,
            "source_role_wording": {
                "as_supplied_in_record": "Clinical Reviewer + Product Lead",
                "superseded_by": "the Step 9A authoritative reviewer record above",
                "implies_clinical_reviewer_participation": False,
                "note": ("The combined wording is retained only as a faithful "
                         "record of the source text. No Clinical reviewer "
                         "participated in, signed, or is implied by this "
                         "record; the clinical role is not assigned."),
            },
            "effective_authority": "product",
            "authority_rule": (
                "The named Product reviewer holds Product authority only. "
                "Without a separate explicit record of a named, qualified "
                "Clinical reviewer accepting responsibility, no statement in "
                "the source record may be represented as a clinical decision "
                "or clinical approval. All dispositions below are Product "
                "dispositions; every clinical-side item is an OPEN "
                "requirement."),
        },
        "product_decisions_attribution": {
            "attributed_to": "Ayodele John Oluwaseyi",
            "in_role": "Co-Founder & CEO, WellaPath (Product reviewer)",
            "on_date": "2026-08-22",
            "covers": ["IM003-PD-001", "IM003-PD-002", "IM003-PD-003",
                       "IM003-PD-004", "IM003-PD-005", "IM003-PD-006"],
        },

        # --- required classification, verbatim from the Step 9 brief --------
        "classification": {
            "im003_sb_001": "OPEN",
            "d004": "PENDING",
            "im003": "DISABLED",
            "mobile_pr_76_merge_authorization": False,
            "product_disposition": "RECORDED",
            "clinical_rule": "REQUIRED_NOT_APPROVED",
            "clinical_approval": False,
            "user_facing_internal_evaluation": "BLOCKED",
            "external_beta": "BLOCKED",
            "production": "BLOCKED",
        },
        "live_state_preconditions": preconditions,

        # --- Product decisions (recorded, Product authority) -----------------
        "product_decisions": [
            {
                "id": "IM003-PD-001",
                "title": "Dynamic re-branching is supported in principle",
                "decision": "YES IN PRINCIPLE; NOT AT THE COST OF SAFETY PREDICTABILITY.",
                "detail": ("Later answers making subsequent questioning more "
                           "relevant is a legitimate product benefit; it does "
                           "not justify ranking mechanics silently weakening "
                           "an already-established safety disposition."),
            },
            {
                "id": "IM003-PD-002",
                "title": "Re-ranking alone must not reduce urgency",
                "decision": "Re-ranking alone must never cause urgency de-escalation.",
                "detail": ("From the user's perspective an assessment must not "
                           "establish emergency urgency and then silently "
                           "become merely urgent because another condition "
                           "overtakes the first in an internal ranking. This "
                           "does not prevent Clinical from separately defining "
                           "a legitimate evidence-based de-escalation "
                           "mechanism."),
            },
            {
                "id": "IM003-PD-003",
                "title": "IM-003 urgency monotonicity is required",
                "decision": ("REQUIRED FOR IM-003 UNLESS CLINICAL APPROVES AN "
                             "EXPLICIT DE-ESCALATION RULE."),
                "detail": ("Deliberately narrower than requiring all future "
                           "WellaPath assessment logic to be mathematically "
                           "monotonic. See the provisional safety invariant."),
            },
            {
                "id": "IM003-PD-004",
                "title": "User explanations communicate care urgency, not ranking",
                "decision": "EXPLAIN ESCALATION, NOT INTERNAL CONDITION RANKING.",
                "detail": ("The interface must not expose diagnostic-looking "
                           "ranking logic ('malaria replaced lassa_fever'). "
                           "Acceptable escalation language: 'Based on the "
                           "additional information you provided, we recommend "
                           "getting care more urgently.' No emergency-to-"
                           "urgent explanatory copy is approved, because the "
                           "circumstances in which such de-escalation would "
                           "be acceptable have not been defined."),
            },
            {
                "id": "IM003-PD-005",
                "title": "IM-003 excluded from user-facing internal evaluation",
                "decision": "KEEP IM-003 EXCLUDED FROM USER-FACING INTERNAL EVALUATION.",
                "detail": ("Investigation may continue in controlled test "
                           "environments; the adaptive behaviour stays "
                           "disabled anywhere a user could rely on its "
                           "urgency result, until the clinical rule is "
                           "approved and the regression suite passes."),
            },
            {
                "id": "IM003-PD-006",
                "title": "Constrained alternatives: investigation only",
                "decision": ("A CONSTRAINED SUBSET MAY BE EVALUATED SEPARATELY "
                             "BUT IS NOT PRE-APPROVED AND NOT ACTIVATED BY "
                             "THIS DECISION."),
                "detail": ("A subset may return for its own review only with "
                           "evidence that it cannot reduce established "
                           "urgency, suppress or bypass applicable red flags, "
                           "remove clinically material evidence, change "
                           "clinical semantics through ranking alone, or "
                           "introduce an unreviewed de-escalation path."),
                "investigation_permitted": True,
                "pre_approved": False,
                "activation_authorized": False,
            },
        ],
        "product_decisions_are_clinical_decisions": False,

        # --- open clinical requirements (NOT decisions) -----------------------
        "clinical_requirements": [
            {
                "id": "IM003-CR-001",
                "question": ("When does a ranked condition have sufficient "
                             "clinical support for its urgency classification "
                             "to affect the final assessment urgency?"),
                "context": ("The missing policy Step 8A exposed. Until it "
                            "exists the system must not assume that falling "
                            "from rank 1 to rank 3 makes an emergency "
                            "implication irrelevant."),
            },
            {
                "id": "IM003-CR-002",
                "question": ("Whether and when may urgency de-escalate after "
                             "additive evidence?"),
                "context": ("The record distinguishes evidence that makes the "
                            "emergency hypothesis no longer clinically "
                            "credible from evidence that merely lets another "
                            "condition out-rank it; S10 demonstrates the "
                            "latter."),
            },
            {
                "id": "IM003-CR-003",
                "question": ("Should final urgency consider one condition, "
                             "multiple qualifying conditions, or a calibrated "
                             "threshold?"),
                "context": ("None of the three mechanisms is approved. "
                            "First-ranked-only is demonstrated insufficiently "
                            "safe for IM-003 as exercised; highest-of-all "
                            "risks systematic over-triage; a threshold needs "
                            "clinical calibration Product cannot invent."),
            },
            {
                "id": "IM003-CR-004",
                "question": "Is S10 clinically plausible and in scope?",
                "context": ("Not established by the evidence provided, and "
                            "not dismissable as an unrealistic edge case on "
                            "present information. Clinical must inspect the "
                            "complete S10 evidence vector, demographics, "
                            "triggering answers and assessment context."),
            },
            {
                "id": "IM003-CR-005",
                "question": ("Is the lassa_fever-to-malaria ranking transition "
                             "clinically appropriate?"),
                "context": ("The numerical transition (lassa_fever 26 to rank "
                            "3; malaria 25 to 52, rank 1) is demonstrated; "
                            "score movement alone does not establish clinical "
                            "appropriateness, and Product must not infer it."),
            },
            {
                "id": "IM003-CR-006",
                "question": ("Does lassa_fever at score 26 / rank 3 require "
                             "emergency urgency?"),
                "context": ("The evidence establishes the unchanged score and "
                            "emergency default, not whether score 26 is "
                            "sufficient clinical credibility to force "
                            "emergency urgency."),
            },
            {
                "id": "IM003-CR-007",
                "question": ("Which population-specific and ranking-"
                             "competition regression cases are required?"),
                "context": ("Includes paediatric, pregnancy and other "
                            "population-specific coverage, and the ten "
                            "required case classes below."),
            },
        ],
        "clinical_requirements_status": "OPEN_REQUIREMENTS_NOT_DECISIONS",

        # --- provisional safety invariant ------------------------------------
        "provisional_safety_invariant": {
            "id": "IM003-INV-001",
            "statement": INVARIANT,
            "status": "provisional_pending_explicit_clinical_rule",
            "scope": "IM-003 adaptive re-branching only",
            "generalized_to_all_wellapath_behavior": False,
            "generalization_requires": "separate clinical approval",
            "clinically_approved": False,
            "may_be_superseded_by": ("an explicit, clinically defined and "
                                     "validated de-escalation rule"),
        },

        # --- required regression case classes --------------------------------
        "required_regression_case_classes": [
            {"id": "IM003-RC-01", "case_class": ("emergency condition rank 1 to rank 2/3 "
                                                 "while its score is unchanged")},
            {"id": "IM003-RC-02", "case_class": ("emergency condition rank 1 to lower rank "
                                                 "while its score increases")},
            {"id": "IM003-RC-03", "case_class": ("emergency condition entering the ranking "
                                                 "after additive evidence")},
            {"id": "IM003-RC-04", "case_class": "multiple simultaneous emergency-default conditions"},
            {"id": "IM003-RC-05", "case_class": ("emergency + urgent and emergency + non-urgent "
                                                 "ranking competition")},
            {"id": "IM003-RC-06", "case_class": ("red-flag and non-red-flag versions of "
                                                 "otherwise similar evidence")},
            {"id": "IM003-RC-07", "case_class": ("cases around whatever clinical qualification/"
                                                 "score boundary is ultimately approved")},
            {"id": "IM003-RC-08", "case_class": "repeated re-branching across several answer cycles"},
            {"id": "IM003-RC-09", "case_class": ("paediatric, pregnancy and other population-"
                                                 "specific cases where applicable")},
            {"id": "IM003-RC-10", "case_class": ("cases demonstrating any clinically approved "
                                                 "de-escalation behaviour, if de-escalation is "
                                                 "ultimately permitted")},
        ],
        "regression_requirements": {
            "must_assert_displayed_urgency_directly": True,
            "ranking_stability_alone_is_insufficient": True,
            "required_before": "IM-003 is reconsidered",
        },

        # --- authorization boundaries ----------------------------------------
        "authorization_boundaries": {
            "authorized": [
                "further analysis",
                "clinical review",
                "regression-case design",
                "safety-rule specification",
                "development of proposals and evidence for subsequent review",
            ],
            "not_authorized": [
                "implementation of a chosen urgency aggregation rule",
                "merging Mobile PR #76",
                "publication",
                "activation of IM-003",
                "user-facing internal evaluation of the adaptive behaviour",
                "external beta",
                "production deployment",
            ],
            "investigation_permission_is_activation_permission": False,
        },
        "urgency_algorithm": {
            "selected": False,
            "first_ranked_only_approved_for_im003": False,
            "highest_among_ranked_approved": False,
            "score_confidence_threshold_approved": False,
            "note": ("Selecting among these is a clinical definition task; it "
                     "must not happen in Product review."),
        },
    }
    for requirement in report["clinical_requirements"]:
        requirement["status"] = "open_requirement"
        requirement["product_approved"] = False
    return report, preconditions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report, preconditions = build()

    failed = {k: v for k, v in preconditions.items() if not v}
    if failed:
        print("FAIL live governance state contradicts the required classification:")
        print(json.dumps(failed, indent=2))
        return 1

    data = dump_report_bytes(report)
    relative = os.path.relpath(REPORT, repo_path())
    if args.check:
        if not os.path.exists(REPORT) or open(REPORT, "rb").read() != data:
            print("FAIL %s is missing or stale" % relative)
            return 1
        print("OK   IM-003 Step 9 disposition record is current")
        return 0

    write_bytes(REPORT, data)
    print("wrote %s" % relative)
    identity = report["reviewer_identity"]
    print("  authority: %s — Product reviewer %s (%s); clinical reviewer %s"
          % (identity["effective_authority"],
             identity["product_reviewer"]["name"],
             identity["product_reviewer"]["title"],
             identity["clinical_reviewer_status"]))
    print("  product decisions recorded: %d" % len(report["product_decisions"]))
    print("  open clinical requirements: %d" % len(report["clinical_requirements"]))
    print("  regression case classes: %d" % len(report["required_regression_case_classes"]))
    print("  clinical approval: %s" % report["classification"]["clinical_approval"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
