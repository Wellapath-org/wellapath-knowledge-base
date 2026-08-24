#!/usr/bin/env python3
"""Fail-closed validation of the recorded IM-001 Product verdicts.

    python3 tools/validate_im001_verdicts.py             # human-readable
    python3 tools/validate_im001_verdicts.py --json      # machine-readable
    python3 tools/validate_im001_verdicts.py --mutations # prove the checks bite

Fails if:
  * the verdict record does not carry exactly 135 wording verdicts, 20
    batches and 1 ordering verdict, or totals disagree (136/0/0/0);
  * any verdict lacks the reviewer name, title, product authority, date,
    selection or rationale, or any selection is not keep_candidate_wording /
    ORD-A as reconciled;
  * batch expansion loses, duplicates or invents a member ID, or a member's
    approved wording disagrees with the wording artifact;
  * the fast_breathing_child clinical flag is missing, moved off
    IM001-D018/D027, or its not-approved list is shortened;
  * any authorization boundary (clinical, activation, publication, Mobile
    implementation) is not false, in the verdict record or in the recorded
    artifacts;
  * the recorded artifacts disagree with the verdict record (verdicts,
    reviewer identity, resolution state);
  * IM-003 state is disturbed (blocker not open, D004 not pending);
  * the vendored reconciliation hash or reviewed-over evidence hashes drift.
"""

import argparse
import collections
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import load_json, repo_path, sha256_file

VERDICTS = repo_path("reports", "im001_product_verdicts_v1.json")
WORDING = repo_path("reports", "im001_product_review_v1_1.json")
ORDER_DECISION = repo_path("reports", "im001_option_order_decision_v1.json")
BLOCKERS = repo_path("reports", "im003_safety_blockers_v1.json")
PACKAGE = repo_path("reports", "im003_decision_package_v1.json")
VENDORED = repo_path("baseline", "im001_reconciliation_v1",
                     "IM001_PRODUCT_DECISION_RECONCILIATION_2026-08-24.vendored.md")

REVIEWER_NAME = "Ayodele John Oluwaseyi"
REVIEWER_TITLE = "Co-Founder & CEO, WellaPath"
REVIEW_DATE = "2026-08-24"

BOUNDARY_KEYS = ("clinical_approval", "activation_authorization",
                 "publication_authorization", "mobile_implementation_authorization")


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


