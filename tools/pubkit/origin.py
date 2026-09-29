"""Origin, transport and object-key policy.

The Backend half is a port of `wellapath-backend/src/manifest/origin.ts` at the pinned commit:
an object key must match the immutable naming convention, and a URL must be HTTPS on an
approved origin with no credentials, query string or fragment, resolving to exactly the
declared key.

The Knowledge Base half adds rejections the contract permits but does not itself perform.
Backend's `OBJECT_KEY_PATTERN` already excludes traversal, absolute paths and unsafe
characters as a side effect of what it matches; the KB tests for them *by name* anyway, so a
rejected key reports why it was rejected rather than only that it failed a regex. Extra
rejections are always contract-safe — they can only shrink the set of keys the KB is willing
to propose, never widen what the Backend will accept.
"""

import re
import unicodedata

from .contract import APPROVED_ARTIFACT_ORIGINS, OBJECT_KEY_PATTERN
from .reasons import reason

_KEY_RE = re.compile(OBJECT_KEY_PATTERN)

#: Names that address "whatever is current" rather than one immutable object. An alias key
#: would let the same address serve different bytes over time, which is the single property
#: an immutable key exists to deny.
MUTABLE_ALIASES = (
    "latest",
    "current",
    "stable",
    "live",
    "head",
    "newest",
    "default",
    "prod",
    "production",
    "active",
    "main",
)

#: Substrings that turn a key into a request rather than a name. Unambiguous: none of these
#: can occur in a legitimate `<artifact>.<country>.v<version>.json` key.
_REQUEST_MARKERS = ("?", "&", "#", "=", "%", "x-amz-")

#: Credential words, matched as whole key segments rather than as substrings.
#:
#: Two deliberate narrowings. Substring matching would reject clinically legitimate names —
#: this repository's vocabulary contains words like "secretion" — so a word only counts when
#: it *is* a segment. And "token" and "key" are absent on purpose: in this domain a token is a
#: clinical symptom token and `token_dictionary.ng.v1.1.json` is a published artifact, so
#: treating either word as credential-shaped would reject real keys. Query-string secrets,
#: which is the case that actually matters, are caught structurally by `_REQUEST_MARKERS`
#: instead — an immutable key contains no `?`, `&`, `#`, `=` or `%` at all.
_CREDENTIAL_WORDS = frozenset(
    [
        "signature",
        "sig",
        "secret",
        "secrets",
        "credential",
        "credentials",
        "password",
        "passwd",
        "apikey",
        "accesskey",
        "authorization",
        "bearer",
        "sessiontoken",
    ]
)

_TRAVERSAL_MARKERS = ("..", "./", "/.", "\\")


def validate_object_key(object_key, path):
    """Every reason an object key is unusable. Empty means the key is a safe immutable name.

    Named checks run before the contract regex so the reported reason is the specific defect.
    All checks run: a key that is both traversal and alias reports both.
    """
    reasons = []

    if not isinstance(object_key, str):
        return [reason("OBJECT_KEY_INVALID", path, "object key must be a string")]
    if object_key == "":
        return [reason("OBJECT_KEY_INVALID", path, "object key must not be empty")]

    if object_key.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", object_key):
        reasons.append(
            reason(
                "KB_KEY_ABSOLUTE_PATH",
                path,
                "object key is an absolute path; a key names an object in a bucket, not a "
                "location on a filesystem: %r" % object_key,
            )
        )
    if any(marker in object_key for marker in _TRAVERSAL_MARKERS):
        reasons.append(
            reason(
                "KB_KEY_PATH_TRAVERSAL",
                path,
                "object key contains a path-traversal or separator sequence: %r" % object_key,
            )
        )

    lowered = object_key.lower()
    segments = [segment for segment in re.split(r"[./_\\-]", lowered) if segment]

    if any(marker in lowered for marker in _REQUEST_MARKERS) or (
        _CREDENTIAL_WORDS & set(segments)
    ):
        reasons.append(
            reason(
                "KB_KEY_EMBEDS_SECRET",
                path,
                "object key embeds a query, fragment or credential-shaped segment; an "
                "immutable object takes no parameters and names no secret",
            )
        )

    # `v` prefixes the version segment, so `vlatest` is an alias wearing the version's clothes.
    normalised_segments = set(segments) | {
        segment[1:] for segment in segments if segment.startswith("v")
    }
    for alias in MUTABLE_ALIASES:
        if alias in normalised_segments:
            reasons.append(
                reason(
                    "KB_KEY_MUTABLE_ALIAS",
                    path,
                    "object key contains the mutable alias %r; a key must address exactly one "
                    "immutable set of bytes forever" % alias,
                )
            )
            break

    if unicodedata.normalize("NFC", object_key) != object_key or not object_key.isascii():
        reasons.append(
            reason(
                "KB_KEY_AMBIGUOUS_NORMALIZATION",
                path,
                "object key is not already NFC-normalised ASCII; two spellings that normalise "
                "to one key would be two names for one object",
            )
        )
    elif re.search(r"[^a-z0-9._]", object_key):
        reasons.append(
            reason(
                "KB_KEY_UNSAFE_CHARACTER",
                path,
                "object key contains a character outside [a-z0-9._]: %r" % object_key,
            )
        )

    if not _KEY_RE.match(object_key):
        reasons.append(
            reason(
                "OBJECT_KEY_INVALID",
                path,
                "object key does not match the immutable naming convention "
                "<artifact>.<country>.v<version>.json: %r" % object_key,
            )
        )

    return reasons


def validate_artifact_url(url, object_key, path):
    """Port of the Backend's `validateArtifactUrl`. Parsed the same way, rejected the same way."""
    try:
        from urllib.parse import urlsplit
    except ImportError:  # pragma: no cover - Python 3 only
        raise

    reasons = []

    if not isinstance(url, str):
        return [reason("MALFORMED_FIELD", path, "url must be a string when present")]

    try:
        parsed = urlsplit(url)
    except ValueError:
        return [reason("MALFORMED_FIELD", path, "url is not parseable")]
    if parsed.scheme == "" or parsed.netloc == "":
        return [reason("MALFORMED_FIELD", path, "url is not parseable as an absolute URL")]

    if parsed.scheme != "https":
        reasons.append(reason("ORIGIN_NOT_HTTPS", path, "protocol %s: refused" % parsed.scheme))
    if parsed.username or parsed.password:
        reasons.append(
            reason(
                "ORIGIN_HAS_CREDENTIALS",
                path,
                "url embeds credentials; credentials are never permitted in a manifest",
            )
        )
    if parsed.query or parsed.fragment:
        reasons.append(
            reason(
                "ORIGIN_HAS_QUERY",
                path,
                "url carries a query string or fragment; immutable objects take no parameters",
            )
        )

    origin = "%s://%s" % (parsed.scheme, parsed.netloc)
    if origin not in APPROVED_ARTIFACT_ORIGINS:
        reasons.append(
            reason(
                "ORIGIN_NOT_APPROVED", path, "origin %s is not an approved artifact origin" % origin
            )
        )
    elif parsed.path != "/%s" % object_key:
        reasons.append(
            reason(
                "ORIGIN_NOT_APPROVED",
                path,
                "url path %s does not resolve to the declared object key" % parsed.path,
            )
        )

    return reasons
