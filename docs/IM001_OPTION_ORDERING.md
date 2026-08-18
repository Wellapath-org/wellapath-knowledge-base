# IM-001 — Option Ordering: Evidence and the Global Product Decision

**Phase:** I2 / W3 Step 5B · **Owner:** Knowledge Base / Data Engineering
**Status:** evidence incorporated · **one Product decision pending** · **no approval given**

| Artifact | Path |
|---|---|
| Evidence table (903 groups) | `reports/im001_option_order_evidence_v1.json` |
| Global decision | `reports/im001_option_order_decision_v1.json` |
| Wording decisions (135) | `reports/im001_product_review_v1_1.json` — **unchanged** |
| Validators | `python3 tools/validate_im001_decisions.py` (51 checks) |

---

## 1. What was found

The live Dart engine's answer-option order depends on the order the user tapped
their symptoms. Reversing the selection order changes the option sequence.

Across **2,300** forward/reversed comparisons from the captured-Dart oracle:

| Mutually exclusive classification | Count |
|---|---:|
| identical | 413 |
| wording **and** option-order differ | 1,665 |
| option-order only | 207 |
| wording only | 15 |
| **total** | **2,300** |

**Option sequences differ on 1,872 paths. Option membership and token mappings
do not differ on any path. This is display-order instability only.**

| Dimension | Differences |
|---|---:|
| wording | 1,680 |
| option ID / label / token-mapping **sequence** | 1,872 |
| option ID **set** | **0** |
| option label **set** | **0** |
| option-to-token mapping **set** | **0** |
| reachable token set | **0** |
| scoring-affecting reachable tokens | **0** |
| red-flag-affecting reachable tokens | **0** |
| question identity / role sequence | **0** |
| truncation set | **0** |
| required / skip semantics | **0** |

### Why membership cannot change

The engine **unions** additional-symptom options over the triggered tokens. A
union is a set operation: reversing the visit order changes the order options are
appended in, and nothing else. Not one token is reachable in one order and not
the other — `tokens_reachable_in_one_order_only` is empty across all 2,300
comparisons.

Consequently option order **cannot** change reachable tokens, scoring inputs,
ranked conditions, the top condition, urgency, red-flag interruption, path length
or completion.

---

## 2. Independent verification

Mobile PR #75 produced an addendum
(`docs/evidence/im001_option_instability_addendum_v1.json`, sha256
`371443cf…`, 1,252,307 bytes), explicitly marked **non-authoritative**.

Its hash and byte count were verified directly against Mobile PR #75 head
`dd9c6d0` — both matched exactly.

Every count above was then **recomputed here** from this repository's own
captured-Dart oracle and the frozen clinical artifacts.
`tools/report_im001_option_ordering.py` never reads Mobile's figures as an input;
it stores them only to reconcile against. **All 21 reconciled dimensions agree**,
with zero unpaired reversed cases.

### One definitional correction worth recording

A first pass defined "question identity" as `(role, question_text)`, which
reported 1,680 identity differences and correctly tripped the safety gate. That
was a defect in the *definition*, not a clinical finding: which wording fills a
slot is a separate reviewable choice, already counted as the `wording` dimension
and decided by the 135 wording decisions. Identity is now `(role,
red_flag_token)` — the slot, not its text — which yields **0** and matches
Mobile. Folding wording into identity double-counted the same 1,680 differences.

---

## 3. One decision, not 903

`IM001-ORD-GLOBAL-001` · type `deterministic_option_ordering_rule` · status
**pending** · reviewer role **Product** · reviewer, date and rationale **null**.

- **Under review:** within a grouped question, options are emitted in a declared
  deterministic order rather than in engine visitation order.
- **Baseline:** option order follows selected-token visitation order.
- **Candidate:** deterministic ordering defined by Question Flow 1.1.
- **Affected:** 903 contest groups · 1,872 paths.
- **Activation blocker:** yes, until approved.

**Approval would authorize:** deterministic ordering of the same existing options
within a grouped question — nothing else.

**Approval would not authorize:** rewording a question, adding an option,
removing an option, changing an option-to-token mapping, changing scoring,
ranking or urgency, changing any red-flag token/rule/trigger, IM-003 adaptive
re-branching, publication of any candidate, or production/beta activation.

### Why one decision is legitimate here

All 903 groups ask the same question — should option order be deterministic? —
and every clinical dimension is identical across all of them. Asking Product 903
times would be asking one question 903 times. The groups are retained in full
because a reviewer is entitled to inspect the instances.

### Why Product review alone is sufficient — and when it stops being

`clinical_review_required: false` is **conditional**, and the condition is
recorded in the artifact:

> Product review alone is sufficient ONLY while option membership,
> option-to-token mapping, reachable tokens, scoring reachability and red-flag
> reachability all remain zero. If any becomes non-zero this classification is
> invalid, clinical review becomes mandatory, and validation fails.

This is enforced, not merely asserted:
`tools/report_im001_option_ordering.py` **refuses to emit the decision at all**
if any clinical dimension is non-zero, and
`tools/validate_im001_decisions.py` fails on
`product_only_classification_is_justified`.

---

## 4. The 903-group evidence table

`reports/im001_option_order_evidence_v1.json` → `option_order_groups`. Each
group carries: `group_id`, `grouped_question_role`,
`source_questions_or_tokens`, `baseline_forward_option_order`,
`baseline_reversed_option_order`, `candidate_deterministic_option_order`,
`option_membership`, `option_to_token_mapping`, `affected_path_count`, example
paths, per-token KB/rules/red-flag references, and
`clinical_impact_classification` (`display_order_only` on all 903).

The global decision is **bound by SHA256** to this table
(`evidence_binding.sha256`). Regenerating the evidence regenerates the binding;
a drifted hash fails validation.

---

## 5. Wording decisions unchanged

The 135 wording decisions in `reports/im001_product_review_v1_1.json` are
**untouched** — file byte-identical to develop. All 135 remain `PENDING`, no
wording text or alternative changed, and no wording decision is merged into the
ordering rule. Validators enforce all of this.

---

## 6. IM-001 remains blocked

> **136 Product decisions are required: 135 wording selections + 1 global
> ordering rule. None is approved. IM-001 is not resolved.**

The two halves are separate and counted separately. `im_001_resolved` is
`false`; the wording review's `sign_off.blocks_activation` remains `true`.

---

## 7. What did not change

- `candidate/question_flow.ng.v1.1.json` — byte-identical (`3ea534b0…`)
- `candidate/question_flow.ng.v1.0.json` — byte-identical
- `schema/question_flow.v1.schema.json` — byte-identical
- `reports/im001_product_review_v1_1.json` — byte-identical
- The captured-Dart oracle — byte-identical (`18c16306…`)
- All frozen clinical artifacts — byte-identical
- No question, option, token mapping, red-flag effect, scoring, urgency, ranking
  or path-limit change. Path limit still 5, optional skips still 0, IM-003 still
  deferred, candidates still unpublished and inactive.
- Mobile and Backend untouched.
