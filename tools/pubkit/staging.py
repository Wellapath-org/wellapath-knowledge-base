"""The disposable staging area, and the rule that nothing is written outside it.

Packaging copies artifact bytes somewhere so a package can be hashed and measured. That
"somewhere" is a single ignored, disposable directory under the repository, and every write
this tooling performs goes through `StagingArea.write`, which refuses any path that does not
resolve inside it — symlinks and `..` included, because the check is on the *resolved* path,
not the string.

Canonical artifacts are never written. `copy_artifact` reads bytes and writes a copy; it has
no mode that touches the source, and `verify_source_unchanged` re-hashes the source afterwards
so "we did not modify the canonical file" is a measurement rather than an assurance.
"""

import os
import shutil

from .integrity import bare_sha256_of_bytes, read_exact_bytes
from .reasons import reason

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Ignored via .gitignore. Nothing in here is ever committed, and nothing outside here is ever
#: written by packaging.
DEFAULT_STAGING_ROOT = os.path.join(REPO_ROOT, ".publication-staging")


class StagingEscape(Exception):
    """Raised when a write would land outside the staging area. Never caught to continue."""


class StagingArea:
    """A disposable directory that is the only place this tooling may write bytes.

    Use as a context manager: the directory is created on entry and removed on exit, including
    on an exception, so a failed run leaves nothing behind to be mistaken for a real package.
    """

    def __init__(self, root=DEFAULT_STAGING_ROOT, name="package"):
        self.root = os.path.abspath(root)
        self.name = name
        self.path = os.path.join(self.root, name)
        self.writes = []

    def __enter__(self):
        os.makedirs(self.path, exist_ok=True)
        # Resolve after creation so a symlinked staging root is caught here rather than on the
        # first write.
        self._resolved = os.path.realpath(self.path)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()
        return False

    def cleanup(self):
        """Remove the staging directory. Safe to call twice; never touches anything above it."""
        if not os.path.isdir(self.path):
            return
        resolved = os.path.realpath(self.path)
        repo = os.path.realpath(REPO_ROOT)
        if not resolved.startswith(os.path.realpath(self.root) + os.sep) and resolved != os.path.realpath(self.root):
            raise StagingEscape("refusing to remove %s: it is not inside the staging root" % resolved)
        if resolved == repo or repo.startswith(resolved + os.sep):
            raise StagingEscape("refusing to remove %s: it contains the repository" % resolved)
        shutil.rmtree(self.path)

        # Remove the staging root too, but only when this was the last package in it and only
        # when it is genuinely empty. `os.rmdir` refuses a non-empty directory, which is the
        # behaviour wanted here: a concurrent run's package must not be swept away, and a
        # lingering empty directory is the one thing left over that a reader could mistake for
        # a package that was never cleaned.
        try:
            os.rmdir(self.root)
        except OSError:
            pass

    def resolve(self, relative_name):
        """Resolve a name inside the staging area, refusing anything that escapes it."""
        if os.path.isabs(relative_name):
            raise StagingEscape("staging writes take a relative name, got absolute %r" % relative_name)
        target = os.path.realpath(os.path.join(self._resolved, relative_name))
        if target != self._resolved and not target.startswith(self._resolved + os.sep):
            raise StagingEscape(
                "write to %r resolves to %s, outside the staging area %s"
                % (relative_name, target, self._resolved)
            )
        return target

    def write(self, relative_name, data):
        """Write bytes into the staging area. The only write path in this package."""
        target = self.resolve(relative_name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(data)
        self.writes.append(target)
        return target

    def copy_artifact(self, source_path, relative_name=None):
        """Copy a canonical artifact into staging and return `(staged_path, digest, count)`.

        Reads the source and writes a copy. There is no code path here that opens the source
        for writing, and `verify_source_unchanged` proves the source is untouched afterwards.
        """
        data = read_exact_bytes(source_path)
        name = relative_name or os.path.basename(source_path)
        staged = self.write(name, data)
        return staged, bare_sha256_of_bytes(data), len(data)


def verify_source_unchanged(source_path, digest_before, path):
    """Re-hash a canonical artifact and report if a single byte moved."""
    if not os.path.exists(source_path):
        return [
            reason(
                "KB_CANONICAL_ARTIFACT_MUTATED",
                path,
                "the canonical artifact no longer exists at %s" % path,
            )
        ]
    digest_after = bare_sha256_of_bytes(read_exact_bytes(source_path))
    if digest_after != digest_before:
        return [
            reason(
                "KB_CANONICAL_ARTIFACT_MUTATED",
                path,
                "canonical artifact changed during the run: %s -> %s" % (digest_before, digest_after),
            )
        ]
    return []
