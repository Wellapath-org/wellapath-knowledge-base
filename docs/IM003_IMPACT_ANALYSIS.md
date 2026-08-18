# IM-003 — Dynamic Re-branching: Impact Analysis and Decision Package

IM-003 would re-evaluate question eligibility after an answer, so a token
derived from an answer could make a further question eligible. **It is not
implemented, and nothing here implements, enables or approves it.**

> ### Analysis only
> No candidate, schema, question, answer, token effect, red-flag rule, scoring
> input, urgency rule or path limit is modified. Every decision below is
> `pending`. IM-003 remains `deferred_pending_product_and_clinical_review` and
> an activation blocker.

**Baseline:** Knowledge Base `0193a03d40f707460e2a8c799221a864776f1b9d` ·
Mobile develop `d820d6cfc3b96cbbba9d434ef4684b9a36140991`.

---

## 1. What IM-003 would do

Today `FollowupScreen.initState` computes the question list **once**, from the
symptom set selected before the screen opened. No answer changes eligibility.
A user who declares "I also have a fever" in an additional-symptoms question
gets no fever questions in that assessment.

Additive re-branching would, after each committed answer:

```
1  evaluate red flags immediately        <- QB-002, unchanged and unconditional
2  stop if a red flag is active
3  derive updated token / demographic / answer state
4  recompute question eligibility
5  keep already-answered questions that remain valid
6  add newly eligible questions
7  (removal of newly ineligible questions - NOT in scope)
8  (dependency invalidation - NOT in scope)
9  group and order deterministically     <- contract 1.1
10 enforce the path limit, red-flag questions exempt
11 select the next question
12 score only at a safe terminal state
```

Four modes exist. **Only the first is analysed.**

| Mode | Status |
|---|---|
| additive-only | analysed here |
| removal / invalidation | not analysed, not proposed, **not monotone** |
| answer-edit-driven | needs an editing model the MVP lacks |
| restoration-driven | needs a persistence model the MVP lacks |

---

## 2. The trigger graph

A node is a token that is a key in `kFollowupQuestionMap`. An edge `a -> b`
exists when `a`'s additional-symptoms question offers `b` as an option **and**
`b` is itself a map key — so answering "yes, I also have b" would make b's
questions eligible.

| | |
|---|---|
| Nodes | **18** |
| Edges | **56** |
| Two-cycles | **15** |
| Self-loops | **0** |
| Max closure from one seed | **14** tokens |
| Max convergence depth | **5** steps |

**Those 56 edges are exactly the 56 `(source, option)` pairs** the candidate's
IM-003 record reports. Recomputed from `kFollowupQuestionMap`, not carried over:
declared 56, recomputed 56, reconciles.

### Cycles do not mean non-termination — proved, not assumed

The graph is heavily cyclic. Under **additive-only** re-branching the token set
is monotone non-decreasing and bounded by a finite universe, so the iteration
reaches a fixed point regardless of cycles.

Monotonicity is **checked over every ordered pair of seed tokens** — adding a
seed never shrinks the reachable set — rather than asserted. Convergence is
measured per seed and bounded by the node count.

**This holds for additive mode only.** Removal re-branching is not monotone,
which is one reason it is out of scope.

---

## 3. The safety question, answered across all four pathways

The earlier IM-003 note said no additional-symptoms option is a *clarifier
trigger*. That is the weaker test: a token can be a danger sign through a global
rule or a condition's own `red_flags` list without ever being a clarifier
trigger.

All four pathways were checked for every one of the **14** newly reachable
tokens:

| Pathway | Tokens affected |
|---|---|
| global red-flag rule (`rules.ng.v2.2` `rules[].token`) | **0** |
| condition-specific red flag (`kb.ng.v2.4` `conditions[].red_flags`) | **0** |
| red-flag clarifier trigger | **0** |
| clarifier red-flag token | **0** |

**No newly reachable token touches any red-flag pathway.** Had one, it would be
a safety-critical decision and immediate evaluation after that answer would be
mandatory.

**Combination-only red flags:** checked and none exist to model —
`rules.ng.v2.2` keys every rule on a **single** token, and condition `red_flags`
are single tokens too.

