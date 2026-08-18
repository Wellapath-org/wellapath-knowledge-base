#!/usr/bin/env python3
"""Reconcile the Mobile IM-003 measurement and register IM003-SB-001.

    python3 tools/report_im003_mobile_measurement.py            # write
    python3 tools/report_im003_mobile_measurement.py --check    # fail if stale

Mobile PR #76 measured IM-003 with the shipped engine. This tool recomputes
every aggregate from the vendored measurement records and re-derives the
IM003-SB-001 arithmetic directly from KB 2.4, so the knowledge base's numbers
are its own rather than Mobile's restated.

The rejected Python scoring approximation is not used anywhere here. Clinical
values come from Mobile's shipped-engine records; the KB independently checks
the SCORE ARITHMETIC those records imply against kb.ng.v2.4.json, which is a
different thing from re-running a scorer and is stated as such.

Outputs:
  reports/im003_mobile_measurement_v1.json  — reconciliation + blocker record
  reports/im003_safety_blockers_v1.json     — the versioned blocker registry

Fail-closed: if any count fails to reconcile, or the de-escalation is absent, or
the S10 arithmetic does not ground in KB 2.4, nothing is written and the tool
exits non-zero.
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_bytes, sha256_file, write_bytes

VENDORED = repo_path("baseline", "im003_mobile_v1",
                     "im003_mobile_scoring_measurement_v1.vendored.json")
REPORT = repo_path("reports", "im003_mobile_measurement_v1.json")
BLOCKERS = repo_path("reports", "im003_safety_blockers_v1.json")

MOBILE_SOURCE = {
    "repository": "Wellapath-org/wellapath-mobile",
    "pull_request": 76,
    "pull_request_state_at_incorporation": "OPEN_UNMERGED",
    "head": "13be0d4937b1c49d6a49ddf096c5d5b6a47c2091",
    "path": "docs/evidence/im003_mobile_scoring_measurement_v1.json",
    "sha256": "fb5aefab9915957f327b70de73e21f02ce0f574163d3b6c9dafa2e43c1f027c5",
    "bytes": 176163,
    "ci": {"check": "Flutter Lint & Build Check", "conclusion": "success",
           "checked_head_sha": "13be0d4937b1c49d6a49ddf096c5d5b6a47c2091"},
    "mobile_base_commit": "d820d6cfc3b96cbbba9d434ef4684b9a36140991",
    "knowledge_base_commit": "5a8563bf8702bd506a7b67ccc6c9a8faef8ef574",
    "generator": "test/im003/im003_measurement_test.dart",
    "authoritative_for_clinical_values": True,
    "authoritative_for_decisions": False,
}

EXPECTED = {
    "total": 63, "authoritative_supplied": 12, "graph_boundary_derived": 51,
    "red_flag_changes": 0, "urgency_changes": 25, "escalations": 24,
    "de_escalations": 1, "urgency_source_changes": 0,
    "top_condition_changed_overlapping": 31, "top_condition_change_primary": 6,
    "ranking_only": 29, "score_only": 0, "no_effect": 3,
    "trigger_nodes": 18, "trigger_edges": 56, "two_cycles": 15, "self_loops": 0,
    "newly_reachable_tokens": 15, "affected_conditions": 31,
    "max_closure": 14, "max_depth": 5, "monotonicity_violations": 0,
}


def reconcile(evidence):
    ms = evidence["measurements"]
    prov = collections.Counter(m["provenance"] for m in ms)
    primary = collections.Counter(m["primary_outcome"] for m in ms)
    top_changed = [m for m in ms if m["top_condition_changed"]]

    actual = {
        "total": len(ms),
        "authoritative_supplied": prov.get("authoritative_supplied", 0),
        "graph_boundary_derived": prov.get("graph_boundary_derived", 0),
        "red_flag_changes": sum(1 for m in ms if m["red_flag_changed"]),
        "urgency_changes": sum(1 for m in ms if m["urgency_changed"]),
        "escalations": sum(1 for m in ms if m["urgency_escalated"]),
        "de_escalations": sum(1 for m in ms if m["urgency_de_escalated"]),
        "urgency_source_changes": sum(1 for m in ms if m["urgency_source_changed"]),
        "top_condition_changed_overlapping": len(top_changed),
        "top_condition_change_primary": primary.get("top_condition_change", 0),
        "ranking_only": primary.get("ranking_change_without_top_condition_change", 0),
        "score_only": primary.get("score_only_change", 0),
        "no_effect": primary.get("no_effect", 0),
    }
    graph = evidence["reproduced_graph_counts"]
    actual.update({
        "trigger_nodes": graph["trigger_nodes"],
        "trigger_edges": graph["trigger_edges"],
        "two_cycles": graph["two_cycles"],
        "self_loops": graph["self_loops"],
        "newly_reachable_tokens": graph["newly_reachable_tokens"],
        "affected_conditions": graph["affected_conditions"],
        "monotonicity_violations": graph["monotonicity_violations"],
        "max_closure": max(len(m["added_tokens"]) for m in ms),
        "max_depth": max(m["closure_depth"] for m in ms),
    })
    return actual, primary, top_changed


def ground_s10(evidence):
    """Re-derive the S10 arithmetic from kb.ng.v2.4.json."""
    kb = {c["condition_id"]: c for c in load_json(repo_path("kb.ng.v2.4.json"))["conditions"]}
    rules = load_json(repo_path("rules.ng.v2.2.json"))["rules"]
    rule_tokens = {r["token"] for r in rules}
    global_tokens = {r["token"] for r in rules if r["applies_to"] == ["all"]}

    record = next(m for m in evidence["measurements"]
                  if m["scenario_id"] == "S10_path_limit_pressure")

    def score(condition_id, tokens):
        condition = kb[condition_id]
        selected = set(tokens)
        matched = [(s["token"], s["weight"]) for s in condition["symptoms"]
                   if s["token"] in selected]
        return {
            "condition_id": condition_id,
            "base_weight": condition["base_weight"],
            "matched": [{"token": t, "weight": w} for t, w in matched],
            "total": condition["base_weight"] + sum(w for _, w in matched),
            "urgency_default": condition["urgency_default"],
        }

    def rank(tokens):
        scored = {cid: score(cid, tokens)["total"] for cid in kb}
        top = max(scored.values())
        winners = sorted(c for c, v in scored.items() if v == top)
        return top, winners

    def ranked(tokens, limit=8):
        """Full KB ranking, so the top-condition transition is shown, not asserted."""
        scored = sorted(((score(cid, tokens)["total"], cid) for cid in kb),
                        key=lambda pair: (-pair[0], pair[1]))
        return [{"rank": i + 1, "condition_id": cid, "score": total,
                 "urgency_default": kb[cid]["urgency_default"]}
                for i, (total, cid) in enumerate(scored[:limit])]

    result = {}
    for side in ("baseline", "expanded"):
        tokens = record[side]["tokens"]
        top_score, winners = rank(tokens)
        result[side] = {
            "tokens": sorted(tokens),
            "kb_ranked_order_top_8": ranked(tokens),
            "engine_ranked_condition_ids": record[side]["ranked_condition_ids"],
            "engine_score_by_condition": record[side]["score_by_condition"],
            "lassa_fever": score("lassa_fever", tokens),
            "malaria": score("malaria", tokens),
            "kb_top_score": top_score,
            "kb_top_condition_ids": winners,
            "kb_top_is_unique": len(winners) == 1,
            "kb_top_urgency_default": kb[winners[0]]["urgency_default"],
            "recorded_top_condition": record[side]["top_condition"],
            "recorded_urgency": record[side]["urgency"],
            "recorded_urgency_source": record[side]["urgency_source"],
            "recorded_red_flag_triggered": record[side]["red_flag_triggered"],
            "recorded_top_score_ties": record[side]["top_score_ties"],
            "rule_tokens_present": sorted(set(tokens) & rule_tokens),
            "global_rule_tokens_present": sorted(set(tokens) & global_tokens),
        }

    checks = []

    def check(name, passed, detail=""):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    b, e = result["baseline"], result["expanded"]
    check("baseline_lassa_fever_is_26", b["lassa_fever"]["total"] == 26, str(b["lassa_fever"]["total"]))
    check("baseline_malaria_is_25", b["malaria"]["total"] == 25, str(b["malaria"]["total"]))
    check("expanded_malaria_is_52", e["malaria"]["total"] == 52, str(e["malaria"]["total"]))
    check("expanded_lassa_fever_unchanged_at_26", e["lassa_fever"]["total"] == 26,
          str(e["lassa_fever"]["total"]))
    check("kb_ranks_lassa_fever_first_at_baseline",
          b["kb_top_condition_ids"] == ["lassa_fever"], str(b["kb_top_condition_ids"]))
    check("kb_ranks_malaria_first_when_expanded",
          e["kb_top_condition_ids"] == ["malaria"], str(e["kb_top_condition_ids"]))
    check("kb_ranking_matches_the_recorded_top_condition",
          b["kb_top_condition_ids"][0] == b["recorded_top_condition"]
          and e["kb_top_condition_ids"][0] == e["recorded_top_condition"])
    check("lassa_fever_urgency_default_is_emergency",
          b["lassa_fever"]["urgency_default"] == "emergency")
    check("malaria_urgency_default_is_urgent", e["malaria"]["urgency_default"] == "urgent")
    check("recorded_urgency_matches_the_top_conditions_default",
          b["recorded_urgency"] == b["kb_top_urgency_default"]
          and e["recorded_urgency"] == e["kb_top_urgency_default"])
    check("urgency_moved_emergency_to_urgent",
          b["recorded_urgency"] == "emergency" and e["recorded_urgency"] == "urgent")
    check("urgency_source_is_urgency_default_on_both_sides",
          b["recorded_urgency_source"] == e["recorded_urgency_source"] == "urgency_default")
    check("no_red_flag_fired_on_either_side",
          b["recorded_red_flag_triggered"] is False and e["recorded_red_flag_triggered"] is False)
    check("no_rule_token_is_present_so_no_rule_was_omitted",
          not b["rule_tokens_present"] and not e["rule_tokens_present"],
          "baseline=%r expanded=%r" % (b["rule_tokens_present"], e["rule_tokens_present"]))
    check("no_tie_explains_the_result", b["kb_top_is_unique"] and e["kb_top_is_unique"])
    check("recorded_ties_show_a_single_winner_each_side",
          len(b["recorded_top_score_ties"]) == 1 and len(e["recorded_top_score_ties"]) == 1)
    check("closure_converged", record["converged"] is True)
    check("baseline_ranked_order_puts_lassa_fever_first",
          result["baseline"]["kb_ranked_order_top_8"][0]["condition_id"] == "lassa_fever"
          and result["baseline"]["kb_ranked_order_top_8"][1]["condition_id"] == "malaria",
          str([r["condition_id"] for r in result["baseline"]["kb_ranked_order_top_8"][:3]]))
    check("expanded_ranked_order_puts_malaria_first",
          result["expanded"]["kb_ranked_order_top_8"][0]["condition_id"] == "malaria",
          str([r["condition_id"] for r in result["expanded"]["kb_ranked_order_top_8"][:3]]))
    check("kb_ranking_agrees_with_the_engine_ranking",
          [r["condition_id"] for r in result["baseline"]["kb_ranked_order_top_8"][:3]]
          == result["baseline"]["engine_ranked_condition_ids"]
          and [r["condition_id"] for r in result["expanded"]["kb_ranked_order_top_8"][:3]]
          == result["expanded"]["engine_ranked_condition_ids"])
    check("lassa_fever_remains_a_scored_candidate_when_expanded",
          any(r["condition_id"] == "lassa_fever"
              for r in result["expanded"]["kb_ranked_order_top_8"]),
          "it is out-ranked, not eliminated — relevant to review question 3")
    check("every_additive_token_is_recorded", len(record["added_tokens"]) == 10
          and record["added_token_count"] == 10, str(len(record["added_tokens"])))

    return record, result, checks


def build():
    evidence = load_json(VENDORED)
    actual, primary, top_changed = reconcile(evidence)
    record, s10, s10_checks = ground_s10(evidence)

    drift = {k: {"knowledge_base": actual[k], "expected": EXPECTED[k]}
             for k in EXPECTED if actual.get(k) != EXPECTED[k]}
    s10_failures = [c for c in s10_checks if not c["passed"]]

    de_escalations = [m for m in evidence["measurements"] if m["urgency_de_escalated"]]
    all_became_malaria = {m["expanded"]["top_condition"] for m in top_changed} == {"malaria"}

    report = {
        "_metadata": {
            "report_id": "im003_mobile_measurement_reconciliation",
            "version": "1",
            "phase": "I2 / W3 Step 8",
            "generator": "tools/report_im003_mobile_measurement.py",
            "generator_version": QFLOW_TOOLING_VERSION,
            "authoritative": True,
            "purpose": "Independent reconciliation of the Mobile shipped-engine IM-003 measurement, and registration of IM003-SB-001.",
            "what_this_is_not": [
                "not clinical adjudication",
                "not approval of IM-003, of any subset, or of Mobile PR #76",
                "not a judgement that the de-escalation is safe, correct, conservative or acceptable",
            ],
            "rejected_python_scoring_model_used": False,
            "rejected_python_scoring_model_note": (
                "The Python scoring approximation (234/239 top-condition, 217/239 urgency "
                "agreement) supplies nothing here. Clinical values come from Mobile's shipped "
                "engine. This report independently re-derives the SCORE ARITHMETIC those "
                "records imply from kb.ng.v2.4.json — checking the numbers add up, which is "
                "not the same as re-running a scorer, and is not claimed to be."
            ),
            "mobile_source": MOBILE_SOURCE,
            "vendored_copy": {
                "path": os.path.relpath(VENDORED, repo_path()),
                "sha256": sha256_file(VENDORED),
                "bytes": os.path.getsize(VENDORED),
                "matches_mobile_head": sha256_file(VENDORED) == MOBILE_SOURCE["sha256"],
            },
            "frozen_clinical_inputs": {
                "kb_v2_4": sha256_file(repo_path("kb.ng.v2.4.json")),
                "rules_v2_2": sha256_file(repo_path("rules.ng.v2.2.json")),
                "token_dictionary_v1_1": sha256_file(repo_path("token_dictionary.ng.v1.1.json")),
            },
        },

        "methodology_verification": {
            "clinical_values_from_shipped_engine": True,
            "engine_symbols_imported": [
                "package:wellapath_mobile/core/engine/engine_controller.dart",
                "package:wellapath_mobile/core/engine/red_flag_evaluator.dart",
                "package:wellapath_mobile/core/engine/scoring_engine.dart",
            ],
            "controller_cross_checked_against_full_scorer": True,
            "cross_check_mechanism": "The harness throws StateError if a controller topCause id or score disagrees with the shipped ScoringEngine ranking, and if the scorer produces conditions while a red flag is active.",
            "copied_scoring_model_supplied_conclusions": False,
            "production_lib_changed_in_pr_76": False,
            "pr_76_changed_paths": ["PROGRESS.md", "docs/", "test/"],
            "harness_is_test_only": True,
            "harness_absent_from_release_binaries": True,
            "isolation_evidence": [
                "test/im003/im003_isolation_test.dart asserts nothing under lib/ imports the harness",
                "asserts engine, UI, controller and startup contain no im003 reference",
                "asserts the harness declares no build flag",
                "asserts the harness never mutates a clinical artifact",
                "asserts pubspec declares no im003 asset and no new dependency",
            ],
            "all_63_scenarios_executed": actual["total"] == 63,
            "no_scenario_silently_filtered": actual["total"] == EXPECTED["total"],
            "all_de_escalations_promoted_to_blockers": (
                len(de_escalations) == len(evidence["potential_safety_blockers"])),
            "generation_deterministic_and_fail_closed": True,
            "accepted_solely_because_ci_passed": False,
        },

        "reconciliation": {
            "all_counts_agree": not drift,
            "drift": drift,
            "counts": {k: actual[k] for k in sorted(actual)},
        },

        "category_definitions": {
            "partition_is_by_highest_order_effect": True,
            "mutually_exclusive_partition": {
                "urgency_change": actual["urgency_changes"],
                "top_condition_change": actual["top_condition_change_primary"],
                "ranking_change_without_top_condition_change": actual["ranking_only"],
                "score_only_change": actual["score_only"],
                "no_effect": actual["no_effect"],
                "sum": (actual["urgency_changes"] + actual["top_condition_change_primary"]
                        + actual["ranking_only"] + actual["score_only"] + actual["no_effect"]),
                "sums_to_total": (actual["urgency_changes"] + actual["top_condition_change_primary"]
                                  + actual["ranking_only"] + actual["score_only"]
                                  + actual["no_effect"]) == actual["total"],
            },
            "overlapping_metrics": {
                "top_condition_changed_total": actual["top_condition_changed_overlapping"],
                "explanation": (
                    "31 is the OVERLAPPING count of scenarios whose top condition changed. "
                    "6 is the mutually exclusive PRIMARY-outcome count: top condition changed "
                    "and urgency did NOT. The other 25 also changed top condition but are "
                    "classified under the higher-order urgency_change bucket. 25 + 6 = 31. "
                    "Reporting 31 alongside the partition without this note would double-count."
                ),
                "top_condition_changed_and_urgency_changed": sum(
                    1 for m in evidence["measurements"]
                    if m["top_condition_changed"] and m["urgency_changed"]),
                "top_condition_changed_urgency_unchanged": actual["top_condition_change_primary"],
            },
            "every_changed_top_condition_became_malaria": all_became_malaria,
            "changed_top_condition_targets": sorted(
                {m["expanded"]["top_condition"] for m in top_changed}),
        },

        "im003_sb_001_grounding": {
            "scenario_id": record["scenario_id"],
            "provenance": record["provenance"],
            "seed_tokens": record["seed_tokens"],
            "added_tokens": record["added_tokens"],
            "added_token_count": record["added_token_count"],
            "closure_depth": record["closure_depth"],
            "converged": record["converged"],
            "scenario_description": record["description"],
            "path_limit_validity": {
                "path_limit": 5,
                "scenario_intent": record["description"],
                "valid_under_the_authoritative_measurement_input": True,
                "why": (
                    "The scenario is one of the 12 authoritative_supplied inputs, and the "
                    "measurement is of SCORING, which the path limit does not bound: the limit "
                    "caps how many follow-up questions are PRESENTED, not how many tokens an "
                    "answered assessment carries. The %d additive tokens are the converged "
                    "closure of the seed set, so this is the scoring state the limit permits at "
                    "its most loaded, not a state beyond it."
                    % record["added_token_count"]
                ),
            },
            "before_after_matrix": {
                "baseline": {
                    "tokens": s10["baseline"]["tokens"],
                    "top_condition": s10["baseline"]["recorded_top_condition"],
                    "lassa_fever_score": s10["baseline"]["lassa_fever"]["total"],
                    "malaria_score": s10["baseline"]["malaria"]["total"],
                    "urgency": s10["baseline"]["recorded_urgency"],
                    "urgency_source": s10["baseline"]["recorded_urgency_source"],
                    "red_flag_triggered": s10["baseline"]["recorded_red_flag_triggered"],
                },
                "expanded": {
                    "tokens": s10["expanded"]["tokens"],
                    "top_condition": s10["expanded"]["recorded_top_condition"],
                    "lassa_fever_score": s10["expanded"]["lassa_fever"]["total"],
                    "malaria_score": s10["expanded"]["malaria"]["total"],
                    "urgency": s10["expanded"]["recorded_urgency"],
                    "urgency_source": s10["expanded"]["recorded_urgency_source"],
                    "red_flag_triggered": s10["expanded"]["recorded_red_flag_triggered"],
                },
            },
            "kb_arithmetic": s10,
            "grounding_checks": s10_checks,
            "all_grounded": not s10_failures,
        },

        "mechanism": {
            "causal_chain": [
                "additive answers unlock further additional-symptom questions",
                "those answers contribute additional scoring tokens",
                "condition scores change (malaria 25 -> 52; lassa_fever unchanged at 26)",
                "a different condition ranks first (lassa_fever -> malaria)",
                "urgency is taken from the top condition's urgency_default",
                "urgency de-escalates (emergency -> urgent) with no red-flag change",
            ],
            "red_flag_invariance_is_insufficient": (
                "Red-flag invariance does NOT prove urgency invariance. Across all 63 scenarios "
                "the red-flag result never changed, and urgency still changed in 25 of them, "
                "once downward. Urgency has a second source — the top condition's "
                "urgency_default — and re-ranking alone can move it."
            ),
            "nothing_repaired_here": [
                "condition weights unchanged",
                "urgency_default unchanged",
                "scoring unchanged",
                "ranking unchanged",
                "red-flag rules unchanged",
                "candidate questions unchanged",
                "path limit unchanged",
                "Mobile behaviour unchanged",
            ],
        },

        "does_not_authorize": [
            "IM-003 activation, in whole or in any subset",
            "merging Mobile PR #76",
            "approving D004 or any other IM-003 decision",
            "describing the measured de-escalation as safe, correct, conservative or acceptable",
            "internal, external-beta or production activation",
            "any change to scoring, ranking, urgency, red flags or the path limit",
        ],
    }
    return report, s10_failures, drift, de_escalations


def build_blockers(report):
    grounding = report["im003_sb_001_grounding"]
    return {
        "_metadata": {
            "report_id": "im003_safety_blockers",
            "version": "1",
            "phase": "I2 / W3 Step 8",
            "generator": "tools/report_im003_mobile_measurement.py",
            "generator_version": QFLOW_TOOLING_VERSION,
            "note": "Potential safety blockers arising from IM-003 measurement. A record here is engineering evidence awaiting clinical and product adjudication. It is not a clinical finding, and it does not say the behaviour is acceptable or unacceptable.",
        },
        "blockers": [
            {
                "blocker_id": "IM003-SB-001",
                "title": "Additive re-branching de-escalated urgency from emergency to urgent with no red-flag change",
                "status": "open_awaiting_clinical_and_product_adjudication",
                "classification_authority": "engineering evidence",
                "potential_safety_blocker": True,
                "clinical_approval": False,
                "product_approval": False,
                "external_beta_approval": False,
                "production_approval": False,
                "im003_activation_authorized": False,
                "mobile_pr_76_merge_authorized_by_this_record": False,
                "affected_decision": "D004",
                "expiry_or_review_milestone": "before any IM-003 internal activation",
                "scenario_id": grounding["scenario_id"],
                "before_after_matrix": grounding["before_after_matrix"],
                "mechanism_summary": (
                    "Additive tokens raised malaria from 25 to 52 while lassa_fever stayed at 26. "
                    "The leading condition flipped, and urgency follows the top condition's "
                    "urgency_default, so emergency became urgent. No red flag fired on either side."
                ),
                "independently_grounded_in_kb_2_4": grounding["all_grounded"],
                "evidence_binding": MOBILE_SOURCE,
                "not_asserted": [
                    "that this behaviour is clinically safe",
                    "that this behaviour is clinically unsafe",
                    "that emergency was the correct baseline urgency",
                    "that urgent is an acceptable expanded urgency",
                ],
                "resolution_requires": [
                    "named clinical reviewer, role, date and rationale",
                    "named product reviewer, role, date and rationale",
                    "a recorded decision on whether urgency must be monotone under additive evidence",
                ],
            }
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report, s10_failures, drift, de_escalations = build()

    if drift:
        print("FAIL counts do not reconcile:")
        print(json.dumps(drift, indent=2))
        return 1
    if s10_failures:
        print("FAIL IM003-SB-001 could not be grounded in KB 2.4:")
        print(json.dumps(s10_failures, indent=2))
        return 1
    if not de_escalations:
        print("FAIL the de-escalation is absent from the measurement records")
        return 1

    blockers = build_blockers(report)
    outputs = [(REPORT, report), (BLOCKERS, blockers)]

    for path, payload in outputs:
        data = dump_report_bytes(payload)
        relative = os.path.relpath(path, repo_path())
        if args.check:
            if not os.path.exists(path) or open(path, "rb").read() != data:
                print("FAIL %s is missing or stale" % relative)
                return 1
        else:
            write_bytes(path, data)
            print("wrote %s" % relative)

    if args.check:
        print("OK   IM-003 Mobile measurement reconciliation is current")
    else:
        counts = report["reconciliation"]["counts"]
        print("  scenarios reconciled: %d (%d authoritative + %d derived)"
              % (counts["total"], counts["authoritative_supplied"],
                 counts["graph_boundary_derived"]))
        print("  urgency changes: %d (%d escalations, %d de-escalation)"
              % (counts["urgency_changes"], counts["escalations"], counts["de_escalations"]))
        print("  red-flag changes: %d" % counts["red_flag_changes"])
        print("  IM003-SB-001 grounded in KB 2.4: %s"
              % report["im003_sb_001_grounding"]["all_grounded"])
        print("  blocker status: open_awaiting_clinical_and_product_adjudication")
    return 0


if __name__ == "__main__":
    sys.exit(main())
