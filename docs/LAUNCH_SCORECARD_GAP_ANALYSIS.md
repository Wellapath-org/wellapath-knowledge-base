# Launch Scorecard — Gap Analysis of the "Pre-Launch Success Metrics" Proposal

**Date:** 2026-09-21
**Author:** Knowledge Base / Data Engineering
**Source under review:** `Pre Launch success metric.pptx` (7 slides, "10 metrics · 7 categories · evidence-based launch gate"), vendored verbatim at
`baseline/launch_metrics_proposal_v1/Pre_Launch_success_metric.vendored.pptx`
**Status of this document:** operational specification for Product. It changes no
Mobile, Backend, telemetry, Sentry, store or infrastructure behaviour, creates no
collection endpoint, and enables no analytics.

---

## 1. Verified ground truth this audit is measured against

Every disposition below is checked against the actual repositories, not the
proposal's assumptions. The load-bearing facts:

| Fact | Evidence |
|---|---|
| Product telemetry is **implemented but disabled by default in every build**; production is double-gated off (`APP_ENV=production` forces off unless `TELEMETRY_PRODUCTION_APPROVED=true`, both default `false`) | `wellapath-mobile docs/TELEMETRY_MOBILE.md` §2; `lib/core/telemetry/telemetry_config.dart` |
| The telemetry contract (backend v1.0) allowlists **12 events**; the client emits 10. Geography ceiling is `admin_area_code`, ISO 3166-2:NG **state level** — and the shipped client **never populates it** (artifact→code mapping unconfirmed). **No LGA field exists anywhere in the contract.** | `lib/core/telemetry/contract/telemetry_contract.dart` (`adminAreaCodes`, "this client never populates `admin_area_code`") |
| `feedback_submit` carries **rating (int 1–5, required)** and **category (enum: usability / performance / content / other, optional)**. **No free-text field is allowlisted**; the privacy guard rejects non-allowlisted keys and value shapes (coordinate-, email-, phone-, JWT-like) fail-closed, twice per event | `telemetry_contract.dart`; `lib/core/telemetry/privacy_guard.dart` |
| **Sentry is a crash sink, not product analytics**, and it is genuinely off in build 210: two gates plus a structurally valid DSN are required and **no DSN is bundled** — verified in the release binaries | `lib/core/crash/crash_config.dart`; mobile `PROGRESS.md` build-210 verification ("no DSN … genuinely off") |
| The active facilities artifact is **v1.1** (nationwide-Lagos-enriched: 45 Lagos records carry verified phones; all others have none). It has **no opening hours, no doctor rosters, no service inventories, no verified availability** | KB `facilities.ng.v1.1.json`; `progress.md` PR #11 |
| Facilities 2.0 (GRID3) is `candidate_unapproved` / `may_publish: false`. Its `type` is only ever `hospital` / `health_centre` / null; **`emergency_capable` is structurally unpopulatable**; FAC-D003 **approved phones and hours as unavailable** (no call / "open now" actions); FAC-D002 requires interface wording that **capability is not verified** | `docs/FACILITIES_GRID3_DECISIONS.md`; decision register 2026-09-15 |
| **No health library ships.** `lib/features/` contains no library feature; the contract's `library_article_view` event exists for a future feature only | `wellapath-mobile lib/features/` |
| Build 0.3.0+210 (AAB `818d60b1…`) is **internal-testing only**. External beta is blocked by CB_211 (RC-BLK-016); store submission by RC-BLK-005/006; Play App Signing enrolment happens at first upload; support email + privacy-policy URL are pending with the founder | mobile `PROGRESS.md` "Store readiness"; `docs/store/CONSOLE_RUNBOOK.md` |
| Backend exposes unauthenticated `/health`, `/version`, `/config` (staging: `wellapath-backend-staging.onrender.com`); artifacts are hash-pinned via the `/config` manifest and verified by the mobile loader on the **raw body sha256** | `docs/TELEMETRY_MOBILE.md`; KB `progress.md` (served-projection hash/transport contract) |
| The mobile telemetry handoff explicitly requires that **telemetry must not become a red-flag oracle** | `mobile_handoff/question_flow_v1/IM002_SAFETY_FIX.md` |

## 2. Classification vocabulary

Every proposed metric is placed in exactly one bucket:

- **MEASURABLE NOW** — from existing non-user-derived evidence (CI, endpoints,
  artifacts, store consoles, device testing, sanitized tester records). Dashboard MVP.
- **CONTROLLED TESTING** — measurable today with internal testers on staging
  builds running fictional scenarios (including staging telemetry, which is
  already permitted and internal-only). Never production users.
- **REQUIRES APPROVED TELEMETRY** — the event exists in contract v1.0 but
  production collection is off and stays off until the approval defined in
  `docs/LAUNCH_PHASE2_ANALYTICS.md` is recorded.
- **UNSUPPORTED** — the current product or data cannot produce the metric, or
  the privacy architecture prohibits it. Stated plainly, with what (if anything)
  could change that.

## 3. Slide-by-slide audit

### Slide 1–2 — framing ("10 metrics · 7 categories · evidence-based launch gate")

