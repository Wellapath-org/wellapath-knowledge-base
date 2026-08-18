#!/usr/bin/env python3
"""Fail-closed guards for the IM-003 evidence and decision package.

    python3 tools/validate_im003.py             # validate the real reports
    python3 tools/validate_im003.py --json      # machine-readable
    python3 tools/validate_im003.py --fixtures  # every invalid fixture must fail

The failure this exists to prevent is a scoring-affecting or red-flag-affecting
effect being signed off as inert. Every check below fails CLOSED: an
unclassified effect, a missing reviewer or a drifted count is an error, never a
default.

Standard library only. No network.
"""

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.dartparse import parse_all
from qflow.im003 import (
    ClinicalIndex,
    build_trigger_graph,
    closure,
    find_cycles,
    is_monotone,
    option_tokens,
    trigger_pairs,
)
from vocab.artifact_io import load_json, repo_path, sha256_file

IMPACT_PATH = repo_path("reports", "im003_impact_analysis_v1.json")
PACKAGE_PATH = repo_path("reports", "im003_decision_package_v1.json")
FIXTURE_DIR = repo_path("testing", "questions", "fixtures", "invalid_im003")

DECLARED_PAIR_COUNT = 56
PATH_LIMIT = 5

#: A decision touching any of these may never be Product-only.
CLINICAL_EVIDENCE_KEYS = (
    "scoring_affecting_count",
    "conditions_touched",
    "red_flag_affecting_count",
    "newly_reachable_tokens",
)


class Results:
    def __init__(self):
        self.checks = []

    def add(self, check_id, name, errors):
        self.checks.append({
            "id": check_id, "name": name,
            "passed": not errors, "errors": list(errors),
        })

    @property
    def failed(self):
        return [c for c in self.checks if not c["passed"]]


def check_pair_count(results, impact, _package, index, entries):
    """I1 — the 56 pairs are recomputed from source, not trusted."""
    errors = []
    recomputed = len(trigger_pairs(entries))
    declared = impact["pair_reconciliation"]["declared_in_candidate"]
    reported = impact["pair_reconciliation"]["recomputed"]
    if recomputed != reported:
        errors.append("report says %d pairs; source yields %d"
                      % (reported, recomputed))
    if recomputed != DECLARED_PAIR_COUNT:
        errors.append("pair count drifted from %d to %d without review — the "
                      "candidate's IM-003 record and every decision bound to it "
                      "must be re-reviewed" % (DECLARED_PAIR_COUNT, recomputed))
    if declared != DECLARED_PAIR_COUNT:
        errors.append("declared count is %d, expected %d" % (declared, DECLARED_PAIR_COUNT))
    if len(impact["pair_reconciliation"]["pairs"]) != recomputed:
        errors.append("the pair table does not contain every pair")
    results.add("I1", "the 56 pairs reconcile against source", errors)


def check_no_scoring_token_called_inert(results, impact, _package, index, _entries):
    """I2 — a token with KB weight is never classified inert."""
    errors = []
    for row in impact["inert_subset_analysis"]["severity_and_duration_answer_tokens"]:
        token = row["token"]
        claimed_inert = row["inert_against_kb_2_4_and_rules_2_2"]
        actually_scoring = index.affects_scoring(token)
        actually_red_flag = index.affects_red_flags(token)
        if claimed_inert and (actually_scoring or actually_red_flag):
            errors.append(
                "token %r is classified inert but has scoring=%s red_flag=%s"
                % (token, actually_scoring, actually_red_flag))
    for row in impact["red_flag_cross_reference"]["tokens"]:
        token = row["token"]
        if row["scoring_conditions"] and not index.affects_scoring(token):
            errors.append("token %r lists scoring conditions it does not have" % token)
        if not row["scoring_conditions"] and index.affects_scoring(token):
            errors.append("token %r has KB weight but no scoring conditions listed"
                          % token)
    results.add("I2", "no scoring-affecting token is classified inert", errors)