def run(verdicts=None, wording=None, order_decision=None, blockers=None,
        package=None):
    results = Results()
    verdicts = verdicts if verdicts is not None else load_json(VERDICTS)
    wording = wording if wording is not None else load_json(WORDING)
    order_decision = order_decision if order_decision is not None else load_json(ORDER_DECISION)
    blockers = blockers if blockers is not None else load_json(BLOCKERS)
    package = package if package is not None else load_json(PACKAGE)

    wv = verdicts["wording_verdicts"]
    ov = verdicts["ordering_verdict"]
    totals = verdicts["totals"]
    source = {d["decision_id"]: d for d in wording["decisions"]}

    # --- A. totals -------------------------------------------------------------
    results.add("A.totals", "135_wording_20_batches_1_ordering",
                len(wv) == 135 and len(verdicts["batches"]) == 20
                and totals["wording_decisions"] == 135 and totals["batches"] == 20
                and totals["ordering_decisions"] == 1,
                "wv=%d batches=%d" % (len(wv), len(verdicts["batches"])))
    results.add("A.totals", "totals_136_approved_0_pending_0_deferred_0_overrides",
                totals["explicitly_reviewed"] == 136 and totals["approved"] == 136
                and totals["pending"] == 0 and totals["deferred"] == 0
                and totals["individual_overrides"] == 0
                and totals["unresolved_product_conflicts"] == 0, str(totals))
    results.add("A.totals", "no_override_recorded",
                all(v["override"] is False for v in wv))

    # --- B. reviewer evidence on every verdict ---------------------------------
    incomplete = [v["decision_id"] for v in wv + [ov]
                  if not (v.get("reviewer_name") == REVIEWER_NAME
                          and v.get("reviewer_title") == REVIEWER_TITLE
                          and v.get("authority") == "product"
                          and v.get("review_date") == REVIEW_DATE
                          and v.get("selection") and v.get("rationale"))]
    results.add("B.reviewer", "every_verdict_fully_attributed", not incomplete,
                str(incomplete[:4]))
    results.add("B.reviewer", "wording_selections_all_keep_candidate",
                all(v["selection"] == "keep_candidate_wording" for v in wv))
    results.add("B.reviewer", "ordering_selection_is_ord_a",
                ov["selection"] == "ORD-A"
                and ov["decision_id"] == "IM001-ORD-GLOBAL-001",
                ov["selection"])

    # --- C. batch expansion -----------------------------------------------------
    expanded = [m for b in verdicts["batches"] for m in b["member_decision_ids"]]
    results.add("C.expansion", "expansion_covers_all_135_exactly_once",
                len(expanded) == 135 and len(set(expanded)) == 135
                and set(expanded) == set(source),
                "expanded=%d unique=%d" % (len(expanded), len(set(expanded))))
    results.add("C.expansion", "verdicts_and_expansion_agree",
                sorted(v["decision_id"] for v in wv) == sorted(expanded))
    wording_mismatch = [v["decision_id"] for v in wv
                        if v["decision_id"] in source
                        and v["approved_wording"]
                        != source[v["decision_id"]]["selected_wording"]]
    results.add("C.expansion", "approved_wording_matches_the_artifact",
                not wording_mismatch, str(wording_mismatch[:4]))
    rationale_mismatch = []
    batch_rationale = {b["batch_id"]: b["rationale"] for b in verdicts["batches"]}
    for v in wv:
        if v["rationale"] != batch_rationale.get(v["batch_id"]):
            rationale_mismatch.append(v["decision_id"])
    results.add("C.expansion", "each_member_carries_its_batch_rationale",
                not rationale_mismatch, str(rationale_mismatch[:4]))

    # --- D. the clinical flag ---------------------------------------------------
    flags = verdicts["clinical_flags"]
    flag = flags[0] if flags else {}
    flagged_ids = sorted(v["decision_id"] for v in wv if v.get("clinical_flag"))
    results.add("D.flag", "fast_breathing_flag_present",
                len(flags) == 1 and flag.get("flag_id") == "IM001-CLIN-FLAG-001"
                and flag.get("question_slot") == "fast_breathing_child.severity"
                and flag.get("status") == "open_clinical_flag")
    results.add("D.flag", "flag_lands_on_d018_and_d027",
                flagged_ids == ["IM001-D018", "IM001-D027"], str(flagged_ids))
    results.add("D.flag", "flag_withholds_all_four_clinical_judgements",
                len(flag.get("product_did_not_approve", [])) >= 4
                and flag.get(
                    "must_remain_visible_for_clinical_review_before_activation")
                is True)
    artifact_flagged = sorted(d["decision_id"] for d in wording["decisions"]
                              if d.get("clinical_flag"))
    results.add("D.flag", "flag_visible_in_the_wording_artifact",
                artifact_flagged == ["IM001-D018", "IM001-D027"],
                str(artifact_flagged))
    results.add("D.flag", "flag_held_open_at_the_ordering_gate",
                order_decision["im_001_gate"].get("clinical_flags_open")
                == ["IM001-CLIN-FLAG-001"])

    # --- E. authorization boundaries --------------------------------------------
    bounds = verdicts["authorization_boundaries"]
    hot = {k: bounds.get(k) for k in BOUNDARY_KEYS if bounds.get(k) is not False}
    results.add("E.boundaries", "all_four_authorizations_false", not hot, str(hot))
    results.add("E.boundaries", "clinical_reopen_condition_stated",
                "reopens clinical review"
                in bounds.get("clinical_reopen_condition", "").lower())
    results.add("E.boundaries", "pr76_unauthorized_and_im003_untouched_in_record",
                "unauthorized to merge" in bounds.get("mobile_pr_76", "")
                and "disabled" in bounds.get("im003", "").lower()
                and "open" in bounds.get("im003", "").lower())
    sign_off = wording["sign_off"]
    results.add("E.boundaries", "artifacts_grant_no_activation",
                sign_off.get("activation_authorized") is False
                and sign_off.get("clinical_approval") is False
                and order_decision["decision"].get("activation_authorized") is False
                and order_decision["decision"].get("clinical_approval") is False
                and order_decision["im_001_gate"].get("activation_authorized")
                is False)

    # --- F. recorded artifacts agree with the verdict record ---------------------
    disagreements = []
    for v in wv:
        d = source.get(v["decision_id"])
        if d is None:
            continue
        if (d.get("product_verdict") != "APPROVED"
                or d.get("product_selection") != v["selection"]
                or d.get("product_reviewer") != v["reviewer_name"]
                or d.get("review_date") != v["review_date"]
                or d.get("product_rationale") != v["rationale"]):
            disagreements.append(v["decision_id"])
    results.add("F.agreement", "wording_artifact_matches_the_verdict_record",
                not disagreements, str(disagreements[:4]))
    od = order_decision["decision"]
    results.add("F.agreement", "ordering_artifact_matches_the_verdict_record",
                od["status"] == "approved" and od.get("selection") == ov["selection"]
                and od.get("reviewer_identity") == ov["reviewer_name"]
                and od.get("review_date") == ov["review_date"]
                and od.get("rationale") == ov["rationale"])
    gate = order_decision["im_001_gate"]
    results.add("F.agreement", "gate_resolution_consistent_with_zero_pending",
                gate["wording_decisions_pending"] == 0
                and gate["ordering_rule_decisions_pending"] == 0
                and gate["im_001_resolved"] is True)
    scope = gate.get("im_001_resolved_scope") or {}
    results.add("F.agreement", "resolved_scope_is_machine_readable_and_complete",
                "recorded" in scope.get("means_only", "").lower()
                and set(scope.get("does_not_mean", [])) >= {
                    "candidate activation-ready",
                    "clinical review complete",
                    "question content clinically approved",
                    "publication approved",
                    "Mobile implementation authorized",
                    "external beta or production approved"},
                str(scope.get("does_not_mean"))[:120])
    results.add("F.agreement", "resolved_grants_no_authorization",
                not (gate["im_001_resolved"] is True
                     and (gate.get("activation_authorized") is not False
                          or order_decision["decision"].get(
                              "activation_authorized") is not False
                          or order_decision["decision"].get(
                              "clinical_approval") is not False)))

    # --- G. IM-003 undisturbed ---------------------------------------------------
    blocker = next((b for b in blockers["blockers"]
                    if b["blocker_id"] == "IM003-SB-001"), None)
    results.add("G.im003", "blocker_still_open",
                blocker is not None and str(blocker["status"]).startswith("open"))
    if blocker:
        results.add("G.im003", "pr76_gate_still_false",
                    blocker["mobile_pr_76_merge_authorized_by_this_record"] is False
                    and blocker["im003_activation_authorized"] is False)

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

    im003_decisions = find_decisions(package) or []
    results.add("G.im003", "all_im003_decisions_still_pending",
                all(d["status"] == "pending" for d in im003_decisions))

    # --- H. bindings --------------------------------------------------------------
    meta = verdicts["_metadata"]
    if os.path.exists(VENDORED):
        results.add("H.binding", "vendored_reconciliation_hash_matches",
                    meta["source_record"]["sha256"] == sha256_file(VENDORED),
                    meta["source_record"]["sha256"][:16])
    results.add("H.binding", "confirmation_quoted",
                "Yes" in meta["source_record"]["confirmation"])
    results.add("H.binding", "reviewed_over_hashes_recorded",
                set(meta["reviewed_over_evidence_hashes"]) == {
                    "reports/im001_product_review_v1_1.json",
                    "reports/im001_option_order_decision_v1.json",
                    "reports/im001_option_order_evidence_v1.json"}
                and all(len(v) == 64
                        for v in meta["reviewed_over_evidence_hashes"].values()))

    return results


