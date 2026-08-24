#!/usr/bin/env python3
"""Authoritative IM-001 option-ordering evidence and the global Product decision.

    python3 tools/report_im001_option_ordering.py            # write
    python3 tools/report_im001_option_ordering.py --check    # fail if stale

Mobile PR #75 produced an addendum decomposing the live option-list instability.
That addendum is explicitly non-authoritative. This tool INDEPENDENTLY recomputes
every count from the knowledge base's own captured-Dart oracle and the frozen
clinical artifacts, and only then records the result. Mobile's numbers are stored
alongside for reconciliation, never used as an input to the computation.

What it produces:

  reports/im001_option_order_evidence_v1.json
      All 903 option-order contest groups, with membership, token mappings and
      per-group clinical impact. Supporting evidence, not 903 approvals.

  reports/im001_option_order_decision_v1.json
      ONE global pending Product decision for the deterministic ordering rule,
      bound by SHA256 to the evidence table above.

Why one decision and not 903: every group is the same question — should option
order be deterministic? — and every clinical dimension is identical across all
of them. Asking Product 903 times would be asking the same question 903 times.
The groups are retained because a reviewer is entitled to see the instances.

The Product-only classification is CONDITIONAL. If any membership, token-mapping,
reachability, scoring or red-flag dimension ever becomes non-zero, this tool
refuses to emit a Product-only decision and exits non-zero.
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_bytes, sha256_file, write_bytes

ORACLE = repo_path("testing", "questions", "fixtures", "oracle", "live_question_oracle_v1.json")
CANDIDATE_1_1 = repo_path("candidate", "question_flow.ng.v1.1.json")
WORDING_REVIEW = repo_path("reports", "im001_product_review_v1_1.json")
EVIDENCE_PATH = repo_path("reports", "im001_option_order_evidence_v1.json")
DECISION_PATH = repo_path("reports", "im001_option_order_decision_v1.json")

# Mobile PR #75 declared figures, recorded for reconciliation only. Nothing below
# reads these to decide anything.
MOBILE_EVIDENCE = {
    "repository": "Wellapath-org/wellapath-mobile",
    "pull_request": 75,
    "head": "dd9c6d080dd807ea4c7a48cca6858ddd6a1cf732",
    "path": "docs/evidence/im001_option_instability_addendum_v1.json",
    "sha256": "371443cf1914b9870ecdd0a3ebe6838bd7322edd59f827058b1db3635f0e57a3",
    "bytes": 1252307,
    "authoritative": False,
    "status_at_receipt": "pending_knowledge_base_incorporation",
    "generator": "test/question_flow_v1_1/reversed_classification_test.dart",
    "oracle_source_commit": "657739cc1745104dd1194a57ef14cc9793c9b98e",
    "knowledge_base_commit": "cffbe8a673c7a5be5dfb882cea77c1705c7515c3",
    "declared_counts": {
        "reversed_comparisons": 2300,
        "identical": 413,
        "wording_and_option_order_difference": 1665,
        "option_order_only_difference": 207,
        "wording_only_difference": 15,
        "wording": 1680,
        "optionIdSequence": 1872,
        "optionLabelSequence": 1872,
        "optionToTokenSequence": 1872,
        "optionIdSet": 0,
        "optionLabelSet": 0,
        "optionToTokenSet": 0,
        "reachableTokenSet": 0,
        "scoringReachableTokenSet": 0,
        "redFlagReachableTokenSet": 0,
        "questionIdentitySequence": 0,
        "questionRoleSequence": 0,
        "truncationSet": 0,
        "requiredSkipSemantics": 0,
        "wording_decision_groups": 135,
        "option_order_decision_groups": 903,
    },
}

# Clarifier answers are display labels, not tokens. Only an explicit "Yes"
# contributes the red-flag token, and that is a property of the question, not of
# the option's position in the list.
CLARIFIER_LABELS = ("Yes", "No")


def clinical_roles():
    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))
    token_dictionary = load_json(repo_path("token_dictionary.ng.v1.1.json"))
    known = set()
    for category in ["symptom_tokens", "red_flag_tokens", "duration_tokens",
                     "body_area_tokens", "demographic_tokens", "severity_tokens"]:
        known.update(token_dictionary[category])
    scoring = collections.defaultdict(list)
    for condition in kb["conditions"]:
        for symptom in condition["symptoms"]:
            scoring[symptom["token"]].append(condition["condition_id"])
    rule_refs = collections.defaultdict(list)
    for rule in rules["rules"]:
        rule_refs[rule["token"]].append(rule["rule_id"])
    condition_red_flags = collections.defaultdict(list)
    for condition in kb["conditions"]:
        for token in condition["red_flags"]:
            condition_red_flags[token].append(condition["condition_id"])
    return known, scoring, rule_refs, condition_red_flags


def option_tokens(question):
    """Canonical tokens an option list can contribute.

    For additional_symptoms the option id IS the canonical token id. For a
    clarifier the options are Yes/No labels; the token it can contribute is
    `red_flag_token`, reachable only via "Yes" and independent of list order.
    """
    if question["role"] == "red_flag_clarifier":
        return [question["red_flag_token"]] if question["red_flag_token"] else []
    return [o for o in question["options"] if o not in CLARIFIER_LABELS]


def compare(forward, reversed_case):
    """Every dimension, computed for one forward/reversed pair."""
    f, r = forward["questions"], reversed_case["questions"]

    def seq(questions, key):
        return [key(q) for q in questions]

    def reachable(questions):
        return {t for q in questions for t in option_tokens(q)}

    return {
        "wording": seq(f, lambda q: q["question_text"]) != seq(r, lambda q: q["question_text"]),
        # Question IDENTITY is the slot — its role and, for a clarifier, which
        # red flag it clarifies. It deliberately EXCLUDES question_text: which
        # wording fills a slot is a separate reviewable choice, tracked as the
        # `wording` dimension and decided by the 135 wording decisions. Folding
        # wording into identity would double-count the same 1,680 differences and
        # would wrongly report a slot as having changed when only its text did.
        "questionIdentitySequence": seq(f, lambda q: (q["role"], q["red_flag_token"]))
                                    != seq(r, lambda q: (q["role"], q["red_flag_token"])),
        "questionRoleSequence": seq(f, lambda q: q["role"]) != seq(r, lambda q: q["role"]),
        "optionIdSequence": seq(f, lambda q: tuple(q["options"]))
                            != seq(r, lambda q: tuple(q["options"])),
        "optionIdSet": seq(f, lambda q: frozenset(q["options"]))
                       != seq(r, lambda q: frozenset(q["options"])),
        # Option id and label are the same string in this engine; both are
        # reported so a future divergence cannot hide behind one name.
        "optionLabelSequence": seq(f, lambda q: tuple(q["options"]))
                               != seq(r, lambda q: tuple(q["options"])),
        "optionLabelSet": seq(f, lambda q: frozenset(q["options"]))
                          != seq(r, lambda q: frozenset(q["options"])),
        "optionToTokenSequence": seq(f, lambda q: tuple(option_tokens(q)))
                                 != seq(r, lambda q: tuple(option_tokens(q))),
        "optionToTokenSet": seq(f, lambda q: frozenset(option_tokens(q)))
                            != seq(r, lambda q: frozenset(option_tokens(q))),
        "reachableTokenSet": reachable(f) != reachable(r),
        "truncationSet": len(f) != len(r),
        "requiredSkipSemantics": False,  # the live engine has no skip concept at all
        "redFlagQuestionSequence": seq(f, lambda q: q["red_flag_token"])
                                   != seq(r, lambda q: q["red_flag_token"]),
    }


def build():
    oracle = load_json(ORACLE)
    known_tokens, scoring, rule_refs, condition_red_flags = clinical_roles()

    forward_by_tokens = {tuple(sorted(c["input_tokens"])): c for c in oracle["forward"]}

    buckets = collections.Counter()
    dimensions = collections.Counter()
    order_groups = collections.OrderedDict()
    wording_groups = collections.OrderedDict()
    unpaired = []
    scoring_reachable_diff = 0
    red_flag_reachable_diff = 0
    tokens_one_order_only = set()

    for case in oracle["reversed"]:
        key = tuple(sorted(case["input_tokens"]))
        forward = forward_by_tokens.get(key)
        if forward is None:
            unpaired.append(list(key))
            continue

        result = compare(forward, case)
        for name, differs in result.items():
            if differs:
                dimensions[name] += 1

        fwd_tokens = {t for q in forward["questions"] for t in option_tokens(q)}
        rev_tokens = {t for q in case["questions"] for t in option_tokens(q)}
        delta = fwd_tokens ^ rev_tokens
        if delta:
            tokens_one_order_only |= delta
            if any(t in scoring for t in delta):
                scoring_reachable_diff += 1
            if any(t in rule_refs or t in condition_red_flags for t in delta):
                red_flag_reachable_diff += 1

        wording_differs = result["wording"]
        order_differs = result["optionIdSequence"]
        if not wording_differs and not order_differs:
            buckets["identical"] += 1
        elif wording_differs and order_differs:
            buckets["wording_and_option_order_difference"] += 1
        elif order_differs:
            buckets["option_order_only_difference"] += 1
        else:
            buckets["wording_only_difference"] += 1

        # Per-question contest grouping.
        for qf, qr in zip(forward["questions"], case["questions"]):
            if tuple(qf["options"]) != tuple(qr["options"]):
                gkey = (qf["role"], tuple(qf["options"]), tuple(qr["options"]))
                entry = order_groups.setdefault(gkey, {"paths": 0, "examples": []})
                entry["paths"] += 1
                if len(entry["examples"]) < 3:
                    entry["examples"].append(sorted(case["input_tokens"]))
            if qf["question_text"] != qr["question_text"]:
                wkey = (qf["role"], qf["question_text"], qr["question_text"])
                wording_groups.setdefault(wkey, 0)
                wording_groups[wkey] += 1

    # --- per-group clinical impact -------------------------------------------
    groups = []
    membership_differing_groups = []
    mapping_differing_groups = []
    for index, ((role, forward_options, reversed_options), meta) in enumerate(
        order_groups.items(), start=1
    ):
        forward_set, reversed_set = frozenset(forward_options), frozenset(reversed_options)
        membership_differs = forward_set != reversed_set
        forward_tokens = [o for o in forward_options if o not in CLARIFIER_LABELS]
        reversed_tokens = [o for o in reversed_options if o not in CLARIFIER_LABELS]
        mapping_differs = frozenset(forward_tokens) != frozenset(reversed_tokens)
        if membership_differs:
            membership_differing_groups.append(index)
        if mapping_differs:
            mapping_differing_groups.append(index)

        tokens = sorted(forward_set | reversed_set)
        clinical_tokens = [t for t in tokens if t not in CLARIFIER_LABELS]
        groups.append({
            "group_id": "IM001-ORD-G%03d" % index,
            "grouped_question_role": role,
            "source_questions_or_tokens": clinical_tokens,
            "baseline_forward_option_order": list(forward_options),
            "baseline_reversed_option_order": list(reversed_options),
            "candidate_deterministic_option_order": sorted(forward_options),
            "option_membership": sorted(forward_set),
            "option_membership_identical": not membership_differs,
            "option_to_token_mapping": {
                t: t for t in clinical_tokens
            },
            "option_to_token_mapping_rule": "identity — an additional-symptom option id IS the canonical token id",
            "option_to_token_mapping_identical": not mapping_differs,
            "affected_path_count": meta["paths"],
            "example_paths": meta["examples"],
            "tokens_carrying_kb_scoring_weight": sorted(
                t for t in clinical_tokens if t in scoring),
            "tokens_referenced_by_rules": sorted(
                t for t in clinical_tokens if t in rule_refs),
            "tokens_in_condition_red_flag_lists": sorted(
                t for t in clinical_tokens if t in condition_red_flags),
            "tokens_unknown_to_token_dictionary_1_1": sorted(
                t for t in clinical_tokens if t not in known_tokens),
            "clinical_impact_classification": (
                "display_order_only" if not membership_differs and not mapping_differs
                else "MEMBERSHIP_OR_MAPPING_DIFFERS_NOT_PRODUCT_ONLY"
            ),
        })

    total = sum(buckets.values())
    clinical_zero = (
        dimensions["optionIdSet"] == 0
        and dimensions["optionLabelSet"] == 0
        and dimensions["optionToTokenSet"] == 0
        and dimensions["reachableTokenSet"] == 0
        and dimensions["questionIdentitySequence"] == 0
        and dimensions["questionRoleSequence"] == 0
        and dimensions["truncationSet"] == 0
        and dimensions["requiredSkipSemantics"] == 0
        and scoring_reachable_diff == 0
        and red_flag_reachable_diff == 0
        and not tokens_one_order_only
        and not membership_differing_groups
        and not mapping_differing_groups
    )

    declared = MOBILE_EVIDENCE["declared_counts"]
    reconciliation = {
        "reversed_comparisons": (total, declared["reversed_comparisons"]),
        "identical": (buckets["identical"], declared["identical"]),
        "wording_and_option_order_difference": (
            buckets["wording_and_option_order_difference"],
            declared["wording_and_option_order_difference"]),
        "option_order_only_difference": (
            buckets["option_order_only_difference"], declared["option_order_only_difference"]),
        "wording_only_difference": (
            buckets["wording_only_difference"], declared["wording_only_difference"]),
        "wording": (dimensions["wording"], declared["wording"]),
        "optionIdSequence": (dimensions["optionIdSequence"], declared["optionIdSequence"]),
        "optionLabelSequence": (dimensions["optionLabelSequence"], declared["optionLabelSequence"]),
        "optionToTokenSequence": (
            dimensions["optionToTokenSequence"], declared["optionToTokenSequence"]),
        "optionIdSet": (dimensions["optionIdSet"], declared["optionIdSet"]),
        "optionLabelSet": (dimensions["optionLabelSet"], declared["optionLabelSet"]),
        "optionToTokenSet": (dimensions["optionToTokenSet"], declared["optionToTokenSet"]),
        "reachableTokenSet": (dimensions["reachableTokenSet"], declared["reachableTokenSet"]),
        "scoringReachableTokenSet": (
            scoring_reachable_diff, declared["scoringReachableTokenSet"]),
        "redFlagReachableTokenSet": (
            red_flag_reachable_diff, declared["redFlagReachableTokenSet"]),
        "questionIdentitySequence": (
            dimensions["questionIdentitySequence"], declared["questionIdentitySequence"]),
        "questionRoleSequence": (
            dimensions["questionRoleSequence"], declared["questionRoleSequence"]),
        "truncationSet": (dimensions["truncationSet"], declared["truncationSet"]),
        "requiredSkipSemantics": (
            dimensions["requiredSkipSemantics"], declared["requiredSkipSemantics"]),
        "wording_decision_groups": (len(wording_groups), declared["wording_decision_groups"]),
        "option_order_decision_groups": (
            len(groups), declared["option_order_decision_groups"]),
    }

    evidence = {
        "_metadata": {
            "report_id": "im001_option_order_evidence",
            "version": "1",
            "phase": "I2 / W3 Step 5B",
            "generator": "tools/report_im001_option_ordering.py",
            "generator_version": QFLOW_TOOLING_VERSION,
            "authoritative": True,
            "computation": (
                "Every count below is computed here from the knowledge base's own "
                "captured-Dart oracle and the frozen clinical artifacts. Mobile's figures "
                "are recorded for reconciliation and are never an input to the computation."
            ),
            "oracle": {
                "path": os.path.relpath(ORACLE, repo_path()),
                "sha256": sha256_file(ORACLE),
                "evidence_class": "CAPTURED_DART",
            },
            "candidate": {
                "path": "candidate/question_flow.ng.v1.1.json",
                "sha256": sha256_file(CANDIDATE_1_1),
                "version": "1.1",
                "unmodified_by_this_step": True,
            },
            "clinical_inputs": {
                "kb_v2_4": sha256_file(repo_path("kb.ng.v2.4.json")),
                "rules_v2_2": sha256_file(repo_path("rules.ng.v2.2.json")),
                "token_dictionary_v1_1": sha256_file(repo_path("token_dictionary.ng.v1.1.json")),
            },
            "mobile_evidence": MOBILE_EVIDENCE,
        },
        "reconciliation": {
            "all_counts_agree": all(a == b for a, b in reconciliation.values()),
            "unpaired_reversed_cases": unpaired,
            "detail": {
                name: {"knowledge_base": a, "mobile": b, "agree": a == b}
                for name, (a, b) in reconciliation.items()
            },
        },
        "primary_classification_mutually_exclusive": {
            "identical": buckets["identical"],
            "wording_and_option_order_difference": buckets["wording_and_option_order_difference"],
            "option_order_only_difference": buckets["option_order_only_difference"],
            "wording_only_difference": buckets["wording_only_difference"],
            "total": total,
            "sums_to_total": (buckets["identical"]
                              + buckets["wording_and_option_order_difference"]
                              + buckets["option_order_only_difference"]
                              + buckets["wording_only_difference"]) == total,
        },
        "dimension_counts_overlapping": dict(sorted(dimensions.items())),
        "clinical_impact": {
            "option_membership_differences": dimensions["optionIdSet"],
            "option_label_set_differences": dimensions["optionLabelSet"],
            "option_to_token_mapping_set_differences": dimensions["optionToTokenSet"],
            "reachable_token_set_differences": dimensions["reachableTokenSet"],
            "scoring_affecting_reachability_differences": scoring_reachable_diff,
            "red_flag_affecting_reachability_differences": red_flag_reachable_diff,
            "tokens_reachable_in_one_order_only": sorted(tokens_one_order_only),
            "question_identity_differences": dimensions["questionIdentitySequence"],
            "question_role_differences": dimensions["questionRoleSequence"],
            "truncation_differences": dimensions["truncationSet"],
            "required_skip_differences": dimensions["requiredSkipSemantics"],
            "groups_with_membership_differences": membership_differing_groups,
            "groups_with_mapping_differences": mapping_differing_groups,
            "all_clinical_dimensions_zero": clinical_zero,
            "why": (
                "The engine UNIONS additional-symptom options over the triggered tokens. A union "
                "is a set operation, so reversing the visit order changes the order options are "
                "appended in and nothing else. Every dimension that governs what a user can "
                "declare — membership, option-to-token mapping, reachable tokens, question set, "
                "roles, truncation and skip state — is identical in both orders across all "
                "%d comparisons." % total
            ),
            "consequences_ruled_out": {
                "can_change_reachable_tokens": False,
                "can_change_scoring_inputs": False,
                "can_change_ranked_conditions": False,
                "can_change_top_condition": False,
                "can_change_urgency": False,
                "can_change_red_flag_interruption": False,
                "can_change_path_length": False,
            },
        },
        "option_order_groups": groups,
    }
    return evidence, len(wording_groups)


def build_decision(evidence, wording_decision_count):
    evidence_bytes = dump_report_bytes(evidence)
    clinical = evidence["clinical_impact"]
    groups = evidence["option_order_groups"]

    return {
        "_metadata": {
            "report_id": "im001_option_order_decision",
            "version": "1",
            "phase": "I2 / W3 Step 5B",
            "generator": "tools/report_im001_option_ordering.py",
            "generator_version": QFLOW_TOOLING_VERSION,
            "authoritative": True,
            "note": (
                "ONE global Product decision covering every option-order contest. The %d "
                "contest groups are evidence, not %d approvals: they are all the same question "
                "and every clinical dimension is identical across all of them."
                % (len(groups), len(groups))
            ),
        },
        "evidence_binding": {
            "path": os.path.relpath(EVIDENCE_PATH, repo_path()),
            "sha256": sha256_bytes(evidence_bytes),
            "group_count": len(groups),
            "affected_path_count": sum(g["affected_path_count"] for g in groups),
            "note": "This decision is valid only against the evidence table with this exact hash. Regenerating the evidence regenerates the binding; a drifted hash fails validation.",
        },
        "decision": {
            "decision_id": "IM001-ORD-GLOBAL-001",
            "decision_type": "deterministic_option_ordering_rule",
            "status": "pending",
            "reviewer_role": "Product",
            "reviewer_identity": None,
            "review_date": None,
            "rationale": None,
            "selection": None,
            "candidate_rule_under_review": (
                "Within a grouped question, answer options are emitted in a declared "
                "deterministic order derived from the candidate's option ordering, rather than "
                "in the order the engine happened to visit the selected tokens."
            ),
            "baseline_behaviour": "Option order follows selected-token visitation order, so the same symptom set tapped in a different order yields a different option sequence.",
            "candidate_behaviour": "Deterministic ordering defined by Question Flow 1.1.",
            "affected_option_order_groups": len(groups),
            "affected_paths": sum(g["affected_path_count"] for g in groups),
            "option_membership_differences": clinical["option_membership_differences"],
            "reachable_token_differences": clinical["reachable_token_set_differences"],
            "scoring_affecting_differences": clinical["scoring_affecting_reachability_differences"],
            "red_flag_affecting_differences": clinical["red_flag_affecting_reachability_differences"],
            "clinical_review_required": False,
            "clinical_review_required_is_conditional": True,
            "clinical_review_condition": (
                "Product review alone is sufficient ONLY while option membership, "
                "option-to-token mapping, reachable tokens, scoring reachability and red-flag "
                "reachability all remain zero. If any becomes non-zero this classification is "
                "invalid, clinical review becomes mandatory, and validation fails."
            ),
            "activation_blocker": True,
            "activation_blocker_reason": "IM-001 stays blocked until this decision is approved.",
            "approval_authorizes": [
                "deterministic ordering of the same existing options within a grouped question",
            ],
            "approval_does_not_authorize": [
                "rewording any question",
                "adding an option",
                "removing an option",
                "changing an option-to-token mapping",
                "changing scoring, ranking or urgency",
                "changing any red-flag token, rule or trigger",
                "IM-003 adaptive re-branching",
                "publication of any candidate",
                "production or beta activation",
            ],
        },
        "im_001_gate": {
            "wording_decisions_pending": wording_decision_count,
            "ordering_rule_decisions_pending": 1,
            "total_product_decisions_required": wording_decision_count + 1,
            "im_001_resolved": False,
            "note": (
                "IM-001 requires %d Product decisions: %d wording selections plus one global "
                "ordering rule. The two are separate and neither is combined into the other."
                % (wording_decision_count + 1, wording_decision_count)
            ),
        },
    }


def apply_recorded_verdict(decision_report, wording_review):
    """I2/W3 Step 11: apply the recorded ORD-A verdict, if the authoritative
    verdict record exists. Approval of the ordering rule never approves
    wording, activation or publication — those stay false and validated."""
    verdicts_path = repo_path("reports", "im001_product_verdicts_v1.json")
    if not os.path.exists(verdicts_path):
        return decision_report
    record = load_json(verdicts_path)
    verdict = record["ordering_verdict"]
    if verdict["decision_id"] != "IM001-ORD-GLOBAL-001":
        raise SystemExit("FAIL verdict record names an unknown ordering decision")

    decision = decision_report["decision"]
    decision["status"] = "approved"
    decision["selection"] = verdict["selection"]
    decision["reviewer_identity"] = verdict["reviewer_name"]
    decision["reviewer_title"] = verdict["reviewer_title"]
    decision["reviewer_authority"] = verdict["authority"]
    decision["review_date"] = verdict["review_date"]
    decision["rationale"] = verdict["rationale"]
    decision["activation_blocker"] = False
    decision["activation_blocker_reason"] = (
        "The ordering decision is approved and no longer blocks. Activation "
        "remains UNAUTHORIZED regardless: approval authorizes deterministic "
        "ordering of the same options only, and activation, publication and "
        "Mobile implementation authorization are all false.")
    decision["activation_authorized"] = False
    decision["clinical_approval"] = False

    wording_pending = sum(1 for d in wording_review["decisions"]
                          if d["product_verdict"] == "PENDING")
    gate = decision_report["im_001_gate"]
    gate["wording_decisions_pending"] = wording_pending
    gate["ordering_rule_decisions_pending"] = 0
    gate["im_001_resolved"] = wording_pending == 0
    gate["activation_authorized"] = False
    gate["clinical_flags_open"] = [f["flag_id"] for f in record["clinical_flags"]]
    gate["note"] = (
        "All 136 Product decisions are recorded (135 wording + 1 ordering; "
        "reports/im001_product_verdicts_v1.json, 2026-08-24). im_001_resolved "
        "refers to the DECISION SET only: activation, publication and Mobile "
        "implementation remain unauthorized, and clinical flag "
        "IM001-CLIN-FLAG-001 must be reviewed by Clinical before any "
        "activation decision involving fast_breathing_child.severity.")
    return decision_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    evidence, wording_count = build()

    # Fail closed: a Product-only classification is only emitted when every
    # clinical dimension really is zero.
    if not evidence["clinical_impact"]["all_clinical_dimensions_zero"]:
        print("FAIL a clinically meaningful difference was found — Product-only "
              "classification is invalid and no decision was written")
        print(json.dumps(evidence["clinical_impact"], indent=2)[:1200])
        return 1
    if not evidence["reconciliation"]["all_counts_agree"]:
        disagreeing = {k: v for k, v in evidence["reconciliation"]["detail"].items()
                       if not v["agree"]}
        print("FAIL knowledge-base counts do not reconcile with Mobile evidence:")
        print(json.dumps(disagreeing, indent=2))
        return 1

    decision = build_decision(evidence, wording_count)
    decision = apply_recorded_verdict(decision, load_json(WORDING_REVIEW))
    outputs = [(EVIDENCE_PATH, evidence), (DECISION_PATH, decision)]

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
        print("OK   IM-001 option-ordering evidence and decision are current")
    else:
        print("  comparisons reconciled: %d" %
              evidence["primary_classification_mutually_exclusive"]["total"])
        print("  option-order groups:    %d" % len(evidence["option_order_groups"]))
        print("  wording decisions:      %d (unchanged)" % wording_count)
        print("  total Product decisions required: %d" %
              decision["im_001_gate"]["total_product_decisions_required"])
        print("  all clinical dimensions zero: %s" %
              evidence["clinical_impact"]["all_clinical_dimensions_zero"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
