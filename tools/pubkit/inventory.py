"""The governed artifact inventory.

Every file in this repository whose name matches the immutable object-key convention
`<artifact>.<country>.v<version>.json` is a governed artifact: something that either has been
published under that key or is a candidate to be. The inventory is discovered from the
filesystem rather than listed by hand, so an artifact cannot be quietly added or removed
without the generated report changing.

Discovery is deliberately narrow. Reports, fixtures, schemas and evidence tables are not
governed artifacts and are not swept in: they are not distributable objects and giving them
object keys would blur exactly the line this step exists to draw.

Each entry records where the bytes live, what they hash to, how large they are, which
lifecycle role the repository assigns them, and — crucially — that the role is a *repository*
fact. `role: "published_lineage"` means "this file sits where published artifacts sit", not
"this is published"; the tooling cannot see R2 and never claims to.
"""

import os
import re

from .integrity import bare_sha256_of_bytes, content_type_of, read_exact_bytes
from .keys import propose_key
from .reasons import reason

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Directories swept for governed artifacts, and the role assigned to what is found there.
#: The repository root is where published artifacts live (see candidate/CANDIDATE_STATUS.md);
#: `candidate/` is where unapproved candidates live, by that same convention.
GOVERNED_LOCATIONS = (
    (".", "published_lineage"),
    ("candidate", "candidate"),
)

_ARTIFACT_FILENAME_RE = re.compile(r"^([a-z][a-z0-9_]*)\.([a-z]{2})\.v(\d+(?:\.\d+)*)\.json$")


def _role_note(role):
    if role == "published_lineage":
        return (
            "Sits at the repository root, the directory published artifacts are uploaded from. "
            "That is a location, not a publication status: this tooling cannot observe storage "
            "and does not assert the object exists at its key."
        )
    return (
        "Sits in candidate/, the directory for unapproved release candidates. Not published, "
        "not approved, not uploaded, not referenced by any manifest."
    )


def discover(repo_root=REPO_ROOT):
    """Return the governed inventory as an ordered list of entries.

    Sorted by `(artifact_id, version tuple, role)` so the generated report is byte-stable
    regardless of filesystem ordering.
    """
    entries = []

    for directory, role in GOVERNED_LOCATIONS:
        absolute = os.path.join(repo_root, directory)
        if not os.path.isdir(absolute):
            continue
        for filename in sorted(os.listdir(absolute)):
            match = _ARTIFACT_FILENAME_RE.match(filename)
            if match is None:
                continue
            path = os.path.join(absolute, filename)
            if not os.path.isfile(path):
                continue

            artifact_id, country, version = match.group(1), match.group(2), match.group(3)
            data = read_exact_bytes(path)
            content_type, content_reason = content_type_of(path)
            object_key, key_reasons = propose_key(artifact_id, version, country)

            relative = os.path.relpath(path, repo_root).replace(os.sep, "/")
            entries.append(
                {
                    "artifact_id": artifact_id,
                    "artifact_version": version,
                    "country": country,
                    "repository_path": relative,
                    "role": role,
                    "role_note": _role_note(role),
                    "sha256": bare_sha256_of_bytes(data),
                    "descriptor_sha256": "sha256:%s" % bare_sha256_of_bytes(data),
                    "byte_count": len(data),
                    "content_type": content_type,
                    "object_key": object_key,
                    "object_key_reasons": key_reasons + ([content_reason] if content_reason else []),
                    "filename_matches_object_key": object_key == filename,
                }
            )

    entries.sort(key=lambda entry: (entry["artifact_id"], _version_key(entry["artifact_version"]), entry["role"]))
    return entries


def _version_key(version):
    return tuple(int(part) for part in version.split("."))


def index_by_identity(entries):
    """`{"artifact_id@version": entry}`, refusing to silently collapse a duplicate identity."""
    index = {}
    duplicates = []
    for entry in entries:
        identity = "%s@%s" % (entry["artifact_id"], entry["artifact_version"])
        if identity in index:
            duplicates.append(identity)
        else:
            index[identity] = entry
    return index, duplicates


def find(entries, artifact_id, artifact_version):
    for entry in entries:
        if entry["artifact_id"] == artifact_id and entry["artifact_version"] == artifact_version:
            return entry
    return None


def check_inventory(entries):
    """Structural problems with the inventory itself."""
    reasons = []
    index, duplicates = index_by_identity(entries)

    for identity in duplicates:
        reasons.append(
            reason(
                "KB_KEY_IDENTITY_COLLISION",
                "inventory(%s)" % identity,
                "two governed files claim identity %s; one identity addresses one set of bytes" % identity,
            )
        )

    by_key = {}
    for entry in entries:
        key = entry["object_key"]
        if key is None:
            continue
        if key in by_key and by_key[key]["sha256"] != entry["sha256"]:
            reasons.append(
                reason(
                    "KB_KEY_OVERWRITE_DIFFERENT_BYTES",
                    "inventory(%s)" % key,
                    "object key %s is claimed by %s and %s with different bytes"
                    % (key, by_key[key]["repository_path"], entry["repository_path"]),
                )
            )
        else:
            by_key[key] = entry

        reasons.extend(entry["object_key_reasons"])
        if not entry["filename_matches_object_key"]:
            reasons.append(
                reason(
                    "KB_KEY_VERSION_DISAGREEMENT",
                    entry["repository_path"],
                    "filename does not equal the object key its identity implies (%s)" % key,
                )
            )

    return reasons
