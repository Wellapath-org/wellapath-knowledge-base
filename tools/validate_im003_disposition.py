#!/usr/bin/env python3
"""Fail-closed validation of the I2/W3 Step 9 disposition record.

    python3 tools/validate_im003_disposition.py             # human-readable
    python3 tools/validate_im003_disposition.py --json      # machine-readable
    python3 tools/validate_im003_disposition.py --mutations # prove the checks bite

Fails if:
  * the Product reviewer's name, title or review date is missing or blank;
  * effective authority is anything but "product" (never "clinical" or
    "clinical_and_product"), or a Clinical reviewer is inferred from the
    source record's combined-role wording;
  * a Clinical reviewer is fabricated, or clinical_reviewer_status is
    anything except not_assigned while the reviewer is null, or the Product
    reviewer is described as a qualified Clinical reviewer without a
    separate explicit record;
  * the Step 9 identity-deferral note is reinstated;
  * Product decisions are described as clinical decisions, or any clinical
    requirement becomes a Product-approved clinical rule;
  * clinical approval becomes true;
  * IM003-SB-001 is recorded closed, or D004 approved;
  * Mobile PR #76 becomes merge-authorized;
  * the provisional invariant is omitted, weakened, generalized to all
    WellaPath behaviour, or called clinically approved;
  * a replacement urgency algorithm is selected;
  * investigation permission is read as activation permission;
  * user-facing evaluation is authorized, or the beta/production/evaluation
    classifications unblock;
  * any of the ten regression case classes is dropped, or displayed-urgency
    assertion is no longer required;
  * evidence bindings drift (vendored record hash, KB baseline commit,
    Mobile PR #76 head) or the record contradicts the live blocker registry
    and decision package.
"""

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import load_json, repo_path, sha256_file

REPORT = repo_path("reports", "im003_disposition_v1.json")
BLOCKERS = repo_path("reports", "im003_safety_blockers_v1.json")
PACKAGE = repo_path("reports", "im003_decision_package_v1.json")
VENDORED = repo_path("baseline", "im003_decision_record_v1",
                     "IM003_SAFETY_REVIEW_DECISION_RECORD_2026-08-22.vendored.md")

KB_BASELINE_COMMIT = "83cd52583a14ec9fb656fae6be18ec0df3877a70"
MOBILE_PR_76_HEAD = "13be0d4937b1c49d6a49ddf096c5d5b6a47c2091"

# The invariant must keep every one of these elements to retain its meaning:
# additive evidence, no lowering, established urgency, ranking as sole cause.
INVARIANT_ELEMENTS = ["adding evidence", "must not lower", "established urgency",
                      "solely", "re-ranking"]

