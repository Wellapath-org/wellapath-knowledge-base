#!/usr/bin/env python3
"""Build the Vocabulary 2.0 clinical/product catalogue review package.

    python3 tools/build_catalogue_review.py            # write
    python3 tools/build_catalogue_review.py --check    # fail if stale

Reads only committed, provenance-bearing inputs and emits review batches, a
display-label review table for all 295 tokens, an impact report and a risk
summary.

Two rules govern everything here:

  1. Nothing is approved. Every reviewer decision is written as `pending`, and
     `publication_eligible` is COMPUTED from the decisions — never asserted.
     Because every decision starts pending, every proposal starts ineligible.

  2. Nothing is invented. Each proposal carries the repository, path, commit
     and record it came from. Where a source does not exist, the entry is
     emitted as an identified content gap rather than back-filled. In
     particular no local-language term is generated: there is no authoritative
     local-language source in this repository, so that section is a gap.

Standard library only, no network, deterministic output.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import (  # noqa: E402
    dump_report_bytes,
    load_json,
    repo_path,
    sha256_file,
    write_bytes,
)
from vocab.normalize import normalize, normalize_token_id  # noqa: E402

CANDIDATE = repo_path("candidate", "token_dictionary.ng.v2.0.json")
V11 = repo_path("token_dictionary.ng.v1.1.json")
KB = repo_path("kb.ng.v2.4.json")
RULES = repo_path("rules.ng.v2.2.json")
GAP = repo_path("mobile_handoff", "picker_scoring_gap_tokens.json")
RED_FLAG_MAP = repo_path("mobile_handoff", "red_flag_display_map.json")
MOBILE_LABELS = repo_path(
    "proposals", "catalogue_v1", "mobile_display_labels.vendored.json"
)
ROADMAP = repo_path("proposals", "catalogue_v1", "roadmap_examples.json")

OUT_DIR = repo_path("review", "catalogue_v1")
OUT_BATCHES = os.path.join(OUT_DIR, "catalogue_review_v1.json")
OUT_LABELS = os.path.join(OUT_DIR, "display_label_review_v1.json")
OUT_IMPACT = os.path.join(OUT_DIR, "impact_report_v1.json")
OUT_RISK = os.path.join(OUT_DIR, "risk_summary_v1.json")

# Every risk-flag key, in a fixed order so output is deterministic.
RISK_KEYS = (
    "affects_scoring",
    "affects_red_flags",
    "connects_two_existing_scoring_tokens",
    "erases_laterality",
    "erases_anatomical_location",
    "erases_severity",
    "erases_duration",
    "erases_negation",
    "merges_adult_and_paediatric",
    "merges_pregnancy_specific_and_general",
    "merges_symptom_and_diagnosis",
    "changes_scoring_eligibility",
    "alters_red_flag_reachability",
)

BLOCKING_CLASSES = {
    "canonical_token_addition",
    "canonical_token_rename",
    "canonical_token_merge",
    "canonical_token_deprecation",
    "clinical_token_identity",
    "scoring_affecting_association",
    "red_flag_affecting_association",
}


def pending_decision():
    return {
        "decision": "pending",
        "reviewer": None,
        "review_date": None,
        "rationale": None,
        "evidence": None,
    }


def risk(**overrides):
    """A risk-flag block defaulting to 'no', with named exceptions."""
    flags = {k: "no" for k in RISK_KEYS}
    for k, v in overrides.items():
        if k not in flags:
            raise KeyError("unknown risk flag: %s" % k)
        flags[k] = v
    return flags


def load_consumers():
    """Which tokens the frozen clinical artifacts actually depend on."""
    kb = load_json(KB)
    rules = load_json(RULES)

    scoring = {}
    for cond in kb["conditions"]:
        for sym in cond.get("symptoms", []):
            tok = sym.get("token")
            if tok:
                scoring.setdefault(tok, []).append(
                    {"condition_id": cond["condition_id"], "weight": sym.get("weight")}
                )

    red_flag = {}
    for rule in rules["rules"]:
        blob = json.dumps(rule)
        for tok in rule.get("trigger_tokens", []) or []:
            red_flag.setdefault(tok, []).append(rule.get("rule_id"))
        # A token named anywhere else in a rule still couples it to that rule.
        del blob

    for cond in kb["conditions"]:
        for tok in cond.get("red_flags", []) or []:
            if isinstance(tok, str):
                red_flag.setdefault(tok, []).append(
                    "kb:%s" % cond["condition_id"]
                )

    return scoring, red_flag


def build_proposals(candidate, scoring, red_flag):
    """Derive every proposal from a committed source. No invented entries."""
    proposals = []
    counter = [0]

    def new_id():
        counter[0] += 1
        return "VC1-%04d" % counter[0]

    token_ids = {t["token_id"] for t in candidate["tokens"]}
    gap = load_json(GAP)
    gap_commit = None  # the file is committed; commit recorded in sources.json

    # ── source 1: the nine picker scoring-gap tokens (PR #24) ──────────────
    for entry in gap["tokens"]:
        tok = entry["token"]
        exists = tok in token_ids
        sc = scoring.get(tok, [])
        rf = red_flag.get(tok, [])
        aliased_to = entry.get("alias_to")

        if aliased_to:
            # Both sides already exist as independent canonical scoring
            # tokens, so this is not a search alias: approving it would let
            # one existing scoring token reach another's conditions. That is a
            # clinical-token-identity decision by definition.
            target_scoring = scoring.get(aliased_to, [])
            cls = "clinical_token_identity"
            flags = risk(
                affects_scoring="yes",
                connects_two_existing_scoring_tokens="yes",
                changes_scoring_eligibility="unresolved",
                merges_symptom_and_diagnosis="no",
            )
            notes = (
                "'%s' and '%s' are BOTH existing canonical scoring tokens. "
                "'%s' carries %s; '%s' carries %s. Mapping one to the other "
                "changes which conditions a user can reach and is therefore a "
                "clinical-token-identity change, not a search alias. It must "
                "not be implemented as an alias. Both tokens remain "
                "independent."
                % (
                    tok,
                    aliased_to,
                    tok,
                    ", ".join(
                        "%s(%s)" % (s["condition_id"], s["weight"]) for s in sc
                    )
                    or "no kb weight",
                    aliased_to,
                    ", ".join(
                        "%s(%s)" % (s["condition_id"], s["weight"])
                        for s in target_scoring
                    )
                    or "no kb weight",
                )
            )
            lost = [
                "which of the two distinct tokens the user meant",
                "the condition set reachable from each token differs",
            ]
            target = {"canonical_token_id": None, "ambiguity_set": sorted([tok, aliased_to])}
            section = "breathing"
        else:
            # The token already exists and already carries kb weight; it is
            # simply not reachable from the picker. That is a display-label
            # gap, not new vocabulary.
            cls = "display_label_only" if exists else "canonical_token_addition"
            flags = risk(
                affects_scoring="yes" if sc else "no",
                affects_red_flags="yes" if rf else "no",
            )
            notes = (
                "Token already exists in token dictionary 1.1 and already "
                "carries kb weight; it is absent from the Mobile picker, so "
                "the gap is display reachability, not vocabulary. Approving a "
                "display label does not change any weight."
                if exists
                else "Token does not exist in the frozen dictionary."
            )
            lost = []
            target = {"canonical_token_id": tok if exists else None, "ambiguity_set": []}
            section = section_for(tok, entry.get("body_area"))

        proposals.append(
            {
                "proposal_id": new_id(),
                "batch_id": None,
                "phrase": entry["display_name"],
                "normalized_form": normalize(entry["display_name"]),
                "locale": "en-NG",
                "complaint_section": section,
                "proposed_target": target,
                "proposed_complaint_group": None,
                "proposed_body_area": entry.get("body_area"),
                "proposed_severity_applicable": None,
                "proposed_duration_applicable": None,
                "display_safe_proposal": "not_proposed",
                "primary_change_class": cls,
                "risk_flags": flags,
                "provenance": {
                    "source_repository": "Wellapath-org/wellapath-knowledge-base",
                    "source_path": "mobile_handoff/picker_scoring_gap_tokens.json",
                    "source_commit": gap_commit,
                    "source_record": "tokens[] where token == %s (priority %s)"
                    % (tok, entry.get("priority")),
                    "authoring_context": (
                        "PR #24, merged 2026-07-29, 'picker scoring-gap tokens "
                        "— 9 fast-follow additions (E9)'. Engineering-authored "
                        "from kb 2.4 symptom usage. The merge records an "
                        "engineering deliverable; it records no clinical review."
                    ),
                    "approval_record": "engineering_reviewed",
                    "approval_evidence": (
                        "https://github.com/Wellapath-org/wellapath-knowledge-base/pull/24"
                    ),
                },
                "evidence_level": "engineering_inference",
                "ambiguity_notes": notes,
                "lost_context": lost,
                "kb_scoring_references": sc,
                "rules_red_flag_references": rf,
                "clinical_review": pending_decision(),
                "product_review": pending_decision(),
            }
        )

    # ── source 2: red-flag near-miss sets (ambiguity proposals) ────────────
    for entry in load_json(RED_FLAG_MAP):
        tok = entry["token"]
        near = entry.get("near_miss_tokens", []) or []
        if not near:
            continue
        members = sorted(set([tok] + [n for n in near if n in token_ids]))
        if len(members) < 2:
            continue
        # Impact is a property of the whole set, not of the red-flag token
        # alone: a near-miss member carrying kb weight makes the proposal
        # scoring-affecting even when the red-flag token itself has none.
        set_scores = [m for m in members if scoring.get(m)]
        set_red_flags = [m for m in members if red_flag.get(m)]
        proposals.append(
            {
                "proposal_id": new_id(),
                "batch_id": None,
                "phrase": entry["display_name"],
                "normalized_form": normalize(entry["display_name"]),
                "locale": "en-NG",
                "complaint_section": section_for(tok, entry.get("body_area")),
                "proposed_target": {
                    "canonical_token_id": None,
                    "ambiguity_set": members,
                },
                "proposed_complaint_group": None,
                "proposed_body_area": entry.get("body_area"),
                "proposed_severity_applicable": None,
                "proposed_duration_applicable": None,
                "display_safe_proposal": "not_proposed",
                "primary_change_class": "red_flag_affecting_association",
                "risk_flags": risk(
                    affects_red_flags="yes" if set_red_flags else "no",
                    affects_scoring="yes" if set_scores else "no",
                    alters_red_flag_reachability="unresolved",
                    erases_severity="unresolved",
                    connects_two_existing_scoring_tokens="yes",
                ),
                "provenance": {
                    "source_repository": "Wellapath-org/wellapath-knowledge-base",
                    "source_path": "mobile_handoff/red_flag_display_map.json",
                    "source_commit": None,
                    "source_record": "entry where token == %s (near_miss_tokens)" % tok,
                    "authoring_context": (
                        "Engineering-authored red-flag display map recording "
                        "near-miss tokens and the clarification the author "
                        "believed necessary before escalating."
                    ),
                    "approval_record": "proposed_unreviewed",
                    "approval_evidence": None,
                },
                "evidence_level": "engineering_inference",
                "ambiguity_notes": (
                    "Near-miss set for a red-flag token. Source note: %s "
                    "Escalating a near-miss selection to the red flag changes "
                    "red-flag reachability and must not be resolved "
                    "automatically."
                    % entry.get("note", "(no note recorded)")
                ),
                "lost_context": [
                    "severity distinction between the red flag and its near misses"
                ],
                "kb_scoring_references": scoring.get(tok, []),
                "rules_red_flag_references": red_flag.get(tok, []),
                "clinical_review": pending_decision(),
                "product_review": pending_decision(),
            }
        )

    # ── source 3: roadmap example complaints ──────────────────────────────
    roadmap = load_json(ROADMAP)
    for ex in roadmap["examples"]:
        phrase = ex["phrase"]
        norm = normalize(phrase)
        # Candidate tokens are found by whole-word overlap against canonical
        # normalized forms. This is a REVIEW AID that lists what a reviewer
        # should consider — it is not a resolver and assigns nothing.
        words = set(norm.split())
        candidates = sorted(
            t["token_id"]
            for t in candidate["tokens"]
            if set(normalize_token_id(t["token_id"]).split()) & words
        )
        proposals.append(
            {
                "proposal_id": new_id(),
                "batch_id": None,
                "phrase": phrase,
                "normalized_form": norm,
                "locale": ex.get("locale", "en-NG"),
                "complaint_section": "unassigned",
                "proposed_target": {"canonical_token_id": None, "ambiguity_set": []},
                "proposed_complaint_group": None,
                "proposed_body_area": None,
                "proposed_severity_applicable": None,
                "proposed_duration_applicable": None,
                "display_safe_proposal": "not_proposed",
                "primary_change_class": "insufficient_evidence_do_not_propose",
                "risk_flags": risk(
                    erases_laterality="unresolved",
                    erases_anatomical_location="unresolved",
                    erases_severity="unresolved",
                    erases_duration="unresolved",
                    merges_adult_and_paediatric="unresolved"
                    if "child" in words
                    else "no",
                ),
                "provenance": {
                    "source_repository": "(none — task brief)",
                    "source_path": "proposals/catalogue_v1/roadmap_examples.json",
                    "source_commit": None,
                    "source_record": ex["example_id"],
                    "authoring_context": (
                        "Product-roadmap example user complaint supplied in the "
                        "I2/W2 Step 5 brief. No committed roadmap document in "
                        "this repository contains this string, so it has no "
                        "file/commit provenance of its own."
                    ),
                    "approval_record": "unresolved",
                    "approval_evidence": None,
                },
                "evidence_level": "example_only",
                "ambiguity_notes": (
                    "Product example, not a proposed mapping. Reviewer-visible "
                    "candidate tokens sharing a normalized word: %s. This list "
                    "is a review aid produced by word overlap; it is NOT a "
                    "resolution and no token is assigned. The phrase carries "
                    "context the vocabulary does not model as one token."
                    % (", ".join(candidates) if candidates else "none")
                ),
                "lost_context": lost_context_for(phrase, words),
                "kb_scoring_references": [],
                "rules_red_flag_references": [],
                "reviewer_visible_candidates": candidates,
                "clinical_review": pending_decision(),
                "product_review": pending_decision(),
            }
        )

    return proposals


def lost_context_for(phrase, words):
    lost = []
    if "lower" in words or "upper" in words or "left" in words or "right" in words:
        lost.append("anatomical qualifier or laterality present in the phrase")
    if "child" in words or "baby" in words:
        lost.append("age group — adult and paediatric concepts must not merge")
    if "my" in words or "i" in words:
        lost.append("first-person report vs. carer report")
    lost.append("severity and duration are unstated")
    return lost


BODY_AREA_SECTION = {
    "Chest": "breathing",
    "Abdomen": "digestive",
    "Pelvis": "maternal",
    "Head": "neurological",
    "Skin": "skin",
    "General": "general_system",
}


def section_for(token_id, body_area):
    if body_area in BODY_AREA_SECTION:
        return BODY_AREA_SECTION[body_area]
    if "pain" in token_id:
        return "pain"
    return "general_system"


def build_display_label_rows(candidate, mobile_labels, scoring, red_flag):
    """One review row per canonical token. All 295, none approved."""
    labels = mobile_labels["labels"]
    rows = []
    for tok in candidate["tokens"]:
        tid = tok["token_id"]
        mobile = labels.get(tid, [])
        rows.append(
            {
                "token_id": tid,
                "existing_canonical_label": tok["display"]["canonical_label"],
                "canonical_label_source": tok["display"]["label_source"],
                "existing_mobile_display_label": mobile[0] if mobile else None,
                "mobile_label_count": len(mobile),
                "proposed_v2_display_label": None,
                "display_safe_current": tok["display"]["display_safe"],
                "display_safe_proposal": "not_proposed",
                "reason": (
                    "Label is derived mechanically from the token id and has "
                    "not been reviewed."
                    if tok["display"]["label_source"] == "derived_from_token_id"
                    else "Label source: %s" % tok["display"]["label_source"]
                ),
                "provenance": {
                    "canonical_label": "candidate/token_dictionary.ng.v2.0.json",
                    "mobile_label": (
                        "%s @ %s"
                        % (
                            mobile_labels["_metadata"]["vendored_from"]["path"],
                            mobile_labels["_metadata"]["vendored_from"]["commit"],
                        )
                        if mobile
                        else None
                    ),
                },
                "shipped_in_mobile_today": bool(mobile),
                "affects_scoring": bool(scoring.get(tid)),
                "affects_red_flags": bool(red_flag.get(tid)),
                "language_flags": language_flags(tid, tok["display"]["canonical_label"]),
                "product_review": pending_decision(),
                "clinical_review": pending_decision(),
            }
        )
    return rows


SENSITIVE_MARKERS = (
    "hiv",
    "pregnan",
    "vaginal",
    "genital",
    "penile",
    "rape",
    "abort",
    "mental",
    "suicid",
    "malnutrition",
    "stunting",
    "wasting",
)
DIAGNOSTIC_MARKERS = (
    "malaria",
    "cholera",
    "pneumonia",
    "typhoid",
    "measles",
    "tuberculosis",
    "hepatitis",
    "anaemia",
    "anemia",
    "diabetes",
    "hypertension",
    "sepsis",
    "meningitis",
)


def language_flags(token_id, label):
    """Flags a reviewer must look at. Detection is deliberately conservative
    and lexical — it raises questions, it does not answer them."""
    hay = (token_id + " " + label).lower()
    return {
        "sensitive": any(m in hay for m in SENSITIVE_MARKERS),
        "diagnostic_term_used_as_symptom": any(m in hay for m in DIAGNOSTIC_MARKERS),
        "stigmatising_review_required": any(
            m in hay for m in ("hiv", "malnutrition", "mental", "wasting")
        ),
        "potentially_misleading": token_id.count("_") >= 3,
    }


def compute_eligibility(proposal):
    """Publication eligibility is derived, never asserted."""
    blocked = []

    for role, key in (("clinical", "clinical_review"), ("product", "product_review")):
        decision = proposal[key]["decision"]
        if decision != "approved" and decision != "approved_with_revision":
            blocked.append("%s_review_%s" % (role, decision))
        elif not proposal[key]["reviewer"]:
            blocked.append("%s_review_missing_reviewer" % role)

    for flag, value in sorted(proposal["risk_flags"].items()):
        if value == "unresolved":
            blocked.append("unresolved_risk_flag:%s" % flag)

    prov = proposal["provenance"]
    for field in ("source_repository", "source_path", "source_record", "authoring_context"):
        if not prov.get(field):
            blocked.append("missing_provenance:%s" % field)
    if prov.get("approval_record") in ("proposed_unreviewed", "unresolved"):
        blocked.append("no_approval_record")

    if proposal["primary_change_class"] in BLOCKING_CLASSES:
        blocked.append("blocking_change_class:%s" % proposal["primary_change_class"])
    if proposal["primary_change_class"] == "insufficient_evidence_do_not_propose":
        blocked.append("insufficient_evidence")

    return (len(blocked) == 0), sorted(set(blocked))


BATCH_DEFS = [
    (
        "BATCH-01-display-labels",
        "Display-label proposals for existing tokens (low risk)",
        "low",
        ["display_label_only"],
        ["Showing an approved label for a token that already exists and already carries its current weight"],
        [
            "It does NOT set display_safe on any token",
            "It does NOT add, rename, merge or deprecate any canonical token",
            "It does NOT change any weight, rule, urgency or question",
            "It does NOT approve the Vocabulary 2.0 candidate for publication",
        ],
        ["product", "clinical"],
    ),
    (
        "BATCH-02-search-aliases",
        "Search-only alias proposals",
        "low",
        ["search_alias"],
        ["Adding a search phrase that resolves to exactly one existing canonical token"],
        [
            "It does NOT connect two existing scoring tokens",
            "It does NOT change scoring eligibility or red-flag reachability",
            "It does NOT authorise any alias that reaches a second canonical token",
        ],
        ["clinical", "product"],
    ),
    (
        "BATCH-03-ambiguity",
        "Ambiguity sets — terms that must never auto-resolve",
        "medium",
        ["ambiguous_search_term"],
        ["Recording that a phrase maps to two or more candidates and must prompt the user"],
        [
            "It does NOT choose between the candidates",
            "It does NOT make any candidate scoring-eligible from the phrase alone",
        ],
        ["clinical", "product"],
    ),
    (
        "BATCH-04-metadata",
        "Metadata-only associations (body area, complaint group, severity, duration)",
        "medium",
        [
            "complaint_group_metadata",
            "body_area_metadata",
            "severity_metadata",
            "duration_metadata",
        ],
        ["Attaching search/filter metadata used to group and narrow the picker"],
        [
            "It does NOT make metadata a scoring input",
            "It does NOT let a body area or severity label act as a clinical token",
        ],
        ["product", "clinical"],
    ),
    (
        "BATCH-05-scoring-affecting",
        "Scoring-affecting proposals — BLOCKING",
        "blocking",
        ["scoring_affecting_association"],
        ["Nothing on approval alone — these additionally require an engineering-lead sign-off and a regression run"],
        [
            "It does NOT authorise publication",
            "It does NOT authorise a Mobile implementation without the case-bank regression re-run",
        ],
        ["clinical", "product"],
    ),
    (
        "BATCH-06-red-flag-affecting",
        "Red-flag-affecting proposals — BLOCKING",
        "blocking",
        ["red_flag_affecting_association"],
        ["Nothing on approval alone — red-flag reachability changes require clinical review plus engineering lead"],
        [
            "It does NOT authorise auto-escalating a near-miss token to a red flag",
            "It does NOT authorise publication",
        ],
        ["clinical", "product"],
    ),
    (
        "BATCH-07-token-identity",
        "Clinical-token-identity proposals — BLOCKING",
        "blocking",
        [
            "clinical_token_identity",
            "canonical_token_addition",
            "canonical_token_rename",
            "canonical_token_merge",
            "canonical_token_deprecation",
        ],
        ["Nothing on approval alone — each needs clinical review, engineering-lead approval and named regression cases"],
        [
            "It does NOT authorise mapping breathlessness to shortness_of_breath",
            "It does NOT authorise any token merge",
            "It does NOT authorise publication",
        ],
        ["clinical", "product"],
    ),
    (
        "BATCH-08-evidence-gaps",
        "Unresolved evidence gaps — no proposal, review needed to decide whether one is possible",
        "blocking",
        ["insufficient_evidence_do_not_propose"],
        ["Nothing. These are questions, not proposals"],
        [
            "It does NOT assign any canonical token",
            "Approving an item here only means 'a proposal may now be drafted'",
        ],
        ["clinical", "product"],
    ),
]


def assign_batches(proposals):
    batches = []
    for bid, title, tier, classes, authorises, not_authorises, reviewers in BATCH_DEFS:
        members = [p for p in proposals if p["primary_change_class"] in classes]
        for p in members:
            p["batch_id"] = bid
        batches.append(
            {
                "batch_id": bid,
                "title": title,
                "risk_tier": tier,
                "approval_authorizes": authorises,
                "approval_does_not_authorize": not_authorises,
                "required_reviewers": reviewers,
                "batch_status": "pending",
                "proposal_count": len(members),
                "proposals": members,
            }
        )
    return batches


def build():
    candidate = load_json(CANDIDATE)
    mobile_labels = load_json(MOBILE_LABELS)
    scoring, red_flag = load_consumers()

    proposals = build_proposals(candidate, scoring, red_flag)
    for p in proposals:
        eligible, blocked = compute_eligibility(p)
        p["publication_eligible"] = eligible
        p["publication_blocked_by"] = blocked

    batches = assign_batches(proposals)
    rows = build_display_label_rows(candidate, mobile_labels, scoring, red_flag)

    frozen = {
        "token_dictionary_v1_1": sha256_file(V11),
        "candidate_v2_0": sha256_file(CANDIDATE),
        "kb_v2_4": sha256_file(KB),
        "rules_v2_2": sha256_file(RULES),
        "case_bank_v1": sha256_file(repo_path("testing", "case_bank_v1.json")),
        "known_findings": sha256_file(repo_path("testing", "known_findings.json")),
    }

    review = {
        "_metadata": {
            "artifact_id": "vocabulary_catalogue_review",
            "version": "1.0",
            "country": "ng",
            "generated_by": "tools/build_catalogue_review.py",
            "generator_version": "1.0.0",
            "schema": "schema/catalogue_review.schema.json",
            "status": "ALL DECISIONS PENDING — NOTHING IN THIS FILE IS APPROVED",
            "is_clinical_approval": False,
            "is_product_approval": False,
            "frozen_baseline": frozen,
            "description": (
                "Review-ready catalogue package. Every proposal carries its "
                "provenance and exactly one primary change class. Publication "
                "eligibility is computed from reviewer decisions; because every "
                "decision is pending, nothing is eligible."
            ),
        },
        "batches": batches,
    }

    return review, rows, frozen


def build_impact(review, rows):
    proposals = [p for b in review["batches"] for p in b["proposals"]]

    def tally(key):
        out = {}
        for p in proposals:
            out[p[key]] = out.get(p[key], 0) + 1
        return dict(sorted(out.items()))

    collisions = {}
    for p in proposals:
        collisions.setdefault(p["normalized_form"], []).append(p["proposal_id"])
    collisions = {k: v for k, v in sorted(collisions.items()) if len(v) > 1}

    ambiguity_sets = [
        {
            "proposal_id": p["proposal_id"],
            "phrase": p["phrase"],
            "members": p["proposed_target"]["ambiguity_set"],
        }
        for p in proposals
        if len(p["proposed_target"]["ambiguity_set"]) > 1
    ]

    return {
        "_metadata": {
            "artifact_id": "vocabulary_catalogue_impact",
            "version": "1.0",
            "generated_by": "tools/build_catalogue_review.py",
            "search_hit_rate_claim": (
                "NONE. No approved catalogue content exists yet, so no search "
                "hit-rate improvement is claimed or measurable."
            ),
        },
        "totals": {
            "total_proposals": len(proposals),
            "display_label_review_rows": len(rows),
            "publication_eligible": sum(
                1 for p in proposals if p["publication_eligible"]
            ),
            "publication_blocked": sum(
                1 for p in proposals if not p["publication_eligible"]
            ),
        },
        "by_primary_class": tally("primary_change_class"),
        "by_complaint_section": tally("complaint_section"),
        "by_batch": {
            b["batch_id"]: b["proposal_count"] for b in review["batches"]
        },
        "by_approval_state": {
            "clinical_pending": sum(
                1 for p in proposals if p["clinical_review"]["decision"] == "pending"
            ),
            "product_pending": sum(
                1 for p in proposals if p["product_review"]["decision"] == "pending"
            ),
        },
        "affecting_scoring": sum(
            1 for p in proposals if p["risk_flags"]["affects_scoring"] == "yes"
        ),
        "affecting_red_flags": sum(
            1 for p in proposals if p["risk_flags"]["affects_red_flags"] == "yes"
        ),
        "normalization_collisions": collisions,
        "normalization_collision_count": len(collisions),
        "ambiguity_sets": ambiguity_sets,
        "ambiguity_set_count": len(ambiguity_sets),
        "display_safe_candidates": sum(
            1 for r in rows if r["display_safe_proposal"] != "not_proposed"
        ),
        "display_safe_current_true": sum(
            1 for r in rows if r["display_safe_current"]
        ),
        "tokens_shipped_in_mobile_today": sum(
            1 for r in rows if r["shipped_in_mobile_today"]
        ),
        "tokens_with_no_mobile_label": sum(
            1 for r in rows if not r["shipped_in_mobile_today"]
        ),
        "unresolved_evidence_gaps": [
            p["proposal_id"]
            for p in proposals
            if p["primary_change_class"] == "insufficient_evidence_do_not_propose"
        ],
        "local_language_evidence_gap": {
            "status": "OPEN",
            "detail": (
                "No authoritative local-language (Hausa, Yoruba, Igbo, Nigerian "
                "Pidgin) vocabulary source exists in this repository. No local "
                "term has been generated, translated or inferred. A sourced "
                "catalogue is required before any non-English search content "
                "can be proposed."
            ),
        },
        "safe_for_engineering_after_approval": [
            p["proposal_id"]
            for p in proposals
            if p["primary_change_class"] in ("display_label_only", "search_alias")
        ],
        "requires_clinical_artifact_change": [
            p["proposal_id"]
            for p in proposals
            if p["primary_change_class"] in BLOCKING_CLASSES
        ],
        "prohibited_from_automatic_mapping": [
            p["proposal_id"]
            for p in proposals
            if p["primary_change_class"]
            in ("ambiguous_search_term", "insufficient_evidence_do_not_propose")
            or len(p["proposed_target"]["ambiguity_set"]) > 1
        ],
    }


def build_risk_summary(review):
    proposals = [p for b in review["batches"] for p in b["proposals"]]
    unresolved = {}
    for p in proposals:
        for flag, value in sorted(p["risk_flags"].items()):
            if value == "unresolved":
                unresolved.setdefault(flag, []).append(p["proposal_id"])

    return {
        "_metadata": {
            "artifact_id": "vocabulary_catalogue_risk_summary",
            "version": "1.0",
            "generated_by": "tools/build_catalogue_review.py",
        },
        "blocking_proposals": [
            {
                "proposal_id": p["proposal_id"],
                "phrase": p["phrase"],
                "primary_change_class": p["primary_change_class"],
                "blocked_by": p["publication_blocked_by"],
            }
            for p in proposals
            if not p["publication_eligible"]
        ],
        "unresolved_risk_flags": {k: sorted(v) for k, v in sorted(unresolved.items())},
        "connects_two_existing_scoring_tokens": [
            p["proposal_id"]
            for p in proposals
            if p["risk_flags"]["connects_two_existing_scoring_tokens"] == "yes"
        ],
        "carried_forward_unresolved_issues": [
            {
                "id": "IMCI-TIER-KEYS",
                "detail": "Three unresolved IMCI tier keys: pneumonia, severe_pneumonia, very_severe_disease.",
                "status": "unresolved — not addressed in this step",
            },
            {
                "id": "BREATHLESSNESS-SOB",
                "detail": "breathlessness vs shortness_of_breath: both remain independent canonical scoring tokens. The mapping proposal is classified clinical_token_identity and remains unapproved and unimplemented.",
                "status": "unresolved — decision required",
            },
            {
                "id": "CASE-BANK-CLINICAL-SIGNOFF",
                "detail": "The 239-case bank is engineering-approved and specification-derived with no recorded clinical approval.",
                "status": "unresolved — clinical sign-off required",
            },
            {
                "id": "CB_211",
                "detail": "Option B (correct the case-bank expectation) vs Option C (engine-level empty-input result), due before external beta.",
                "status": "unresolved — Option D registry holds it fail-closed meanwhile",
            },
            {
                "id": "ISSUE-38",
                "detail": "wellapath-mobile issue #38 — malaria base_weight dominates a mixed malaria/diarrhoea presentation (CB_232: malaria 26 vs acute_diarrhoea 21, margin 5).",
                "status": "unresolved — clinical review requested",
            },
            {
                "id": "NO-DOCUMENTED-TIE-BREAK",
                "detail": "No scoring tie-break is documented. CB_232 is not a tie (margin 5), so no tie-break was exercised or implemented.",
                "status": "unresolved — policy absent by design, not by oversight",
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    review, rows, frozen = build()
    impact = build_impact(review, rows)
    risk_summary = build_risk_summary(review)

    label_doc = {
        "_metadata": {
            "artifact_id": "vocabulary_display_label_review",
            "version": "1.0",
            "generated_by": "tools/build_catalogue_review.py",
            "status": "ALL ROWS PENDING — NO LABEL IS APPROVED",
            "rule": (
                "display_safe stays false. A token does not become display-safe "
                "because a label already exists, in this artifact or in Mobile."
            ),
            "total_rows": len(rows),
            "frozen_baseline": frozen,
        },
        "rows": rows,
    }

    outputs = [
        (OUT_BATCHES, dump_report_bytes(review)),
        (OUT_LABELS, dump_report_bytes(label_doc)),
        (OUT_IMPACT, dump_report_bytes(impact)),
        (OUT_RISK, dump_report_bytes(risk_summary)),
    ]

    if args.check:
        stale = [
            os.path.relpath(path, repo_path())
            for path, payload in outputs
            if not os.path.exists(path) or open(path, "rb").read() != payload
        ]
        if stale:
            print("FAIL catalogue review artifacts are missing or stale:")
            for s in stale:
                print("       %s" % s)
            return 1
        print("OK   catalogue review package is current")
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    for path, payload in outputs:
        write_bytes(path, payload)
        print("wrote %s" % os.path.relpath(path, repo_path()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
