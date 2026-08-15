# CB_232 — Review Package

**Phase:** I2 / W2 Step 3 · **Owner of this document:** Knowledge Base / Data Engineering
**Status:** evidence report for human review — **no weight, tie-break, expected output or KB content changed**

Machine-readable evidence: `reports/case_findings_v1.json`
Reproduce: `python3 tools/report_case_findings.py`

CB_232 is one of three `observe` cases. Those cases carry **no asserted expected
value** by design — `testing/README.md` instructs the runner to *"record actual
output for human review; do not mark pass/fail."* CB_232 did not fail. It is
here because it was designed to be looked at.

---

## 1. The case

```json
{
  "case_id": "CB_232",
  "condition_target": "",
  "description": "Edge: conflicting tokens from malaria + acute_diarrhoea -> observe top condition",
  "input_tokens": ["fever", "chills", "watery_stool", "vomiting"],
  "demographic_tokens": [],
  "season": null,
  "expected_urgency": null,
  "expected_top_condition": null,
  "safety_critical": false,
  "expected_urgency_source": "observe"
}
```

| | Value |
|---|---|
| Input tokens | `fever`, `chills`, `watery_stool`, `vomiting` |
| Demographic tokens | *(none)* |
| Season | `null` |
| Context | none — no candidate condition IDs, no modifiers |
| **Expected** | *(none — `observe`)* |
| **Actual urgency** | `urgent` |
| **Actual top condition** | `malaria` |
| **Actual urgency source** | `urgency_default` |
| Red flag triggered | no |

Deliberately a **mixed presentation**: `fever` + `chills` point at malaria,
`watery_stool` + `vomiting` at acute diarrhoea.

---

## 2. Score contributions

Algorithm, from `wellapath-mobile/lib/core/engine/scoring_engine.dart`:

```
total_score = base_weight + Σ(weights of matched symptoms) + modifier_points
```

`modifier_points = 0` here: demographic modifiers only fire when the modifier
token is present in `candidateConditionIds` (none supplied), and seasonal
modifiers only fire when `currentSeason` is non-null (it is `null`).

### All conditions matching at least one input token (kb.ng.v2.4)

| Rank | Condition | base | matched symptoms (token:weight) | symptom Σ | **total** | urgency_default |
|---:|---|---:|---|---:|---:|---|
| **1** | **malaria** | **10** | `fever:9`, `chills:7` | **16** | **26** | **urgent** |
| 2 | acute_diarrhoea | 8 | `watery_stool:8`, `vomiting:5` | 13 | 21 | non_urgent |
| 3 | csm | 4 | `fever:7`, `vomiting:5` | 12 | 16 | emergency |
| 4 | yellow_fever | 3 | `fever:7`, `vomiting:5` | 12 | 15 | emergency |
| 5 | gastroenteritis | 7 | `vomiting:7` | 7 | 14 | non_urgent |
| 6 | dysentery | 7 | `fever:6` | 6 | 13 | urgent |

Full top-10 with every contribution: `reports/case_findings_v1.json` →
`findings[].ranking.top_10`.

---

## 3. Why malaria wins

Two independent reasons, and it needs only one of them:

1. **Highest symptom subtotal.** `fever:9 + chills:7 = 16` beats acute
   diarrhoea's `watery_stool:8 + vomiting:5 = 13`. Malaria's `fever` weight (9)
   is the highest `fever` weight in the KB, and `chills` (7) is matched by no
   other condition in this input.
2. **Highest base weight in the entire KB.** Malaria's `base_weight` is 10; the
   next highest anywhere is 8.

Margin over the runner-up: **5 points (26 vs 21)**.

Malaria would still rank first on symptom subtotal alone (16 vs 13), so this is
not purely a base-weight artifact — though the base weight widens the gap.

---

## 4. Determinism and tie-break — the direct answer

> **No tie-break is involved. There is no tie.**

| | |
|---|---|
| Top score | 26 |
| Conditions tied at top | **1** |
| Margin over runner-up | **5** |
| Tie-break required | **No** |
| Depends on iteration order | **No** |

The result is a strict, unambiguous win. It is fully deterministic and does not
depend on KB array order, map iteration order, or sort stability.

### Worth recording for the future, though