---

## 4. What IM-003 *does* change: scoring input

All 15 newly reachable tokens carry KB scoring weight. They touch **31 of 50
conditions**.

The exact per-condition weight delta is published in
`scoring_input_delta.by_condition`.

### What is deliberately **not** computed here

Score values, ranked conditions, top condition and urgency. Those come from
Mobile's `ScoringEngine`, which this repository does not contain.

A Python scoring model was written and validated against the 239-case bank. It
reproduced **234/239** top conditions and only **217/239** urgencies — it does
not agree with the shipped engine. Publishing IM-003 deltas from a model that
disagrees with production on 22 urgencies would be worse than publishing none,
so the exact scoring **input** delta is published instead and the Mobile harness
is specified in the handoff.

---

## 5. Clinically inert versus active

| Answer role | Tokens | Scoring | Global RF | Condition RF | Clarifier | Verdict |
|---|---|---|---|---|---|---|
| severity | mild, moderate, severe, very_severe | 0 | 0 | 0 | 0 | inert today |
| duration | days_1_3, days_3_7, days_7_plus, weeks_2_plus | 0 | 0 | 0 | 0 | inert today |
| additional symptoms | 15 newly reachable tokens | **all 15** | 0 | 0 | 0 | **scoring-active** |

> **"Inert today" is not "nonclinical".** These tokens carry no weight and no
> red-flag reference **in kb 2.4 and rules 2.2**. That is a property of the
> current artifacts, not of the tokens. A future KB revision that gives `severe`
> a weight would make this subset clinically active with no change to the
> question flow — so any approval of an inert subset must be re-validated on
> every clinical artifact change and enforced by a validator, not by this
> sentence.

---

## 6. Path length and truncation

The path limit stays at **5**. IM-003 does not change it, and every extra
question competes for the same slots.

**Grouping is what keeps this small.** Under contract 1.1 each groupable role
presents one question, so N newly eligible severity questions still present one
severity question. Worst case is 3 clarifiers + 3 grouped roles = **6**, which
can exceed 5 by one.

Across the 12 scenarios: max questions added **1** · red-flag questions
displaced **0** · required questions displaced **0** · completion never becomes
impossible.

**No truncation priority is approved here.** Decision D006 sets out the
alternatives.

---

## 7. The 239-case bank cannot exercise IM-003

Every case supplies `input_tokens` — a **final token set** — plus demographics,
season and expected outcome. There is **no answer sequence and no question
order** in any of the 239 cases.

IM-003 is a property of the sequence: which answer unlocked which question. The
bank has no sequence, so it cannot exercise it. **No sequence was invented, and
the 239-case suite is not claimed to validate adaptive branching.**

What the bank still proves: the clinical baseline is unchanged, because no
runtime artifact was modified.

---

## 8. User experience

Measured where measurable; the rest is Product's, and no UI is proposed.

- max additional questions: **1** across the scenarios
- repeated/redundant questions: none — grouping presents one question per role,
  and answering an option for a token already in state is idempotent
- **a progress indicator can move backwards**, and a question can appear after
  the user believed the flow was complete

That last point is safety-adjacent rather than cosmetic: the QB-002 finding was
**abandonment**, not under-triage.

---

## 9. Decisions — 9, all pending

| ID | Decision | Reviewers |
|---|---|---|
| D001 | Is additive re-branching permitted at all? | product + clinical |
| D002 | Inert **severity** re-branching | product + clinical |
| D003 | Inert **duration** re-branching | product + clinical |
| D004 | **Scoring-token reachability** | product + clinical |
| D005 | Red-flag reachability (measured: none) | product + clinical |
| D006 | Truncation priority when 6 questions want 5 slots | product + clinical |
| D007 | Recursion depth | product + clinical |
| D008 | Progress display | product |
| D009 | Activation milestone | product + clinical |

Each names its evidence, affected paths, clinical impact, Product impact,
regression requirements, what approval authorizes and **what it does not**.

**There is deliberately no single "allow IM-003" checkbox.** One approval would
hide three different clinical risks behind one signature.

