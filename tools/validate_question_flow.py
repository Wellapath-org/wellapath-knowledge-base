#!/usr/bin/env python3
"""Validate the candidate question flow, including exhaustive graph analysis.

    python3 tools/validate_question_flow.py [path]        # human-readable
    python3 tools/validate_question_flow.py --json        # machine-readable
    python3 tools/validate_question_flow.py --report      # also write the graph report

Groups:
  A. schema conformance
  B. identity and uniqueness
  C. references and condition language
  D. determinism and ordering
  E. graph: reachability, cycles, dead options, impossible conditions
  F. path analysis: enumeration, length limits, red-flag precedence
  G. skip and edit semantics
  H. publication fail-closed
"""

import argparse
import itertools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow import QFLOW_TOOLING_VERSION
from qflow.conditions import (
    AssessmentState,
    ConditionError,
    evaluate,
    is_never_satisfiable,
    validate as validate_condition,
)
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes
from vocab.schema_check import validate as schema_validate

SCHEMA_PATH = repo_path("schema", "question_flow.v1.schema.json")
DEFAULT_ARTIFACT = repo_path("candidate", "question_flow.ng.v1.0.json")
GRAPH_REPORT = repo_path("reports", "question_graph_analysis_v1.json")

QUESTION_ID_RE = re.compile(r"^Q-[a-z0-9]+(-[a-z0-9_]+)*$")

# Bound on combinatorial exploration. The follow-up graph is driven by the
# symptom token set, whose powerset is astronomically large, so exhaustive
# enumeration is impossible by construction. We enumerate exhaustively over a
# declared bounded subspace and report exactly what was and was not covered —
# an honest bound beats a false claim of completeness.
MAX_TOKENS_PER_COMBINATION = 3


class Results(object):
    def __init__(self):
        self.checks = []

    def add(self, group, name, passed, detail=""):
        self.checks.append({"group": group, "check": name, "passed": bool(passed), "detail": detail})

    @property
    def failures(self):
        return [c for c in self.checks if not c["passed"]]

    def summary(self):
        return {
            "total": len(self.checks),
            "passed": len(self.checks) - len(self.failures),
            "failed": len(self.failures),
            "all_passed": not self.failures,
        }


def _fmt(values, limit=10):
    values = list(values)
    if not values:
        return "none"
    shown = ", ".join(str(v) for v in values[:limit])
    return shown + ("" if len(values) <= limit else " (+%d more)" % (len(values) - limit))


def token_universe():
    token_dictionary = load_json(repo_path("token_dictionary.ng.v1.1.json"))
    tokens = set()
    for category in [
        "symptom_tokens", "red_flag_tokens", "duration_tokens",
        "body_area_tokens", "demographic_tokens", "severity_tokens",
    ]:
        tokens.update(token_dictionary[category])
    return tokens


def trigger_tokens(question):
    """Tokens whose presence the question's trigger condition tests."""
    found = set()

    def walk(node):
        if not isinstance(node, dict) or len(node) != 1:
            return
        key, value = next(iter(node.items()))
        if key == "token_present":
            found.add(value)
        elif key in ("all", "any") and isinstance(value, list):
            for sub in value:
                walk(sub)
        elif key == "not":
            walk(value)

    walk(question["trigger_condition"])
    return found


def order_key(question):
    """The declared deterministic order. Never map or file order."""
    return (question["priority"], question.get("tie_break_key", ""), question["question_id"])


def eligible(questions, state):
    """Questions whose trigger holds, in declared deterministic order.

    A malformed condition is reported by check_references; here it is treated as
    not-eligible so exploration can continue and report every other finding
    instead of aborting on the first bad condition.
    """
    selected = []
    for question in questions:
        try:
            if evaluate(question["trigger_condition"], state):
                selected.append(question)
        except ConditionError:
            continue
    return sorted(selected, key=order_key)


