#!/usr/bin/env python3
"""Derive question-flow schema 1.1 from 1.0 by pure addition.

    python3 tools/build_question_schema_v11.py            # build
    python3 tools/build_question_schema_v11.py --check    # fail if stale

Schema 1.1 exists for exactly one reason: schema 1.0 declares
``additionalProperties: false`` on a question, so the grouping semantics the
live engine actually implements cannot be expressed under it at all. Rather than
hand-writing a second schema and hoping it stayed a superset, 1.1 is COMPUTED
from 1.0 — load, add, dump. Every field 1.0 required is still required, every
enum 1.0 allowed is still allowed, and `--check` plus
``tools/validate_question_flow.py --schema-diff`` prove it.

What is added, and nothing else:

  * ``$defs.grouping``   — the merge contract for one presented question
  * ``$defs.groupSource``— one baseline source that can feed a merged question
  * ``question.grouping``— optional; absent means "this question never merges"
  * ``metadata.grouping_semantics`` — the artifact-level declaration
  * ``pathControls.grouping_phase`` — where merging sits relative to truncation
  * ``metadata.schema_version`` widens from ``const "1.0"`` to
    ``enum ["1.0", "1.1"]`` — a widening, so a 1.0 artifact still validates

Standard library only. No network.
"""

import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.grouping import (
    GROUPABLE_ROLES,
    NON_GROUPABLE_ROLES,
    OPTION_UNION_RULES,
    REPRESENTATIVE_SELECTION,
)
from vocab.artifact_io import dump_artifact_bytes, load_json, repo_path, sha256_bytes, write_bytes

SOURCE_SCHEMA = repo_path("schema", "question_flow.v1.schema.json")
TARGET_SCHEMA = repo_path("schema", "question_flow.v1_1.schema.json")
GENERATOR = "tools/build_question_schema_v11.py"


GROUP_SOURCE_DEF = {
    "type": "object",
    "description": (
        "One baseline authoring site that can feed a merged question. In the "
        "live engine these are the per-token entries of kFollowupQuestionMap; "
        "the engine visits them in user-selection order and keeps the first. "
        "Here they are declared explicitly so selection can be resolved by a "
        "stated rule instead of by tap order."
    ),
    "required": [
        "source_id",
        "source_token",
        "source_order_index",
        "trigger_condition",
        "source_text",
        "provenance",
    ],
    "additionalProperties": False,
    "properties": {
        "source_id": {
            "type": "string",
            "minLength": 1,
            "description": "Stable identifier for this authoring site. Unique within a grouping block.",
        },
        "source_token": {
            "$ref": "#/$defs/tokenId",
            "description": "The canonical token whose selection makes this source contribute.",
        },
        "source_order_index": {
            "type": "integer",
            "minimum": 0,
            "description": (
                "Total order over the sources of one group. Assigned from the "
                "sorted canonical token id, so it is a property of the artifact "
                "and not of any run. Unique within a grouping block."
            ),
        },
        "trigger_condition": {"$ref": "#/$defs/condition"},
        "source_text": {
            "type": "string",
            "minLength": 1,
            "description": "Verbatim baseline wording of this source. Rendered only if this source is selected as representative.",
        },
        "answer_options": {
            "type": "array",
            "description": (
                "Options this source contributes when option_union_rule is "
                "union_of_triggered_sources. Every entry MUST also appear in the "
                "owning question's answer_options; the union can never introduce "
                "an option the question does not declare."
            ),
            "items": {"$ref": "#/$defs/answerOption"},
        },
        "provenance": {"type": "string", "minLength": 1},
    },
}