def check_red_flag_completeness(results, impact, _package, index, entries):
    """I3 — every red-flag pathway is checked, not just clarifier membership."""
    errors = []
    rf = impact["red_flag_cross_reference"]
    if not rf.get("not_relying_on_clarifier_membership_alone"):
        errors.append("the report does not assert that all pathways were checked")
    if len(rf["checked_pathways"]) < 4:
        errors.append("fewer than four red-flag pathways were checked: %s"
                      % rf["checked_pathways"])

    # Recompute the reachable set and its pathways from source.
    reachable = set()
    for _source, option in trigger_pairs(entries):
        reachable |= option_tokens(entries, option)
    if sorted(reachable) != rf["newly_reachable_tokens"]:
        errors.append("newly reachable token set drifted from source")

    missed = []
    for token in sorted(reachable):
        pathways = index.red_flag_pathways(token)
        row = next((r for r in rf["tokens"] if r["token"] == token), None)
        if row is None:
            errors.append("token %r is missing from the cross-reference" % token)
            continue
        if sorted(pathways) != sorted(row["red_flag_pathways"]):
            missed.append("%s: source=%s report=%s"
                          % (token, pathways, row["red_flag_pathways"]))
        if bool(pathways) != row["is_red_flag_affecting"]:
            missed.append("%s: is_red_flag_affecting disagrees with source" % token)
    if missed:
        errors.append("red-flag references missed or misreported: %s" % missed[:5])

    counted = sum(1 for r in rf["tokens"] if r["is_red_flag_affecting"])
    if counted != rf["red_flag_affecting_count"]:
        errors.append("red_flag_affecting_count %d does not match the table (%d)"
                      % (rf["red_flag_affecting_count"], counted))
    if rf["safety_critical_decision_required"] != (counted > 0):
        errors.append("safety_critical_decision_required disagrees with the count")
    results.add("I3", "every red-flag pathway is cross-referenced", errors)


def check_decisions_complete(results, _impact, package, _index, _entries):
    """I4 — every decision carries evidence, reviewers and a status."""
    errors = []
    decisions = package["decisions"]
    if not decisions:
        errors.append("no decisions recorded")
    seen = set()
    for decision in decisions:
        did = decision.get("decision_id")
        if not did:
            errors.append("a decision has no id")
            continue
        if did in seen:
            errors.append("duplicate decision id %r" % did)
        seen.add(did)
        if not decision.get("evidence"):
            errors.append("%s has no evidence" % did)
        if not decision.get("required_reviewers"):
            errors.append("%s names no reviewer" % did)
        if decision.get("status") != "pending":
            errors.append("%s is not pending (status=%r)" % (did, decision.get("status")))
        if not decision.get("approval_authorizes"):
            errors.append("%s does not say what approval authorizes" % did)
        if not decision.get("approval_does_not_authorize"):
            errors.append("%s does not say what approval does NOT authorize" % did)
        if not decision.get("regression_requirements"):
            errors.append("%s names no regression requirement" % did)
    results.add("I4", "every decision has evidence, reviewers and status", errors)


def check_no_clinical_decision_is_product_only(results, _impact, package, _index, _entries):
    """I5 — a clinical-impact decision may never be Product-only."""
    errors = []
    for decision in package["decisions"]:
        reviewers = decision.get("required_reviewers")
        evidence = decision.get("evidence") or {}
        clinical_signal = any(k in evidence for k in CLINICAL_EVIDENCE_KEYS)
        impact_text = (decision.get("clinical_impact") or "").lower()
        claims_no_impact = impact_text.startswith("none")
        if reviewers == "product" and clinical_signal and not claims_no_impact:
            errors.append(
                "%s carries clinical evidence %s but is Product-only"
                % (decision["decision_id"],
                   [k for k in CLINICAL_EVIDENCE_KEYS if k in evidence]))
    results.add("I5", "no clinical-impact decision is Product-only", errors)


def check_no_activation(results, impact, package, _index, _entries):
    """I6 — nothing here enables, publishes or activates IM-003."""
    errors = []
    if impact["_metadata"].get("im_003_implemented") is not False:
        errors.append("the impact report does not state IM-003 is unimplemented")
    if package["_metadata"].get("im_003_enabled") is not False:
        errors.append("the decision package does not state IM-003 is disabled")
    approved = [d["decision_id"] for d in package["decisions"]
                if d.get("status") != "pending"]
    if approved:
        errors.append("decisions are no longer pending: %s" % approved)
    if package["decision_counts"]["approved"] != 0:
        errors.append("the package reports approved decisions")
    for decision in package["decisions"]:
        if not decision.get("activation_blocker"):
            errors.append("%s is not marked an activation blocker"
                          % decision["decision_id"])
    if package["decomposition_recommendation"].get("this_is_not_approval") is not True:
        errors.append("the recommendation does not disclaim approval")
    results.add("I6", "IM-003 remains disabled and nothing is approved", errors)


