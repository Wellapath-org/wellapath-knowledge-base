# Progress Log — wellapath-knowledge-base

Last updated: 2026-07-26

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
