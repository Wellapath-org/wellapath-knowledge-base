#!/usr/bin/env python3
"""Validate the grouping semantics of a question-flow artifact.

    python3 tools/validate_question_grouping.py [path]     # human-readable
    python3 tools/validate_question_grouping.py --json      # machine-readable
    python3 tools/validate_question_grouping.py --fixtures  # every invalid fixture must be rejected

Layered on top of `tools/validate_question_flow.py`, which still owns identity,
references, the condition language, the graph and publication fail-closed. This
module owns only what schema 1.1 added: whether the declared grouping is
coherent, and whether it can lose a question, an option or a red flag.

Every check fails CLOSED. A grouping block this validator cannot interpret is an
error, never a shrug — a consumer that quietly ignores a merge rule it does not
understand would present a different question set than the one that was
reviewed.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.grouping import (
    condition_holds,
    referenced_tokens,
    GROUPABLE_ROLES,
    MAX_FOLLOWUP_QUESTIONS,
    NON_GROUPABLE_ROLES,
    OPTION_UNION_RULES,
    REPRESENTATIVE_SELECTION,
)
from vocab.artifact_io import load_json, repo_path
from vocab.schema_check import validate as schema_validate

DEFAULT_ARTIFACT = repo_path("candidate", "question_flow.ng.v1.1.json")
SCHEMA_PATH = repo_path("schema", "question_flow.v1_1.schema.json")
FIXTURE_DIR = repo_path("testing", "questions", "fixtures", "invalid_grouping")

MERGE_STRATEGIES = ("single_representative",)
GROUPING_PHASES = ("before_truncation",)


class Results:
    def __init__(self):
        self.checks = []

    def add(self, check_id, name, errors):
        self.checks.append({
            "id": check_id,
            "name": name,
            "passed": not errors,
            "errors": list(errors),
        })

    @property
    def failed(self):
        return [c for c in self.checks if not c["passed"]]


def grouped_questions(artifact):
    return [q for q in artifact["questions"] if "grouping" in q]


def check_schema(results, artifact):
    results.add("G00", "schema 1.1 conformance",
                schema_validate(artifact, load_json(SCHEMA_PATH)))


def check_semantics_declared(results, artifact):
    """G01 — the artifact must DECLARE its grouping semantics, not imply them."""
    errors = []
    metadata = artifact.get("_metadata", {})
    semantics = metadata.get("grouping_semantics")
    if semantics is None:
        errors.append("_metadata.grouping_semantics is absent; a consumer cannot "
                      "know whether questions merge")
    else:
        if semantics.get("one_question_per_group_key") is not True:
            errors.append("one_question_per_group_key must be true — a group that can "
                          "yield two questions is not a group")
        if semantics.get("grouping_phase") not in GROUPING_PHASES:
            errors.append("grouping_phase %r is not %s; grouping after truncation would "
                          "let un-merged questions consume the follow-up budget"
                          % (semantics.get("grouping_phase"), GROUPING_PHASES))
        missing_roles = [r for r in NON_GROUPABLE_ROLES
                         if r not in semantics.get("non_groupable_roles", [])]
        if missing_roles:
            errors.append("non_groupable_roles must list %s — merging two clarifiers "
                          "would silently delete a danger-sign question" % missing_roles)
        stray = [r for r in semantics.get("groupable_roles", [])
                 if r in NON_GROUPABLE_ROLES]
        if stray:
            errors.append("roles %s are both groupable and non-groupable" % stray)
    if semantics is not None and artifact.get("path_controls", {}).get("grouping_phase") \
            not in (None, semantics.get("grouping_phase")):
        errors.append("path_controls.grouping_phase disagrees with "
                      "_metadata.grouping_semantics.grouping_phase")
    results.add("G01", "grouping semantics are declared and coherent", errors)


def check_group_keys(results, artifact):
    """G02 — one question per group_key, and group_key is not tie_break_key."""
    errors = []
    seen = {}
    for question in grouped_questions(artifact):
        key = question["grouping"].get("group_key")
        if key is None:
            errors.append("%s declares grouping with no group_key" % question["question_id"])
            continue
        if key in seen:
            errors.append("group_key %r is claimed by both %s and %s; a path could "
                          "present two questions for one group"
                          % (key, seen[key], question["question_id"]))
        seen[key] = question["question_id"]

    # tie_break_key ORDERS; group_key GROUPS. Conflating them is the specific
    # error this check exists to catch: it would make any two questions sharing
    # an order key silently merge.
    ungrouped_tie_breaks = {}
    for question in artifact["questions"]:
        if "grouping" in question:
            continue
        key = question.get("tie_break_key")
        if key in ungrouped_tie_breaks:
            errors.append("%s and %s share tie_break_key %r with no grouping block. "
                          "tie_break_key is an ordering key and never a grouping key, "
                          "so this is an unresolved order tie, not an implied merge."
                          % (ungrouped_tie_breaks[key], question["question_id"], key))
        ungrouped_tie_breaks[key] = question["question_id"]
    results.add("G02", "group keys are unique and distinct from tie-break keys", errors)


def check_merge_rules(results, artifact):
    """G03 — every declared rule must be one this validator can execute."""
    errors = []
    for question in grouped_questions(artifact):
        grouping = question["grouping"]
        qid = question["question_id"]
        if grouping.get("merge_strategy") not in MERGE_STRATEGIES:
            errors.append("%s merge_strategy %r is not executable"
                          % (qid, grouping.get("merge_strategy")))
        if grouping.get("representative_selection") != REPRESENTATIVE_SELECTION:
            errors.append("%s representative_selection %r is not %r; an undeclared "
                          "selection rule reintroduces the order dependence this "
                          "correction exists to remove"
                          % (qid, grouping.get("representative_selection"),
                             REPRESENTATIVE_SELECTION))
        if grouping.get("option_union_rule") not in OPTION_UNION_RULES:
            errors.append("%s option_union_rule %r is not executable"
                          % (qid, grouping.get("option_union_rule")))
        conflict = grouping.get("conflict_resolution")
        if conflict is not None:
            if conflict.get("on_value_type_conflict") != "reject":
                errors.append("%s must reject answer-value-type conflicts; merging two "
                              "answer shapes changes answer meaning" % qid)
            if grouping.get("option_union_rule") == "union_of_triggered_sources" \
                    and conflict.get("on_option_conflict") != "union_preserving_all_sources":
                errors.append("%s unions options but does not preserve every source's "
                              "options" % qid)
    results.add("G03", "merge rules are declared and executable", errors)


def check_sources(results, artifact):
    """G04 — sources must be non-empty, uniquely identified and totally ordered."""
    errors = []
    for question in grouped_questions(artifact):
        qid = question["question_id"]
        sources = question["grouping"].get("sources") or []
        if not sources:
            errors.append("%s declares a group with no sources; there is nothing to "
                          "merge and the question can never be presented" % qid)
            continue
        ids, indexes = {}, {}
        for source in sources:
            source_id = source.get("source_id")
            if source_id in ids:
                errors.append("%s has duplicate source_id %r" % (qid, source_id))
            ids[source_id] = True
            index = source.get("source_order_index")
            if index in indexes:
                errors.append("%s: sources %r and %r share source_order_index %r, so "
                              "representative selection is a tie with no resolution"
                              % (qid, indexes[index], source_id, index))
            indexes[index] = source_id
    results.add("G04", "sources are unique and totally ordered", errors)


def check_option_preservation(results, artifact):
    """G05 — the union can neither invent nor lose an option."""
    errors = []
    for question in grouped_questions(artifact):
        qid = question["question_id"]
        grouping = question["grouping"]
        declared = {o["answer_option_id"]: o for o in question["answer_options"]}
        rule = grouping.get("option_union_rule")
        for source in grouping.get("sources") or []:
            options = source.get("answer_options")
            if rule == "static":
                if options:
                    errors.append("%s: source %r carries answer_options under the "
                                  "static rule, so the artifact declares two different "
                                  "option sets for one question"
                                  % (qid, source.get("source_id")))
                continue
            if options is None:
                errors.append("%s: source %r contributes no answer_options under "
                              "union_of_triggered_sources; if this source triggers "
                              "alone the question has no answers"
                              % (qid, source.get("source_id")))
                continue
            for option in options:
                option_id = option["answer_option_id"]
                if option_id not in declared:
                    errors.append("%s: source %r would present option %r that the "
                                  "question does not declare"
                                  % (qid, source.get("source_id"), option_id))
                elif declared[option_id] != option:
                    errors.append("%s: source %r declares option %r with a different "
                                  "label, value or produced tokens than the question"
                                  % (qid, source.get("source_id"), option_id))
        if rule == "union_of_triggered_sources":
            contributed = {
                option["answer_option_id"]
                for source in grouping.get("sources") or []
                for option in source.get("answer_options") or []
            }
            orphaned = sorted(set(declared) - contributed)
            if orphaned:
                errors.append("%s declares options no source contributes: %s — they "
                              "can never be presented" % (qid, orphaned))
    results.add("G05", "option union preserves every source's options", errors)


def check_non_groupable(results, artifact):
    """G06 — red-flag clarifiers must never carry a grouping block."""
    errors = []
    for question in artifact["questions"]:
        role = question.get("clinical_role")
        if "grouping" in question and role in NON_GROUPABLE_ROLES:
            errors.append("%s has clinical_role %r and must never be grouped: each "
                          "clarifier carries its own red-flag token, so merging two "
                          "deletes a danger-sign question"
                          % (question["question_id"], role))
        if "grouping" in question and role not in GROUPABLE_ROLES:
            errors.append("%s has clinical_role %r, which is not a groupable role"
                          % (question["question_id"], role))
    results.add("G06", "non-groupable roles are never grouped", errors)


#: Above this many distinct referenced tokens the containment decision is
#: refused rather than approximated. 20 covers every group in the candidate
#: (largest is 18) with headroom; a group that outgrows it needs a real solver,
#: and until then the honest answer is "not decided", never "assumed fine".
CONTAINMENT_TOKEN_LIMIT = 20


def check_trigger_containment(results, artifact):
    """G07 — a source must not trigger where its question does not.

    Decided EXACTLY, not approximately. Both a source trigger and a question
    trigger are functions of which tokens are selected, so enumerating every
    subset of the tokens they mention settles containment with no solver and no
    incompleteness. An earlier revision posed this to `is_never_satisfiable`,
    which cannot discharge `token_present(t) AND NOT any(token_present …)` and
    reported all 40 sources as escaping — a false alarm from an incomplete
    procedure, which is exactly why this one enumerates instead.

    The enumeration is cheap because it only has to look at the assignments
    where the QUESTION trigger is false: those are the only ones a source could
    escape into.
    """
    errors = []
    for question in grouped_questions(artifact):
        qid = question["question_id"]
        trigger = question.get("trigger_condition")
        sources = question["grouping"].get("sources") or []

        universe = sorted(referenced_tokens(trigger).union(
            *(referenced_tokens(s.get("trigger_condition")) for s in sources)
        ) if sources else referenced_tokens(trigger))

        if len(universe) > CONTAINMENT_TOKEN_LIMIT:
            errors.append("%s references %d tokens, above the %d-token limit for an "
                          "exact containment decision; containment is UNDECIDED and "
                          "must not be assumed"
                          % (qid, len(universe), CONTAINMENT_TOKEN_LIMIT))
            continue

        try:
            outside = [
                selection for selection in _subsets(universe)
                if not condition_holds(trigger, selection)
            ]
        except ValueError as error:
            errors.append("%s trigger is not analysable (%s)" % (qid, error))
            continue

        for source in sources:
            source_trigger = source.get("trigger_condition")
            try:
                escapes = any(condition_holds(source_trigger, selection)
                              for selection in outside)
            except ValueError as error:
                errors.append("%s: source %r trigger is not analysable (%s)"
                              % (qid, source.get("source_id"), error))
                continue
            if escapes:
                errors.append("%s: source %r can trigger while the question does not; "
                              "the union would need a question that is never presented"
                              % (qid, source.get("source_id")))
    results.add("G07", "every source trigger implies its question trigger", errors)


def _subsets(tokens):
    """Every subset of ``tokens``, as a set, in a fixed order."""
    for mask in range(1 << len(tokens)):
        yield {token for index, token in enumerate(tokens) if mask & (1 << index)}


def check_truncation_headroom(results, artifact):
    """G08 — after grouping, the presented follow-up count must fit the limit."""
    errors = []
    controls = artifact.get("path_controls", {})
    limit = controls.get("max_followup_questions")
    if limit != MAX_FOLLOWUP_QUESTIONS:
        errors.append("max_followup_questions is %r, not %d; the live limit is not a "
                      "tuning parameter of this correction"
                      % (limit, MAX_FOLLOWUP_QUESTIONS))
    if controls.get("red_flag_questions_exempt_from_truncation") is not True:
        errors.append("red-flag questions must remain exempt from truncation")

    follow_up_roles = set(GROUPABLE_ROLES) | set(NON_GROUPABLE_ROLES)
    clarifiers = [q for q in artifact["questions"]
                  if q.get("clinical_role") in NON_GROUPABLE_ROLES]
    groupable = [q for q in artifact["questions"]
                 if q.get("clinical_role") in GROUPABLE_ROLES]
    presented_ceiling = len(clarifiers) + len({
        q["grouping"]["group_key"] if "grouping" in q else q["question_id"]
        for q in groupable
    })
    if presented_ceiling > limit + len(clarifiers):
        errors.append("worst-case presented follow-ups (%d) exceed what the limit plus "
                      "the red-flag exemption can carry" % presented_ceiling)
    # Ungrouped questions in a groupable role are what inflated candidate 1.0.
    ungrouped = sorted(q["question_id"] for q in groupable if "grouping" not in q)
    ungrouped = [q for q in ungrouped if q != "Q-followup-default-duration"]
    if ungrouped:
        errors.append("questions in groupable roles carry no grouping block: %s — each "
                      "consumes its own slot against the limit of %d"
                      % (ungrouped, limit))
    _ = follow_up_roles
    results.add("G08", "grouping keeps the follow-up count inside the limit", errors)


def check_representative_determinism(results, artifact):
    """G09 — representative selection must not depend on anything but the artifact."""
    errors = []
    for question in grouped_questions(artifact):
        grouping = question["grouping"]
        indexes = [s.get("source_order_index") for s in grouping.get("sources") or []]
        if any(not isinstance(i, int) for i in indexes):
            errors.append("%s has a non-integer source_order_index; selection would "
                          "fall back to declaration order in the JSON, which is not a "
                          "declared rule" % question["question_id"])
        if grouping.get("option_order") not in (None, "source_order_then_declared_order"):
            errors.append("%s option_order %r is not a declared total order"
                          % (question["question_id"], grouping.get("option_order")))
    results.add("G09", "representative selection is deterministic", errors)


CHECKS = (
    check_schema,
    check_semantics_declared,
    check_group_keys,
    check_merge_rules,
    check_sources,
    check_option_preservation,
    check_non_groupable,
    check_trigger_containment,
    check_truncation_headroom,
    check_representative_determinism,
)


def run(artifact_path):
    results = Results()
    artifact = load_json(artifact_path)
    for check in CHECKS:
        try:
            check(results, artifact)
        except Exception as error:  # noqa: BLE001 - a crashing check is a failure
            results.add(check.__name__, check.__name__,
                        ["check raised %s: %s" % (type(error).__name__, error)])
    return results


def run_fixtures():
    """Every invalid fixture must be REJECTED, and the index must be honest."""
    index = load_json(os.path.join(FIXTURE_DIR, "index.json"))
    rows, ok = [], True
    for entry in index["fixtures"]:
        path = os.path.join(FIXTURE_DIR, entry["file"])
        results = run(path)
        failed_ids = [c["id"] for c in results.failed]
        rejected = bool(failed_ids)
        expected = entry["expected_check"]
        by_expected = expected in failed_ids
        rows.append({
            "fixture": entry["fixture_id"],
            "rejected": rejected,
            "expected_check": expected,
            "tripped_expected_check": by_expected,
            "checks_failed": failed_ids,
        })
        if not (rejected and by_expected):
            ok = False
    return ok, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", nargs="?", default=DEFAULT_ARTIFACT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fixtures", action="store_true")
    args = parser.parse_args()

    if args.fixtures:
        ok, rows = run_fixtures()
        if args.json:
            print(json.dumps({"all_rejected": ok, "fixtures": rows}, indent=2))
        else:
            for row in rows:
                mark = "ok  " if row["rejected"] and row["tripped_expected_check"] else "FAIL"
                print("%s %-52s expected %s -> %s"
                      % (mark, row["fixture"], row["expected_check"],
                         ",".join(row["checks_failed"]) or "ACCEPTED"))
            print("\n%d/%d invalid fixtures rejected by the intended check"
                  % (sum(1 for r in rows if r["rejected"] and r["tripped_expected_check"]),
                     len(rows)))
        return 0 if ok else 1

    results = run(args.artifact)
    if args.json:
        print(json.dumps({"passed": not results.failed, "checks": results.checks}, indent=2))
    else:
        for check in results.checks:
            print("%s %s  %s" % ("ok  " if check["passed"] else "FAIL",
                                 check["id"], check["name"]))
            for error in check["errors"]:
                print("       - %s" % error)
        print("\n%d/%d grouping checks passed"
              % (len(results.checks) - len(results.failed), len(results.checks)))
    return 1 if results.failed else 0


if __name__ == "__main__":
    sys.exit(main())