GROUPING_DEF = {
    "type": "object",
    "description": (
        "Declares that several baseline authoring sites collapse into ONE "
        "presented question, and states exactly how. Present only on questions "
        "that can merge; its absence means the question is always presented "
        "alone."
    ),
    "required": [
        "group_key",
        "merge_strategy",
        "representative_selection",
        "option_union_rule",
        "sources",
    ],
    "additionalProperties": False,
    "properties": {
        "group_key": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Identity of the merged question. At most one question may be "
                "presented per group_key on any path. This is a DISTINCT concept "
                "from tie_break_key, which orders questions and never groups them."
            ),
        },
        "merge_strategy": {
            "type": "string",
            "enum": ["single_representative"],
            "description": (
                "single_representative: the group yields exactly one presented "
                "question, whose wording comes from the representative source and "
                "whose options come from option_union_rule."
            ),
        },
        "representative_selection": {
            "type": "string",
            "enum": [REPRESENTATIVE_SELECTION],
            "description": (
                "lowest_source_order_index: among sources whose trigger_condition "
                "holds, the one with the smallest source_order_index supplies the "
                "wording. Deterministic and independent of selection order — this "
                "is the declared replacement for the baseline's first-tapped-wins."
            ),
        },
        "option_union_rule": {
            "type": "string",
            "enum": list(OPTION_UNION_RULES),
            "description": (
                "static: the question's own answer_options are presented "
                "unchanged, regardless of which sources triggered. "
                "union_of_triggered_sources: the presented options are the union "
                "of the answer_options of the TRIGGERED sources only, "
                "de-duplicated by answer_option_id, ordered by "
                "(source_order_index, position within that source)."
            ),
        },
        "option_order": {
            "type": "string",
            "enum": ["source_order_then_declared_order"],
            "description": "Stated so two consumers cannot present the same option set in different orders.",
        },
        "conflict_resolution": {
            "type": "object",
            "description": "What happens when triggered sources disagree on a presented property.",
            "required": ["on_text_conflict", "on_option_conflict", "on_value_type_conflict"],
            "additionalProperties": False,
            "properties": {
                "on_text_conflict": {
                    "type": "string",
                    "enum": ["representative_wins"],
                    "description": "Baseline behaviour: the first-visited wording is kept and the others are never shown.",
                },
                "on_option_conflict": {
                    "type": "string",
                    "enum": ["union_preserving_all_sources", "reject"],
                    "description": (
                        "union_preserving_all_sources: no triggered source's option "
                        "may be lost. reject: a disagreement is a contract failure, "
                        "used where the baseline offers no merge behaviour to copy."
                    ),
                },
                "on_value_type_conflict": {
                    "type": "string",
                    "enum": ["reject"],
                    "description": "Sources of one group must share answer_value_type. Merging different answer shapes would change answer meaning.",
                },
            },
        },
        "sources": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/groupSource"},
        },
    },
}


GROUPING_SEMANTICS_DEF = {
    "type": "object",
    "description": "Artifact-level grouping declaration. A consumer that does not understand it must refuse the artifact rather than ignore it.",
    "required": [
        "enabled",
        "groupable_roles",
        "non_groupable_roles",
        "grouping_phase",
        "one_question_per_group_key",
    ],
    "additionalProperties": False,
    "properties": {
        "enabled": {"type": "boolean"},
        "groupable_roles": {
            "type": "array",
            "items": {"type": "string", "enum": list(GROUPABLE_ROLES)},
        },
        "non_groupable_roles": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "enum": list(NON_GROUPABLE_ROLES)},
            "description": (
                "Roles that must never be merged. red_flag_clarifier is here "
                "because each clarifier carries its own red-flag token: merging "
                "two would silently delete a danger-sign question."
            ),
        },
        "grouping_phase": {
            "type": "string",
            "enum": ["before_truncation"],
            "description": (
                "Merging happens BEFORE the follow-up limit is applied, so the "
                "limit counts presented questions. Grouping after truncation "
                "would let a merged pair consume two slots and drop a third "
                "question that the live engine asks."
            ),
        },
        "one_question_per_group_key": {"type": "boolean", "const": True},
    },
}


