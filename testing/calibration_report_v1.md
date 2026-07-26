# E8.2 Weight Calibration Report — v1

**Phase:** E8.2 (Weight Calibration) · **Input:** E8.1 case bank results · **Author:** Data Engineer
**Scope guard:** scoring accuracy only. The safety layer — red flag rules and urgency priority
order — is **not** touched by any recommendation here. Changes below are **proposed, not
implemented**; engineering lead reviews first, and any scoring change affecting clinical routing
should still get a clinician's eyes before release.

---

## Item 1 — Malaria `base_weight` dominance (Issue #38 / CB_232)

### Current state
`malaria` has `base_weight: 10` — the sole outlier in the KB. Distribution:

| base_weight | # conditions | examples |
|---|---|---|
| 10 | 1 | malaria |
| 8 | 3 | urti, cough_common_cold, acute_diarrhoea |
| 7 | 5 | typhoid_fever, pneumonia_children, dysentery, gastroenteritis, hypertension |
| 3–6 | 41 | the rest |

### CB_232 analysis — the premise doesn't hold up
The issue states malaria "wins before symptom weights are counted." I scored the actual case
(input: `fever, chills, watery_stool, vomiting`):

| condition | base | matched symptoms | total |
|---|---|---|---|
| **malaria** | 10 | fever (9) + chills (7) = 16 | **26** |
| acute_diarrhoea | 8 | watery_stool (8) + vomiting (5) = 13 | 21 |

Malaria's lead here is **symptom-driven, not base-driven**. Its matched symptom weight (16)
already exceeds diarrhoea's (13) before base weight is added. Counterfactual:

| malaria base | malaria total | vs diarrhoea 21 | outcome |
|---|---|---|---|
| 10 | 26 | +5 | malaria wins |
| 9 | 25 | +4 | malaria wins |
| 8 | 24 | +3 | **malaria still wins** |

So reducing `base_weight` to 8 would **not** change CB_232's result. The base weight widens the
margin but is not the deciding factor in this case. The case bank contains no case where malaria's
base weight is the sole reason it wins — the "dominance" concern is not demonstrated by CB_232.

### Clinical context
Malaria is the leading cause of febrile illness in Nigeria; a modest prior lean toward malaria in
ambiguous fever presentations is epidemiologically defensible and reduces the more dangerous
failure mode (under-considering malaria in a fever). The competing risk is crowding out
co-circulating febrile conditions (typhoid especially, which is frequently co-infected).

### Recommendation: **Option A (keep base_weight 10)**, with 9 as an acceptable compromise
- **Keep 10 (recommended):** the malaria lead in genuinely mixed cases is small and symptom-driven;
  the conservative prior is justified for Nigeria. No evidence in the case bank that 10 causes a
  clinically wrong win.
- **Reduce to 9 (acceptable):** trims the artificial base advantage by one point while malaria still
  leads on real symptom weights. Low-risk if the team prefers symptom weights be marginally more
  decisive.
- **Advise against 8:** this flattens malaria to the same base as `urti` / `cough_common_cold`
  (self-care conditions), which understates malaria's pre-test probability in the Nigerian context.

**Proposed change (only if Option 9 is chosen):** `malaria.base_weight: 10 → 9`. No other file
touched. If Option A, no change.

---

## Item 2 — `increase_urgency` no-op on already-urgent conditions (Issue #36)

### Current state
43 `increase_urgency` modifier occurrences KB-wide. Priority 4a escalates **one tier**
(`self_care → non_urgent`, `non_urgent → urgent`) and caps at `urgent` (below the safety layer).
Split:

- **12 functional** — default `self_care`/`non_urgent`, value moves.
- **31 no-op** — default already `urgent` or `emergency`, value is capped and does not move.

### Why Option B does not help this set
`escalate_urgent` (Option B) returns `urgent`. On a condition whose default is **already** `urgent`
or `emergency`, that is **also a no-op** — identical outcome to today. The only tier above `urgent`
is `emergency`, which is the **safety layer** (red-flag / escalate_emergency territory) and is
explicitly out of scope for E8.2. So B changes nothing for the 31 cases. It would only matter for
`non_urgent`/`self_care` defaults, which are the 12 already-functional cases.

### The 31 no-op occurrences (19 conditions)

| condition | default | no-op modifier(s) | recommendation |
|---|---|---|---|
| asthma | urgent | children_under_5 | A |
| cardio_symptoms | urgent | over_40, hypertension_known, diabetes_known | A |
| cholera | emergency | pregnancy | A |
| csm | emergency | unvaccinated | A |
| dysentery | urgent | children_under_5, moderate_malnutrition_mam | A |
| fever_unknown | urgent | elderly | A |
| hepatitis_b | urgent | immunocompromised | A |
| lassa_fever | emergency | healthcare_worker | A |
| lower_respiratory_infection | urgent | elderly | A |
| malaria | urgent | children_under_5, pregnancy, elderly | A |
| malnutrition | urgent | moderate_malnutrition_mam | A |
| measles | urgent | unvaccinated, moderate_malnutrition_mam | A |
| mpox | urgent | immunocompromised, hiv_positive | A |
| neonatal_infection | emergency | preterm_birth | A |
| pneumonia_children | urgent | moderate_malnutrition_mam, hiv_positive | A |
| tuberculosis_suspected | urgent | hiv_positive, immunocompromised, elderly | A |
| typhoid_fever | urgent | children_under_5, pregnancy | A |
| vhf_suspected | emergency | healthcare_worker | A |
| yellow_fever | emergency | unvaccinated, elderly | A |

