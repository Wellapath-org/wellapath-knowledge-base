# Progress Log — wellapath-knowledge-base

Last updated: 2026-08-15

## Merged

| PR | Branch | Summary |
|---|---|---|
| #2 | `feat/e5-facility-locator-data` | E5 facility locator data: `facilities.ng.v1.0.json`, source research, cleaning log, GRID3/HOTOSM source CSVs. |
| #3 | `feat/e7-full-kb-expansion` | E7.1/E7.2: full 50-condition `kb.ng.v2.0.json` and expanded `rules.ng.v2.0.json` (red flag rules for all 50 conditions). Individual `conditions/*.ng.v2.0.json` files (E7.3) added in a follow-up commit on the same PR. |
| #4 | `feat/e7-medical-review-fixes` | Medical reviewer fixes: `token_dictionary.ng.v1.1.json` (new `moderate_malnutrition_mam` token), SAM/MAM modifier split, diabetes DKA symptoms, hypertension severe tier fix in `kb.ng.v2.0.json`; new hypertension/Ludwig's angina rules, RTI `rf_147` bug fix, `rf_101` extended to diabetes in `rules.ng.v2.0.json`. |
| #5 | `feat/e7-version-bump-v2-1` | Version bump: `kb.ng.v2.1.json` / `rules.ng.v2.1.json` (`_metadata.version` → "2.1") reflecting the merged medical review fixes. |
| #6 | `feat/e7-red-flag-mirror-fix` | Mirrored new red flag tokens (hypertensive emergency, Ludwig's angina, diabetes extension) into `conditions/hypertension.ng.v2.0.json`, `conditions/diabetes.ng.v2.0.json`, `conditions/dental_oral.ng.v2.0.json`, and `kb.ng.v2.1.json`. Also added `kb.ng.v2.2.json` (version bump) in a later commit — **see Known Issues below, this file did not make it into `develop`.** |
| #7 | `feat/case04-malaria-explanation` | Case 04: updated malaria `explanation_template` with clinical-reviewer-approved under-5/rainy-season wording. Regenerated `kb.ng.v2.3.json` (all 50 conditions, version 2.3). SHA256 reported to engineering lead for R2 verification (not yet uploaded). |
| #10 | `docs/progress-log` | Added this progress.md file. |
| #11 | `feat/lagos-hfr-phone-enrichment` | Applied 45 verified Lagos facility phone numbers (`source/lagos_facility_phone_enrichment_v1.csv`, matched by `facility_id`) to `facilities.ng.v1.0.json`. Saved as `facilities.ng.v1.1.json` (v1.0 left untouched), phones normalized to `+234` E.164 format. 45/45 matched, 0 unmatched. SHA256 reported to engineering lead for R2 verification (not yet uploaded). |

## Open

| PR | Branch | Summary | Status |
|---|---|---|---|
| #9 | `feat/e9-symptom-token-mapping` | Issue #25 (E9 beta blocker): data engineer deliverable — `mobile_handoff/symptom_display_body_area_map.csv`/`.json` (all 164 symptom tokens → display name → body area, 61 flagged ambiguous) and `condition_top5_symptom_tokens.json` (top-5-by-weight tokens for all 50 conditions). Awaiting mobile engineer's `symptom_display_map.dart` expansion on `feat/e9-symptom-picker-expansion`. | Open, awaiting review/merge |

| Issue | Title | Status |
|---|---|---|
| #8 | `chore(kb): resolve headache condition token reachability gap` | Open, `task` label. Found by medical reviewer during E7 verification: `headache` condition has no literal `"headache"` symptom token, so it's rarely reached (users match `hypertension`/`malaria` instead). Decision needed at E8 calibration: add the literal token (Option A) vs. document as intentional (Option B). |
| #25 | E9 symptom picker — 11% token coverage, 19 conditions unreachable | Blocking E9 beta. Data engineer part delivered via PR #9. Mobile engineer part (`symptom_display_map.dart` expansion, prioritizing the 19 unreachable conditions) still pending. |

## Facility Data (v1.x manual enrichment vs. v2.0 NHFR rebuild)

- **Decision (2026-07-26):** ship the 45 phone-matched Lagos facilities as `facilities.ng.v1.1.json` now; treat manual enrichment as the interim v1.x strategy, with a future NHFR API integration as the v2.0 rebuild path.
- **NHFR in-portal API request (hfr.fmohconnect.gov.ng):** retry was **not submitted** — WellaPath's organization domain isn't verified yet and a personal email was not used as a substitute. Still outstanding; needs a proper org domain/email before resubmission.

## Known Issues

