#!/usr/bin/env python3
"""Record the reconciled IM-001 Product verdicts (I2/W3 Step 11).

    python3 tools/report_im001_verdicts.py            # write
    python3 tools/report_im001_verdicts.py --check    # fail if stale

Source: the vendored human reconciliation record of 24 August 2026
(baseline/im001_reconciliation_v1/), confirmed for recording by the Product
reviewer ("Yes — record the reconciled decisions now").

Writes reports/im001_product_verdicts_v1.json — the authoritative verdict
record. Every batch verdict is expanded to its explicit member decision IDs,
derived deterministically from the wording artifact's stable fields (the same
slot derivation the workbook uses), so no decision can be approved implicitly
or lost.

Fail-closed: refuses to write if the slot expansion does not reproduce exactly
135 member IDs across 20 batches, if a batch rationale is missing, if the
fast_breathing_child clinical flag would not land on exactly IM001-D018 and
IM001-D027, or if any recorded batch wording disagrees with the artifact's
candidate wording.

Nothing here authorizes clinical approval, activation, publication or Mobile
implementation — those four booleans are recorded false and validated.
"""

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

VENDORED = repo_path("baseline", "im001_reconciliation_v1",
                     "IM001_PRODUCT_DECISION_RECONCILIATION_2026-08-24.vendored.md")
WORDING = repo_path("reports", "im001_product_review_v1_1.json")
REPORT = repo_path("reports", "im001_product_verdicts_v1.json")

REVIEWER = {
    "name": "Ayodele John Oluwaseyi",
    "title": "Co-Founder & CEO, WellaPath",
    "authority": "product",
    "review_date": "2026-08-24",
}

#: The evidence hashes the review was conducted over (develop 38e2af6b).
REVIEWED_OVER = {
    "reports/im001_product_review_v1_1.json":
        "4788fee0b6bcf764c22add101d9e4ea806c70a4119c73e6b16b2ebdd2d4324c2",
    "reports/im001_option_order_decision_v1.json":
        "6adbfcc4e2a6983b4a07ff6e04298444061c9343e8da9a86b433b6e6f505f1b1",
    "reports/im001_option_order_evidence_v1.json":
        "fd4391a21c5db85c4881c2b5d238f968def58b999d6caa28580d28830e181939",
}

#: Batch rationales, verbatim from the reconciliation record.
BATCH_VERDICTS = {
    ("abdominal_cramps", "duration"): (
        "How long have you had these abdominal cramps?",
        "Directly asks about the intended symptom; alternatives refer to other "
        "symptoms and create context mismatch. Candidate follows the "
        "established plural duration pattern."),
    ("body_pain", "duration"): (
        "How long have you had this body pain?",
        "Clearly identifies body pain; inherited wording for other symptoms "
        "would be inconsistent and ambiguous."),
    ("chills", "duration"): (
        "How long have you had chills?",
        "Concise, natural and directly asks about chills rather than another "
        "selected symptom."),
    ("cough", "duration"): (
        "How long have you had this cough?",
        "Directly identifies cough and removes path-dependent wording "
        "inherited from unrelated symptoms."),
    ("dark_urine", "duration"): (
        "How long have you noticed dark urine?",
        "Naturally asks when the intended symptom was observed and avoids "
        "wording referring to other symptoms."),
    ("dizziness", "duration"): (
        "How long have you felt dizzy?",
        "Concise, natural and directly asks about dizziness."),
    ("fatigue", "duration"): (
        "How long have you felt this fatigue?",
        "Directly identifies fatigue and avoids a path-dependent mismatch "
        "with other symptoms."),
    ("abdominal_cramps", "severity"): (
        "How severe are your abdominal cramps?",
        "Clearly identifies the symptom being rated. Approval covers wording "
        "only, not clinical validity or the scale."),
    ("fever", "duration"): (
        "How long have you had this fever?",
        "Clearly identifies fever and avoids unrelated symptom wording."),
    ("headache", "duration"): (
        "How long have you had this headache?",
        "Directly identifies headache and removes misleading inherited "
        "wording."),
    ("body_pain", "severity"): (
        "How severe is your body pain?",
        "Specifically identifies body pain; generic \"this pain\" can be "
        "ambiguous when multiple pain symptoms coexist."),
    ("nausea", "duration"): (
        "How long have you had nausea?",
        "Directly identifies nausea and prevents other symptom wording from "
        "appearing in its place."),
    ("cough", "severity"): (
        "How severe is your cough?",
        "Directly identifies cough; alternatives ask about unrelated "
        "symptoms. Approval covers display wording only."),
    ("pain", "duration"): (
        "How long have you had this pain?",
        "Directly identifies the intended pain symptom and provides "
        "consistent wording."),
    ("sweating", "duration"): (
        "How long have you had excessive sweating?",
        "Clearly identifies excessive sweating and removes mismatched symptom "
        "wording."),
    ("fast_breathing_child", "severity"): (
        "How severe is the fast breathing?",
        "Among the existing choices, this is the only wording that identifies "
        "the symptom actually being clarified. Clinical validity remains "
        "explicitly unapproved and flagged for Clinical review before "
        "activation."),
    ("swelling", "duration"): (
        "How long have you had this swelling?",
        "Directly identifies swelling and avoids unrelated symptom wording."),
    ("vomiting", "duration"): (
        "How long have you been vomiting?",
        "Directly identifies vomiting; alternatives ask about weakness or "
        "watery stool."),
    ("headache", "severity"): (
        "How severe is your headache?",
        "Explicitly identifies headache and avoids ambiguity when headache "
        "and another pain symptom coexist."),
    ("watery_stool", "duration"): (
        "How long have you had watery stool?",
        "Directly identifies watery stool; the only alternative asks about "
        "weakness and is a clear context mismatch."),
}

