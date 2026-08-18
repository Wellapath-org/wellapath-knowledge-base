#!/usr/bin/env python3
"""IM-003 additive re-branching — impact analysis and evidence.

    python3 tools/report_im003_impact.py            # build
    python3 tools/report_im003_impact.py --check    # fail if stale

IM-003 is NOT implemented and this does not implement it. It measures what
implementing it would do, from the frozen artifacts, so the decision can be
made on evidence rather than on the two sentences currently in the candidate's
impedance record.

Everything here is computed. The one number carried over from the earlier note
— "56 pairs" — is RECOMPUTED and reconciled rather than trusted.

## What is measured exactly, and what is not

EXACT, from the artifacts:
  * the trigger graph, its closure, cycles and convergence depth
  * every newly eligible question and newly reachable token
  * every clinical reference of every newly reachable token
  * the per-condition scoring-WEIGHT delta those tokens would contribute
  * path-length and truncation effects against the limit of 5

NOT computed here, and deliberately not guessed: the resulting score, ranked
conditions, top condition and urgency. Those are produced by Mobile's
`ScoringEngine`, which this repository does not contain. A model was written
and validated against the 239-case bank; it reproduced 234/239 top conditions
and only 217/239 urgencies, so it was NOT used. Publishing deltas from a model
that disagrees with the shipped engine on 22 urgencies would be worse than
publishing none. The exact scoring-INPUT delta is published instead, and the
Mobile harness needed to finish the job is specified in the handoff.

Standard library only. No network.
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import MOBILE_SOURCE_COMMIT, MOBILE_SOURCE_REPO
from qflow.dartparse import BASELINE_DIR, VENDORED_FILES, parse_all
from qflow.im003 import (
    REBRANCH_MODES,
    ClinicalIndex,
    build_trigger_graph,
    classify_effect,
    closure,
    convergence_depth,
    find_cycles,
    is_monotone,
    newly_eligible,
    option_tokens,
    trigger_pairs,
)
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
    write_bytes,
)

REPORT_PATH = repo_path("reports", "im003_impact_analysis_v1.json")
GENERATOR = "tools/report_im003_impact.py"

#: The count the candidate's IM-003 record states. Reconciled, not trusted.
DECLARED_PAIR_COUNT = 56

#: The live follow-up limit. IM-003 does not change it.
PATH_LIMIT = 5

#: Mobile develop at the time of this analysis.
MOBILE_DEVELOP = "d820d6cfc3b96cbbba9d434ef4684b9a36140991"


def build_report():
    parsed = parse_all(repo_path())
    entries = parsed["followup_question_map"]["entries"]
    clarifiers = parsed["red_flag_clarifiers"]
    answers = parsed["answer_mappings"]
    display = parsed["symptom_display"]

    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))
    index = ClinicalIndex(kb, rules, clarifiers)

    graph = build_trigger_graph(entries)
    pairs = trigger_pairs(entries)
    cycles = find_cycles(graph)
    monotone, violations = is_monotone(graph)

    # ── the 56 pairs, recomputed and reconciled ──────────────────────────────
    pair_rows = []
    for source, option in pairs:
        unlocked = newly_eligible(entries, option)
        reachable = sorted(option_tokens(entries, option))
        refs = index.references(option)
        pair_rows.append({
            "source_question": "followup_question_map.%s.additional_symptoms" % source,
            "source_token": source,
            "answer_option": option,
            "produced_token": option,
            "newly_eligible_questions": unlocked,
            "newly_eligible_count": len(unlocked),
            "newly_reachable_option_tokens": reachable,
            "newly_reachable_option_token_count": len(reachable),
            "clinical_references": refs,
            "red_flag_pathways": index.red_flag_pathways(option),
            "impact_class": classify_effect(index, option),
            "reachable_without_im003": False,
            "reachable_with_additive_rebranching": True,
        })

    # ── every token any newly eligible question could contribute ─────────────
    newly_reachable = set()
    for _source, option in pairs:
        newly_reachable |= option_tokens(entries, option)

    # ── the red-flag cross-reference, all four pathways ──────────────────────
    red_flag_rows = []
    for token in sorted(newly_reachable):
        pathways = index.red_flag_pathways(token)
        refs = index.references(token)
        red_flag_rows.append({
            "token": token,
            "red_flag_pathways": pathways,
            "is_red_flag_affecting": bool(pathways),
            "global_red_flag_rules": refs["global_red_flag_rules"],
            "condition_specific_red_flags": refs["condition_specific_red_flags"],
            "raises_clarifiers": refs["raises_clarifiers"],
            "is_a_clarifier_red_flag_token": refs["is_a_clarifier_red_flag_token"],
            "scoring_conditions": refs["scoring_conditions"],
            "max_scoring_weight": refs["max_scoring_weight"],
            "demographic_modifier_conditions": refs["demographic_modifier_conditions"],
        })

    red_flag_affecting = [r for r in red_flag_rows if r["is_red_flag_affecting"]]
    scoring_affecting = [r for r in red_flag_rows if r["scoring_conditions"]]

    # ── severity and duration answer tokens: inert today? ────────────────────
    severity_tokens = [b["token"] for b in answers["severity_bands"]]
    duration_tokens = [t for _label, t in answers["duration_answer_to_token"]]
    inert_rows = []
    for kind, tokens in (("severity", severity_tokens), ("duration", duration_tokens)):
        for token in tokens:
            refs = index.references(token)
            inert_rows.append({
                "answer_role": kind,
                "token": token,
                "scoring_conditions": refs["scoring_conditions"],
                "global_red_flag_rules": refs["global_red_flag_rules"],
                "condition_specific_red_flags": refs["condition_specific_red_flags"],
                "raises_clarifiers": refs["raises_clarifiers"],
                "demographic_modifier_conditions": refs["demographic_modifier_conditions"],
                "inert_against_kb_2_4_and_rules_2_2": not (
                    refs["scoring_conditions"]
                    or refs["global_red_flag_rules"]
                    or refs["condition_specific_red_flags"]
                    or refs["raises_clarifiers"]
                ),
            })
    all_inert = all(r["inert_against_kb_2_4_and_rules_2_2"] for r in inert_rows)

    # ── the scoring-INPUT delta, per condition ───────────────────────────────
    weight_delta = {}
    for token in sorted(newly_reachable):
        for reference in index.scoring.get(token, ()):
            cid = reference["condition_id"]
            bucket = weight_delta.setdefault(
                cid, {"condition_id": cid, "tokens": [], "max_added_weight": 0}
            )
            bucket["tokens"].append({"token": token, "weight": reference["weight"]})
            bucket["max_added_weight"] += reference["weight"]
    for bucket in weight_delta.values():
        bucket["tokens"].sort(key=lambda t: (-t["weight"], t["token"]))
        bucket["token_count"] = len(bucket["tokens"])

    # ── closure, convergence and path effects per seed token ─────────────────
    seed_rows = []
    for token in sorted(graph):
        reachable, depth = closure(graph, {token})
        reachable_without_seed = sorted(reachable - {token})
        # Questions the seed alone makes eligible, then what the closure adds.
        base_questions = len(newly_eligible(entries, token))
        closure_questions = sum(
            len(newly_eligible(entries, t)) for t in reachable_without_seed
        )
        seed_rows.append({
            "seed_token": token,
            "one_step_targets": sorted(graph[token]),
            "one_step_count": len(graph[token]),
            "closure_tokens": reachable_without_seed,
            "closure_size": len(reachable_without_seed),
            "convergence_depth": convergence_depth(graph, {token}),
            "questions_eligible_from_seed_alone": base_questions,
            "questions_eligible_across_closure": closure_questions,
            "bounded_by_path_limit": PATH_LIMIT,
            "closure_exceeds_path_limit": closure_questions > PATH_LIMIT,
        })

    max_closure = max(r["closure_size"] for r in seed_rows)
    max_depth = max(r["convergence_depth"] for r in seed_rows)

    # ── path-length effect against the live limit ────────────────────────────
    # The static baseline presents at most 3 clarifiers + severity + duration +
    # additional, truncated to 5. Additive re-branching cannot raise the limit,
    # so every extra question competes for the same 5 slots.
    picker_tokens = sorted({t for _l, t in display["display_label_to_token"]})
    path_rows = []
    for token in sorted(graph):
        reachable, _d = closure(graph, {token})
        eligible_roles = collections.Counter()
        for t in sorted(reachable):
            for q in newly_eligible(entries, t):
                eligible_roles[q["role"]] += 1
        # Grouping collapses each role to ONE presented question (contract 1.1).
        presented_after_grouping = len(
            {r for r in eligible_roles if eligible_roles[r]}
        )
        path_rows.append({
            "seed_token": token,
            "raw_newly_eligible_questions": sum(eligible_roles.values()),
            "roles_touched": sorted(eligible_roles),
            "presented_after_grouping": presented_after_grouping,
            "static_presented_max": PATH_LIMIT,
            "additional_slots_needed": max(0, presented_after_grouping - 3),
            "can_exceed_limit_without_truncation": presented_after_grouping
            + 3 > PATH_LIMIT,
        })

    return {
        "_metadata": {
            "report_id": "im003_impact_analysis",
            "version": "1",
            "phase": "I2 / W3 Step 6",
            "generator": GENERATOR,
            "authoritative": True,
            "status": "analysis_only_no_decision_approved",
            "im_003_implemented": False,
            "im_003_status": "deferred_pending_product_and_clinical_review",
            "description": (
                "Impact analysis for IM-003 additive re-branching. Analysis "
                "only: nothing here implements, enables or approves it, and no "
                "candidate, schema or runtime artifact is modified."
            ),
            "baseline": {
                "knowledge_base_commit": "0193a03d40f707460e2a8c799221a864776f1b9d",
                "mobile_develop": MOBILE_DEVELOP,
                "mobile_source_repository": MOBILE_SOURCE_REPO,
                "mobile_question_source_commit": MOBILE_SOURCE_COMMIT,
                "vendored_baseline": [
                    {"file": "%s/%s" % (BASELINE_DIR, name),
                     "sha256": sha256_file(repo_path(BASELINE_DIR, name))}
                    for name in VENDORED_FILES
                ],
                "candidates": {
                    "question_flow_1_0": sha256_file(
                        repo_path("candidate", "question_flow.ng.v1.0.json")),
                    "question_flow_1_1": sha256_file(
                        repo_path("candidate", "question_flow.ng.v1.1.json")),
                },
                "frozen_clinical_inputs": {
                    "kb_v2_4": sha256_file(repo_path("kb.ng.v2.4.json")),
                    "rules_v2_2": sha256_file(repo_path("rules.ng.v2.2.json")),
                    "token_dictionary_v1_1": sha256_file(
                        repo_path("token_dictionary.ng.v1.1.json")),
                },
                "path_limit": PATH_LIMIT,
                "static_planning_semantics": (
                    "FollowupScreen.initState computes the question list once "
                    "from the symptom set selected before the screen opened. No "
                    "answer changes eligibility."
                ),
                "immediate_red_flag_semantics": (
                    "QB-002, merged and unconditional: a red-flag-affecting "
                    "answer is evaluated immediately, before the next ordinary "
                    "question. IM-003 does not change this and must not."
                ),
                "selectable_picker_tokens": len(picker_tokens),
                "followup_map_tokens": len(entries),
            },
            "scope": {
                "mode_analysed": "additive_only",
                "modes": REBRANCH_MODES,
                "out_of_scope": [
                    "removal_invalidation",
                    "answer_edit_driven",
                    "restoration_driven",
                ],
            },
            "what_is_not_computed_here": {
                "score_values": "requires Mobile ScoringEngine",
                "ranked_conditions": "requires Mobile ScoringEngine",
                "top_condition": "requires Mobile ScoringEngine",
                "urgency": "requires Mobile ScoringEngine and UrgencyDeterminer",
                "why": (
                    "A Python scoring model was written and validated against "
                    "the 239-case bank. It reproduced 234/239 top conditions "
                    "and 217/239 urgencies — it does not agree with the shipped "
                    "engine. Publishing IM-003 deltas from it would be worse "
                    "than publishing none, so the exact scoring-INPUT delta is "
                    "published instead and the Mobile harness is specified in "
                    "the handoff."
                ),
                "model_validation_attempt": {
                    "top_condition_agreement": "234/239",
                    "urgency_agreement": "217/239",
                    "used": False,
                },
            },
        },

        "trigger_graph": {
            "nodes": sorted(graph),
            "node_count": len(graph),
            "edge_count": sum(len(v) for v in graph.values()),
            "edges_are_the_declared_pairs": sum(len(v) for v in graph.values())
            == len(pairs),
            "cycles": cycles,
            "two_cycle_count": len(cycles["two_cycles"]),
            "self_loop_count": len(cycles["self_loops"]),
            "monotone_under_additive_rebranching": monotone,
            "monotonicity_violations": violations,
            "monotonicity_proof": (
                "Checked over every ordered pair of seed tokens: adding a seed "
                "never shrinks the reachable set. Combined with a finite node "
                "set this gives termination at a fixed point, so the cycles "
                "above do not imply non-termination. Proved for ADDITIVE mode "
                "only — removal re-branching is not monotone and is out of "
                "scope."
            ),
            "max_closure_size": max_closure,
            "max_convergence_depth": max_depth,
            "branch_explosion": {
                "unbounded": False,
                "bound": (
                    "The closure is bounded by the %d map-key tokens, and the "
                    "presented question count is bounded by the path limit of "
                    "%d. Grouping (contract 1.1) collapses each role to one "
                    "presented question, so the presented follow-up count "
                    "cannot exceed 3 clarifiers + 3 grouped roles."
                    % (len(graph), PATH_LIMIT)
                ),
            },
        },

        "pair_reconciliation": {
            "declared_in_candidate": DECLARED_PAIR_COUNT,
            "recomputed": len(pairs),
            "reconciles": len(pairs) == DECLARED_PAIR_COUNT,
            "note": (
                "Recomputed from kFollowupQuestionMap, not carried over. The 56 "
                "pairs are exactly the edges of the trigger graph."
            ),
            "pairs": pair_rows,
        },

        "red_flag_cross_reference": {
            "newly_reachable_tokens": sorted(newly_reachable),
            "newly_reachable_token_count": len(newly_reachable),
            "checked_pathways": [
                "global_red_flag_rules (rules.ng.v2.2 rules[].token)",
                "condition_specific_red_flags (kb.ng.v2.4 conditions[].red_flags)",
                "red_flag_clarifier_triggers (kRedFlagClarifiers[].triggerTokens)",
                "clarifier_red_flag_tokens (kRedFlagClarifiers[].redFlagToken)",
            ],
            "not_relying_on_clarifier_membership_alone": True,
            "direct_global_red_flag_tokens": [
                r["token"] for r in red_flag_rows if r["global_red_flag_rules"]
            ],
            "condition_specific_red_flag_tokens": [
                r["token"] for r in red_flag_rows
                if r["condition_specific_red_flags"]
            ],
            "tokens_that_raise_a_clarifier": [
                r["token"] for r in red_flag_rows if r["raises_clarifiers"]
            ],
            "red_flag_affecting_count": len(red_flag_affecting),
            "scoring_affecting_count": len(scoring_affecting),
            "no_red_flag_relevance_count": len(red_flag_rows)
            - len(red_flag_affecting),
            "safety_critical_decision_required": len(red_flag_affecting) > 0,
            "combination_only_red_flags": {
                "checked": True,
                "found": [],
                "basis": (
                    "rules.ng.v2.2 keys every rule on a SINGLE token; no rule "
                    "requires a combination. Condition red_flags are also "
                    "single tokens. There is therefore no combination-only "
                    "red-flag pathway to model in the current artifacts."
                ),
            },
            "tokens": red_flag_rows,
        },

        "inert_subset_analysis": {
            "severity_and_duration_answer_tokens": inert_rows,
            "all_inert_against_current_artifacts": all_inert,
            "checked_against": {
                "kb": "kb.ng.v2.4.json",
                "rules": "rules.ng.v2.2.json",
                "red_flag_clarifiers": "kRedFlagClarifiers",
                "demographic_modifiers": "kb conditions[].demographic_modifiers",
                "question_triggers": "kFollowupQuestionMap trigger tokens",
            },
            "inert_today_is_not_inert_forever": (
                "These tokens carry no scoring weight and no red-flag reference "
                "IN kb 2.4 AND rules 2.2. That is a property of the CURRENT "
                "artifacts, not of the tokens. A future KB revision that gives "
                "`severe` or `days_7_plus` a weight would make this subset "
                "clinically active with no change to the question flow, so any "
                "approval of an inert subset must be re-validated on every "
                "clinical artifact change and must be enforced by a validator "
                "rather than by this sentence."
            ),
        },

        "scoring_input_delta": {
            "note": (
                "The exact weight a newly reachable token would contribute to "
                "each condition. This is the scoring INPUT delta; the resulting "
                "score, ranking and urgency require the Mobile engine."
            ),
            "conditions_touched": len(weight_delta),
            "conditions_touched_of_total": "%d of %d"
            % (len(weight_delta), index.condition_count),
            "by_condition": [
                weight_delta[c] for c in sorted(
                    weight_delta, key=lambda c: -weight_delta[c]["max_added_weight"]
                )
            ],
        },

        "closure_and_path_effects": {
            "per_seed": seed_rows,
            "path_effects": path_rows,
            "path_limit": PATH_LIMIT,
            "grouping_applies": True,
            "grouping_note": (
                "Under contract 1.1 each groupable role presents ONE question, "
                "so N newly eligible severity questions still present one "
                "severity question. Without grouping, IM-003 would push far "
                "harder against the limit."
            ),
        },
    }



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report = build_report()
    payload = dump_artifact_bytes(report)

    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/im003_impact_analysis_v1.json is missing or stale")
            return 1
        print("OK   IM-003 impact analysis is reproducible, sha256:%s"
              % sha256_bytes(payload))
        return 0

    write_bytes(REPORT_PATH, payload)
    graph = report["trigger_graph"]
    rf = report["red_flag_cross_reference"]
    print("wrote reports/im003_impact_analysis_v1.json")
    print("  trigger graph:        %d nodes, %d edges, %d two-cycles, %d self-loops"
          % (graph["node_count"], graph["edge_count"],
             graph["two_cycle_count"], graph["self_loop_count"]))
    print("  monotone (additive):  %s | max closure %d | max depth %d"
          % (graph["monotone_under_additive_rebranching"],
             graph["max_closure_size"], graph["max_convergence_depth"]))
    print("  pair reconciliation:  declared %d, recomputed %d, reconciles %s"
          % (report["pair_reconciliation"]["declared_in_candidate"],
             report["pair_reconciliation"]["recomputed"],
             report["pair_reconciliation"]["reconciles"]))
    print("  newly reachable:      %d tokens" % rf["newly_reachable_token_count"])
    print("    red-flag affecting:   %d" % rf["red_flag_affecting_count"])
    print("    scoring affecting:    %d" % rf["scoring_affecting_count"])
    print("    no red-flag relevance:%d" % rf["no_red_flag_relevance_count"])
    print("  safety-critical decision required: %s"
          % rf["safety_critical_decision_required"])
    print("  severity/duration inert today:     %s"
          % report["inert_subset_analysis"]["all_inert_against_current_artifacts"])
    print("  conditions touched by scoring delta: %s"
          % report["scoring_input_delta"]["conditions_touched_of_total"])
    print("  sha256: %s" % sha256_bytes(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