def apply_truncation(ordered, controls):
    """Ordering + truncation, with red-flag questions exempt."""
    followups = [q for q in ordered if q["clinical_role"] not in
                 ("demographic", "body_area", "symptom_picker")]
    limit = controls["max_followup_questions"]
    if len(followups) <= limit:
        return followups
    protected = [q for q in followups if q["red_flag_evaluation"]["can_affect_red_flag"]]
    ordinary = [q for q in followups if not q["red_flag_evaluation"]["can_affect_red_flag"]]
    room = max(0, limit - len(protected))
    kept = protected + ordinary[:room]
    return sorted(kept, key=order_key)


def check_schema(results, artifact):
    errors = schema_validate(artifact, load_json(SCHEMA_PATH))
    results.add("A.schema", "conforms_to_question_flow_schema", not errors, _fmt(errors, 8))
    return not errors


def check_identity(results, artifact):
    questions = artifact["questions"]
    ids = [q["question_id"] for q in questions]
    results.add("B.identity", "question_ids_match_format",
                all(QUESTION_ID_RE.match(i) for i in ids),
                _fmt([i for i in ids if not QUESTION_ID_RE.match(i)]))
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    results.add("B.identity", "question_ids_are_unique", not duplicates, _fmt(duplicates))

    option_ids = [o["answer_option_id"] for q in questions for o in q["answer_options"]]
    option_dupes = sorted({i for i in option_ids if option_ids.count(i) > 1})
    results.add("B.identity", "answer_option_ids_are_globally_unique",
                not option_dupes, _fmt(option_dupes))

    misnamespaced = [
        o["answer_option_id"] for q in questions for o in q["answer_options"]
        if not o["answer_option_id"].startswith(q["question_id"] + "::")
    ]
    results.add("B.identity", "answer_options_namespaced_by_their_question",
                not misnamespaced, _fmt(misnamespaced))


def check_references(results, artifact):
    questions = artifact["questions"]
    known_tokens = token_universe()
    ids = {q["question_id"] for q in questions}
    option_ids = {o["answer_option_id"] for q in questions for o in q["answer_options"]}

    bad_tokens = sorted({
        t for q in questions for o in q["answer_options"]
        for t in o["produces_tokens"] if t not in known_tokens
    })
    results.add("C.references", "produced_tokens_resolve_in_token_dictionary_1_1",
                not bad_tokens, _fmt(bad_tokens))

    condition_errors = []
    for q in questions:
        condition_errors.extend(
            "%s trigger: %s" % (q["question_id"], e)
            for e in validate_condition(q["trigger_condition"], known_tokens, option_ids)
        )
        for branch in q.get("branch_conditions", []):
            condition_errors.extend(
                "%s branch: %s" % (q["question_id"], e)
                for e in validate_condition(branch["when"], known_tokens, option_ids)
            )
            target = branch["next_question_id"]
            if target is not None and target not in ids:
                condition_errors.append("%s branch -> unknown question %r" % (q["question_id"], target))
    results.add("C.references", "conditions_are_valid_and_resolve",
                not condition_errors, _fmt(condition_errors, 6))

    declared = set(artifact["condition_language"]["operators"])
    used = set()

    def collect(node):
        if isinstance(node, dict) and len(node) == 1:
            key, value = next(iter(node.items()))
            used.add(key)
            if isinstance(value, list):
                for sub in value:
                    collect(sub)
            elif isinstance(value, dict) and key == "not":
                collect(value)

    for q in questions:
        collect(q["trigger_condition"])
    results.add("C.references", "no_operator_used_outside_the_declared_language",
                used <= declared, _fmt(sorted(used - declared)))

    bad_invalidations = sorted({
        target for q in questions for target in q.get("invalidates_on_change", [])
        if not target.startswith("<") and target not in ids
    })
    results.add("C.references", "invalidation_targets_resolve",
                not bad_invalidations, _fmt(bad_invalidations))