The framing is sound and is retained. Two corrections:

1. "Evidence-based launch gate" is made literal: the gate is the **Launch
   Decision Scorecard** (`docs/LAUNCH_DASHBOARD_MVP.md` §4), whose rows are
   verifiable artifacts, not aspirations.
2. Category 02's "zero tolerance" cannot attach to a metric the product cannot
   measure (see Slide 4). Zero-tolerance framing is moved to the two things that
   genuinely support it today: **privacy-control evidence** (0 PHI hits, telemetry
   and Sentry verified off in release binaries) and **clinical regression**
   (0 unexpected failures, fail-closed).

### Slide 3 — Core Journey (3 metrics)

| Proposed metric | Disposition | Detail |
|---|---|---|
| Assessment completion rate | **CONTROLLED TESTING** now · **REQUIRES APPROVED TELEMETRY** for production | `assessment_start` / `assessment_complete` exist in contract v1.0 and work on staging builds. Production collection is off by design. Until approval: measure via the tester scorecard (KPI LS-09) and staging funnel (LS-16). |
| Assessment abandonment by question | **CONTROLLED TESTING** now · **REQUIRES APPROVED TELEMETRY** for production, **with a design constraint** | `assessment_step_view` exists. Constraint: per-question abandonment analysis must be designed so it cannot function as a red-flag oracle (a step-level exit adjacent to a clarifier can leak red-flag state). Analysis granularity is capped at step index + role class, never token identity. |
| Median assessment time | **CONTROLLED TESTING** now (stopwatch protocol in the tester scorecard, LS-10) · approved telemetry later (`assessment_complete` carries duration context on staging) | No production source today. |

### Slide 4 — "Facility Match & Availability Rate" (1 metric, "zero tolerance")

**Disposition: UNSUPPORTED as proposed.** The slide claims measurement of
direction to "the right healthcare facility … with backup options provided if
the first facility is unavailable, closed, or does not have the required
service/doctor available", and asks "Can users **always** find an appropriate
place to get care without reaching a dead end?"

The product has **no verified availability, no doctors, no services, no opening
status, and no universal-matching guarantee**, and the 2026-09-15 decision
register makes several of these *deliberately* unavailable (FAC-D003: no phones,
no hours, no call/"open now" actions; FAC-D002: `emergency_capable` stays
unpopulatable and the UI must say capability is not verified). A metric defined
over fields that do not exist is not strict — it is unfalsifiable. No KPI may
claim verified facility availability, doctors, services, opening status or
universal matching.

**Replaced by three measurable proxies:**

1. **Facility data coverage & identity** (MEASURABLE NOW, LS-05): active
   artifact identity (sha256 vs `/config` manifest), record count, state
   coverage, % records with `type`, % with verified phone (currently 45, Lagos
   only — reported as exactly that, never generalized).
2. **Locator dead-end rate under scripted queries** (CONTROLLED TESTING, LS-11):
   share of scripted searches (drawn from all 36 states + FCT) that return ≥1
   facility or a graceful empty state with a usable next step. Target is 0 dead
   ends **on the script** — a bounded, honest version of "no dead end", never
   "always" for all users.
3. **Facility result appropriateness under fictional scenarios** (CONTROLLED
   TESTING, tester scorecard §T3): tester-judged "was a plausible facility type
   surfaced for the scripted need", explicitly labelled as tester judgment, not
   verified capability.

**"Privacy … encrypted and be immune to leaks" — REMOVED.** No system is immune
to leaks and the claim must not appear in any scorecard, store copy or launch
material. Replaced by **privacy-control evidence** (MEASURABLE NOW, LS-14):
transport is TLS; assessment scoring is on-device; telemetry and Sentry verified
off in the shipped binary; the two-layer privacy guard's tests pass; the KB
content-safety scan reports 0 PHI hits with its positive/negative controls
green. These are verifiable controls, not immunity claims.

### Slide 5 — Care Navigation & Retention (3 metrics)

| Proposed metric | Disposition | Detail |
|---|---|---|
| Facility view-to-call / directions rate | **CONTROLLED TESTING** now · **REQUIRES APPROVED TELEMETRY** for production | `facility_view`, `facility_call`, `directions_open` exist in the contract. Denominator caveat that must ride with the metric: **call** actions are only possible on the 45 phone-verified Lagos facilities, so call-rate is Lagos-only and must never be read as national. Directions-open rate is national. |
| 7-day / 30-day return rate | **UNSUPPORTED today — BLOCKED pending an approved privacy-safe measurement method** | Contract v1.0 has no persistent cross-session user identifier, deliberately. No retention KPI exists in this scorecard. Candidate privacy-safe methods (each **unimplemented, pending approval**) are catalogued in `docs/LAUNCH_PHASE2_ANALYTICS.md` §4. Nothing may be built until one is approved by Product + privacy review. |
| Health-library engagement ("what questions are they asking the most?") | **UNSUPPORTED — feature does not exist** | No health library ships in the app; `library_article_view` is a dormant contract event for a future feature. Additionally, "what questions are they asking" implies free-text health input, which is excluded from analytics categorically (see Slide 6). Marked unavailable; revisit only if/when a library feature ships. |