REQUIRED_CASE_CLASS_MARKERS = [
    "rank 2/3 while its score is unchanged",
    "lower rank while its score increases",
    "entering the ranking after additive evidence",
    "multiple simultaneous emergency-default conditions",
    "non-urgent ranking competition",
    "red-flag and non-red-flag versions",
    "boundary is ultimately approved",
    "repeated re-branching",
    "population-specific cases",
    "clinically approved de-escalation behaviour",
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


def run(report=None, blockers=None, package=None):
    results = Results()
    report = report if report is not None else load_json(REPORT)
    blockers = blockers if blockers is not None else load_json(BLOCKERS)
    package = package if package is not None else load_json(PACKAGE)

    meta = report["_metadata"]

    # --- A. reviewer identity (Step 9A) ----------------------------------------
    identity = report.get("reviewer_identity")
    results.add("A.identity", "reviewer_identity_block_present", identity is not None)
    if identity:
        product = identity.get("product_reviewer") or {}
        results.add("A.identity", "product_reviewer_name_present",
                    bool(str(product.get("name") or "").strip()),
                    repr(product.get("name")))
        results.add("A.identity", "product_reviewer_name_is_the_authoritative_one",
                    product.get("name") == "Ayodele John Oluwaseyi",
                    repr(product.get("name")))
        results.add("A.identity", "product_reviewer_title_present",
                    bool(str(product.get("title") or "").strip()),
                    repr(product.get("title")))
        results.add("A.identity", "product_review_date_present",
                    product.get("review_date") == "2026-08-22",
                    repr(product.get("review_date")))
        results.add("A.identity", "effective_authority_is_product_exactly",
                    identity.get("effective_authority") == "product",
                    repr(identity.get("effective_authority")))
        source_role = identity.get("source_role_wording") or {}
        results.add("A.identity", "source_role_wording_recorded_faithfully",
                    source_role.get("as_supplied_in_record")
                    == "Clinical Reviewer + Product Lead")
        results.add("A.identity", "combined_wording_does_not_imply_a_clinical_reviewer",
                    source_role.get("implies_clinical_reviewer_participation") is False
                    and bool(source_role.get("superseded_by")),
                    str(source_role.get("implies_clinical_reviewer_participation")))
        results.add("A.identity", "clinical_reviewer_is_null",
                    identity.get("clinical_reviewer") is None,
                    repr(identity.get("clinical_reviewer")))
        results.add("A.identity", "clinical_status_not_assigned_while_reviewer_null",
                    identity.get("clinical_reviewer") is not None
                    or identity.get("clinical_reviewer_status") == "not_assigned",
                    repr(identity.get("clinical_reviewer_status")))
        results.add("A.identity", "no_named_qualified_clinical_reviewer_claimed",
                    identity.get("named_qualified_clinical_reviewer") is False
                    or identity.get("clinical_reviewer") is not None)
        results.add("A.identity",
                    "product_reviewer_not_described_as_qualified_clinical_reviewer",
                    identity.get("product_reviewer_is_qualified_clinical_reviewer")
                    is False,
                    str(identity.get("product_reviewer_is_qualified_clinical_reviewer")))
        results.add("A.identity", "identity_deferral_note_no_longer_active",
                    "name_deferred_note" not in identity
                    and "name_supplied" not in identity)
        attribution = report.get("product_decisions_attribution") or {}
        results.add("A.identity", "product_decisions_attributed_to_the_named_reviewer",
                    attribution.get("attributed_to") == "Ayodele John Oluwaseyi"
                    and sorted(attribution.get("covers", []))
                    == ["IM003-PD-%03d" % i for i in range(1, 7)],
                    str(attribution.get("attributed_to")))

    # --- B. classification ----------------------------------------------------
    c = report["classification"]
    for key, expected in [("im003_sb_001", "OPEN"), ("d004", "PENDING"),
                          ("im003", "DISABLED"),
                          ("mobile_pr_76_merge_authorization", False),
                          ("product_disposition", "RECORDED"),
                          ("clinical_rule", "REQUIRED_NOT_APPROVED"),
                          ("clinical_approval", False),
                          ("user_facing_internal_evaluation", "BLOCKED"),
                          ("external_beta", "BLOCKED"),
                          ("production", "BLOCKED")]:
        results.add("B.classification", "required:%s" % key, c.get(key) == expected,
                    "found=%r expected=%r" % (c.get(key), expected))

    # --- C. product vs clinical separation ------------------------------------
    decisions = report["product_decisions"]
    results.add("C.separation", "six_product_decisions_recorded", len(decisions) == 6,
                str(len(decisions)))
    results.add("C.separation", "product_decisions_not_described_as_clinical",
                report["product_decisions_are_clinical_decisions"] is False)
    blob = json.dumps(decisions).lower()
    results.add("C.separation", "no_product_decision_claims_clinical_authority",
                "clinical approval" not in blob and "clinically approved" not in blob
                and "clinical decision" not in blob)
    requirements = report["clinical_requirements"]
    results.add("C.separation", "seven_clinical_requirements_open",
                len(requirements) == 7, str(len(requirements)))
    results.add("C.separation", "clinical_requirements_are_requirements_not_decisions",
                report["clinical_requirements_status"]
                == "OPEN_REQUIREMENTS_NOT_DECISIONS")
    results.add("C.separation", "no_clinical_requirement_is_product_approved",
                all(r.get("status") == "open_requirement"
                    and r.get("product_approved") is False for r in requirements),
                str([r["id"] for r in requirements
                     if r.get("status") != "open_requirement"
                     or r.get("product_approved") is not False]))
    req_blob = json.dumps(requirements).lower()
    for marker, name in [("sufficient clinical support", "urgency_contribution_rule"),
                         ("de-escalate", "de_escalation_conditions"),
                         ("calibrated", "one_multiple_or_threshold"),
                         ("plausible", "s10_plausibility"),
                         ("lassa_fever-to-malaria", "ranking_transition_validity"),
                         ("rank 3", "rank3_emergency_question"),
                         ("population-specific", "regression_case_definition")]:
        results.add("C.separation", "requirement_present:%s" % name, marker in req_blob)

    # --- D. the provisional invariant ------------------------------------------
    inv = report.get("provisional_safety_invariant")
    results.add("D.invariant", "invariant_present", inv is not None)
    if inv:
        statement = inv["statement"].lower()
        missing = [e for e in INVARIANT_ELEMENTS if e not in statement]
        results.add("D.invariant", "invariant_not_weakened", not missing,
                    "missing elements: %s" % missing)
        results.add("D.invariant", "invariant_scoped_to_im003",
                    "im-003" in inv["scope"].lower())
        results.add("D.invariant", "invariant_not_generalized",
                    inv["generalized_to_all_wellapath_behavior"] is False
                    and "clinical" in inv["generalization_requires"].lower())
        results.add("D.invariant", "invariant_not_called_clinically_approved",
                    inv["clinically_approved"] is False
                    and inv["status"] == "provisional_pending_explicit_clinical_rule",
                    inv["status"])

    # --- E. no algorithm selected ----------------------------------------------
    algo = report["urgency_algorithm"]
    results.add("E.algorithm", "no_replacement_urgency_algorithm_selected",
                algo["selected"] is False
                and algo["first_ranked_only_approved_for_im003"] is False
                and algo["highest_among_ranked_approved"] is False
                and algo["score_confidence_threshold_approved"] is False)

    # --- F. authorization boundaries -------------------------------------------
    bounds = report["authorization_boundaries"]
    results.add("F.boundaries", "investigation_is_not_activation",
                bounds["investigation_permission_is_activation_permission"] is False)
    not_auth = json.dumps(bounds["not_authorized"]).lower()
    for needle, name in [("mobile pr #76", "pr76_merge"),
                         ("activation of im-003", "im003_activation"),
                         ("user-facing internal evaluation", "user_facing_evaluation"),
                         ("external beta", "external_beta"),
                         ("production", "production"),
                         ("urgency aggregation rule", "algorithm_implementation"),
                         ("publication", "publication")]:
        results.add("F.boundaries", "not_authorized:%s" % name, needle in not_auth)
    subset = next(d for d in decisions if d["id"] == "IM003-PD-006")
    results.add("F.boundaries", "constrained_subset_not_pre_approved",
                subset["pre_approved"] is False
                and subset["activation_authorized"] is False)

    # --- G. regression case classes --------------------------------------------
    classes = report["required_regression_case_classes"]
    results.add("G.regression", "ten_case_classes_present", len(classes) == 10,
                str(len(classes)))
    class_blob = json.dumps(classes).lower()
    for marker in REQUIRED_CASE_CLASS_MARKERS:
        results.add("G.regression", "case_class:%s" % marker.split()[0] + "_" +
                    marker.split()[-1], marker in class_blob, marker)
    rr = report["regression_requirements"]
    results.add("G.regression", "displayed_urgency_asserted_directly",
                rr["must_assert_displayed_urgency_directly"] is True
                and rr["ranking_stability_alone_is_insufficient"] is True)

    # --- H. evidence bindings ---------------------------------------------------
    source = meta["source_record"]
    if os.path.exists(VENDORED):
        results.add("H.binding", "vendored_record_hash_matches",
                    source["sha256"] == sha256_file(VENDORED), source["sha256"][:16])
    results.add("H.binding", "kb_baseline_commit_pinned",
                meta["kb_baseline_commit"] == KB_BASELINE_COMMIT)
    results.add("H.binding", "mobile_pr76_head_pinned",
                meta["mobile_pr_76"]["head"] == MOBILE_PR_76_HEAD
                and meta["mobile_pr_76"]["merge_authorized"] is False
                and meta["mobile_pr_76"]["state_required"] == "OPEN_UNMERGED")
    results.add("H.binding", "record_denies_being_clinical_approval",
                any("not clinical approval" in x for x in meta["what_this_is_not"]))

    # --- I. consistency with the live governance records ------------------------
    blocker = next((b for b in blockers["blockers"]
                    if b["blocker_id"] == "IM003-SB-001"), None)
    results.add("I.live", "blocker_still_open",
                blocker is not None and str(blocker["status"]).startswith("open"),
                str(blocker and blocker["status"]))
    if blocker:
        results.add("I.live", "blocker_gates_still_false",
                    blocker["clinical_approval"] is False
                    and blocker["im003_activation_authorized"] is False
                    and blocker["mobile_pr_76_merge_authorized_by_this_record"] is False)

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

    package_decisions = find_decisions(package) or []
    d004 = next((d for d in package_decisions if "D004" in d.get("decision_id", "")), None)
    results.add("I.live", "d004_still_pending",
                d004 is not None and d004["status"] == "pending",
                str(d004 and d004["status"]))
    results.add("I.live", "no_im003_decision_approved",
                all(d["status"] == "pending" for d in package_decisions))

    return results


# --- mutation proofs -----------------------------------------------------------

def _m_identity_removed(r, b, p):
    r.pop("reviewer_identity")
    return r, b, p, "A.identity:reviewer_identity_block_present"


def _m_name_removed(r, b, p):
    r["reviewer_identity"]["product_reviewer"]["name"] = None
    return r, b, p, "A.identity:product_reviewer_name_present"


def _m_name_blank(r, b, p):
    r["reviewer_identity"]["product_reviewer"]["name"] = "   "
    return r, b, p, "A.identity:product_reviewer_name_present"


def _m_title_removed(r, b, p):
    r["reviewer_identity"]["product_reviewer"]["title"] = ""
    return r, b, p, "A.identity:product_reviewer_title_present"


def _m_review_date_absent(r, b, p):
    del r["reviewer_identity"]["product_reviewer"]["review_date"]
    return r, b, p, "A.identity:product_review_date_present"


def _m_combined_authority_restored(r, b, p):
    r["reviewer_identity"]["effective_authority"] = "clinical_and_product"
    return r, b, p, "A.identity:effective_authority_is_product_exactly"


def _m_clinical_inferred_from_wording(r, b, p):
    r["reviewer_identity"]["source_role_wording"][
        "implies_clinical_reviewer_participation"] = True
    return r, b, p, "A.identity:combined_wording_does_not_imply_a_clinical_reviewer"


def _m_clinical_reviewer_fabricated(r, b, p):
    r["reviewer_identity"]["clinical_reviewer"] = "Dr. Invented Person"
    return r, b, p, "A.identity:clinical_reviewer_is_null"


def _m_clinical_status_assigned_without_identity(r, b, p):
    r["reviewer_identity"]["clinical_reviewer_status"] = "assigned"
    return r, b, p, "A.identity:clinical_status_not_assigned_while_reviewer_null"


def _m_product_reviewer_called_clinically_qualified(r, b, p):
    r["reviewer_identity"]["product_reviewer_is_qualified_clinical_reviewer"] = True
    return r, b, p, ("A.identity:"
                     "product_reviewer_not_described_as_qualified_clinical_reviewer")


def _m_deferral_note_reinstated(r, b, p):
    r["reviewer_identity"]["name_deferred_note"] = "we can add it later"
    return r, b, p, "A.identity:identity_deferral_note_no_longer_active"


def _m_requirement_product_approved(r, b, p):
    r["clinical_requirements"][0]["product_approved"] = True
    r["clinical_requirements"][0]["status"] = "approved_by_product"
    return r, b, p, "C.separation:no_clinical_requirement_is_product_approved"


def _m_product_called_clinical(r, b, p):
    r["product_decisions_are_clinical_decisions"] = True
    return r, b, p, "C.separation:product_decisions_not_described_as_clinical"


def _m_clinical_approval_true(r, b, p):
    r["classification"]["clinical_approval"] = True
    return r, b, p, "B.classification:required:clinical_approval"


def _m_blocker_closed(r, b, p):
    r["classification"]["im003_sb_001"] = "RESOLVED"
    return r, b, p, "B.classification:required:im003_sb_001"


def _m_live_blocker_closed(r, b, p):
    b["blockers"][0]["status"] = "resolved"
    return r, b, p, "I.live:blocker_still_open"


def _m_d004_approved(r, b, p):
    def flip(node):
        if isinstance(node, dict):
            if isinstance(node.get("decisions"), list):
                for d in node["decisions"]:
                    if "D004" in d["decision_id"]:
                        d["status"] = "approved"
                return True
            return any(flip(v) for v in node.values())
        if isinstance(node, list):
            return any(flip(i) for i in node)
        return False
    flip(p)
    return r, b, p, "I.live:d004_still_pending"


def _m_pr76_authorized(r, b, p):
    r["classification"]["mobile_pr_76_merge_authorization"] = True
    return r, b, p, "B.classification:required:mobile_pr_76_merge_authorization"


def _m_invariant_omitted(r, b, p):
    r.pop("provisional_safety_invariant")
    return r, b, p, "D.invariant:invariant_present"


def _m_invariant_weakened(r, b, p):
    r["provisional_safety_invariant"]["statement"] = (
        "For IM-003, adding evidence should generally keep urgency stable.")
    return r, b, p, "D.invariant:invariant_not_weakened"


def _m_invariant_generalized(r, b, p):
    r["provisional_safety_invariant"]["generalized_to_all_wellapath_behavior"] = True
    return r, b, p, "D.invariant:invariant_not_generalized"


def _m_algorithm_selected(r, b, p):
    r["urgency_algorithm"]["selected"] = True
    r["urgency_algorithm"]["highest_among_ranked_approved"] = True
    return r, b, p, "E.algorithm:no_replacement_urgency_algorithm_selected"


def _m_investigation_as_activation(r, b, p):
    r["authorization_boundaries"]["investigation_permission_is_activation_permission"] = True
    return r, b, p, "F.boundaries:investigation_is_not_activation"


def _m_subset_pre_approved(r, b, p):
    for d in r["product_decisions"]:
        if d["id"] == "IM003-PD-006":
            d["pre_approved"] = True
            d["activation_authorized"] = True
    return r, b, p, "F.boundaries:constrained_subset_not_pre_approved"


def _m_user_evaluation_authorized(r, b, p):
    r["classification"]["user_facing_internal_evaluation"] = "PERMITTED"
    return r, b, p, "B.classification:required:user_facing_internal_evaluation"


def _m_binding_drift(r, b, p):
    r["_metadata"]["source_record"]["sha256"] = "0" * 64
    return r, b, p, "H.binding:vendored_record_hash_matches"


def _m_case_class_dropped(r, b, p):
    r["required_regression_case_classes"] = r["required_regression_case_classes"][:-1]
    return r, b, p, "G.regression:ten_case_classes_present"


def _m_displayed_urgency_not_asserted(r, b, p):
    r["regression_requirements"]["must_assert_displayed_urgency_directly"] = False
    return r, b, p, "G.regression:displayed_urgency_asserted_directly"


MUTATIONS = [
    ("reviewer identity removed", _m_identity_removed),
    ("Product reviewer name removed", _m_name_removed),
    ("Product reviewer name blanked", _m_name_blank),
    ("Product reviewer title removed", _m_title_removed),
    ("Product review date absent", _m_review_date_absent),
    ("combined authority restored", _m_combined_authority_restored),
    ("clinical reviewer inferred from wording", _m_clinical_inferred_from_wording),
    ("clinical reviewer fabricated", _m_clinical_reviewer_fabricated),
    ("clinical status assigned without identity", _m_clinical_status_assigned_without_identity),
    ("Product reviewer called clinically qualified", _m_product_reviewer_called_clinically_qualified),
    ("identity-deferral note reinstated", _m_deferral_note_reinstated),
    ("a clinical requirement Product-approved", _m_requirement_product_approved),
    ("Product decisions described as clinical", _m_product_called_clinical),
    ("clinical approval flipped to true", _m_clinical_approval_true),
    ("IM003-SB-001 classified resolved", _m_blocker_closed),
    ("live blocker registry closed", _m_live_blocker_closed),
    ("D004 approved in the decision package", _m_d004_approved),
    ("Mobile PR #76 merge-authorized", _m_pr76_authorized),
    ("provisional invariant omitted", _m_invariant_omitted),
    ("provisional invariant weakened", _m_invariant_weakened),
    ("invariant generalized to all behaviour", _m_invariant_generalized),
    ("a replacement urgency algorithm selected", _m_algorithm_selected),
    ("investigation read as activation", _m_investigation_as_activation),
    ("constrained subset pre-approved", _m_subset_pre_approved),
    ("user-facing evaluation authorized", _m_user_evaluation_authorized),
    ("evidence binding drifted", _m_binding_drift),
    ("a regression case class dropped", _m_case_class_dropped),
    ("displayed-urgency assertion dropped", _m_displayed_urgency_not_asserted),
]


def run_mutations():
    base = (load_json(REPORT), load_json(BLOCKERS), load_json(PACKAGE))
    print("mutation proofs — each must trip its named check\n")
    failures = 0
    for label, mutate in MUTATIONS:
        r, b, p, expected = mutate(*copy.deepcopy(base))
        results = run(r, b, p)
        tripped = {"%s:%s" % (c["group"], c["check"]) for c in results.failures}
        ok = expected in tripped
        if not ok:
            failures += 1
        print("  %-4s %-46s -> %s" % ("OK" if ok else "MISS", label, expected))
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
            print("%-4s %-16s %s%s" % ("OK" if check["passed"] else "FAIL",
                                       check["group"], check["check"],
                                       ("  [%s]" % check["detail"])
                                       if not check["passed"] and check["detail"] else ""))
        summary = results.summary()
        print("\n%d checks, %d passed, %d failed"
              % (summary["total"], summary["passed"], summary["failed"]))
    return 0 if results.summary()["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