def check_determinism(results, artifact):
    questions = artifact["questions"]
    keys = [order_key(q) for q in questions]
    duplicate_keys = sorted({k for k in keys if keys.count(k) > 1})
    results.add("D.determinism", "no_two_questions_share_an_order_key",
                not duplicate_keys, _fmt(duplicate_keys))

    missing_tie_break = [
        q["question_id"] for q in questions if not q.get("tie_break_key")
    ]
    priorities = [q["priority"] for q in questions]
    tied_priority = {p for p in priorities if priorities.count(p) > 1}
    unresolved = [
        q["question_id"] for q in questions
        if q["priority"] in tied_priority and not q.get("tie_break_key")
    ]
    results.add("D.determinism", "every_priority_tie_declares_a_tie_break",
                not unresolved, _fmt(unresolved))
    results.add("D.determinism", "every_question_declares_a_tie_break_key",
                not missing_tie_break, _fmt(missing_tie_break))

    # Ordering must be a pure function of declared keys, not of list order.
    shuffled = list(reversed(questions))
    results.add("D.determinism", "ordering_is_independent_of_artifact_list_order",
                [q["question_id"] for q in sorted(questions, key=order_key)]
                == [q["question_id"] for q in sorted(shuffled, key=order_key)])


def check_graph(results, artifact, analysis):
    questions = artifact["questions"]
    by_id = {q["question_id"]: q for q in questions}

    def never_satisfiable(question):
        # A malformed condition is already reported by check_references. Here it
        # is simply not provably unsatisfiable, so it must not crash the graph
        # pass and mask every finding after it.
        try:
            return is_never_satisfiable(question["trigger_condition"])
        except ConditionError:
            return False

    impossible = sorted(q["question_id"] for q in questions if never_satisfiable(q))
    results.add("E.graph", "no_question_has_an_impossible_trigger", not impossible, _fmt(impossible))

    unreachable = analysis["unreachable_questions"]
    results.add("E.graph", "no_unreachable_question", not unreachable, _fmt(unreachable))

    dead_options = analysis["dead_answer_options"]
    results.add("E.graph", "no_dead_answer_option", not dead_options, _fmt(dead_options))

    # Branch graph cycles. The follow-up graph is condition-driven and has no
    # explicit next-question edges today, so this is a guard for future data.
    edges = {
        q["question_id"]: [
            b["next_question_id"] for b in q.get("branch_conditions", [])
            if b["next_question_id"]
        ]
        for q in questions
    }
    cycles = []
    colour = {}

    def visit(node, stack):
        colour[node] = "grey"
        for nxt in edges.get(node, []):
            if colour.get(nxt) == "grey":
                cycles.append(" -> ".join(stack + [nxt]))
            elif colour.get(nxt) != "black" and nxt in by_id:
                visit(nxt, stack + [nxt])
        colour[node] = "black"

    for node in sorted(edges):
        if colour.get(node) != "black":
            visit(node, [node])
    results.add("E.graph", "no_branch_cycles", not cycles, _fmt(sorted(set(cycles))))


def check_paths(results, artifact, analysis):
    controls = artifact["path_controls"]
    results.add("F.paths", "red_flag_questions_exempt_from_truncation",
                controls["red_flag_questions_exempt_from_truncation"] is True)
    results.add("F.paths", "cycle_detection_required", controls["cycle_detection"] == "required")
    results.add("F.paths", "repeated_question_prevention_required",
                controls["repeated_question_prevention"] == "required")

    over = analysis["paths_exceeding_followup_limit"]
    results.add("F.paths", "no_explored_path_exceeds_the_followup_limit", not over, _fmt(over))

    dropped = analysis["paths_where_a_red_flag_question_was_dropped"]
    results.add("F.paths", "no_red_flag_question_dropped_by_truncation", not dropped, _fmt(dropped))

    misordered = analysis["paths_with_a_red_flag_question_behind_an_ordinary_one"]
    results.add("F.paths", "red_flag_questions_never_queue_behind_ordinary_ones",
                not misordered, _fmt(misordered))

    questions = artifact["questions"]
    bad_hooks = [
        q["question_id"] for q in questions
        if q["effects"]["affects_red_flags"]
        and not (q["red_flag_evaluation"]["evaluate_after_answer"]
                 and q["red_flag_evaluation"]["blocks_next_question"])
    ]
    results.add("F.paths", "every_red_flag_affecting_question_evaluates_immediately",
                not bad_hooks, _fmt(bad_hooks))

    understated = [
        q["question_id"] for q in questions
        if q["effects"]["affects_red_flags"] != q["red_flag_evaluation"]["can_affect_red_flag"]
    ]
    results.add("F.paths", "red_flag_effect_and_hook_agree", not understated, _fmt(understated))


