# Known-Findings Contract

**Status:** **PROPOSED** — not wired into any test runner, and this PR does not change Mobile
**Record:** `testing/known_findings.json`
**Validator:** `python3 tools/validate_known_findings.py`

---

## 1. The problem this solves

The 239-case run has one failure, CB_211, which is adjudicated at engineering
level but awaiting a lead and clinical decision. Two bad options present
themselves:

- **Leave the run red.** A permanently failing suite trains reviewers to skim
  past failures. The next real regression arrives into a suite nobody trusts.
- **Skip or waive the case.** This converts an unresolved question into a silent
  pass and loses the finding entirely.

This contract takes neither. A known finding is a **pinned observation**, not a
suppressed failure: the case still runs, its exact observed output is asserted,
and *any* deviation — better or worse — fails the run.

## 2. Existing repository mechanism

There was no case-level mechanism before this proposal. There is a direct
precedent one level up: `KNOWN_BASELINE_FINDINGS` in `tools/report_baseline.py`,
which records the three pre-existing unresolved IMCI severity tier keys and
fails the check on any *new* unresolved reference. Same shape — record the known
reality, fail on anything that is not it. This proposal follows it deliberately
rather than inventing a second idiom.

## 3. Fail-closed semantics

A conforming runner **must**:

1. Execute every registered case exactly as authored. Never skip, never filter.
2. Compare observed output against `observed_output` **field by field**.
3. **Fail** if any observed field differs from the registry.
4. **Fail** if any case *not* in the registry mismatches its expectation.
5. **Fail** if the fixture hash differs from `authoritative_fixture.sha256`.
6. Report every entry prominently with its `decision_status`.

And **must not**:

1. Report a registered case as `passed`.
2. Count it toward the pass total.
3. Downgrade a failure to a warning.
4. Treat an empty or unreadable registry as permission to ignore a failure.

### The asymmetry that matters

The registry asserts the mismatch **exactly**. If CB_211 started returning
`non_urgent` — the value the case bank originally expected — the run would
**fail**, because the registry's description of reality would have become wrong.
That is intentional. An unexplained improvement is as much a signal as a
regression, and someone must look at it before the registry is updated.

### Reporting shape

```
239 executed · 238 passed · 1 known finding · 0 unexpected failures

KNOWN FINDING  CB_211  [open_awaiting_engineering_lead_and_clinical]
  expected  non_urgent / empty_default
  observed  urgent / urgency_default / malaria   (matches registry — pinned)
  owner     engineering lead + clinical reviewer
  evidence  docs/CB_211_DECISION_PACKAGE.md
  expires   external_beta
```

The known-finding count is **never** folded into the pass count.

## 4. Wiring it (NOT done here)

Wiring is a separate, separately reviewed **Mobile** change. It is out of scope
for this PR, which changes no Mobile file. When it happens, the runner in
`test/engine/case_bank_validation_test.dart` would:

1. Load `known_findings.json` alongside the case bank.
2. Verify `authoritative_fixture.sha256` matches the loaded fixture; abort if not.
3. Run all 239 cases unchanged.
4. Partition results into `passed` / `known findings` / `unexpected failures`.
5. Exit non-zero if `unexpected failures > 0`, **or** if any registered case
   deviates from its pinned `observed_output`.

Until then, the run reports CB_211 as a failure, which is correct and honest.

## 5. Record fields

| Field | Purpose |
|---|---|
| `case_id` | The case, as it appears in the bank |
| `fixture_version` / `fixture_sha256` | The registry entry is valid only against this exact fixture |
| `classification` | Engineering classification — see the decision package |
| `classification_authority` | `engineering` — never `clinical` unless a clinician signed it |
| `classification_is_clinical_approval` | Always `false` unless clinical approval genuinely exists |
| `input` | The exact input, so the entry is self-contained |
| `expected_output` | What the bank asserts, and where that assertion came from |
| `observed_output` | What the engine does, pinned. Deviation fails the run. |
| `safety_impact` | Direction, criticality, red-flag and blast-radius analysis |
| `product_reachability` | Guards, guard tests, and what pins the behaviour |
| `decision_status` | Open / resolved, and who it is waiting on |
| `owner` | Per question — different questions have different owners |
| `resolution_options` | The options on the table, from the decision package |
| `evidence_references` | Files, commits, issues, line numbers |
| `review_trigger` | Expiry milestone plus the conditions that force re-review |

## 6. Expiry

Every entry carries a `review_trigger`. CB_211's `expires_at_milestone` is
`external_beta` — consistent with Mobile's own `PROGRESS.md`, which lists this
item as due *"before external beta"* with owner *"Eng lead / clinical"*.

An entry is **not** a permanent exemption. Reaching the milestone with the entry
unresolved is itself the failure condition.

## 7. What this proposal does not do

- It does not decide CB_211. See `docs/CB_211_DECISION_PACKAGE.md` §8.
- It does not make any failing case pass.
- It does not change the case bank, the engine, or any expected output.
- It does not claim clinical approval for anything.
- It is not wired into Mobile, and this PR touches no Mobile file.
