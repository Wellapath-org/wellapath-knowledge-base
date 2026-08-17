#!/usr/bin/env python3
"""Generate invalid grouping fixtures, one per way grouping can go wrong.

    python3 tools/build_grouping_invalid_fixtures.py            # build
    python3 tools/build_grouping_invalid_fixtures.py --check    # fail if stale

Each fixture is candidate 1.1 with exactly ONE defect introduced, and each names
the check that must reject it. A fixture that is rejected by some OTHER check is
reported as a failure, not quietly counted as a pass: that would prove only that
the artifact is broken, not that the intended guard works.

These are the mutation tests for the grouping contract. Without them, a check
that never fires is indistinguishable from a check that cannot fire.
"""

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    write_bytes,
)

CANDIDATE_PATH = repo_path("candidate", "question_flow.ng.v1.1.json")
FIXTURE_DIR = repo_path("testing", "questions", "fixtures", "invalid_grouping")
GENERATOR = "tools/build_grouping_invalid_fixtures.py"

ADDITIONAL = "Q-followup-additional-symptoms"
SEVERITY = "Q-followup-severity"
DURATION = "Q-followup-duration"


def find(artifact, question_id):
    for question in artifact["questions"]:
        if question["question_id"] == question_id:
            return question
    raise SystemExit("fixture base has no question %r" % question_id)


# --- mutations -------------------------------------------------------------
# Each takes the artifact and breaks exactly one thing.

def m_unknown_grouping_field(artifact):
    find(artifact, SEVERITY)["grouping"]["merge_window_ms"] = 250


def m_semantics_absent(artifact):
    del artifact["_metadata"]["grouping_semantics"]


def m_phase_after_truncation(artifact):
    artifact["_metadata"]["grouping_semantics"]["grouping_phase"] = "after_truncation"
    artifact["path_controls"]["grouping_phase"] = "after_truncation"


def m_clarifier_role_declared_groupable(artifact):
    artifact["_metadata"]["grouping_semantics"]["non_groupable_roles"] = []


def m_group_can_yield_two_questions(artifact):
    artifact["_metadata"]["grouping_semantics"]["one_question_per_group_key"] = False


def m_duplicate_group_key(artifact):
    find(artifact, DURATION)["grouping"]["group_key"] = \
        find(artifact, SEVERITY)["grouping"]["group_key"]


def m_tie_break_reused_as_group_key(artifact):
    """The specific misuse the contract forbids: two questions given the same
    ordering key and no grouping block, as if sharing tie_break_key implied a
    merge. It does not — it is an unresolved order tie."""
    question = find(artifact, "Q-followup-default-duration")
    question["tie_break_key"] = find(artifact, "Q-demo-age")["tie_break_key"]


def m_unknown_representative_selection(artifact):
    find(artifact, SEVERITY)["grouping"]["representative_selection"] = "first_selected_by_user"


def m_unknown_option_union_rule(artifact):
    find(artifact, ADDITIONAL)["grouping"]["option_union_rule"] = "intersection_of_sources"


def m_option_conflict_not_preserving(artifact):
    find(artifact, ADDITIONAL)["grouping"]["conflict_resolution"]["on_option_conflict"] = "reject"


def m_value_type_conflict_accepted(artifact):
    find(artifact, SEVERITY)["grouping"]["conflict_resolution"]["on_value_type_conflict"] = \
        "representative_wins"


def m_empty_sources(artifact):
    find(artifact, SEVERITY)["grouping"]["sources"] = []


def m_duplicate_source_id(artifact):
    sources = find(artifact, DURATION)["grouping"]["sources"]
    sources[1]["source_id"] = sources[0]["source_id"]


def m_duplicate_source_order_index(artifact):
    sources = find(artifact, DURATION)["grouping"]["sources"]
    sources[1]["source_order_index"] = sources[0]["source_order_index"]


def m_source_option_not_declared(artifact):
    question = find(artifact, ADDITIONAL)
    source = question["grouping"]["sources"][0]
    source["answer_options"] = source["answer_options"] + [{
        "answer_option_id": "%s::invented_symptom" % ADDITIONAL,
        "label": "invented_symptom",
        "produces_tokens": ["invented_symptom"],
        "is_skip_sentinel": False,
        "value": "invented_symptom",
    }]


def m_source_option_dropped(artifact):
    """An option the question declares that no source contributes any more —
    it can never be presented, so a reviewer would approve content no user sees."""
    question = find(artifact, ADDITIONAL)
    victim = question["answer_options"][0]["answer_option_id"]
    for source in question["grouping"]["sources"]:
        source["answer_options"] = [
            option for option in source["answer_options"]
            if option["answer_option_id"] != victim
        ]


