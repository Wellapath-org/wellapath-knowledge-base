"""Deterministic extraction of the current question flow from vendored Dart.

The current flow has no versioned artifact. Its authoritative definition is Dart
source in the mobile repository, so this module parses vendored copies of that
source rather than inventing a schema and hand-transcribing values into it —
hand-transcription is exactly how a baseline stops matching the thing it claims
to freeze.

Scope of the parser, stated plainly: it recognises the specific literal forms
these six files actually use — `const Map<String, List<FollowupQuestion>>`,
`const List<RedFlagClarifier>`, `const Map<String, String>`,
`const Map<String, List<String>>` — and nothing else. It is not a Dart parser.
Every extractor below raises on a shape it does not recognise rather than
returning a partial result, so a future edit to the Dart that this cannot read
fails loudly instead of silently shrinking the baseline.
"""

import os
import re

BASELINE_DIR = "baseline/questions_v1"

VENDORED_FILES = [
    "followup_question_map.vendored.dart",
    "red_flag_clarifiers.vendored.dart",
    "symptom_display_map.vendored.dart",
    "question_engine.vendored.dart",
    "assessment_controller.vendored.dart",
    "followup_screen.vendored.dart",
    "followup_question.vendored.dart",
]


class DartParseError(Exception):
    pass


def _read(repo_root, filename):
    path = os.path.join(repo_root, BASELINE_DIR, filename)
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8")


def _strip_line_comments(text):
    """Remove `//` comments without touching `//` inside a string literal."""
    out = []
    for line in text.split("\n"):
        result = []
        in_string = None
        i = 0
        while i < len(line):
            ch = line[i]
            if in_string:
                if ch == "\\":
                    result.append(line[i : i + 2])
                    i += 2
                    continue
                if ch == in_string:
                    in_string = None
                result.append(ch)
            elif ch in "'\"":
                in_string = ch
                result.append(ch)
            elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            else:
                result.append(ch)
            i += 1
        out.append("".join(result))
    return "\n".join(out)


def _block(text, header):
    """Return the body between the braces of `header ... = { ... };`."""
    start = text.find(header)
    if start < 0:
        raise DartParseError("declaration not found: %r" % header)
    open_idx = text.find("{", start)
    if open_idx < 0:
        raise DartParseError("no opening brace after %r" % header)
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i]
    raise DartParseError("unbalanced braces after %r" % header)


def _list_block(text, header):
    """Return the body between the brackets of `header ... = [ ... ];`."""
    start = text.find(header)
    if start < 0:
        raise DartParseError("declaration not found: %r" % header)
    open_idx = text.find("[", start)
    if open_idx < 0:
        raise DartParseError("no opening bracket after %r" % header)
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i]
    raise DartParseError("unbalanced brackets after %r" % header)


# Dart string literals appear in both quote styles here: the display map uses
# double quotes for keys that themselves contain an apostrophe
# (e.g. "Fear of water / can't swallow liquids").
_SQ = r"'((?:[^'\\]|\\.)*)'"
_DQ = r'"((?:[^"\\]|\\.)*)"'
_STRING = r"(?:" + _SQ + r"|" + _DQ + r")"

_STRING_RE = re.compile(_STRING)


def _unescape(value):
    return (
        value.replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
        .replace("\\n", "\n")
    )


def _first_group(match):
    """A _STRING match has two alternatives; exactly one participates."""
    return _unescape(match.group(1) if match.group(1) is not None else match.group(2))


def _string_list(fragment):
    return [_first_group(m) for m in _STRING_RE.finditer(fragment)]


def _split_top_level(body, opener, closer):
    """Split a body on commas that sit at nesting depth 0."""
    parts, depth, current, in_string = [], 0, [], None
    i = 0
    while i < len(body):
        ch = body[i]
        if in_string:
            current.append(ch)
            if ch == "\\":
                if i + 1 < len(body):
                    current.append(body[i + 1])
                    i += 2
                    continue
            elif ch == in_string:
                in_string = None
        elif ch in "'\"":
            in_string = ch
            current.append(ch)
        elif ch in opener:
            depth += 1
            current.append(ch)
        elif ch in closer:
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    if "".join(current).strip():
        parts.append("".join(current))
    return parts