### Slide 6 — Outcome Quality & Reach (2 metrics)

| Proposed metric | Disposition | Detail |
|---|---|---|
| Helpful-result rating (helpful/not, confidence, "optional comment") | **CONTROLLED TESTING** now (sanitized tester scorecard, LS-12) · **REQUIRES APPROVED TELEMETRY** for the in-app rating at scale | The allowlisted `feedback_submit` event carries **rating 1–5 + category enum only**. The proposal's "optional comment" **must not enter analytics**: free-text health feedback is excluded — the privacy guard structurally rejects non-allowlisted fields, and this scorecard adds the policy statement on top: no free-text field is to be proposed for the telemetry contract. Tester free text exists only in the tester channel, sanitized per `schema/tester_feedback.v1.schema.json`, and never contains real health information (fictional scenarios only). |
| Usage by state / LGA | **LGA: UNSUPPORTED — prohibited by the telemetry boundary.** State: **REQUIRES APPROVED TELEMETRY** plus one data fix | The contract's only geography field is state-level (`admin_area_code`, ISO 3166-2:NG). **LGA-level usage is outside the boundary and is removed from the proposal** — the slide's own "aggregated level" caveat does not rescue it; the field does not exist and will not be added under the current architecture. State-level usage additionally requires the artifact→state-code mapping to be confirmed by the facilities owner (today the client sends nothing rather than risk a wrong-but-valid code). Near-term coarse proxy once store tracks are live: Play Console acquisition/geography reports (country-level; **not** state-resolution — reported as what it is). |

### Slide 7 — Technical Reliability (1 metric)

**Disposition: SPLIT into two KPIs.** The slide fuses two different things with
different sources, owners and failure modes:

1. **Crash-free sessions** — **REQUIRES A TOOLING DECISION, not measurable
   today.** Sentry is off (no DSN, double-gated) and **Sentry is not product
   analytics** — if enabled it is a crash sink only, and enabling it is a
   Product + privacy decision recorded in phase 2 (§5), because it is a
   third-party data processor named in the privacy policy. Independent
   alternative once store tracks are live: **Play Console Android vitals**
   (crash rate / ANR from consenting devices) — platform-provided, no app change,
   and the MVP's designated source (LS-13 note).
2. **Low-end device performance** — **MEASURABLE NOW** via the physical-device
   release gate (LS-08): the existing low-end validation practice
   (`docs/I1_TELEMETRY_LOW_END_VALIDATION.md`, offline-screen timing budgets,
   cold-start budgets, offline mode, limited connectivity) formalized into a
   pass/fail matrix run before every release. This is testing evidence, not
   user-derived data.

## 4. Corrections register (as instructed, all applied)

| # | Instruction | Where applied |
|---|---|---|
| 1 | No claims of verified facility availability, doctors, services, opening status or universal matching | §3 Slide 4; KPI register LS-05/LS-11 definitions; tester scorecard T3 wording |
| 2 | Remove "immune to leaks" | §3 Slide 4 — removed, replaced by LS-14 privacy-control evidence |
| 3 | Sentry is not product analytics | §3 Slide 7; phase-2 plan §5 |
| 4 | No LGA-level usage under the state-only boundary | §3 Slide 6 — LGA removed outright |
| 5 | No free-text health feedback in analytics | §3 Slide 6; tester schema confines free text to sanitized, fictional-scenario tester records |
| 6 | Health-library engagement unavailable (no library ships) | §3 Slide 5 |
| 7 | Crash-free sessions ≠ low-end performance | §3 Slide 7 — split into two KPIs with different sources |
| 8 | Retention blocked pending an approved privacy-safe method | §3 Slide 5; phase-2 plan §4 |

## 5. What survives, in one view

| Proposal metric (10) | Bucket |
|---|---|
| Assessment completion rate | Controlled testing → approved telemetry |
| Abandonment by question | Controlled testing → approved telemetry (granularity-capped) |
| Median assessment time | Controlled testing → approved telemetry |
| Facility match & availability | **Unsupported** → replaced by coverage/identity + scripted dead-end rate + tester appropriateness |
| View-to-call / directions | Controlled testing → approved telemetry (call = Lagos-only denominator) |
| 7/30-day return | **Blocked** (privacy-safe method pending approval) |
| Health-library engagement | **Unsupported** (no feature) |
| Helpful-result rating | Controlled testing (sanitized) → approved telemetry (rating+category only, no free text) |
| Usage by state / LGA | State: approved telemetry + mapping confirmation. **LGA: prohibited** |
| Crash-free / low-end (fused) | Split: crash-free = tooling decision (Play vitals designated) / low-end = **measurable now** |

**Bottom line for Product:** of the ten proposed metrics, **zero are measurable
in production today** — production telemetry is off by design and the store
listing is not yet live. But a defensible launch gate does not need them: the
dashboard MVP (`docs/LAUNCH_DASHBOARD_MVP.md`) runs entirely on evidence that
exists now, and the KPI register (`docs/LAUNCH_KPI_REGISTER.md`) states exactly
what each future metric costs to unlock and who owns that decision.
