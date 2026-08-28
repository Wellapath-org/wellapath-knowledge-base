"""A small, dependency-free JSON Schema validator.

`jsonschema` is not available in this repository (there is no dependency
manifest at all — see `tools/vocab/__init__.py`), but the W2 contract requires a
*machine-validated* schema rather than a prose one. This module implements the
subset of JSON Schema draft 2020-12 that `schema/token_dictionary.v2.schema.json`
actually uses, so the shipped schema file is executable here and remains a
standard document that Backend (Ajv) and Mobile can validate against with their
own tooling.

Supported keywords:
    $ref (local "#/$defs/..." pointers only), type, enum, const,
    properties, required, additionalProperties, patternProperties,
    items, prefixItems, minItems, maxItems, uniqueItems,
    minLength, maxLength, pattern, minimum, maximum,
    minProperties, maxProperties,
    allOf, anyOf, oneOf, not, propertyNames,
    format ("date" and "date-time" only, asserted rather than annotated).

Anything outside that list raises `UnsupportedKeyword` rather than being
silently ignored — a validator that quietly skips a constraint is worse than no
validator at all.

`validate(..., extra_keywords=...)` widens *only* the set of keywords tolerated
as annotations, for schemas authored elsewhere that carry vocabulary this
validator has no assertion for (the vendored Backend contract, for instance, is
draft-07 and keeps its subschemas under `definitions` alongside a
`contract_version` annotation).

The parameter is **closed, not open**: a caller may only name keywords listed in
`ANNOTATION_ONLY_KEYWORDS`, and asking to tolerate anything else raises. That
restriction is the whole safety property. An unrestricted version would let a
caller pass `multipleOf`, `contains` or `dependentRequired` — real assertions
this validator does not implement — and the constraint they express would be
silently dropped while validation reported success, which is strictly worse than
not validating at all. Tolerating a keyword must never be a way to stop checking
one.

Note what the parameter does *not* touch: every assertion in this module is
driven by an explicit `if "<keyword>" in schema` test, never by the allowlist, so
naming an already-supported keyword changes nothing either. Anything
unrecognised and unlisted raises as before.
"""

import re

_SUPPORTED = frozenset(
    [
        "$ref", "$id", "$schema", "$defs", "$comment", "title", "description",
        "type", "enum", "const", "default", "examples",
        "properties", "required", "additionalProperties", "patternProperties",
        "propertyNames", "minProperties", "maxProperties",
        "items", "prefixItems", "minItems", "maxItems", "uniqueItems",
        "minLength", "maxLength", "pattern",
        "minimum", "maximum",
        "allOf", "anyOf", "oneOf", "not",
        "format",
    ]
)

#: The only keywords `validate(extra_keywords=...)` will tolerate. Closed set, one line of
#: justification each, and every entry must be verifiably assertion-free:
#:
#:  * `definitions` — draft-07's subschema container. It asserts nothing where it appears; it
#:    holds subschemas that `$ref` resolves into, and `_resolve_ref` walks the raw schema dict,
#:    so refs into it are still applied in full.
#:  * `contract_version` — a custom annotation on the Backend contract's root object. Not a
#:    JSON Schema keyword at all, so it cannot express a constraint in any dialect.
#:
#: Adding an entry here means asserting that the keyword carries no constraint in any dialect
#: a schema in this repository might use. That claim needs checking, not assuming.
ANNOTATION_ONLY_KEYWORDS = frozenset(["definitions", "contract_version"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


class UnsupportedKeyword(Exception):
    pass


# The allowlist may not overlap the keywords this validator already handles: an entry that did
# would be pointless at best, and at worst would suggest the allowlist can influence how a
# supported keyword is treated. It cannot — but the invariant is cheap to assert and expensive
# to rediscover.
assert ANNOTATION_ONLY_KEYWORDS.isdisjoint(_SUPPORTED), (
    "ANNOTATION_ONLY_KEYWORDS must not name keywords this validator already implements: %s"
    % ", ".join(sorted(ANNOTATION_ONLY_KEYWORDS & _SUPPORTED))
)


def _type_ok(value, expected):
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise UnsupportedKeyword("unknown type %r" % expected)


def _resolve_ref(root, ref):
    if not ref.startswith("#/"):
        raise UnsupportedKeyword("only local $ref pointers are supported, got %r" % ref)
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def validate(instance, schema, root=None, path="$", extra_keywords=frozenset()):
    """Return a list of human-readable error strings. Empty means valid."""
    root = schema if root is None else root
    errors = []

    if schema is True:
        return errors
    if schema is False:
        return ["%s: schema is `false` — no value is valid here" % path]

    extra = frozenset(extra_keywords)
    forbidden = extra - ANNOTATION_ONLY_KEYWORDS
    if forbidden:
        raise UnsupportedKeyword(
            "extra_keywords may only name keywords known to carry no assertion (%s); refusing "
            "to tolerate %s. Tolerating an assertion keyword would silently drop the constraint "
            "it expresses while reporting success."
            % (
                ", ".join(sorted(ANNOTATION_ONLY_KEYWORDS)),
                ", ".join(sorted(forbidden)),
            )
        )

    unknown = set(schema) - _SUPPORTED - extra
    if unknown:
        raise UnsupportedKeyword(
            "%s: schema uses keyword(s) this validator does not implement: %s"
            % (path, ", ".join(sorted(unknown)))
        )

    if "$ref" in schema:
        errors.extend(
            validate(instance, _resolve_ref(root, schema["$ref"]), root, path, extra_keywords)
        )

    if "type" in schema:
        expected = schema["type"]
        expected_list = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(instance, t) for t in expected_list):
            return errors + [
                "%s: expected type %s, got %s"
                % (path, "/".join(expected_list), type(instance).__name__)
            ]

    if "const" in schema and instance != schema["const"]:
        errors.append("%s: expected const %r, got %r" % (path, schema["const"], instance))

    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r is not one of %r" % (path, instance, schema["enum"]))

    if isinstance(instance, str):
        errors.extend(_validate_string(instance, schema, path))
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: %r < minimum %r" % (path, instance, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: %r > maximum %r" % (path, instance, schema["maximum"]))
    if isinstance(instance, list):
        errors.extend(_validate_array(instance, schema, root, path, extra_keywords))
    if isinstance(instance, dict):
        errors.extend(_validate_object(instance, schema, root, path, extra_keywords))

    errors.extend(_validate_combinators(instance, schema, root, path, extra_keywords))
    return errors


