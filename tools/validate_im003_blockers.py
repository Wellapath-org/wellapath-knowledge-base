#!/usr/bin/env python3
"""Fail-closed validation of the IM-003 Mobile measurement and safety blockers.

    python3 tools/validate_im003_blockers.py             # human-readable
    python3 tools/validate_im003_blockers.py --json      # machine-readable
    python3 tools/validate_im003_blockers.py --mutations # prove the checks bite

Fails if:
  * the Mobile evidence hash, byte count or binding changes;
  * any of the 63 scenarios disappears, or an aggregate count drifts;
  * the de-escalation is omitted, flipped to an escalation, or its ranked
    order, additive tokens or exact S10 arithmetic are altered;
  * the primary and overlapping top-condition counts are conflated;
  * IM003-SB-001 is marked resolved without reviewer identity, role, date and rationale;
  * D004 is approved while the blocker is open;
  * IM-003 is described as activation-ready;
  * a red-flag-invariant result is described as urgency-safe;
  * Product-only review is claimed sufficient for a clinical-impact decision;
  * the report claims clinical approval;
  * Mobile PR #76 is described as authorized to merge;
  * evidence and decision-package hashes are inconsistent.
"""

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from vocab.artifact_io import load_json, repo_path, sha256_file

MEASUREMENT = repo_path("reports", "im003_mobile_measurement_v1.json")
BLOCKERS = repo_path("reports", "im003_safety_blockers_v1.json")
PACKAGE = repo_path("reports", "im003_decision_package_v1.json")
IMPACT = repo_path("reports", "im003_impact_analysis_v1.json")
VENDORED = repo_path("baseline", "im003_mobile_v1",
                     "im003_mobile_scoring_measurement_v1.vendored.json")

MOBILE_EVIDENCE_SHA = "fb5aefab9915957f327b70de73e21f02ce0f574163d3b6c9dafa2e43c1f027c5"
MOBILE_EVIDENCE_BYTES = 176163
MOBILE_HEAD = "13be0d4937b1c49d6a49ddf096c5d5b6a47c2091"

EXPECTED_COUNTS = {
    "total": 63, "urgency_changes": 25, "escalations": 24, "de_escalations": 1,
    "red_flag_changes": 0, "urgency_source_changes": 0,
    "top_condition_changed_overlapping": 31, "top_condition_change_primary": 6,
    "ranking_only": 29, "score_only": 0, "no_effect": 3,
    "newly_reachable_tokens": 15, "affected_conditions": 31,
}

# Phrases that would misrepresent the evidence. Matched case-insensitively
# against the report and blocker registry.
FORBIDDEN_PHRASES = [
    "activation ready", "activation-ready", "ready for activation",
    "urgency safe", "urgency-safe", "clinically safe", "safe to activate",
    "clinically approved", "clinical approval granted",
    "authorized to merge", "authorised to merge", "cleared to merge",
    "product review alone is sufficient", "product-only review is sufficient",
]


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


