#!/usr/bin/env python3
"""Fail-closed validation of the IM-001 Product decision workbook.

    python3 tools/validate_im001_workbook.py             # human-readable
    python3 tools/validate_im001_workbook.py --json      # machine-readable
    python3 tools/validate_im001_workbook.py --mutations # prove the checks bite

Fails if:
  * the source decision count is not 135, the global decision is absent, or
    the total is not 136;
  * any decision is omitted, duplicated, or invented by the workbook;
  * an alternative wording is lost or altered, or an affected-path count
    drifts from the source;
  * a decision is marked approved without reviewer name, title, date,
    selection and rationale;
  * a batch omits or duplicates members, sums to the wrong total, or contains
    conflicting alternatives (two selected wordings for one slot, or a
    member whose candidate wording is another member's alternative for the
    same slot);
  * any clinical-impact dimension is nonzero;
  * the workbook claims activation, publication, clinical-approval or Mobile
    implementation authority;
  * IM-001 is marked resolved while any decision remains pending;
  * source evidence hashes drift.
"""

import argparse
import collections
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import load_json, repo_path, sha256_file

WORKBOOK = repo_path("review", "im001_workbook_v1", "im001_workbook_v1.json")
TEMPLATE = repo_path("review", "im001_workbook_v1", "im001_decision_template_v1.json")
REVIEW = repo_path("reports", "im001_product_review_v1_1.json")
ORDER_DECISION = repo_path("reports", "im001_option_order_decision_v1.json")
ORDER_EVIDENCE = repo_path("reports", "im001_option_order_evidence_v1.json")

FORBIDDEN_CLAIMS = [
    "activation is authorized", "authorizes activation", "activation approved",
    "publication is authorized", "authorizes publication", "publish immediately",
    "clinical approval granted", "clinically approved",
    "mobile implementation is authorized", "authorizes mobile implementation",
    "authorized to merge", "authorised to merge",
]

REVIEWER_FIELDS = ("reviewer_selection", "reviewer_rationale", "reviewer_name",
                   "reviewer_title", "review_date")


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


