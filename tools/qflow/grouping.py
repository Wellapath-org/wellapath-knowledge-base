"""Live question grouping semantics, and the grouped candidate planner.

Two models live here on purpose, side by side:

  * ``live_effective_questions`` — a faithful transcription of
    ``QuestionEngine.generateQuestions`` from
    ``baseline/questions_v1/question_engine.vendored.dart``. It exists so the
    corrected projection can be compared against what the app actually does.
    It is validated against ``testing/questions/fixtures/oracle/`` — real Dart
    output, not a second opinion about it.

  * ``plan_grouped`` — what a consumer of the corrected candidate would
    present. Same effective question set, with the one place the baseline is
    unstable replaced by a declared deterministic rule.

The difference between them is IM-001, and it is measured rather than assumed.

Standard library only.
"""

# ─────────────────────────────────────────────────────────────────────────────
# The live algorithm, transcribed
#
# for token in symptomTokens:                    <- SELECTED order, not sorted
#     entries = kFollowupQuestionMap[token]
#     if entries is None: needsDefaultDuration = True; continue
#     for q in entries:
#         severity:   severityQuestion ??= q     <- FIRST WINS, whole iteration
#         duration:   durationQuestion ??= q     <- FIRST WINS
#         clarifier:  (not authored here)
#         additional: additionalQuestionText ??= q.text   <- FIRST WINS
#                     options += [o for o in q.options if o not in options]
#                                                <- ORDERED UNION, dedup by value
# if needsDefaultDuration: durationQuestion ??= kDefaultFollowupQuestion
#
# clarifiers = [c for c in kRedFlagClarifiers          <- DECLARATION order
#               if c.redFlagToken not in selected
#               and any(t in selected for t in c.triggerTokens)]
#
# result = clarifiers + [severity?] + [duration?] + [additional?]
# return result[:5] if len(result) > 5 else result     <- drops from the TAIL
# ─────────────────────────────────────────────────────────────────────────────

#: Emission ranks, from ``question_engine.dart``'s result list order.
ROLE_ORDER = {
    "red_flag_clarifier": 0,
    "severity": 10,
    "duration": 20,
    "additional_symptoms": 30,
}

#: The live limit. Not raised, not lowered.
MAX_FOLLOWUP_QUESTIONS = 5

#: Roles that may be grouped into a single presented question.
GROUPABLE_ROLES = ("severity", "duration", "additional_symptoms")

#: Roles that must NEVER be grouped. A clarifier carries its own red-flag
#: token; merging two of them would silently drop a danger-sign question.
NON_GROUPABLE_ROLES = ("red_flag_clarifier",)

#: How a grouped question picks its wording when several sources trigger.
REPRESENTATIVE_SELECTION = "lowest_source_order_index"

#: How a grouped question builds its option list.
OPTION_UNION_RULES = ("static", "union_of_triggered_sources")


def _role_of(entry_type):
    return "additional_symptoms" if entry_type == "additionalSymptoms" else entry_type


def live_effective_questions(selected_tokens, followup_map, default_question,
                             clarifiers):
    """Exactly what ``QuestionEngine.generateQuestions`` returns.

    ``selected_tokens`` is an ORDERED list: the live algorithm's first-wins
    behaviour depends on it, and reproducing that dependence is the whole point
    of this function.
    """
    severity = None
    duration = None
    additional_text = None
    additional_options = []
    needs_default_duration = False

    for token in selected_tokens:
        entries = followup_map.get(token)
        if entries is None:
            needs_default_duration = True
            continue
        for entry in entries:
            role = _role_of(entry["type"])
            if role == "severity":
                if severity is None:
                    severity = {"role": "severity", "token": token,
                                "question_text": entry["question_text"],
                                "options": []}
            elif role == "duration":
                if duration is None:
                    duration = {"role": "duration", "token": token,
                                "question_text": entry["question_text"],
                                "options": []}
            elif role == "additional_symptoms":
                if additional_text is None:
                    additional_text = entry["question_text"]
                for option in entry["options"]:
                    if option not in additional_options:
                        additional_options.append(option)

    if needs_default_duration and duration is None:
        duration = {"role": "duration", "token": None,
                    "question_text": default_question["question_text"],
                    "options": [], "is_default": True}

    selected = set(selected_tokens)
    fired = [
        {"role": "red_flag_clarifier",
         "token": c["red_flag_token"],
         "question_text": c["question_text"],
         "options": ["Yes", "No"],
         "red_flag_token": c["red_flag_token"]}
        for c in clarifiers
        if c["red_flag_token"] not in selected
        and any(t in selected for t in c["trigger_tokens"])
    ]

    result = list(fired)
    if severity is not None:
        result.append(severity)
    if duration is not None:
        result.append(duration)
    if additional_options:
        result.append({"role": "additional_symptoms", "token": None,
                       "question_text": additional_text,
                       "options": list(additional_options)})

    # Truncation drops from the TAIL, so clarifiers (which lead) survive.
    return result[:MAX_FOLLOWUP_QUESTIONS]


