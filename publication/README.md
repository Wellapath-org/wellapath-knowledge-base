# `publication/` — dry-run publication artifacts

> **Nothing in this directory is published, uploaded, active, approved or eligible.**
> Everything here is generated, reproducible from its generator, and explicitly non-operative.

Full documentation: [`../docs/PUBLICATION_LIFECYCLE.md`](../docs/PUBLICATION_LIFECYCLE.md).
Backend-facing note: [`../backend_handoff/publication_tooling_v1/README.md`](../backend_handoff/publication_tooling_v1/README.md).

```bash
python3 tools/run_publication_checks.py     # everything; this is what CI runs
```

## Contents

| Path | What it is |
|---|---|
| `governance/decision_register_v1.json` | Every decision record this repository holds, transcribed and bound to its source by path and sha256. **Derived, never authored** — a generator that reads existing records cannot invent an approval nobody gave. |
| `plans/token_dictionary.ng.v2.0.dryrun.json` | Dry-run plan for Vocabulary 2.0. Not publishable, not activatable, ineligible everywhere. |
| `plans/question_flow.ng.v1.1.dryrun.json` | Dry-run plan for Question Flow 1.1. Same, plus two open blockers. |
| `fixtures/compat/kb_baseline.manifest.json` | A valid manifest for the negative cases to break. `artifact_id` is `fixture_artifact` — unmistakably synthetic — with real repository digests so integrity cases run against bytes that exist. |
| `fixtures/compat/kb_blocked_candidates.manifest.json` | The real candidates, real hashes, true governance. Descriptors extracted verbatim from the plans so the two cannot disagree. |
| `fixtures/compat/negative_fixtures.compat.json` | 41 contract-level cases **in the Backend's own fixture format**, executable unchanged by `tests/unit/manifest-fixtures.test.ts`. |
| `fixtures/compat/approval_scope_reconciliation_v1.json` | The I3 Step 2A approval-scope ruling, with every claim **computed** by running the contract's own eligibility semantics over both encodings — not asserted in prose. Records the Backend fixture's `granted` product as a defect, with the controlled probe that demonstrates it. |
| `fixtures/negative/kb_stage_fixtures_v1.json` | 60 cases for the stages the Backend has no opinion on: pinning, generation, keys, governance, lifecycle, rollback, write safety. |
| `receipts/*.example.json` | Shape definitions for four future operations. Every one is `operative: false`, every `*_performed` is false, every decision is `refused`. |

## Reading a plan

Start at `conclusion`, then `blocking_reasons`. Every refusal carries a machine-readable code
and a location.

```
operations_performed.*          what this tooling did — all false
eligible_for_environment        false, and false in all three environments
lifecycle.states                nine independent states; the five external ones are always false
descriptor                      a contract 1.0.0 descriptor, validated by two routes that agree
governance.claims               five claims, all refused, each with reasons
rollback                        the proposed target and every reason it is refused
blocking_reasons                everything stopping publication
```

## Rules

- **Never hand-edit anything here.** Every file is generated; `--check` on its generator fails
  if it was touched. Change the generator and rebuild.
- **Never move a candidate to the repository root.** The root is the directory published
  artifacts are uploaded from.
- **Never add a descriptor from these fixtures or plans to a live manifest.** They name no
  uploaded object.
- **Never set an approval, authorization or activation field by tooling.** Only an authoritative
  decision record can populate one, and the register is derived from records that already exist.
