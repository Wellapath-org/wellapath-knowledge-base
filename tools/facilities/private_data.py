"""Resolve pipeline artifacts that this public repository may not distribute.

Five files are withheld from public distribution:

* ``facilities/source/nigeria_health_facilities.csv`` — the NHFR source export
* ``candidate/facilities.ng.v2.0.json`` — 29,028 facility-level records
* ``reports/facilities_coordinate_audit_v1.json`` — 11,141 per-record corrections
* ``reports/facilities_quarantine_v1.json`` — 2,362 per-record rejections
* ``reports/facilities_comparison_v1.json`` — per-record match samples

The reason is licensing, not privacy. NHFR publishes no licence and no terms of
use, and its only public rights statement reserves all rights, so permission to
redistribute has not been established. See
``docs/FACILITIES_SOURCE_AUTHORIZATION_CHECKLIST.md``.

All five are reproducible from a private copy of the source. Point
``WELLAPATH_PRIVATE_DATA`` at the directory holding it and they resolve
normally; leave it unset and the callers skip rather than fail.
"""

import os

WITHHELD = (
    ("facilities", "source", "nigeria_health_facilities.csv"),
    ("candidate", "facilities.ng.v2.0.json"),
    ("reports", "facilities_coordinate_audit_v1.json"),
    ("reports", "facilities_quarantine_v1.json"),
    ("reports", "facilities_comparison_v1.json"),
)

ENV_VAR = "WELLAPATH_PRIVATE_DATA"

REASON = (
    "Withheld from the public repository pending NHFR redistribution terms. "
    "Set {} to a directory holding a private copy to run this.".format(ENV_VAR)
)


def private_root():
    """The configured private-data directory, or None when unset or missing."""
    root = os.environ.get(ENV_VAR)
    if not root:
        return None
    root = os.path.expanduser(root)
    return root if os.path.isdir(root) else None


def resolve(*parts):
    """Absolute path to a withheld artifact, or None when unavailable.

    Looks under ``$WELLAPATH_PRIVATE_DATA`` both at the repository-relative
    path and flattened to the basename, so either layout works.
    """
    root = private_root()
    if root is None:
        return None
    for candidate in (os.path.join(root, *parts), os.path.join(root, parts[-1])):
        if os.path.exists(candidate):
            return candidate
    return None


def available():
    """True when every withheld artifact resolves."""
    return all(resolve(*parts) is not None for parts in WITHHELD)


def missing():
    """The withheld artifacts that do not resolve, as repo-relative paths."""
    return ["/".join(p) for p in WITHHELD if resolve(*p) is None]
