<!--
  VENDORED HUMAN DECISION RECORD — DO NOT EDIT.

  Supplied by the Product reviewer in the I2/W3 Step 11 brief as chat text on
  24 August 2026, together with the explicit confirmation quoted at the end
  ("Yes — record the reconciled decisions now."). No file artifact existed;
  this file is the authoritative transcription. Tables were re-flowed from
  garbled paste formatting; no wording was altered.

  Reviewed over (the evidence hashes the review saw, at develop 38e2af6b):
    reports/im001_product_review_v1_1.json
      4788fee0b6bcf764c22add101d9e4ea806c70a4119c73e6b16b2ebdd2d4324c2
    reports/im001_option_order_decision_v1.json
      6adbfcc4e2a6983b4a07ff6e04298444061c9343e8da9a86b433b6e6f505f1b1
    reports/im001_option_order_evidence_v1.json
      fd4391a21c5db85c4881c2b5d238f968def58b999d6caa28580d28830e181939
-->

# I2/W3 Step 11 — Final Product Decision Reconciliation

**Reviewer:** Ayodele John Oluwaseyi
**Role:** Co-Founder & CEO, WellaPath
**Authority:** Product
**Review date:** 2026-08-24

The authoritative workbook contains **136 Product decisions: 135 wording
choices across 20 question-slot batches plus 1 global ordering decision**.
Batch approvals expand explicitly to their underlying decision IDs.

## Final decision totals

| Status | Count |
|---|---|
| Explicitly reviewed | **136 / 136** |
| Approved | **136** |
| Pending | **0** |
| Deferred | **0** |
| Individual overrides | **0** |
| Unresolved Product conflicts | **0** |

All 135 wording decisions resolve to **`keep_candidate_wording`**. The global
ordering decision resolves to **`ORD-A`**.

The workbook's measured clinical-impact dimensions remain zero for option
membership, labels, token mappings, reachable tokens, scoring reachability and
red-flag reachability. Product authority remains valid only while those
measurements remain zero.

## Global ordering decision

| Decision | Selection | Product rationale |
|---|---|---|
| `IM001-ORD-GLOBAL-001` | **ORD-A — approve candidate 1.1 deterministic option ordering** | A stable option order provides a consistent and predictable user experience regardless of symptom-selection order and improves reproducibility, testing and documentation. Evidence establishes that the change affects display order only. |

The workbook identifies this as **903 option groups across 1,872 captured
paths**, with option membership, labels, mappings, reachable scoring tokens and
reachable red-flag tokens unchanged.

## Wording decisions

| Batch | IDs | Approved candidate wording | Confirmed rationale |
|---|---|---|---|
| `DURATION-abdominal_cramps` | 15 | **How long have you had these abdominal cramps?** | Directly asks about the intended symptom; alternatives refer to other symptoms and create context mismatch. Candidate follows the established plural duration pattern. |
| `DURATION-body_pain` | 14 | **How long have you had this body pain?** | Clearly identifies body pain; inherited wording for other symptoms would be inconsistent and ambiguous. |
| `DURATION-chills` | 13 | **How long have you had chills?** | Concise, natural and directly asks about chills rather than another selected symptom. |
| `DURATION-cough` | 12 | **How long have you had this cough?** | Directly identifies cough and removes path-dependent wording inherited from unrelated symptoms. |
| `DURATION-dark_urine` | 11 | **How long have you noticed dark urine?** | Naturally asks when the intended symptom was observed and avoids wording referring to other symptoms. |
| `DURATION-dizziness` | 10 | **How long have you felt dizzy?** | Concise, natural and directly asks about dizziness. |
| `DURATION-fatigue` | 9 | **How long have you felt this fatigue?** | Directly identifies fatigue and avoids a path-dependent mismatch with other symptoms. |
| `SEVERITY-abdominal_cramps` | 5 | **How severe are your abdominal cramps?** | Clearly identifies the symptom being rated. Approval covers wording only, not clinical validity or the scale. |
| `DURATION-fever` | 8 | **How long have you had this fever?** | Clearly identifies fever and avoids unrelated symptom wording. |
| `DURATION-headache` | 7 | **How long have you had this headache?** | Directly identifies headache and removes misleading inherited wording. |
| `SEVERITY-body_pain` | 4 | **How severe is your body pain?** | Specifically identifies body pain; generic "this pain" can be ambiguous when multiple pain symptoms coexist. |
| `DURATION-nausea` | 6 | **How long have you had nausea?** | Directly identifies nausea and prevents other symptom wording from appearing in its place. |
| `SEVERITY-cough` | 3 | **How severe is your cough?** | Directly identifies cough; alternatives ask about unrelated symptoms. Approval covers display wording only. |
| `DURATION-pain` | 5 | **How long have you had this pain?** | Directly identifies the intended pain symptom and provides consistent wording. |
| `DURATION-sweating` | 4 | **How long have you had excessive sweating?** | Clearly identifies excessive sweating and removes mismatched symptom wording. |
| `SEVERITY-fast_breathing_child` | 2 | **How severe is the fast breathing?** | Among the existing choices, this is the only wording that identifies the symptom actually being clarified. **Clinical validity remains explicitly unapproved and flagged for Clinical review before activation.** |
| `DURATION-swelling` | 3 | **How long have you had this swelling?** | Directly identifies swelling and avoids unrelated symptom wording. |
| `DURATION-vomiting` | 2 | **How long have you been vomiting?** | Directly identifies vomiting; alternatives ask about weakness or watery stool. |
| `SEVERITY-headache` | 1 | **How severe is your headache?** | Explicitly identifies headache and avoids ambiguity when headache and another pain symptom coexist. |
| `DURATION-watery_stool` | 1 | **How long have you had watery stool?** | Directly identifies watery stool; the only alternative asks about weakness and is a clear context mismatch. |

