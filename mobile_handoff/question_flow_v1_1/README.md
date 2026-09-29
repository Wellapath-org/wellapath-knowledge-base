# Mobile handoff — Question Flow 1.1 (grouping correction)

Everything Mobile needs to consume candidate 1.1. **Additive** to
`mobile_handoff/question_flow_v1/` — the condition language, ordering, red-flag
hooks and path controls documented there are unchanged and still apply.

> **Do not activate anything.** The candidate is unpublished, clinically
> unreviewed, and consumed by no build. This package is for an engineering
> consumer behind a test boundary, exactly as Question Flow 1.0 was.
>
> **Do not implement IM-003.** Nothing here makes dynamic re-branching
> implementable, and adding it would change scoring inputs.

---

## What changed, in one paragraph

The live engine asks **one** severity question, **one** duration question and
**one** additional-symptoms question, no matter how many symptoms were selected.
Candidate 1.0 modelled one question per token per role, which planned a
different question set on 1,930 of 2,325 paths. Candidate 1.1 models the
grouping, and now matches real live output on **2,325 of 2,325**.

---

## Files

| File | What it is |
|---|---|
| `candidate/question_flow.ng.v1.1.json` | The corrected candidate |
| `schema/question_flow.v1_1.schema.json` | Schema 1.1 — additive over 1.0 |
| `mobile_handoff/question_flow_v1_1/question_grouping_types.dart` | Dart contract types for the grouping block |
| `docs/W3_QUESTION_GROUPING_CONTRACT.md` | The grouping specification |
| `testing/questions/fixtures/paths/grouping_path_fixtures_v1_1.json` | 16 authoritative path cases |
| `testing/questions/fixtures/invalid_grouping/` | 22 invalid fixtures + index |
| `testing/questions/fixtures/oracle/live_question_oracle_v1.json` | Real captured Dart output, 4,625 cases |
| `reports/question_grouping_parity_v1_1.json` | Path-by-path parity vs real output |
| `reports/question_grouping_coverage_v1_1.json` | Transcription validation + sizes 4–5 |
| `reports/question_no_clinical_change_v1_1.json` | 1.1 vs 1.0 clinical diff, GF-006/GF-008 regressions, PHI scan |
| `reports/im001_product_review_v1_1.json` | The 135 wording decisions Product must sign off |
| `reports/im001_option_order_evidence_v1.json` | 903 option-order contest groups (evidence, not 903 approvals) |
| `reports/im001_option_order_decision_v1.json` | The ONE global pending Product decision for deterministic option ordering |
| `docs/IM001_OPTION_ORDERING.md` | How the option-order evidence was verified and why one decision covers 903 groups |
| `testing/questions/fixtures/oracle/…provenance.json` | Immutable provenance record for the oracle |
| `testing/questions/fixtures/oracle/…harness.dart.txt` | Reproduction harness for the capture |

Candidate **1.0 and schema 1.0 are retained unmodified.** 1.0's sha256 is
unchanged and still matches the copy already vendored into Mobile — verify that
before assuming anything about the 1.1 package.

---

## Integration instructions

**1. Vendor byte-for-byte and verify.** Same discipline as Question Flow 1.0:
copy the files, record their sha256 in the Dart contract file, and fail the test
suite if a hash drifts. Do not hand-edit a vendored artifact.

**2. Refuse the version you cannot fully apply.** The existing loader supports
schema major 1 and would parse 1.1 without error, because the grouping block is
merely an unknown field to it — and would then present the **full** option union
instead of the triggered union, offering the user symptoms no selected token
contributed. Gate on the exact version:

```dart
if (!isSupportedQuestionFlowSchema(artifact.schemaVersion)) {
  throw const FlowLoadFailure.unsupportedSchemaVersion();
}
```

**3. Refuse an artifact whose grouping you cannot honour.** Fail closed on:
an unknown `merge_strategy`, `representative_selection` or `option_union_rule`;
a missing `_metadata.grouping_semantics`; `grouping_phase` other than
`before_truncation`; `one_question_per_group_key` false; `red_flag_clarifier`
absent from `non_groupable_roles`; a grouping block on a clarifier; two
questions sharing a `group_key`; duplicate `source_id` or `source_order_index`.

Each of those has an invalid fixture in `testing/questions/fixtures/invalid_grouping/`
that your loader must reject. Assert against the fixture index — it names the
expected failure for each.

**4. Plan with a Set, not a List.**

```dart
final List<QuestionGroupSource> triggered =
    grouping.triggeredSources(selectedTokens, evaluate);   // Set<String>
if (triggered.isEmpty) continue;                            // group is silent
final String text = grouping.representativeText(triggered)!;
final List<String> optionIds =
    grouping.presentedOptionIds(triggered, question.answerOptionIds);
```

Taking a `Set` is not a style preference. The defect being corrected is a
dependence on selection order; accepting a `List` leaves the door open to
reintroducing it.

**5. Group, then order, then truncate — in that order.**

```
group by group_key           → one presented question per group
sort by (priority, tie_break_key, question_id)
truncate to max_followup_questions, red-flag questions exempt
```

Truncating before grouping is exactly what made 1.0 drop questions the live
engine asks. `tie_break_key` orders and never groups.

**6. Assert against the path fixtures.** 16 cases. 11 carry the **real live
questions** alongside the expected plan; assert both. A consumer that only
agrees with the model proves nothing about the app.

The 5 cases marked `live_evidence: "not_captured"` mix driving tokens with
picker tokens the oracle does not enumerate. Their expectations are
model-derived, and the fixture says so — do not cite them as live evidence.