def check_graph_termination(results, impact, _package, _index, entries):
    """I7 — cycles are disclosed and convergence is proven within the bound."""
    errors = []
    graph = build_trigger_graph(entries)
    cycles = find_cycles(graph)
    reported = impact["trigger_graph"]

    if len(cycles["two_cycles"]) != reported["two_cycle_count"]:
        errors.append("two-cycle count drifted: source %d, report %d"
                      % (len(cycles["two_cycles"]), reported["two_cycle_count"]))
    if len(cycles["self_loops"]) != reported["self_loop_count"]:
        errors.append("self-loop count drifted")

    monotone, violations = is_monotone(graph)
    if not monotone:
        errors.append("additive re-branching is NOT monotone: %s" % violations[:3])
    if reported["monotone_under_additive_rebranching"] != monotone:
        errors.append("the report's monotonicity claim disagrees with source")

    # Convergence must be proven within the declared bound, not assumed.
    bound = len(graph)
    for token in graph:
        _reach, depth = closure(graph, {token})
        observed = max(depth.values()) if depth else 0
        if observed > bound:
            errors.append("closure from %r did not converge within %d steps"
                          % (token, bound))
    if reported["max_convergence_depth"] > bound:
        errors.append("reported convergence depth exceeds the node count")
    if reported["branch_explosion"]["unbounded"]:
        errors.append("branch explosion is reported as unbounded")
    results.add("I7", "cycles disclosed, convergence proven within the bound", errors)


def check_path_limit(results, impact, package, _index, _entries):
    """I8 — the path limit and red-flag exemption are never violated."""
    errors = []
    if impact["_metadata"]["baseline"]["path_limit"] != PATH_LIMIT:
        errors.append("the baseline path limit is not %d" % PATH_LIMIT)
    path = package["path_length_analysis"]
    if path["path_limit"] != PATH_LIMIT:
        errors.append("the path analysis uses a different limit")
    if path["red_flag_questions_displaced"] != 0:
        errors.append("a red-flag question is displaced")
    if path["required_questions_displaced"] != 0:
        errors.append("a required question is displaced")
    if path["completion_becomes_impossible"]:
        errors.append("completion becomes impossible on some path")
    for scenario in package["scenarios"]:
        if scenario.get("red_flag_question_displaced"):
            errors.append("scenario %s displaces a red-flag question"
                          % scenario["scenario_id"])
        if scenario.get("im_003_enabled"):
            errors.append("scenario %s claims IM-003 is enabled"
                          % scenario["scenario_id"])
    results.add("I8", "path limit and red-flag exemption hold", errors)


def check_frozen_artifacts(results, impact, _package, _index, _entries):
    """I9 — candidates and frozen clinical inputs are unchanged."""
    errors = []
    baseline = impact["_metadata"]["baseline"]
    for key, path in (
        ("question_flow_1_0", ("candidate", "question_flow.ng.v1.0.json")),
        ("question_flow_1_1", ("candidate", "question_flow.ng.v1.1.json")),
    ):
        actual = sha256_file(repo_path(*path))
        if actual != baseline["candidates"][key]:
            errors.append("%s changed: recorded %s, on disk %s"
                          % ("/".join(path), baseline["candidates"][key], actual))
    for key, filename in (
        ("kb_v2_4", "kb.ng.v2.4.json"),
        ("rules_v2_2", "rules.ng.v2.2.json"),
        ("token_dictionary_v1_1", "token_dictionary.ng.v1.1.json"),
    ):
        actual = sha256_file(repo_path(filename))
        if actual != baseline["frozen_clinical_inputs"][key]:
            errors.append("%s changed" % filename)
    for entry in baseline["vendored_baseline"]:
        actual = sha256_file(repo_path(*entry["file"].split("/")))
        if actual != entry["sha256"]:
            errors.append("%s changed" % entry["file"])
    results.add("I9", "candidates and frozen artifacts unchanged", errors)


