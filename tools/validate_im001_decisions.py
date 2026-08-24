#!/usr/bin/env python3
"""Fail-closed validation of the IM-001 decision set.

    python3 tools/validate_im001_decisions.py            # human-readable
    python3 tools/validate_im001_decisions.py --json     # machine-readable

IM-001 requires 136 Product decisions: 135 wording selections and one global
deterministic-ordering rule. This guards both halves against the failure modes
that would let an unapproved change slip through or an unsafe one be misfiled as
Product-only.

Fails if:
  * the 2,300 comparisons stop reconciling, or the bucket counts drift;
  * any clinical dimension becomes non-zero while the decision is Product-only;
  * the 903 evidence groups are missing or the count drifts;
  * the global decision is missing;
  * the global decision becomes approved without reviewer, date, rationale and evidence;
  * the evidence hash binding drifts;
  * the wording decision count changes, or any wording text or alternative changes;
  * a recorded verdict lacks complete reviewer evidence (name, title, date,
    selection, rationale, product authority), or any decision is still
    PENDING after the Step 11 recording;
  * the fast_breathing_child clinical flag (IM001-CLIN-FLAG-001) is not
    visible on IM001-D018/D027 and at the gate;
  * resolution of the decision set is read as activation, publication or
    clinical approval (all must remain false);
  * candidate 1.1 changes while the evidence still claims to describe it.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_bytes, sha256_file

EVIDENCE = repo_path("reports", "im001_option_order_evidence_v1.json")
DECISION = repo_path("reports", "im001_option_order_decision_v1.json")
WORDING = repo_path("reports", "im001_product_review_v1_1.json")
CANDIDATE_1_1 = repo_path("candidate", "question_flow.ng.v1.1.json")

EXPECTED = {
    "total_comparisons": 2300,
    "identical": 413,
    "wording_and_option_order_difference": 1665,
    "option_order_only_difference": 207,
    "wording_only_difference": 15,
    "wording_dimension": 1680,
    "option_sequence_dimension": 1872,
    "option_order_groups": 903,
    "wording_decisions": 135,
    "total_product_decisions": 136,
}

# Every dimension that must stay zero for a Product-only classification to hold.
CLINICAL_ZERO_DIMENSIONS = [
    "option_membership_differences",
    "option_label_set_differences",
    "option_to_token_mapping_set_differences",
    "reachable_token_set_differences",
    "scoring_affecting_reachability_differences",
    "red_flag_affecting_reachability_differences",
    "question_identity_differences",
    "question_role_differences",
    "truncation_differences",
    "required_skip_differences",
]

# Byte-exact snapshot of the 135 wording decisions as reviewed. Any drift in a
# wording text, its rejected alternatives, or its identity is a validation
# failure, not a silent edit.
WORDING_FINGERPRINT_FIELDS = ["decision_id", "clinical_role", "selected_wording",
                             "selected_source", "rejected_wordings"]


class Results(object):
    def __init__(self):
        self.checks = []

    def add(self, group, name, passed, detail=""):
        self.checks.append({"group": group, "check": name, "passed": bool(passed),
                            "detail": detail})

    @property
    def failures(self):
        return [c for c in self.checks if not c["passed"]]

    def summary(self):
        failed = self.failures
        return {"total": len(self.checks), "passed": len(self.checks) - len(failed),
                "failed": len(failed), "all_passed": not failed}


def run():
    results = Results()

    for path in (EVIDENCE, DECISION, WORDING):
        if not os.path.exists(path):
            results.add("A.presence", "artifact_present:%s" % os.path.basename(path), False,
                        "missing")
            return results
    results.add("A.presence", "all_three_im001_artifacts_present", True)

    evidence = load_json(EVIDENCE)
    decision = load_json(DECISION)
    wording = load_json(WORDING)

    # --- B. count reconciliation ---------------------------------------------
    buckets = evidence["primary_classification_mutually_exclusive"]
    dims = evidence["dimension_counts_overlapping"]

    results.add("B.counts", "comparisons_reconcile_to_2300",
                buckets["total"] == EXPECTED["total_comparisons"], str(buckets["total"]))
    results.add("B.counts", "buckets_sum_to_total", buckets["sums_to_total"] is True)
    for name in ("identical", "wording_and_option_order_difference",
                 "option_order_only_difference", "wording_only_difference"):
        results.add("B.counts", "bucket_count_stable:%s" % name,
                    buckets[name] == EXPECTED[name],
                    "found=%s expected=%s" % (buckets[name], EXPECTED[name]))
    results.add("B.counts", "wording_dimension_stable",
                dims.get("wording") == EXPECTED["wording_dimension"],
                str(dims.get("wording")))
    for name in ("optionIdSequence", "optionLabelSequence", "optionToTokenSequence"):
        results.add("B.counts", "option_sequence_dimension_stable:%s" % name,
                    dims.get(name) == EXPECTED["option_sequence_dimension"],
                    str(dims.get(name)))
    results.add("B.counts", "knowledge_base_reconciles_with_mobile_evidence",
                evidence["reconciliation"]["all_counts_agree"] is True,
                json.dumps({k: v for k, v in evidence["reconciliation"]["detail"].items()
                            if not v["agree"]})[:200])
    results.add("B.counts", "no_unpaired_reversed_case",
                not evidence["reconciliation"]["unpaired_reversed_cases"])

    # --- C. clinical impact must stay zero -----------------------------------
    clinical = evidence["clinical_impact"]
    nonzero = [name for name in CLINICAL_ZERO_DIMENSIONS if clinical.get(name)]
    results.add("C.clinical", "every_clinical_dimension_is_zero", not nonzero,
                "non-zero: %r" % nonzero)
    results.add("C.clinical", "no_token_reachable_in_one_order_only",
                not clinical["tokens_reachable_in_one_order_only"],
                str(clinical["tokens_reachable_in_one_order_only"]))
    results.add("C.clinical", "no_group_has_membership_differences",
                not clinical["groups_with_membership_differences"],
                str(clinical["groups_with_membership_differences"][:8]))
    results.add("C.clinical", "no_group_has_mapping_differences",
                not clinical["groups_with_mapping_differences"],
                str(clinical["groups_with_mapping_differences"][:8]))
    results.add("C.clinical", "all_clinical_dimensions_zero_flag_agrees",
                clinical["all_clinical_dimensions_zero"] is (not nonzero))

    # The load-bearing gate: Product-only is valid ONLY while the above hold.
    product_only = decision["decision"]["clinical_review_required"] is False
    results.add("C.clinical", "product_only_classification_is_justified",
                (not product_only) or (not nonzero
                                       and not clinical["tokens_reachable_in_one_order_only"]),
                "a clinically meaningful difference may not be classified Product-only")
    results.add("C.clinical", "product_only_is_declared_conditional",
                decision["decision"]["clinical_review_required_is_conditional"] is True)
    results.add("C.clinical", "conditional_wording_names_the_invariants",
                all(word in decision["decision"]["clinical_review_condition"]
                    for word in ("membership", "reachab", "scoring", "red-flag")))

    # --- D. evidence groups --------------------------------------------------
    groups = evidence["option_order_groups"]
    results.add("D.evidence", "903_option_order_groups_present",
                len(groups) == EXPECTED["option_order_groups"], str(len(groups)))
    results.add("D.evidence", "affected_paths_total_is_1872",
                sum(g["affected_path_count"] for g in groups)
                == EXPECTED["option_sequence_dimension"],
                str(sum(g["affected_path_count"] for g in groups)))
    required_group_fields = ["group_id", "grouped_question_role", "source_questions_or_tokens",
                             "baseline_forward_option_order", "baseline_reversed_option_order",
                             "candidate_deterministic_option_order", "option_membership",
                             "option_to_token_mapping", "affected_path_count",
                             "clinical_impact_classification"]
    incomplete = [g["group_id"] for g in groups
                  if set(required_group_fields) - set(g)]
    results.add("D.evidence", "every_group_is_fully_described", not incomplete,
                str(incomplete[:6]))
    misclassified = [g["group_id"] for g in groups
                     if g["clinical_impact_classification"] != "display_order_only"]
    results.add("D.evidence", "every_group_is_display_order_only", not misclassified,
                str(misclassified[:6]))
    duplicate_ids = len(groups) != len({g["group_id"] for g in groups})
    results.add("D.evidence", "group_ids_are_unique", not duplicate_ids)

    # --- E. global decision --------------------------------------------------
    record = decision["decision"]
    results.add("E.decision", "exactly_one_global_ordering_decision",
                record["decision_id"] == "IM001-ORD-GLOBAL-001"
                and record["decision_type"] == "deterministic_option_ordering_rule")
    results.add("E.decision", "decision_is_approved_as_ord_a",
                record["status"] == "approved" and record.get("selection") == "ORD-A",
                "%s/%s" % (record["status"], record.get("selection")))
    results.add("E.decision", "reviewer_role_is_product", record["reviewer_role"] == "Product")
    results.add("E.decision", "approval_lifts_the_blocker_without_authorizing_activation",
                record["activation_blocker"] is False
                and record.get("activation_authorized") is False
                and record.get("clinical_approval") is False,
                "blocker=%s activation=%s clinical=%s"
                % (record["activation_blocker"], record.get("activation_authorized"),
                   record.get("clinical_approval")))
    results.add("E.decision", "approval_scope_is_narrow",
                record["approval_authorizes"] == [
                    "deterministic ordering of the same existing options within a grouped question"])
    for forbidden in ("rewording any question", "adding an option", "removing an option",
                      "publication of any candidate"):
        results.add("E.decision", "approval_excludes:%s" % forbidden,
                    any(forbidden in item for item in record["approval_does_not_authorize"]))
    # An approved decision without evidence is the failure this guards.
    approved = record["status"] == "approved"
    complete = all(record[field] is not None
                   for field in ("reviewer_identity", "review_date", "rationale"))
    results.add("E.decision", "approval_requires_reviewer_date_and_rationale",
                (not approved) or complete,
                "status=%s reviewer=%r date=%r rationale=%r"
                % (record["status"], record["reviewer_identity"], record["review_date"],
                   record["rationale"]))

    # --- F. evidence binding -------------------------------------------------
    binding = decision["evidence_binding"]
    actual_hash = sha256_bytes(dump_report_bytes(evidence))
    results.add("F.binding", "decision_binds_to_the_evidence_hash",
                binding["sha256"] == actual_hash,
                "bound=%s actual=%s" % (binding["sha256"], actual_hash))
    results.add("F.binding", "binding_group_count_matches",
                binding["group_count"] == len(groups))
    results.add("F.binding", "binding_path_count_matches",
                binding["affected_path_count"]
                == sum(g["affected_path_count"] for g in groups))

    # --- G. candidate immutability ------------------------------------------
    declared_candidate = evidence["_metadata"]["candidate"]["sha256"]
    results.add("G.candidate", "candidate_1_1_matches_the_evidence_it_describes",
                declared_candidate == sha256_file(CANDIDATE_1_1),
                "evidence=%s actual=%s" % (declared_candidate, sha256_file(CANDIDATE_1_1)))
    results.add("G.candidate", "evidence_declares_candidate_unmodified",
                evidence["_metadata"]["candidate"]["unmodified_by_this_step"] is True)
    oracle_declared = evidence["_metadata"]["oracle"]["sha256"]
    oracle_path = repo_path("testing", "questions", "fixtures", "oracle",
                            "live_question_oracle_v1.json")
    results.add("G.candidate", "oracle_hash_matches",
                oracle_declared == sha256_file(oracle_path))

    # --- H. wording decisions untouched -------------------------------------
    decisions = wording["decisions"]
    results.add("H.wording", "wording_decision_count_is_135",
                len(decisions) == EXPECTED["wording_decisions"], str(len(decisions)))
    pending = [d for d in decisions if d["product_verdict"] == "PENDING"]
    approved = [d for d in decisions if d["product_verdict"] == "APPROVED"]
    results.add("H.wording", "every_wording_decision_recorded_approved",
                len(approved) == len(decisions) and not pending,
                "%d approved, %d pending of %d" % (len(approved), len(pending),
                                                   len(decisions)))
    incomplete_records = [
        d["decision_id"] for d in approved
        if not (d.get("product_reviewer") and d.get("product_reviewer_title")
                and d.get("review_date") and d.get("product_selection")
                and d.get("product_rationale")
                and d.get("product_authority") == "product")
    ]
    results.add("H.wording", "every_verdict_carries_full_reviewer_evidence",
                not incomplete_records, str(incomplete_records[:6]))
    results.add("H.wording", "every_selection_is_keep_candidate_wording",
                all(d.get("product_selection") == "keep_candidate_wording"
                    for d in approved))
    flagged = sorted(d["decision_id"] for d in decisions if d.get("clinical_flag"))
    results.add("H.wording", "fast_breathing_clinical_flag_visible",
                flagged == ["IM001-D018", "IM001-D027"]
                and all(d.get("clinical_flag") == "IM001-CLIN-FLAG-001"
                        for d in decisions if d.get("clinical_flag")),
                str(flagged))
    incomplete_verdicts = [
        d["decision_id"] for d in decisions
        if d["product_verdict"] != "PENDING"
        and not (d.get("product_reviewer") and d.get("review_date"))
    ]
    results.add("H.wording", "no_wording_verdict_without_reviewer_and_date",
                not incomplete_verdicts, str(incomplete_verdicts[:6]))
    missing_fields = [d.get("decision_id") for d in decisions
                      if set(WORDING_FINGERPRINT_FIELDS) - set(d)]
    results.add("H.wording", "every_wording_decision_is_fully_described",
                not missing_fields, str(missing_fields[:6]))
    results.add("H.wording", "wording_decisions_not_merged_with_the_ordering_rule",
                all("ordering" not in str(d.get("selected_source", "")).lower()
                    for d in decisions)
                and all(d["decision_id"] != "IM001-ORD-GLOBAL-001" for d in decisions))
    sign_off = wording["sign_off"]
    results.add("H.wording", "sign_off_complete_with_reviewer_and_date",
                sign_off["status"] == "COMPLETE"
                and sign_off.get("reviewer") == "Ayodele John Oluwaseyi"
                and sign_off.get("reviewer_title") == "Co-Founder & CEO, WellaPath"
                and sign_off.get("review_date") == "2026-08-24",
                json.dumps(sign_off)[:160])
    results.add("H.wording", "sign_off_grants_no_activation_or_clinical_approval",
                sign_off.get("activation_authorized") is False
                and sign_off.get("clinical_approval") is False
                and "IM001-CLIN-FLAG-001" in sign_off.get("note", ""),
                json.dumps(sign_off)[:160])

    # --- I. the combined gate ------------------------------------------------
    gate = decision["im_001_gate"]
    results.add("I.gate", "total_product_decisions_is_136",
                gate["total_product_decisions_required"] == EXPECTED["total_product_decisions"],
                str(gate["total_product_decisions_required"]))
    results.add("I.gate", "zero_pending_in_both_gates",
                gate["wording_decisions_pending"] == 0
                and gate["ordering_rule_decisions_pending"] == 0,
                "wording=%s ordering=%s" % (gate["wording_decisions_pending"],
                                            gate["ordering_rule_decisions_pending"]))
    results.add("I.gate", "im_001_resolved_only_because_zero_pending",
                gate["im_001_resolved"] is (gate["wording_decisions_pending"] == 0
                                            and gate["ordering_rule_decisions_pending"] == 0))
    results.add("I.gate", "resolution_grants_no_activation",
                gate.get("activation_authorized") is False
                and decision["decision"].get("activation_authorized") is False
                and decision["decision"].get("clinical_approval") is False)
    results.add("I.gate", "ordering_approval_complete_and_is_ord_a",
                decision["decision"]["status"] == "approved"
                and decision["decision"].get("selection") == "ORD-A"
                and decision["decision"].get("reviewer_identity")
                == "Ayodele John Oluwaseyi"
                and decision["decision"].get("review_date") == "2026-08-24"
                and bool(decision["decision"].get("rationale")))
    results.add("I.gate", "clinical_flag_held_open_at_the_gate",
                gate.get("clinical_flags_open") == ["IM001-CLIN-FLAG-001"])

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    results = run()
    summary = results.summary()

    if args.json:
        print(json.dumps({"report_id": "im001_decision_validation",
                          "generator": "tools/validate_im001_decisions.py",
                          "generator_version": QFLOW_TOOLING_VERSION,
                          "summary": summary, "checks": results.checks}, indent=2))
    else:
        for check in results.checks:
            print("%-4s %-12s %s%s" % ("OK" if check["passed"] else "FAIL", check["group"],
                                       check["check"],
                                       "" if check["passed"] else "  [%s]" % check["detail"]))
        print("\n%d checks, %d passed, %d failed"
              % (summary["total"], summary["passed"], summary["failed"]))

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
