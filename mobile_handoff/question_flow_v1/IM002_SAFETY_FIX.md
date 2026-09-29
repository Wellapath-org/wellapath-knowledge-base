# Mobile W3 Task 1 — IM-002 Safety Correction (and nothing else)

**From:** Knowledge Base / Data Engineering · **Phase:** I2 / W3 Step 1A
**Disposition:** IM-002 **adopted as a required safety correction** (engineering lead)
**Scope:** this fix **only**. Not the adaptive engine.

Evidence: `reports/qb002_evidence_v1.json` · Contract: `docs/W3_QUESTION_FLOW_CONTRACT.md`

---

## 1. What is wrong

A red-flag clarifier answered **"Yes"** does not interrupt the assessment. The
answer sits in widget state until the **last** follow-up question is answered.

**Measured worst case: 4 further ordinary questions** are presented after the
user declares a danger sign. Example, from the evidence report:

```
Q-clarifier-breathlessness_at_rest        <- user answers "Yes"
Q-followup-abdominal_cramps-severity      <- still asked
Q-followup-body_pain-severity             <- still asked
Q-followup-abdominal_cramps-duration      <- still asked
Q-followup-body_pain-duration             <- still asked
                                          -> only now does the engine see it
```

### What is NOT wrong

**The final result is correct.** `RedFlagEvaluator` runs before
`ScoringEngine`; a matched global rule returns `proceedToScoring: false`;
`ScoringEngine.score` **throws** if called with that false; `UrgencyDeterminer`
checks `redFlagTriggered` at priority 1. The 239-case bank confirms it: 124/124
red-flag cases returned emergency, **0 safety-critical under-triage**.

So this is **not an under-triage defect**. The harm is that someone who has just
declared a danger sign is asked four more routine questions before being told to
seek emergency care — and may abandon the assessment first, receiving nothing.

---

## 2. Affected files and symbols

| File | Symbol | Line | Role |
|---|---|---|---|
| `lib/features/assessment/followup_screen.dart` | `_answers` | 30 | `Map<int, dynamic>` — answers held locally |
| `lib/features/assessment/followup_screen.dart` | `_onNext` | 69–80 | **the fix site** |
| `lib/features/assessment/followup_screen.dart` | `_commitAnswers` | 90 | only reached on the last question |
| `lib/core/engine/red_flag_evaluator.dart` | `RedFlagEvaluator.evaluate` | — | correct already — **do not change** |
| `lib/features/assessment/assessment_controller.dart` | `addSymptomToken` | — | where the token must land |

---

## 3. Earliest safe interception point

> `_onNext`, inside the `if (_currentQuestion < _questions.length - 1)` branch,
> **before** `setState` advances the index.

Why here:

- it is the first moment the app knows the current answer is final;
- the widget already owns both the answer map and navigation — no new plumbing;
- it is **before** `recordStepView()`, so an interrupted path emits no extra
  step event (see §8).

**Not** `_commitAnswers` — that is only reached on the last question, so fixing
it there removes no delay. **Not** the engine — the engine is already right.

---

## 4. Required order of operations

For **every** answer, not only clarifiers:

```
1. Commit THIS question's answer to AssessmentController.
2. If the question can affect a red flag  ->  evaluate red flags NOW.
3. If a red flag fired  ->  stop. Navigate to emergency presentation.
                            Do NOT advance. Do NOT present a queued question.
4. Otherwise            ->  recordStepView(); advance to the next question.
```

**State must be committed before evaluation.** Evaluating against state that
does not yet include the answer is the bug in a new place.

Which questions require evaluation: those whose
`red_flag_evaluation.can_affect_red_flag` is true — the 3 clarifiers, plus the
symptom picker. Read it from the contract; do not hardcode a list.

### Also required

| Trigger | Requirement |
|---|---|
| After an **edited** answer | Re-evaluate before presenting the next question |
| After **restored** state | Evaluate before presenting anything |
| Before **scoring** | Already true — keep it |
| Before **results rendering** | Already true — keep it |

---

## 5. Cancellation and races

- Evaluation is **synchronous and local**. No network, no async gap where a
  further tap could slip through.
- Guard against double-advance: disable the Next control while evaluation runs.
  A double-tap must not produce two advances or skip the interrupt.
- If the user cancels **during** an interrupt, treat it as abandonment —
  `CompletionStatus.interrupted`, no result. Do not fall through to the next
  question.
- If a red flag fires, the queued questions are **discarded**, not deferred.
  Do not show them after the emergency screen.

---

## 6. Offline and restoration