- **`kb.ng.v2.2.json` is missing from `develop`.** It was committed to `feat/e7-red-flag-mirror-fix` (commit `a4d9c5d`) after PR #6 had already been merged (merge commit `8bc622b`'s second parent is the earlier `2a8ffaf`, not `a4d9c5d`). The file exists on the remote branch but was never folded into mainline. `kb.ng.v2.3.json` (PR #7) was regenerated directly from the 50 `conditions/*.json` files, so it isn't affected by this gap, but the `v2.2` artifact itself needs to be recovered or intentionally abandoned.
- **Symptom vocabulary has zero "Arms"-specific tokens** (flagged in PR #9) — the body-diagram picker has an Arms zone with nothing to route to it under the current 164-token set.
- **61 of 164 symptom tokens are ambiguous** for lay users (no body location, near-duplicate tokens, or unexplained clinical jargon) — see `mobile_handoff/symptom_display_body_area_map.csv` for the full list and reasoning.

## I2 / W2 — Symptom Vocabulary 2.0 foundation (Step 1)

Branch `feat/i2-w2-vocabulary-schema-foundation`. Contract-defining step: schema,
migration, validators, case-bank baseline and downstream contracts, so Backend and
Mobile stop guessing. **Nothing published, nothing clinically approved.**
Full write-up: `docs/I2_W2_VOCABULARY_FOUNDATION.md`.

- **Baseline frozen from committed bytes** — no frozen artifact re-serialized or
  rewritten. `token_dictionary` 1.1 · `kb` 2.4 · `rules` 2.2 · `facilities` 1.1 ·
  `case_bank` 1.0, all five hashes matching the E9.1 freeze. 295 tokens, 240
  referenced, 55 unused, 0 duplicate normalized labels, 0 ID-format violations.
  `reports/baseline_freeze_v1.json`, `reports/token_reference_graph_v1.json`.

- **Candidate artifact** `candidate/token_dictionary.ng.v2.0.json` — schema 2.0,
  artifact 2.0, SHA256 `07f93596…`, `release_status: candidate_unapproved`.
  295 → 295 tokens: zero added, removed, renamed, merged or deprecated. Generated
  by `tools/build_vocabulary_v2.py`; the downgrade projection rebuilds
  `token_dictionary.ng.v1.1.json` byte for byte from the new `tokens[]` alone,
  asserted at build time and in tests.

- **Backward compatible, measured not assumed.** The shipped mobile engine reads
  exactly two keys of the token dictionary (`symptom_tokens`, `red_flag_tokens`,
  in `red_flag_evaluator.dart`); both are byte identical, so the current build
  loads the candidate with **no code change**. All six legacy arrays unchanged;
  everything new sits under keys a schema 1.0 reader never touches.

- **Aliases can never be scored** — structurally, not by convention. An alias is a
  string inside `search.aliases` with no `token_id` and no `scoring_eligible`
  flag. Ambiguous input returns candidates with `resolved_token_id: null` and
  `scoring_eligible: false`. No fuzzy, prefix or substring matching anywhere, so
  `no fever` cannot reach `fever`.

- **Case bank: it was never missing.** The canonical 239-case bank is committed
  here at `testing/case_bank_v1.json` (v1.0, `c7bdc434…`, provenance `ba7815e` →
  `c974100`). What is missing is a copy at the *mobile* repo's default fixture
  path `test/fixtures/case_bank_v1.json` — a cross-repo distribution gap, not
  absent data. Mobile's harness skips rather than fails, by design. Copy command
  in `mobile_handoff/vocabulary_v2/README.md` §9.
  **Harness ready · data available · clinical approval NOT recorded · regression
  result STALE** (last run 234 cases against kb 2.3; bank is now 239 and the
  freeze is kb 2.4). Top-50 behaviour is proven unchanged *structurally* — every
  clinical input is byte identical — **not** by an executed run. Not certified.
  `reports/case_bank_status_v1.json`.

- **Checks:** `python3 tools/run_w2_checks.py` — 11 groups green: 45 content
  validators, 26 compatibility checks, 91 unit tests, plus staleness checks on
  every generated file so a hand-edit turns CI red. Standard library only, no
  network. CI: `.github/workflows/w2-vocabulary-validation.yml`.

- **Diff classification:** `search_only_metadata` only, no blocking class. A clean
  classification is *not* an approval — `reports/baseline_diff_v1.json` carries
  `publication_decision.may_publish: false`.

- **Live `/config` manifest unchanged.** No file in `wellapath-backend` or
  `wellapath-mobile` was modified. Nothing uploaded to R2.

### New in this repository

`schema/token_dictionary.v2.schema.json` · `schema/token_dictionary_schema_v2.0.json` ·
`tools/vocab/` + 10 generators/validators · `candidate/` · `reports/` ·
`testing/vocabulary/` (91 tests, 45 search fixtures, 21 invalid fixtures) ·
`docs/VOCABULARY_*.md` · `templates/vocabulary_expansion_request.template.json` ·
`mobile_handoff/vocabulary_v2/` · `backend_handoff/vocabulary_v2/`

### Blocked on clinical / product input

1. **Approved alias & label catalogue.** None exists, so every optional metadata
   field ships empty — no alias, body area, complaint group, severity/duration
   descriptor or reviewer name was invented. Recommended first batch: promote the
   already-merged `mobile_handoff/red_flag_display_map.json` labels and body areas
   for the 12 global red-flag tokens, with clinical sign-off on each label.
2. **Case bank v1.0 clinical sign-off**, or an explicit decision that
   engineering-lead approval is the accepted bar. The case-bank schema has no
   reviewer field at all.
3. **Three IMCI severity tier keys** (`pneumonia`, `severe_pneumonia`,
   `very_severe_disease`) used by `pneumonia_children.severity_levels` do not
   resolve against `token_dictionary` 1.1, and `kb_schema_v1.0.json` contradicts
   itself about whether they should. Pre-existing; assessed as behaviourally
   inert (no engine path resolves a tier *key*); **not fixed here** — both
   remedies touch frozen artifacts. Recorded in
   `reports/baseline_freeze_v1.json` → `known_baseline_findings`.
4. **`breathlessness` → `shortness_of_breath` alias proposal** (PR #24). Both are
   live scoring tokens, so this is a `clinical_token_identity` change, not a
   search tweak.
5. **239-case regression re-run against kb 2.4** (mobile engineer). Does not block
   W2 Step 1, which publishes nothing; does block any later vocabulary change
   classified beyond search-only metadata.

## I2 / W2 Step 3 — CB_211 / CB_232 adjudication

Branch `feat/i2-w2-cb211-cb232-adjudication`. Evidence and disposition for the
findings from the Mobile 239-case run (PR #71 @ `04dcf75`, base `678e300`,
against token_dictionary 1.1 / kb 2.4 / rules 2.2 — 239 executed, 235 passed,
1 failed, 3 human-review, **0 safety-critical under-triage**).
**No clinical ruling made. Mobile PR #71 stays unmerged.**

- **CB_211 — provenance proven, and the key document is not missing.** The
  expectation was hardcoded in `testing/build_case_bank.py:174-177` at `ba7815e`
  (PR #13) and never touched since, with the note *"matches E3.5 Case 12
  behaviour"*. **E3.5 Case 12 is a live test**, not a lost spec:
  `wellapath-mobile test/engine/pilot_case_validation_test.dart:422-439`
  (commit `b34cfb8`, 2026-05-18). It asserts the engine must not crash and that
  urgency is **any one of the four valid values — `urgent` explicitly included**.
  It never mentions `empty_default`. So the engine *conforms* to the cited
  source; the case bank narrowed a deliberately permissive assertion and invented
  a source value.

- **`empty_default` never existed.** Verified across all 5 historical revisions
  of `urgency_determiner.dart` (`e20f45a`, `51afd89`, `7aeb13c`, `cfe1a25`,
  `33a214e`) and every commit under `lib/`: the engine has only ever emitted
  `global_red_flag`, `condition_specific_red_flag`, `demographic_escalation`,
  `urgency_default`. Not a removed value — a value that was never implemented.

- **Prior-run claim verified from committed evidence.** The identical mismatch
  is in `testing/case_bank_results_v1.json` (234-case run, kb **2.3**) in three
  places, byte-identical in every field. Recomputing CB_211 against kb 2.3 and
  kb 2.4 gives the same result — **nothing regressed**. Tracked as
  **wellapath-mobile issue #35** (OPEN), which carries its own open question to
  the lead.

- **Provisional engineering classification: `obsolete/stale case-bank
  expectation`** — same conclusion Mobile reached, now grounded in the primary
  artifact rather than a characterisation of it. Refinement worth keeping: this
  is an **authoring-time over-constraint, not drift** — nothing was superseded,
  so there is no earlier contract to restore. **Engineering classification only;
  no clinical approval claimed or implied.**

- **Reachability:** unreachable in product behind two tested guards —
  `symptom_selection_screen.dart:83/250` (Continue disabled) and
  `loading_screen.dart:71` (blocks before the engine). Reachable only by direct
  engine invocation, which is what the case bank and
  `engine_wiring_test.dart:218-229` do. Over-triage, not safety-critical, cannot
  suppress a red flag (no tokens → no rule can match) and cannot change any
  non-empty assessment.

- **CB_232 — no tie, no tie-break, no regression.** malaria 26 vs
  acute_diarrhoea 21, **margin 5**, one condition at top. Malaria leads on
  symptom subtotal alone (`fever:9 + chills:7 = 16` vs `watery_stool:8 +
  vomiting:5 = 13`) before its base weight of 10 is counted. Ranking and every
  score are **identical between kb 2.3 and kb 2.4**. Not a safety concern
  (urgency `urgent` is the conservative of the two candidates). The
  mixed-presentation question it raises is the existing **Issue #38**
  (malaria base_weight), not a new finding. CB_225 and CB_233 reproduced too.
  Noted separately: the engine has **no documented tie-break**, and Dart's
  `List.sort` is not stable — irrelevant to CB_232, but real for a future tie
  between conditions with different urgency defaults (cf. CB_239's recorded tie).

- **Proposed known-findings contract** (`testing/known_findings.json` +
  `docs/KNOWN_FINDINGS_CONTRACT.md`) — **not wired into Mobile.** A registered
  finding is a *pinned observation, never a suppressed failure*: the case still
  executes, its exact observed output is asserted, and the run fails if anything
  deviates — including an unexplained improvement. Follows the existing
  `KNOWN_BASELINE_FINDINGS` precedent in `tools/report_baseline.py`.
  `tools/validate_known_findings.py` (22 checks) enforces that the registry
  quotes the case bank accurately, still matches reality, genuinely disagrees
  with the expectation, claims no clinical authority, and carries an expiry.

- **Checks:** `python3 tools/run_w2_checks.py` now runs **13** groups, all green.
  Case bank, results file and generator are byte-identical; all four frozen
  artifacts unchanged; candidate still `candidate_unapproved` / `may_publish:
  false`; live manifest still on token_dictionary 1.1.

### Engineering disposition (Step 3A) — Option D adopted

The engineering lead adopted **Option D**: CB_211 is preserved byte-for-byte and
registered as an explicit, unresolved, **fail-closed** known discrepancy. It must
execute on every regression run, its exact observed result is asserted, it is
**never counted as passed**, and any change in its observed behaviour — or any
additional case mismatch — fails the run. Recorded in
`testing/known_findings.json` as `engineering_disposition: option_d_adopted`,
enforced by `tools/validate_known_findings.py` (28 checks).

**Options B and C are deferred** for clinical/product adjudication **before
external beta**. CB_232 requires no scoring, KB, case-bank or tie-break change.

This is an **engineering** disposition only — not clinical approval, not
external-beta approval, not production approval. **CB_211 remains unresolved.**

### Still open

1. **CB_211 final resolution** — B (correct the expectation in a **new versioned**
   bank; v1 is immutable) vs C (engine-level empty-input result, issue #35's own
   question). Needs clinical input on whether `urgent` + a fabricated malaria
   differential is acceptable for empty input. **Due before external beta.**
2. Case bank v1.0 clinical sign-off — still absent, still no schema field for it.
3. Issue #38 — malaria base_weight in mixed presentations; CB_232/CB_225 are
   worked examples for that monitoring item.
4. No documented tie-break in the scoring engine (new, low priority).

---

# I2 / W2 Step 5 — Vocabulary 2.0 Clinical/Product Catalogue Review Package

**Branch:** `feat/i2-w2-catalogue-review-package` (off `develop` `550e8f17`)
**Date:** 2026-08-15

## Status: review-ready — nothing approved, nothing publishable

Builds the package clinical and product reviewers need to decide the Vocabulary
2.0 catalogue item by item. **Every decision is `pending`, all 25 proposals are
publication-blocked, and the candidate artifact is byte-identical** to the one
merged at `dceecde2` (`07f93596…4e34cd2d`).

## What was produced

| Artifact | Contents |
|---|---|
| `review/catalogue_v1/catalogue_review_v1.json` | 25 proposals, 8 batches |
| `review/catalogue_v1/display_label_review_v1.json` | review rows for **all 295** tokens |
| `review/catalogue_v1/impact_report_v1.json` | counts by class, section, batch, state |
| `review/catalogue_v1/risk_summary_v1.json` | blockers and carried-forward issues |
| `schema/catalogue_review.schema.json` | proposal + decision contract |
| `tools/build_catalogue_review.py` | deterministic generator, `--check` mode |
| `tools/validate_catalogue.py` | fail-closed validators |
| `testing/test_catalogue_review.py` | 57 checks incl. the pending dry run |
| `docs/VOCABULARY_CATALOGUE_GOVERNANCE.md` | governance workflow |

Inputs are committed and provenance-bearing; Mobile display labels are vendored
(`proposals/catalogue_v1/mobile_display_labels.vendored.json`) so the generator
never reads another repository at build time.

## Proposals

| Primary class | Count |
|---|---|
| `display_label_only` | 8 |
| `red_flag_affecting_association` | 12 |
| `clinical_token_identity` | 1 |
| `insufficient_evidence_do_not_propose` | 4 |

9 affect scoring · 12 affect red flags · 13 ambiguity sets · **0 normalization
collisions** · **0 publication-eligible**.

## The nine picker scoring-gap tokens (PR #24)

All nine **already exist** as canonical symptom tokens in v1.1 and already carry
kb weight; none is reachable from the Mobile picker. So eight are
`display_label_only` — a reachability gap, not new vocabulary. No new token is
needed for any of them.

The ninth is not: `breathlessness` → `shortness_of_breath` is proposed as an
alias, but both are existing canonical scoring tokens —
`breathlessness` carries `lower_respiratory_infection` (7), `shortness_of_breath`
carries `sari` (9), `asthma` (8), `cardio_symptoms` (7). Mapping one to the other
changes reachability across four conditions, so it is classified
**`clinical_token_identity`**, is publication-blocked, and **is not implemented**.
Both tokens remain independent and active.

## Roadmap examples

The four example complaints carry **no repository provenance** — a search found
no committed roadmap document containing them. Each is recorded as
`insufficient_evidence_do_not_propose` with its lost context named; **no
canonical token is assigned to any of them.**

## Local-language gap: OPEN

No authoritative Hausa/Yoruba/Igbo/Pidgin source exists in this repository. **No
local term was generated, translated or inferred.** A sourced catalogue is
required before any non-English content can be proposed.

## Verification

`python3 tools/run_w2_checks.py` — **all 16 checks pass** (13 pre-existing plus
3 new). Generation is byte-reproducible; the validator recomputes publication
eligibility and fails if a stored value disagrees. A control test proves the
eligibility gate is a real gate: a fully approved, low-risk, fully-provenanced
item *does* become eligible.

Dry run with all decisions pending: zero eligible proposals, candidate hash
unchanged, alias count 0, association count 0, `display_safe` false for all 295,
`release_status` still `candidate_unapproved`.

## Still open (unchanged, none repaired here)

1. **CB_211** — Option B vs C, due before external beta.
2. **Case bank v1.0 clinical sign-off** — still absent.
3. **Issue #38** — malaria base_weight in mixed presentations.
4. **No documented tie-break** — CB_232's margin was 5, so none was exercised.
5. **Three IMCI tier keys** — `pneumonia`, `severe_pneumonia`, `very_severe_disease`.
6. **`breathlessness` vs `shortness_of_breath`** — decision required.

## I2 / W3 Step 1 — Adaptive Question Engine 2.0 contract

Branch `feat/i2-w3-question-flow-contract`. Contract-defining step: freeze the
existing question flow, define a versioned schema, project the current behaviour
into a candidate, and hand Mobile an exact contract. **Nothing published, nothing
approved, no Mobile or Backend file touched.**
Full write-up: `docs/W3_QUESTION_FLOW_CONTRACT.md`.

- **Headline finding: there is no question artifact.** The whole flow is Dart
  source in wellapath-mobile — 18 token keys and 40 authored questions in
  `followup_question_map.dart`, 3 red-flag clarifiers, one static engine class,
  five screens and a controller. No version, no hash, no `/config` entry, and no
  rollback independent of an app release. Six source files are vendored into
  `baseline/questions_v1/` and hashed so the baseline is pinned to real bytes.

- **Frozen baseline** (`reports/question_baseline_freeze_v1.json`): 44 question
  definitions, 6 demographic questions, 154 answer options, 3 red-flag-affecting,
  18 scoring-affecting, 121 picker-reachable tokens, 140 referenced tokens,
  **0 unresolved references**, 0 dead options, enforced path limit 5.

- **Eleven defects recorded, none repaired.** The important one is **QB-002**:
  red-flag clarifier answers are **not evaluated when answered** —
  `_commitAnswers()` runs only after the last follow-up question, so a "yes"
  does not interrupt and the red flag is evaluated once, in the engine, after
  every question has been shown. Also QB-005 (question wording depends on the
  order symptoms were tapped), QB-006 (truncation is applied after clarifiers
  are prepended; no clarifier is dropped today only because there are three),
  QB-003 (no re-branching on newly derived tokens), QB-011 (123 picker labels
  onto 121 tokens).

- **Candidate** `candidate/question_flow.ng.v1.0.json` — schema 1.0, artifact
  1.0, `candidate_unapproved`, `may_publish: false`. **50 questions, 300 answer
  options.** Zero added, removed or reworded; zero answer meanings or token
  effects changed; token output universe identical.

- **Parity is claimed honestly.** Six impedance mismatches are recorded in the
  artifact itself, and `parity_claim` says **"NOT identical"** — a test enforces
  that it keeps saying so. IM-002 (immediate red-flag evaluation) is
  clinically substantive and in the safe direction: **earlier, never later**.
  IM-001 replaces the selection-order dependence with a declared tie-break.
  Neither is implemented in Mobile here.

- **Condition language:** 13 operators, 4 readable fields, closed and finite.
  No expression parser, no scripting, no regex over clinical free text, no
  network, no fuzzy or probabilistic branching. Fail-closed throughout: unknown
  operator or field is an error, not `false`; unknown sex/pregnancy/age makes a
  condition false, so a gated question is not asked rather than wrongly asked.

- **Red-flag precedence** is structural: every red-flag-affecting question
  declares immediate evaluation and blocks the next question, a validator fails
  if any does not, and a second fails if the declared hook disagrees with the
  computed effect. Truncation exemption is a schema **constant** — if red-flag
  questions exceed the limit, the limit yields.

- **Path controls:** limit 5 measured from the implementation, distribution
  measured over 2,325 explored paths (max 5, min 1). **No final threshold
  invented** — three bounded options proposed and `final_threshold_status` reads
  PENDING product and clinical approval.

- **Checks:** `python3 tools/run_w2_checks.py` now runs **22** groups, all green
  — including 34 question-flow validators, 26 compatibility checks and 81
  question-flow tests. 18 path scenarios + 3 edit scenarios; **23/23 invalid
  fixtures** trip their named check. Exploration bound is declared, not glossed:
  exhaustive over token subsets up to size 3, with the uncovered space stated.

### Blocked on clinical / product input

1. **IM-002 — immediate red-flag evaluation.** Safe direction, real behaviour
   change. Engineering lead + clinical.
2. **Question wording approval** — all 50 are `content_approved: false`.
3. **Final path-length threshold** — three options proposed, none approved.
4. **Whether any question may become skippable** — none is today.
5. **QB-009** — the `0-12` age band maps to `children_under_5`, so a
   6-to-12-year-old is tokenised as under-5; `children_under_15` is unused.
   Pre-existing, not changed here.
6. **Distribution model** — the flow is compiled into the app. Serving it as an
   artifact needs a `/config` entry, a download path and last-known-good
   fallback, none of which exists.

### W3 Step 1A — dispositions recorded, full impedance disclosure

Engineering-lead dispositions recorded in the candidate as
`_metadata.engineering_dispositions`, enforced by 20 new fail-closed validators.

- **Correction: there are SEVEN impedance mismatches, not six.** The artifact
  always recorded IM-001 through IM-007; the PR description and contract doc
  said "six". The artifact was right and the prose was wrong — now corrected,
  and a validator asserts the enumerated list so a mismatch cannot be added
  without being disclosed.

- **Correction: IM-003 was under-classified.** It was recorded as "not
  clinically substantive — can only ask more questions". Measured: newly
  triggerable severity and duration questions produce tokens that carry **no**
  kb weight and are **not** red-flag relevant, but newly triggerable
  *additionalSymptoms* questions **do** affect scoring — they give the user
  further chances to declare symptoms, which can change the token set and
  therefore the top condition. Verified separately that **no** additionalSymptoms
  option anywhere is a clarifier trigger token, so re-branching **cannot** raise
  a red-flag clarifier that does not fire today. IM-003 is now classified
  path-affecting, marked an activation blocker and **deferred**.

- **Dispositions:** IM-001 adopted (ordering `(priority, tie_break_key,
  question_id)`, regression evidence required before activation); IM-002 adopted
  as a **required safety correction**; path limit **fixed at 5**; optional skips
  **deferred** (candidate has zero); distribution **compiled-in / default-off /
  internal only**, served distribution deferred to I3; wording preserved
  byte-for-byte **without approval**. Every disposition states what it does
  **not** authorize. Production, public-beta, external-beta, clinical and
  product approval all **false**.

- **QB-002 reproduced and measured** (`reports/qb002_evidence_v1.json`): a
  clarifier answered "Yes" is followed by up to **4 further ordinary questions**
  before the engine ever sees the red-flag token. `_commitAnswers()` runs only
  on the last question. Scoring **cannot** override the eventual red flag —
  `ScoringEngine.score` throws when `proceed_to_scoring` is false. So this is not
  an under-triage defect; the harm is abandonment before the result. Earliest
  safe interception point identified: `_onNext`, in the advance branch, before
  `setState` and before the step-view event.

- **Mobile IM-002 handoff** (`mobile_handoff/question_flow_v1/IM002_SAFETY_FIX.md`)
  — the safety fix only, not the adaptive engine. 12 regression cases, telemetry
  must not become a red-flag oracle, default-off flag for rollback.

- No clinical-content change: question wording byte-identical (27 texts), token
  output universe identical (139 tokens), 50 questions / 300 options unchanged.
  Checks now **23 groups**, all green; 53 question-flow validators; 103 tests.

## I2 / W3 Step 4 — Reconcile the question candidate with live de-duplication

**Status: parity achieved, activation still blocked.** Candidate 1.1 and schema
1.1 are unpublished, clinically unreviewed and consumed by no build. Candidate
1.0 and schema 1.0 are retained unmodified.

- **The blocker from Step 3 is cleared.** Candidate 1.0 planned a different
  question SET on 1,930 of 2,325 paths because it modelled one question per
  token per role while the live engine de-duplicates. Candidate 1.1 models the
  grouping and is now **identical to real live output on 2,325 of 2,325 paths** —
  0 question-set, 0 order, 0 wording, 0 option-set, 0 option-order, 0
  token-effect, 0 red-flag, 0 truncation differences, 0 red-flag questions
  dropped, path limit never exceeded.

- **Measured against the real Dart engine, not a reimplementation.** The oracle
  (`testing/questions/fixtures/oracle/`, 4,625 cases, 4.0 MB) is the actual
  output of `QuestionEngine.generateQuestions` at Mobile `657739cc`, captured by
  running it. A model compared against itself would have proved nothing.

- **IM-001 is narrowed to what it always should have been.** It no longer changes
  which questions are asked, only which of two existing wordings is shown where
  the baseline has no stable answer. Under reversed selection order the live
  engine **disagrees with itself on 1,680 of 2,300 paths**; the candidate is
  unstable on **0**. 1.0's superseded IM-001 statement — which called it
  `path_affecting: false` before measurement showed otherwise — is carried in the
  record rather than overwritten.

- **Two defects found by measurement, not by reading code.** GF-006: 1.0's
  default-duration trigger fired on the empty selection and missed
  `{chest_indrawing_severe, boils}` — two mapped tokens have no duration entry.
  GF-008: every clarifier had priority 0, so ordering fell to the tie-break key,
  i.e. alphabetical; `kRedFlagClarifiers` is not alphabetical, so the first and
  third clarifier swapped on 168 paths. **Declaration order was already stable —
  removing nondeterminism elsewhere is not a licence to reorder deterministic
  output.**

- **Two defects in my own tooling, corrected rather than worked around.** The
  parity comparator derived option labels by splitting option ids and reported
  1,249 false differences (`::yes` is not `Yes`). The containment check posed
  `source AND NOT question` to `is_never_satisfiable`, which cannot discharge it,
  and flagged all 40 sources; it now decides containment **exactly** by
  enumerating the referenced token subsets, and refuses above 20 tokens rather
  than approximating.

- **Schema 1.1 is computed from 1.0, not hand-written.** `additionalProperties:
  false` on a question made grouping inexpressible under 1.0. The generator loads
  1.0, adds `$defs.grouping`, `$defs.groupSource`, `question.grouping`,
  `metadata.grouping_semantics` and `pathControls.grouping_phase`, and re-proves
  additivity on every run — refusing to write if any required field, enum value
  or const was narrowed. One constraint widened: `schema_version` from
  `const "1.0"` to `enum ["1.0","1.1"]`.

- **Grouping is declared, not inferred:** `group_key` (distinct from
  `tie_break_key`, which orders and never groups), `merge_strategy`,
  `representative_selection` = `lowest_source_order_index`, `option_union_rule`,
  `conflict_resolution`, and 40 explicit `sources`. Red-flag clarifiers are
  **prohibited** from grouping. Grouping runs **before** truncation.

- **Guards:** 10 grouping checks, all passing; **22 invalid fixtures, 22
  rejected by the intended check** (rejection by a different check counts as a
  failure). The existing 53-check validator passes on 1.1 **and** still passes
  unchanged on 1.0. `tools/run_w3_grouping_checks.py` — 18 checks, 0 failed.

- **Coverage beyond the oracle is labelled honestly.** The Python transcription
  was first validated against all 4,625 real cases (0 mismatches) and only then
  used to reach sizes 4 and 5: 53,130 further paths, 0 differences on every
  dimension. That evidence is **model-derived and marked as such** — weaker than
  live output, and not presented as it.

- **Nothing clinical moved.** kb 2.4, rules 2.2, token dictionary 1.1 and 2.0,
  candidate 1.0 and schema 1.0 all verified byte-unchanged. No question added,
  removed or reworded; no answer meaning, produced token or red-flag rule
  changed; IM-002 timing untouched; IM-003 not implemented; path limit still 5.

- **Activation remains blocked** on product sign-off for representative wording,
  unapproved content, absent clinical review, and publication — not on path
  content, which is now measured at zero change.

### Step 4A — final verification before merge

Verification found **two defects in the Step 4 work itself**, both fixed before merge.

- **Schema 1.1 was not additive.** `grouping_semantics` had been added to
  `_metadata.required`, so candidate 1.0 no longer validated under 1.1 — exactly
  what an additive extension may not do. The additivity guard had missed it
  because it only checked that 1.0's constraints *survived*, never that new ones
  were *added*. The guard now rejects a grown `required`, a changed `const` and
  any new restricting keyword, and is **mutation-tested against all three**. The
  requirement itself moved to where it belongs — the artifact version, enforced
  by validator check G01, proven by the `grouping_semantics_absent` fixture.
  Compatibility is now proven twice, structurally and behaviourally: candidate
  1.0 validates under both schemas, candidate 1.1 is correctly refused by schema
  1.0, and **23 schema-invalid 1.0 fixtures were re-checked under 1.1 with 0
  newly accepted**.

- **Oracle provenance was incomplete.** The capture used a temporary Mobile test
  that was deleted and is committed nowhere. `tools/validate_oracle_provenance.py`
  now re-derives the bounded enumeration, input ordering, reversed-case rule,
  field sets, role vocabulary and question limit **from first principles** —
  none of it read from the fixture's own metadata — and pins the fixture in a
  **sidecar** record, so captured evidence is never edited to describe itself.
  The reproduction harness is recorded in the KB and explicitly **not** claimed
  to be byte-identical to the deleted test; the fixture's authenticity rests on
  the structural re-derivation plus the independent 4,625-case transcription
  match, not on that file.

- **The PHI scan's first revision was wrong in both directions.** It reported 27
  "phone numbers" that were fragments of the candidate 1.0 SHA256, and flagged
  the token-dictionary schema's own sentence *"No PHI fields — no name, dob,
  phone, email, address"* — the prose forbidding PHI. Patterns were narrowed
  precisely rather than loosened generally, and the scan now carries **9 positive
  and 4 negative controls** so a pattern narrowed into uselessness fails instead
  of passing. 91 files, 0 hits.

- **No clinical or runtime change, computed not asserted:** 33 question texts
  identical · 169 answer labels, none changed in meaning · 139-token output
  universe identical · red-flag effects identical · path limit 5 · zero skips ·
  zero skip sentinels · IM-003 deferred and structurally absent · Vocabulary 2.0
  unused with no alias operator in any condition.

- **GF-006 and GF-008 re-measured against captured output.** GF-006: candidate
  1.0 was wrong on 3 of 6 named cases; 1.1 matches live on all 6, and no duration
  entry was invented for the two mapped tokens that lack one. GF-008: of **248**
  captured paths presenting two or more clarifiers, 1.0's ordering differed from
  live on **168**; 1.1 differs on **0**. The 168 figure is now computed, not
  recalled.

- **IM-001 is now actionable for Product.** `reports/im001_product_review_v1_1.json`
  collapses the 1,680 order-dependent captured paths into **135 distinct wording
  decisions**, each listing the selected wording, the rejected alternatives and
  the paths riding on it. Every wording involved already exists in the live app.
  All 135 are `PENDING`; until they are signed off, IM-001 remains an activation
  blocker regardless of this merge.

`tools/run_w3_grouping_checks.py` — **23 checks, 0 failed**.

## I2 / W3 Step 5B — Mobile IM-001 option-ordering evidence incorporated

Branch `feat/i2-w3-im001-option-ordering`. Mobile PR #75 produced a
non-authoritative addendum decomposing the live option-list instability; this
step verifies it, recomputes every count independently, and creates **one**
global pending Product decision. **No decision approved. No candidate or clinical
artifact changed.** Full write-up: `docs/IM001_OPTION_ORDERING.md`.

- **Provenance verified against Mobile PR #75 head `dd9c6d0`:**
  `docs/evidence/im001_option_instability_addendum_v1.json`, sha256
  `371443cf1914b9870ecdd0a3ebe6838bd7322edd59f827058b1db3635f0e57a3`,
  **1,252,307 bytes** — both matched exactly.

- **Independently reproduced, not copied.** Every count recomputed from this
  repository's captured-Dart oracle and the frozen artifacts;
  `tools/report_im001_option_ordering.py` stores Mobile's figures only to
  reconcile against and never reads them as an input. **All 21 dimensions agree,
  zero unpaired reversed cases.** 2,300 comparisons = 413 identical + 1,665
  wording-and-order + 207 order-only + 15 wording-only. Wording differs on 1,680;
  option ID/label/token-mapping **sequence** differs on **1,872**.
  *(Narrative count corrected from "22" to 21 in I2/W3 Step 6: the
  `reconciliation.detail` table has 21 entries and always did. A prose count
  error only — no evidence array, count, hash, conclusion, candidate or
  decision changed, and every one of the 21 entries still agrees.)*

- **Every clinical dimension is zero** — option ID set, label set,
  option-to-token mapping set, reachable tokens, scoring reachability, red-flag
  reachability, question identity, role sequence, truncation, required/skip. Not
  one token is reachable in one order and not the other. The engine **unions**
  additional-symptom options, and a union is a set operation, so reversing visit
  order changes only the order options are appended in. **Display-order
  instability only.**

- **One decision, not 903.** `IM001-ORD-GLOBAL-001`, type
  `deterministic_option_ordering_rule`, status **pending**, reviewer role
  **Product**, reviewer/date/rationale **null**, activation blocker **true**.
  Bound by SHA256 to a 903-group evidence table
  (`reports/im001_option_order_evidence_v1.json`); a drifted hash fails
  validation. All 903 groups retained with membership, token mappings, path
  counts and per-group classification (`display_order_only` on all 903).

- **Product-only is conditional and enforced.** The generator **refuses to emit
  the decision at all** if any clinical dimension is non-zero, and
  `tools/validate_im001_decisions.py` (51 checks) fails on
  `product_only_classification_is_justified`.

- **One definitional correction recorded.** A first pass defined question
  identity as `(role, question_text)`, reporting 1,680 identity differences and
  correctly tripping the safety gate. That was a defect in the definition, not a
  clinical finding — which wording fills a slot is already the `wording`
  dimension and the subject of the 135 wording decisions. Identity is now
  `(role, red_flag_token)`, which yields 0 and matches Mobile.

- **135 wording decisions untouched** — file byte-identical to develop, all still
  `PENDING`, none merged into the ordering rule.

- **IM-001 remains blocked on 136 Product decisions**: 135 wording selections +
  1 ordering rule. `im_001_resolved: false`.

- **Checks:** W3 grouping suite **25/25**, W2/W3 suite **23/23**, IM-001
  validators **51/51**, content safety **93 files, 0 PHI hits, 0/13 controls
  failed**. Candidate 1.1, candidate 1.0, schema, the wording review and the
  oracle all byte-identical; all frozen clinical artifacts byte-identical; path
  limit still 5; optional skips still 0; IM-003 still deferred.

**Note on repository location:** the working copy moved from
`~/wellapath-knowledge-base` to `~/dev/wellapath-knowledge-base` during this
step. Nothing was lost — the move was verified against the remote and every
frozen hash re-checked.

## I2 / W3 Step 6 — IM-003 dynamic re-branching: impact analysis

**Analysis only. IM-003 is not implemented, not enabled and not approved.** All
9 decisions are `pending`; IM-003 remains
`deferred_pending_product_and_clinical_review` and an activation blocker. No
candidate, schema, question, answer, token effect, red-flag rule, scoring input,
urgency rule or path limit was modified.

**The 56 pairs reconcile exactly, and they are the trigger graph.** Recomputed
from `kFollowupQuestionMap` rather than carried over: 18 nodes, **56 edges**,
declared 56 = recomputed 56. Newly triggerable: 11 severity, 54 duration, 56
additional-symptoms questions.

**Cycles exist and do not mean non-termination — proved, not assumed.** 15
two-cycles, 0 self-loops, max closure 14 tokens, max convergence depth 5. Under
additive-only re-branching the token set is monotone non-decreasing and bounded,
so a fixed point is reached regardless of cycles. Monotonicity is **checked over
every ordered pair of seed tokens**, not asserted. It holds for additive mode
only; removal re-branching is not monotone and is out of scope.

**The safety question, answered across all four pathways.** The earlier IM-003
note relied on clarifier-trigger membership alone, which is the weaker test — a
token can be a danger sign through a global rule or a condition's own
`red_flags` without ever being a clarifier trigger. All 15 newly reachable
tokens were checked against global rules, condition-specific red flags,
clarifier triggers and clarifier red-flag tokens: **0, 0, 0, 0**. Combination-only
red flags cannot exist in the current artifacts — every rule and every condition
red flag keys on a single token.

**What IM-003 does change is scoring input.** All 15 newly reachable tokens carry
KB weight, touching **31 of 50 conditions**. The exact per-condition weight delta
is published.

**What is deliberately not published.** Score, ranked conditions, top condition
and urgency require Mobile's `ScoringEngine`. A Python model was written and
validated against the 239-case bank: **234/239 top conditions, 217/239
urgencies** — it disagrees with the shipped engine on 22 urgencies, so it was
**not used**. Publishing IM-003 deltas from it would have been worse than
publishing none. The exact scoring *input* delta is published instead and the
Mobile harness is specified in the handoff.

**The 239-case bank cannot exercise IM-003.** Every case carries `input_tokens`
— a final token set — and **no answer sequence, no question order**. IM-003 is a
property of the sequence. No sequence was invented and the suite is **not**
claimed to validate adaptive branching.

**Severity and duration tokens are inert today, not permanently.** Zero scoring
weight, zero red-flag references across kb 2.4, rules 2.2, condition red flags,
clarifier triggers and demographic modifiers — a property of the current
artifacts, not of the tokens. Any approval of an inert subset must be
re-validated on every clinical artifact change and enforced by a validator.

**Recommendation: B with conditions, then C separately** — an engineering
recommendation, not approval. The inert subset (severity, duration) and the
scoring-active subset (additional symptoms) carry different risk and must not
share one approval. The split must be **structurally enforceable** — a
generator-computed `rebranch_class`, re-validated on every clinical artifact
change — not a prose convention. No schema change is made here.

**Guards:** 12 fail-closed checks, **18 invalid fixtures, 18 rejected by the
intended check**. The decision package is bound to the impact report's exact
hash, so regenerating the evidence invalidates the decisions.
`tools/run_im003_checks.py` — **21 check groups, 0 failed**.

**Documentation correction.** The IM-001 narrative said "All 22 dimensions
agree"; the `reconciliation.detail` table has **21** entries and always did.
Corrected to 21 — a prose count error with no measurement impact: no evidence
array, count, hash, conclusion, candidate or decision changed.

**One derived report changed as a consequence, disclosed rather than hidden.**
`reports/question_no_clinical_change_v1_1.json` walks `reports/` and
`testing/questions/fixtures/` wholesale, so adding this step's artifacts changed
its scanned-file count (94 -> 113). Its scan now excludes the two IM-003 reports
**by exact path**, because those are scanned by `run_im003_checks.py` with the
same patterns and controls. An earlier `im003_` *prefix* rule also swallowed the
19 invalid fixtures, which that runner does not scan — 19 files would have gone
unscanned by anything. Mobile's vendored copy is pinned at `cffbe8a6` and is
unaffected.

### Step 6A correction — newly-reachable set undercounted by one token

Pre-merge review of PR #31 found the impact analysis reported **14** newly
reachable tokens and **30 of 50** conditions, while its own 56-pair array and
18-node trigger graph produced **15**. `newly_reachable` accumulated only the
second hop (the newly eligible question's own options) and never the produced
token itself, so `pain` — reached from `swelling` and present in no other
token's option list — disappeared. `pain` is canonical, picker-reachable and
**scores on `minor_injury` at weight 6**, so the omission understated the
scoring blast radius.

The red-flag conclusion is unaffected: `pain` intersects zero of all six
pathways, so "zero red-flag references" holds for all 15 tokens. Convergence is
unaffected (15 two-cycles, closure 14, depth 5, 0 monotonicity violations — all
independently reproduced).

Check **I3** shared the same defect — it recomputed with the same
second-hop-only rule, so it agreed with the wrong report and the disagreement
was invisible. I3 is corrected and a new **I13** asserts the derived token list
equals the two-hop closure of the pair array. A negative test confirms I13
rejects the original 14/30 shape.

Corrected: **15** newly reachable tokens, **31 of 50** conditions,
`minor_injury` (weight 6) added to the scoring-input delta. No pair added or
removed, no decision approved, IM-003 still disabled.

Also corrected: `docs/IM001_OPTION_ORDERING.md` still read "All 22 reconciled
dimensions agree" — the 21-dimension fix had been applied to `progress.md` only.
Prose-only; no evidence value, hash, conclusion or decision changed.
