# WellaPath Launch KPI Register v1

**Date:** 2026-09-21 (rev. 2 — build 211 live on both internal tracks; production backend verified) · **Author:** Knowledge Base / Data Engineering

Disposition buckets and the four **observation states** (`ZERO_OBSERVED` /
`INSUFFICIENT_DATA` / `REPORTING_DELAY` / `UNMEASURABLE`) are defined in
`LAUNCH_SCORECARD_GAP_ANALYSIS.md` §2. Every dashboard reading of every KPI
below carries one; **a blank is never rendered as a zero.**
**Companion documents:** `LAUNCH_SCORECARD_GAP_ANALYSIS.md` (why each KPI exists),
`LAUNCH_DASHBOARD_MVP.md` (where each KPI is displayed), `LAUNCH_TESTER_SCORECARD.md`
(how tester-derived KPIs are collected), `LAUNCH_PHASE2_ANALYTICS.md` (what Tier 3 unlocks).

Targets and thresholds below are **proposed by Data Engineering and pending
Product adoption**; adopting or amending them is a Product decision to be
recorded in the register's next version. Owners are roles; the same person may
hold several today.

**Privacy classes** (used throughout):

| Class | Meaning |
|---|---|
| **P0** | Non-user-derived system evidence (CI, artifacts, endpoint probes). No person's data at all. |
| **P1** | Aggregate platform-provided reports (Play Console / App Store Connect). No access to individuals beyond what the store surfaces. |
| **P2** | Internal tester records: pseudonymous, fictional scenarios only, sanitized before entry (`schema/tester_feedback.v1.schema.json`). |
| **P3** | Production telemetry under contract v1.0. **Collection is off; every P3 KPI is dormant until the phase-2 approval is recorded.** |
| **PX** | Prohibited under the current privacy architecture (LGA geography, free-text health content, cross-session identifiers without an approved method). PX items are listed only to say no. |

---

## Tier 1 — POPULATED NOW or CONSOLE-MEASURABLE (dashboard MVP; all P0/P1/P2)

LS-01…LS-15 are populated-now evidence KPIs; LS-24 and LS-26 are
console-populated now; LS-25 is console-measurable, awaiting data (readings
carry `INSUFFICIENT_DATA`/`REPORTING_DELAY` until the cohort accrues
observations — never a silent zero).

### LS-01 · CI green rate on integration branches
- **Definition:** share of CI runs on `develop`/`main` (mobile + KB repos) that succeed.
- **Numerator:** successful workflow runs in window. **Denominator:** all completed runs in window.
- **Source:** GitHub Actions. **Collection:** `gh run list` during weekly dashboard refresh.
- **Target:** 100% at gate time. **Warning:** any branch red > 24 h. **Failure:** red at a release-gate evaluation.
- **Owner:** Engineering Lead. **Cadence:** weekly + at every gate. **Privacy:** P0.
- **On failure:** release gate holds; owning engineer fixes or reverts before any build is cut.

### LS-02 · Release artifact integrity
- **Definition:** the release AAB/IPA matches its committed payload manifest (all untagged entries identical; PER-BUILD/PATH-DEPENDENT entries excepted), is release-signed, and carries the intended version/build.
- **Numerator:** deterministic manifest entries matching. **Denominator:** all deterministic entries (currently 461/473 untagged for build 210).
- **Source:** mobile repo payload manifest + rebuild verification. **Collection:** documented rebuild-and-compare procedure per release.
- **Target:** 100% deterministic entries match, `jar verified`, 0 debug-cert matches. **Warning:** none (binary check). **Failure:** any deterministic mismatch or signing anomaly.
- **Owner:** Mobile Engineer. **Cadence:** per release candidate. **Privacy:** P0.
- **On failure:** artifact quarantined, not uploaded; rebuild from clean worktree and diff.

### LS-03 · Backend availability (`/health`)
- **Definition:** share of scripted probes of `/health` returning 200 within 30 s (tolerating Render cold starts), on **production `https://api.wellapath.org` (primary — live, verified 2026-09-21: 200, `status: ok`)** and staging (`wellapath-backend-staging.onrender.com`, secondary).
- **Numerator:** successful probes. **Denominator:** all probes in window.
- **Source:** Render-hosted endpoints. **Collection:** manual or scheduled `curl` probe log kept in the dashboard workbook — **no new backend code**.
- **Target:** ≥ 99% over 7 days. **Warning:** < 99%. **Failure:** < 95% or any outage > 1 h unexplained.
- **Owner:** Engineering Lead. **Cadence:** probes ≥ daily; reviewed weekly. **Privacy:** P0.
- **On failure:** incident review of Render service before launch decisions proceed; launch gate holds while red.

