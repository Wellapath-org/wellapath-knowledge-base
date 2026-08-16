# Mobile Handoff — Adaptive Question Flow 1.0 (candidate)

**From:** Knowledge Base / Data Engineering · **Phase:** I2 / W3 Step 1
**Action required from Mobile right now:** **none.** Read and comment.

---

## 1. Bottom line

- The candidate is **not published, not approved, and not consumed by any build.**
- **Nothing in your app changes.** No Mobile file was modified by this work.
- This package exists so that when W3 implementation starts, the contract is
  read rather than guessed.
- Two things in it are **behaviour changes** you will have to implement and that
  need approval first — IM-002 and IM-001 in §6. They are flagged, not smuggled.

---

## 2. What we found in your code

Recorded in `reports/question_baseline_freeze_v1.json`, from vendored copies of
your source at `a269168`. Six files are hashed into `baseline/questions_v1/`.

**There is no question artifact** — the flow is Dart source: 18 token keys and
40 authored questions in `followup_question_map.dart`, 3 clarifiers, one static
engine class, five screens and a controller. It cannot be versioned, hashed or
rolled back independently of an app release.

Eleven findings are recorded. The one that matters most:

> **QB-002 (high): red-flag clarifier answers are not evaluated when answered.**
> `followup_screen.dart` accumulates answers in `Map<int, dynamic> _answers` and
> calls `_commitAnswers()` only when the **last** follow-up question is
> answered. A "yes" to *"Is it hard to breathe even when resting?"* does not
> interrupt — the red flag is evaluated once, in the engine, after every
> question has been shown.

Also worth your attention: QB-005 (which severity wording you ask depends on the
order the user tapped symptoms), QB-006 (truncation to 5 is applied *after*
clarifiers are prepended — no clarifier is dropped today only because there are
three of them), and QB-003 (the question list is computed once in `initState`,
so a token added by an answer generates no further questions).

---

## 3. Candidate artifact

| Field | Value |
|---|---|
| Path | `candidate/question_flow.ng.v1.0.json` |
| Schema | `schema/question_flow.v1.schema.json` (draft 2020-12) |
| Version / schema version | `1.0` / `1.0` |
| Questions / answer options | **50 / 300** |
| Release status | `candidate_unapproved` · `may_publish: false` |

Zero questions added, removed or reworded. Zero answer meanings or token effects
changed. Every question, label and token is **copied** from your Dart.

---

## 4. Types

`question_flow_types.dart` in this directory. Plain data classes, `dart:core`
only. Copy to `lib/core/questions/` and adjust the header for local lints.

Three deliberate choices:

- `RedFlagEvaluationHook.fromJson` defaults every flag to **`true`**. An
  unreadable hook means evaluate too often, never too late.
- `QuestionEffects.affectsRedFlags` defaults to **`true`** for the same reason.
- `triggerCondition` defaults to `{"never": true}` when absent — an
  unparseable question is not asked rather than asked unconditionally.

---

## 5. The three rules

1. **A red-flag-affecting answer is evaluated immediately** — before the next
   ordinary question is selected, and before scoring.
2. **A red-flag-affecting question is never dropped** to satisfy a length limit.
   If they exceed the limit, **the limit yields**.
3. **Editing clears dependents** — and the tokens they produced. Never keep a
   downstream answer and hope it still applies.

### Ordering

Sort by `(priority, tieBreakKey, questionId)` — use `FlowQuestion.orderKey`.
**Never** rely on map iteration, file order, or `List.sort`'s stability (Dart
does not guarantee it). Priority bands: clarifiers `0` → severity `10` →
duration `20` → additional symptoms `30` → demographics `100+`.

### Condition language

13 operators, 4 readable fields, no regex, no free-text matching, no fuzzy or
probabilistic branching. Evaluate with a shared evaluator; never with anything
that can execute code.

Fail-closed, and please keep it that way: unknown operator or field is an
**error**, not `false`. Unknown `sex`/`pregnancy`/`age` makes the condition
**false** — an unanswered question is not "no", so a gated question is *not
asked* rather than wrongly asked.

### Skip

Six distinct states — see `QuestionAnswerState`. A skip sentinel produces **no
clinical token**; a required question is **never** skippable. The projection
introduces **no skips**: every question is `skippable: false` today.

---

## 6. Behaviour changes you will have to implement

Both are recorded in `_metadata.impedance_mismatches` and **need approval before
implementation**.

**IM-002 — immediate red-flag evaluation** (clinically substantive).
Move evaluation from "once, after everything" to "after every red-flag-affecting
answer". This is strictly **earlier, never later**: it cannot suppress a red flag
that fires today, only fire the same one sooner. Needs engineering-lead +
clinical approval. **Not implemented here.**

**IM-001 — deterministic question selection** (not clinically substantive).
Replace `severityQuestion ??= question` over selected tokens with the declared
`tieBreakKey`. The competing questions differ only in wording ("How severe is
your headache?" vs "How severe is this pain?") — no token, weight, red flag or
urgency differs. Needs product confirmation of the chosen wording.

Also specified but additive: IM-003 (re-branch on newly derived tokens — can
only ask *more*, still bounded), IM-004 (key answers by ID, not list index),
IM-005 (truncation exemption made structural), IM-007 (`skippable` supported but
unused).

---

## 7. Privacy — unchanged and non-negotiable

**Telemetry contract v1.0 is unchanged.** Nothing here alters it.

Never send to Backend or telemetry: question IDs correlated with a session,
answers, selected symptoms, derived tokens, red-flag IDs, rule IDs, scores,
urgency, narrative clinical text, or any partial path.

Your current code already gets this right, and it should stay right:
`followup_screen.dart` records a step view with **no `step_count`**, precisely
because the count is derived from the symptom set and would leak it. Please keep
that comment and that behaviour.

There is **no free-text answer type** in the contract — every answer is an
enumerated option ID.

---

## 8. Fixtures

| File | Contents |
|---|---|
| `testing/questions/fixtures/paths/path_fixtures_v1.json` | 18 path scenarios + 3 edit scenarios, with expected question sequences |
| `testing/questions/fixtures/invalid/` | 23 invalid artifacts, one defect each, with the validator check each must trip |

Scenarios cover: male path with pregnancy skipped, applicable and non-applicable
pregnancy, shortest and longest paths, multiple and no eligible follow-ups,
branch convergence, five body areas, red-flag clarifier raised and suppressed,
restored offline state, and three upstream-edit invalidation cases.

All synthetic and spec-derived. **No real-user assessment data.** Use these as
golden fixtures — if your implementation reproduces all 21, it conforms.

---

## 9. Do not

- Do not ship a build depending on this candidate before approval.
- Do not implement IM-001 or IM-002 before they are approved.
- Do not let any condition read anything outside `QuestionAssessmentState`.
- Do not add a free-text clinical answer.
- Do not send question IDs, answers, tokens or paths anywhere.
- Do not treat an unanswered demographic as a "no".
- Do not drop a red-flag question to fit a length limit.

---

## 10. Open questions for you

1. Does anything else in the app call `QuestionEngine.generateQuestions` besides
   `followup_screen.dart`? Our inventory says no; please confirm.
2. Is assessment state ever persisted today? We found none — it is in-memory and
   lost on exit. The contract specifies restored-state behaviour; you would be
   building that from scratch.
3. The flow is compiled into the binary. Serving it as an artifact needs a
   `/config` entry, a download path and a last-known-good fallback — none of
   which exists. Is that the intended direction, or should the artifact stay a
   build-time input?
