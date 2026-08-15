#!/usr/bin/env python3
"""Tests for the Vocabulary 2.0 catalogue review package.

    python3 testing/test_catalogue_review.py

Covers the happy path, every fail-closed guard, and the pending-catalogue dry
run that proves no proposal can reach the candidate artifact.

A guard that has never been seen to fail is an assumption, not a control, so
each one is exercised against a deliberately broken copy held in memory. The
committed artifacts are never modified.

Standard library only, no network.
"""

import copy
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from vocab.artifact_io import load_json, sha256_file  # noqa: E402
from vocab.normalize import normalize  # noqa: E402

import build_catalogue_review as gen  # noqa: E402
import validate_catalogue as val  # noqa: E402

REVIEW = os.path.join(ROOT, "review", "catalogue_v1", "catalogue_review_v1.json")
LABELS = os.path.join(ROOT, "review", "catalogue_v1", "display_label_review_v1.json")
IMPACT = os.path.join(ROOT, "review", "catalogue_v1", "impact_report_v1.json")
RISK = os.path.join(ROOT, "review", "catalogue_v1", "risk_summary_v1.json")
CANDIDATE = os.path.join(ROOT, "candidate", "token_dictionary.ng.v2.0.json")

CANDIDATE_SHA = "07f935967acb1d5515cb53ffd1c8e39b59b8daf85c67cf36fa3e25094e34cd2d"

results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition), detail))


def blockers(proposal):
    """Recompute eligibility blockers with the validator's own logic."""
    return val.recompute_blockers(proposal)