**7. Keep the boundary.** Same as 1.0: no live assessment source imports the
consumer, the consumer imports no networking, telemetry, scoring or
`AssessmentController`, and there is no `fromEnvironment` that could switch it
on. Assert it structurally.

---

## Two things that will look like bugs and are not

**`Q-followup-severity` is worded for `body_pain` when you selected
`headache, body_pain`.** Correct. The representative is the triggered source with
the lowest `source_order_index`, which is assigned from the sorted token id, and
`body_pain` sorts before `headache`. The live engine asks the same thing when
the user taps in that order; it asks the *other* wording when they tap the other
way, which is the instability being removed.

**The default duration question does not fire for `chest_indrawing_severe`
alone.** Correct, and it matches live. That token has no duration entry, but it
*is* mapped, so `needsDefaultDuration` never gets set. Add an unmapped token —
`{chest_indrawing_severe, boils}` — and the fallback appears. Candidate 1.0 got
this wrong in both directions (GF-006).

---

## What Mobile must reproduce

These are the acceptance conditions for the 1.1 consumer update. Each is a
number your test suite should compute, not copy:

| | Expected |
|---|---|
| Captured-oracle paths compared | **2,325** |
| Paths identical to live | **2,325** |
| Question-set / order / wording differences | **0 / 0 / 0** |
| Option-set / option-order differences | **0 / 0** |
| Token-effect / red-flag-effect differences | **0 / 0** |
| Truncation differences · red-flag questions dropped | **0 · 0** |
| Path-limit violations | **0** |
| Reversed-order paths compared | **2,300** |
| **Live** engine differs from itself | **1,680** |
| **Candidate** differs from itself | **0** |

The last two lines matter as much as the parity table. Reproducing only the
parity result would leave you unable to tell a correct implementation from one
that has quietly reintroduced an order dependence — the candidate must be stable
under reversed selection order, and the live baseline must not be.

GF-006 and GF-008 need their own regressions: the default-duration trigger must
fire for `{chest_indrawing_severe, boils}` and stay silent on the empty
selection, and two clarifiers must emit in `kRedFlagClarifiers` declaration
order, not alphabetical.

---

## What Mobile must NOT do with this

- **Update the isolated consumer to 1.1 — and no further.** Do not connect it to
  any screen, controller, route or widget. The runtime isolation asserted for
  1.0 must hold unchanged: no live assessment source imports it, it imports no
  networking, telemetry, scoring or `AssessmentController`, and there is no
  `fromEnvironment` that could switch it on.
- Do not publish, upload to R2, or add a `/config` entry.
- Do not enable any candidate question flow in a user-facing build.
- **Do not treat IM-001 as resolved.** It is still an activation blocker,
  pending **136** Product decisions: the **135** wording selections in
  `reports/im001_product_review_v1_1.json` **plus one** global
  deterministic-option-ordering rule in
  `reports/im001_option_order_decision_v1.json`. Merging 1.1 into the knowledge
  base did not change that, and neither did incorporating your PR #75 evidence.
- Do not implement IM-003 dynamic re-branching, restoration, editing or skips.
- Do not change the live `QuestionEngine`. The correction lives in the artifact;
  changing the engine to match is a separate, reviewed step.
- Do not treat sizes 4–5 evidence as live output.
- Do not claim clinical or product approval. Content is `content_approved:
  false` throughout and review status is `not_reviewed`.

---

## Option-order instability — your PR #75 evidence, now incorporated

Your addendum is **incorporated and superseded as the authority**. Its hash and
byte count were verified directly against PR #75 head `dd9c6d0`
(`371443cf…`, 1,252,307 bytes — both matched), and then **every count was
recomputed independently** from this repository's captured-Dart oracle. All 22
reconciled dimensions agree, with zero unpaired reversed cases.

The authoritative records are now
`reports/im001_option_order_evidence_v1.json` and
`reports/im001_option_order_decision_v1.json`. Cite those, not the addendum.

**What the evidence says:** option sequences differ on **1,872** paths. Option
membership and option-to-token mappings **do not differ on any path**. This is
**display-order instability only** — every dimension governing what a user can
declare is identical in both selection orders across all 2,300 comparisons, so
option order cannot change reachable tokens, scoring inputs, ranked conditions,
the top condition, urgency, red-flag interruption or path length.

**What that means for you:**

- The 903 contest groups collapse to **one** Product decision
  (`IM001-ORD-GLOBAL-001`, status `pending`). Do not build anything that expects
  903 separate approvals.
- Product review alone is sufficient **conditionally**. If a future change makes
  option membership, token mapping, reachable tokens, scoring reachability or
  red-flag reachability differ, the Product-only classification becomes invalid,
  clinical review becomes mandatory, and our validators fail closed.
- **Do not change the live `QuestionEngine` option ordering** on the strength of
  this evidence. It is evidence for a decision, not the decision.

### For PR #75 itself

1. Keep the addendum where it is — it is the provenance for our incorporation.
2. Update its `_metadata.status` from `pending_knowledge_base_incorporation` to
   `incorporated_superseded_by_knowledge_base`, and reference
   `reports/im001_option_order_decision_v1.json` as the authority. Leave
   `authoritative: false`.
3. Do not restate the counts as approved findings; cite the knowledge-base
   reports.
4. PR #75 may merge on its own merits once the above is done. Merging it does
   **not** resolve IM-001 and does **not** authorize an ordering change.