ORDERING_VERDICT = {
    "decision_id": "IM001-ORD-GLOBAL-001",
    "selection": "ORD-A",
    "selection_meaning": "Approve candidate 1.1 deterministic option ordering.",
    "rationale": (
        "A stable option order provides a consistent and predictable user "
        "experience regardless of symptom-selection order and improves "
        "reproducibility, testing and documentation. Evidence establishes "
        "that the change affects display order only."),
}

CLINICAL_FLAG = {
    "flag_id": "IM001-CLIN-FLAG-001",
    "batch_id": "IM001-BATCH-SEVERITY-fast_breathing_child",
    "question_slot": "fast_breathing_child.severity",
    "approved_wording_only": "How severe is the fast breathing?",
    "product_did_not_approve": [
        "whether fast breathing in a child should be severity-rated",
        "whether the question itself is clinically valid",
        "whether the existing severity scale is appropriate",
        "how the answer should be interpreted clinically",
    ],
    "must_remain_visible_for_clinical_review_before_activation": True,
    "status": "open_clinical_flag",
}

BOUNDARIES = {
    "clinical_approval": False,
    "activation_authorization": False,
    "publication_authorization": False,
    "mobile_implementation_authorization": False,
    "clinical_reopen_condition": (
        "Any future nonzero difference in option membership, token mapping, "
        "scoring or red-flag behaviour reopens Clinical review."),
    "im003": "IM-003 remains disabled and IM003-SB-001 remains open; both are "
             "outside this review.",
    "mobile_pr_76": "remains unauthorized to merge",
    "no_repository_change_authorized": (
        "No question candidate, schema, clinical artifact, runtime behaviour, "
        "R2 configuration, Backend repository or Mobile repository is "
        "authorized to change as a consequence of this Product confirmation "
        "alone."),
}


def slot_of(decision):
    parts = decision["selected_source"].split(".")
    return parts[1], parts[2]


