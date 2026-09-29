"""The immutable object-key proposal, and collision safety over an identity register.

A key binds four things: artifact id, artifact version, content identity (sha256 over the
exact bytes) and content type. Only the first two and the type appear in the key *string* —
the Backend's convention is `<artifact>.<country>.v<version>.json` and the KB does not invent
a different one — so the hash is bound by *registration* instead: a key is recorded against
the digest it was proposed for, and proposing the same key for different bytes is a collision.

That distinction matters. A key that carried its own hash would be self-verifying but would
break the convention Backend, Mobile and R2 already use. A key that carries only a version is
self-consistent but says nothing about content. Registering the pair makes the binding
checkable without changing the address, which is what "never reused for changed content"
actually requires.

Nothing here creates, alters or contacts a bucket. `propose_key` returns a string and a set of
reasons; `IdentityRegister` is an in-memory record of what this run has seen.
"""

import re

from .contract import VERSION_PATTERN
from .origin import validate_object_key
from .reasons import reason

_VERSION_RE = re.compile(VERSION_PATTERN)
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def propose_key(artifact_id, artifact_version, country, path="object_key"):
    """Propose the immutable key for an identity, with every reason it would be unusable.

    Returns `(key_or_None, reasons)`. A key is returned alongside reasons when it was
    constructible but unsafe, so a caller can report *which* key was rejected.
    """
    reasons = []

    if not isinstance(artifact_id, str) or artifact_id == "":
        reasons.append(reason("OBJECT_KEY_INVALID", path, "artifact_id is required to form a key"))
    if not isinstance(artifact_version, str) or not _VERSION_RE.match(str(artifact_version)):
        reasons.append(
            reason(
                "KB_KEY_VERSION_DISAGREEMENT",
                path,
                "artifact_version %r is not a dotted numeric version and cannot be encoded in a "
                "key" % (artifact_version,),
            )
        )
    if not isinstance(country, str) or not re.match(r"^[a-z]{2}$", str(country)):
        reasons.append(
            reason("OBJECT_KEY_INVALID", path, "country %r is not a two-letter code" % (country,))
        )
    if reasons:
        return None, reasons

    key = "%s.%s.v%s.json" % (artifact_id, country, artifact_version)
    return key, validate_object_key(key, path)


def check_key_agrees_with_identity(object_key, artifact_id, artifact_version, country, path):
    """A key must decode back to the identity it claims to name.

    The Backend validates the key's *shape*; nothing there checks that
    `question_flow.ng.v1.1.json` actually belongs to `question_flow@1.1`. A key that names one
    version while the descriptor declares another is the exact shape of an accidental
    overwrite, so the disagreement is rejected here.
    """
    reasons = []
    expected, key_reasons = propose_key(artifact_id, artifact_version, country, path)
    if key_reasons:
        return key_reasons
    if object_key != expected:
        reasons.append(
            reason(
                "KB_KEY_VERSION_DISAGREEMENT",
                path,
                "object key %r does not encode identity %s@%s (%s); expected %r"
                % (object_key, artifact_id, artifact_version, country, expected),
            )
        )
    return reasons


class IdentityRegister:
    """An in-memory register binding object keys to the content identity proposed for them.

    Purely a bookkeeping structure for one tooling run. It knows nothing about what exists in
    storage — asserting otherwise would be inventing infrastructure evidence this repository
    does not have. What it can prove is internal: within one plan or one manifest, a key is
    never proposed twice for different bytes, and an identity never claims two keys.
    """

    def __init__(self):
        self._by_key = {}
        self._by_identity = {}

    def register(self, object_key, artifact_id, artifact_version, sha256, path):
        """Record a key/identity/digest binding. Returns reasons the binding is unsafe."""
        reasons = []

        if not isinstance(sha256, str) or not _SHA256_RE.match(sha256):
            return [
                reason(
                    "MALFORMED_FIELD",
                    "%s.sha256" % path,
                    "a key can only be bound to a sha256:<64 hex> content identity",
                )
            ]

        identity = "%s@%s" % (artifact_id, artifact_version)
        existing = self._by_key.get(object_key)

        if existing is None:
            self._by_key[object_key] = {
                "identity": identity,
                "sha256": sha256,
                "path": path,
            }
        elif existing["sha256"] != sha256:
            reasons.append(
                reason(
                    "KB_KEY_OVERWRITE_DIFFERENT_BYTES",
                    path,
                    "object key %r was already bound to %s with digest %s; binding it to %s "
                    "would overwrite an immutable object with different bytes"
                    % (object_key, existing["identity"], existing["sha256"], sha256),
                )
            )
        elif existing["identity"] != identity:
            reasons.append(
                reason(
                    "KB_KEY_IDENTITY_COLLISION",
                    path,
                    "object key %r is claimed by both %s and %s"
                    % (object_key, existing["identity"], identity),
                )
            )

        claimed = self._by_identity.get(identity)
        if claimed is None:
            self._by_identity[identity] = object_key
        elif claimed != object_key:
            reasons.append(
                reason(
                    "KB_KEY_IDENTITY_COLLISION",
                    path,
                    "identity %s claims two different keys, %r and %r"
                    % (identity, claimed, object_key),
                )
            )

        return reasons

    def digest_for(self, object_key):
        entry = self._by_key.get(object_key)
        return entry["sha256"] if entry else None

    def keys(self):
        return dict(self._by_key)
