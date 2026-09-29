"""Knowledge Base publication tooling (I3 / Step 2).

Deterministic, offline, fail-closed tooling that *prepares* governed artifacts and
Backend-contract-compatible descriptors. It inventories, validates, hashes, packages into a
disposable staging directory and emits dry-run publication plans.

It does not upload, publish, activate, deploy, write to R2 or change any artifact byte, and
there is no code path here that could. Every plan it emits carries

    upload_performed: false
    publication_performed: false
    activation_performed: false
    eligible_for_environment: false

as facts about what this tooling did, not as placeholders awaiting a later value.

Standard library only, matching every other generator in this repository
(`tools/vocab/`, `testing/build_case_bank.py`, `facilities/source/build_e5.py`): no
dependency manifest, no `pip install`, no network, so the artifacts and the plans are
reproducible on any machine with a stock Python 3.9+.

The Backend manifest contract is *vendored and pinned*, never reimplemented from memory:
`contracts/backend/manifest.v1.schema.json` is a byte-for-byte copy and
`contracts/backend/PIN.json` records where it came from. `contract.py`, `manifest.py`,
`eligibility.py`, `integrity.py` and `origin.py` are deliberate ports of the Backend's own
modules at the pinned commit, so a descriptor this repository accepts is one the Backend
accepts. Where the two could disagree, the shared fixtures under
`publication/fixtures/compat/` are the arbiter — both implementations evaluate them and must
agree case for case.
"""

__all__ = [
    "contract",
    "eligibility",
    "governance",
    "integrity",
    "inventory",
    "keys",
    "lifecycle",
    "manifest",
    "origin",
    "pin",
    "plan",
    "reasons",
    "safety",
    "staging",
]

#: Version of this tooling. Recorded in every plan so a plan names the code that built it.
PUBKIT_VERSION = "1.0.0"