- Everything here is on-device. **No network call may be added.** The fix must
  work with the device in airplane mode.
- Restoration: rebuild the token set from persisted answers, then evaluate
  **before** presenting a question. A restored assessment that already contains
  a red-flag token must land on the emergency presentation, not mid-flow.
- Answers must be keyed by **stable question ID**, not list index (IM-004), or
  restoration cannot reattribute them safely. This is a prerequisite.

---

## 7. Regression cases

Every one must be added.

| # | Case | Expected |
|---|---|---|
| 1 | Clarifier answered Yes with 4 questions queued | Interrupt immediately; **0** further ordinary questions presented |
| 2 | Clarifier answered Yes as the last question | Same behaviour as today |
| 3 | Clarifier answered **No** | Flow continues normally; no red flag |
| 4 | Ordinary path, no clarifier raised | **Identical** question sequence to today |
| 5 | Clarifier raised but red flag already selected | Clarifier suppressed (unchanged) |
| 6 | Red flag fires → scoring | `ScoringEngine.score` is never called |
| 7 | Edit an earlier answer that removes the trigger | Red flag re-evaluated; clarifier retired |
| 8 | Restore state containing a red-flag token | Emergency presentation, not mid-flow |
| 9 | Double-tap Next on a clarifier "Yes" | One interrupt, no advance |
| 10 | Cancel during interrupt | `interrupted`, no result |
| 11 | Airplane mode, cases 1 and 8 | Identical behaviour |
| 12 | All 239 case-bank cases | **238 pass, CB_211 known finding, 0 unexpected failures** — unchanged |

### Proof that ordinary paths are unchanged

Case 4 is the load-bearing one. Assert the **exact question sequence** for a
path with no red-flag-affecting question, before and after the fix. It must be
identical — same questions, same order, same count. The 18 path scenarios in
`testing/questions/fixtures/paths/path_fixtures_v1.json` are the source for
these expectations.

---

## 8. Telemetry — must not become a red-flag oracle

**Telemetry contract v1.0 is unchanged. Do not extend it.**

An interrupted assessment emits **fewer** step-view events than a completed one.
If an interrupt emitted a distinguishable event — a different status, an extra
field, a reliably different count — telemetry would become a side channel
revealing that a specific user hit a danger sign. That is symptom-level PHI by
inference.

Requirements:

- Interception happens **before** `recordStepView()`, so an interrupted path
  emits no step event for the question that triggered it.
- Do **not** add a new completion status for "interrupted by red flag". Reuse
  the existing `interrupted` disposition, which already covers every
  non-clinical failure and therefore cannot be read as a clinical signal.
- Do **not** record which question interrupted, the red-flag token, the rule ID,
  or the resulting urgency.
- Keep the existing comment in `followup_screen.dart` explaining why the
  step-view event carries **no `step_count`** — that reasoning now covers this
  case too.

**Regression test:** the telemetry emitted by a red-flag path must be
indistinguishable from an assessment abandoned at the same step.

---

## 9. Rollback

- Put the fix behind a **default-off** compile-time flag
  (`--dart-define=W3_IMMEDIATE_RED_FLAG=true`), consistent with the adopted
  compiled-in / default-off internal distribution.
- Flag off ⇒ byte-identical behaviour to today. That is the rollback.
- Revert is a single-commit revert; nothing is persisted, no artifact is
  published, no `/config` entry exists.
- Because the fix only makes evaluation **earlier**, rolling back cannot
  introduce an under-triage that was not already present.

---

## 10. Out of scope — do not implement

- ❌ Adaptive re-branching (IM-003) — **deferred**, changes scoring inputs
- ❌ Optional skips (IM-007) — none exist; activation deferred
- ❌ Changing the path limit — **fixed at 5**
- ❌ The declarative condition evaluator, the graph engine, or loading the
  candidate artifact — later W3 tasks
- ❌ Any question wording, answer meaning or token effect change
- ❌ Any Backend work, `/config` entry, R2 upload or manifest change
- ❌ Any new red-flag token, rule or trigger

IM-004 (ID-keyed answers) is in scope **only** to the extent restoration
requires it.

---

## 11. Definition of done

- [ ] All 12 regression cases pass
- [ ] Case 4 proves ordinary paths are byte-identical
- [ ] Case 12 reproduces 238/239 with CB_211 as the known finding
- [ ] Telemetry cannot distinguish a red-flag path
- [ ] Works in airplane mode
- [ ] Behind a default-off flag
- [ ] `RedFlagEvaluator`, `ScoringEngine` and `UrgencyDeterminer` unmodified
- [ ] No question, answer or token changed