def plan_grouped(selected_tokens, grouped_questions, clarifier_questions,
                 default_question):
    """What a consumer of the corrected candidate presents.

    ``selected_tokens`` is accepted as a SET: the corrected model must not
    depend on selection order, and taking a set makes that impossible rather
    than merely unlikely.
    """
    selected = set(selected_tokens)
    presented = []

    # Clarifiers: never grouped. Ordered by (priority, tie_break_key), where
    # the clarifier priority encodes kRedFlagClarifiers DECLARATION order. That
    # order is a fixed const list — stable, not selection-dependent — so there
    # is no nondeterminism to remove and reordering it would be an unrequested
    # behaviour change.
    for q in sorted(clarifier_questions,
                    key=lambda q: (q["priority"], q["tie_break_key"])):
        if condition_holds(q["trigger_condition"], selected):
            presented.append({
                "question_id": q["question_id"],
                "role": "red_flag_clarifier",
                "question_text": q["content_ref"]["source_text"],
                "options": [o["answer_option_id"] for o in q["answer_options"]],
                "option_values": [o["value"] for o in q["answer_options"]],
                "red_flag_token": q["tie_break_key"],
                "priority": q["priority"],
            })

    # Grouped roles: one presented question per group, wording and options
    # derived from the sources that actually triggered.
    for q in sorted(grouped_questions, key=lambda q: (q["priority"],
                                                      q["tie_break_key"],
                                                      q["question_id"])):
        grouping = q["grouping"]
        triggered = [
            s for s in grouping["sources"]
            if condition_holds(s["trigger_condition"], selected)
        ]
        if not triggered:
            continue

        triggered.sort(key=lambda s: s["source_order_index"])
        representative = triggered[0]

        if grouping["option_union_rule"] == "union_of_triggered_sources":
            options, values = [], []
            for source in triggered:
                for option in source["answer_options"]:
                    if option["answer_option_id"] not in options:
                        options.append(option["answer_option_id"])
                        values.append(option["value"])
        else:
            options = [o["answer_option_id"] for o in q["answer_options"]]
            values = [o["value"] for o in q["answer_options"]]

        presented.append({
            "question_id": q["question_id"],
            "role": q["clinical_role"],
            "question_text": representative["source_text"],
            "representative_source": representative["source_id"],
            "options": options,
            "option_values": values,
            "red_flag_token": None,
            "priority": q["priority"],
            "contributing_sources": [s["source_id"] for s in triggered],
        })

    # Fallback duration, only when no grouped duration triggered.
    has_duration = any(p["role"] == "duration" for p in presented)
    if not has_duration and condition_holds(
            default_question["trigger_condition"], selected):
        presented.append({
            "question_id": default_question["question_id"],
            "role": "duration",
            "question_text": default_question["content_ref"]["source_text"],
            "options": [o["answer_option_id"]
                        for o in default_question["answer_options"]],
            "option_values": [o["value"]
                              for o in default_question["answer_options"]],
            "red_flag_token": None,
            "priority": default_question["priority"],
        })

    presented.sort(key=lambda p: (p["priority"], p["question_id"]))

    # Grouping happens BEFORE truncation, and a red-flag question is never
    # dropped: the ordinary budget is what the limit leaves after them.
    red_flags = [p for p in presented if p["role"] == "red_flag_clarifier"]
    ordinary = [p for p in presented if p["role"] != "red_flag_clarifier"]
    budget = MAX_FOLLOWUP_QUESTIONS - len(red_flags)

    kept = red_flags + ordinary[:max(budget, 0)]
    dropped = ordinary[max(budget, 0):]
    kept.sort(key=lambda p: (p["priority"], p["question_id"]))
    return kept, dropped


def condition_holds(condition, tokens):
    """Evaluates the subset of the condition language the projection uses.

    Deliberately small: an unknown operator raises rather than returning False,
    so a condition this model cannot represent surfaces instead of silently
    excluding a question.
    """
    if not isinstance(condition, dict) or len(condition) != 1:
        raise ValueError("condition must carry exactly one operator: %r" % (condition,))
    operator, payload = next(iter(condition.items()))

    if operator == "always":
        return bool(payload)
    if operator == "never":
        return not bool(payload)
    if operator == "token_present":
        return payload in tokens
    if operator == "token_absent":
        return payload not in tokens
    if operator == "all":
        return all(condition_holds(c, tokens) for c in payload)
    if operator == "any":
        return any(condition_holds(c, tokens) for c in payload)
    if operator == "not":
        return not condition_holds(payload, tokens)
    raise ValueError("operator %r is not representable in the parity model" % operator)


def referenced_tokens(condition):
    """Every token id a condition's truth can depend on.

    Used to bound an exact containment decision. Raises on an operator this
    module cannot interpret, so an unrecognised condition can never be silently
    treated as depending on nothing.
    """
    if not isinstance(condition, dict) or len(condition) != 1:
        raise ValueError("condition must carry exactly one operator: %r" % (condition,))
    operator, payload = next(iter(condition.items()))
    if operator in ("always", "never"):
        return set()
    if operator in ("token_present", "token_absent"):
        return {payload}
    if operator in ("all", "any"):
        return set().union(*(referenced_tokens(c) for c in payload)) if payload else set()
    if operator == "not":
        return referenced_tokens(payload)
    raise ValueError("operator %r is not representable in the parity model" % operator)


def bounded_subsets(tokens, max_size=3):
    """Every subset up to ``max_size``, plus the empty set, in a fixed order.

    Matches the knowledge base's published bound of 2,325 for 24 tokens.
    """
    ordered = sorted(tokens)
    out = [[]]
    for i in range(len(ordered)):
        out.append([ordered[i]])
        for j in range(i + 1, len(ordered)):
            out.append([ordered[i], ordered[j]])
            for k in range(j + 1, len(ordered)):
                out.append([ordered[i], ordered[j], ordered[k]])
    if max_size != 3:
        raise ValueError("only the published bound of 3 is supported")
    return out