def check_evidence_binding(results, impact, package, _index, _entries):
    """I10 — the decisions are bound to the exact evidence hash."""
    errors = []
    binding = package["_metadata"]["evidence_binding"]
    actual = sha256_file(IMPACT_PATH)
    if binding["sha256"] != actual:
        errors.append("decisions are bound to evidence %s but the report is %s — "
                      "regenerating the evidence invalidates the decisions"
                      % (binding["sha256"], actual))
    if binding["impact_analysis"] != "reports/im003_impact_analysis_v1.json":
        errors.append("the decision package binds to an unexpected evidence path")
    _ = impact
    results.add("I10", "decisions are bound to the exact evidence hash", errors)


def check_case_bank_claim(results, _impact, package, _index, _entries):
    """I11 — no claim that the case bank validates adaptive branching."""
    errors = []
    applicability = package["case_bank_applicability"]
    if applicability["can_exercise_im_003"]:
        errors.append("the package claims the case bank can exercise IM-003")
    if applicability["carries_answer_sequence"]:
        errors.append("the package claims the case bank carries answer sequences")
    if not applicability.get("limitation"):
        errors.append("the limitation is not stated")

    # And verify it against the bank itself rather than trusting the field.
    bank = load_json(repo_path("testing", "case_bank_v1.json"))
    cases = bank["cases"] if isinstance(bank, dict) and "cases" in bank else bank
    fields = set()
    for case in cases:
        fields |= set(case)
    sequence_fields = [f for f in fields
                       if any(w in f.lower() for w in ("answer", "sequence", "step"))]
    if sequence_fields:
        errors.append("the case bank DOES carry sequence-like fields %s; the "
                      "limitation claim must be re-examined" % sequence_fields)
    if len(cases) != applicability["cases"]:
        errors.append("case count drifted: bank has %d, package says %d"
                      % (len(cases), applicability["cases"]))
    results.add("I11", "no false case-bank validation claim", errors)


def check_scoring_delta_honesty(results, impact, _package, _index, _entries):
    """I12 — score/urgency deltas are not published from an unvalidated model."""
    errors = []
    not_computed = impact["_metadata"]["what_is_not_computed_here"]
    for key in ("score_values", "ranked_conditions", "top_condition", "urgency"):
        if key not in not_computed:
            errors.append("the report does not disclose that %s is uncomputed" % key)
    attempt = not_computed.get("model_validation_attempt", {})
    if attempt.get("used") is not False:
        errors.append("an unvalidated scoring model was used")
    if "scoring_input_delta" not in impact:
        errors.append("the exact scoring-input delta is not published")
    results.add("I12", "no deltas published from an unvalidated scoring model",
                errors)


CHECKS = (
    check_pair_count,
    check_no_scoring_token_called_inert,
    check_red_flag_completeness,
    check_decisions_complete,
    check_no_clinical_decision_is_product_only,
    check_no_activation,
    check_graph_termination,
    check_path_limit,
    check_frozen_artifacts,
    check_evidence_binding,
    check_case_bank_claim,
    check_scoring_delta_honesty,
)


def run(impact_path=IMPACT_PATH, package_path=PACKAGE_PATH):
    results = Results()
    impact = load_json(impact_path)
    package = load_json(package_path)
    parsed = parse_all(repo_path())
    entries = parsed["followup_question_map"]["entries"]
    index = ClinicalIndex(
        load_json(repo_path("kb.ng.v2.4.json")),
        load_json(repo_path("rules.ng.v2.2.json")),
        parsed["red_flag_clarifiers"],
    )
    for check in CHECKS:
        try:
            check(results, impact, package, index, entries)
        except Exception as error:  # noqa: BLE001 — a crashing check is a failure
            results.add(check.__name__, check.__name__,
                        ["check raised %s: %s" % (type(error).__name__, error)])
    return results


# ── invalid fixtures ─────────────────────────────────────────────────────────

def m_pair_count_drift(impact, _package):
    impact["pair_reconciliation"]["recomputed"] = 55
    impact["pair_reconciliation"]["pairs"] = impact["pair_reconciliation"]["pairs"][:55]


def m_scoring_token_called_inert(impact, _package):
    impact["inert_subset_analysis"]["severity_and_duration_answer_tokens"].append({
        "answer_role": "severity", "token": "fever",
        "scoring_conditions": [], "global_red_flag_rules": [],
        "condition_specific_red_flags": [], "raises_clarifiers": [],
        "demographic_modifier_conditions": [],
        "inert_against_kb_2_4_and_rules_2_2": True,
    })