### LS-04 · Version parity (`/version` ↔ release)
- **Definition:** deployed backend `/version` matches the release under gate evaluation, and the mobile build's pinned config matches. **Current reading (2026-09-21): production `/version` = `0.3.0` / `environment: production`, matching mobile 0.3.0+211 (merge `9269a87`) — PARITY.**
- **Numerator/Denominator:** binary (match / no match).
- **Source:** `/version` endpoint + git tags. **Collection:** `curl` + `git describe` at refresh.
- **Target:** exact match. **Failure:** any mismatch.
- **Owner:** Engineering Lead. **Cadence:** weekly + per deploy. **Privacy:** P0.
- **On failure:** deploy or tag corrected before gate evaluation continues.

### LS-05 · Served-artifact identity (facilities / kb / rules)
- **Definition:** every artifact named in the `/config` manifest hash-matches its committed KB source of truth, and the **active** facilities artifact is the approved one (today: v1.1; never an unapproved candidate).
- **Numerator:** manifest entries whose sha256 matches the KB pin. **Denominator:** all manifest entries.
- **Source:** `/config` + KB pinned hashes. **Collection:** `curl /config` + hash comparison script at refresh.
- **Current reading (production, verified 2026-09-21):** `https://api.wellapath.org/config` serves `token_dictionary 1.1 · knowledge_base 2.4 · rules 2.2 · facilities 1.1`, **4/4 manifest sha256 values byte-match the committed KB artifacts** (facilities 1.1 = `25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398`); no `facilities_v2` key. The manifest's two fingerprints, both re-derived live (1,000 B) and recorded in full so they are never confused: **raw-body** sha256 `183a15bda78f7ccb3b3954e829e7228b1154a17f200c609bff7a0b73cdf45d3b` · **canonical** (key-sorted compact JSON) sha256 `3b2bbb1cec6b25631bcf499902314c22c19cbab33fe7fcfae0c6288a4f8578ed` — the canonical value independently reproduced by method and matching Mobile's declared baseline (`docs/release/RC_FROZEN_INPUTS.json` @ `9269a87`) exactly. Snapshots must state which fingerprint they record; a raw-vs-canonical comparison is a false mismatch by construction. **GREEN.**
- **Target:** 100%; active facilities = `facilities.ng.v1.1.json`. **Failure:** any mismatch, or any `candidate_unapproved` artifact found live.
- **Owner:** Data Engineer. **Cadence:** weekly + per publication event. **Privacy:** P0.
- **On failure:** treat as a publication-lifecycle breach: freeze publication, identify who/what changed the manifest, restore last-known-good per rollback binding.
- **Coverage sub-metrics reported with it (display-only):** record count, states covered, % records typed, % with verified phone — currently 45 verified phones, **Lagos only**, and reported as exactly that. **No availability, doctor, service or opening-status claim may appear on this panel** (FAC-D003; gap analysis §3 Slide 4).

### LS-06 · Clinical regression gate
- **Definition:** the 239-case bank executes with 238 passes, exactly the pinned known finding (CB_211, fail-closed per Option D), 0 unexpected failures — against the frozen artifact set.
- **Numerator:** cases matching expectation (incl. the pinned CB_211 assertion). **Denominator:** 239.
- **Source:** mobile regression harness + `testing/known_findings.json`. **Collection:** CI run per release candidate.
- **Target:** 239/239 as specified. **Failure:** any unexpected failure, any drift in CB_211's observed result, or a stale run (artifact set newer than last execution).
- **Owner:** Mobile Engineer (execution), Data Engineer (bank integrity). **Cadence:** per release candidate + per clinical-artifact change. **Privacy:** P0 (fictional cases only).
- **On failure:** hard stop. No build advances; adjudicate per the known-findings contract.