def run(workbook=None, template=None, review=None, order_decision=None,
        order_evidence=None):
    results = Results()
    workbook = workbook if workbook is not None else load_json(WORKBOOK)
    template = template if template is not None else load_json(TEMPLATE)
    review = review if review is not None else load_json(REVIEW)
    order_decision = order_decision if order_decision is not None else load_json(ORDER_DECISION)
    order_evidence = order_evidence if order_evidence is not None else load_json(ORDER_EVIDENCE)

    source = {d["decision_id"]: d for d in review["decisions"]}
    items = {d["decision_id"]: d for d in workbook["decisions"]}

    # --- A. counts and one-to-one traceability ---------------------------------
    results.add("A.counts", "source_wording_count_is_135", len(review["decisions"]) == 135,
                str(len(review["decisions"])))
    results.add("A.counts", "workbook_carries_every_decision_exactly_once",
                len(workbook["decisions"]) == 135
                and len(items) == 135 and set(items) == set(source),
                "missing=%s extra=%s" % (sorted(set(source) - set(items))[:3],
                                         sorted(set(items) - set(source))[:3]))
    results.add("A.counts", "global_decision_present",
                workbook["global_ordering_decision"]["decision_id"]
                == "IM001-ORD-GLOBAL-001")
    results.add("A.counts", "total_is_136",
                workbook["counts"]["original_wording_decisions"] == 135
                and workbook["counts"]["global_ordering_decisions"] == 1
                and workbook["counts"]["total_product_decisions"] == 136)
    results.add("A.counts", "original_and_grouped_counts_reported_separately",
                workbook["counts"]["grouped_presentation_batches"] == len(workbook["batches"])
                and workbook["counts"]["grouped_presentation_units"]
                == len(workbook["batches"]) + 1)
    results.add("A.counts", "template_covers_all_136",
                len(template["wording_verdicts"]) == 135
                and {t["decision_id"] for t in template["wording_verdicts"]} == set(source)
                and template["ordering_verdict"]["decision_id"] == "IM001-ORD-GLOBAL-001")

    # --- B. fidelity to the source ---------------------------------------------
    lost_alternatives, path_drift, wording_drift = [], [], []
    for did, s in source.items():
        w = items.get(did)
        if not w:
            continue
        if w["alternative_wordings"] != s["rejected_wordings"]:
            lost_alternatives.append(did)
        if w["captured_paths_affected"] != s["captured_paths_affected"]:
            path_drift.append(did)
        if w["candidate_selected_wording"] != s["selected_wording"]:
            wording_drift.append(did)
    results.add("B.fidelity", "no_alternative_wording_lost", not lost_alternatives,
                str(lost_alternatives[:3]))
    results.add("B.fidelity", "no_affected_path_count_drift", not path_drift,
                str(path_drift[:3]))
    results.add("B.fidelity", "no_candidate_wording_drift", not wording_drift,
                str(wording_drift[:3]))
    results.add("B.fidelity", "representative_paths_from_source",
                all(items[d]["representative_paths"] == source[d]["example_selections"]
                    for d in source if d in items))

    # --- C. pending/approval integrity ------------------------------------------
    bad_approvals = []
    statuses = collections.Counter()
    for w in workbook["decisions"]:
        statuses[w["status"]] += 1
        if w["status"] != "PENDING":
            if not all(w.get(f) for f in REVIEWER_FIELDS):
                bad_approvals.append(w["decision_id"])
    g = workbook["global_ordering_decision"]
    if g["status"] != "PENDING":
        if not all(g.get(f) for f in ("reviewer_selection", "reviewer_rationale",
                                      "reviewer_name", "reviewer_title", "review_date")):
            bad_approvals.append(g["decision_id"])
    results.add("C.integrity", "no_approval_without_full_reviewer_evidence",
                not bad_approvals, str(bad_approvals[:3]))
    pending_total = statuses.get("PENDING", 0) + (1 if g["status"] == "PENDING" else 0)
    results.add("C.integrity", "progress_summary_matches_item_statuses",
                workbook["progress"]["pending"] == pending_total
                and workbook["progress"]["reviewed"]
                == 136 - pending_total - workbook["progress"]["deferred"],
                "progress=%s actual_pending=%d" % (workbook["progress"], pending_total))
    results.add("C.integrity", "im001_not_resolved_while_pending",
                not (pending_total > 0
                     and order_decision["im_001_gate"]["im_001_resolved"] is True))
    results.add("C.integrity", "ordering_choice_is_one_of_three_or_null",
                g["reviewer_selection"] in (None, "ORD-A", "ORD-B", "ORD-C")
                and len(g["choices_mutually_exclusive"]) == 3,
                str(g["reviewer_selection"]))

    # --- D. batch structure -------------------------------------------------------
    batches = workbook["batches"]
    all_members = [d for b in batches for d in b["member_decision_ids"]]
    results.add("D.batches", "batches_partition_all_135_exactly_once",
                len(all_members) == 135 and len(set(all_members)) == 135
                and set(all_members) == set(source),
                "members=%d unique=%d" % (len(all_members), len(set(all_members))))
    results.add("D.batches", "batch_expansion_is_explicit_and_deterministic",
                all(b["batch_approval_expands_to"] == b["member_decision_ids"]
                    and b["member_count"] == len(b["member_decision_ids"])
                    for b in batches))
    conflicted = []
    for b in batches:
        members = [items[d] for d in b["member_decision_ids"] if d in items]
        by_slot = collections.defaultdict(set)
        for m in members:
            by_slot[m["question_slot"]].add(m["candidate_selected_wording"])
        if any(len(v) > 1 for v in by_slot.values()):
            conflicted.append(b["batch_id"])
        # a member's candidate wording must never be a same-slot sibling's alternative
        for m in members:
            for sibling in members:
                if (sibling is not m
                        and m["question_slot"] == sibling["question_slot"]
                        and m["candidate_selected_wording"]
                        in sibling["alternative_wordings"]):
                    conflicted.append(b["batch_id"])
    results.add("D.batches", "no_batch_contains_conflicting_alternatives",
                not conflicted, str(sorted(set(conflicted))[:3]))
    results.add("D.batches", "individual_override_allowed_everywhere",
                all(b["individual_override_allowed"] is True for b in batches))
    results.add("D.batches", "path_volume_priority_not_called_clinical",
                "not clinical importance"
                in workbook["priority_by_path_volume"]["note"].lower())

    # --- E. clinical-impact dimensions -------------------------------------------
    impact = order_evidence["clinical_impact"]
    nonzero = {k: v for k, v in workbook["clinical_impact_dimensions_all_zero"].items()
               if v != 0}
    results.add("E.impact", "workbook_impact_dimensions_all_zero", not nonzero,
                str(nonzero))
    results.add("E.impact", "source_impact_dimensions_all_zero",
                impact["all_clinical_dimensions_zero"] is True
                and not impact["tokens_reachable_in_one_order_only"])
    results.add("E.impact", "conditional_classification_stated",
                "reopens clinical review" in json.dumps(
                    workbook["authorization_boundaries"]).lower())

    # --- F. authority claims --------------------------------------------------------
    blob = json.dumps(workbook, ensure_ascii=True).lower()
    # "unauthorized to merge" is a denial, not a claim; strip negated forms
    # before matching so the guard cannot be satisfied BY the denial text.
    scrubbed = blob.replace("unauthorized to merge", "").replace(
        "unauthorised to merge", "").replace("not authorized to merge", "").replace(
        "not authorised to merge", "")
    hits = [p for p in FORBIDDEN_CLAIMS if p in scrubbed]
    results.add("F.claims", "no_activation_publication_clinical_or_mobile_authority_claim",
                not hits, str(hits))
    bounds = workbook["authorization_boundaries"]
    results.add("F.claims", "boundaries_deny_the_five_authorities",
                bounds["clinical_approval_granted"] is False
                and len(bounds["approval_does_not"]) >= 5
                and "unauthorized to merge" in bounds["mobile_pr_76"])
    results.add("F.claims", "im003_stated_out_of_scope",
                "outside" in bounds["im003_status"].lower()
                and "OPEN" in bounds["im003_status"])
    results.add("F.claims", "workbook_records_no_verdicts",
                "no verdicts" in json.dumps(
                    workbook["recording_instructions"]["no_auto_approval"]).lower())

    # --- G. evidence bindings ---------------------------------------------------------
    src = workbook["_metadata"]["source_evidence"]
    for key, path in (("product_review", REVIEW), ("order_decision", ORDER_DECISION),
                      ("order_evidence", ORDER_EVIDENCE)):
        if os.path.exists(path):
            results.add("G.binding", "hash_current:%s" % key,
                        src[key]["sha256"] == sha256_file(path),
                        src[key]["sha256"][:16])
    results.add("G.binding", "order_decision_binding_intact",
                order_decision["evidence_binding"]["sha256"]
                == sha256_file(ORDER_EVIDENCE))

    return results