def m_red_flag_reference_missed(impact, _package):
    for row in impact["red_flag_cross_reference"]["tokens"]:
        row["red_flag_pathways"] = []
        row["is_red_flag_affecting"] = False
    impact["red_flag_cross_reference"]["tokens"][0]["token"] = "nonexistent_token"


def m_clarifier_membership_only(impact, _package):
    impact["red_flag_cross_reference"]["checked_pathways"] = [
        "red_flag_clarifier_triggers"
    ]
    impact["red_flag_cross_reference"]["not_relying_on_clarifier_membership_alone"] = False


def m_decision_without_reviewer(_impact, package):
    package["decisions"][0]["required_reviewers"] = ""


def m_decision_without_evidence(_impact, package):
    package["decisions"][0]["evidence"] = {}


def m_clinical_decision_product_only(_impact, package):
    for decision in package["decisions"]:
        if decision["decision_id"] == "IM003-D004-SCORING-REACHABILITY":
            decision["required_reviewers"] = "product"


def m_decision_approved(_impact, package):
    package["decisions"][0]["status"] = "approved"


def m_im003_enabled(_impact, package):
    package["_metadata"]["im_003_enabled"] = True


def m_scenario_enables_im003(_impact, package):
    package["scenarios"][0]["im_003_enabled"] = True


def m_red_flag_displaced(_impact, package):
    package["path_length_analysis"]["red_flag_questions_displaced"] = 1


def m_path_limit_raised(impact, _package):
    impact["_metadata"]["baseline"]["path_limit"] = 7


def m_cycle_count_hidden(impact, _package):
    impact["trigger_graph"]["two_cycle_count"] = 0
    impact["trigger_graph"]["cycles"]["two_cycles"] = []


def m_unbounded_branching(impact, _package):
    impact["trigger_graph"]["branch_explosion"]["unbounded"] = True


def m_frozen_artifact_hash_changed(impact, _package):
    impact["_metadata"]["baseline"]["candidates"]["question_flow_1_1"] = "0" * 64


def m_evidence_binding_broken(_impact, package):
    package["_metadata"]["evidence_binding"]["sha256"] = "0" * 64


def m_case_bank_validation_claimed(_impact, package):
    package["case_bank_applicability"]["can_exercise_im_003"] = True


def m_unvalidated_model_used(impact, _package):
    impact["_metadata"]["what_is_not_computed_here"][
        "model_validation_attempt"]["used"] = True


FIXTURES = [
    ("im003_pair_count_drift", "I1", m_pair_count_drift,
     "The 56-pair count drifts without review, invalidating every decision bound to it."),
    ("im003_scoring_token_called_inert", "I2", m_scoring_token_called_inert,
     "A token with KB scoring weight is classified clinically inert."),
    ("im003_red_flag_reference_missed", "I3", m_red_flag_reference_missed,
     "A red-flag reference is dropped from the cross-reference."),
    ("im003_clarifier_membership_only", "I3", m_clarifier_membership_only,
     "Only clarifier-trigger membership is checked — the weaker test the earlier note relied on."),
    ("im003_decision_without_reviewer", "I4", m_decision_without_reviewer,
     "A decision names no reviewer."),
    ("im003_decision_without_evidence", "I4", m_decision_without_evidence,
     "A decision carries no evidence."),
    ("im003_clinical_decision_product_only", "I5", m_clinical_decision_product_only,
     "The scoring-reachability decision is filed as Product-only."),
    ("im003_decision_approved", "I6", m_decision_approved,
     "A decision is marked approved in an analysis-only package."),
    ("im003_enabled", "I6", m_im003_enabled,
     "The package declares IM-003 enabled."),
    ("im003_scenario_enables_im003", "I8", m_scenario_enables_im003,
     "A scenario claims IM-003 is enabled."),
    ("im003_red_flag_displaced", "I8", m_red_flag_displaced,
     "A red-flag question is displaced by truncation."),
    ("im003_path_limit_raised", "I8", m_path_limit_raised,
     "The path limit is raised from 5."),
    ("im003_cycle_count_hidden", "I7", m_cycle_count_hidden,
     "Graph cycles are hidden from the report."),
    ("im003_unbounded_branching", "I7", m_unbounded_branching,
     "Branch explosion is declared unbounded."),
    ("im003_frozen_artifact_hash_changed", "I9", m_frozen_artifact_hash_changed,
     "A frozen candidate hash no longer matches the artifact on disk."),
    ("im003_evidence_binding_broken", "I10", m_evidence_binding_broken,
     "Decisions are bound to an evidence hash that does not exist."),
    ("im003_case_bank_validation_claimed", "I11", m_case_bank_validation_claimed,
     "The package claims the 239-case bank validates adaptive branching."),
    ("im003_unvalidated_model_used", "I12", m_unvalidated_model_used,
     "Score/urgency deltas are published from the unvalidated scoring model."),
]


