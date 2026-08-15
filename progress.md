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

### Still open (unchanged by this step)

1. **CB_211 disposition** — options A/D (preserve + registry) vs B (correct the
   expectation in a new versioned bank) vs C (engine-level empty-input result,
   issue #35's question). **Engineering lead**, with clinical input on whether
   `urgent` + a fabricated malaria differential is acceptable for empty input.
2. Case bank v1.0 clinical sign-off — still absent, still no schema field for it.
3. Issue #38 — malaria base_weight in mixed presentations; CB_232/CB_225 are
   worked examples for that monitoring item.
4. No documented tie-break in the scoring engine (new, low priority).