def m_source_option_relabelled(artifact):
    question = find(artifact, ADDITIONAL)
    source = question["grouping"]["sources"][0]
    source["answer_options"][0] = dict(source["answer_options"][0], label="Something else")


def m_static_rule_with_source_options(artifact):
    question = find(artifact, SEVERITY)
    question["grouping"]["sources"][0]["answer_options"] = question["answer_options"][:1]


def m_clarifier_grouped(artifact):
    question = find(artifact, "Q-clarifier-abnormal_bleeding")
    question["grouping"] = {
        "group_key": "red_flag",
        "merge_strategy": "single_representative",
        "representative_selection": "lowest_source_order_index",
        "option_union_rule": "static",
        "sources": [{
            "source_id": "red_flag_clarifiers.abnormal_bleeding",
            "source_token": "bleeding",
            "source_order_index": 0,
            "trigger_condition": {"token_present": "bleeding"},
            "source_text": question["content_ref"]["source_text"],
            "provenance": "red_flag_clarifiers.dart",
        }],
    }


def m_source_triggers_outside_question(artifact):
    question = find(artifact, SEVERITY)
    question["grouping"]["sources"][0]["trigger_condition"] = {"token_present": "fever"}


def m_ungrouped_question_in_groupable_role(artifact):
    """The candidate 1.0 shape: a per-token follow-up with no grouping block,
    which consumes its own slot against the limit of 5."""
    question = copy.deepcopy(find(artifact, SEVERITY))
    question["question_id"] = "Q-followup-headache-severity"
    question["tie_break_key"] = "headache"
    question["trigger_condition"] = {"token_present": "headache"}
    question["answer_options"] = [
        dict(option, answer_option_id=option["answer_option_id"].replace(
            SEVERITY, "Q-followup-headache-severity"))
        for option in question["answer_options"]
    ]
    del question["grouping"]
    artifact["questions"].append(question)


def m_source_order_index_not_integer(artifact):
    find(artifact, DURATION)["grouping"]["sources"][0]["source_order_index"] = "0"


FIXTURES = [
    ("grouping_unknown_field", "G00", m_unknown_grouping_field,
     "A grouping block carrying a field schema 1.1 does not define. A consumer would ignore it; the schema must not."),
    ("grouping_semantics_absent", "G01", m_semantics_absent,
     "The artifact groups questions but never declares that it does, so a consumer cannot know to apply a merge rule."),
    ("grouping_phase_after_truncation", "G01", m_phase_after_truncation,
     "Merging after truncation lets un-merged questions consume the follow-up budget and drops questions the live engine asks."),
    ("grouping_clarifier_role_declared_groupable", "G01", m_clarifier_role_declared_groupable,
     "red_flag_clarifier removed from non_groupable_roles — the declaration that stops two danger-sign questions being merged into one."),
    ("grouping_group_can_yield_two_questions", "G01", m_group_can_yield_two_questions,
     "one_question_per_group_key false. A group that can present twice is not a group, and re-inflates the question count."),
    ("grouping_duplicate_group_key", "G02", m_duplicate_group_key,
     "Two questions claim one group_key, so a path can present two questions for a single group."),
    ("grouping_tie_break_key_reused_as_group_key", "G02", m_tie_break_reused_as_group_key,
     "Two ungrouped questions share a tie_break_key. tie_break_key orders and never groups; this is an unresolved order tie, not an implied merge."),
    ("grouping_unknown_representative_selection", "G03", m_unknown_representative_selection,
     "A selection rule naming user order. Accepting it would reintroduce exactly the nondeterminism this correction removes."),
    ("grouping_unknown_option_union_rule", "G03", m_unknown_option_union_rule,
     "An option rule this validator cannot execute. Intersection would silently drop options a triggered source contributes."),
    ("grouping_option_conflict_not_preserving", "G03", m_option_conflict_not_preserving,
     "A unioning group that does not promise to preserve every source's options."),
    ("grouping_value_type_conflict_accepted", "G03", m_value_type_conflict_accepted,
     "Merging different answer shapes by picking one. That changes what an answer MEANS, which no grouping rule may do."),
    ("grouping_empty_sources", "G04", m_empty_sources,
     "A group with nothing to merge. The question can never be presented and its content is unreachable."),
    ("grouping_duplicate_source_id", "G04", m_duplicate_source_id,
     "Two sources share an id, so provenance for the presented wording is ambiguous."),
    ("grouping_duplicate_source_order_index", "G04", m_duplicate_source_order_index,
     "Two sources share an order index, so representative selection is a tie with no declared resolution."),
    ("grouping_source_option_not_declared", "G05", m_source_option_not_declared,
     "A source would present an option the question never declares — an answer with no reviewed content and no ID-keyed home."),
    ("grouping_source_option_dropped", "G05", m_source_option_dropped,
     "The question declares an option no source contributes. It can never be presented, so review would approve content no user sees."),
    ("grouping_source_option_relabelled", "G05", m_source_option_relabelled,
     "A source declares a different label for a shared option id, so the presented text depends on which source triggered."),
    ("grouping_static_rule_with_source_options", "G05", m_static_rule_with_source_options,
     "A static group whose source also carries options — two different option sets declared for one question."),
    ("grouping_clarifier_grouped", "G06", m_clarifier_grouped,
     "A red-flag clarifier carrying a grouping block. Merging clarifiers deletes a danger-sign question; this must be impossible, not merely avoided."),
    ("grouping_source_triggers_outside_question", "G07", m_source_triggers_outside_question,
     "A source that fires on a token its question's trigger does not cover, so the union needs a question that is never presented."),
    ("grouping_ungrouped_question_in_groupable_role", "G08", m_ungrouped_question_in_groupable_role,
     "The candidate 1.0 shape restored: a per-token follow-up with no grouping block, consuming its own slot against the limit of 5."),
    ("grouping_source_order_index_not_integer", "G09", m_source_order_index_not_integer,
     "A non-integer order index. Selection would fall back to JSON declaration order, which is not a declared rule."),
]