def build_fixtures():
    impact = load_json(IMPACT_PATH)
    package = load_json(PACKAGE_PATH)
    written = []
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    index = {
        "_metadata": {
            "fixture_set_id": "im003_invalid",
            "version": "1",
            "generator": "tools/validate_im003.py",
            "description": (
                "One fixture per way the IM-003 evidence or decision package "
                "could mislead a reviewer. Each names the check that must "
                "reject it; rejection by a different check counts as a failure."
            ),
            "count": len(FIXTURES),
        },
        "fixtures": [],
    }
    for fixture_id, expected, mutate, why in FIXTURES:
        bad_impact = copy.deepcopy(impact)
        bad_package = copy.deepcopy(package)
        mutate(bad_impact, bad_package)
        payload = {
            "_metadata": {
                "fixture_id": fixture_id,
                "expected_check": expected,
                "must_be_rejected": True,
                "defect": why,
                "note": "INVALID BY CONSTRUCTION. Never cite as evidence.",
            },
            "impact": bad_impact,
            "package": bad_package,
        }
        path = os.path.join(FIXTURE_DIR, "%s.json" % fixture_id)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
        written.append(fixture_id)
        index["fixtures"].append({
            "fixture_id": fixture_id,
            "file": "%s.json" % fixture_id,
            "expected_check": expected,
            "defect": why,
        })
    with open(os.path.join(FIXTURE_DIR, "index.json"), "w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    return written


def run_fixtures():
    build_fixtures()
    index = load_json(os.path.join(FIXTURE_DIR, "index.json"))
    rows, ok = [], True
    for entry in index["fixtures"]:
        payload = load_json(os.path.join(FIXTURE_DIR, entry["file"]))
        results = Results()
        parsed = parse_all(repo_path())
        entries = parsed["followup_question_map"]["entries"]
        clinical = ClinicalIndex(
            load_json(repo_path("kb.ng.v2.4.json")),
            load_json(repo_path("rules.ng.v2.2.json")),
            parsed["red_flag_clarifiers"],
        )
        for check in CHECKS:
            try:
                check(results, payload["impact"], payload["package"], clinical, entries)
            except Exception as error:  # noqa: BLE001
                results.add(check.__name__, check.__name__, [str(error)])
        failed = [c["id"] for c in results.failed]
        hit = entry["expected_check"] in failed
        rows.append({
            "fixture": entry["fixture_id"],
            "expected_check": entry["expected_check"],
            "rejected": bool(failed),
            "tripped_expected_check": hit,
            "checks_failed": failed,
        })
        if not (failed and hit):
            ok = False
    return ok, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fixtures", action="store_true")
    args = parser.parse_args()

    if args.fixtures:
        ok, rows = run_fixtures()
        if args.json:
            print(json.dumps({"all_rejected": ok, "fixtures": rows}, indent=2))
        else:
            for row in rows:
                mark = "ok  " if row["rejected"] and row["tripped_expected_check"] else "FAIL"
                print("%s %-42s expected %-4s -> %s"
                      % (mark, row["fixture"], row["expected_check"],
                         ",".join(row["checks_failed"]) or "ACCEPTED"))
            hit = sum(1 for r in rows if r["rejected"] and r["tripped_expected_check"])
            print("\n%d/%d invalid fixtures rejected by the intended check"
                  % (hit, len(rows)))
        return 0 if ok else 1

    results = run()
    if args.json:
        print(json.dumps({"passed": not results.failed, "checks": results.checks},
                         indent=2))
    else:
        for check in results.checks:
            print("%s %-4s %s" % ("ok  " if check["passed"] else "FAIL",
                                  check["id"], check["name"]))
            for error in check["errors"]:
                print("       - %s" % error)
        print("\n%d/%d IM-003 checks passed"
              % (len(results.checks) - len(results.failed), len(results.checks)))
    return 1 if results.failed else 0


if __name__ == "__main__":
    sys.exit(main())