# --- followup_question_map.dart -----------------------------------------------

_QUESTION_RE = re.compile(
    r"FollowupQuestion\s*\(\s*type:\s*QuestionType\.(?P<type>\w+)\s*,"
    r"\s*questionText:\s*(?P<text>" + _STRING + r")\s*,"
    r"(?:\s*options:\s*\[(?P<options>[^\]]*)\]\s*,?)?",
    re.S,
)


def _one_string(fragment):
    """Extract the single string literal in `fragment`."""
    values = _string_list(fragment)
    if len(values) != 1:
        raise DartParseError("expected exactly one string literal in %r" % fragment[:60])
    return values[0]


def parse_followup_question_map(repo_root):
    """token_id -> ordered list of {type, question_text, options}."""
    text = _strip_line_comments(_read(repo_root, "followup_question_map.vendored.dart"))
    body = _block(text, "const Map<String, List<FollowupQuestion>> kFollowupQuestionMap")

    entries = {}
    order = []
    for chunk in _split_top_level(body, "[{(", "]})"):
        chunk = chunk.strip()
        if not chunk:
            continue
        key = re.match(r"\s*(?P<key>" + _STRING + r")\s*:", chunk)
        if not key:
            raise DartParseError("map entry without a string key: %r" % chunk[:60])
        token = _one_string(key.group("key"))
        questions = []
        for match in _QUESTION_RE.finditer(chunk):
            questions.append(
                {
                    "type": match.group("type"),
                    "question_text": _one_string(match.group("text")),
                    "options": _string_list(match.group("options") or ""),
                }
            )
        if not questions:
            raise DartParseError("map entry %r produced no questions" % token)
        entries[token] = questions
        order.append(token)

    if not entries:
        raise DartParseError("kFollowupQuestionMap parsed as empty")

    default_match = _QUESTION_RE.search(
        text[text.find("kDefaultFollowupQuestion") :]
    )
    if not default_match:
        raise DartParseError("kDefaultFollowupQuestion not found")
    default = {
        "type": default_match.group("type"),
        "question_text": _one_string(default_match.group("text")),
        "options": _string_list(default_match.group("options") or ""),
    }
    return {"entries": entries, "order": order, "default_question": default}


# --- red_flag_clarifiers.dart --------------------------------------------------


def parse_red_flag_clarifiers(repo_root):
    text = _strip_line_comments(_read(repo_root, "red_flag_clarifiers.vendored.dart"))
    body = _list_block(text, "const List<RedFlagClarifier> kRedFlagClarifiers")

    clarifiers = []
    for chunk in _split_top_level(body, "[{(", "]})"):
        if "RedFlagClarifier" not in chunk:
            continue
        triggers = re.search(r"triggerTokens:\s*\[([^\]]*)\]", chunk, re.S)
        flag = re.search(r"redFlagToken:\s*(?P<f>" + _STRING + r")", chunk)
        question = re.search(r"questionText:\s*(?P<q>(?:" + _STRING + r"\s*)+)", chunk, re.S)
        if not (triggers and flag and question):
            raise DartParseError("incomplete RedFlagClarifier: %r" % chunk[:80])
        clarifiers.append(
            {
                "trigger_tokens": _string_list(triggers.group(1)),
                "red_flag_token": _one_string(flag.group("f")),
                # Dart adjacent-string concatenation: join the parts in order.
                "question_text": "".join(_string_list(question.group("q"))),
            }
        )
    if not clarifiers:
        raise DartParseError("kRedFlagClarifiers parsed as empty")
    return clarifiers


# --- symptom_display_map.dart --------------------------------------------------


def _string_string_map(body):
    pairs = []
    for chunk in _split_top_level(body, "[{(", "]})"):
        match = re.match(
            r"\s*(?P<k>" + _STRING + r")\s*:\s*(?P<v>" + _STRING + r")\s*$", chunk, re.S
        )
        if not match:
            if chunk.strip():
                raise DartParseError("unrecognised map entry: %r" % chunk[:60])
            continue
        pairs.append((_one_string(match.group("k")), _one_string(match.group("v"))))
    return pairs


