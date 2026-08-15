# CB_211 — Decision Package

**Phase:** I2 / W2 Step 3 · **Owner of this document:** Knowledge Base / Data Engineering
**Status:** provisional **engineering** classification — **no clinical ruling made or implied**
**Blocks:** Mobile PR #71 remains unmerged until a disposition is recorded

Machine-readable evidence: `reports/case_findings_v1.json`
Reproduce: `python3 tools/report_case_findings.py`

---

## 1. The case, exactly as authored

```json
{
  "case_id": "CB_211",
  "condition_target": null,
  "description": "Edge: empty input — engine must not crash, returns safe default",
  "input_tokens": [],
  "demographic_tokens": [],
  "season": null,
  "expected_urgency": "non_urgent",
  "expected_top_condition": null,
  "safety_critical": false,
  "expected_urgency_source": "empty_default",
  "note": "matches E3.5 Case 12 behaviour"
}
```

## 2. Expected versus actual

| | Expected | Actual (Mobile PR #71 @ `04dcf75`) | Reproduced here |
|---|---|---|---|
| urgency | `non_urgent` | **`urgent`** | ✅ `urgent` |
| urgency source | `empty_default` | **`urgency_default`** | ✅ `urgency_default` |
| top condition | `null` | **`malaria`** | ✅ `malaria` |
| direction | — | **over-triage** | — |
| safety critical | `false` | no under-triage | — |

Mechanism, computed from `kb.ng.v2.4.json`: with no symptoms, every condition
scores `base_weight + 0`. Malaria has the highest base weight in the KB (10);
the runner-up group scores 8. Margin **2**, **no tie**. Malaria's
`urgency_default` is `urgent`, and `UrgencyDeterminer` falls through to
priority 5, emitting `urgency_default`.

---

## 3. Provenance

### 3.1 Where the expectation came from

`testing/build_case_bank.py:174-177` — hardcoded, not derived from the
spec-priority ladder that generates the rest of the bank:

```python
# Empty input
add(None, "Edge: empty input — engine must not crash, returns safe default",
    [], [], None, "non_urgent", None, safety=False,
    exp_source="empty_default", note="matches E3.5 Case 12 behaviour")
```

Introduced in `ba7815e` (PR #13, E8.1 case bank). **Never modified since** —
`7ea1724` (PR #15), `0d3a159` (PR #18) and `c974100` (PR #19) all left CB_211
untouched.

### 3.2 The cited source, read directly

The note cites *E3.5 Case 12*. That is not a lost document — it is a live test:

**`wellapath-mobile/test/engine/pilot_case_validation_test.dart:422-439`**,
added in `b34cfb8` *"test(engine): add 12 pilot case validation tests — E3.5"*
(2026-05-18):

```dart
// CASE 12 — Empty input must not crash
test(
  'case_12 — empty input: must not crash, any valid urgency returned',
  () {
    final output = _buildController().run(
      const EngineInput(symptomTokens: [], candidateConditionIds: []),
    );
    expect(
      ['emergency', 'urgent', 'non_urgent', 'self_care'].contains(output.urgency),
      isTrue,
    );
  },
);
```

**This is the decisive finding.** E3.5 Case 12 asserts two things: the engine
must not crash, and the urgency must be **any one of the four valid values** —
`urgent` explicitly among them. It contains **zero** occurrences of
`empty_default`, and `non_urgent` appears only as one member of the permitted
set, never as a required value.

So the case bank's note is factually wrong. CB_211 does **not** "match E3.5
Case 12 behaviour": it narrows a deliberately permissive assertion to a single
value, and adds an `expected_urgency_source` its cited source never mentions.

### 3.3 Prior-run history — verified, not reported

The same mismatch appears in the committed results of the previous 234-case
run, `testing/case_bank_results_v1.json` (merged via PR #15), recorded in three
places — `as_shipped.results[210]`, `as_shipped.failures[0]` and
`as_shipped.urgency_source_mismatches[0]`:

```json
{ "case_id": "CB_211", "expected_urgency": "non_urgent",
  "expected_urgency_source": "empty_default", "actual_urgency": "urgent",
  "actual_urgency_source": "urgency_default", "actual_top_condition": "malaria",
  "pass": false, "triage_direction": "over_triage",
  "safety_critical": false, "safety_critical_failure": false }
```

That run used **kb 2.3 / rules 2.2**; the current run uses **kb 2.4 / rules 2.2**.
The record is identical in every field. **Nothing regressed** — confirmed
independently by recomputing CB_211 against both KB versions
(`kb_version_delta.changed_between_2_3_and_2_4: false`).

### 3.4 Tracking

**wellapath-mobile issue #35** — OPEN, label `bug`, opened 2026-07-26:
*"fix(engine): empty symptom input produces a fabricated result if it reaches
the engine"*. Its own words: *"E3.5 Case 12 asserted only that empty input 'must
not crash'. It does not crash — it invents."* It closes with an explicit
**open question for the lead**: should the engine itself refuse empty input
rather than relying on every caller to guard?

---

## 4. Governing contract for empty input and urgency-source values

### 4.1 Urgency-source values

The authoritative enumeration is the doc comment on `EngineOutput.urgencySource`
(`wellapath-mobile/lib/core/engine/models/engine_output.dart`):

> Why `urgency` came out the way it did: one of `global_red_flag`,
> `condition_specific_red_flag`, `demographic_escalation` or `urgency_default`.

**Four values. `empty_default` is not one of them.** Verified exhaustively:

| Check | Result |
|---|---|
| `urgencySource` literals in current `urgency_determiner.dart` | `global_red_flag`, `condition_specific_red_flag`, `demographic_escalation`, `urgency_default` |
| Same, across **all 5 historical revisions** (`e20f45a`, `51afd89`, `7aeb13c`, `cfe1a25`, `33a214e`) | identical set — no revision ever emitted anything else |
| `empty_default` in any commit under `lib/` | **none** |
| `empty_default` as a sealed type / enum member | none — `urgencySource` is a plain `String`; there is no sealed type to violate |
| `empty_default` anywhere in Mobile | only in `PROGRESS.md`, `docs/CASE_BANK_PROVENANCE.md` and the copied fixture — all documentation *about* this finding |

So `empty_default` is not a stale value that was removed. It **never existed**.

### 4.2 Empty input

There is no engine-level contract requiring any particular result for empty
input. The only governing artifact is E3.5 Case 12, which requires non-crash and
permits any of the four urgency values. The engine satisfies it.

The engine's actual empty-input behaviour is not accidental — it is
**deliberately pinned** by `test/engine/engine_wiring_test.dart:218-229`:

```dart
group('empty input', () {
  test('still fabricates a result if it ever reaches the engine', () {
    final EngineOutput output = run(input(symptoms: const <String>[]));
    expect(output.topCauses, isNotEmpty);
    expect(output.topCauses.first['condition_id'], 'malaria');
    expect(output.urgency, 'urgent');
  });
});
```

---

## 5. Reachability

| Path | Reachable? | Evidence |
|---|---|---|
| **Normal UI** | **No** | Guard 1: `symptom_selection_screen.dart:83` `final isEnabled = tokens.isNotEmpty;` → `:250` `onPressed: isEnabled ? … : null`. Continue is disabled with nothing selected. |
| **Last step before engine** | **No** | Guard 2: `loading_screen.dart:71` `if (widget.assessmentController.symptomTokens.isEmpty)` blocks before any work, records `CompletionStatus.interrupted`, shows *"Please select at least one symptom to continue."* Its own comment calls it *"defence in depth on the last step before the engine, not the only gate."* |
| Guard test coverage | — | `test/assessment/empty_input_guard_test.dart` (3,747 B) on `develop` |
| **Direct engine invocation** | **Yes** | `EngineController.run()` with an empty token list. This is exactly what CB_211 and `engine_wiring_test.dart` do. |
| Offline | No | Same two guards; they are client-side and do not depend on network. |
| Deep link / state restoration / corrupted state | **Not proven either way** | Both guards key on `assessmentController.symptomTokens`. Any future entry point that reaches `loading_screen` with a restored-but-empty controller is caught by Guard 2. A path that bypasses `loading_screen` entirely and calls the engine directly would not be. No such path exists today; this is the residual risk issue #35 names. |

### Which of the four categories this is

- ❌ *reachable product behaviour* — double-guarded, both guards tested
- ❌ *invalid fixture structure* — the record is well-formed and schema-valid
- ✅ **unreachable synthetic engine test** — that is precisely what it is
- ⚠️ *actual missing engine requirement* — **partly.** Whether a CDSS should
  fabricate a differential from no input is a real open question. But it is a
  *new* requirement, not one any contract already imposed.

---

## 6. Provisional engineering classification

> ### `obsolete/stale case-bank expectation`
>
> **This is an engineering classification based on artifact evidence. It is not
> a clinical ruling, not clinical approval, and not a release approval.**

Reasoning, in the order the evidence forces:

1. The engine **conforms** to its governing specification. E3.5 Case 12 permits
   `urgent`. So the classification *"valid expectation; engine non-conforming"*
   is **excluded by primary evidence**.
2. The fixture is structurally valid, so *"invalid fixture structure"* is excluded.
3. The expected behaviour is **not** unresolved at the engineering level —
   E3.5 Case 12 resolved it permissively — so *"valid synthetic robustness case
   with unresolved expected behaviour"* is excluded. (The *clinical* question is
   still open; that is §7, not a classification of the fixture.)
4. What remains: the expectation is not grounded in any contract that has ever
   existed. It over-constrains its own cited source and names an
   `expected_urgency_source` value no engine version ever emitted.

### One refinement worth recording

Mobile's `docs/CASE_BANK_PROVENANCE.md` reaches the same classification. This
package agrees, and grounds it in the **primary artifact** (the E3.5 Case 12
test body) rather than a characterisation of it.

The refinement: "stale" normally implies *once correct, later superseded*. That
is not what happened. `empty_default` was never implemented at any point, and
`non_urgent` was never required. This is an **authoring-time over-constraint**,
not drift. It matters for the remedy: there is no earlier engine contract to
restore, so option B is a straightforward correction rather than a rollback.

---

## 7. Safety and release impact

| Question | Answer |
|---|---|
| Reachable through the current UI? | **No** — two independent tested guards |
| Reachable offline / deep link / state restoration / corrupted state? | Not through any path that reaches `loading_screen`. Direct engine invocation reaches it; no product path does today. |
| Over-triage or under-triage? | **Over-triage** — `urgent` where the bank expected `non_urgent`. The conservative direction. |
| Can it suppress or bypass a red flag? | **No.** Red-flag evaluation runs before scoring and is unaffected by an empty token set — with no tokens, no rule can match, so there is no flag to suppress. All 13 global rules fired correctly in the run (124/124 red-flag cases returned emergency). |
| Can it change a non-empty assessment result? | **No.** The behaviour is entirely a consequence of the symptom set being empty. Every non-empty case is scored identically with or without this finding. |
| Does it affect any other case? | **No.** 235/239 passed; the other three deltas are the pre-declared `observe` cases. |

### Release gating — engineering view

| Gate | Blocked? | Why |
|---|---|---|
| Merging fixture/provenance infrastructure (Mobile PR #71) | **No** | The finding is carried forward, unchanged, non-safety-critical and documented. Blocking the harness would leave the repository with no executable regression at all — strictly worse. |
| Beginning Vocabulary 2.0 search work | **No** | Unrelated. W2 changes no scoring input and adds no reachable behaviour. |
| Internal testing | **No** | Unreachable in product; over-triage direction. |
| **External beta** | **Not approved by this document** | Mobile's own PROGRESS.md lists this as due *"before external beta"* with owner *"Eng lead / clinical"*. This package does not clear that gate and does not attempt to. |
| **Production** | **Not approved by this document** | Same. |

---

## 8. Resolution options

Each is supported by the evidence above. **None is implemented in this step.**

### Option A — Preserve CB_211 unchanged; treat the mismatch as unresolved
Change nothing. The run continues to report 238/239 with one documented failure.
*For:* zero risk; preserves the signal.
*Against:* a permanently red run trains reviewers to ignore failures.

### Option B — Correct the case-bank expectation, via a reviewed data-artifact revision
Publish a new case-bank version whose CB_211 expectation matches its own cited
source: accept any valid urgency, and drop `expected_urgency_source: empty_default`
(or set it to `urgency_default`).
*For:* removes an expectation no contract supports; makes the bank green and
honest. *Against:* removes the standing prompt for the clinical question in §7.
**Constraint:** requires a new versioned case-bank artifact with its own hash and
provenance. `testing/case_bank_v1.json` is immutable and **must not be edited**.

### Option C — Introduce an engine-level empty-input result, via a reviewed Mobile change
Make the engine refuse empty input — throw, or return a dedicated
"insufficient input" output with a new `empty_default` (or similarly named)
source. This is exactly issue #35's open question to the lead.
*For:* fixes the underlying concern — a CDSS should not fabricate a differential
from nothing — and makes the guards defence-in-depth rather than the only gate.
*Against:* an engine **contract change**; adds a fifth `urgencySource` value;
needs its own clinical review and regression.

### Option D — Retain unchanged, plus an explicit known-discrepancy registry
Keep CB_211 exactly as authored, and record it in a machine-readable registry
that keeps executing the case, asserts the *exact* known mismatch, and fails if
anything changes. See `docs/KNOWN_FINDINGS_CONTRACT.md` and
`testing/known_findings.json` (proposed in this PR, **not wired into Mobile**).
*For:* keeps the finding visible and fail-closed while adjudication proceeds;
does not pretend the failure is a pass.
*Against:* a holding position, not a resolution — needs an expiry.

**Options B, C and D are not mutually exclusive.** D is the natural interim
while B or C is decided.

---

## 9. Recommended decision owner

| Question | Owner |
|---|---|
| Should the engine refuse empty input / emit a dedicated source? (Option C) | **Engineering lead**, with clinical input — it is an engine contract change |
| Is `urgent` + a fabricated malaria differential acceptable for empty input? | **Clinical reviewer** — the only genuinely clinical question here |
| Correcting the case-bank expectation (Option B) | **Engineering lead** approves; Knowledge Base / Data Engineering implements as a new versioned artifact |
| Interim registry (Option D) | **Engineering lead** — a process decision |

**Recommended sequence:** adopt **D** now so Mobile PR #71 can merge with the
finding visible and fail-closed, then have the lead and clinical reviewer decide
between **B** and **C** before external beta.

---

## 10. Statement on clinical rulings

No clinical ruling was invented, inferred or implied in this document.

- The classification in §6 is an **engineering** classification derived from
  artifact evidence: source code, tests, commits, committed run results and an
  open issue. Every claim above cites a file, a commit or a line number.
- Whether an empty assessment should yield `urgent`, `non_urgent`, or a refusal
  is a **clinical** question. It is recorded as open. It is not answered here.
- No clinical reviewer has approved CB_211, its expected value, or the engine's
  empty-input behaviour. No such approval is claimed.
- This document approves nothing for external beta or production.