def main():
    review = load_json(REVIEW)
    labels = load_json(LABELS)
    impact = load_json(IMPACT)
    risk = load_json(RISK)
    proposals = [p for b in review["batches"] for p in b["proposals"]]

    # ── frozen artifacts ──────────────────────────────────────────────────
    for rel, expected in sorted(val.FROZEN.items()):
        actual = sha256_file(os.path.join(ROOT, *rel.split("/")))
        check("frozen:%s" % rel, actual == expected, actual)

    check("candidate hash unchanged", sha256_file(CANDIDATE) == CANDIDATE_SHA)

    # ── deterministic generation ──────────────────────────────────────────
    r1 = subprocess.run(
        [sys.executable, "tools/build_catalogue_review.py", "--check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    check("generator --check passes", r1.returncode == 0, r1.stdout.strip())

    before = {p: open(p, "rb").read() for p in (REVIEW, LABELS, IMPACT, RISK)}
    subprocess.run(
        [sys.executable, "tools/build_catalogue_review.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    after = {p: open(p, "rb").read() for p in (REVIEW, LABELS, IMPACT, RISK)}
    check("regeneration is byte-identical", before == after)

    # ── validator passes on the real package ──────────────────────────────
    r2 = subprocess.run(
        [sys.executable, "tools/validate_catalogue.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    check("validator passes", r2.returncode == 0, r2.stdout.strip())

    # ── structural expectations ───────────────────────────────────────────
    ids = [p["proposal_id"] for p in proposals]
    check("proposal ids unique", len(ids) == len(set(ids)))
    check("every proposal has one primary class",
          all(p["primary_change_class"] for p in proposals))
    check("295 display-label rows", len(labels["rows"]) == 295)
    check("no row is display safe",
          not any(r["display_safe_current"] for r in labels["rows"]))
    check("no display-safe proposal yet",
          all(r["display_safe_proposal"] == "not_proposed" for r in labels["rows"]))

    check("nothing is publication eligible",
          all(not p["publication_eligible"] for p in proposals))
    check("every proposal lists why it is blocked",
          all(p["publication_blocked_by"] for p in proposals))

    check("all clinical reviews pending",
          all(p["clinical_review"]["decision"] == "pending" for p in proposals))
    check("all product reviews pending",
          all(p["product_review"]["decision"] == "pending" for p in proposals))

    check("normalized forms are computed",
          all(p["normalized_form"] == normalize(p["phrase"]) for p in proposals))

    # ── the breathlessness / shortness_of_breath boundary ─────────────────
    bsob = [
        p for p in proposals
        if set(p["proposed_target"]["ambiguity_set"])
        == {"breathlessness", "shortness_of_breath"}
    ]
    check("breathlessness proposal exists", len(bsob) == 1)
    if bsob:
        p = bsob[0]
        check("breathlessness is clinical_token_identity",
              p["primary_change_class"] == "clinical_token_identity",
              p["primary_change_class"])
        check("breathlessness is NOT a search alias",
              p["primary_change_class"] != "search_alias")
        check("breathlessness connects two scoring tokens flagged",
              p["risk_flags"]["connects_two_existing_scoring_tokens"] == "yes")
        check("breathlessness not publication eligible",
              not p["publication_eligible"])
        check("breathlessness assigns no single token",
              p["proposed_target"]["canonical_token_id"] is None)

    cand = load_json(CANDIDATE)
    tokens = {t["token_id"] for t in cand["tokens"]}
    check("breathlessness still a canonical token", "breathlessness" in tokens)
    check("shortness_of_breath still a canonical token",
          "shortness_of_breath" in tokens)
    check("neither is deprecated or repointed",
          all(
              t["clinical_identity"]["status"] == "active"
              and t["clinical_identity"]["replaced_by"] is None
              for t in cand["tokens"]
              if t["token_id"] in ("breathlessness", "shortness_of_breath")
          ))

    # ── fail-closed guards, on in-memory copies ───────────────────────────
    def guard(name, mutate):
        p = copy.deepcopy(proposals[0])
        mutate(p)
        check(name, len(blockers(p)) > 0 or p.get("_expect_ok"), str(blockers(p)))

    def approve_fully(p):
        for role in ("clinical_review", "product_review"):
            p[role]["decision"] = "approved"
            p[role]["reviewer"] = "Dr Test Reviewer"
            p[role]["review_date"] = "2026-08-15"
            p[role]["rationale"] = "test"

    # pending stays blocked
    guard("pending is blocked", lambda p: None)

    # rejected / deferred stay blocked even with a reviewer
    for state in ("rejected", "deferred", "pending"):
        p = copy.deepcopy(proposals[0])
        approve_fully(p)
        p["clinical_review"]["decision"] = state
        if state == "pending":
            p["clinical_review"]["reviewer"] = None
        check("%s is never eligible" % state, len(blockers(p)) > 0)

    # a blocking class stays blocked even when both reviewers approve
    p = copy.deepcopy(proposals[0])
    approve_fully(p)
    p["primary_change_class"] = "clinical_token_identity"
    p["risk_flags"] = {k: "no" for k in p["risk_flags"]}
    p["provenance"]["approval_record"] = "clinically_approved"
    check("blocking class stays blocked", len(blockers(p)) > 0, str(blockers(p)))

    # an unresolved risk flag blocks
    p = copy.deepcopy(proposals[0])
    approve_fully(p)
    p["primary_change_class"] = "display_label_only"
    p["provenance"]["approval_record"] = "clinically_approved"
    p["risk_flags"] = {k: "no" for k in p["risk_flags"]}
    p["risk_flags"]["erases_severity"] = "unresolved"
    check("unresolved risk flag blocks", len(blockers(p)) > 0)

    # missing provenance blocks
    p = copy.deepcopy(proposals[0])
    approve_fully(p)
    p["primary_change_class"] = "display_label_only"
    p["risk_flags"] = {k: "no" for k in p["risk_flags"]}
    p["provenance"]["approval_record"] = "clinically_approved"
    p["provenance"]["source_record"] = ""
    check("missing provenance blocks", len(blockers(p)) > 0)

    # an approved, low-risk, fully-provenanced item WOULD be eligible — proving
    # the gate is a real gate and not a constant `false`
    p = copy.deepcopy(proposals[0])
    approve_fully(p)
    p["primary_change_class"] = "display_label_only"
    p["risk_flags"] = {k: "no" for k in p["risk_flags"]}
    p["provenance"]["approval_record"] = "clinically_approved"
    p["provenance"]["approval_evidence"] = "https://example.invalid/approval"
    check("a fully approved low-risk item becomes eligible",
          len(blockers(p)) == 0, str(blockers(p)))

    # ── ambiguity guards ──────────────────────────────────────────────────
    amb = [p for p in proposals if len(p["proposed_target"]["ambiguity_set"]) > 1]
    check("ambiguity sets exist", len(amb) > 0)
    check("no ambiguity set pre-selects a token",
          all(p["proposed_target"]["canonical_token_id"] is None for p in amb))
    check("every ambiguity member resolves",
          all(m in tokens for p in amb for m in p["proposed_target"]["ambiguity_set"]))
    check("every ambiguity set has >= 2 members",
          all(len(p["proposed_target"]["ambiguity_set"]) >= 2 for p in amb))

    # ── alias graph ───────────────────────────────────────────────────────
    aliases = [p for p in proposals if p["primary_change_class"] == "search_alias"]
    check("no alias proposal connects two scoring tokens",
          all(p["risk_flags"]["connects_two_existing_scoring_tokens"] != "yes"
              for p in aliases))

    # ── impact and risk reports ───────────────────────────────────────────
    check("impact totals match", impact["totals"]["total_proposals"] == len(proposals))
    check("impact claims no hit-rate improvement",
          "NONE" in impact["_metadata"]["search_hit_rate_claim"])
    check("local-language gap recorded open",
          impact["local_language_evidence_gap"]["status"] == "OPEN")
    check("all six carried-forward issues recorded",
          len(risk["carried_forward_unresolved_issues"]) == 6)
    check("package claims no clinical approval",
          review["_metadata"]["is_clinical_approval"] is False)
    check("package claims no product approval",
          review["_metadata"]["is_product_approval"] is False)

    # ── pending-catalogue dry run ─────────────────────────────────────────
    # Applying the catalogue while every decision is pending must change
    # nothing. The strongest available statement is that no eligible proposal
    # exists to apply, and the candidate is byte-identical afterwards.
    eligible = [p for p in proposals if p["publication_eligible"]]
    check("dry run: zero eligible proposals to apply", len(eligible) == 0)
    check("dry run: candidate hash unchanged",
          sha256_file(CANDIDATE) == CANDIDATE_SHA)
    check("dry run: candidate alias count still zero",
          sum(len(t["search"]["aliases"]) for t in cand["tokens"]) == 0)
    check("dry run: candidate association count still zero",
          sum(len(t["associations"][k]) for t in cand["tokens"]
              for k in ("body_areas", "complaint_groups",
                        "severity_descriptors", "duration_descriptors")) == 0)
    check("dry run: display_safe false for all 295",
          sum(1 for t in cand["tokens"] if t["display"]["display_safe"]) == 0)
    check("dry run: release_status still candidate_unapproved",
          cand["_metadata"]["release_status"] == "candidate_unapproved")
    check("dry run: may_publish is not true",
          cand["_metadata"].get("may_publish") is not True)
    check("dry run: clinical_review still not_reviewed",
          cand["_metadata"]["clinical_review"]["status"] == "not_reviewed")
    check("dry run: token count still 295", len(cand["tokens"]) == 295)

    # ── reporting ─────────────────────────────────────────────────────────
    failed = [(n, d) for n, ok, d in results if not ok]
    for name, ok, detail in results:
        if not ok:
            print("FAIL %s %s" % (name, ("— " + detail) if detail else ""))
    print()
    print("%d/%d catalogue checks passed" % (len(results) - len(failed), len(results)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
