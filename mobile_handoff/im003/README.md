# Mobile handoff — IM-003 impact analysis

> ## DO NOT IMPLEMENT IM-003
>
> This is **evidence for review**. No decision is approved. Live behaviour
> remains static — `FollowupScreen` computes its question list once and no
> answer changes eligibility. The Question Flow 1.1 consumer remains isolated
> and unchanged.
>
> All **9** IM-003 decisions are `pending`. IM-003 remains
> `deferred_pending_product_and_clinical_review` and an activation blocker.

**Baseline:** Knowledge Base `0193a03d40f707460e2a8c799221a864776f1b9d` ·
Mobile develop `d820d6cfc3b96cbbba9d434ef4684b9a36140991`.

---

## Files

| File | What it is |
|---|---|
| `reports/im003_impact_analysis_v1.json` | Trigger graph, 56-pair table, red-flag cross-reference, scoring-input delta, closure and path effects |
| `reports/im003_decision_package_v1.json` | 9 decision records, 12 scenarios, path/UX analysis, case-bank applicability, decomposition recommendation |
| `docs/IM003_IMPACT_ANALYSIS.md` | The narrative |
| `testing/questions/fixtures/invalid_im003/` | 18 invalid fixtures + index |
| `tools/validate_im003.py` | 12 fail-closed guards |
| `tools/run_im003_checks.py` | One-command runner |

Hashes are published in the PR description and re-verified by
`tools/run_im003_checks.py`.

---

## The one thing Mobile is asked to do

**Nothing is asked to be implemented.** One measurement is asked for, and only
when engineering leadership wants decision D004 to become decidable.

### The missing measurement

Decision **D004 — scoring-token reachability** cannot be taken on this evidence
alone. The analysis establishes exactly which tokens become reachable and what
weight they contribute to which conditions. It does **not** establish the
resulting score, ranked conditions, top condition or urgency, because that
requires Mobile's `ScoringEngine`.

A Python model was written and validated against the 239-case bank. It
reproduced **234/239** top conditions and **217/239** urgencies — it disagrees
with the shipped engine on 22 urgencies, so it was **not used**. Publishing
deltas from it would have been worse than publishing none.

### The harness that would close the gap

Test-only, in Mobile, behind the same isolation as the 1.1 consumer:

1. For each state in a declared bounded set (the 24 driving tokens, subsets up
   to size 3 — the same bound the oracle uses):
   - run the **static** model: `QuestionEngine.generateQuestions(tokens)`;
   - simulate answering every reachable additional-symptoms option;
   - run the **additive** model: recompute eligibility with the answered option
     tokens added to state;
2. For both token sets, run the **existing** `RedFlagEvaluator`, then the
   **existing** `ScoringEngine` only when no red flag is active;
3. Compare and report separately: urgency · urgency source · ranked condition
   ids · top condition · score contributions · red-flag result · question count
   · completion · truncation set.

**Use the existing frozen KB, rules and scoring semantics. Do not alter an
expected result to obtain parity.** A difference is the finding.

Expected from this analysis, and worth asserting in that harness:

| | |
|---|---|
| Newly reachable tokens | **14** |
| Touching any red-flag pathway | **0** |
| Conditions whose scoring input can change | **30 of 50** |
| Red-flag questions displaced | **0** |
| Max questions added after grouping | **1** |
| Path limit | **5**, unchanged |

---

## What Mobile must NOT do

- Do not implement dynamic re-branching, in the live engine or the consumer.
- Do not connect the Question Flow 1.1 consumer to any screen.
- Do not implement removal, invalidation, answer editing, restoration or skips —
  only the **additive** mode was analysed, and it is the only monotone one.
- Do not change the path limit, question content, answer meanings, token
  effects, red-flag rules, scoring, urgency or ranking.
- Do not approve any decision.
- Do not treat the 239-case bank as validating adaptive branching. It carries
  `input_tokens` and **no answer sequence**, so it cannot exercise IM-003. Do
  not invent a sequence to make it fit.
- Do not treat severity and duration tokens as permanently nonclinical. They are
  inert **against kb 2.4 and rules 2.2**; that must be re-validated on every
  clinical artifact change.

---

## Reviewing

```bash
python3 tools/run_im003_checks.py            # 21 check groups
python3 tools/validate_im003.py              # 12 fail-closed guards
python3 tools/validate_im003.py --fixtures   # 18/18 rejected
```

Start with `docs/IM003_IMPACT_ANALYSIS.md`, then the decision records in
`reports/im003_decision_package_v1.json`.
