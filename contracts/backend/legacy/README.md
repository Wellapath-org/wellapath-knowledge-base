# Legacy contract material — NOT the active contract

Everything in this directory is **superseded test material**, kept only so backward
compatibility can be tested against the contract version it was actually written for. None of
it is the contract this repository validates against.

The active contract is `contracts/backend/manifest.v1.schema.json` (version **1.1.0**, pinned by
`contracts/backend/PIN.json`). Tooling reads the active contract through
`tools/pubkit/pin.py`; nothing here is on that path.

| File | What it is |
|---|---|
| `manifest.v1.0.0.schema.json` | The Backend manifest schema at contract **1.0.0**, vendored byte-for-byte from `wellapath-backend@fc40ac3e7d59cfed8e2584b78136c9704f7ab8cd`. Superseded by 1.1.0 on 2026-08-28. |

## Why it is kept

Contract 1.1.0 added the optional approval field `decision_scope` and tightened one previously
unsafe claim: a `granted` approval that declares no `artifact_publication` scope no longer
counts. That is a minor bump rather than a major one because descriptors making no
granted-approval claim stay valid — but "stay valid" is a property worth *testing*, not
assuming, and testing it needs the 1.0.0 schema to hand.

`testing/publication/test_publication.py` uses this file to prove:

- a safe legacy 1.0.0 descriptor is still consumable under 1.1.0;
- a legacy descriptor claiming `granted` without publication scope is now rejected — this is
  the tightening, and it is the one behaviour change;
- a non-granted legacy approval still needs no `decision_scope`;
- a strict 1.0.0 consumer rejects the new field, which is precisely why the version moved.

That last point is the honest reason for the bump. Under 1.0.0 the approval record is
`additionalProperties: false`, so a 1.1.0 descriptor carrying `decision_scope` is *invalid*
against 1.0.0. The change is additive going forward and breaking going backward, which is what
a minor version is for.

## Rules

- Never validate a real descriptor against anything in this directory.
- Never update these bytes. A legacy artifact that drifts is not a legacy artifact.
- Add a file here only when a new contract version supersedes one that tests still need.
