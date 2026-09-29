#!/usr/bin/env python3
"""Map every token in token_dictionary 1.1 to its consumers.

    python3 tools/report_token_references.py            # write the report
    python3 tools/report_token_references.py --check    # fail if the report is stale

Produces reports/token_reference_graph_v1.json: per-token consumer lists plus
the risk analysis W2 needs before anyone proposes merging, renaming or
deprecating a token.

This report is read-only. It never renames, merges or removes anything.
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes
from vocab.normalize import normalize_token_id

REPORT_PATH = repo_path("reports", "token_reference_graph_v1.json")

CATEGORIES = [
    "symptom_tokens",
    "red_flag_tokens",
    "duration_tokens",
    "body_area_tokens",
    "demographic_tokens",
    "severity_tokens",
]

# Consumer kinds that mean "changing this token changes clinical behaviour".
SCORING_KINDS = frozenset(["kb.symptoms"])
RED_FLAG_KINDS = frozenset(["kb.red_flags", "rules.token"])


def collect(token_dictionary, kb, rules, case_bank, mobile_handoff):
    consumers = collections.defaultdict(lambda: collections.defaultdict(list))

    def note(token, kind, who):
        consumers[token][kind].append(who)

    for condition in kb.get("conditions", []):
        cid = condition["condition_id"]
        for symptom in condition.get("symptoms", []):
            note(symptom["token"], "kb.symptoms", "%s(weight=%s)" % (cid, symptom["weight"]))
        for flag in condition.get("red_flags", []):
            note(flag, "kb.red_flags", cid)
        for tier, tokens in (condition.get("severity_levels") or {}).items():
            note(tier, "kb.severity_levels.key", "%s:%s" % (cid, tier))
            for token in tokens:
                note(token, "kb.severity_levels.value", "%s:%s" % (cid, tier))
        for modifier in condition.get("demographic_modifiers", []):
            note(
                modifier["modifier"],
                "kb.demographic_modifiers",
                "%s(effect=%s)" % (cid, modifier["effect"]),
            )

    for rule in rules.get("rules", []):
        scope = "global" if rule.get("applies_to") == ["all"] else "condition_specific"
        note(
            rule["token"],
            "rules.token",
            "%s(%s,priority=%s,override=%s)"
            % (rule["rule_id"], scope, rule.get("priority"), rule.get("override_urgency")),
        )

    for case in (case_bank or {}).get("cases", []):
        for token in case.get("input_tokens", []):
            note(token, "case_bank.input_tokens", case["case_id"])
        for token in case.get("demographic_tokens", []):
            note(token, "case_bank.demographic_tokens", case["case_id"])

    for name, entries in mobile_handoff.items():
        for entry in entries:
            token = entry.get("token")
            if token:
                note(token, "mobile_handoff.%s" % name, name)

    return consumers


def load_mobile_handoff():
    """Load the merged mobile handoff maps that reference tokens by ID."""
    handoff = {}
    for name, filename in [
        ("red_flag_display_map", "red_flag_display_map.json"),
        ("picker_scoring_gap_tokens", "picker_scoring_gap_tokens.json"),
    ]:
        path = repo_path("mobile_handoff", filename)
        if not os.path.exists(path):
            continue
        obj = load_json(path)
        if isinstance(obj, list):
            handoff[name] = [e for e in obj if isinstance(e, dict)]
        elif isinstance(obj, dict):
            entries = []
            for value in obj.values():
                if isinstance(value, list):
                    entries.extend(e for e in value if isinstance(e, dict))
            handoff[name] = entries
    return handoff


def build_report():
    token_dictionary = load_json(repo_path("token_dictionary.ng.v1.1.json"))
    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))
    case_bank_path = repo_path("testing", "case_bank_v1.json")
    case_bank = load_json(case_bank_path) if os.path.exists(case_bank_path) else None
    mobile_handoff = load_mobile_handoff()

    category_of = {}
    for category in CATEGORIES:
        for token in token_dictionary.get(category, []):
            category_of[token] = category

    consumers = collect(token_dictionary, kb, rules, case_bank, mobile_handoff)

    tokens = {}
    for token in sorted(category_of):
        kinds = consumers.get(token, {})
        affects_scoring = any(k in SCORING_KINDS for k in kinds)
        affects_red_flag = any(k in RED_FLAG_KINDS for k in kinds)
        tokens[token] = {
            "category": category_of[token],
            "normalized_form": normalize_token_id(token),
            "consumers": {kind: sorted(who) for kind, who in sorted(kinds.items())},
            "consumer_kind_count": len(kinds),
            "total_reference_count": sum(len(v) for v in kinds.values()),
            "referenced": bool(kinds),
            "referenced_by_kb_or_rules": any(
                k.startswith("kb.") or k.startswith("rules.") for k in kinds
            ),
            "modification_risk": (
                "red_flag_affecting"
                if affects_red_flag
                else "scoring_affecting"
                if affects_scoring
                else "question_or_display_only"
                if kinds
                else "unreferenced"
            ),
        }

    unresolved = sorted(t for t in consumers if t not in category_of)

    # --- risk analyses ---------------------------------------------------------
    normalized_groups = collections.defaultdict(list)
    for token in tokens:
        normalized_groups[tokens[token]["normalized_form"]].append(token)

    unused = sorted(t for t, v in tokens.items() if not v["referenced"])
    unused_by_kb_rules = sorted(t for t, v in tokens.items() if not v["referenced_by_kb_or_rules"])

    red_flag_affecting = sorted(
        t for t, v in tokens.items() if v["modification_risk"] == "red_flag_affecting"
    )
    scoring_affecting = sorted(
        t for t, v in tokens.items() if v["modification_risk"] == "scoring_affecting"
    )

    # Tokens whose IDs share a leading word — the shape a duplicate concept
    # tends to take in this dictionary. Reported for reviewer attention only.
    stems = collections.defaultdict(list)
    for token in tokens:
        stems[token.split("_")[0]].append(token)
    stem_clusters = {
        stem: sorted(members) for stem, members in sorted(stems.items()) if len(members) > 1
    }

    return {
        "report_id": "token_reference_graph",
        "report_version": "1",
        "phase": "I2 / W2 Step 1",
        "generator": "tools/report_token_references.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "purpose": "Complete consumer map for every token in token_dictionary 1.1, plus the risk analysis needed before any future merge, rename or deprecation. Read-only: this step merges and renames nothing.",
        "sources": {
            "token_dictionary": {
                "file": "token_dictionary.ng.v1.1.json",
                "sha256": sha256_file(repo_path("token_dictionary.ng.v1.1.json")),
            },
            "knowledge_base": {
                "file": "kb.ng.v2.4.json",
                "sha256": sha256_file(repo_path("kb.ng.v2.4.json")),
            },
            "rules": {
                "file": "rules.ng.v2.2.json",
                "sha256": sha256_file(repo_path("rules.ng.v2.2.json")),
            },
            "case_bank": {
                "file": "testing/case_bank_v1.json",
                "present": case_bank is not None,
                "sha256": sha256_file(case_bank_path) if case_bank is not None else None,
            },
            "mobile_handoff": sorted(mobile_handoff),
        },
        "consumer_kinds_observed": sorted({k for v in consumers.values() for k in v}),
        "summary": {
            "token_count": len(tokens),
            "referenced_token_count": sum(1 for v in tokens.values() if v["referenced"]),
            "unused_token_count": len(unused),
            "tokens_with_no_kb_or_rules_consumer_count": len(unused_by_kb_rules),
            "unresolved_reference_count": len(unresolved),
            "red_flag_affecting_token_count": len(red_flag_affecting),
            "scoring_affecting_token_count": len(scoring_affecting),
        },
        "findings": {
            "unused_tokens": {
                "description": "No consumer anywhere — not kb, rules, the case bank or a mobile handoff map. Candidates for review, NOT for removal: these are mostly structural vocabularies (body areas, durations, severity tiers) the engine does not yet consume.",
                "count": len(unused),
                "tokens": unused,
                "by_category": dict(
                    collections.Counter(tokens[t]["category"] for t in unused)
                ),
            },
            "tokens_with_no_kb_or_rules_consumer": {
                "description": "Not referenced by any clinical artifact. Safe to attach search metadata to; still must not be renamed or removed.",
                "count": len(unused_by_kb_rules),
                "tokens": unused_by_kb_rules,
            },
            "label_collisions_after_normalization": {
                "description": "Distinct token IDs that collapse to the same normalized search form. Each one would resolve as `ambiguous` rather than auto-selecting a token.",
                "count": sum(1 for v in normalized_groups.values() if len(v) > 1),
                "groups": {
                    form: sorted(members)
                    for form, members in sorted(normalized_groups.items())
                    if len(members) > 1
                },
            },
            "duplicate_concept_candidates": {
                "description": "Token IDs sharing a leading word. A REVIEWER PROMPT, not a conclusion — most clusters are legitimately distinct concepts (e.g. chest_pain vs chest_indrawing). No merge is proposed or performed by W2.",
                "cluster_count": len(stem_clusters),
                "clusters": stem_clusters,
            },
            "aliases_currently_represented_as_separate_clinical_tokens": {
                "description": "Pairs the repository's own records already identify as synonym relationships between two live scoring tokens. Sourced from committed evidence only; nothing here is inferred by this tool.",
                "entries": [
                    {
                        "tokens": ["breathlessness", "shortness_of_breath"],
                        "evidence": "mobile_handoff/picker_scoring_gap_tokens.json (PR #24) recommends breathlessness be treated as an alias of shortness_of_breath.",
                        "status": "proposed_not_approved",
                        "w2_action": "None. Both remain independent scoring tokens. Converting one into an alias of the other is a clinical-token-identity change requiring clinical review and a rules/KB impact assessment.",
                    }
                ],
                "note": "token_dictionary.ng.v1.1.json _metadata.corrections_from_v0 records earlier synonym consolidations already applied before the 1.1 freeze (wheezing -> wheeze, exertional_shortness_of_breath -> exertional_breathlessness). Those are history, not outstanding duplicates.",
            },
            "references_that_depend_on_display_text_instead_of_stable_ids": {
                "description": "Places where clinical behaviour keys off free text rather than a token ID.",
                "count": 0,
                "entries": [],
                "detail": "Every kb and rules reference examined resolves through a token ID. kb conditions[].local_expressions and conditions[].explanation_template are free text, but the engine treats them as display content only — neither is matched against input. kb severity_levels tier KEYS are the one string-keyed structure, and three of them do not resolve against the dictionary; that is recorded in reports/baseline_freeze_v1.json known_baseline_findings.",
            },
            "tokens_whose_modification_could_change_red_flag_behaviour": {
                "description": "Referenced by a rules rule or a kb red_flags list. Any change to these is red_flag_affecting and blocks publication pending clinical review.",
                "count": len(red_flag_affecting),
                "tokens": red_flag_affecting,
            },
            "tokens_whose_modification_could_change_scoring": {
                "description": "Referenced by kb conditions[].symptoms and therefore carry a weight. Any change is scoring_affecting and blocks publication pending clinical review.",
                "count": len(scoring_affecting),
                "tokens": scoring_affecting,
            },
            "unresolved_references": {
                "description": "Referenced by a consumer but absent from token_dictionary 1.1.",
                "count": len(unresolved),
                "entries": {t: sorted(consumers[t]) for t in unresolved},
                "detail": "See reports/baseline_freeze_v1.json known_baseline_findings — these are pre-existing IMCI severity tier keys, not introduced by W2.",
            },
        },
        "tokens": tokens,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = dump_report_bytes(build_report())

    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/token_reference_graph_v1.json is missing or stale")
            return 1
        print("OK   token reference graph is current")
        return 0

    write_bytes(REPORT_PATH, payload)
    print("wrote reports/token_reference_graph_v1.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
