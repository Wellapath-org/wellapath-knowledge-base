# IM003-SB-001 — Clinical and Product Adjudication Package

**Phase:** I2 / W3 Step 8 · **Owner:** Knowledge Base / Data Engineering
**Status:** `open_awaiting_clinical_and_product_adjudication`
**Classification authority:** engineering evidence — **not** a clinical finding

| Record | Path |
|---|---|
| Blocker registry | `reports/im003_safety_blockers_v1.json` |
| Reconciliation | `reports/im003_mobile_measurement_v1.json` |
| Vendored Mobile evidence | `baseline/im003_mobile_v1/im003_mobile_scoring_measurement_v1.vendored.json` |
| Validators | `python3 tools/validate_im003_blockers.py` (66 checks, 17 mutation proofs) |

---

## 1. What was measured

Mobile PR #76 (**open, unmerged**, head `13be0d4937b1c49d6a49ddf096c5d5b6a47c2091`) ran
63 IM-003 scenarios through the **shipped** `EngineController` — the same
`RedFlagEvaluator`, `ScoringEngine`, `UrgencyDeterminer` and `OutputFormatter`
the app uses — over pinned KB 2.4, rules 2.2 and token dictionary 1.1.

No scoring was reimplemented. Controller output is cross-checked against the
shipped scorer's full ranking on every scenario, throwing on any disagreement.
The rejected Python approximation supplied nothing.

| Result | Count |
|---|---:|
| Scenarios | 63 (12 authoritative + 51 graph-derived) |
| **Red-flag changes** | **0** |
| Urgency changes | **25** |
| — escalations | 24 |
| — **de-escalations** | **1** |
| Urgency-source changes | 0 |
| Top-condition changes (overlapping) | 31 — **all became malaria** |
| Primary top-condition changes | 6 |
| Ranking-only changes | 29 |
| Score-only / no effect | 0 / 3 |

**Category note.** The partition is by *highest-order effect* and sums to 63:
25 urgency + 6 top-condition + 29 ranking-only + 0 score-only + 3 no-effect.
The figure **31** is an **overlapping** metric — every scenario whose top
condition changed. 25 of those also changed urgency and are counted in that
higher bucket; the remaining **6** are the primary top-condition changes.
25 + 6 = 31. Quoting 31 alongside the partition without this note double-counts.

---

## 2. The finding

> **S10_path_limit_pressure: urgency de-escalated from `emergency` to `urgent`
> with no red-flag change.**

| | Baseline | Expanded |
|---|---|---|
| Tokens | `bleeding`, `difficulty_breathing`, `fever`, `headache`, `poor_feeding` | + 10 additive tokens |
| **lassa_fever** score | **26** | 26 (unchanged) |
| **malaria** score | 25 | **52** |
| Top condition | **lassa_fever** | **malaria** |
| Urgency | **emergency** | **urgent** |
| Urgency source | `urgency_default` | `urgency_default` |
| Red flag triggered | `false` | `false` |

**Ranked order — the transition, observed rather than asserted.** Re-ranking the
whole of KB 2.4 over each token set reproduces the shipped engine's ranking
exactly on both sides:

| Rank | Baseline | Expanded |
|---:|---|---|
| 1 | **lassa_fever** 26 · `emergency` | **malaria** 52 · `urgent` |
| 2 | malaria 25 · `urgent` | acute_diarrhoea 30 · `non_urgent` |
| 3 | snake_bite 23 · `emergency` | **lassa_fever** 26 · `emergency` |

`lassa_fever` is **out-ranked, not eliminated** — it holds the same score, 26,
and the same `urgency_default: emergency` on both sides. It simply stops being
the condition urgency is read from. This is the substance of review question 3.

**Path-limit validity.** The scenario is one of the 12 `authoritative_supplied`
inputs, seeded to the point where "the limit of 5 is already reached before
re-branching". The limit caps how many follow-up questions are *presented*, not
how many tokens an answered assessment carries, and scoring is what is measured
here. The ten additive tokens are the converged closure (depth 3) of the seed
set, so this is the most loaded scoring state the limit permits — not a state
beyond it.

Independently re-derived from `kb.ng.v2.4.json`:

- lassa_fever 26 = base 4 + fever 7 + headache 5 + bleeding 10 — `urgency_default: emergency`
- malaria 25 = base 10 + fever 9 + headache 6 — `urgency_default: urgent`
- malaria 52 = base 10 + fever 9 + chills 7 + headache 6 + sweating 6 + body_pain 5 + weakness 5 + nausea 4
- No rule token appears in either set, so **no rule was omitted** — the red-flag
  result really is `false` on both sides.
