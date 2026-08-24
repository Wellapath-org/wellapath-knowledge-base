#!/usr/bin/env python3
"""The IM-001 wording decisions Product has to sign off, and nothing else.

    python3 tools/report_im001_product_review.py            # build
    python3 tools/report_im001_product_review.py --check    # fail if stale

IM-001 is the last engineering-side blocker on candidate 1.1, and it is now a
narrow one: path CONTENT no longer changes — measured at zero over 2,325
captured paths — but on paths where the live engine's answer depends on the
order the user tapped, a deterministic rule has to pick ONE of the existing
wordings. Which one is a product call.

Handing Product 1,680 affected paths would be handing them a spreadsheet, not a
decision. The same handful of wording contests recur across those paths, so this
report collapses them into the DISTINCT decisions: for each, the wording the
candidate selects, the wordings it does not, and how many captured paths ride on
it.

No wording is added, removed or reworded here. Every candidate and alternative
is text that exists in the live app today.

Standard library only. No network.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.dartparse import parse_all
from qflow.grouping import live_effective_questions, plan_grouped
from report_question_grouping_parity import split_questions
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
    write_bytes,
)

CANDIDATE_PATH = repo_path("candidate", "question_flow.ng.v1.1.json")
ORACLE_PATH = repo_path("testing", "questions", "fixtures", "oracle",
                        "live_question_oracle_v1.json")
REPORT_PATH = repo_path("reports", "im001_product_review_v1_1.json")
GENERATOR = "tools/report_im001_product_review.py"


def build_report():
    candidate = load_json(CANDIDATE_PATH)
    oracle = load_json(ORACLE_PATH)
    parsed = parse_all(repo_path())
    followup_map = {
        token: [{"type": e["type"], "question_text": e["question_text"],
                 "options": list(e["options"])} for e in entries]
        for token, entries in parsed["followup_question_map"]["entries"].items()
    }
    default_question = parsed["followup_question_map"]["default_question"]
    clarifiers = parsed["red_flag_clarifiers"]
    grouped, clarifier_questions, default = split_questions(candidate)

    # Which source supplies which wording, per group.
    source_text = {
        q["grouping"]["group_key"]: {
            s["source_id"]: (s["source_token"], s["source_text"],
                             s["source_order_index"])
            for s in q["grouping"]["sources"]
        }
        for q in grouped
    }

    decisions = {}
    unstable_paths = 0
    forward_live = {tuple(sorted(c["input_tokens"])): c for c in oracle["forward"]}

    for case in oracle["reversed"]:
        key = tuple(sorted(case["input_tokens"]))
        forward = forward_live[key]
        forward_words = [q["question_text"] for q in forward["questions"]]
        reversed_words = [q["question_text"] for q in case["questions"]]
        if forward_words == reversed_words:
            continue
        unstable_paths += 1

        planned, _ = plan_grouped(case["input_tokens"], grouped,
                                  clarifier_questions, default)
        by_role_forward = {q["role"]: q["question_text"] for q in forward["questions"]}
        by_role_reversed = {q["role"]: q["question_text"] for q in case["questions"]}

        for question in planned:
            role = question["role"]
            if role not in source_text:
                continue
            chosen = question["question_text"]
            alternatives = {by_role_forward.get(role), by_role_reversed.get(role)}
            alternatives.discard(chosen)
            alternatives.discard(None)
            if not alternatives:
                continue
            decision_key = (role, chosen, tuple(sorted(alternatives)))
            entry = decisions.setdefault(decision_key, {
                "clinical_role": role,
                "selected_wording": chosen,
                "selected_source": question.get("representative_source"),
                "rejected_wordings": sorted(alternatives),
                "captured_paths_affected": 0,
                "example_selections": [],
            })
            entry["captured_paths_affected"] += 1
            if len(entry["example_selections"]) < 3:
                entry["example_selections"].append(sorted(case["input_tokens"]))

    ordered = sorted(decisions.values(),
                     key=lambda d: (-d["captured_paths_affected"],
                                    d["clinical_role"], d["selected_wording"]))
    for index, decision in enumerate(ordered, start=1):
        decision["decision_id"] = "IM001-D%03d" % index
        decision["product_verdict"] = "PENDING"
        decision["product_reviewer"] = None
        decision["review_date"] = None

    # I2/W3 Step 11: apply the recorded Product verdicts, if the authoritative
    # verdict record exists. Only stable fields identify decisions; a verdict
    # that names an unknown decision, or leaves any decision unrecorded, is a
    # hard failure rather than a partial write.
    verdicts_path = repo_path("reports", "im001_product_verdicts_v1.json")
    sign_off_recorded = False
    if os.path.exists(verdicts_path):
        verdict_record = load_json(verdicts_path)
        by_id = {v["decision_id"]: v for v in verdict_record["wording_verdicts"]}
        unknown = sorted(set(by_id) - {d["decision_id"] for d in ordered})
        missing = sorted({d["decision_id"] for d in ordered} - set(by_id))
        if unknown or missing:
            raise SystemExit("FAIL verdict record does not match decisions: "
                             "unknown=%s missing=%s" % (unknown[:3], missing[:3]))
        for decision in ordered:
            verdict = by_id[decision["decision_id"]]
            if verdict["approved_wording"] != decision["selected_wording"]:
                raise SystemExit("FAIL %s: approved wording disagrees with the "
                                 "artifact" % decision["decision_id"])
            decision["product_verdict"] = "APPROVED"
            decision["product_selection"] = verdict["selection"]
            decision["product_rationale"] = verdict["rationale"]
            decision["product_reviewer"] = verdict["reviewer_name"]
            decision["product_reviewer_title"] = verdict["reviewer_title"]
            decision["product_authority"] = verdict["authority"]
            decision["review_date"] = verdict["review_date"]
            if "clinical_flag" in verdict:
                decision["clinical_flag"] = verdict["clinical_flag"]
        sign_off_recorded = True

    return {
        "_metadata": {
            "report_id": "im001_product_review",
            "version": "1.1",
            "generator": GENERATOR,
            "candidate": {
                "path": "candidate/question_flow.ng.v1.1.json",
                "sha256": sha256_file(CANDIDATE_PATH),
                "version": candidate["_metadata"]["version"],
            },
            "oracle": {
                "path": "testing/questions/fixtures/oracle/live_question_oracle_v1.json",
                "sha256": sha256_file(ORACLE_PATH),
                "evidence_class": "CAPTURED_DART",
            },
            "what_product_is_being_asked": (
                "For each decision below, confirm the selected wording is the right one "
                "to show. Every wording listed — selected and rejected alike — already "
                "exists in the live app; the live engine shows one or the other "
                "depending on the order the user tapped their symptoms."
            ),
            "what_product_is_NOT_being_asked": (
                "Not to approve question CONTENT — that is a separate clinical and "
                "content review, still outstanding, and `content_approved` is false "
                "throughout. Not to approve publication. Not to approve activation."
            ),
            "selection_rule_under_review": (
                "lowest_source_order_index — among the sources whose token was "
                "selected, the wording belonging to the alphabetically first canonical "
                "token id. Deterministic and independent of tap order. Accepted as the "
                "ENGINEERING proposal; this report is the product half."
            ),
        },
        "scope": {
            "captured_reversed_paths": len(oracle["reversed"]),
            "paths_where_live_is_order_dependent": unstable_paths,
            "distinct_wording_decisions": len(ordered),
            "note": (
                "%d affected paths collapse to %d distinct decisions, because the same "
                "wording contests recur. Reviewing the decisions covers every path."
                % (unstable_paths, len(ordered))
            ),
        },
        "invariants_not_under_review": {
            "question_set_changes": 0,
            "option_set_changes": 0,
            "token_effect_changes": 0,
            "red_flag_effect_changes": 0,
            "truncation_changes": 0,
            "basis": "reports/question_grouping_parity_v1_1.json, 2,325 captured paths.",
        },
        "decisions": ordered,
        "sign_off": (
            {
                "status": "COMPLETE",
                "reviewer": "Ayodele John Oluwaseyi",
                "reviewer_title": "Co-Founder & CEO, WellaPath",
                "authority": "product",
                "review_date": "2026-08-24",
                "blocks_activation": False,
                "activation_authorized": False,
                "clinical_approval": False,
                "note": (
                    "All 135 wording decisions carry Product verdicts, recorded "
                    "2026-08-24 from the Step 11 reconciliation "
                    "(reports/im001_product_verdicts_v1.json). The IM-001 wording "
                    "decision set no longer blocks activation, but NOTHING here "
                    "authorizes activation: publication and activation "
                    "authorization remain false, candidate 1.1 remains unpublished "
                    "and inactive, and clinical flag IM001-CLIN-FLAG-001 "
                    "(fast_breathing_child.severity, IM001-D018/D027) requires "
                    "Clinical review before any activation decision involving "
                    "that question."
                ),
            } if sign_off_recorded else {
                "status": "PENDING",
                "reviewer": None,
                "review_date": None,
                "blocks_activation": True,
                "note": (
                    "Until every decision carries a product_verdict, IM-001 remains an "
                    "activation blocker. Merging candidate 1.1 into the knowledge base does "
                    "not change that: the artifact is an engineering contract, not a "
                    "release."
                ),
            }
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report = build_report()
    payload = dump_artifact_bytes(report)

    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/im001_product_review_v1_1.json is missing or stale")
            return 1
        print("OK   IM-001 product review report is reproducible, sha256:%s"
              % sha256_bytes(payload))
        return 0

    write_bytes(REPORT_PATH, payload)
    scope = report["scope"]
    print("wrote reports/im001_product_review_v1_1.json")
    print("  order-dependent captured paths: %d of %d"
          % (scope["paths_where_live_is_order_dependent"],
             scope["captured_reversed_paths"]))
    print("  distinct wording decisions:     %d" % scope["distinct_wording_decisions"])
    for decision in report["decisions"][:8]:
        print("    %s  %-20s %4d paths" % (decision["decision_id"],
                                           decision["clinical_role"],
                                           decision["captured_paths_affected"]))
        print("        selects : %s" % decision["selected_wording"])
        for rejected in decision["rejected_wordings"]:
            print("        not     : %s" % rejected)
    if len(report["decisions"]) > 8:
        print("    … %d more" % (len(report["decisions"]) - 8))
    return 0


if __name__ == "__main__":
    sys.exit(main())