### LS-07 · Full test-suite gate
- **Definition:** mobile suite (1,381 at last baseline) and all KB check suites (W2/W3/IM-003/publication/GRID3/content-safety) pass with 0 failures.
- **Numerator:** suites green. **Denominator:** all suites.
- **Source:** CI. **Collection:** per-PR + per-release CI.
- **Target:** 100%. **Warning:** flaky test observed (recorded, quarantined with an issue). **Failure:** any suite red at gate.
- **Owner:** Engineering Lead. **Cadence:** per PR / per release. **Privacy:** P0.
- **On failure:** gate holds; fix or formally quarantine with an issue and owner.

### LS-08 · Low-end device release gate (distinct from crash-free)
- **Definition:** pass rate of the physical-device matrix (low-end Android, offline mode, limited connectivity, cold-start and offline-screen timing budgets per `I1_TELEMETRY_LOW_END_VALIDATION.md` practice) on the release candidate.
- **Numerator:** P0-severity scenarios passing on every matrix device. **Denominator:** all P0 scenarios × devices.
- **Source:** physical-device test sessions. **Collection:** structured checklist per release, results filed with the dashboard.
- **Target:** 100% of P0 scenarios; timing budgets met (e.g. offline screen ≤ 33 s worst case as measured for 210). **Warning:** any P1 scenario failing. **Failure:** any P0 scenario failing on any matrix device.
- **Owner:** Mobile Engineer + QA Coordinator. **Cadence:** per release candidate. **Privacy:** P0.
- **On failure:** release candidate rejected; defect filed; re-run after fix.
- **Build-211 status:** iOS — the founder installed and launched 211 on a **physical iPhone 15** via TestFlight (recorded as the first 211 device observation: install + cold launch pass). Android — **the low-end physical-device matrix pass for 211 remains OPEN until recorded**; the gate is not green on the iPhone 15 observation alone (it is neither Android nor low-end).

### LS-09 · Tester assessment completion rate (fictional scenarios)
- **Definition:** share of scripted tester sessions (fictional scenario cards only) in which the tester completes the assessment journey to a result screen without assistance.
- **Numerator:** completed sessions. **Denominator:** all attempted scripted sessions in the round.
- **Source:** tester scorecard (`LAUNCH_TESTER_SCORECARD.md`). **Collection:** per testing round, sanitized records conforming to `schema/tester_feedback.v1.schema.json`.
- **Target:** ≥ 90%. **Warning:** < 90%. **Failure:** < 75%.
- **Owner:** QA Coordinator (collection), Product (interpretation). **Cadence:** per testing round (≥ 1 per release candidate). **Privacy:** P2.
- **On failure:** abandonment step analysis (LS-17 staging data or observer notes) → UX fix before external testing expands.

### LS-10 · Tester median assessment time
- **Definition:** median wall-clock time from assessment start to result across scripted sessions, per scenario card.
- **Numerator/Denominator:** median over completed sessions (report n).
- **Source/Collection:** tester scorecard timings (observer stopwatch or screen recording timestamp).
- **Target:** ≤ 5 min per standard card (baseline to be set at the first round and pinned). **Warning:** > baseline +25%. **Failure:** > baseline +50%.
- **Owner:** QA Coordinator. **Cadence:** per round. **Privacy:** P2.
- **On failure:** identify the slow step(s) from observer notes; Product decides fix vs accept with rationale.

### LS-11 · Locator dead-end rate (scripted queries)
- **Definition:** share of scripted locator searches (state-stratified script covering all 36 states + FCT) ending in a dead end — defined as: no results **and** no graceful empty state with a usable next step. *This is the honest replacement for "users can always find care"; it claims nothing about real availability.*
- **Numerator:** scripted searches ending in a dead end. **Denominator:** all scripted searches.
- **Source/Collection:** tester scorecard section T3.
- **Target:** 0 on script. **Warning:** any dead end. **Failure:** > 5% of scripted searches.
- **Owner:** Data Engineer (script), QA Coordinator (execution). **Cadence:** per round + after any facilities artifact change. **Privacy:** P2.
- **On failure:** classify — data gap (Data Engineer) vs UX gap (Mobile) — and fix or document before gate.