# --- mutation proofs -------------------------------------------------------------

def _base():
    return (load_json(WORKBOOK), load_json(TEMPLATE), load_json(REVIEW),
            load_json(ORDER_DECISION), load_json(ORDER_EVIDENCE))


def _m_source_count(w, t, r, od, oe):
    r["decisions"] = r["decisions"][:-1]
    return (w, t, r, od, oe), "A.counts:source_wording_count_is_135"


def _m_decision_omitted(w, t, r, od, oe):
    w["decisions"] = w["decisions"][1:]
    return (w, t, r, od, oe), "A.counts:workbook_carries_every_decision_exactly_once"


def _m_decision_duplicated(w, t, r, od, oe):
    w["decisions"].append(copy.deepcopy(w["decisions"][0]))
    return (w, t, r, od, oe), "A.counts:workbook_carries_every_decision_exactly_once"


def _m_global_absent(w, t, r, od, oe):
    w["global_ordering_decision"]["decision_id"] = "SOMETHING-ELSE"
    return (w, t, r, od, oe), "A.counts:global_decision_present"


def _m_total_not_136(w, t, r, od, oe):
    w["counts"]["total_product_decisions"] = 135
    return (w, t, r, od, oe), "A.counts:total_is_136"


def _m_alternative_lost(w, t, r, od, oe):
    w["decisions"][0]["alternative_wordings"] = []
    return (w, t, r, od, oe), "B.fidelity:no_alternative_wording_lost"