def build():
    base = load_json(CANDIDATE_PATH)
    files = []
    for fixture_id, expected_check, mutate, why in FIXTURES:
        artifact = copy.deepcopy(base)
        mutate(artifact)
        if dump_artifact_bytes(artifact) == dump_artifact_bytes(base):
            raise SystemExit("fixture %s introduced no change" % fixture_id)
        artifact["_metadata"]["fixture"] = {
            "fixture_id": fixture_id,
            "expected_check": expected_check,
            "must_be_rejected": True,
            "defect": why,
            "base": "candidate/question_flow.ng.v1.1.json",
            "generator": GENERATOR,
            "note": "INVALID BY CONSTRUCTION. Never publish, never consume, never treat as a candidate.",
        }
        files.append((fixture_id, expected_check, why, artifact))

    index = {
        "_metadata": {
            "fixture_set_id": "question_grouping_invalid",
            "version": "1",
            "generator": GENERATOR,
            "base_artifact": "candidate/question_flow.ng.v1.1.json",
            "base_sha256": sha256_bytes(dump_artifact_bytes(base)),
            "description": (
                "One fixture per way the grouping contract can be violated. Each names "
                "the check that must reject it; being rejected by a different check "
                "counts as a FAILURE, because that proves the artifact is broken rather "
                "than that the intended guard works."
            ),
            "count": len(files),
        },
        "fixtures": [
            {
                "fixture_id": fixture_id,
                "file": "%s.json" % fixture_id,
                "expected_check": expected_check,
                "defect": why,
                "sha256": sha256_bytes(dump_artifact_bytes(artifact)),
            }
            for fixture_id, expected_check, why, artifact in files
        ],
    }
    return files, index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    files, index = build()
    payloads = {"index.json": dump_artifact_bytes(index)}
    for fixture_id, _check, _why, artifact in files:
        payloads["%s.json" % fixture_id] = dump_artifact_bytes(artifact)

    if args.check:
        stale = []
        for name, payload in sorted(payloads.items()):
            path = os.path.join(FIXTURE_DIR, name)
            if not os.path.exists(path) or open(path, "rb").read() != payload:
                stale.append(name)
        extra = sorted(
            name for name in (os.listdir(FIXTURE_DIR) if os.path.isdir(FIXTURE_DIR) else [])
            if name not in payloads
        )
        if stale or extra:
            print("FAIL invalid grouping fixtures are stale: %s" % (stale + extra))
            return 1
        print("OK   %d invalid grouping fixtures are reproducible" % len(files))
        return 0

    for name, payload in sorted(payloads.items()):
        write_bytes(os.path.join(FIXTURE_DIR, name), payload)
    print("wrote %d invalid grouping fixtures to testing/questions/fixtures/invalid_grouping/"
          % len(files))
    by_check = {}
    for fixture_id, check, _why, _artifact in files:
        by_check.setdefault(check, []).append(fixture_id)
    for check in sorted(by_check):
        print("  %s: %d" % (check, len(by_check[check])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