### LS-12 · Sanitized tester helpfulness rating
- **Definition:** mean of testers' 1–5 "the result told me what to do next" rating across scripted sessions (fictional scenarios; testers rate clarity of guidance, not real medical value).
- **Numerator:** sum of ratings. **Denominator:** rating count (report n and distribution, not just the mean).
- **Source/Collection:** tester scorecard ratings block.
- **Target:** ≥ 4.0/5 with n ≥ 10. **Warning:** < 4.0. **Failure:** < 3.5 or any scripted red-flag scenario rated "did not understand urgency".
- **Owner:** Product. **Cadence:** per round. **Privacy:** P2.
- **On failure:** result-screen copy review; red-flag comprehension failures escalate to Clinical wording review before launch.

### LS-13 · Store readiness (three separated stages)
- **Definition:** the console-gated checklist (`docs/store/CONSOLE_RUNBOOK.md`) tracked as **three distinct stages that must never be conflated**:
  - **13a · Internal distribution — COMPLETE.** Build 0.3.0+211 live on the Play internal-testing track (Play App Signing enrolled at first upload) and on TestFlight internal testing. Founder-verified 2026-09-21.
  - **13b · Public listing requirements — INCOMPLETE.** Store listing assets, data-safety / privacy-label declarations (must match the actual off state of telemetry and Sentry, LS-14), support email and public privacy-policy URL, content rating, health-app reviewer package.
  - **13c · Public review / submission — NOT STARTED.** Submission for public release review on either store; gated on 13b plus G3/G4 of the decision scorecard (CB_211, RC-BLK-006).
- **Numerator/Denominator:** per stage, checklist items complete / total.
- **Target:** 13a done (met) · 13b 100% before submission · 13c only after G4 GO.
- **Source:** Play Console / App Store Connect. **Collection:** manual console capture into the dashboard workbook — no SDK, no new telemetry.
- **Owner:** Founder/Product (declarations, listing) + Mobile Engineer (technical items). **Cadence:** weekly. **Privacy:** P1 (13a/13c status is P0 fact).
- **On failure:** submission blocked; item owner and date assigned on the blocker register.