- A single condition holds the top score on each side, so **no tie or unstable
  ordering** explains the flip.

## 3. Mechanism

```
additive answers
  → additional scoring tokens
    → condition scores change (malaria 25 → 52; lassa_fever static at 26)
      → a different condition ranks first (lassa_fever → malaria)
        → urgency is taken from that condition's urgency_default
          → emergency → urgent, with no red-flag change
```

> **Red-flag invariance does not prove urgency invariance.** Across all 63
> scenarios the red-flag result never changed, and urgency still changed 25
> times — once downward. Urgency has a second source: the top condition's
> `urgency_default`. Re-ranking alone can move it.

**Nothing was repaired.** Condition weights, `urgency_default`, scoring,
ranking, red-flag rules, candidate questions, the path limit and Mobile
behaviour are all unchanged.

---

## 4. What this document does not say

It does **not** say the behaviour is safe, correct, conservative or acceptable.
It does not say it is unsafe. It does not say `emergency` was the right baseline
urgency, nor that `urgent` is an acceptable expanded urgency. Those are clinical
judgements, and they are exactly what is being asked for below.

---

## 5. Questions for clinical and product review

These are **questions**, not proposed answers.

1. **Is any `emergency` → `urgent` transition caused solely by a new top
   condition acceptable?** The user supplied *more* symptom evidence and the
   result became less urgent. Is that ever acceptable, and if so under what
   constraints?

2. **Should final urgency be monotonic with respect to additive symptom
   evidence?** That is: may adding a symptom ever lower urgency? If not,
   monotonicity becomes a design requirement, not an implementation detail.

3. **Should urgency combine the highest applicable urgency across credible
   ranked conditions, rather than only the top condition's default?** In S10,
   lassa_fever remained the **third**-ranked candidate at 26 with
   `urgency_default: emergency` — it was out-ranked, not eliminated, and its
   score did not move. `snake_bite` (23, `emergency`) sat third in the baseline
   ranking on the same evidence. Should a credible emergency-default condition
   still be able to hold urgency when it is no longer ranked first?

4. **Is `S10_path_limit_pressure` clinically plausible and in scope?** It seeds
   five tokens including `bleeding` and `poor_feeding`, then adds ten. Is that a
   presentation worth designing for, or an artificial worst case?

5. **Is the lassa_fever → malaria ranking transition expected for these
   tokens?** Malaria gains 27 points from seven common symptoms; lassa_fever
   gains nothing. Is that the intended relative behaviour of these two
   conditions?

6. **Should IM-003 remain fully blocked, or may a structurally inert subset be
   evaluated separately?** Severity- and duration-only re-branching produce
   tokens with no KB weight and no red-flag reference against the current
   artifacts. Is separating them worth the added surface, given this finding?

7. **What regression cases are required before reconsideration?** At minimum:
   does the 239-case bank need question-path coverage it does not currently
   have? (It supplies tokens directly to the engine and does not traverse the
   question flow.)

---

## 6. Effect on D004

`IM003-D004-SCORING-REACHABILITY` remains **pending** and activation-blocking.
Its evidence now records the shipped-engine measurement and names IM003-SB-001.
It requires **clinical and product** review, and it cannot be taken while the
blocker is open.

The earlier engineering recommendation — *"B with conditions, then C
separately"* — could have been read as permitting scoring-affecting
re-branching once C was reviewed. That reading is **suspended**
(`status: NARROWED_PENDING_IM003_SB_001`). The original text is retained
verbatim rather than deleted, so the reasoning that led here stays auditable.

---

## 7. What is authorized by this document

**Nothing.** Not IM-003 activation in whole or in any subset. Not merging Mobile
PR #76. Not approving D004 or any IM-003 decision. Not internal, external-beta
or production activation. Not any change to scoring, ranking, urgency, red flags
or the path limit.

Mobile PR #76 remains **open and unmerged**, as does this package.

---

## 8. Step 9 update — Product disposition recorded, blocker still open

A human decision record dated 22 August 2026 was incorporated at I2/W3 Step 9
(see `docs/IM003_DISPOSITION_RECORD.md` and `reports/im003_disposition_v1.json`).
It **does not resolve IM003-SB-001** and grants no approval of any kind. It
records six Product decisions (including the provisional invariant that, for
IM-003, adding evidence must not lower established urgency solely because
condition ranking changes), and converts questions 1–7 above into seven open
clinical requirements (IM003-CR-001…007) plus ten required regression case
classes. The Step 9A authoritative reviewer record names **Ayodele John
Oluwaseyi (Co-Founder & CEO, WellaPath)** as the Product reviewer; the
Clinical reviewer is **not assigned**, effective authority is `product`, and
nothing in the disposition is clinical approval.