def run(measurement=None, blockers=None, package=None):
    results = Results()
    measurement = measurement if measurement is not None else load_json(MEASUREMENT)
    blockers = blockers if blockers is not None else load_json(BLOCKERS)
    package = package if package is not None else load_json(PACKAGE)

    # --- A. evidence binding --------------------------------------------------
    source = measurement["_metadata"]["mobile_source"]
    results.add("A.binding", "mobile_evidence_hash_unchanged",
                source["sha256"] == MOBILE_EVIDENCE_SHA, source["sha256"])
    results.add("A.binding", "mobile_evidence_bytes_unchanged",
                source["bytes"] == MOBILE_EVIDENCE_BYTES, str(source["bytes"]))
    results.add("A.binding", "mobile_head_unchanged", source["head"] == MOBILE_HEAD,
                source["head"])
    if os.path.exists(VENDORED):
        results.add("A.binding", "vendored_copy_matches_mobile_head",
                    sha256_file(VENDORED) == MOBILE_EVIDENCE_SHA, sha256_file(VENDORED))
    results.add("A.binding", "ci_conclusion_bound_to_the_measured_head",
                source["ci"]["conclusion"] == "success"
                and source["ci"]["checked_head_sha"] == MOBILE_HEAD)
    results.add("A.binding", "knowledge_base_binding_recorded",
                bool(source.get("knowledge_base_commit")) and bool(source.get("mobile_base_commit")))

    # --- B. counts ------------------------------------------------------------
    counts = measurement["reconciliation"]["counts"]
    results.add("B.counts", "all_counts_reconcile",
                measurement["reconciliation"]["all_counts_agree"] is True,
                json.dumps(measurement["reconciliation"]["drift"])[:200])
    for name, expected in EXPECTED_COUNTS.items():
        results.add("B.counts", "count_stable:%s" % name, counts.get(name) == expected,
                    "found=%s expected=%s" % (counts.get(name), expected))
    partition = measurement["category_definitions"]["mutually_exclusive_partition"]
    results.add("B.counts", "partition_sums_to_total", partition["sums_to_total"] is True,
                "sum=%s" % partition["sum"])
    overlap = measurement["category_definitions"]["overlapping_metrics"]
    results.add("B.counts", "overlapping_metric_is_labelled_as_such",
                overlap["top_condition_changed_total"] == 31
                and overlap["top_condition_changed_and_urgency_changed"]
                + overlap["top_condition_changed_urgency_unchanged"] == 31)
    results.add("B.counts", "primary_and_overlapping_counts_are_not_conflated",
                partition["top_condition_change"] == 6
                and overlap["top_condition_changed_total"] == 31
                and partition["top_condition_change"] != overlap["top_condition_changed_total"]
                and partition["sum"] == 63,
                "partition=%s overlapping=%s" % (partition["top_condition_change"],
                                                 overlap["top_condition_changed_total"]))
    results.add("B.counts", "every_changed_top_condition_became_malaria",
                measurement["category_definitions"]["every_changed_top_condition_became_malaria"] is True)

    # --- C. the de-escalation must survive ------------------------------------
    results.add("C.deescalation", "de_escalation_is_present", counts["de_escalations"] == 1,
                str(counts["de_escalations"]))
    grounding = measurement["im003_sb_001_grounding"]
    results.add("C.deescalation", "s10_is_the_recorded_de_escalation",
                grounding["scenario_id"] == "S10_path_limit_pressure")
    matrix = grounding["before_after_matrix"]
    results.add("C.deescalation", "urgency_moved_emergency_to_urgent",
                matrix["baseline"]["urgency"] == "emergency"
                and matrix["expanded"]["urgency"] == "urgent")
    results.add("C.deescalation", "red_flag_unchanged_false_to_false",
                matrix["baseline"]["red_flag_triggered"] is False
                and matrix["expanded"]["red_flag_triggered"] is False)
    results.add("C.deescalation", "scores_are_the_recorded_ones",
                matrix["baseline"]["lassa_fever_score"] == 26
                and matrix["baseline"]["malaria_score"] == 25
                and matrix["expanded"]["malaria_score"] == 52)
    severity = {"non_urgent": 0, "routine": 0, "urgent": 1, "emergency": 2}
    before = severity.get(matrix["baseline"]["urgency"])
    after = severity.get(matrix["expanded"]["urgency"])
    results.add("C.deescalation", "direction_is_a_de_escalation_not_an_escalation",
                before is not None and after is not None and after < before,
                "%s -> %s" % (matrix["baseline"]["urgency"], matrix["expanded"]["urgency"]))
    results.add("C.deescalation", "top_condition_moved_lassa_fever_to_malaria",
                matrix["baseline"]["top_condition"] == "lassa_fever"
                and matrix["expanded"]["top_condition"] == "malaria",
                "%s -> %s" % (matrix["baseline"]["top_condition"],
                              matrix["expanded"]["top_condition"]))
    # The ranked order must be present, or the top-condition transition is an
    # assertion rather than an observation.
    arithmetic = grounding.get("kb_arithmetic", {})
    ranked_ok = True
    for side in ("baseline", "expanded"):
        entry = arithmetic.get(side, {})
        kb_rank = [r["condition_id"] for r in entry.get("kb_ranked_order_top_8", [])]
        engine_rank = entry.get("engine_ranked_condition_ids") or []
        if not kb_rank or not engine_rank or kb_rank[:len(engine_rank)] != engine_rank:
            ranked_ok = False
    results.add("C.deescalation", "ranked_order_present_and_kb_reproduces_the_engine_order",
                ranked_ok,
                str([[r["condition_id"] for r in arithmetic.get(side, {}).get(
                    "kb_ranked_order_top_8", [])][:3] for side in ("baseline", "expanded")]))
    results.add("C.deescalation", "out_ranked_emergency_condition_still_recorded",
                any(r["condition_id"] == "lassa_fever" for r in
                    arithmetic.get("expanded", {}).get("kb_ranked_order_top_8", [])),
                "lassa_fever remains a scored candidate; relevant to review question 3")
    # Every additive token must survive: dropping one understates the closure.
    results.add("C.deescalation", "all_additive_tokens_recorded",
                len(grounding["added_tokens"]) == 10
                and grounding["added_token_count"] == len(grounding["added_tokens"])
                and set(matrix["expanded"]["tokens"])
                == set(matrix["baseline"]["tokens"]) | set(grounding["added_tokens"]),
                "added=%d declared=%s" % (len(grounding["added_tokens"]),
                                          grounding["added_token_count"]))
    results.add("C.deescalation", "path_limit_validity_is_recorded_and_reasoned",
                bool(grounding.get("path_limit_validity", {}).get("why"))
                and grounding["path_limit_validity"].get("path_limit") == 5)
    results.add("C.deescalation", "grounded_in_kb_2_4", grounding["all_grounded"] is True,
                json.dumps([c for c in grounding["grounding_checks"] if not c["passed"]])[:200])
    # The statement must explicitly deny the inference, not merely be filed under
    # a key whose name denies it. Check the sentence, not the label.
    statement = measurement["mechanism"]["red_flag_invariance_is_insufficient"].lower()
    denies = ("does not prove" in statement or "does not imply" in statement
              or "is not sufficient" in statement)
    results.add("C.deescalation", "red_flag_invariance_is_not_called_urgency_safe",
                denies and "urgency invariance" in statement,
                statement[:120])

    # --- D. blocker record ----------------------------------------------------
    record = next((b for b in blockers["blockers"] if b["blocker_id"] == "IM003-SB-001"), None)
    results.add("D.blocker", "im003_sb_001_is_registered", record is not None)
    if record:
        results.add("D.blocker", "status_is_open_awaiting_adjudication",
                    record["status"] == "open_awaiting_clinical_and_product_adjudication",
                    record["status"])
        results.add("D.blocker", "classification_authority_is_engineering_evidence",
                    record["classification_authority"] == "engineering evidence")
        results.add("D.blocker", "potential_safety_blocker_is_true",
                    record["potential_safety_blocker"] is True)
        for gate in ("clinical_approval", "product_approval", "external_beta_approval",
                     "production_approval", "im003_activation_authorized",
                     "mobile_pr_76_merge_authorized_by_this_record"):
            results.add("D.blocker", "gate_is_false:%s" % gate, record[gate] is False,
                        str(record[gate]))
        results.add("D.blocker", "affected_decision_is_d004", record["affected_decision"] == "D004")
        results.add("D.blocker", "review_milestone_recorded",
                    bool(record["expiry_or_review_milestone"]))
        results.add("D.blocker", "makes_no_safety_judgement",
                    len(record["not_asserted"]) >= 4)
        # Resolution requires full reviewer evidence.
        resolved = not str(record["status"]).startswith("open")
        complete = all(record.get(f) for f in ("resolved_by_reviewer", "resolved_by_role",
                                               "resolution_date", "resolution_rationale"))
        results.add("D.blocker", "resolution_requires_reviewer_role_date_and_rationale",
                    (not resolved) or complete,
                    "status=%s" % record["status"])

    # --- E. D004 --------------------------------------------------------------
    def find_decisions(node):
        if isinstance(node, dict):
            if "decisions" in node and isinstance(node["decisions"], list):
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

    decisions = find_decisions(package) or []
    d004 = next((d for d in decisions if "D004" in d.get("decision_id", "")), None)
    results.add("E.d004", "d004_exists", d004 is not None)
    if d004:
        blocker_open = bool(record) and str(record["status"]).startswith("open")
        results.add("E.d004", "d004_is_pending", d004["status"] == "pending", d004["status"])
        results.add("E.d004", "d004_not_approved_while_the_blocker_is_open",
                    not (blocker_open and d004["status"] == "approved"))
        results.add("E.d004", "d004_requires_clinical_review",
                    "clinical" in str(d004.get("required_reviewers", "")).lower(),
                    str(d004.get("required_reviewers")))
        evidence_blob = json.dumps(d004)
        results.add("E.d004", "d004_records_the_shipped_engine_measurement",
                    "IM003-SB-001" in evidence_blob and "63" in evidence_blob)
    results.add("E.d004", "all_im003_decisions_remain_pending",
                all(d["status"] == "pending" for d in decisions),
                str([d["decision_id"] for d in decisions if d["status"] != "pending"]))

    # --- F. recommendation narrowed ------------------------------------------
    rec = package.get("decomposition_recommendation", {})
    results.add("F.recommendation", "recommendation_is_narrowed_or_suspended",
                rec.get("status") == "NARROWED_PENDING_IM003_SB_001", str(rec.get("status")))
    results.add("F.recommendation", "recommendation_history_retained",
                bool(rec.get("engineering_recommendation")))
    results.add("F.recommendation", "recommendation_authorizes_nothing",
                rec.get("authorizes_implementation") is False
                and rec.get("authorizes_activation") is False)

    # --- G. language guards ---------------------------------------------------
    blob = (json.dumps(measurement) + json.dumps(blockers)).lower()
    hits = [phrase for phrase in FORBIDDEN_PHRASES if phrase in blob]
    # "clinically safe" is permitted only inside an explicit denial.
    allowed_context = measurement["_metadata"]["what_this_is_not"] + (
        record["not_asserted"] if record else [])
    allowed_blob = json.dumps(allowed_context).lower()
    real_hits = [h for h in hits if h not in allowed_blob]
    results.add("G.language", "no_misrepresenting_phrase_outside_an_explicit_denial",
                not real_hits, str(real_hits))
    results.add("G.language", "report_denies_clinical_approval",
                measurement["_metadata"].get("authoritative") is True
                and any("not approval" in x.lower() or "not clinical" in x.lower()
                        for x in measurement["_metadata"]["what_this_is_not"]))
    results.add("G.language", "pr_76_merge_not_authorized",
                any("merging Mobile PR #76" in x for x in measurement["does_not_authorize"]))
    results.add("G.language", "rejected_python_model_not_used",
                measurement["_metadata"]["rejected_python_scoring_model_used"] is False)

    # --- H. cross-artifact hash consistency ----------------------------------
    if os.path.exists(IMPACT):
        impact_declared = measurement["_metadata"]["frozen_clinical_inputs"]["kb_v2_4"]
        results.add("H.consistency", "kb_hash_in_report_matches_the_repository",
                    impact_declared == sha256_file(repo_path("kb.ng.v2.4.json")))
    binding = record["evidence_binding"] if record else {}
    results.add("H.consistency", "blocker_binds_to_the_same_evidence_as_the_report",
                binding.get("sha256") == source["sha256"]
                and binding.get("head") == source["head"])

    return results