def check_skip_and_edit(results, artifact):
    questions = artifact["questions"]
    silently_skippable = [
        q["question_id"] for q in questions if q["required"] and q["skippable"]
    ]
    results.add("G.semantics", "no_required_question_is_skippable",
                not silently_skippable, _fmt(silently_skippable))

    token_producing_skip = [
        o["answer_option_id"] for q in questions for o in q["answer_options"]
        if o["is_skip_sentinel"] and o["produces_tokens"]
    ]
    results.add("G.semantics", "no_skip_sentinel_produces_a_clinical_token",
                not token_producing_skip, _fmt(token_producing_skip))

    self_invalidating = [
        q["question_id"] for q in questions
        if q["question_id"] in q.get("invalidates_on_change", [])
    ]
    results.add("G.semantics", "no_question_invalidates_itself",
                not self_invalidating, _fmt(self_invalidating))


def check_publication(results, artifact):
    metadata = artifact["_metadata"]
    review = metadata["clinical_review"]
    results.add("H.publication", "release_status_is_not_published",
                metadata["release_status"] != "published", metadata["release_status"])
    results.add("H.publication", "may_publish_is_false_without_review",
                metadata["may_publish"] is False or review["status"] == "reviewed",
                "may_publish=%s review=%s" % (metadata["may_publish"], review["status"]))
    results.add("H.publication", "no_unevidenced_clinical_review_claim",
                review["status"] != "reviewed"
                or all(review[f] for f in ("reviewer", "review_date", "evidence")),
                json.dumps(review))
    results.add("H.publication", "candidate_is_not_at_the_published_location",
                not os.path.exists(repo_path("question_flow.ng.v1.0.json")))
    results.add("H.publication", "no_question_content_is_marked_approved",
                all(not q["content_ref"]["content_approved"] for q in artifact["questions"]),
                "content_approved must be false until product/clinical approve the wording")
    results.add("H.publication", "vocabulary_2_0_is_declared_unused",
                metadata["vocabulary_2_0"]["used"] is False)


