#!/usr/bin/env python3
"""Reproduce the CB_211 / CB_225 / CB_232 / CB_233 case-bank findings.

    python3 tools/report_case_findings.py            # write reports/case_findings_v1.json
    python3 tools/report_case_findings.py --check     # fail if the report is stale

WHAT THIS IS
------------
An *evidence model*, not an engine. It reimplements the arithmetic of
`ScoringEngine.score` (wellapath-mobile lib/core/engine/scoring_engine.dart) for
the narrow slice the four findings occupy — no demographic tokens, no season —
so that the numbers in the decision packages are reproducible from this
repository instead of being copied out of a run log.

WHAT THIS IS NOT
----------------
It is NOT a second CDSS engine and must never be used to certify clinical
behaviour. Scoring executes on-device in Dart; that implementation is
authoritative. This model deliberately covers only the four cases below, and
`model_limitations` in the output records exactly what it does not implement.
Agreement between this model and the Mobile run is corroboration, not proof.

The model is validated against the Mobile run in the output: every case carries
`model_matches_mobile_actual`, and the script exits non-zero if any of them is
false. If the model and the real engine ever disagree, that is a finding about
the model and this report must not be trusted until it is resolved.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

REPORT_PATH = repo_path("reports", "case_findings_v1.json")

CASE_BANK = "testing/case_bank_v1.json"
CASE_BANK_SHA256 = "c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834"

CASES = ["CB_211", "CB_225", "CB_232", "CB_233"]

# Observed output of the Mobile 239-case run (PR #71, head 04dcf75) against
# token_dictionary 1.1 / kb 2.4 / rules 2.2. Recorded here so the model can be
# checked against the real engine rather than asserted to agree with it.
MOBILE_ACTUAL = {
    "CB_211": {"urgency": "urgent", "urgency_source": "urgency_default", "top_condition": "malaria"},
    "CB_225": {"urgency": "urgent", "urgency_source": "urgency_default", "top_condition": "malaria"},
    "CB_232": {"urgency": "urgent", "urgency_source": "urgency_default", "top_condition": "malaria"},
    "CB_233": {"urgency": "urgent", "urgency_source": "urgency_default", "top_condition": "cardio_symptoms"},
}

# The complete set of urgencySource values the engine emits, taken from the
# doc comment on EngineOutput.urgencySource and confirmed against every
# historical revision of urgency_determiner.dart.
ENGINE_URGENCY_SOURCES = [
    "global_red_flag",
    "condition_specific_red_flag",
    "demographic_escalation",
    "urgency_default",
]


def score_conditions(conditions, tokens):
    """Port of ScoringEngine.score for demographics=[] and season=None.

    score = base_weight + sum(weights of matched symptoms) + modifier_points,
    with modifier_points necessarily 0 here: demographic modifiers only fire
    when the modifier token is in candidateConditionIds, and seasonal modifiers
    only fire when currentSeason is non-null. All four cases supply neither.
    """
    selected = set(tokens)
    scored = []
    for condition in conditions:
        matched = [
            (s["token"], s["weight"]) for s in condition["symptoms"] if s["token"] in selected
        ]
        symptom_score = sum(w for _, w in matched)
        scored.append(
            {
                "condition_id": condition["condition_id"],
                "base_weight": condition["base_weight"],
                "matched_symptom_score": symptom_score,
                "total_score": condition["base_weight"] + symptom_score,
                "matched_symptoms": [{"token": t, "weight": w} for t, w in matched],
                "urgency_default": condition["urgency_default"],
            }
        )
    scored.sort(key=lambda c: -c["total_score"])
    return scored


def red_flag_analysis(rules, tokens, top_condition_id):
    selected = set(tokens)
    global_tokens = {r["token"] for r in rules if r["applies_to"] == ["all"]}
    condition_tokens = set()
    for rule in rules:
        if rule["applies_to"] != ["all"] and top_condition_id in rule["applies_to"]:
            condition_tokens.add(rule["token"])
    return {
        "global_red_flag_tokens_present": sorted(selected & global_tokens),
        "condition_specific_red_flag_tokens_present": sorted(selected & condition_tokens),
        "red_flag_triggered": bool((selected & global_tokens) or (selected & condition_tokens)),
    }


def analyse(case, conditions, rules):
    tokens = case["input_tokens"]
    scored = score_conditions(conditions, tokens)
    top = scored[0]
    top_score = top["total_score"]
    tied = [c for c in scored if c["total_score"] == top_score]

    kb_order = {c["condition_id"]: i for i, c in enumerate(conditions)}

    model = {
        "top_condition": top["condition_id"],
        "urgency": top["urgency_default"],
        # Priority 5 is the only reachable path: no red flag fires and no
        # demographic token is supplied, so UrgencyDeterminer falls through to
        # the top condition's urgency_default.
        "urgency_source": "urgency_default",
    }

    return {
        "case_id": case["case_id"],
        "description": case["description"],
        "input_tokens": tokens,
        "demographic_tokens": case["demographic_tokens"],
        "season": case["season"],
        "expected": {
            "urgency": case["expected_urgency"],
            "urgency_source": case["expected_urgency_source"],
            "top_condition": case["expected_top_condition"],
        },
        "case_bank_note": case.get("note"),
        "safety_critical": case["safety_critical"],
        "mobile_actual": MOBILE_ACTUAL[case["case_id"]],
        "model_result": model,
        "model_matches_mobile_actual": (
            model["top_condition"] == MOBILE_ACTUAL[case["case_id"]]["top_condition"]
            and model["urgency"] == MOBILE_ACTUAL[case["case_id"]]["urgency"]
            and model["urgency_source"] == MOBILE_ACTUAL[case["case_id"]]["urgency_source"]
        ),
        "red_flags": red_flag_analysis(rules, tokens, top["condition_id"]),
        "demographic_escalation_applies": bool(case["demographic_tokens"]),
        "ranking": {
            "top_score": top_score,
            "runner_up_score": scored[1]["total_score"] if len(scored) > 1 else None,
            "margin_over_runner_up": (
                top_score - scored[1]["total_score"] if len(scored) > 1 else None
            ),
            "conditions_tied_at_top": len(tied),
            "tie_break_required": len(tied) > 1,
            "tied_condition_ids": [c["condition_id"] for c in tied] if len(tied) > 1 else [],
            "tied_kb_array_positions": (
                {c["condition_id"]: kb_order[c["condition_id"]] for c in tied}
                if len(tied) > 1
                else {}
            ),
            "top_10": scored[:10],
        },
    }


def kb_version_delta(case, kb_new, kb_old):
    """Did this case behave differently under the previous KB version?"""
    new = score_conditions(kb_new, case["input_tokens"])
    old = score_conditions(kb_old, case["input_tokens"])
    return {
        "kb_2_4_top": {"condition_id": new[0]["condition_id"], "score": new[0]["total_score"],
                       "urgency_default": new[0]["urgency_default"]},
        "kb_2_3_top": {"condition_id": old[0]["condition_id"], "score": old[0]["total_score"],
                       "urgency_default": old[0]["urgency_default"]},
        "ranking_identical": [c["condition_id"] for c in new] == [c["condition_id"] for c in old],
        "scores_identical": [c["total_score"] for c in new] == [c["total_score"] for c in old],
        "changed_between_2_3_and_2_4": not (
            [c["condition_id"] for c in new] == [c["condition_id"] for c in old]
            and [c["total_score"] for c in new] == [c["total_score"] for c in old]
        ),
    }


def build_report():
    bank = load_json(repo_path(CASE_BANK))
    by_id = {c["case_id"]: c for c in bank["cases"]}
    kb24 = load_json(repo_path("kb.ng.v2.4.json"))["conditions"]
    kb23 = load_json(repo_path("kb.ng.v2.3.json"))["conditions"]
    rules = load_json(repo_path("rules.ng.v2.2.json"))["rules"]

    findings = []
    for case_id in CASES:
        entry = analyse(by_id[case_id], kb24, rules)
        entry["kb_version_delta"] = kb_version_delta(by_id[case_id], kb24, kb23)
        findings.append(entry)

    prior = load_json(repo_path("testing", "case_bank_results_v1.json"))
    prior_cb211 = next(
        (r for r in prior["as_shipped"]["results"] if r["case_id"] == "CB_211"), None
    )

    return {
        "report_id": "case_findings",
        "report_version": "1",
        "phase": "I2 / W2 Step 3",
        "generator": "tools/report_case_findings.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "purpose": "Reproduce the four case-bank findings from the authoritative artifacts so the decision packages cite computed evidence rather than a run log.",
        "model_status": {
            "is_an_engine": False,
            "authoritative_engine": "wellapath-mobile lib/core/engine/ (Dart, on-device)",
            "may_be_used_to_certify_clinical_behaviour": False,
            "model_limitations": [
                "Implements only base_weight + matched symptom weights. Demographic and seasonal modifier points are not implemented — none of the four cases supplies a demographic token or a season, so they contribute 0.",
                "Does not implement red-flag evaluation ordering; it reports which red-flag tokens are present and confirms none are.",
                "Does not implement UrgencyDeterminer priorities 1-4; it asserts priority 5 (urgency_default) is the only reachable path for these four cases and shows why.",
                "Ties are reported but not broken: Dart List.sort is not a stable sort, so a tie has no defined winner. None of the four cases ties.",
            ],
        },
        "authoritative_inputs": {
            "case_bank": {
                "file": CASE_BANK,
                "version": bank["_metadata"]["version"],
                "sha256": sha256_file(repo_path(CASE_BANK)),
                "sha256_matches_authoritative": sha256_file(repo_path(CASE_BANK)) == CASE_BANK_SHA256,
                "total_cases": len(bank["cases"]),
            },
            "knowledge_base": {"file": "kb.ng.v2.4.json", "sha256": sha256_file(repo_path("kb.ng.v2.4.json"))},
            "rules": {"file": "rules.ng.v2.2.json", "sha256": sha256_file(repo_path("rules.ng.v2.2.json"))},
            "token_dictionary": {"file": "token_dictionary.ng.v1.1.json", "sha256": sha256_file(repo_path("token_dictionary.ng.v1.1.json"))},
        },
        "mobile_run": {
            "pr": 71,
            "branch": "test/i2-w2-case-bank-239",
            "head": "04dcf75",
            "base": "678e300",
            "executed": 239,
            "passed": 235,
            "failed": 1,
            "human_review": 3,
            "safety_critical_under_triage": 0,
            "merged": False,
        },
        "engine_urgency_source_contract": {
            "values": ENGINE_URGENCY_SOURCES,
            "source": "wellapath-mobile lib/core/engine/models/engine_output.dart, doc comment on EngineOutput.urgencySource",
            "confirmed_against": "all 5 historical revisions of lib/core/engine/urgency_determiner.dart (e20f45a, 51afd89, 7aeb13c, cfe1a25, 33a214e) and every commit touching lib/",
            "empty_default_present": "empty_default" in ENGINE_URGENCY_SOURCES,
        },
        "cb_211_prior_run": {
            "results_file": "testing/case_bank_results_v1.json",
            "run_size": prior["as_shipped"]["summary"]["total_cases"],
            "knowledge_base": prior["run_metadata"]["artifacts"]["knowledge_base"],
            "rules": prior["run_metadata"]["artifacts"]["rules"],
            "record": prior_cb211,
            "identical_to_current_run": bool(
                prior_cb211
                and prior_cb211["actual_urgency"] == MOBILE_ACTUAL["CB_211"]["urgency"]
                and prior_cb211["actual_urgency_source"] == MOBILE_ACTUAL["CB_211"]["urgency_source"]
                and prior_cb211["actual_top_condition"] == MOBILE_ACTUAL["CB_211"]["top_condition"]
            ),
        },
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report = build_report()

    # Fail closed: if the evidence model disagrees with the real engine, or the
    # fixture is not the authoritative one, the report is not trustworthy.
    problems = []
    if not report["authoritative_inputs"]["case_bank"]["sha256_matches_authoritative"]:
        problems.append("case bank SHA256 does not match the authoritative fixture")
    for finding in report["findings"]:
        if not finding["model_matches_mobile_actual"]:
            problems.append("model disagrees with the Mobile run for %s" % finding["case_id"])
    if problems:
        for problem in problems:
            print("FAIL %s" % problem)
        return 1

    payload = dump_report_bytes(report)

    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/case_findings_v1.json is missing or stale")
            return 1
        print("OK   case findings report is current")
        return 0

    write_bytes(REPORT_PATH, payload)
    print("wrote reports/case_findings_v1.json")
    for finding in report["findings"]:
        ranking = finding["ranking"]
        print(
            "  %s  model=%s/%s  mobile=%s/%s  match=%s  margin=%s  tie=%s"
            % (
                finding["case_id"],
                finding["model_result"]["top_condition"],
                finding["model_result"]["urgency"],
                finding["mobile_actual"]["top_condition"],
                finding["mobile_actual"]["urgency"],
                finding["model_matches_mobile_actual"],
                ranking["margin_over_runner_up"],
                ranking["tie_break_required"],
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