---

## 10. Engineering recommendation: **B, with conditions — then C separately**

Not approval. An engineering recommendation for the reviewers.

The evidence supports a clean split: a newly eligible question whose answer
tokens carry no scoring weight and no red-flag reference (severity and duration
today) is clinically inert against the current artifacts, while a newly eligible
**additional-symptoms** question makes new scoring tokens reachable and is not.
The two carry different risk and should not share one approval.

- **Not A** (defer everything) — the inert subset carries no measured clinical
  risk, and a flow that cannot react to its own answers stays broken.
- **Not C yet** — the scoring-affecting subset changes scoring input on 31 of 50
  conditions and its score/urgency/ranking delta has **not been measured**.
  Approving it first would be approving an unquantified change to triage input.
- **Not D** — nothing shows the question or content model is wrong. The gap is
  behavioural, not structural.

### The split must be structurally enforceable

A prose convention is not enough. The proposed shape is a per-question
`rebranch_class` (`inert` / `scoring_affecting`) **computed by the generator**
from the token's clinical references and re-validated on every clinical artifact
change — so a KB revision that gives `severe` a weight reclassifies the question
automatically instead of silently invalidating an approval.

**No schema change is made in this step.** That is a recommendation for a future
step to design and review.

---

## 11. Guards

12 fail-closed checks; **18 invalid fixtures, 18 rejected by the intended
check**. The build fails if the 56-pair count drifts, a scoring-affecting token
is called inert, a red-flag reference is missed, only clarifier membership is
checked, a clinical decision is filed Product-only, a decision lacks evidence or
a reviewer, any decision is approved, IM-003 is enabled, cycles are hidden,
branching is declared unbounded, the path limit or red-flag exemption is
violated, a frozen hash changes, the evidence binding breaks, case-bank
validation is claimed, or deltas are published from the unvalidated model.

The decision package is **bound to the impact report's exact hash** —
regenerating the evidence invalidates the decisions.

`python3 tools/run_im003_checks.py` — **21 check groups, 0 failed.**

---

## 12. Documentation correction


### Correction: the newly-reachable set was undercounted by one token

An earlier revision reported **14** newly reachable tokens and **30 of 50**
affected conditions. Both were wrong by one.

`newly_reachable` accumulated only the **second hop** — the options of each
newly eligible question — and never the produced token itself. Any token that is
*only* ever a first-hop target therefore disappeared. `pain` is exactly that
case: reached from `swelling`, and present in no other token's option list.

`pain` is canonical in token_dictionary 1.1, is picker-reachable, and **scores on
`minor_injury` at weight 6**, so the omission understated the scoring blast
radius by one token and one condition. It was visible as an internal
contradiction the whole time: the trigger graph listed `pain` among its 18 nodes
and the 56 pairs produced it, while the impact sections did not.

The red-flag conclusion is **unaffected** — `pain` intersects zero of all six
red-flag pathways, so "zero red-flag references" holds for all 15 tokens.

The check that should have caught this shared the same defect: I3 recomputed the
set with the same second-hop-only rule, so both sides were wrong in the same
direction and agreed. I3 is corrected, and a new **I13** asserts that the derived
token list equals the two-hop closure of the pair array, so the two views can
never silently diverge again.

Corrected figures: **15** newly reachable tokens, **31 of 50** conditions.


`progress.md` narrated "All 22 dimensions agree" for the IM-001 reconciliation
table, which has **21** entries and always did. Corrected to 21.

A prose count error only: no evidence array, count, hash, conclusion, candidate
or decision changed, and all 21 entries still agree with zero unpaired reversed
cases.

---

## 13. Activation blockers

1. **All 9 IM-003 decisions pending**, D004 blocked on a Mobile scoring measurement
2. IM-001 unresolved — 136 Product decisions pending
3. Question content unapproved
4. No clinical review of the candidate
5. Candidates unpublished — no R2, no `/config`, no manifest
6. Path limit 5 measured, not approved
7. Distribution deferred to I3

**Rollback is not applicable: nothing was activated.** IM-003 is exactly as
disabled after this analysis as before it.