`ScoringEngine` ranks with `scored.sort((a, b) => b.score.compareTo(a.score))`.
Dart's `List.sort` is **not guaranteed stable**, and for a 50-element list it
does not use the insertion-sort path. So if two conditions ever *did* tie at the
top, the winner would be decided by sort implementation detail, not by a defined
rule. **There is no documented tie-break in the engine.**

That does not affect CB_232. It is flagged because the case bank contains at
least one known genuine tie — CB_239's note records *"hypertension ties anaemia
at 17 on this input; both non_urgent, so urgency holds; top-condition tie-break
resolved to hypertension in the engine run."* There, urgency was unaffected
because both tied conditions share an `urgency_default`. A future tie between
conditions with **different** urgency defaults would make the displayed urgency
depend on an unspecified sort. Out of scope here; worth a separate ticket.

---

## 5. Red flags and demographic escalation

| Check | Result |
|---|---|
| Global red-flag tokens in input | **none** — none of the 4 tokens is in the 13 global rules |
| Condition-specific red-flag tokens for malaria | **none** present |
| Red flag triggered | **no** — scoring proceeded normally |
| Demographic tokens supplied | **none** |
| Demographic escalation applied | **no** |
| Seasonal modifier applied | **no** (`season: null`) |
| Resulting urgency path | priority 5 → `urgency_default` of the top condition (`malaria` → `urgent`) |

---

## 6. Did this change between KB 2.3 and KB 2.4?

**No.**

| | kb 2.3 | kb 2.4 |
|---|---|---|
| Top | malaria, 26, urgent | malaria, 26, urgent |
| 2nd | acute_diarrhoea, 21, non_urgent | acute_diarrhoea, 21, non_urgent |
| 3rd | csm, 16, emergency | csm, 16, emergency |

Full ranking identical, every score identical
(`kb_version_delta.changed_between_2_3_and_2_4: false`). Malaria's `symptoms`
array is byte-identical between the two versions and its `base_weight` is 10 in
both. The only KB 2.4 change was adding a literal `headache` token to the
*headache* condition (E8.2, Issue #8), which this input does not touch.

---

## 7. Assessment

> **Deterministic ranking behaving as specified. Not a safety concern.
> There is a content-quality question worth recording.**

**Not a safety concern:**

- Urgency is `urgent` — the *more* conservative of the two candidates
  (acute diarrhoea would give `non_urgent`). Any error is over-triage.
- No red flag was suppressed; none was present to suppress.
- Result is deterministic and reproducible; no order dependence.
- Not safety-critical, and the run recorded **0 safety-critical under-triage**
  across all 150 safety-critical cases.

**Content-quality question, for clinical/product awareness — not raised as a defect:**

A patient reporting fever, chills, watery stool and vomiting is shown **malaria**
as the top cause, with acute diarrhoea second. In a Nigerian primary-care
context that is defensible — malaria is highly prevalent and febrile
presentations with GI symptoms are common — and the case bank author flagged the
case as `observe` precisely because reasonable people could differ.

This is the same tension already tracked as **Issue #38 — "Malaria base_weight in
mixed presentations"**, which `progress.md` records as: *base_weight kept at 10
(E8.2 Item 1), monitoring post-beta*. CB_232 is a concrete worked example of
that monitoring item, not a new finding.

**Recommended disposition:** record CB_232's observed output as the reference
result for this input, attach it to Issue #38 as evidence, and leave weights
unchanged. Nothing here justifies a KB change on its own.

---

## 8. Companion observe cases

Both reproduced identically; neither ties.

| Case | Input | Top condition | Urgency | Margin | Note |
|---|---|---|---|---:|---|
| **CB_225** | `fever` | malaria | urgent | 6 | Single common symptom. Malaria wins on `fever:9` + base 10 = 19 vs 13. Directly illustrates Issue #38. |
| **CB_233** | `chest_pain`, `dizziness`, `palpitations` | cardio_symptoms | urgent | 12 | Clean, decisive win (24 vs 12). The intuitively correct condition; no concern. |

---

## 9. Scope statement

Nothing was changed by this analysis:

- ❌ no symptom weight changed
- ❌ no `base_weight` changed
- ❌ no tie-break introduced or modified
- ❌ no expected output changed
- ❌ no KB, rules, token-dictionary or case-bank content changed
- ❌ no Mobile code changed

`kb.ng.v2.4.json`, `rules.ng.v2.2.json` and `testing/case_bank_v1.json` remain
byte-identical, asserted by `tools/check_compatibility.py` and CI.