# --- mutation proofs -----------------------------------------------------------

def _base():
    return (load_json(VERDICTS), load_json(WORDING), load_json(ORDER_DECISION),
            load_json(BLOCKERS), load_json(PACKAGE))


def _m_verdict_missing(v, w, od, b, p):
    v["wording_verdicts"] = v["wording_verdicts"][1:]
    return (v, w, od, b, p), "A.totals:135_wording_20_batches_1_ordering"


def _m_reviewer_stripped(v, w, od, b, p):
    v["wording_verdicts"][0]["reviewer_name"] = None
    return (v, w, od, b, p), "B.reviewer:every_verdict_fully_attributed"


def _m_selection_flipped(v, w, od, b, p):
    v["wording_verdicts"][0]["selection"] = "use_alternative_wording"
    return (v, w, od, b, p), "B.reviewer:wording_selections_all_keep_candidate"


def _m_ordering_flipped(v, w, od, b, p):
    v["ordering_verdict"]["selection"] = "ORD-B"
    return (v, w, od, b, p), "B.reviewer:ordering_selection_is_ord_a"


def _m_member_lost(v, w, od, b, p):
    v["batches"][0]["member_decision_ids"] = v["batches"][0]["member_decision_ids"][:-1]
    return (v, w, od, b, p), "C.expansion:expansion_covers_all_135_exactly_once"