### LS-24 · Internal-track adoption & tester participation — **console-populated now**
- **Definition:** per store: testers on the internal list vs testers who accepted/installed, and installs of the **latest** internal build (release adoption).
- **Numerator:** testers with 211 installed (per store). **Denominator:** testers invited (Play list currently 5; TestFlight list per console).
- **Source:** Play Console internal-testing page + release dashboard ("installs on active devices" per release); TestFlight build page (installs per build) and tester list. **Collection:** manual console capture at refresh (screenshot/CSV where offered). Values may read `REPORTING_DELAY` (Play statistics lag ≈ 24–48 h) — never rendered as 0.
- **Target:** ≥ 80% of invited testers on the latest build within 7 days of rollout. **Warning:** < 80%. **Failure:** < 50% (the round's evidence is then unrepresentative of the shipped build).
- **Owner:** QA Coordinator. **Cadence:** weekly + per rollout. **Privacy:** P1 (aggregate counts; individual tester rows stay in the console, never in the repo).
- **On failure:** chase testers / re-invite before treating any tester-round KPI as valid for the gate.

### LS-25 · Store crash & session evidence — **console-measurable, awaiting data**
- **Definition:** iOS: TestFlight per-build **sessions** and **crashes** (crash-free ≈ 1 − crashes/sessions, small-n caveat always printed). Android: **Android vitals crash rate / ANR** from diagnostics-sharing devices (no session denominator exists on Play without app telemetry — reported as crash *rate*, never "crash-free sessions").
- **Numerator/Denominator:** as defined per store above; every reading carries its observation state — with a 5-tester Android cohort, `INSUFFICIENT_DATA` is the expected honest reading, and TestFlight metrics may sit at `REPORTING_DELAY` (up to ~24 h).
- **Source:** TestFlight build metrics; Play Console Android vitals. **Collection:** manual console capture at refresh.
- **Target:** 0 crashes observed in internal testing (`ZERO_OBSERVED`, not blank). **Warning:** any crash (internal cohort). **Failure:** ≥ 2 distinct crash clusters on 211, or any crash in a red-flag/emergency path.
- **Owner:** Mobile Engineer. **Cadence:** weekly. **Privacy:** P1.
- **On failure:** stack/cluster triage from the console; fix before wider distribution. **Sentry remains inactive and is never a source for this KPI — it is engineering diagnostics only, not product analytics** (gap analysis §3 Slide 7).

### LS-26 · Tester device & OS distribution — **console-populated now**
- **Definition:** distribution of device models / OS versions across internal testers, checked against the low-end target profile (are we actually testing on the devices we claim to serve?).
- **Numerator:** testers on devices at or below the low-end target profile. **Denominator:** all active testers.
- **Source:** TestFlight tester/build device info; Play statistics device/OS breakdown once above threshold (small cohorts may read `INSUFFICIENT_DATA` — Play thresholds low-count rows). **Collection:** manual console capture.
- **Target:** ≥ 1 active low-end Android device in the cohort before G2 closes. **Warning:** 0 low-end devices (currently the likely reading — the recorded 211 device is an iPhone 15, a high-end iOS device). **Failure:** G2 asserted green with 0 low-end devices in the cohort.
- **Owner:** QA Coordinator. **Cadence:** per round. **Privacy:** P1.
- **On failure:** recruit/allocate a low-end device before the tester round is accepted as gate evidence.

### LS-14 · Privacy-control evidence gate
- **Definition:** all of — content-safety scan 0 hits with all positive/negative controls passing; telemetry master gate default-off and production double-gate present (pinned tests green); Sentry structurally off (no DSN in binary); store data-safety declarations consistent with all of the above.
- **Numerator:** controls verified. **Denominator:** all listed controls.
- **Target:** 100%, every release. **Failure:** any control red, any hit, any declaration inconsistency. No warning band — this gate is binary.
- **Source:** KB content-safety runner, mobile pinned tests, release-binary verification, store declarations. **Collection:** per release candidate.
- **Owner:** Data Engineer + Mobile Engineer. **Cadence:** per release. **Privacy:** P0 (it is evidence *about* controls, not user data).
- **On failure:** hard stop; treated as a privacy incident candidate, not a bug.

### LS-15 · Launch-blocker burn-down
- **Definition:** count of open launch-gating blockers, each with owner + target date. Seed register (2026-09-21): **open** — CB_211 adjudication [external-beta gate], RC-BLK-006 [public submission], public listing items incl. support email + privacy-policy URL [13b], case-bank clinical sign-off, IM-002 implementation status confirmation, Android 211 low-end matrix pass [LS-08]; **closed** — RC-BLK-005 (production endpoint live), Play App Signing (enrolled at first upload); FAC-D002 joins only if Facilities 2.0 activation enters launch scope — **Facilities 2.0 is not a launch dependency; 1.1 is active and production-verified.**
- **Numerator:** blockers closed. **Denominator:** blockers opened (report both + trend).
- **Source:** blocker register (dashboard panel 9). **Collection:** standing register updated at refresh.
- **Target:** 0 open gating blockers at the gate under evaluation. **Warning:** any blocker without owner or date. **Failure:** attempting a gate with an open blocker scoped to that gate.
- **Owner:** Founder/Product. **Cadence:** weekly. **Privacy:** P0.
- **On failure:** the corresponding scorecard gate reads HOLD; no override without a recorded Product decision.

---

## Tier 2 — CONTROLLED TESTING (staging telemetry, internal testers, fictional scenarios; P2)

Staging telemetry is already permitted (internal builds, `--dart-define`,
documented in `TELEMETRY_MOBILE.md` §2) and is internal-only. These KPIs read
the **staging** ingest only; they never touch production users.

**Standing rule: telemetry is never activated — on staging or anywhere else —
merely to populate this dashboard.** A Tier-2 run happens because a testing
round needs it, on internal builds, for the round's duration; an empty Tier-2
panel is a correct reading (`UNMEASURABLE` outside rounds), not a problem to
fix by switching collection on. The production 211 build ships with telemetry
doubly off and stays that way (LS-14 verifies it per release).

### LS-16 · Staging funnel completion rate
- **Definition:** `assessment_complete` ÷ `assessment_start` over internal-tester staging sessions in a testing round.
- **Source:** staging telemetry export (backend staging DB/log, read by Engineering Lead). **Collection:** per-round export, aggregated; no dashboards wired to production.
- **Target:** ≥ 85% (testers on script). **Warning:** < 85%. **Failure:** < 70%.
- **Owner:** Data Engineer. **Cadence:** per testing round. **Privacy:** P2 (tester devices, fictional inputs).
- **On failure:** cross-read with LS-17 to locate the step; UX fix before round repeats.

### LS-17 · Staging abandonment by step (granularity-capped)
- **Definition:** last `assessment_step_view` step index before an abandoned staging session, aggregated by step index + role class only. **Never token identity, never per-question red-flag adjacency** — the analysis must not become a red-flag oracle (IM-002 handoff constraint).
- **Source/Collection:** staging export per round.
- **Target:** no single step > 30% of abandonments. **Warning:** any step > 30%. **Failure:** any step > 50%.
- **Owner:** Data Engineer. **Cadence:** per round. **Privacy:** P2, granularity-capped.
- **On failure:** step-level UX review with Mobile; wording changes route through the existing Product wording-decision process.

### LS-18 · Staging view-to-directions rate
- **Definition:** `directions_open` ÷ `facility_view` on staging sessions. (`facility_call` ÷ views with a phone shown is reported separately and labelled **Lagos-only denominator, 45 facilities**.)
- **Source/Collection:** staging export per round.
- **Target:** informational baseline in first two rounds; thresholds set after baseline. **Warning/Failure:** n/a until baseline pinned.
- **Owner:** Data Engineer. **Cadence:** per round. **Privacy:** P2.
- **On failure (post-baseline):** locator UX review.

### LS-19 · Staging feedback rating distribution
- **Definition:** distribution of `feedback_submit.rating` (1–5) + category counts from tester sessions. Rating + enum only; the contract has no free-text field and none will be proposed.
- **Source/Collection:** staging export per round.
- **Target:** median ≥ 4. **Warning:** median 3. **Failure:** median < 3.
- **Owner:** Product. **Cadence:** per round. **Privacy:** P2.
- **On failure:** triangulate with LS-12 comments (sanitized tester channel) for the why.

---

## Tier 3 — REQUIRES APPROVED TELEMETRY (production; P3; **all dormant**)

Every KPI below is fully specified so that approval is a decision, not a design
project — but **none may be activated before the phase-2 approval record
described in `LAUNCH_PHASE2_ANALYTICS.md` §2 exists.** Activation without that
record is a privacy-gate breach (LS-14 fails).

### LS-20 · Production assessment completion rate
As LS-16, over production events. **Target (proposed):** ≥ 70% in month 1. Warning < 70%, failure < 55%. Owner: Product. Cadence: weekly. Privacy: P3.

### LS-21 · Production abandonment by step
As LS-17 including the granularity cap, over production events. Thresholds as LS-17. Owner: Data Engineer. Privacy: P3.

### LS-22 · Production care-navigation action rate
As LS-18, production. Call-rate remains Lagos-denominator-only and labelled so. Owner: Product. Privacy: P3.

### LS-23 · Production helpful-result rating & state-level usage
`feedback_submit` aggregates, plus **state-level** (never LGA) usage via `admin_area_code` — which additionally requires the artifact→ISO-code mapping to be confirmed by the facilities owner before the client may populate the field. Owner: Product (metric) + Data Engineer (mapping). Privacy: P3, state ceiling.

---

## Blocked / prohibited (PX — listed to say no)

| ID | Item | Status |
|---|---|---|
| LS-B1 | 7-day / 30-day retention | **Blocked.** No privacy-safe measurement method is approved; contract v1.0 has no cross-session identifier by design. Candidate methods in `LAUNCH_PHASE2_ANALYTICS.md` §4, all unimplemented pending approval. |
| LS-B2 | LGA-level usage | **Prohibited** under the state-only telemetry boundary. Not a backlog item. |
| LS-B3 | Health-library engagement | **Unavailable** — no health library ships. Revisit only if the feature ships; the dormant `library_article_view` event does not make the metric real. |
| LS-B4 | Free-text health feedback in analytics | **Prohibited.** Analytics carries rating + enum only. Tester free text lives in the sanitized P2 channel, fictional scenarios only. |
| LS-B5 | "Facility availability / doctors / services / open-now" metrics | **Unsupported by data**; FAC-D003 keeps hours/phones unavailable in 2.0 and `emergency_capable` is structurally unpopulatable. See gap analysis §3 Slide 4 replacements. |
