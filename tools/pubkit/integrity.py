"""Content integrity, computed from exact bytes and nothing else.

A port of `wellapath-backend/src/manifest/integrity.ts` at the pinned commit. Both checks run
unconditionally so a failure names every mismatch rather than the first, and both are computed
from the bytes on disk — never from a cached value, a recorded size, or anything a descriptor
claims about itself. A descriptor's `sha256` and `byte_count` are assertions to be tested, not
inputs to be trusted.
"""

import hashlib
import os
import re

from .contract import SHA256_PATTERN
from .reasons import reason

_SHA256_RE = re.compile(SHA256_PATTERN)


def sha256_of_bytes(data):
    """The descriptor-format digest (`sha256:<hex>`) of a byte string."""
    return "sha256:%s" % hashlib.sha256(data).hexdigest()


def bare_sha256_of_bytes(data):
    """The bare hex digest, for records that store hashes without the `sha256:` prefix."""
    return hashlib.sha256(data).hexdigest()


def read_exact_bytes(path):
    """Read a file in binary. The only way bytes enter this tooling.

    Text mode is never used: a newline translation or an encoding guess would change the
    bytes being hashed, and the hash must be of the object that would actually be uploaded.
    """
    with open(path, "rb") as handle:
        return handle.read()


def measure(path):
    """Return `(bytes, digest, byte_count)` for a file, all derived from one read."""
    data = read_exact_bytes(path)
    return data, sha256_of_bytes(data), len(data)


def verify_bytes(data, declared_sha256, declared_byte_count, path):
    """Verify bytes against a declared hash and byte count.

    Empty result means the bytes are exactly the object the declaration names.
    """
    reasons = []

    if not isinstance(declared_sha256, str) or not _SHA256_RE.match(declared_sha256):
        reasons.append(
            reason(
                "MALFORMED_FIELD",
                "%s.sha256" % path,
                "declared sha256 is not a valid sha256:<64 hex> digest",
            )
        )
    elif sha256_of_bytes(data) != declared_sha256:
        reasons.append(
            reason("HASH_MISMATCH", "%s.sha256" % path, "bytes do not hash to the declared sha256")
        )

    if len(data) != declared_byte_count:
        reasons.append(
            reason(
                "BYTE_COUNT_MISMATCH",
                "%s.byte_count" % path,
                "read %d bytes, declaration says %d" % (len(data), declared_byte_count),
            )
        )

    return reasons


def content_type_of(path):
    """Determine content type from the artifact itself, not from a caller's assertion.

    The contract admits exactly one content type. Rather than assume it, the file is parsed:
    a `.json` name over bytes that are not JSON is a mislabelled artifact, and returning
    `application/json` for it would put a false content type into a descriptor.
    """
    import json

    if not path.endswith(".json"):
        return None, reason(
            "KB_CONTENT_TYPE_UNDETERMINED",
            path,
            "only .json artifacts have a determinable content type under contract 1.0.0",
        )
    try:
        json.loads(read_exact_bytes(path).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        return None, reason(
            "KB_CONTENT_TYPE_UNDETERMINED",
            path,
            "named .json but the bytes do not parse as UTF-8 JSON: %s" % error,
        )
    return "application/json", None


def file_digest(path):
    """Bare hex digest of a file, or None when it is absent."""
    if not os.path.exists(path):
        return None
    return bare_sha256_of_bytes(read_exact_bytes(path))