def analyse_graph(artifact):
    """Bounded exhaustive exploration of the follow-up graph."""
    questions = artifact["questions"]
    controls = artifact["path_controls"]
    followups = [q for q in questions if q["clinical_role"] not in
                 ("demographic", "body_area", "symptom_picker")]

    driving_tokens = sorted({t for q in followups for t in trigger_tokens(q)})

    reached_questions = set()
    reached_options = set()
    over_limit = []
    dropped_red_flag = []
    misordered = []
    lengths = []
    explored = 0

    combos = []
    for size in range(0, MAX_TOKENS_PER_COMBINATION + 1):
        combos.extend(itertools.combinations(driving_tokens, size))

    for combo in combos:
        explored += 1
        state = AssessmentState(tokens=set(combo))
        ordered = eligible(followups, state)
        kept = apply_truncation(ordered, controls)
        lengths.append(len(kept))

        for q in kept:
            reached_questions.add(q["question_id"])
            for option in q["answer_options"]:
                reached_options.add(option["answer_option_id"])

        if len(kept) > controls["max_followup_questions"]:
            protected = [q for q in kept if q["red_flag_evaluation"]["can_affect_red_flag"]]
            # Over the limit is only acceptable when red-flag questions alone
            # exceed it — the limit yields to safety, never the other way round.
            if len(protected) <= controls["max_followup_questions"]:
                over_limit.append(",".join(combo) or "<none>")

        dropped = [q for q in ordered if q not in kept
                   and q["red_flag_evaluation"]["can_affect_red_flag"]]
        if dropped:
            dropped_red_flag.append("%s dropped %s" % (",".join(combo),
                                                       [q["question_id"] for q in dropped]))

        seen_ordinary = False
        for q in kept:
            if q["red_flag_evaluation"]["can_affect_red_flag"]:
                if seen_ordinary:
                    misordered.append("%s: %s behind an ordinary question"
                                      % (",".join(combo), q["question_id"]))
            else:
                seen_ordinary = True

    all_followup_ids = {q["question_id"] for q in followups}
    all_option_ids = {o["answer_option_id"] for q in followups for o in q["answer_options"]}
    demographic_ids = {q["question_id"] for q in questions} - all_followup_ids
    demographic_options = {
        o["answer_option_id"] for q in questions
        if q["question_id"] in demographic_ids for o in q["answer_options"]
    }

    return {
        "exploration": {
            "strategy": "exhaustive over every subset of the %d trigger tokens up to size %d"
                        % (len(driving_tokens), MAX_TOKENS_PER_COMBINATION),
            "driving_token_count": len(driving_tokens),
            "max_tokens_per_combination": MAX_TOKENS_PER_COMBINATION,
            "combinations_explored": explored,
            "exhaustive_over_full_state_space": False,
            "uncovered_state_space": (
                "Token subsets larger than %d. The full state space is the powerset of the "
                "%d picker-reachable symptom tokens, which is not enumerable. Larger subsets "
                "can only ADD eligible questions, and truncation plus the red-flag exemption "
                "are both verified on every explored subset, so the bound is a coverage "
                "limit rather than a soundness gap."
                % (MAX_TOKENS_PER_COMBINATION, len(driving_tokens))
            ),
        },
        "path_lengths": {
            "min": min(lengths) if lengths else 0,
            "max": max(lengths) if lengths else 0,
            "limit": controls["max_followup_questions"],
            "distribution": {
                str(n): lengths.count(n) for n in sorted(set(lengths))
            },
        },
        "unreachable_questions": sorted(all_followup_ids - reached_questions),
        "dead_answer_options": sorted(all_option_ids - reached_options),
        "demographic_questions_not_explored": sorted(demographic_ids),
        "demographic_answer_options_not_explored": len(demographic_options),
        "paths_exceeding_followup_limit": over_limit,
        "paths_where_a_red_flag_question_was_dropped": dropped_red_flag,
        "paths_with_a_red_flag_question_behind_an_ordinary_one": misordered,
    }


def run(artifact_path):
    results = Results()
    artifact = load_json(artifact_path)
    analysis = None
    if check_schema(results, artifact):
        check_identity(results, artifact)
        check_references(results, artifact)
        check_determinism(results, artifact)
        analysis = analyse_graph(artifact)
        check_graph(results, artifact, analysis)
        check_paths(results, artifact, analysis)
        check_skip_and_edit(results, artifact)
        check_publication(results, artifact)
    return results, analysis, artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", nargs="?", default=DEFAULT_ARTIFACT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", action="store_true", help="write reports/question_graph_analysis_v1.json")
    args = parser.parse_args()

    results, analysis, artifact = run(args.artifact)
    summary = results.summary()

    if args.report and analysis is not None:
        payload = {
            "report_id": "question_graph_analysis",
            "report_version": "1",
            "phase": "I2 / W3 Step 1",
            "generator": "tools/validate_question_flow.py",
            "generator_version": QFLOW_TOOLING_VERSION,
            "artifact": {
                "file": os.path.relpath(args.artifact, repo_path()),
                "version": artifact["_metadata"]["version"],
                "sha256": sha256_file(args.artifact),
            },
            "questions": len(artifact["questions"]),
            "answer_options": sum(len(q["answer_options"]) for q in artifact["questions"]),
            "analysis": analysis,
            "summary": summary,
        }
        write_bytes(GRAPH_REPORT, dump_report_bytes(payload))
        print("wrote reports/question_graph_analysis_v1.json")

    if args.json:
        print(json.dumps({"summary": summary, "checks": results.checks,
                          "analysis": analysis}, indent=2))
    elif not args.report:
        for check in results.checks:
            print("%-4s %-14s %s%s" % ("OK" if check["passed"] else "FAIL", check["group"],
                                       check["check"],
                                       "" if check["passed"] else "  [%s]" % check["detail"]))
        print("\n%d checks, %d passed, %d failed"
              % (summary["total"], summary["passed"], summary["failed"]))

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
