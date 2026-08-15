#!/usr/bin/env python3
"""Validate the Vocabulary 2.0 catalogue review package.

    python3 tools/validate_catalogue.py

Exit 0 means every check below holds. Each check exists because a specific
mistake would otherwise reach a clinical reviewer looking like settled fact:

  * frozen artifacts unchanged — a catalogue reviewed against a moved baseline
    is a catalogue reviewed against nothing;
  * proposal IDs unique;
  * every canonical token reference resolves against the frozen dictionary;
  * ambiguity sets have >= 2 distinct, resolvable members;
  * no two proposals collide on their normalized form without being declared
    an ambiguity set;
  * no alias targets another alias, and no alias cycle exists;
  * any proposal connecting two existing scoring tokens is classified as
    clinical_token_identity, never as a search alias;
  * red-flag-affecting proposals are classified as such;
  * provenance is complete, and a merged PR is not treated as clinical
    approval;
  * reviewer fields are consistent with the decision state;
  * publication eligibility is RECOMPUTED and must match the stored value;
  * nothing pending, rejected or deferred is publication-eligible;
  * generated files are reproducible from the generator (no hand edits);
  * no PHI-shaped or unsafe content in reviewer-visible text.

Standard library only, no network.
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import load_json, repo_path, sha256_file  # noqa: E402
from vocab.normalize import normalize  # noqa: E402

REVIEW = repo_path("review", "catalogue_v1", "catalogue_review_v1.json")
LABELS = repo_path("review", "catalogue_v1", "display_label_review_v1.json")
IMPACT = repo_path("review", "catalogue_v1", "impact_report_v1.json")
RISK = repo_path("review", "catalogue_v1", "risk_summary_v1.json")
CANDIDATE = repo_path("candidate", "token_dictionary.ng.v2.0.json")

FROZEN = {
    "token_dictionary.ng.v1.1.json": "0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019",
    "candidate/token_dictionary.ng.v2.0.json": "07f935967acb1d5515cb53ffd1c8e39b59b8daf85c67cf36fa3e25094e34cd2d",
    "kb.ng.v2.4.json": "6c00d8257f8417e86bd5e237630bf8a4623ad72e2e46b1b071dd447c067cec2b",
    "rules.ng.v2.2.json": "1d27e854cba95b179577a88f92445400f494a7fe8e6a53a60fcaa98b3870d1c4",
    "testing/case_bank_v1.json": "c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834",
    "testing/known_findings.json": "fadaea063303ecd27a90c233dba7782f8840c85aef4e3a7cca61b1e4793537ed",
}

BLOCKING_CLASSES = {
    "canonical_token_addition",
    "canonical_token_rename",
    "canonical_token_merge",
    "canonical_token_deprecation",
    "clinical_token_identity",
    "scoring_affecting_association",
    "red_flag_affecting_association",
}

APPROVED_STATES = {"approved", "approved_with_revision"}

failures = []


def fail(check, detail):
    failures.append("%-42s %s" % (check, detail))


def proposals_of(review):
    return [p for b in review["batches"] for p in b["proposals"]]


def check_frozen():
    for rel, expected in sorted(FROZEN.items()):
        actual = sha256_file(repo_path(*rel.split("/")))
        if actual != expected:
            fail(
                "frozen_artifact_unchanged",
                "%s changed: expected %s got %s" % (rel, expected, actual),
            )


def check_reproducible():
    result = subprocess.run(
        [sys.executable, "tools/build_catalogue_review.py", "--check"],
        cwd=repo_path(),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(
            "generated_files_not_hand_edited",
            "generator --check failed: %s" % result.stdout.strip(),
        )


def check_proposals(review, token_ids, scoring, red_flag):
    seen = set()
    by_norm = {}

    for p in proposals_of(review):
        pid = p["proposal_id"]

        if not re.match(r"^VC1-\d{4}$", pid):
            fail("proposal_id_format", pid)
        if pid in seen:
            fail("proposal_id_unique", "duplicate %s" % pid)
        seen.add(pid)

        if p["normalized_form"] != normalize(p["phrase"]):
            fail(
                "normalized_form_is_computed",
                "%s stored %r but normalize() gives %r"
                % (pid, p["normalized_form"], normalize(p["phrase"])),
            )

        target = p["proposed_target"]
        members = target["ambiguity_set"]

        if target["canonical_token_id"] is not None:
            if target["canonical_token_id"] not in token_ids:
                fail(
                    "canonical_reference_resolves",
                    "%s -> unknown token %s" % (pid, target["canonical_token_id"]),
                )
            if members:
                fail(
                    "single_target_xor_ambiguity_set",
                    "%s carries both a canonical token and an ambiguity set" % pid,
                )

        if members:
            if len(members) < 2:
                fail("ambiguity_set_min_two", "%s has %d member(s)" % (pid, len(members)))
            if len(set(members)) != len(members):
                fail("ambiguity_set_distinct", "%s repeats a member" % pid)
            for m in members:
                if m not in token_ids:
                    fail("ambiguity_member_resolves", "%s -> unknown token %s" % (pid, m))
            if target["canonical_token_id"] is not None:
                fail("ambiguity_never_auto_resolves", "%s pre-selects a token" % pid)

        by_norm.setdefault(p["normalized_form"], []).append(p)

        # An alias must resolve to exactly one token. If the proposal would
        # connect two existing scoring tokens it is an identity change.
        connects = p["risk_flags"]["connects_two_existing_scoring_tokens"] == "yes"
        if connects and p["primary_change_class"] == "search_alias":
            fail(
                "alias_vs_identity_boundary",
                "%s connects two existing scoring tokens but is classed as a "
                "search alias" % pid,
            )

        # Anything touching a red-flag token must say so.
        touched = set(members) | (
            {target["canonical_token_id"]} if target["canonical_token_id"] else set()
        )
        if any(t in red_flag for t in touched):
            if p["risk_flags"]["affects_red_flags"] != "yes":
                fail(
                    "red_flag_impact_declared",
                    "%s touches a red-flag token but affects_red_flags is %r"
                    % (pid, p["risk_flags"]["affects_red_flags"]),
                )

        if any(t in scoring for t in touched):
            if p["risk_flags"]["affects_scoring"] != "yes":
                fail(
                    "scoring_impact_declared",
                    "%s touches a scoring token but affects_scoring is %r"
                    % (pid, p["risk_flags"]["affects_scoring"]),
                )

        prov = p["provenance"]
        for field in (
            "source_repository",
            "source_path",
            "source_record",
            "authoring_context",
            "approval_record",
        ):
            if not prov.get(field):
                fail("provenance_complete", "%s missing %s" % (pid, field))
        if prov.get("approval_record") in ("product_approved", "clinically_approved"):
            if not prov.get("approval_evidence"):
                fail(
                    "approval_claim_needs_evidence",
                    "%s claims %s with no evidence link" % (pid, prov["approval_record"]),
                )

        for role in ("clinical_review", "product_review"):
            d = p[role]["decision"]
            if d not in (
                "pending",
                "approved",
                "approved_with_revision",
                "rejected",
                "deferred",
            ):
                fail("decision_state_valid", "%s %s=%r" % (pid, role, d))
            if d != "pending" and not p[role]["reviewer"]:
                fail(
                    "reviewer_named_for_decision",
                    "%s %s is %s with no named reviewer" % (pid, role, d),
                )
            if d == "pending" and p[role]["reviewer"]:
                fail(
                    "pending_has_no_reviewer",
                    "%s %s is pending but names a reviewer" % (pid, role),
                )

        recomputed_blocked = recompute_blockers(p)
        if bool(p["publication_eligible"]) != (len(recomputed_blocked) == 0):
            fail(
                "publication_eligibility_is_computed",
                "%s stored eligible=%s but recomputation says %s"
                % (pid, p["publication_eligible"], len(recomputed_blocked) == 0),
            )
        if sorted(p["publication_blocked_by"]) != recomputed_blocked:
            fail(
                "blocked_by_matches_recomputation",
                "%s stored %s, recomputed %s"
                % (pid, p["publication_blocked_by"], recomputed_blocked),
            )

        # Fail closed: nothing unapproved may ever be eligible.
        if p["publication_eligible"]:
            for role in ("clinical_review", "product_review"):
                if p[role]["decision"] not in APPROVED_STATES:
                    fail(
                        "fail_closed_no_unapproved_publication",
                        "%s eligible while %s is %s"
                        % (pid, role, p[role]["decision"]),
                    )
            if p["primary_change_class"] in BLOCKING_CLASSES:
                fail(
                    "fail_closed_blocking_class",
                    "%s eligible with blocking class %s"
                    % (pid, p["primary_change_class"]),
                )
            if any(v == "unresolved" for v in p["risk_flags"].values()):
                fail(
                    "fail_closed_unresolved_risk",
                    "%s eligible with an unresolved risk flag" % pid,
                )

    # Two proposals normalizing alike must be a declared ambiguity, not a
    # silent collision.
    for norm, group in sorted(by_norm.items()):
        if len(group) < 2:
            continue
        if not all(len(g["proposed_target"]["ambiguity_set"]) > 1 for g in group):
            fail(
                "normalization_collision_declared",
                "%r shared by %s without all being ambiguity sets"
                % (norm, [g["proposal_id"] for g in group]),
            )


def recompute_blockers(p):
    blocked = []
    for role, key in (("clinical", "clinical_review"), ("product", "product_review")):
        d = p[key]["decision"]
        if d not in APPROVED_STATES:
            blocked.append("%s_review_%s" % (role, d))
        elif not p[key]["reviewer"]:
            blocked.append("%s_review_missing_reviewer" % role)
    for flag, value in sorted(p["risk_flags"].items()):
        if value == "unresolved":
            blocked.append("unresolved_risk_flag:%s" % flag)
    prov = p["provenance"]
    for field in (
        "source_repository",
        "source_path",
        "source_record",
        "authoring_context",
    ):
        if not prov.get(field):
            blocked.append("missing_provenance:%s" % field)
    if prov.get("approval_record") in ("proposed_unreviewed", "unresolved"):
        blocked.append("no_approval_record")
    if p["primary_change_class"] in BLOCKING_CLASSES:
        blocked.append("blocking_change_class:%s" % p["primary_change_class"])
    if p["primary_change_class"] == "insufficient_evidence_do_not_propose":
        blocked.append("insufficient_evidence")
    return sorted(set(blocked))


def check_alias_graph(review):
    """No alias may target another alias, and no cycle may exist."""
    edges = {}
    for p in proposals_of(review):
        if p["primary_change_class"] != "search_alias":
            continue
        target = p["proposed_target"]["canonical_token_id"]
        if target is None:
            fail("alias_has_target", "%s is a search alias with no target" % p["proposal_id"])
            continue
        edges[normalize(p["phrase"])] = target

    for src, target in sorted(edges.items()):
        if normalize(target.replace("_", " ")) in edges:
            fail(
                "no_alias_targets_an_alias",
                "%r targets %s, which is itself an alias source" % (src, target),
            )

    # Cycle detection over the alias graph.
    for start in sorted(edges):
        seen = {start}
        cursor = edges.get(start)
        while cursor is not None:
            key = normalize(cursor.replace("_", " "))
            if key in seen:
                fail("no_alias_cycles", "cycle reached from %r" % start)
                break
            seen.add(key)
            cursor = edges.get(key)


def check_labels(labels, token_ids):
    rows = labels["rows"]
    if len(rows) != len(token_ids):
        fail(
            "display_label_covers_every_token",
            "%d rows for %d tokens" % (len(rows), len(token_ids)),
        )
    seen = set()
    for r in rows:
        tid = r["token_id"]
        if tid not in token_ids:
            fail("label_row_resolves", "unknown token %s" % tid)
        if tid in seen:
            fail("label_row_unique", "duplicate %s" % tid)
        seen.add(tid)
        if r["display_safe_current"]:
            fail("no_token_is_display_safe", tid)
        if r["display_safe_proposal"] != "not_proposed":
            fail("no_display_safe_proposed_yet", tid)
        for role in ("product_review", "clinical_review"):
            if r[role]["decision"] != "pending":
                fail("label_reviews_pending", "%s %s" % (tid, role))
    missing = token_ids - seen
    if missing:
        fail("display_label_covers_every_token", "missing %s" % sorted(missing)[:5])


PHI_PATTERNS = [
    (r"\b\d{11}\b", "11-digit number (possible NIN/phone)"),
    (r"\b\+?234\d{10}\b", "Nigerian phone number"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "email address"),
    (r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\b", "timestamp with time of day"),
]


def check_content_safety(review, labels):
    blobs = [
        ("catalogue_review_v1.json", json.dumps(review)),
        ("display_label_review_v1.json", json.dumps(labels)),
    ]
    for name, blob in blobs:
        for pattern, what in PHI_PATTERNS:
            for m in re.finditer(pattern, blob):
                # The vendored Mobile commit and generator metadata are hex/ids,
                # not PHI; only flag matches that look like personal data.
                fail("no_phi_shaped_content", "%s contains %s: %s" % (name, what, m.group(0)))


def main():
    review = load_json(REVIEW)
    labels = load_json(LABELS)
    candidate = load_json(CANDIDATE)
    token_ids = {t["token_id"] for t in candidate["tokens"]}

    kb = load_json(repo_path("kb.ng.v2.4.json"))
    rules = load_json(repo_path("rules.ng.v2.2.json"))
    scoring = {
        s["token"]
        for c in kb["conditions"]
        for s in c.get("symptoms", [])
        if s.get("token")
    }
    red_flag = set()
    for r in rules["rules"]:
        for t in r.get("trigger_tokens", []) or []:
            red_flag.add(t)
    for c in kb["conditions"]:
        for t in c.get("red_flags", []) or []:
            if isinstance(t, str):
                red_flag.add(t)

    check_frozen()
    check_reproducible()
    check_proposals(review, token_ids, scoring, red_flag)
    check_alias_graph(review)
    check_labels(labels, token_ids)
    check_content_safety(review, labels)

    # The package must claim no approval anywhere.
    meta = review["_metadata"]
    if meta.get("is_clinical_approval") is not False:
        fail("package_claims_no_clinical_approval", "is_clinical_approval is not False")
    if meta.get("is_product_approval") is not False:
        fail("package_claims_no_product_approval", "is_product_approval is not False")

    eligible = [p for p in proposals_of(review) if p["publication_eligible"]]
    if eligible:
        fail(
            "nothing_is_publication_eligible_yet",
            "%s" % [p["proposal_id"] for p in eligible],
        )

    if failures:
        print("FAIL catalogue validation — %d problem(s)" % len(failures))
        for f in failures:
            print("       %s" % f)
        return 1

    total = len(proposals_of(review))
    print(
        "OK   catalogue validation — %d proposals, %d label rows, "
        "0 publication-eligible" % (total, len(labels["rows"]))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