The workbook confirms that the 15 duration batches contain **120 decisions**,
while the five severity batches contain **15 decisions**, for all **135
wording decisions**.

## Individual overrides

**None.**

No decision was changed from the candidate-selected wording to an alternative
wording.

## Deferred or unresolved Product decisions

**None.**

After Unit 21:

**Approved:** 136
**Pending:** 0
**Deferred:** 0
**Overrides:** 0

There are therefore no unresolved Product-selection conflicts.

## Explicit Clinical flag

One Product decision carries an additional boundary:

**`IM001-BATCH-SEVERITY-fast_breathing_child`**

Product approves only:

> **"How severe is the fast breathing?"**

as the least ambiguous of the already-existing displayed wordings.

Product does **not** approve:

- whether fast breathing in a child should be severity-rated;
- whether the question itself is clinically valid;
- whether the existing severity scale is appropriate;
- how the answer should be interpreted clinically.

The two underlying decisions are `IM001-D018` and `IM001-D027`.

This flag must remain visible for Clinical review before any activation
decision involving that question.

## Decision-record fields to be applied

For the global ordering decision:

```
reviewer_name: Ayodele John Oluwaseyi
reviewer_title: Co-Founder & CEO, WellaPath
authority: product
review_date: 2026-08-24
selection: ORD-A
clinical_approval: false
activation_authorization: false
```

For all **135 wording decisions**:

```
reviewer_name: Ayodele John Oluwaseyi
reviewer_title: Co-Founder & CEO, WellaPath
authority: product
review_date: 2026-08-24
selection: keep_candidate_wording
clinical_approval: false
activation_authorization: false
```

Each underlying decision should receive the confirmed rationale belonging to
its approved parent batch. Batch approval is explicitly permitted as shorthand
for expanding `keep_candidate_wording` across every member ID.

## Authorization boundaries

This final Product review does **not** authorize publication or activation of
candidate 1.1 and does **not** authorize Mobile implementation. Any future
nonzero difference in membership, token mapping, scoring or red-flag behaviour
reopens Clinical review.

Accordingly, after recording:

**Clinical approval:** `false`
**Activation authorization:** `false`
**Publication authorization:** `false`
**Mobile implementation authorization:** `false`

`IM-003` and `IM003-SB-001` remain outside this review. `IM-003` remains
disabled, its blocker remains open, and **Mobile PR #76 remains unauthorized
to merge**.

No question candidate, schema, clinical artifact, runtime behaviour, R2
configuration, Backend repository or Mobile repository is authorized to change
as a consequence of this Product confirmation alone.

## Final confirmation

> **Confirm these Product decisions for recording in the Knowledge Base? Yes
> or No.**
>
> Only an explicit **"Yes"** authorizes writing the decision artifacts.

**Confirmation given:** "Yes — record the reconciled decisions now."
(Product reviewer, 2026-08-24.)
