"""The Adaptive Question condition language — reference implementation.

A closed, declarative, finite language. Every condition is a JSON object with
exactly one operator key. There is no expression parser, no scripting, no
regular expression over clinical free text, no network access and no
probabilistic or model-driven branching. A condition is a pure function of the
assessment state, so the same state always yields the same answer.

Operators (the complete set — anything else is a hard validation failure):

    {"all": [c, ...]}                   every sub-condition holds
    {"any": [c, ...]}                   at least one sub-condition holds
    {"not": c}                          the sub-condition does not hold
    {"equals": {"field": f, "value": v}}
    {"one_of": {"field": f, "values": [v, ...]}}
    {"token_present": "t"}              t is in the derived token set
    {"token_absent": "t"}               t is not in the derived token set
    {"prior_answer_equals": {"question_id": q, "answer_option_id": a}}
    {"age_range": {"min_years": n, "max_years": m}}   either bound optional
    {"sex": "male" | "female"}
    {"pregnancy": true | false}
    {"always": true}
    {"never": true}

Empty `all` is TRUE (vacuous truth) and empty `any` is FALSE. Both are stated
here rather than left to the reader because a schema that permits an empty list
without defining its value is a source of silent divergence between two
implementations.

`{"all": []}` and `{"always": true}` are therefore equivalent. `always` exists
because a rule that is deliberately unconditional should say so.
"""

FIELDS = frozenset(["sex", "age_token", "body_area", "assessment_phase"])

OPERATORS = frozenset(
    [
        "all",
        "any",
        "not",
        "equals",
        "one_of",
        "token_present",
        "token_absent",
        "prior_answer_equals",
        "age_range",
        "sex",
        "pregnancy",
        "always",
        "never",
    ]
)

CONDITION_LANGUAGE_VERSION = "1.0.0"


class ConditionError(Exception):
    """Raised for a malformed condition. Never for a merely false one."""


class AssessmentState(object):
    """The complete input a condition may read. Nothing else is visible."""

    def __init__(
        self,
        tokens=None,
        answers=None,
        sex=None,
        age_token=None,
        age_years=None,
        pregnancy=None,
        body_area=None,
        assessment_phase="followup",
    ):
        self.tokens = frozenset(tokens or [])
        # question_id -> answer_option_id (or the sentinel skip/invalid states)
        self.answers = dict(answers or {})
        self.sex = sex
        self.age_token = age_token
        self.age_years = age_years
        self.pregnancy = pregnancy
        self.body_area = body_area
        self.assessment_phase = assessment_phase

    def field(self, name):
        if name not in FIELDS:
            raise ConditionError("unknown field %r" % name)
        return getattr(self, name)


def _one_key(condition):
    if not isinstance(condition, dict):
        raise ConditionError("condition must be an object, got %r" % type(condition).__name__)
    if len(condition) != 1:
        raise ConditionError(
            "condition must have exactly one operator key, got %r" % sorted(condition)
        )
    operator, operand = next(iter(condition.items()))
    if operator not in OPERATORS:
        raise ConditionError("unknown operator %r" % operator)
    return operator, operand


def evaluate(condition, state):
    """Evaluate `condition` against `state`. Returns a bool; raises if malformed."""
    operator, operand = _one_key(condition)

    if operator == "all":
        _require_list(operand, "all")
        return all(evaluate(sub, state) for sub in operand)

    if operator == "any":
        _require_list(operand, "any")
        return any(evaluate(sub, state) for sub in operand)

    if operator == "not":
        return not evaluate(operand, state)

    if operator == "equals":
        _require_keys(operand, {"field", "value"}, "equals")
        return state.field(operand["field"]) == operand["value"]

    if operator == "one_of":
        _require_keys(operand, {"field", "values"}, "one_of")
        _require_list(operand["values"], "one_of.values")
        return state.field(operand["field"]) in operand["values"]

    if operator == "token_present":
        _require_token(operand, "token_present")
        return operand in state.tokens

    if operator == "token_absent":
        _require_token(operand, "token_absent")
        return operand not in state.tokens

    if operator == "prior_answer_equals":
        _require_keys(operand, {"question_id", "answer_option_id"}, "prior_answer_equals")
        return state.answers.get(operand["question_id"]) == operand["answer_option_id"]

    if operator == "age_range":
        if not isinstance(operand, dict) or not operand:
            raise ConditionError("age_range needs min_years and/or max_years")
        extra = set(operand) - {"min_years", "max_years"}
        if extra:
            raise ConditionError("age_range has unknown key(s) %r" % sorted(extra))
        # An unknown age cannot satisfy an age range. Failing closed here means
        # an age-gated question is not asked rather than wrongly asked.
        if state.age_years is None:
            return False
        if "min_years" in operand and state.age_years < operand["min_years"]:
            return False
        if "max_years" in operand and state.age_years > operand["max_years"]:
            return False
        return True

    if operator == "sex":
        if operand not in ("male", "female"):
            raise ConditionError("sex must be 'male' or 'female', got %r" % (operand,))
        return state.sex == operand

    if operator == "pregnancy":
        if not isinstance(operand, bool):
            raise ConditionError("pregnancy must be a boolean, got %r" % (operand,))
        # Unknown pregnancy status is not the same as "not pregnant"; only an
        # explicit answer satisfies either branch.
        if state.pregnancy is None:
            return False
        return state.pregnancy is operand

    if operator == "always":
        if operand is not True:
            raise ConditionError("always must be exactly true")
        return True

    if operator == "never":
        if operand is not True:
            raise ConditionError("never must be exactly true")
        return False

    raise ConditionError("unhandled operator %r" % operator)  # pragma: no cover