# --- mutation proofs ----------------------------------------------------------

def _m_hash_drift(m, b, p):
    m["_metadata"]["mobile_source"]["sha256"] = "0" * 64
    return m, b, p, "A.binding:mobile_evidence_hash_unchanged"


def _m_scenario_lost(m, b, p):
    m["reconciliation"]["counts"]["total"] = 62
    return m, b, p, "B.counts:count_stable:total"


def _m_deescalation_omitted(m, b, p):
    m["reconciliation"]["counts"]["de_escalations"] = 0
    return m, b, p, "C.deescalation:de_escalation_is_present"


def _m_blocker_resolved_without_reviewer(m, b, p):
    b["blockers"][0]["status"] = "resolved"
    return m, b, p, "D.blocker:resolution_requires_reviewer_role_date_and_rationale"


def _m_d004_approved(m, b, p):
    decisions = p["decisions"] if "decisions" in p else None
    if decisions is None:
        for value in p.values():
            if isinstance(value, dict) and "decisions" in value:
                decisions = value["decisions"]
                break
    for d in decisions:
        if "D004" in d["decision_id"]:
            d["status"] = "approved"
    return m, b, p, "E.d004:d004_is_pending"


def _m_activation_ready(m, b, p):
    m["interpretation_note"] = "IM-003 is activation-ready."
    return m, b, p, "G.language:no_misrepresenting_phrase_outside_an_explicit_denial"