### Recommendation: **Option A (accept the no-op, document explicitly) for all 31**
Rationale:
1. The urgency tier is already at or above where the modifier would push it. There is nowhere
   clinically appropriate to escalate to without entering the safety layer (→ emergency), which is
   out of scope and would be wrong — e.g. a pregnant woman with cholera is already `emergency`; an
   HIV-positive TB suspect at `urgent` should not auto-jump to `emergency` absent a danger sign.
2. Option B is a no-op on this set (see above); Option C (remove) discards a real clinical signal.
3. **These modifiers retain value even when the tier doesn't move:** they mark genuine risk
   factors (pregnancy, HIV, MAM, preterm) that (a) should drive the explanation-template wording,
   (b) are the natural hook if scoring becomes weighted rather than tiered later, and (c) document
   known higher-risk sub-populations. Removing them loses that.

**Do not treat "no-op" as "useless."** The recommendation is to **document** the behaviour (a note
in the KB metadata or schema docs stating that `increase_urgency` on an urgent/emergency default is
an intentional clinical-signal marker that does not change the tier), not to change data.

**Two worth a closer clinical look (still Option A, flagged):** `pneumonia_children +
moderate_malnutrition_mam` and `malnutrition + moderate_malnutrition_mam`. MAM genuinely raises
deterioration risk; both are already `urgent`, and the real safety net is the **SAM**
`escalate_emergency` path plus red flags. Confirm the team is comfortable that MAM (not SAM) stays
`urgent` here — consistent with the E7 SAM/MAM split decision.

---

## Item 3 — Headache condition token reachability (Issue #8)

### Current state
`headache` condition symptoms: `head_pain`, `throbbing_headache`, `pressure_headache`,
`one_sided_headache`. The literal `headache` token is **not** among them. Conditions that **do**
carry the literal `headache` token: malaria (6), typhoid_fever (5), lassa_fever (5), yellow_fever
(5), hypertension (5). So a user reporting generic "headache" routes to one of those — most often
hypertension (for an isolated headache) or malaria (if fever is also present) — never to the
`headache` condition itself.

### Safety net check — this is NOT a hard safety hole
The meningitis red flag `neck_stiffness_fever` is reachable regardless of which condition wins:
`rf_104` (malaria/csm/typhoid), `rf_125` (ear_infections), `rf_127` (fever_unknown), `rf_153`
(headache). So a headache-with-neck-stiffness-and-fever presentation still escalates to emergency
even if the top condition is malaria rather than headache. The reachability gap is a **scoring/
routing accuracy** issue, not a missed danger sign.

### Recommendation: **Option A (add the `headache` token to the headache condition)**
Rationale:
- "Headache" is the most common lay term; the condition named for it should be reachable by it.
- Adding it routes generic headache to the condition with the most relevant **explanation template**
  and its own red-flag set, rather than to hypertension's or malaria's framing.
- The token already exists in `token_dictionary.ng.v1.1.json`, so this is valid with no dictionary
  change. Low risk.

**Calibration caveat (important):** the assigned weight matters. Set it **modest** (suggest 6, in
line with `head_pain`) so that generic headache reaches the headache condition when it appears
**alone**, but does **not** outweigh malaria when `fever`/`chills` are also present (malaria's
fever 9 + chills 7 should still win a febrile headache). This preserves the correct febrile-headache
→ malaria routing while fixing the isolated-headache case. Recommend validating with a few added
case-bank cases (`headache` alone; `headache + fever`) after the change.

**Proposed change:** add `{ "token": "headache", "weight": 6 }` to `headache.ng.v2.0.json` symptoms
(and mirror into `kb.ng.v2.x`). Note the near-duplicate `head_pain`/`headache` pairing already
flagged in the E9 token map — both would map to this condition, which is fine.

---

## Summary of recommendations

| Item | Issue | Recommendation | KB change proposed? | Needs clinical review? |
|---|---|---|---|---|
| 1 — malaria base_weight | #38 | **A (keep 10)**; 9 acceptable; not 8 | Only if 9 chosen | Low — scoring prior |
| 2 — increase_urgency no-op | #36 | **A (accept + document) ×31** | No (docs only) | Confirm MAM cases |
| 3 — headache token | #8 | **A (add token, weight 6)** | Yes, 1 token | Low — validate routing |

**Net:** at most two small data changes (malaria base → 9 *if* chosen; add `headache` token), plus a
documentation note for Item 2. None touches red flags or urgency priorities. All await engineering-
lead approval before implementation, per E8.2 process.
