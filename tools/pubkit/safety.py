"""Instrumented refusal of network, subprocess and out-of-staging writes.

The dry-run path is supposed to be incapable of uploading. "Supposed to be" is not a property
a reader can check, so this module makes it one: `no_side_effects()` monkeypatches the socket
layer, the subprocess launcher and `open()` for the duration of a block, and records any
attempt instead of allowing it.

Two distinct uses, and the difference matters:

  * **In tests**, it is the assertion. A test wraps a dry-run in `no_side_effects()` and fails
    if anything was attempted, which is how "the dry run does not touch the network" stops
    being a claim about intent and becomes a claim about behaviour.
  * **In the tools themselves**, it is defence in depth around plan generation. It is not the
    reason the tooling cannot upload — the reason is that no upload code exists anywhere in
    this package — but a future edit that added some would trip this immediately.

It is not a sandbox and does not pretend to be one. Code that reaches past Python (a C
extension, an `os.system` via a path not patched here) is out of its reach. It is an
instrument for proving the tooling as written does not do these things.
"""

import builtins
import os
import socket
import subprocess

from .reasons import reason

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Modules whose mere import signals an intent to reach a cloud API. Checked rather than
#: blocked: this tooling never imports them, and a test asserts the module list stays empty.
CLOUD_SDK_MODULES = ("boto3", "botocore", "google.cloud", "azure", "s3transfer", "aiobotocore")


class SideEffectAttempted(Exception):
    """Raised the moment a guarded operation is attempted."""


class _Recorder:
    def __init__(self, allowed_write_roots, raise_on_attempt):
        self.attempts = []
        self.allowed_write_roots = [os.path.realpath(root) for root in allowed_write_roots]
        self.raise_on_attempt = raise_on_attempt

    def record(self, code, path, detail):
        item = reason(code, path, detail)
        self.attempts.append(item)
        if self.raise_on_attempt:
            raise SideEffectAttempted("%s at %s: %s" % (code, path, detail))
        return item

    def write_allowed(self, path):
        resolved = os.path.realpath(path)
        for root in self.allowed_write_roots:
            if resolved == root or resolved.startswith(root + os.sep):
                return True
        return False


class no_side_effects:
    """Context manager recording (and by default refusing) network, subprocess and stray writes.

    `allowed_write_roots` defaults to nothing at all: a dry run that writes no file anywhere is
    the baseline, and a caller that legitimately stages bytes passes its staging directory in
    explicitly. Reads are never restricted — this tooling has to read artifacts to hash them.
    """

    def __init__(self, allowed_write_roots=(), raise_on_attempt=True):
        self.recorder = _Recorder(allowed_write_roots, raise_on_attempt)
        self._saved = {}

    def __enter__(self):
        recorder = self.recorder

        self._saved["socket"] = socket.socket
        self._saved["create_connection"] = socket.create_connection
        self._saved["getaddrinfo"] = socket.getaddrinfo
        self._saved["Popen"] = subprocess.Popen
        self._saved["open"] = builtins.open

        def blocked_socket(*args, **kwargs):
            recorder.record("KB_NETWORK_ATTEMPTED", "socket.socket", "the dry-run path opened a socket")
            raise SideEffectAttempted("socket creation is refused in the dry-run path")

        def blocked_connection(address, *args, **kwargs):
            recorder.record(
                "KB_NETWORK_ATTEMPTED", "socket.create_connection", "attempted connection to %r" % (address,)
            )
            raise SideEffectAttempted("outbound connections are refused in the dry-run path")

        def blocked_getaddrinfo(host, *args, **kwargs):
            recorder.record("KB_NETWORK_ATTEMPTED", "socket.getaddrinfo", "attempted DNS lookup of %r" % (host,))
            raise SideEffectAttempted("DNS resolution is refused in the dry-run path")

        def blocked_popen(args, *rest, **kwargs):
            recorder.record(
                "KB_SUBPROCESS_ATTEMPTED",
                "subprocess.Popen",
                "attempted to launch %r; a subprocess is how an upload would hide" % (args,),
            )
            raise SideEffectAttempted("subprocess launch is refused in the dry-run path")

        def guarded_open(file, mode="r", *rest, **kwargs):
            writing = any(flag in mode for flag in ("w", "a", "x", "+"))
            if writing and not recorder.write_allowed(file):
                recorder.record(
                    "KB_STAGING_ESCAPE",
                    str(file),
                    "attempted to open %r for writing outside every permitted directory" % (file,),
                )
                raise SideEffectAttempted("write outside the staging area is refused")
            return self._saved["open"](file, mode, *rest, **kwargs)

        socket.socket = blocked_socket
        socket.create_connection = blocked_connection
        socket.getaddrinfo = blocked_getaddrinfo
        subprocess.Popen = blocked_popen
        builtins.open = guarded_open
        return recorder

    def __exit__(self, exc_type, exc_value, traceback):
        socket.socket = self._saved["socket"]
        socket.create_connection = self._saved["create_connection"]
        socket.getaddrinfo = self._saved["getaddrinfo"]
        subprocess.Popen = self._saved["Popen"]
        builtins.open = self._saved["open"]
        return False


def imported_cloud_sdks():
    """Cloud SDK modules currently imported. Should always be empty in this repository."""
    import sys

    return sorted(name for name in CLOUD_SDK_MODULES if name in sys.modules)
