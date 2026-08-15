"""Artifact serialization and hashing helpers.

The repository already has a de-facto serialization convention, verified against
the frozen artifacts: `json.dumps(obj, indent=2, ensure_ascii=True)` with **no
trailing newline**. `token_dictionary.ng.v1.1.json` and `kb.ng.v2.4.json` both
reproduce byte-for-byte under it (`rules.ng.v2.2.json` has a trailing newline,
which is why the projection test targets the token dictionary specifically).

Every generator here writes bytes through `dump_artifact_bytes` so that
generation is deterministic and the published SHA256 is reproducible on any
machine.
"""

import hashlib
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def repo_path(*parts):
    return os.path.join(REPO_ROOT, *parts)


def dump_artifact_bytes(obj):
    """Serialize an artifact to its canonical on-disk bytes."""
    return json.dumps(obj, indent=2, ensure_ascii=True).encode("utf-8")


def dump_report_bytes(obj):
    """Serialize a generated report.

    Reports are machine-readable outputs rather than distributed artifacts, so
    they get a trailing newline for tidy diffs. Key order is preserved (not
    sorted) so the emitted structure reads in a deliberate order.
    """
    return (json.dumps(obj, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def write_bytes(path, data):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load_json(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def file_size(path):
    return os.path.getsize(path)