def _validate_string(instance, schema, path):
    errors = []
    if "minLength" in schema and len(instance) < schema["minLength"]:
        errors.append("%s: length %d < minLength %d" % (path, len(instance), schema["minLength"]))
    if "maxLength" in schema and len(instance) > schema["maxLength"]:
        errors.append("%s: length %d > maxLength %d" % (path, len(instance), schema["maxLength"]))
    if "pattern" in schema and re.search(schema["pattern"], instance) is None:
        errors.append("%s: %r does not match pattern %r" % (path, instance, schema["pattern"]))
    fmt = schema.get("format")
    if fmt == "date" and _DATE_RE.match(instance) is None:
        errors.append("%s: %r is not a YYYY-MM-DD date" % (path, instance))
    elif fmt == "date-time" and _DATE_TIME_RE.match(instance) is None:
        errors.append("%s: %r is not an RFC 3339 date-time" % (path, instance))
    elif fmt not in (None, "date", "date-time"):
        raise UnsupportedKeyword("%s: unsupported format %r" % (path, fmt))
    return errors


def _validate_array(instance, schema, root, path, extra_keywords=frozenset()):
    errors = []
    if "minItems" in schema and len(instance) < schema["minItems"]:
        errors.append("%s: %d items < minItems %d" % (path, len(instance), schema["minItems"]))
    if "maxItems" in schema and len(instance) > schema["maxItems"]:
        errors.append("%s: %d items > maxItems %d" % (path, len(instance), schema["maxItems"]))
    if schema.get("uniqueItems") is True:
        seen = []
        for item in instance:
            if item in seen:
                errors.append("%s: duplicate item %r" % (path, item))
                break
            seen.append(item)
    prefix = schema.get("prefixItems", [])
    for index, sub in enumerate(prefix):
        if index < len(instance):
            errors.extend(
                validate(instance[index], sub, root, "%s[%d]" % (path, index), extra_keywords)
            )
    if "items" in schema:
        for index in range(len(prefix), len(instance)):
            errors.extend(
                validate(
                    instance[index],
                    schema["items"],
                    root,
                    "%s[%d]" % (path, index),
                    extra_keywords,
                )
            )
    return errors


def _validate_object(instance, schema, root, path, extra_keywords=frozenset()):
    errors = []
    if "minProperties" in schema and len(instance) < schema["minProperties"]:
        errors.append(
            "%s: %d properties < minProperties %d"
            % (path, len(instance), schema["minProperties"])
        )
    if "maxProperties" in schema and len(instance) > schema["maxProperties"]:
        errors.append(
            "%s: %d properties > maxProperties %d"
            % (path, len(instance), schema["maxProperties"])
        )
    for name in schema.get("required", []):
        if name not in instance:
            errors.append("%s: missing required property %r" % (path, name))

    properties = schema.get("properties", {})
    pattern_properties = schema.get("patternProperties", {})
    for name, value in instance.items():
        matched = False
        if name in properties:
            matched = True
            errors.extend(
                validate(value, properties[name], root, "%s.%s" % (path, name), extra_keywords)
            )
        for pattern, sub in pattern_properties.items():
            if re.search(pattern, name):
                matched = True
                errors.extend(
                    validate(value, sub, root, "%s.%s" % (path, name), extra_keywords)
                )
        if not matched:
            extra = schema.get("additionalProperties", True)
            if extra is False:
                errors.append("%s: unexpected property %r" % (path, name))
            elif isinstance(extra, dict):
                errors.extend(
                    validate(value, extra, root, "%s.%s" % (path, name), extra_keywords)
                )
        if "propertyNames" in schema:
            errors.extend(
                validate(
                    name,
                    schema["propertyNames"],
                    root,
                    "%s.<key %r>" % (path, name),
                    extra_keywords,
                )
            )
    return errors


def _validate_combinators(instance, schema, root, path, extra_keywords=frozenset()):
    errors = []
    for sub in schema.get("allOf", []):
        errors.extend(validate(instance, sub, root, path, extra_keywords))
    if "anyOf" in schema:
        if not any(
            not validate(instance, sub, root, path, extra_keywords) for sub in schema["anyOf"]
        ):
            errors.append("%s: does not match any subschema in anyOf" % path)
    if "oneOf" in schema:
        matches = sum(
            1
            for sub in schema["oneOf"]
            if not validate(instance, sub, root, path, extra_keywords)
        )
        if matches != 1:
            errors.append("%s: matched %d subschemas in oneOf, expected exactly 1" % (path, matches))
    if "not" in schema and not validate(instance, schema["not"], root, path, extra_keywords):
        errors.append("%s: matched a subschema forbidden by `not`" % path)
    return errors
