#!/usr/bin/env python3
"""Project the live question flow into candidate 1.1, with grouping.

    python3 tools/build_question_candidate_v11.py            # build
    python3 tools/build_question_candidate_v11.py --check    # fail if stale

Candidate 1.0 modelled ONE QUESTION PER TOKEN PER ROLE. The live engine does
not: it keeps the first severity question it meets, the first duration question
it meets, and merges every additional-symptoms option list into a single
question. Across the 2,325 bounded paths that difference changed the question
set on 1,930 of them — not the order, the SET — which is why activation stayed
blocked.

Candidate 1.1 models what the engine does. The per-token questions become
SOURCES of three grouped questions, and the group declares how a representative
is chosen and how options are unioned. Everything outside the three groupable
roles is copied from candidate 1.0 byte-for-byte and asserted to be unchanged.

What is deliberately NOT preserved, and is the whole point of the correction:

  * the baseline picks its representative by user tap order. 1.1 picks by
    ``lowest_source_order_index``. Same question set, stable wording. This is
    IM-001, narrowed to the only place it still applies.

What is preserved:

  * question content, answer meanings, produced tokens, red-flag rules and
    timing, path limit 5, red-flag non-droppability, and the effective question
    set on every representable baseline path.

Standard library only. No network.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_question_candidate as v10
from qflow import MOBILE_SOURCE_COMMIT, MOBILE_SOURCE_REPO, QFLOW_TOOLING_VERSION
from qflow.conditions import CONDITION_LANGUAGE_VERSION, FIELDS, OPERATORS
from qflow.dartparse import BASELINE_DIR, VENDORED_FILES, parse_all
from qflow.grouping import (
    GROUPABLE_ROLES,
    NON_GROUPABLE_ROLES,
    REPRESENTATIVE_SELECTION,
)
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    sha256_file,
    write_bytes,
)

CANDIDATE_PATH = repo_path("candidate", "question_flow.ng.v1.1.json")
SUPERSEDED_PATH = repo_path("candidate", "question_flow.ng.v1.0.json")
GENERATOR = "tools/build_question_candidate_v11.py"
GENERATOR_VERSION = "1.1.0"
DEFAULT_GENERATED_AT = "2026-08-17T00:00:00Z"

CANDIDATE_VERSION = "1.1"
SCHEMA_VERSION = "1.1"

#: One grouped question per role, replacing the per-token questions of 1.0.
GROUP_QUESTION_ID = {
    "severity": "Q-followup-severity",
    "duration": "Q-followup-duration",
    "additional_symptoms": "Q-followup-additional-symptoms",
}

#: Severity and duration options are global in the baseline — every token's
#: entry offers the same answers — so the presented set never varies. Only
#: additional-symptoms options are contributed per source.
OPTION_UNION_RULE = {
    "severity": "static",
    "duration": "static",
    "additional_symptoms": "union_of_triggered_sources",
}


GROUPING_FINDINGS = [
    {
        "id": "GF-001",
        "behaviour": "single severity question",
        "baseline": "`severityQuestion ??= question` — the first severity entry met while iterating the selected tokens wins, and no later one is asked.",
        "candidate_1_0": "One severity question per token with a severity entry. Selecting two such tokens planned two severity questions.",
        "candidate_1_1": "One grouped question, group_key `severity`, with 6 sources. The representative is the triggered source with the lowest source_order_index.",
        "affects_question_set": True,
        "affects_content": False,
        "affects_tokens": False,
        "deterministic_change": "Representative selection replaces tap order. Baseline is unstable here, so there is no stable behaviour to preserve.",
    },
    {
        "id": "GF-002",
        "behaviour": "single duration question",
        "baseline": "`durationQuestion ??= question` — same first-wins rule over duration entries.",
        "candidate_1_0": "One duration question per token with a duration entry (16 of them).",
        "candidate_1_1": "One grouped question, group_key `duration`, with 16 sources.",
        "affects_question_set": True,
        "affects_content": False,
        "affects_tokens": False,
        "deterministic_change": "As GF-001.",
    },
    {
        "id": "GF-003",
        "behaviour": "merged additional-symptoms question with unioned options",
        "baseline": "The question TEXT is first-wins (`additionalQuestionText ??=`), but the OPTIONS accumulate: every triggered token's options are appended in visit order, de-duplicated by exact string. The presented option set is therefore path-dependent.",
        "candidate_1_0": "One question per token, each carrying only that token's options. No union existed.",
        "candidate_1_1": "One grouped question, group_key `additional_symptoms`, 18 sources, option_union_rule `union_of_triggered_sources`.",
        "affects_question_set": True,
        "affects_content": False,
        "affects_tokens": False,
        "deterministic_change": "Option ORDER becomes (source_order_index, declared order) instead of tap order. The option SET on any path is unchanged.",
    },
    {
        "id": "GF-004",
        "behaviour": "red-flag clarifiers are never grouped",
        "baseline": "Clarifiers are built by a separate comprehension over `kRedFlagClarifiers` in declaration order, with no `??=` anywhere. Every triggered clarifier is emitted.",
        "candidate_1_0": "One question per clarifier. Correct.",
        "candidate_1_1": "Unchanged, and now explicitly prohibited from grouping via `grouping_semantics.non_groupable_roles`.",
        "affects_question_set": False,
        "affects_content": False,
        "affects_tokens": False,
        "deterministic_change": "None. Declaration order and tie_break_key order agree; verified against the oracle.",
    },
    {
        "id": "GF-005",
        "behaviour": "clarifier emission is order-INsensitive, follow-up selection is order-SENSITIVE",
        "baseline": "Clarifiers read `selected` as a Set; the follow-up loop reads `symptomTokens` as a List.",
        "candidate_1_0": "Did not distinguish the two.",
        "candidate_1_1": "Distinguished structurally: `plan_grouped` takes a SET, so no ordering dependence can be reintroduced by accident.",
        "affects_question_set": False,
        "affects_content": False,
        "affects_tokens": False,
        "deterministic_change": "None for clarifiers.",
    },
    {
        "id": "GF-006",
        "behaviour": "default duration fallback trigger",
        "baseline": "`needsDefaultDuration` is set when a selected token has NO map entry; the default is then applied only if `durationQuestion` is still null.",
        "candidate_1_0": "Trigger was `all tokens absent` over the 18 mapped tokens. That is wrong in two directions: it fired on the EMPTY selection (baseline asks nothing), and it failed to fire for a mapped-but-duration-less token combined with an unmapped one — `chest_indrawing_severe` and `fast_breathing_child` have no duration entry, so `{chest_indrawing_severe, abdominal_pain}` gets a default duration live and got none in 1.0.",
        "candidate_1_1": "Trigger is the conjunction the baseline actually computes: at least one unmapped selectable token present, AND every duration-bearing token absent.",
        "affects_question_set": True,
        "affects_content": False,
        "affects_tokens": False,
        "deterministic_change": "None — this is a correctness fix, not a determinism choice. Found by comparing against the real Dart oracle, not by inspection.",
    },
    {
        "id": "GF-008",
        "behaviour": "clarifier emission order is declaration order, not alphabetical",
        "baseline": "`for (final clarifier in kRedFlagClarifiers)` — a fixed const list ordered breathlessness_at_rest, inability_to_drink, abnormal_bleeding.",
        "candidate_1_0": "Every clarifier had priority 0, so ordering fell to tie_break_key = the red-flag token, i.e. alphabetical. That reversed the first and third clarifier on every path presenting both.",
        "candidate_1_1": "Clarifier priority is 0 + declaration index. tie_break_key still identifies the clarifier and is NOT used as a grouping key.",
        "affects_question_set": False,
        "affects_content": False,
        "affects_tokens": False,
        "deterministic_change": "None — declaration order is already stable. This is a correctness fix; eliminating nondeterminism is not a licence to reorder deterministic output. Found by the oracle comparison on 168 paths, not by inspection.",
    },
    {
        "id": "GF-007",
        "behaviour": "truncation drops from the tail",
        "baseline": "`result.sublist(0, 5)` over `[clarifiers…, severity?, duration?, additional?]`. Clarifiers lead, so they are structurally undroppable; at most 3 exist, so the limit never has to yield.",
        "candidate_1_0": "Modelled correctly, but on inflated question counts, so it dropped questions the baseline asks.",
        "candidate_1_1": "Unchanged rule, applied AFTER grouping (`grouping_phase: before_truncation`). With grouping the follow-up count never exceeds 3 clarifiers + 3 grouped = 6, and the observed maximum is 5.",
        "affects_question_set": True,
        "affects_content": False,
        "affects_tokens": False,
        "deterministic_change": "None.",
    },
]


def restate_im001(mismatches):
    """Re-state IM-001 for 1.1 without deleting what 1.0 said.

    1.0's IM-001 described the correction as `tie_break_key = the trigger token`
    and classified it `path_affecting: false`. Measurement then showed it changed
    the question SET on 1,930 of 2,325 paths, because the per-token model — not
    the tie-break — was the cause. 1.1 removes that cause, so the classification
    is now accurate for the first time. The superseded wording is carried in the
    record rather than overwritten: a reviewer needs to see what the earlier
    claim was in order to judge why it was wrong.

    IM-002 and IM-003 are passed through untouched. IM-002 is the merged QB-002
    safety correction and 1.1 changes nothing about red-flag timing; IM-003
    remains unimplemented and is not made implementable here.
    """
    restated = []
    for mismatch in mismatches:
        if mismatch["id"] != "IM-001":
            restated.append(mismatch)
            continue
        entry = dict(mismatch)
        entry["superseded_statement_from_1_0"] = {
            "candidate_behaviour": mismatch["candidate_behaviour"],
            "classification": dict(mismatch["classification"]),
            "affected_existing_paths": mismatch["affected_existing_paths"],
            "why_it_was_wrong": (
                "It attributed the difference to the tie-break key. The measured "
                "cause was the per-token question model: 1.0 planned one question "
                "per token per role where the engine asks one, changing the question "
                "SET on 1,930 of 2,325 bounded paths, 1,192 with different "
                "truncation. The tie-break was never the mechanism."
            ),
        }
        entry["candidate_behaviour"] = (
            "Questions are grouped exactly as the engine groups them. Within a group, "
            "the wording comes from the triggered source with the lowest "
            "source_order_index — a property of the artifact, not of the user's tap "
            "order. The same symptom SET always yields the same questions, the same "
            "options and the same wording."
        )
        entry["classification"] = dict(mismatch["classification"], path_affecting=False)
        entry["affected_existing_paths"] = (
            "Wording only, and only where the baseline has no stable answer to "
            "preserve. Measured over 2,325 real captured paths: 0 question-set, "
            "0 option-set, 0 token-effect, 0 red-flag and 0 truncation differences; "
            "the candidate matches live forward-order output on all 2,325. The live "
            "engine disagrees with ITSELF on 1,680 of 2,300 reversed-order paths, "
            "which is the defect IM-001 removes."
        )
        entry["measured_in"] = [
            "reports/question_grouping_parity_v1_1.json",
            "reports/question_grouping_coverage_v1_1.json",
        ]
        entry["activation_blocker"] = True
        entry["activation_blocker_reason"] = (
            "No longer blocked on path-content evidence — that evidence now shows zero "
            "question-set change. It remains blocked on PRODUCT sign-off that the "
            "deterministically chosen wording is the right one on the paths where the "
            "baseline was unstable, and on the unrelated blockers (content unapproved, "
            "no clinical review, unpublished)."
        )
        entry["required_review"] = (
            "product — confirm the representative wording on paths where the baseline "
            "was order-dependent. Content is unchanged; only WHICH existing wording is "
            "shown can differ from a given tap order."
        )
        restated.append(entry)
    return restated


def unmapped_selectable_tokens(parsed):
    """Selectable tokens with no kFollowupQuestionMap entry.

    These are what set `needsDefaultDuration`. The domain is the SYMPTOM PICKER,
    not the whole dictionary, because `FollowupScreen` is only ever handed
    `AssessmentController.selectedSymptomTokens`. Stated rather than assumed:
    a token that cannot be picked cannot reach this code.
    """
    picker = {token for _, token in parsed["symptom_display"]["display_label_to_token"]}
    return sorted(picker - set(parsed["followup_question_map"]["entries"]))


def build_candidate(generated_at):
    parsed = parse_all(repo_path())
    fq = parsed["followup_question_map"]
    entries = fq["entries"]
    answers = parsed["answer_mappings"]
    engine = parsed["engine"]
    scoring_tokens, red_flag_tokens = v10.clinical_roles()

    # Everything that does not group is taken from candidate 1.0 as-is. Copying
    # rather than re-deriving is what makes "unchanged" checkable.
    baseline_artifact = v10.build_candidate(generated_at)
    carried = [
        q for q in baseline_artifact["questions"]
        if q["clinical_role"] not in GROUPABLE_ROLES
    ]

    # The ONE correction applied to a carried question (GF-008). Candidate 1.0
    # gave every clarifier priority 0, leaving their relative order to the
    # tie-break key — alphabetical by red-flag token. The live engine emits them
    # in `kRedFlagClarifiers` DECLARATION order, which is not alphabetical
    # (breathlessness_at_rest, inability_to_drink, abnormal_bleeding). That order
    # is a fixed const list: stable, not selection-dependent, so there is no
    # nondeterminism to remove and no licence to reorder it.
    declaration_index = {
        clarifier["red_flag_token"]: index
        for index, clarifier in enumerate(parsed["red_flag_clarifiers"])
    }
    for question in carried:
        if question["clinical_role"] != "red_flag_clarifier":
            continue
        index = declaration_index[question["tie_break_key"]]
        question["priority"] = v10.PRIORITY["red_flag_clarifier"] + index
        question["provenance"] = (
            "red_flag_clarifiers.dart kRedFlagClarifiers[%d] — priority encodes "
            "declaration order, which is the emission order of the live engine" % index
        )

    questions = list(carried)

    def add(question):
        produced = sorted({t for o in question["answer_options"] for t in o["produces_tokens"]})
        question["effects"] = {
            "produces_tokens": produced,
            "affects_scoring": bool(set(produced) & scoring_tokens),
            "affects_red_flags": bool(set(produced) & red_flag_tokens),
        }
        can_affect = question["effects"]["affects_red_flags"]
        question["red_flag_evaluation"] = {
            "can_affect_red_flag": can_affect,
            "evaluate_after_answer": can_affect,
            "blocks_next_question": can_affect,
        }
        question.setdefault("terminal", False)
        question.setdefault("branch_conditions", [])
        question.setdefault("invalidates_on_change", [])
        question["review"] = {
            "review_status": "not_reviewed",
            "clinical_reviewer": None,
            "review_date": None,
        }
        questions.append(question)

    severity_bands = answers["severity_bands"]
    duration_answers = answers["duration_answer_to_token"]

    # source_order_index is assigned from the SORTED canonical token id: a
    # property of the artifact, never of a run.
    order_index = {token: index for index, token in enumerate(sorted(entries))}

    for role in ("severity", "duration", "additional_symptoms"):
        qid = GROUP_QUESTION_ID[role]
        baseline_type = "additionalSymptoms" if role == "additional_symptoms" else role

        contributing = [
            (token, entry)
            for token in sorted(entries)
            for entry in entries[token]
            if entry["type"] == baseline_type
        ]
        if not contributing:
            raise SystemExit("no baseline sources for role %r — refusing to emit an empty group" % role)

        if role == "severity":
            options = [
                v10.make_option(qid, band["token"], band["token"], [band["token"]],
                                value=band["max_value"])
                for band in severity_bands
            ]
            value_type, question_type = "option_id", "scale_select"
        elif role == "duration":
            options = [
                v10.make_option(qid, token, label, [token], value=label)
                for label, token in duration_answers
            ]
            value_type, question_type = "option_id", "single_select"
        else:
            # Union of every source's options, de-duplicated by option id, in
            # (source_order_index, declared order). The presented set on a given
            # path is the union of the TRIGGERED sources only — this full list
            # exists so every presentable option is declared by the question,
            # which is what makes an ID-keyed answer model possible.
            seen, options = set(), []
            for token, entry in contributing:
                for label in entry["options"]:
                    if label in seen:
                        continue
                    seen.add(label)
                    options.append(v10.make_option(qid, label, label, [label], value=label))
            value_type, question_type = "option_id_set", "multi_select"

        by_id = {option["answer_option_id"]: option for option in options}
        sources = []
        for token, entry in contributing:
            source = {
                "source_id": "followup_question_map.%s.%s" % (token, role),
                "source_token": token,
                "source_order_index": order_index[token],
                "trigger_condition": {"token_present": token},
                "source_text": entry["question_text"],
                "provenance": "followup_question_map.dart kFollowupQuestionMap[%r]" % token,
            }
            if OPTION_UNION_RULE[role] == "union_of_triggered_sources":
                source["answer_options"] = [
                    by_id["%s::%s" % (qid, label)] for label in entry["options"]
                ]
            sources.append(source)

        source_tokens = sorted({token for token, _ in contributing})
        add({
            "question_id": qid,
            "question_type": question_type,
            "clinical_role": role,
            "content_ref": {
                # The representative's wording is what gets rendered; this is the
                # group's identity, and source_text carries the wording of the
                # lowest-indexed source so the field is never empty or invented.
                "content_id": "followup_question_map.group.%s" % role,
                "source_text": sources[0]["source_text"],
                "content_approved": False,
            },
            "answer_value_type": value_type,
            "required": True,
            "skippable": False,
            "answer_options": options,
            "trigger_condition": {"any": [{"token_present": t} for t in source_tokens]},
            "priority": v10.PRIORITY[role],
            # tie_break_key ORDERS questions. It is NOT the grouping key — that
            # is grouping.group_key, defined and validated separately.
            "tie_break_key": role,
            "path_length_contribution": 1,
            "grouping": {
                "group_key": role,
                "merge_strategy": "single_representative",
                "representative_selection": REPRESENTATIVE_SELECTION,
                "option_union_rule": OPTION_UNION_RULE[role],
                "option_order": "source_order_then_declared_order",
                "conflict_resolution": {
                    "on_text_conflict": "representative_wins",
                    "on_option_conflict": (
                        "union_preserving_all_sources"
                        if OPTION_UNION_RULE[role] == "union_of_triggered_sources"
                        else "reject"
                    ),
                    "on_value_type_conflict": "reject",
                },
                "sources": sources,
            },
            "provenance": (
                "question_engine.dart generateQuestions — %s de-duplication over "
                "kFollowupQuestionMap (%d sources)" % (role, len(sources))
            ),
        })

    # --- default duration fallback, with the corrected trigger (GF-006) -------
    default_qid = "Q-followup-default-duration"
    unmapped = unmapped_selectable_tokens(parsed)
    duration_tokens = sorted(
        token for token in entries
        if any(entry["type"] == "duration" for entry in entries[token])
    )
    add({
        "question_id": default_qid,
        "question_type": "single_select",
        "clinical_role": "duration",
        "content_ref": {
            "content_id": "followup_question_map.default.duration",
            "source_text": fq["default_question"]["question_text"],
            "content_approved": False,
        },
        "answer_value_type": "option_id",
        "required": True,
        "skippable": False,
        "answer_options": [
            v10.make_option(default_qid, token, label, [token], value=label)
            for label, token in duration_answers
        ],
        # Exactly the baseline conjunction: `needsDefaultDuration` (some selected
        # token has no map entry) AND `durationQuestion == null` (no selected
        # token contributed one).
        "trigger_condition": {
            "all": [
                {"any": [{"token_present": token} for token in unmapped]},
                {"all": [{"token_absent": token} for token in duration_tokens]},
            ]
        },
        "priority": v10.PRIORITY["duration"] + 1,
        "tie_break_key": "zzz-default",
        "path_length_contribution": 1,
        "terminal": False,
        "provenance": "followup_question_map.dart kDefaultFollowupQuestion — fires only when no grouped duration source triggers",
    })

    metadata = dict(baseline_artifact["_metadata"])
    metadata["impedance_mismatches"] = restate_im001(
        baseline_artifact["_metadata"]["impedance_mismatches"])
    metadata.update({
        "version": CANDIDATE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "generator": GENERATOR,
        "generator_version": GENERATOR_VERSION,
        "tooling_version": QFLOW_TOOLING_VERSION,
        "description": (
            "WellaPath Adaptive Question Flow CANDIDATE 1.1 — candidate 1.0 corrected "
            "to model the live engine's question grouping and de-duplication. Not "
            "published, not clinically approved, not consumed by any build."
        ),
        "supersedes": {
            "version": "1.0",
            "artifact": "candidate/question_flow.ng.v1.0.json",
            "sha256": sha256_file(SUPERSEDED_PATH),
            "status": "superseded_retained",
            "reason": (
                "1.0 modelled one question per token per role. The live engine "
                "de-duplicates, so 1.0 planned a different question SET on 1,930 of "
                "2,325 bounded paths. 1.0 is retained unmodified as the record of "
                "what was measured, and must not be published or consumed."
            ),
            "migration": (
                "The 40 per-token follow-up questions of 1.0 become the 40 SOURCES of 3 "
                "grouped questions in 1.1; the default-duration fallback remains a "
                "separate question. A 1.0 consumer reading 1.1 sees 3 "
                "follow-up questions and no grouping block, and would ask the "
                "lowest-indexed wording with the FULL option union rather than the "
                "triggered union — so a 1.0 consumer MUST refuse schema_version 1.1 "
                "rather than best-effort parse it. Answer option IDs changed for "
                "grouped questions (from Q-followup-<token>-<role>::x to "
                "Q-followup-<role>::x); no answer LABEL, produced token or value "
                "changed. Question IDs outside the grouped roles are byte-identical."
            ),
        },
        "grouping_semantics": {
            "enabled": True,
            "groupable_roles": list(GROUPABLE_ROLES),
            "non_groupable_roles": list(NON_GROUPABLE_ROLES),
            "grouping_phase": "before_truncation",
            "one_question_per_group_key": True,
        },
        "grouping_findings": GROUPING_FINDINGS,
        "grouping_finding_count": len(GROUPING_FINDINGS),
        "source": {
            "repository": MOBILE_SOURCE_REPO,
            "commit": MOBILE_SOURCE_COMMIT,
            "vendored_files": [
                {"file": "%s/%s" % (BASELINE_DIR, name),
                 "sha256": sha256_file(repo_path(BASELINE_DIR, name))}
                for name in VENDORED_FILES
            ],
        },
        "frozen_clinical_inputs": {
            "token_dictionary_v1_1": sha256_file(repo_path("token_dictionary.ng.v1.1.json")),
            "kb_v2_4": sha256_file(repo_path("kb.ng.v2.4.json")),
            "rules_v2_2": sha256_file(repo_path("rules.ng.v2.2.json")),
        },
        "parity_claim": (
            "Question CONTENT, answer meanings, produced tokens, red-flag rules and "
            "red-flag timing are unchanged from 1.0. The EFFECTIVE QUESTION SET now "
            "matches the live engine on every representable bounded path — measured "
            "against real Dart output, not against a reimplementation. The remaining "
            "declared differences are IM-001 (representative wording on paths where "
            "the baseline is order-dependent), IM-002 (red-flag timing, merged and "
            "live) and IM-003 (not implemented)."
        ),
        "changelog": [
            "Grouping semantics added: group_key, merge strategy, representative selection, option union rule, sources (schema 1.1).",
            "40 per-token follow-up questions collapsed into 3 grouped questions with 40 declared sources (6 severity, 16 duration, 18 additional-symptoms).",
            "Default-duration trigger corrected — 1.0 fired it on the empty selection and missed it for duration-less mapped tokens (GF-006).",
            "IM-001 narrowed to representative wording only; it no longer changes which questions are asked.",
            "No question added, removed or reworded; no answer meaning, produced token or red-flag rule changed.",
            "Path limit unchanged at 5; red-flag questions remain undroppable; grouping happens before truncation.",
            "Not published; may_publish is false and no clinical review is recorded.",
        ],
        "provenance": [
            "Projected from wellapath-mobile %s by %s." % (MOBILE_SOURCE_COMMIT, GENERATOR),
            "Questions outside the grouped roles are copied verbatim from candidate 1.0 and asserted byte-identical.",
            "Grouping semantics were derived by tracing QuestionEngine.generateQuestions and then MEASURED against real Dart output captured in testing/questions/fixtures/oracle/.",
            "No PHI and no real-user assessment data.",
        ],
    })

    path_controls = dict(baseline_artifact["path_controls"])
    path_controls["max_questions_per_assessment"] = (
        len([q for q in questions if q["clinical_role"] in
             ("demographic", "body_area", "symptom_picker")])
        + engine["max_followup_questions"]
    )
    path_controls["grouping_phase"] = "before_truncation"
    path_controls["truncation_rule"] = (
        "Group first, then order, then drop the lowest-priority PRESENTED questions "
        "until the follow-up count fits max_followup_questions. A question whose "
        "red_flag_evaluation.can_affect_red_flag is true is never dropped; if "
        "red-flag questions alone exceed the limit, the limit yields and all of them "
        "are asked. Grouping strictly precedes truncation: counting un-merged "
        "questions against the limit would drop questions the live engine asks."
    )

    return {
        "_metadata": metadata,
        "condition_language": {
            "version": CONDITION_LANGUAGE_VERSION,
            "operators": sorted(OPERATORS),
            "fields": sorted(FIELDS),
        },
        "path_controls": path_controls,
        "questions": questions,
    }


#: The only fields a carried question is permitted to differ in, and why.
CARRIED_ALLOWED_DELTA = {
    "red_flag_clarifier": ("priority", "provenance"),
}


def assert_carried_questions_unchanged(artifact, generated_at):
    """Every non-grouped question must match candidate 1.0.

    Clarifiers may differ in `priority` and `provenance` only — GF-008, the
    declaration-order correction. Any other delta, on any question, is drift and
    fails the build. The allowance is enumerated rather than implicit so a
    second unnoticed change cannot ride along with the intended one.
    """
    old = {q["question_id"]: q for q in v10.build_candidate(generated_at)["questions"]}
    problems, deltas = [], []
    for question in artifact["questions"]:
        if question["clinical_role"] in GROUPABLE_ROLES:
            continue
        previous = old.get(question["question_id"])
        if previous is None:
            problems.append("%s is new outside the grouped roles" % question["question_id"])
            continue
        if dump_artifact_bytes(previous) == dump_artifact_bytes(question):
            continue
        allowed = CARRIED_ALLOWED_DELTA.get(question["clinical_role"], ())
        changed = sorted(
            key for key in set(previous) | set(question)
            if previous.get(key) != question.get(key)
        )
        unexpected = [key for key in changed if key not in allowed]
        if unexpected:
            problems.append("%s changed in %s outside the grouped roles"
                            % (question["question_id"], unexpected))
        else:
            deltas.append("%s: %s (GF-008)" % (question["question_id"], changed))
    return problems, deltas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    args = parser.parse_args()

    artifact = build_candidate(args.generated_at)

    problems, deltas = assert_carried_questions_unchanged(artifact, args.generated_at)
    if problems:
        print("FAIL non-grouped questions drifted from candidate 1.0:")
        for problem in problems:
            print("  - %s" % problem)
        return 1

    payload = dump_artifact_bytes(artifact)

    if args.check:
        if not os.path.exists(CANDIDATE_PATH) or open(CANDIDATE_PATH, "rb").read() != payload:
            print("FAIL candidate/question_flow.ng.v1.1.json is missing or stale")
            return 1
        print("OK   candidate 1.1 is reproducible, sha256:%s" % sha256_bytes(payload))
        return 0

    write_bytes(CANDIDATE_PATH, payload)
    grouped = [q for q in artifact["questions"] if "grouping" in q]
    print("wrote candidate/question_flow.ng.v1.1.json")
    print("  questions:        %d (was %d in 1.0)"
          % (len(artifact["questions"]), len(v10.build_candidate(args.generated_at)["questions"])))
    print("  grouped:          %d questions over %d sources"
          % (len(grouped), sum(len(q["grouping"]["sources"]) for q in grouped)))
    print("  answer options:   %d" % sum(len(q["answer_options"]) for q in artifact["questions"]))
    print("  non-grouped questions identical to 1.0: %s"
          % ("yes" if not deltas else "yes, except %d clarifier priority corrections" % len(deltas)))
    for delta in deltas:
        print("      %s" % delta)
    print("  sha256:           %s" % sha256_bytes(payload))
    print("  release_status:   %s | may_publish: %s"
          % (artifact["_metadata"]["release_status"], artifact["_metadata"]["may_publish"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