def build_schema():
    schema = load_json(SOURCE_SCHEMA)

    schema["$id"] = "https://wellapath.org/schema/question_flow.v1_1.schema.json"
    schema["title"] = "WellaPath Adaptive Question Flow — schema 1.1"
    schema["description"] = (
        "Schema 1.1 = schema 1.0 plus explicit question grouping. Additive only: "
        "every 1.0 required field is still required and every 1.0 enum value is "
        "still accepted, so any artifact valid under 1.0 remains structurally "
        "valid here. 1.1 exists because 1.0 sets additionalProperties:false on a "
        "question and therefore cannot express the de-duplication the live "
        "QuestionEngine performs. Generated by %s from schema 1.0." % GENERATOR
    )

    defs = schema["$defs"]
    if "grouping" in defs or "groupSource" in defs:
        raise SystemExit("schema 1.0 already defines grouping — refusing to overwrite")
    defs["groupSource"] = copy.deepcopy(GROUP_SOURCE_DEF)
    defs["grouping"] = copy.deepcopy(GROUPING_DEF)

    question = defs["question"]
    if "grouping" in question["properties"]:
        raise SystemExit("question already carries grouping — refusing to overwrite")
    question["properties"]["grouping"] = {"$ref": "#/$defs/grouping"}
    # Deliberately NOT added to `required`: a question with no grouping block is
    # a question that never merges, which is the correct reading of every
    # question schema 1.0 could express.

    metadata = defs["metadata"]
    if "grouping_semantics" in metadata["properties"]:
        raise SystemExit("metadata already carries grouping_semantics — refusing to overwrite")
    metadata["properties"]["grouping_semantics"] = copy.deepcopy(GROUPING_SEMANTICS_DEF)
    metadata["required"] = sorted(set(metadata["required"]) | {"grouping_semantics"})

    # The one existing constraint that must widen rather than be added to.
    # Left as const "1.0" the new schema could not validate the artifact it was
    # written for; changed to a different const it would stop accepting 1.0.
    # An enum containing both is the only additive option.
    schema_version = metadata["properties"]["schema_version"]
    if schema_version != {"const": "1.0"}:
        raise SystemExit("schema 1.0 no longer pins schema_version as expected: %r"
                         % (schema_version,))
    metadata["properties"]["schema_version"] = {
        "enum": ["1.0", "1.1"],
        "description": (
            "1.0 artifacts remain valid under this schema. A consumer must still "
            "refuse a MAJOR version it does not implement, and a 1.0-only consumer "
            "must refuse 1.1 because it cannot apply the grouping block."
        ),
    }

    path_controls = defs["pathControls"]
    path_controls["properties"]["grouping_phase"] = {
        "type": "string",
        "enum": ["before_truncation"],
        "description": "Mirrors _metadata.grouping_semantics.grouping_phase where the truncation rule is read.",
    }

    return schema


def additive_violations(old, new, path="$"):
    """Every way ``new`` could be narrower than ``old``. Empty means additive."""
    problems = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key, value in old.items():
            if key not in new:
                if key == "const" and value in new.get("enum", []):
                    continue  # const widened into an enum that still accepts it
                problems.append("%s.%s was removed" % (path, key))
                continue
            if key == "required" and isinstance(value, list):
                missing = [r for r in value if r not in new[key]]
                if missing:
                    problems.append("%s.required lost %s" % (path, missing))
            elif key == "enum" and isinstance(value, list):
                missing = [e for e in value if e not in new[key]]
                if missing:
                    problems.append("%s.enum lost %s" % (path, missing))
            elif key == "const" and new[key] != value:
                problems.append("%s.const changed %r -> %r; a const may only widen "
                                "into an enum that still contains it"
                                % (path, value, new[key]))
            else:
                problems.extend(additive_violations(value, new[key], "%s.%s" % (path, key)))
    elif isinstance(old, list) and isinstance(new, list):
        if len(new) < len(old):
            problems.append("%s shrank from %d to %d" % (path, len(old), len(new)))
        for index, item in enumerate(old[: len(new)]):
            problems.extend(additive_violations(item, new[index], "%s[%d]" % (path, index)))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    schema = build_schema()
    payload = dump_artifact_bytes(schema)

    # Prove additivity before writing anything, every run — the claim is only
    # worth making if it is re-tested each time the generator changes.
    ignored = ("$id", "title", "description")
    old = {k: v for k, v in load_json(SOURCE_SCHEMA).items() if k not in ignored}
    new = {k: v for k, v in schema.items() if k not in ignored}
    problems = additive_violations(old, new)
    if problems:
        print("FAIL schema 1.1 is not additive over 1.0:")
        for problem in problems:
            print("  - %s" % problem)
        return 1

    if args.check:
        if not os.path.exists(TARGET_SCHEMA) or open(TARGET_SCHEMA, "rb").read() != payload:
            print("FAIL schema/question_flow.v1_1.schema.json is missing or stale")
            return 1
        print("OK   schema 1.1 is reproducible and additive over 1.0, sha256:%s"
              % sha256_bytes(payload))
        return 0

    write_bytes(TARGET_SCHEMA, payload)
    print("wrote schema/question_flow.v1_1.schema.json")
    print("  additive over 1.0: yes (0 removed fields, 0 narrowed required, 0 narrowed enums)")
    print("  added $defs:       grouping, groupSource")
    print("  sha256:            %s" % sha256_bytes(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