def _m_urgency_safe(m, b, p):
    m["mechanism"]["summary"] = "Red flags never changed, so the flow is urgency-safe."
    return m, b, p, "G.language:no_misrepresenting_phrase_outside_an_explicit_denial"


def _m_pr76_authorized(m, b, p):
    b["blockers"][0]["mobile_pr_76_merge_authorized_by_this_record"] = True
    return m, b, p, "D.blocker:gate_is_false:mobile_pr_76_merge_authorized_by_this_record"


def _m_activation_authorized(m, b, p):
    b["blockers"][0]["im003_activation_authorized"] = True
    return m, b, p, "D.blocker:gate_is_false:im003_activation_authorized"


def _m_binding_inconsistent(m, b, p):
    b["blockers"][0]["evidence_binding"]["sha256"] = "1" * 64
    return m, b, p, "H.consistency:blocker_binds_to_the_same_evidence_as_the_report"


def _m_deescalation_flipped_to_escalation(m, b, p):
    matrix = m["im003_sb_001_grounding"]["before_after_matrix"]
    matrix["baseline"]["urgency"] = "urgent"
    matrix["expanded"]["urgency"] = "emergency"
    return m, b, p, "C.deescalation:direction_is_a_de_escalation_not_an_escalation"


def _m_s10_score_changed(m, b, p):
    m["im003_sb_001_grounding"]["before_after_matrix"]["expanded"]["malaria_score"] = 40
    return m, b, p, "C.deescalation:scores_are_the_recorded_ones"