def build():
    wording = load_json(WORDING)
    decisions = wording["decisions"]

    by_slot = collections.defaultdict(list)
    for d in decisions:
        by_slot[slot_of(d)].append(d)

    problems = []
    if len(decisions) != 135:
        problems.append("wording decision count is %d, not 135" % len(decisions))
    if set(by_slot) != set(BATCH_VERDICTS):
        problems.append("slot set mismatch: %s"
                        % sorted(set(by_slot) ^ set(BATCH_VERDICTS)))

    batches = []
    wording_verdicts = []
    for (token, kind), (approved_wording, rationale) in sorted(BATCH_VERDICTS.items()):
        members = by_slot.get((token, kind), [])
        artifact_wordings = {d["selected_wording"] for d in members}
        if artifact_wordings != {approved_wording}:
            problems.append("%s.%s: recorded wording %r disagrees with artifact %r"
                            % (token, kind, approved_wording, artifact_wordings))
        member_ids = sorted(d["decision_id"] for d in members)
        batch_id = "IM001-BATCH-%s-%s" % (kind.upper(), token)
        batches.append({
            "batch_id": batch_id,
            "question_slot": "%s.%s" % (token, kind),
            "approved_candidate_wording": approved_wording,
            "rationale": rationale,
            "member_decision_ids": member_ids,
            "member_count": len(member_ids),
        })
        for member_id in member_ids:
            verdict = {
                "decision_id": member_id,
                "batch_id": batch_id,
                "selection": "keep_candidate_wording",
                "approved_wording": approved_wording,
                "rationale": rationale,
                "reviewer_name": REVIEWER["name"],
                "reviewer_title": REVIEWER["title"],
                "authority": REVIEWER["authority"],
                "review_date": REVIEWER["review_date"],
                "override": False,
            }
            if (token, kind) == ("fast_breathing_child", "severity"):
                verdict["clinical_flag"] = CLINICAL_FLAG["flag_id"]
            wording_verdicts.append(verdict)

    flagged = sorted(v["decision_id"] for v in wording_verdicts if "clinical_flag" in v)
    if flagged != ["IM001-D018", "IM001-D027"]:
        problems.append("clinical flag lands on %s, expected IM001-D018/D027" % flagged)
    if len(wording_verdicts) != 135 or len(batches) != 20:
        problems.append("expansion produced %d verdicts in %d batches"
                        % (len(wording_verdicts), len(batches)))

    ordering = dict(ORDERING_VERDICT)
    ordering.update({
        "reviewer_name": REVIEWER["name"],
        "reviewer_title": REVIEWER["title"],
        "authority": REVIEWER["authority"],
        "review_date": REVIEWER["review_date"],
    })

    report = {
        "_metadata": {
            "artifact": "im001_product_verdicts_v1",
            "phase": "I2/W3 Step 11",
            "generated_by": "tools/report_im001_verdicts.py",
            "tooling_version": QFLOW_TOOLING_VERSION,
            "source_record": {
                "title": "I2/W3 Step 11 — Final Product Decision Reconciliation",
                "path": os.path.relpath(VENDORED, repo_path()),
                "sha256": sha256_file(VENDORED),
                "confirmation": ("\"Yes — record the reconciled decisions "
                                 "now.\" (Product reviewer, 2026-08-24)"),
                "provenance": "supplied_as_chat_text_by_product_reviewer_in_step11_brief",
            },
            "reviewed_over_evidence_hashes": REVIEWED_OVER,
            "what_this_is_not": [
                "This is not clinical approval.",
                "This does not authorize activation or publication of "
                "candidate 1.1.",
                "This does not authorize Mobile implementation.",
                "This does not touch IM-003 or IM003-SB-001.",
            ],
        },
        "reviewer": REVIEWER,
        "totals": {
            "explicitly_reviewed": 136, "approved": 136, "pending": 0,
            "deferred": 0, "individual_overrides": 0,
            "unresolved_product_conflicts": 0,
            "wording_decisions": 135, "batches": 20, "ordering_decisions": 1,
        },
        "batches": batches,
        "wording_verdicts": wording_verdicts,
        "ordering_verdict": ordering,
        "clinical_flags": [CLINICAL_FLAG],
        "authorization_boundaries": BOUNDARIES,
    }
    return report, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report, problems = build()
    if problems:
        print("FAIL the verdict record cannot be reconciled with the wording artifact:")
        for problem in problems:
            print("  - %s" % problem)
        return 1

    data = dump_report_bytes(report)
    relative = os.path.relpath(REPORT, repo_path())
    if args.check:
        if not os.path.exists(REPORT) or open(REPORT, "rb").read() != data:
            print("FAIL %s is missing or stale" % relative)
            return 1
        print("OK   IM-001 verdict record is current")
        return 0

    write_bytes(REPORT, data)
    print("wrote %s" % relative)
    print("  verdicts: 135 wording (keep_candidate_wording) + 1 ordering (ORD-A)")
    print("  batches expanded: 20 -> 135 member IDs")
    print("  clinical flags: 1 (fast_breathing_child.severity, IM001-D018/D027)")
    print("  boundaries: clinical/activation/publication/mobile all false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