def parse_symptom_display_map(repo_root):
    text = _strip_line_comments(_read(repo_root, "symptom_display_map.vendored.dart"))
    display = _string_string_map(_block(text, "kSymptomDisplayMap"))

    body_area_body = _block(text, "const Map<String, List<String>> kBodyAreaSymptoms")
    areas = {}
    area_order = []
    for chunk in _split_top_level(body_area_body, "[{(", "]})"):
        match = re.match(
            r"\s*(?P<k>" + _STRING + r")\s*:\s*\[(?P<v>.*)\]\s*$", chunk, re.S
        )
        if not match:
            if chunk.strip():
                raise DartParseError("unrecognised body-area entry: %r" % chunk[:60])
            continue
        area = _one_string(match.group("k"))
        areas[area] = _string_list(match.group("v"))
        area_order.append(area)
    if not display or not areas:
        raise DartParseError("symptom display map or body-area map parsed as empty")
    return {
        "display_label_to_token": display,
        "body_area_symptoms": areas,
        "body_area_order": area_order,
    }


# --- assessment_controller.dart ------------------------------------------------


def parse_controller_maps(repo_root):
    text = _strip_line_comments(_read(repo_root, "assessment_controller.vendored.dart"))
    age = _string_string_map(_block(text, "_ageTokenMap"))
    conditions = _string_string_map(_block(text, "_medicalConditionTokenMap"))
    pregnancy = re.search(
        r"shouldShowPregnancyScreen\s*=>\s*_sex\s*==\s*(?P<v>" + _STRING + r")", text
    )
    if not (age and conditions and pregnancy):
        raise DartParseError("controller maps or pregnancy predicate not found")
    return {
        "age_label_to_token": age,
        "medical_condition_label_to_token": conditions,
        "pregnancy_shown_when_sex_equals": _one_string(pregnancy.group("v")),
    }


# --- followup_screen.dart ------------------------------------------------------


def parse_answer_mappings(repo_root):
    text = _strip_line_comments(_read(repo_root, "followup_screen.vendored.dart"))
    duration = _string_string_map(_block(text, "_durationTokens"))

    severity_fn = text[text.find("String _severityToken(") :]
    severity = []
    for match in re.finditer(
        r"if\s*\(value\s*<=\s*(?P<v>[0-9.]+)\)\s*return\s*(?P<t>" + _STRING + r")",
        severity_fn,
    ):
        severity.append(
            {"max_value": float(match.group("v")), "token": _one_string(match.group("t"))}
        )
    tail = re.search(r"return\s*(?P<t>" + _STRING + r")\s*;\s*\}", severity_fn)
    if not (duration and severity and tail):
        raise DartParseError("duration or severity answer mapping not found")
    severity.append({"max_value": 1.0, "token": _one_string(tail.group("t"))})
    return {"duration_answer_to_token": duration, "severity_bands": severity}


# --- question_engine.dart ------------------------------------------------------


def parse_engine_constants(repo_root):
    text = _strip_line_comments(_read(repo_root, "question_engine.vendored.dart"))
    limit = re.search(r"result\.length\s*>\s*(\d+)\s*\?\s*result\.sublist\(0,\s*(\d+)\)", text)
    if not limit or limit.group(1) != limit.group(2):
        raise DartParseError("path-length limit not found or inconsistent")
    ordering = []
    for name in ("clarifiers", "severityQuestion", "durationQuestion", "additionalOptions"):
        idx = text.find(name, text.find("final List<FollowupQuestion> result"))
        ordering.append((idx, name))
    ordering = [n for _, n in sorted(ordering) if _ >= 0]
    return {
        "max_followup_questions": int(limit.group(1)),
        "emission_order": ["red_flag_clarifier", "severity", "duration", "additional_symptoms"],
        "ordering_source_symbols": ordering,
        "dedupe_rule": "first token in the selected order wins for severity and duration; additional-symptom options are unioned preserving first-seen order",
    }


def parse_all(repo_root):
    return {
        "followup_question_map": parse_followup_question_map(repo_root),
        "red_flag_clarifiers": parse_red_flag_clarifiers(repo_root),
        "symptom_display": parse_symptom_display_map(repo_root),
        "controller": parse_controller_maps(repo_root),
        "answer_mappings": parse_answer_mappings(repo_root),
        "engine": parse_engine_constants(repo_root),
    }