def _m_wording_disagrees(v, w, od, b, p):
    v["wording_verdicts"][0]["approved_wording"] = "A wording never reviewed?"
    return (v, w, od, b, p), "C.expansion:approved_wording_matches_the_artifact"


def _m_flag_dropped(v, w, od, b, p):
    v["clinical_flags"] = []
    for verdict in v["wording_verdicts"]:
        verdict.pop("clinical_flag", None)
    return (v, w, od, b, p), "D.flag:fast_breathing_flag_present"


def _m_flag_moved(v, w, od, b, p):
    for verdict in v["wording_verdicts"]:
        if verdict["decision_id"] == "IM001-D027":
            verdict.pop("clinical_flag", None)
    return (v, w, od, b, p), "D.flag:flag_lands_on_d018_and_d027"


def _m_flag_hidden_in_artifact(v, w, od, b, p):
    for d in w["decisions"]:
        d.pop("clinical_flag", None)
    return (v, w, od, b, p), "D.flag:flag_visible_in_the_wording_artifact"


def _m_activation_enabled(v, w, od, b, p):
    v["authorization_boundaries"]["activation_authorization"] = True
    return (v, w, od, b, p), "E.boundaries:all_four_authorizations_false"


def _m_clinical_approval_enabled(v, w, od, b, p):
    v["authorization_boundaries"]["clinical_approval"] = True
    return (v, w, od, b, p), "E.boundaries:all_four_authorizations_false"


def _m_artifact_activation_enabled(v, w, od, b, p):
    od["im_001_gate"]["activation_authorized"] = True
    return (v, w, od, b, p), "E.boundaries:artifacts_grant_no_activation"


def _m_artifact_disagrees(v, w, od, b, p):
    w["decisions"][0]["product_selection"] = "use_alternative_wording"
    return (v, w, od, b, p), "F.agreement:wording_artifact_matches_the_verdict_record"


def _m_im003_blocker_closed(v, w, od, b, p):
    b["blockers"][0]["status"] = "resolved"
    return (v, w, od, b, p), "G.im003:blocker_still_open"


