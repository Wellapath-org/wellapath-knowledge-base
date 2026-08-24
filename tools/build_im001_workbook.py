#!/usr/bin/env python3
"""Build the IM-001 Product decision workbook (I2/W3 Step 10).

    python3 tools/build_im001_workbook.py            # write
    python3 tools/build_im001_workbook.py --check    # fail if stale

Derives, deterministically and only from the authoritative merged artifacts:

  reports/im001_product_review_v1_1.json      (135 wording decisions)
  reports/im001_option_order_decision_v1.json (IM001-ORD-GLOBAL-001)
  reports/im001_option_order_evidence_v1.json (903 groups, 21 dimensions)

three review artifacts under review/im001_workbook_v1/:

  im001_workbook_v1.json          — the full machine-readable workbook
  im001_decision_template_v1.json — the fill-in template for recording verdicts
  IM001_DECISION_WORKBOOK.md      — the human review document

The workbook PRESENTS the 136 pending Product decisions; it decides none of
them. Every reviewer field is emitted null/PENDING. Grouping is by question
slot (token + follow-up kind): each slot has exactly one candidate-selected
wording contested against N alternatives, so a slot batch cannot contain
conflicting alternatives; the tool refuses to write if that ever stops being
true. Batch approval expands to the explicit member decision IDs — nothing is
approved implicitly and no decision disappears.

Fail-closed: refuses to write if the source counts, pending statuses,
clinical-impact zeros, 21-dimension reconciliation or evidence bindings differ
from the verified baseline.
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

REVIEW = repo_path("reports", "im001_product_review_v1_1.json")
ORDER_DECISION = repo_path("reports", "im001_option_order_decision_v1.json")
ORDER_EVIDENCE = repo_path("reports", "im001_option_order_evidence_v1.json")

OUT_DIR = repo_path("review", "im001_workbook_v1")
WORKBOOK = os.path.join(OUT_DIR, "im001_workbook_v1.json")
TEMPLATE = os.path.join(OUT_DIR, "im001_decision_template_v1.json")
DOC = os.path.join(OUT_DIR, "IM001_DECISION_WORKBOOK.md")

INTENDED_REVIEWER = {
    "name": "Ayodele John Oluwaseyi",
    "title": "Co-Founder & CEO, WellaPath",
    "role": "Product reviewer",
}

BOUNDARIES = {
    "review_authority": "Product review only",
    "clinical_approval_granted": False,
    "clinical_approval_required_for_measured_display_only_differences": False,
    "classification_is_conditional": (
        "Product-only review remains valid ONLY while option membership, "
        "option-to-token mapping, reachable tokens, scoring reachability and "
        "red-flag reachability differences all stay zero. Any future nonzero "
        "value in any of those dimensions reopens Clinical review and "
        "invalidates this workbook's classification."),
    "approval_does_not": [
        "publish candidate 1.1",
        "activate candidate 1.1 in any environment",
        "authorize Mobile implementation",
        "approve, alter or unblock IM-003 or IM003-SB-001 (outside this review)",
        "authorize merging Mobile PR #76",
    ],
    "im003_status": "IM-003 remains DISABLED and IM003-SB-001 remains OPEN; "
                    "both are outside the scope of this workbook.",
    "mobile_pr_76": "remains unauthorized to merge",
}


def humanize(token):
    return token.replace("_", " ")


def slot_of(decision):
    parts = decision["selected_source"].split(".")
    return parts[1], parts[2]  # (token, kind)


def wording_pattern(decision):
    """A display-only pattern family index; never a grouping mechanism."""
    token, _ = slot_of(decision)
    wording = decision["selected_wording"]
    label = humanize(token)
    lowered = wording.lower()
    if label in lowered:
        i = lowered.index(label)
        return wording[:i] + "{symptom}" + wording[i + len(label):]
    return "(irregular) " + wording


def build():
    review = load_json(REVIEW)
    order_decision = load_json(ORDER_DECISION)
    order_evidence = load_json(ORDER_EVIDENCE)
    decisions = review["decisions"]
    global_d = order_decision["decision"]
    impact = order_evidence["clinical_impact"]
    recon = order_evidence["reconciliation"]

    # --- refuse to build against a drifted baseline ---------------------------
    preconditions = {
        "wording_decisions_are_135": len(decisions) == 135,
        "all_wording_pending": all(d["product_verdict"] == "PENDING"
                                   and d["product_reviewer"] is None
                                   for d in decisions),
        "global_decision_pending": (global_d["decision_id"] == "IM001-ORD-GLOBAL-001"
                                    and global_d["status"] == "pending"),
        "im001_unresolved": (order_decision["im_001_gate"]["im_001_resolved"] is False
                             and review["sign_off"]["status"] == "PENDING"
                             and review["sign_off"]["blocks_activation"] is True),
        "clinical_impact_all_zero": impact["all_clinical_dimensions_zero"] is True,
        "reconciliation_21_dimensions_agree": (
            len(recon["detail"]) == 21 and recon["all_counts_agree"] is True
            and all(v["agree"] is True for v in recon["detail"].values())),
        "evidence_binding_intact": (order_decision["evidence_binding"]["sha256"]
                                    == sha256_file(ORDER_EVIDENCE)),
        "one_selected_wording_per_slot": all(
            len({d["selected_wording"] for d in group}) == 1
            for group in _by_slot(decisions).values()),
    }
    if not all(preconditions.values()):
        return None, None, None, preconditions

    # --- per-decision items ----------------------------------------------------
    items = []
    for d in decisions:
        token, kind = slot_of(d)
        items.append({
            "decision_id": d["decision_id"],
            "question_role": d["clinical_role"],
            "trigger_token": token,
            "question_slot": "%s.%s" % (token, kind),
            "candidate_selected_wording": d["selected_wording"],
            "selected_source": d["selected_source"],
            "alternative_wordings": list(d["rejected_wordings"]),
            "wording_pattern_family": wording_pattern(d),
            "captured_paths_affected": d["captured_paths_affected"],
            "representative_paths": d["example_selections"],
            "option_display_order_also_differs_within_this_question": False,
            "option_order_note": (
                "All 903 measured option-order groups are additional_symptoms "
                "questions; no duration or severity question has an option-"
                "order difference. Option-order instability on the captured "
                "paths is governed separately by IM001-ORD-GLOBAL-001."),
            "status": "PENDING",
            "reviewer_selection": None,
            "reviewer_selection_options": [
                "keep_candidate_wording", "use_alternative_wording", "defer"],
            "reviewer_rationale": None,
            "reviewer_name": None,
            "reviewer_title": None,
            "review_date": None,
            "evidence_binding": {
                "artifact": "reports/im001_product_review_v1_1.json",
                "decision_id": d["decision_id"],
            },
        })

    # --- slot batches ------------------------------------------------------------
    batches = []
    for (token, kind), group in sorted(_by_slot(decisions).items()):
        member_ids = sorted(d["decision_id"] for d in group)
        batches.append({
            "batch_id": "IM001-BATCH-%s-%s" % (kind.upper(), token),
            "section": "%s wording" % kind,
            "question_slot": "%s.%s" % (token, kind),
            "candidate_selected_wording": group[0]["selected_wording"],
            "member_decision_ids": member_ids,
            "member_count": len(member_ids),
            "distinct_alternatives": sorted(
                {w for d in group for w in d["rejected_wordings"]}),
            "total_captured_path_attributions": sum(
                d["captured_paths_affected"] for d in group),
            "path_attribution_note": (
                "Sum of per-decision counts; a captured path can appear under "
                "several decisions. A volume measure for prioritisation, not "
                "clinical importance."),
            "conflict_free_because": (
                "every member contests the SAME candidate wording against a "
                "different alternative; approving the batch approves one "
                "wording, once, for one question slot"),
            "batch_approval_expands_to": member_ids,
            "individual_override_allowed": True,
            "override_consistency_note": (
                "Overriding one member to an alternative wording while "
                "keeping siblings on the candidate wording leaves the slot "
                "with two wordings; the validator flags mixed verdicts within "
                "a slot for explicit confirmation."),
        })

    total_paths = {b["batch_id"]: b["total_captured_path_attributions"] for b in batches}
    priority = sorted(total_paths, key=lambda k: (-total_paths[k], k))

    # --- the global ordering decision -------------------------------------------
    global_section = {
        "decision_id": "IM001-ORD-GLOBAL-001",
        "presented_separately_because": (
            "It is one rule over 903 groups and 1,872 paths, not a wording "
            "choice; approving it does not touch any of the 135 wording "
            "decisions."),
        "plain_language": {
            "current_behaviour": (
                "Today, the order of answer options in the grouped additional-"
                "symptoms question can depend on the order the user tapped "
                "their symptoms. The same symptoms tapped in a different order "
                "can show the same options in a different sequence."),
            "candidate_behaviour": (
                "Candidate 1.1 always shows those options in one declared, "
                "deterministic order."),
            "what_is_unchanged": [
                "option membership (which options appear): unchanged",
                "option labels: unchanged",
                "option-to-token mappings: unchanged",
                "reachable scoring tokens: unchanged",
                "reachable red-flag tokens: unchanged",
            ],
            "what_this_affects": "display order only",
            "what_approval_does_not_do": (
                "Approving the ordering rule does not approve any of the 135 "
                "wording choices and does not activate or publish candidate "
                "1.1."),
        },
        "choices_mutually_exclusive": [
            {"choice_id": "ORD-A",
             "choice": "Approve candidate 1.1 deterministic option ordering."},
            {"choice_id": "ORD-B",
             "choice": "Retain current selection-order-dependent option ordering."},
            {"choice_id": "ORD-C",
             "choice": "Request a different deterministic ordering rule."},
        ],
        "status": "PENDING",
        "reviewer_selection": None,
        "reviewer_rationale": None,
        "reviewer_name": None,
        "reviewer_title": None,
        "review_date": None,
        "affected_option_order_groups": global_d["affected_option_order_groups"],
        "affected_paths": global_d["affected_paths"],
        "evidence_binding": {
            "artifact": "reports/im001_option_order_decision_v1.json",
            "decision_id": "IM001-ORD-GLOBAL-001",
            "evidence_sha256": order_decision["evidence_binding"]["sha256"],
        },
    }

    workbook = {
        "_metadata": {
            "artifact": "im001_workbook_v1",
            "phase": "I2/W3 Step 10",
            "generated_by": "tools/build_im001_workbook.py",
            "purpose": ("Compact Product review of all 136 pending IM-001 "
                        "decisions with one-to-one traceability to the "
                        "authoritative evidence. Presents decisions; decides "
                        "none of them."),
            "intended_reviewer": INTENDED_REVIEWER,
            "source_evidence": {
                "product_review": {"path": "reports/im001_product_review_v1_1.json",
                                   "sha256": sha256_file(REVIEW)},
                "order_decision": {"path": "reports/im001_option_order_decision_v1.json",
                                   "sha256": sha256_file(ORDER_DECISION)},
                "order_evidence": {"path": "reports/im001_option_order_evidence_v1.json",
                                   "sha256": sha256_file(ORDER_EVIDENCE)},
            },
            "raw_oracle_not_required": (
                "Every fact a reviewer needs is carried here or in the three "
                "source reports above; no 4 MB oracle inspection is required."),
        },
        "counts": {
            "original_wording_decisions": 135,
            "global_ordering_decisions": 1,
            "total_product_decisions": 136,
            "grouped_presentation_batches": len(batches),
            "grouped_presentation_units": len(batches) + 1,
            "grouping_hides_nothing": (
                "135 wording decisions are presented as %d slot batches plus "
                "1 separate global decision; every decision remains "
                "individually identifiable and individually overridable."
                % len(batches)),
        },
        "progress": {
            "reviewed": 0, "pending": 136, "deferred": 0,
            "wording_pending": 135, "ordering_pending": 1,
        },
        "clinical_impact_dimensions_all_zero": {
            k: impact[k] for k in (
                "option_membership_differences",
                "option_label_set_differences",
                "option_to_token_mapping_set_differences",
                "reachable_token_set_differences",
                "scoring_affecting_reachability_differences",
                "red_flag_affecting_reachability_differences",
                "question_identity_differences",
                "question_role_differences",
                "truncation_differences",
                "required_skip_differences")
        },
        "authorization_boundaries": BOUNDARIES,
        "batches": batches,
        "priority_by_path_volume": {
            "order": priority,
            "note": ("Sorted by captured-path attribution volume so the "
                     "reviewer can start where wording is seen most often. "
                     "Volume is presentation frequency, NOT clinical "
                     "importance; no clinical ranking is implied."),
        },
        "wording_pattern_families_index": _pattern_index(items),
        "decisions": items,
        "global_ordering_decision": global_section,
        "recording_instructions": {
            "individual": (
                "Set reviewer_selection to keep_candidate_wording, "
                "use_alternative_wording (and name the alternative in the "
                "rationale) or defer; fill reviewer_rationale, reviewer_name, "
                "reviewer_title and review_date on the item."),
            "batch": (
                "A batch approval means: record keep_candidate_wording, with "
                "one shared rationale, on EVERY member_decision_id listed in "
                "the batch — the expansion is this explicit list, nothing "
                "implicit. Any member may be individually overridden before "
                "or after."),
            "ordering": (
                "Record exactly one of ORD-A / ORD-B / ORD-C with rationale, "
                "name, title and date on the global ordering decision."),
            "template": "review/im001_workbook_v1/im001_decision_template_v1.json",
            "no_auto_approval": (
                "This workbook records no verdicts itself. All 136 decisions "
                "are emitted PENDING with null reviewer fields."),
        },
    }

    template = {
        "_metadata": {
            "artifact": "im001_decision_template_v1",
            "instructions": ("Fill reviewer fields; do not delete entries. "
                             "Entries left with verdict null remain PENDING."),
            "reviewer": INTENDED_REVIEWER,
            "workbook_binding": {"path": "review/im001_workbook_v1/im001_workbook_v1.json"},
        },
        "wording_verdicts": [
            {"decision_id": d["decision_id"], "verdict": None,
             "chosen_wording": None, "rationale": None,
             "reviewer_name": None, "reviewer_title": None, "review_date": None}
            for d in decisions
        ],
        "ordering_verdict": {
            "decision_id": "IM001-ORD-GLOBAL-001", "choice": None,
            "rationale": None, "reviewer_name": None, "reviewer_title": None,
            "review_date": None,
        },
    }
    return workbook, template, batches, preconditions


def _by_slot(decisions):
    by = collections.defaultdict(list)
    for d in decisions:
        by[slot_of(d)].append(d)
    return by


def _pattern_index(items):
    families = collections.defaultdict(list)
    for item in items:
        families[item["wording_pattern_family"]].append(item["decision_id"])
    return [{"pattern": p, "decision_ids": sorted(ids), "count": len(ids)}
            for p, ids in sorted(families.items(), key=lambda kv: (-len(kv[1]), kv[0]))]


def render_markdown(workbook):
    lines = []
    a = lines.append
    counts = workbook["counts"]
    a("# IM-001 Product Decision Workbook")
    a("")
    a("**Phase:** I2/W3 Step 10 · **Reviewer:** %s, %s · **Authority:** Product only"
      % (INTENDED_REVIEWER["name"], INTENDED_REVIEWER["title"]))
    a("")
    a("## Executive summary")
    a("")
    a("**136 Product decisions are pending: 135 wording choices + 1 global "
      "option-ordering rule.** Nothing else. Every measured clinical-impact "
      "dimension is **zero** — option membership, labels, token mappings, "
      "reachable tokens, scoring reachability and red-flag reachability are "
      "all identical between the live behaviour and candidate 1.1 — so these "
      "are display-wording and display-order choices, reviewable by Product "
      "alone *while those dimensions stay zero*.")
    a("")
    a("The 135 wording decisions collapse naturally into **%d question-slot "
      "batches**: each slot has exactly one candidate wording contested "
      "against several alternatives, so approving a batch approves one "
      "wording, once, for one question. Every one of the 135 remains "
      "individually listed and individually overridable below — grouping "
      "hides nothing. This workbook records **no verdicts**; all reviewer "
      "fields are blank." % counts["grouped_presentation_batches"])
    a("")
    a("| Progress | Count |")
    a("|---|---:|")
    a("| Reviewed | 0 |")
    a("| Pending | 136 |")
    a("| Deferred | 0 |")
    a("")
    a("## Authorization boundaries")
    a("")
    a("- **Product review only.** No clinical approval is granted, and none is "
      "required for the already-measured display-only differences.")
    a("- That classification is **conditional**: it holds only while all "
      "clinical-impact dimensions stay zero. Any future nonzero membership, "
      "token-mapping, scoring or red-flag difference **reopens Clinical "
      "review**.")
    a("- Approval here does **not** publish or activate candidate 1.1 and does "
      "**not** authorize Mobile implementation.")
    a("- **IM-003 and IM003-SB-001 are outside this review** — IM-003 remains "
      "disabled and the blocker remains open.")
    a("- **Mobile PR #76 remains unauthorized to merge.**")
    a("")
    a("## How to record decisions")
    a("")
    a("Use `im001_decision_template_v1.json` beside this file. Per item: "
      "`keep_candidate_wording`, `use_alternative_wording` (name it in the "
      "rationale), or `defer` — with rationale, name, title and date. A batch "
      "approval is shorthand for recording `keep_candidate_wording` on every "
      "listed member ID; the expansion is that explicit list. Any member can "
      "be overridden individually.")
    a("")
    a("## Review priority by path volume")
    a("")
    a("Batches ordered by how often their wording is seen on captured paths "
      "(attribution sums; a path can count under several decisions). **Volume "
      "is presentation frequency, not clinical importance.**")
    a("")
    by_id = {b["batch_id"]: b for b in workbook["batches"]}
    a("| # | Batch | Decisions | Path attributions |")
    a("|---:|---|---:|---:|")
    for i, bid in enumerate(workbook["priority_by_path_volume"]["order"], 1):
        b = by_id[bid]
        a("| %d | `%s` | %d | %d |" % (i, bid, b["member_count"],
                                       b["total_captured_path_attributions"]))
    a("")
    a("## Batch index")
    a("")
    for section in ("duration wording", "severity wording"):
        blist = [b for b in workbook["batches"] if b["section"] == section]
        a("### %s — %d batches, %d decisions" % (
            section.capitalize(), len(blist),
            sum(b["member_count"] for b in blist)))
        a("")
        a("| Batch | Slot | Candidate wording | Alternatives | Decisions |")
        a("|---|---|---|---:|---:|")
        for b in blist:
            a("| `%s` | `%s` | %s | %d | %d |" % (
                b["batch_id"], b["question_slot"],
                b["candidate_selected_wording"],
                len(b["distinct_alternatives"]), b["member_count"]))
        a("")
    a("### Wording pattern families (index only — not an approval unit)")
    a("")
    a("| Pattern | Decisions |")
    a("|---|---:|")
    for fam in workbook["wording_pattern_families_index"]:
        a("| %s | %d |" % (fam["pattern"].replace("|", "\\|"), fam["count"]))
    a("")
    a("## Detailed decisions")
    a("")
    a("Every one of the 135 wording decisions, grouped by batch. Status of "
      "all: **PENDING**. No duration or severity question has an option-order "
      "difference (all 903 measured order groups are additional-symptoms "
      "questions); option order is decided once, globally, in the next "
      "section.")
    a("")
    items_by_id = {i["decision_id"]: i for i in workbook["decisions"]}
    for b in workbook["batches"]:
        a("### `%s`" % b["batch_id"])
        a("")
        a("**Slot** `%s` · **Candidate wording:** %s" % (
            b["question_slot"], b["candidate_selected_wording"]))
        a("")
        a("| Decision | Alternative wording | Paths | Example path |")
        a("|---|---|---:|---|")
        for did in b["member_decision_ids"]:
            item = items_by_id[did]
            example = ", ".join(item["representative_paths"][0])
            alt = "; ".join(item["alternative_wordings"])
            a("| `%s` | %s | %d | %s |" % (did, alt,
                                           item["captured_paths_affected"], example))
        a("")
    g = workbook["global_ordering_decision"]
    a("## The global ordering decision — `IM001-ORD-GLOBAL-001`")
    a("")
    a("**In plain terms:** %s %s" % (g["plain_language"]["current_behaviour"],
                                     g["plain_language"]["candidate_behaviour"]))
    a("")
    a("What is unchanged either way:")
    a("")
    for line in g["plain_language"]["what_is_unchanged"]:
        a("- %s" % line)
    a("")
    a("**This decision affects display order only** — %d option groups on %d "
      "captured paths. %s" % (g["affected_option_order_groups"],
                              g["affected_paths"],
                              g["plain_language"]["what_approval_does_not_do"]))
    a("")
    a("Choose exactly one (none is pre-selected):")
    a("")
    for choice in g["choices_mutually_exclusive"]:
        a("- **%s** — %s" % (choice["choice_id"], choice["choice"]))
    a("")
    a("Status: **PENDING**.")
    a("")
    a("## Evidence bindings")
    a("")
    src = workbook["_metadata"]["source_evidence"]
    a("| Artifact | SHA256 |")
    a("|---|---|")
    for key in ("product_review", "order_decision", "order_evidence"):
        a("| `%s` | `%s` |" % (src[key]["path"], src[key]["sha256"]))
    a("")
    a("The workbook is regenerated deterministically from these artifacts by "
      "`tools/build_im001_workbook.py`; drift fails `--check` and validation.")
    a("")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    workbook, template, batches, preconditions = build()
    if workbook is None:
        print("FAIL baseline preconditions do not hold:")
        print(json.dumps({k: v for k, v in preconditions.items() if not v}, indent=2))
        return 1

    outputs = [(WORKBOOK, dump_report_bytes(workbook)),
               (TEMPLATE, dump_report_bytes(template)),
               (DOC, render_markdown(workbook).encode("utf-8"))]
    for path, data in outputs:
        relative = os.path.relpath(path, repo_path())
        if args.check:
            if not os.path.exists(path) or open(path, "rb").read() != data:
                print("FAIL %s is missing or stale" % relative)
                return 1
        else:
            write_bytes(path, data)
            print("wrote %s" % relative)

    if args.check:
        print("OK   IM-001 workbook is current")
    else:
        print("  decisions: 135 wording + 1 ordering = 136, all PENDING")
        print("  batches: %d (grouping hides nothing)" % len(batches))
    return 0


if __name__ == "__main__":
    sys.exit(main())