def _m_path_count_drift(w, t, r, od, oe):
    w["decisions"][0]["captured_paths_affected"] += 5
    return (w, t, r, od, oe), "B.fidelity:no_affected_path_count_drift"


def _m_approved_without_reviewer(w, t, r, od, oe):
    w["decisions"][0]["status"] = "APPROVED"
    w["decisions"][0]["reviewer_selection"] = "keep_candidate_wording"
    # rationale/name/title/date left null
    return (w, t, r, od, oe), "C.integrity:no_approval_without_full_reviewer_evidence"


def _m_conflicting_batch(w, t, r, od, oe):
    # Present the same slot with two different candidate wordings in one batch.
    donor = w["decisions"][1]
    victim_batch = next(b for b in w["batches"]
                        if w["decisions"][0]["decision_id"] in b["member_decision_ids"])
    donor_id = donor["decision_id"]
    if donor_id not in victim_batch["member_decision_ids"]:
        victim_batch["member_decision_ids"] = victim_batch["member_decision_ids"] + [donor_id]
        victim_batch["batch_approval_expands_to"] = victim_batch["member_decision_ids"]
        victim_batch["member_count"] = len(victim_batch["member_decision_ids"])
    donor["question_slot"] = w["decisions"][0]["question_slot"]
    donor["candidate_selected_wording"] = "A different wording entirely?"
    return (w, t, r, od, oe), "D.batches:no_batch_contains_conflicting_alternatives"


def _m_impact_nonzero(w, t, r, od, oe):
    w["clinical_impact_dimensions_all_zero"]["reachable_token_set_differences"] = 2
    return (w, t, r, od, oe), "E.impact:workbook_impact_dimensions_all_zero"


def _m_source_impact_nonzero(w, t, r, od, oe):
    oe["clinical_impact"]["all_clinical_dimensions_zero"] = False
    return (w, t, r, od, oe), "E.impact:source_impact_dimensions_all_zero"


def _m_authority_claimed(w, t, r, od, oe):
    w["_metadata"]["purpose"] += " Once complete, activation is authorized."
    return (w, t, r, od, oe), ("F.claims:"
                               "no_activation_publication_clinical_or_mobile_authority_claim")


def _m_resolved_while_pending(w, t, r, od, oe):
    od["im_001_gate"]["im_001_resolved"] = True
    return (w, t, r, od, oe), "C.integrity:im001_not_resolved_while_pending"


def _m_hash_drift(w, t, r, od, oe):
    w["_metadata"]["source_evidence"]["product_review"]["sha256"] = "f" * 64
    return (w, t, r, od, oe), "G.binding:hash_current:product_review"


MUTATIONS = [
    ("source decision count not 135", _m_source_count),
    ("a decision omitted from the workbook", _m_decision_omitted),
    ("a decision duplicated in the workbook", _m_decision_duplicated),
    ("the global decision absent", _m_global_absent),
    ("the total not 136", _m_total_not_136),
    ("an alternative wording lost", _m_alternative_lost),
    ("an affected-path count drifted", _m_path_count_drift),
    ("approved without reviewer evidence", _m_approved_without_reviewer),
    ("a batch given conflicting alternatives", _m_conflicting_batch),
    ("a clinical-impact dimension nonzero (workbook)", _m_impact_nonzero),
    ("a clinical-impact dimension nonzero (source)", _m_source_impact_nonzero),
    ("activation authority claimed", _m_authority_claimed),
    ("IM-001 resolved while decisions pend", _m_resolved_while_pending),
    ("source evidence hash drifted", _m_hash_drift),
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
        print("  %-4s %-48s -> %s" % ("OK" if ok else "MISS", label, expected))
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
            print("%-4s %-12s %s%s" % ("OK" if check["passed"] else "FAIL",
                                       check["group"], check["check"],
                                       ("  [%s]" % check["detail"])
                                       if not check["passed"] and check["detail"] else ""))
        summary = results.summary()
        print("\n%d checks, %d passed, %d failed"
              % (summary["total"], summary["passed"], summary["failed"]))
    return 0 if results.summary()["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