def _m_s10_condition_changed(m, b, p):
    m["im003_sb_001_grounding"]["before_after_matrix"]["baseline"]["top_condition"] = "malaria"
    return m, b, p, "C.deescalation:top_condition_moved_lassa_fever_to_malaria"


def _m_ranked_order_removed(m, b, p):
    m["im003_sb_001_grounding"]["kb_arithmetic"]["expanded"]["kb_ranked_order_top_8"] = []
    return m, b, p, "C.deescalation:ranked_order_present_and_kb_reproduces_the_engine_order"


def _m_additive_token_omitted(m, b, p):
    grounding = m["im003_sb_001_grounding"]
    grounding["added_tokens"] = grounding["added_tokens"][:-1]
    return m, b, p, "C.deescalation:all_additive_tokens_recorded"


def _m_path_limit_validity_dropped(m, b, p):
    m["im003_sb_001_grounding"].pop("path_limit_validity", None)
    return m, b, p, "C.deescalation:path_limit_validity_is_recorded_and_reasoned"


def _m_categories_conflated(m, b, p):
    # The classic misreading: quoting the overlapping 31 as the primary count.
    m["category_definitions"]["mutually_exclusive_partition"]["top_condition_change"] = 31
    return m, b, p, "B.counts:primary_and_overlapping_counts_are_not_conflated"


MUTATIONS = [
    ("evidence hash drift", _m_hash_drift),
    ("a scenario disappears", _m_scenario_lost),
    ("the de-escalation is omitted", _m_deescalation_omitted),
    ("blocker resolved without reviewer evidence", _m_blocker_resolved_without_reviewer),
    ("D004 approved while the blocker is open", _m_d004_approved),
    ("IM-003 described as activation-ready", _m_activation_ready),
    ("red-flag invariance described as urgency-safe", _m_urgency_safe),
    ("PR #76 described as authorized to merge", _m_pr76_authorized),
    ("IM-003 activation described as authorized", _m_activation_authorized),
    ("evidence binding made inconsistent", _m_binding_inconsistent),
    ("the de-escalation flipped to an escalation", _m_deescalation_flipped_to_escalation),
    ("the exact S10 score changed", _m_s10_score_changed),
    ("the S10 top condition changed", _m_s10_condition_changed),
    ("the ranked order removed", _m_ranked_order_removed),
    ("an additive token omitted", _m_additive_token_omitted),
    ("path-limit validity dropped", _m_path_limit_validity_dropped),
    ("primary and overlapping categories conflated", _m_categories_conflated),
]


def run_mutations():
    base = (load_json(MEASUREMENT), load_json(BLOCKERS), load_json(PACKAGE))
    print("mutation proofs — each must trip its named check\n")
    failures = 0
    for label, mutate in MUTATIONS:
        m, b, p, expected = mutate(*copy.deepcopy(base))
        results = run(m, b, p)
        tripped = {"%s:%s" % (c["group"], c["check"]) for c in results.failures}
        ok = expected in tripped
        if not ok:
            failures += 1
        print("  %-4s %-46s -> %s" % ("OK" if ok else "MISS", label, expected))
        if not ok:
            print("       actually tripped: %s" % sorted(tripped)[:3])
    print("\n%d/%d mutations tripped their intended check" % (len(MUTATIONS) - failures, len(MUTATIONS)))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--mutations", action="store_true")
    args = parser.parse_args()

    if args.mutations:
        return run_mutations()

    results = run()
    summary = results.summary()
    if args.json:
        print(json.dumps({"report_id": "im003_blocker_validation",
                          "generator_version": QFLOW_TOOLING_VERSION,
                          "summary": summary, "checks": results.checks}, indent=2))
    else:
        for check in results.checks:
            print("%-4s %-16s %s%s" % ("OK" if check["passed"] else "FAIL", check["group"],
                                       check["check"],
                                       "" if check["passed"] else "  [%s]" % check["detail"]))
        print("\n%d checks, %d passed, %d failed"
              % (summary["total"], summary["passed"], summary["failed"]))
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
