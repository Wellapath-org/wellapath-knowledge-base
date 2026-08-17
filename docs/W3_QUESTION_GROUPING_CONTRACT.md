# W3 — Question Grouping Contract (schema 1.1, candidate 1.1)

The live `QuestionEngine` **de-duplicates**. Candidate 1.0 did not model that,
and the difference was not cosmetic: it changed which questions get asked on
1,930 of 2,325 paths. This contract makes the grouping explicit, so it can be
validated instead of inferred.

> **Unpublished, clinically unreviewed, inactive.** `may_publish` is false, no
> R2 object exists, no `/config` entry references it, and no build consumes it.
> Candidate 1.0 is retained unmodified and is likewise not published.

---

## 1. What the live engine actually does

Traced verbatim from `question_engine.dart` at Mobile
`657739cc1745104dd1194a57ef14cc9793c9b98e`:

```dart
for (final token in symptomTokens) {          // SELECTED order, not sorted
  final questions = kFollowupQuestionMap[token];
  if (questions == null) { needsDefaultDuration = true; continue; }
  for (final question in questions) {
    case severity:   severityQuestion ??= question;          // FIRST WINS
    case duration:   durationQuestion ??= question;          // FIRST WINS
    case additionalSymptoms:
      additionalQuestionText ??= question.questionText;      // FIRST WINS
      for (final o in question.options)                      // ORDERED UNION
        if (!additionalOptions.contains(o)) additionalOptions.add(o);
  }
}
if (needsDefaultDuration) durationQuestion ??= kDefaultFollowupQuestion;

clarifiers = [for (c in kRedFlagClarifiers)                  // DECLARATION order
  if (!selected.contains(c.redFlagToken) &&
      c.triggerTokens.any(selected.contains)) …];

result = [...clarifiers, ?severity, ?duration, ?additional];
return result.length > 5 ? result.sublist(0, 5) : result;    // drops from TAIL
```

Four consequences, each of which the contract has to represent:

| | Behaviour |
|---|---|
| Severity | Exactly one, first-encountered wins, **order-sensitive** |
| Duration | Exactly one, first-encountered wins, or the default fallback |
| Additional symptoms | Exactly one; **text** first-wins, **options** are the ordered union of the *triggered* tokens only, de-duplicated by exact string |
| Clarifiers | Every triggered one, in declaration order, **order-insensitive**, structurally undroppable (they lead the list) |

---

## 2. The eight grouping findings

| ID | Behaviour | Set? | Content? | Tokens? |
|---|---|---|---|---|
| GF-001 | Single severity question | yes | no | no |
| GF-002 | Single duration question | yes | no | no |
| GF-003 | Merged additional-symptoms question, unioned options | yes | no | no |
| GF-004 | Clarifiers are never grouped | no | no | no |
| GF-005 | Clarifier emission is order-**in**sensitive; follow-up selection is order-sensitive | no | no | no |
| GF-006 | Default-duration trigger | yes | no | no |
| GF-007 | Truncation drops from the tail | yes | no | no |
| GF-008 | Clarifier order is declaration order, not alphabetical | no | no | no |

Two of these were found by measurement, not by reading the code:

- **GF-006.** Candidate 1.0's default-duration trigger was `all 18 mapped tokens
  absent`. That fires on the *empty* selection, where the baseline asks nothing,
  and fails to fire for `{chest_indrawing_severe, boils}`, where the baseline
  does ask — `chest_indrawing_severe` and `fast_breathing_child` are mapped but
  have no duration entry. The corrected trigger is the conjunction the baseline
  computes: *some unmapped selectable token present* **and** *every
  duration-bearing token absent*.

- **GF-008.** Candidate 1.0 gave every clarifier priority 0, so ordering fell to
  the tie-break key — alphabetical. `kRedFlagClarifiers` is ordered
  `breathlessness_at_rest, inability_to_drink, abnormal_bleeding`, which is not
  alphabetical, so the first and third swapped on every path presenting both.
  168 paths. **Declaration order is already stable, so there was no
  nondeterminism to remove** — eliminating nondeterminism elsewhere is not a
  licence to reorder deterministic output.

---

## 3. The grouping semantics

### Group key

`grouping.group_key` identifies the merged question. **At most one question per
`group_key` on any path.**

`group_key` is **not** `tie_break_key`. `tie_break_key` orders questions;
`group_key` merges them. Two questions sharing a `tie_break_key` with no
grouping block is an *unresolved order tie* and is rejected (check G02) — never
read as an implied merge.

### Representative selection

`lowest_source_order_index`. Among sources whose `trigger_condition` holds, the
one with the smallest `source_order_index` supplies the wording.

`source_order_index` is assigned from the **sorted canonical token id**, so it
is a property of the artifact and not of any run, map iteration or build.

This is the **only** place the correction departs from the baseline, and it
departs only where the baseline has no stable answer to preserve.

### Option union

| Rule | Meaning |
|---|---|
| `static` | The question's own `answer_options`, unchanged. Used where every source offers identical answers (severity, duration). |
| `union_of_triggered_sources` | The union of the **triggered** sources' options, de-duplicated by `answer_option_id`, ordered by (`source_order_index`, position within that source). |

"Triggered only" is the part that is easy to get wrong. Presenting the full
union would offer the user symptoms no selected token contributed.

Two invariants, both validated:

- no source may present an option its question does not declare (check G05);
- no question may declare an option no source contributes (check G05) — such an
  option can never be presented, so review would approve content no user sees.

### Conflicts

| Conflict | Resolution |
|---|---|
| Text | `representative_wins` — the baseline shows one wording and never the others |
| Options | `union_preserving_all_sources`, or `reject` under the static rule |
| Answer value type | **`reject`, always.** Merging two answer shapes changes what an answer *means*. |

### What may never be grouped

`red_flag_clarifier`. Each clarifier carries its own red-flag token; merging two
would silently delete a danger-sign question. Declared in
`grouping_semantics.non_groupable_roles` and enforced at check G06 — an artifact
that omits the declaration is refused, so the protection cannot go missing
quietly.

### Grouping happens before truncation

`grouping_phase: before_truncation`. The limit of 5 counts **presented**
questions. Counting un-merged questions against it is precisely what made
candidate 1.0 drop questions the live engine asks, on 1,192 paths.

Red-flag questions remain exempt from truncation. If they alone reach the limit,
the limit yields.

---

## 4. Evidence

### Against real live output

`reports/question_grouping_parity_v1_1.json`. The comparison target is
`testing/questions/fixtures/oracle/live_question_oracle_v1.json` — the **actual
output of the Dart implementation**, captured by running it, not a Python
opinion about what it does.

| Dimension | Result over 2,325 paths |
|---|---|
| Identical | **2,325 / 2,325** |
| Question-set differences | **0** |
| Question-order differences | **0** |
| Wording differences | **0** |
| Option-set differences | **0** |
| Option-order differences | **0** |
| Token-effect differences | **0** |
| Red-flag-effect differences | **0** |
| Truncation differences | **0** |
| Red-flag questions dropped | **0** |
| Path limit exceeded | **0** |

Under reversed selection order the live engine **disagrees with itself on 1,680
of 2,300 paths**. The candidate is unstable on **0**. That gap is the defect
IM-001 removes.

Comparison keys are declared in the report rather than chosen to flatter it.
Severity and duration options are **not** compared: the live `FollowupQuestion`
carries an empty option list for them (their answers come from the severity
slider and duration chips), so there is nothing to compare and no match is
claimed.

### Beyond the oracle

`reports/question_grouping_coverage_v1_1.json`, in two stages.

**Stage 1** validates the Python transcription of the live algorithm against all
**4,625** real captured cases, forward and reversed: **0 mismatches**.

**Stage 2** — and only because stage 1 was clean — applies it to sizes the
oracle does not contain:

| Size | Paths | Set | Option | Red-flag | Truncation | Live order-sensitive | Candidate stable |
|---|---|---|---|---|---|---|---|
| 4 | 10,626 | 0 | 0 | 0 | 0 | 10,251 | yes |
| 5 | 42,504 | 0 | 0 | 0 | 0 | 42,092 | yes |

**Stage 2 is model-derived, not live output**, and is labelled as such wherever
it is cited. A transcription that matches 4,625 real cases can still diverge on
behaviour none of them exercises.

### Guards

`tools/validate_question_grouping.py` — 10 checks, all passing on candidate 1.1.
`--fixtures` runs **22 invalid fixtures**, each naming the check that must
reject it. **22/22 are rejected by the intended check**; being caught by a
*different* check counts as a failure, since that would prove only that the
artifact is broken and not that the guard works.

`tools/validate_question_flow.py` — the existing 53 checks, now schema-aware,
pass on candidate 1.1 **and** still pass unchanged on candidate 1.0.

---

## 5. Schema 1.1 is additive, and provably so

Schema 1.0 sets `additionalProperties: false` on a question, so grouping could
not be expressed under it at all. Rather than hand-writing a second schema and
hoping it stayed a superset, **1.1 is computed from 1.0** by
`tools/build_question_schema_v11.py`: load, add, dump. The generator re-proves
additivity on every run and refuses to write otherwise.

Added: `$defs.grouping`, `$defs.groupSource`, `question.grouping` (optional),
`metadata.grouping_semantics`, `pathControls.grouping_phase`.

One existing constraint **widened**: `metadata.schema_version` from
`const "1.0"` to `enum ["1.0", "1.1"]`. A 1.0 artifact still validates.

---

## 6. Versioning and migration

Candidate **1.0 is retained unmodified** as the record of what was measured, is
marked `superseded_retained`, and must not be published or consumed. Its
sha256 is unchanged and still matches the copy vendored into Mobile.

- 40 per-token follow-up questions become the 40 **sources** of 3 grouped
  questions. The default-duration fallback remains a separate question.
- Questions outside the grouped roles are **byte-identical** to 1.0, asserted by
  the generator, with one enumerated exception: clarifier `priority` and
  `provenance` (GF-008). Any other delta fails the build.
- Answer option ids changed for grouped questions
  (`Q-followup-<token>-<role>::x` → `Q-followup-<role>::x`). **No answer label,
  produced token or value changed.**

**A 1.0-only consumer must refuse schema_version 1.1.** It would parse a 1.1
artifact without error — the grouping block is just an unknown field to it — and
then present the full option union rather than the triggered union, offering the
user symptoms no selected token contributed. Silent partial understanding is the
failure mode; `kSupportedQuestionFlowSchemaVersions` in the handoff types exists
to prevent it.

---

## 7. What did not change

- No question added, removed or reworded.
- No answer meaning, produced token or value changed.
- No red-flag rule, trigger or token changed. **IM-002 timing is untouched** —
  the merged QB-002 correction stands, and grouping cannot move a red-flag
  evaluation later.
- Path limit stays 5. Red-flag questions stay undroppable.
- **IM-003 is not implemented** and is not made implementable here.
- Scoring, urgency, ranking, KB, rules, token dictionary, case bank and known
  findings are untouched. Frozen-input hashes are re-recorded in the artifact
  and unchanged.
- Vocabulary 2.0 remains declared unused.

---

## 8. Activation blockers

1. **Product sign-off on representative wording.** Path content no longer
   changes — that is now measured at zero — but on paths where the baseline was
   order-dependent, *which* existing wording is shown can differ from a given
   tap order. Content is unchanged; the choice among existing content is not.
2. Question content is unapproved (`content_approved: false` throughout).
3. No clinical review of the candidate (`not_reviewed`).
4. Unpublished — no R2 object, no `/config` entry, no manifest.
5. 7 of 13 condition operators remain unverified against real candidate data.
6. IM-003 deferred.
7. Path-limit value 5 is measured, not approved.
8. Coverage above subset size 5 is a stated limit, and sizes 4–5 rest on
   model-derived evidence rather than captured live output.