def _require_list(value, where):
    if not isinstance(value, list):
        raise ConditionError("%s expects a list, got %r" % (where, type(value).__name__))


def _require_keys(operand, expected, where):
    if not isinstance(operand, dict):
        raise ConditionError("%s expects an object" % where)
    if set(operand) != expected:
        raise ConditionError(
            "%s expects exactly %r, got %r" % (where, sorted(expected), sorted(operand))
        )


def _require_token(value, where):
    if not isinstance(value, str) or not value:
        raise ConditionError("%s expects a non-empty token id" % where)


def validate(condition, known_tokens=None, known_answers=None, path="$"):
    """Structural validation. Returns a list of error strings; empty means valid.

    `known_tokens` and `known_answers` turn cross-reference errors into
    validation failures instead of silent never-true conditions — a condition
    naming a token that does not exist is a defect, not a false branch.
    """
    errors = []
    try:
        operator, operand = _one_key(condition)
    except ConditionError as exc:
        return ["%s: %s" % (path, exc)]

    if operator in ("all", "any"):
        if not isinstance(operand, list):
            return ["%s: %s expects a list" % (path, operator)]
        for index, sub in enumerate(operand):
            errors.extend(
                validate(sub, known_tokens, known_answers, "%s.%s[%d]" % (path, operator, index))
            )
    elif operator == "not":
        errors.extend(validate(operand, known_tokens, known_answers, "%s.not" % path))
    elif operator in ("token_present", "token_absent"):
        if not isinstance(operand, str) or not operand:
            errors.append("%s: %s expects a non-empty token id" % (path, operator))
        elif known_tokens is not None and operand not in known_tokens:
            errors.append("%s: %s references unknown token %r" % (path, operator, operand))
    elif operator == "prior_answer_equals":
        if not isinstance(operand, dict) or set(operand) != {"question_id", "answer_option_id"}:
            errors.append("%s: prior_answer_equals expects question_id and answer_option_id" % path)
        elif known_answers is not None and operand["answer_option_id"] not in known_answers:
            errors.append(
                "%s: prior_answer_equals references unknown answer option %r"
                % (path, operand["answer_option_id"])
            )
    else:
        # Exercise the operator's own operand checks with a neutral state.
        try:
            evaluate(condition, AssessmentState())
        except ConditionError as exc:
            errors.append("%s: %s" % (path, exc))

    return errors


def is_never_satisfiable(condition):
    """Detect conditions that can never hold, without solving the general case.

    Catches the two shapes that actually occur in authored data: an explicit
    `never`, and an `all` requiring a token to be both present and absent.
    Anything it cannot decide is reported as satisfiable, so this only ever
    produces findings it can justify.
    """
    operator, operand = _one_key(condition)
    if operator == "never":
        return True
    if operator == "all":
        present, absent = set(), set()
        for sub in operand:
            if not isinstance(sub, dict) or len(sub) != 1:
                continue
            key, value = next(iter(sub.items()))
            if key == "token_present":
                present.add(value)
            elif key == "token_absent":
                absent.add(value)
            elif key == "never":
                return True
        if present & absent:
            return True
        return any(is_never_satisfiable(sub) for sub in operand if isinstance(sub, dict))
    return False