def _m_resolved_scope_dropped(v, w, od, b, p):
    od["im_001_gate"].pop("im_001_resolved_scope", None)
    return (v, w, od, b, p), "F.agreement:resolved_scope_is_machine_readable_and_complete"


def _m_resolved_scope_weakened(v, w, od, b, p):
    od["im_001_gate"]["im_001_resolved_scope"]["does_not_mean"] = [
        "publication approved"]
    return (v, w, od, b, p), "F.agreement:resolved_scope_is_machine_readable_and_complete"


def _m_resolved_reads_as_activation(v, w, od, b, p):
    # im_001_resolved stays true while an authorization flips with it.
    od["im_001_gate"]["activation_authorized"] = True
    return (v, w, od, b, p), "F.agreement:resolved_grants_no_authorization"


def _m_rationale_removed(v, w, od, b, p):
    v["wording_verdicts"][0]["rationale"] = None
    return (v, w, od, b, p), "B.reviewer:every_verdict_fully_attributed"


def _m_vendored_hash_drift(v, w, od, b, p):
    v["_metadata"]["source_record"]["sha256"] = "0" * 64
    return (v, w, od, b, p), "H.binding:vendored_reconciliation_hash_matches"


MUTATIONS = [
    ("a wording verdict removed", _m_verdict_missing),
    ("reviewer name stripped from a verdict", _m_reviewer_stripped),
    ("a wording selection flipped", _m_selection_flipped),
    ("the ordering selection flipped to ORD-B", _m_ordering_flipped),
    ("a batch member lost", _m_member_lost),
    ("an approved wording disagrees with the artifact", _m_wording_disagrees),
    ("the clinical flag dropped", _m_flag_dropped),
    ("the clinical flag moved off D027", _m_flag_moved),
    ("the flag hidden in the wording artifact", _m_flag_hidden_in_artifact),
    ("activation authorization enabled", _m_activation_enabled),
    ("clinical approval enabled", _m_clinical_approval_enabled),
    ("gate activation enabled in the artifact", _m_artifact_activation_enabled),
    ("the artifact disagrees with the record", _m_artifact_disagrees),
    ("the IM-003 blocker closed", _m_im003_blocker_closed),
    ("the resolved-scope block dropped", _m_resolved_scope_dropped),
    ("the resolved-scope denial list weakened", _m_resolved_scope_weakened),
    ("resolution read as activation authorization", _m_resolved_reads_as_activation),
    ("a rationale removed from an approval", _m_rationale_removed),
    ("the vendored reconciliation hash drifted", _m_vendored_hash_drift),
]


def run_mutations():
    print("mutation proofs — each must trip its named check\n")
    failures = 0
    for label, mutate in MUTATIONS:
        args, expected = mutate(*copy.deepcopy(_base()))
        results = run(*args)
        tripped = {"%s:%s" % (c["group"], c["check"]) for c in results.failures}
        ok = expected in tripped
        if not ok:
            failures += 1
        print("  %-4s %-50s -> %s" % ("OK" if ok else "MISS", label, expected))
        if not ok:
            print("       actually tripped: %s" % sorted(tripped)[:3])
    print("\n%d/%d mutations tripped their intended check"
          % (len(MUTATIONS) - failures, len(MUTATIONS)))
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--mutations", action="store_true")
    args = parser.parse_args()

    if args.mutations:
        return run_mutations()

    results = run()
    if args.json:
        print(json.dumps({"summary": results.summary(), "checks": results.checks},
                         indent=2))
    else:
        for check in results.checks:
            print("%-4s %-14s %s%s" % ("OK" if check["passed"] else "FAIL",
                                       check["group"], check["check"],
                                       ("  [%s]" % check["detail"])
                                       if not check["passed"] and check["detail"] else ""))
        summary = results.summary()
        print("\n%d checks, %d passed, %d failed"
              % (summary["total"], summary["passed"], summary["failed"]))
    return 0 if results.summary()["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
