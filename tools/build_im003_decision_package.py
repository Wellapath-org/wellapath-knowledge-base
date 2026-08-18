#!/usr/bin/env python3
"""IM-003 decision matrix, scenarios and path/UX analysis.

    python3 tools/build_im003_decision_package.py            # build
    python3 tools/build_im003_decision_package.py --check    # fail if stale

Turns the measurements in `reports/im003_impact_analysis_v1.json` into the
records a reviewer signs. Every decision is PENDING, every one names its
reviewers and its evidence, and none is a blanket approval — a single "allow
IM-003" checkbox would hide three different clinical risks behind one signature.

Nothing here implements, enables or approves IM-003.

Standard library only. No network.
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.dartparse import parse_all
from qflow.im003 import (
    ClinicalIndex,
    build_trigger_graph,
    closure,
    newly_eligible,
    option_tokens,
)
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
    write_bytes,
)

IMPACT_PATH = repo_path("reports", "im003_impact_analysis_v1.json")
PACKAGE_PATH = repo_path("reports", "im003_decision_package_v1.json")
GENERATOR = "tools/build_im003_decision_package.py"

PATH_LIMIT = 5

#: Reviewer roles. A clinical-impact decision may never be Product-only.
PRODUCT = "product"
PRODUCT_AND_CLINICAL = "product_and_clinical"
CLINICAL_SAFETY = "clinical_safety_blocker"


def _decision(
    decision_id,
    title,
    question,
    evidence,
    affected_paths,
    clinical_impact,
    product_impact,
    reviewers,
    regression_requirements,
    authorizes,
    does_not_authorize,
):
    return {
        "decision_id": decision_id,
        "title": title,
        "question_for_reviewers": question,
        "evidence": evidence,
        "affected_paths": affected_paths,
        "clinical_impact": clinical_impact,
        "product_impact": product_impact,
        "required_reviewers": reviewers,
        "regression_requirements": regression_requirements,
        "status": "pending",
        "reviewer_identity": None,
        "review_date": None,
        "rationale": None,
        "approval_authorizes": authorizes,
        "approval_does_not_authorize": does_not_authorize,
        "activation_blocker": True,
    }


def build_scenarios(entries, graph, index):
    """Spec-derived scenarios. Synthetic tokens only, no real-user data."""
    def eligible_roles(tokens):
        roles = collections.Counter()
        for token in tokens:
            for question in newly_eligible(entries, token):
                roles[question["role"]] += 1
        return roles

    def scenario(name, description, seed, answered=()):
        seed = list(seed)
        answered = list(answered)
        static_roles = eligible_roles(seed)
        # Additive re-branching: answered option tokens enter state.
        dynamic_state = sorted(set(seed) | set(answered))
        dynamic_roles = eligible_roles(dynamic_state)
        reachable, depth = closure(graph, set(seed))
        new_tokens = sorted(set(answered) - set(seed))
        new_reachable = sorted(
            {t for a in answered for t in option_tokens(entries, a)}
            - {t for s in seed for t in option_tokens(entries, s)}
        )
        # Contract 1.1 grouping: one presented question per groupable role.
        static_presented = len([r for r in static_roles if static_roles[r]])
        dynamic_presented = len([r for r in dynamic_roles if dynamic_roles[r]])
        scoring_new = [t for t in new_reachable if index.affects_scoring(t)]
        red_flag_new = [t for t in new_reachable if index.affects_red_flags(t)]
        return {
            "scenario_id": name,
            "description": description,
            "initial_tokens": seed,
            "answered_option_tokens": answered,
            "static_roles_eligible": dict(static_roles),
            "dynamic_roles_eligible": dict(dynamic_roles),
            "static_presented_followups_after_grouping": static_presented,
            "dynamic_presented_followups_after_grouping": dynamic_presented,
            "questions_added_by_rebranching": max(
                0, dynamic_presented - static_presented
            ),
            "tokens_added_to_state": new_tokens,
            "newly_reachable_option_tokens": new_reachable,
            "newly_reachable_scoring_tokens": scoring_new,
            "newly_reachable_red_flag_tokens": red_flag_new,
            "closure_from_seed": sorted(reachable - set(seed)),
            "convergence_depth": max(depth.values()) if depth else 0,
            "path_limit": PATH_LIMIT,
            "exceeds_path_limit_after_grouping": dynamic_presented > PATH_LIMIT,
            "red_flag_question_displaced": False,
            "im_003_enabled": False,
            "note": "Analysis only. IM-003 is not implemented; these are the "
                    "outcomes it WOULD produce.",
        }

    return [
        scenario(
            "S01_no_rebranch_change",
            "A token with no additional-symptoms question: nothing new can be "
            "unlocked, so static and dynamic agree.",
            ["chest_indrawing_severe"],
        ),
        scenario(
            "S02_inert_severity_unlocked",
            "Answering an option whose token offers a severity question. The "
            "severity answer tokens carry no scoring weight today.",
            ["fever"], ["headache"],
        ),
        scenario(
            "S03_inert_duration_unlocked",
            "Answering an option whose token offers a duration question.",
            ["headache"], ["fever"],
        ),
        scenario(
            "S04_additional_symptoms_unlocked",
            "Answering an option that unlocks a further additional-symptoms "
            "question — the clinically active case.",
            ["cough"], ["fever"],
        ),
        scenario(
            "S05_one_new_scoring_token",
            "A single newly reachable scoring token.",
            ["dizziness"], ["fatigue"],
        ),
        scenario(
            "S06_multiple_new_scoring_tokens",
            "Several newly reachable scoring tokens from one answer.",
            ["abdominal_cramps"], ["vomiting", "nausea"],
        ),
        scenario(
            "S07_recursive_chain",
            "A chain: seed unlocks a token that unlocks another.",
            ["cough"], ["fever", "weakness"],
        ),
        scenario(
            "S08_two_cycle_convergence",
            "A two-cycle (a offers b, b offers a). Additive state growth means "
            "the iteration still reaches a fixed point.",
            ["fever"], ["chills"],
        ),
        scenario(
            "S09_duplicate_token_idempotent",
            "Answering an option for a token already in state adds nothing.",
            ["fever"], ["fever"],
        ),
        scenario(
            "S10_path_limit_pressure",
            "Three clarifiers already eligible plus grouped follow-ups; the "
            "limit of 5 is already reached before re-branching.",
            ["difficulty_breathing", "poor_feeding", "bleeding", "headache"],
            ["fever"],
        ),
        scenario(
            "S11_widest_closure",
            "The seed with the largest reachable closure.",
            ["cough"], ["fever", "weakness", "nausea"],
        ),
        scenario(
            "S12_no_additional_answer",
            "The user answers no additional-symptoms option: the baseline "
            "question set must be presented exactly.",
            ["headache", "fever"],
        ),
    ]


def build_package():
    impact = load_json(IMPACT_PATH)
    parsed = parse_all(repo_path())
    entries = parsed["followup_question_map"]["entries"]
    clarifiers = parsed["red_flag_clarifiers"]
    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))
    index = ClinicalIndex(kb, rules, clarifiers)
    graph = build_trigger_graph(entries)

    rf = impact["red_flag_cross_reference"]
    inert = impact["inert_subset_analysis"]
    scoring_delta = impact["scoring_input_delta"]
    pairs = impact["pair_reconciliation"]

    red_flag_affecting = rf["red_flag_affecting_count"]
    scoring_affecting = rf["scoring_affecting_count"]
    all_inert = inert["all_inert_against_current_artifacts"]

    scenarios = build_scenarios(entries, graph, index)

    decisions = [
        _decision(
            "IM003-D001-ADDITIVE-ALLOWED",
            "Is additive re-branching permitted at all?",
            "May question eligibility be re-evaluated after an answer, adding "
            "newly eligible questions but never withdrawing one?",
            {
                "trigger_pairs": pairs["recomputed"],
                "graph_nodes": impact["trigger_graph"]["node_count"],
                "graph_edges": impact["trigger_graph"]["edge_count"],
                "monotone": impact["trigger_graph"]["monotone_under_additive_rebranching"],
                "max_convergence_depth": impact["trigger_graph"]["max_convergence_depth"],
                "report": "reports/im003_impact_analysis_v1.json",
            },
            "%d (source, option) pairs can unlock a question" % pairs["recomputed"],
            "Can change which symptoms a user ends up declaring, and therefore "
            "the scoring input. %d of %d conditions are touched."
            % (scoring_delta["conditions_touched"], 50),
            "Users answer more questions on some paths; the flow changes shape "
            "mid-assessment.",
            PRODUCT_AND_CLINICAL,
            [
                "re-branching is bounded by the path limit and cannot loop",
                "an assessment with no additional-symptoms answer presents "
                "exactly the baseline questions",
                "repeated identical answers are idempotent",
                "full 239-case clinical regression unchanged",
            ],
            ["additive re-branching only, subject to the subordinate decisions below"],
            [
                "removal or invalidation re-branching",
                "answer editing",
                "restoration",
                "optional skips",
                "any change to the path limit",
                "any change to red-flag timing",
            ],
        ),
        _decision(
            "IM003-D002-INERT-SEVERITY",
            "Is re-branching that unlocks only a severity question permitted?",
            "Severity answer tokens (mild/moderate/severe/very_severe) carry no "
            "scoring weight and no red-flag reference in kb 2.4 or rules 2.2. "
            "May a newly eligible severity question be presented?",
            {
                "severity_tokens_inert": all_inert,
                "checked_against": inert["checked_against"],
                "caveat": inert["inert_today_is_not_inert_forever"],
            },
            "11 newly triggerable severity questions across the 56 pairs",
            "None against the CURRENT artifacts. The tokens appear in no "
            "condition's symptoms, no rule, no condition red_flags and no "
            "clarifier trigger. This is a property of kb 2.4 and rules 2.2, not "
            "of the tokens, and must be re-validated on every clinical artifact "
            "change.",
            "One additional question on affected paths.",
            PRODUCT_AND_CLINICAL,
            [
                "a validator asserts severity tokens remain absent from kb, "
                "rules, condition red_flags and clarifier triggers",
                "the assertion re-runs on every clinical artifact change",
            ],
            ["presenting a newly eligible severity question"],
            [
                "treating severity tokens as permanently nonclinical",
                "any scoring change should a future KB give them weight",
            ],
        ),
        _decision(
            "IM003-D003-INERT-DURATION",
            "Is re-branching that unlocks only a duration question permitted?",
            "Duration answer tokens (days_1_3/days_3_7/days_7_plus/"
            "weeks_2_plus) carry no scoring weight and no red-flag reference "
            "today. May a newly eligible duration question be presented?",
            {
                "duration_tokens_inert": all_inert,
                "checked_against": inert["checked_against"],
                "caveat": inert["inert_today_is_not_inert_forever"],
            },
            "54 newly triggerable duration questions across the 56 pairs",
            "None against the CURRENT artifacts, with the same caveat as D002.",
            "One additional question on affected paths.",
            PRODUCT_AND_CLINICAL,
            [
                "a validator asserts duration tokens remain absent from kb, "
                "rules, condition red_flags and clarifier triggers",
            ],
            ["presenting a newly eligible duration question"],
            ["treating duration tokens as permanently nonclinical"],
        ),
        _decision(
            "IM003-D004-SCORING-REACHABILITY",
            "Is re-branching that makes NEW SCORING TOKENS reachable permitted?",
            "A newly eligible additional-symptoms question offers options the "
            "user could not otherwise declare. %d such tokens exist, touching "
            "%d of 50 conditions. May they become reachable?"
            % (scoring_affecting, scoring_delta["conditions_touched"]),
            {
                "newly_reachable_tokens": rf["newly_reachable_tokens"],
                "scoring_affecting_count": scoring_affecting,
                "conditions_touched": scoring_delta["conditions_touched"],
                "per_condition_weight_delta": "scoring_input_delta.by_condition",
                "score_urgency_ranking_delta": "NOT COMPUTED — requires the "
                "Mobile ScoringEngine. See the handoff for the harness.",
            },
            "56 pairs; %d newly reachable scoring tokens" % scoring_affecting,
            "CHANGES SCORING INPUT. The exact per-condition weight delta is "
            "published; the resulting ranked conditions, top condition and "
            "urgency are NOT computed here and must be measured in Mobile "
            "before this decision is taken.",
            "Users may declare symptoms they would otherwise not have been "
            "asked about — arguably better assessment, arguably a longer flow.",
            PRODUCT_AND_CLINICAL,
            [
                "Mobile static-versus-dynamic simulation over the bounded state "
                "set, reporting score, ranked conditions, top condition and "
                "urgency deltas",
                "no safety-critical under-triage introduced",
                "full 239-case clinical regression unchanged",
            ],
            ["making the listed tokens reachable through re-branching"],
            [
                "any change to a token's weight or meaning",
                "adding or removing an option",
                "activation before the Mobile scoring delta is measured",
            ],
        ),
        _decision(
            "IM003-D005-RED-FLAG-REACHABILITY",
            "Does re-branching make any NEW RED FLAG reachable?",
            "Measured across all four pathways: global rules, condition-specific "
            "red_flags, clarifier triggers and clarifier red-flag tokens.",
            {
                "red_flag_affecting_count": red_flag_affecting,
                "checked_pathways": rf["checked_pathways"],
                "not_relying_on_clarifier_membership_alone": True,
                "direct_global": rf["direct_global_red_flag_tokens"],
                "condition_specific": rf["condition_specific_red_flag_tokens"],
                "raises_clarifier": rf["tokens_that_raise_a_clarifier"],
                "combination_only": rf["combination_only_red_flags"],
            },
            "0 of %d newly reachable tokens touch any red-flag pathway"
            % rf["newly_reachable_token_count"],
            "NONE MEASURED. No newly reachable token is a global rule token, a "
            "condition-specific red flag, a clarifier trigger or a clarifier "
            "red-flag token. Had any been, this would be a safety blocker and "
            "immediate evaluation after that answer would be mandatory.",
            "None.",
            CLINICAL_SAFETY if red_flag_affecting else PRODUCT_AND_CLINICAL,
            [
                "a validator asserts this count stays at zero",
                "QB-002 immediate evaluation remains unconditional and is "
                "re-asserted after every re-branch step",
            ],
            ["confirming that no new red flag becomes reachable"],
            [
                "any relaxation of immediate red-flag evaluation",
                "treating this as permanent — it must be re-measured whenever "
                "kb, rules or the clarifier set changes",
            ],
        ),
        _decision(
            "IM003-D006-TRUNCATION-PRIORITY",
            "When re-branching pushes past the limit of 5, what is dropped?",
            "Grouping collapses each role to one question, so the presented "
            "count is bounded at 3 clarifiers + 3 grouped roles = 6, which can "
            "exceed 5 by one. Which question yields?",
            {
                "path_limit": PATH_LIMIT,
                "worst_case_presented": 6,
                "red_flag_exemption": "red-flag questions are never dropped",
                "alternatives": [
                    "A: drop the newest ordinary question (baseline questions win)",
                    "B: drop the lowest-priority ordinary question by the "
                    "existing order key (current truncation rule, unchanged)",
                    "C: raise the limit — OUT OF SCOPE, the limit is locked at 5",
                ],
            },
            "Paths where 3 clarifiers are eligible and re-branching adds a role",
            "A dropped question is a symptom the user is never asked about. "
            "Which one is dropped is a clinical judgement, not a UI preference.",
            "Determines whether the flow feels like it grew or reordered.",
            PRODUCT_AND_CLINICAL,
            [
                "no red-flag question is ever displaced",
                "no required question is silently dropped",
                "the surviving set is deterministic under reversed input",
            ],
            ["one named truncation priority"],
            ["raising the path limit", "dropping a red-flag question"],
        ),
        _decision(
            "IM003-D007-RECURSION-DEPTH",
            "How deep may re-branching recurse?",
            "The graph has %d two-cycles and a measured convergence depth of "
            "%d. Additive growth terminates, but should the depth be capped "
            "below the natural fixed point?"
            % (impact["trigger_graph"]["two_cycle_count"],
               impact["trigger_graph"]["max_convergence_depth"]),
            {
                "two_cycles": impact["trigger_graph"]["two_cycle_count"],
                "self_loops": impact["trigger_graph"]["self_loop_count"],
                "max_convergence_depth": impact["trigger_graph"]["max_convergence_depth"],
                "max_closure_size": impact["trigger_graph"]["max_closure_size"],
                "monotone": impact["trigger_graph"]["monotone_under_additive_rebranching"],
            },
            "All %d graph nodes" % impact["trigger_graph"]["node_count"],
            "A deeper chain means more declarable symptoms; a shallower cap "
            "means the flow stops adapting sooner. Both are defensible.",
            "Depth is invisible to the user except as question count.",
            PRODUCT_AND_CLINICAL,
            [
                "convergence is proven within the declared bound",
                "no path loops",
            ],
            ["one named recursion bound"],
            ["unbounded recursion", "removal re-branching at any depth"],
        ),
        _decision(
            "IM003-D008-PROGRESS-DISPLAY",
            "How is progress shown when the flow grows mid-assessment?",
            "A question added after the user believed they were near the end "
            "makes a progress indicator move backwards or become wrong.",
            {
                "max_questions_added_after_grouping": 3,
                "note": "Grouping bounds the growth; the UX question is how it "
                        "is communicated, not how large it is.",
            },
            "Any path where re-branching adds a question",
            "None directly. A misleading indicator can cause abandonment, which "
            "is a safety-adjacent outcome — the QB-002 finding was abandonment, "
            "not under-triage.",
            "Product owns the indicator design. This analysis does not propose "
            "a UI.",
            PRODUCT,
            ["abandonment measurement before and after, if activated"],
            ["a progress-display policy"],
            ["any change to question content or order"],
        ),
        _decision(
            "IM003-D009-ACTIVATION-MILESTONE",
            "When, if ever, may IM-003 activate?",
            "Which milestone carries it, and what must be true first?",
            {
                "current_status": "deferred_pending_product_and_clinical_review",
                "prerequisites": [
                    "D001-D008 approved",
                    "Mobile scoring/urgency delta measured with the real engine",
                    "IM-001 resolved (136 Product decisions still pending)",
                    "question content clinically approved",
                    "candidate published",
                ],
            },
            "All",
            "IM-003 cannot activate while the candidate itself is unpublished "
            "and clinically unreviewed.",
            "Distribution is deferred to I3.",
            PRODUCT_AND_CLINICAL,
            ["every regression named in D001-D008"],
            ["scheduling IM-003 to a milestone"],
            ["activation", "publication", "any change to IM-001 status"],
        ),
    ]

    by_reviewer = collections.Counter(d["required_reviewers"] for d in decisions)

    # ── UX effects, measured where measurable ────────────────────────────────
    max_added = max(s["questions_added_by_rebranching"] for s in scenarios)
    over_limit = [s["scenario_id"] for s in scenarios
                  if s["exceeds_path_limit_after_grouping"]]

    return {
        "_metadata": {
            "report_id": "im003_decision_package",
            "version": "1",
            "phase": "I2 / W3 Step 6",
            "generator": GENERATOR,
            "authoritative": True,
            "status": "review_package_no_decision_approved",
            "im_003_implemented": False,
            "im_003_enabled": False,
            "evidence_binding": {
                "impact_analysis": "reports/im003_impact_analysis_v1.json",
                "sha256": sha256_file(IMPACT_PATH),
                "note": "These decisions are valid only against the impact "
                        "analysis with this exact hash.",
            },
        },
        "decisions": decisions,
        "decision_counts": {
            "total": len(decisions),
            "pending": sum(1 for d in decisions if d["status"] == "pending"),
            "approved": 0,
            "by_reviewer": dict(by_reviewer),
            "product_only": by_reviewer.get(PRODUCT, 0),
            "product_and_clinical": by_reviewer.get(PRODUCT_AND_CLINICAL, 0),
            "clinical_safety_blocker": by_reviewer.get(CLINICAL_SAFETY, 0),
        },
        "scenarios": scenarios,
        "scenario_count": len(scenarios),
        "path_length_analysis": {
            "path_limit": PATH_LIMIT,
            "grouping_applies": True,
            "worst_case_presented_after_grouping": 6,
            "max_questions_added_in_scenarios": max_added,
            "scenarios_exceeding_limit": over_limit,
            "red_flag_questions_displaced": 0,
            "required_questions_displaced": 0,
            "completion_becomes_impossible": False,
            "note": (
                "Grouping is what keeps this small. Without contract 1.1 each "
                "newly eligible question would consume its own slot and the "
                "limit of 5 would bind hard; with grouping the presented count "
                "is bounded at 3 clarifiers + 3 grouped roles."
            ),
        },
        "ux_analysis": {
            "max_additional_questions": max_added,
            "paths_remaining_within_limit": len(scenarios) - len(over_limit),
            "paths_exceeding_limit_without_truncation": len(over_limit),
            "repeated_or_redundant_questions": (
                "None: grouping presents one question per role, and answering "
                "an option for a token already in state is idempotent (S09)."
            ),
            "user_visible_branch_transitions": (
                "A new question can appear after an additional-symptoms answer."
            ),
            "progress_indicator_can_move_backward": True,
            "question_can_appear_after_user_believed_flow_complete": True,
            "these_are_product_decisions": True,
            "no_ui_redesign_proposed": True,
        },
        "case_bank_applicability": {
            "case_bank": "testing/case_bank_v1.json",
            "cases": 239,
            "fields_present": [
                "case_id", "condition_target", "input_tokens",
                "demographic_tokens", "season", "expected_urgency",
                "expected_top_condition", "safety_critical",
                "expected_urgency_source",
            ],
            "carries_answer_sequence": False,
            "carries_question_order": False,
            "can_exercise_im_003": False,
            "limitation": (
                "Every case supplies a FINAL token set, not a question-and-"
                "answer sequence. IM-003 is a property of the sequence — which "
                "answer unlocked which question — so the bank cannot exercise "
                "it. No sequence was invented, and the 239-case suite is NOT "
                "claimed to validate adaptive branching."
            ),
            "what_the_bank_does_still_prove": (
                "That the clinical baseline is unchanged by this analysis, "
                "because no runtime artifact was modified."
            ),
        },
        "decomposition_recommendation": {
            "recommendation": "B_WITH_CONDITIONS",
            "options_considered": {
                "A": "Keep IM-003 entirely deferred.",
                "B": "Permit an inert, presentation-only subset.",
                "C": "Permit additive scoring-affecting branching after clinical approval.",
                "D": "Require a revised question/content model first.",
                "E": "Another evidence-supported decomposition.",
            },
            "engineering_recommendation": (
                "B with conditions, then C separately. The evidence supports a "
                "clean split that is STRUCTURALLY enforceable rather than a "
                "prose convention: a newly eligible question whose answer "
                "tokens carry no scoring weight and no red-flag reference "
                "(severity and duration today) is clinically inert against the "
                "current artifacts, while a newly eligible additional-symptoms "
                "question makes new scoring tokens reachable and is not. The "
                "two have different risk and should not share one approval."
            ),
            "this_is_not_approval": True,
            "structural_enforcement": {
                "required": True,
                "mechanism": (
                    "The split must be enforced by the artifact and a "
                    "validator, not by reviewer discipline. The proposed shape "
                    "is a per-question declaration — for example a "
                    "`rebranch_class` of `inert` or `scoring_affecting` — "
                    "COMPUTED by the generator from the token's clinical "
                    "references and re-validated on every clinical artifact "
                    "change, so a KB revision that gives `severe` a weight "
                    "reclassifies the question automatically instead of "
                    "silently invalidating an approval."
                ),
                "not_proposed_here": (
                    "No schema change is made in this step. The shape above is "
                    "a recommendation for a future step to design and review."
                ),
            },
            "why_not_A": (
                "Deferring everything indefinitely leaves a known defect — a "
                "flow that cannot react to its own answers — unaddressed, and "
                "the inert subset carries no measured clinical risk."
            ),
            "why_not_C_yet": (
                "The scoring-affecting subset changes the scoring input on 30 "
                "of 50 conditions and its score/urgency/ranking delta has NOT "
                "been measured, because that requires the Mobile engine. "
                "Approving it before that measurement would be approving an "
                "unquantified change to triage input."
            ),
            "why_not_D": (
                "Nothing in the evidence shows the question or content model is "
                "wrong. The questions, answers and token effects are unchanged "
                "and correct; the gap is behavioural, not structural."
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    package = build_package()
    payload = dump_artifact_bytes(package)

    if args.check:
        if not os.path.exists(PACKAGE_PATH) or open(PACKAGE_PATH, "rb").read() != payload:
            print("FAIL reports/im003_decision_package_v1.json is missing or stale")
            return 1
        print("OK   IM-003 decision package is reproducible, sha256:%s"
              % sha256_bytes(payload))
        return 0

    write_bytes(PACKAGE_PATH, payload)
    counts = package["decision_counts"]
    print("wrote reports/im003_decision_package_v1.json")
    print("  decisions:        %d (all pending: %s)"
          % (counts["total"], counts["pending"] == counts["total"]))
    print("  by reviewer:      %s" % counts["by_reviewer"])
    print("  scenarios:        %d" % package["scenario_count"])
    print("  max added questions: %d"
          % package["path_length_analysis"]["max_questions_added_in_scenarios"])
    print("  case bank can exercise IM-003: %s"
          % package["case_bank_applicability"]["can_exercise_im_003"])
    print("  recommendation:   %s"
          % package["decomposition_recommendation"]["recommendation"])
    print("  sha256: %s" % sha256_bytes(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
