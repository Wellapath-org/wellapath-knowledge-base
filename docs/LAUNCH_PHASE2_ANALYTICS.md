# WellaPath Phase-2 Analytics Plan — UNIMPLEMENTED, PENDING APPROVAL

**Date:** 2026-09-21 · **Author:** Knowledge Base / Data Engineering
**Status: nothing in this document is implemented, enabled, or authorized by
this document.** It exists so that when Product wants production analytics, the
decision is a recorded approval against a fixed plan — not an improvised
enablement. Until the approval record in §2 exists: `TELEMETRY_ENABLED` stays
default-off, `TELEMETRY_PRODUCTION_APPROVED` stays unset, Sentry stays DSN-less,
store data-safety declarations stay as they are, and no collection endpoint is
created or modified. The build now distributed on both internal tracks
(0.3.0+211) ships with telemetry doubly off — **live tracks change
distribution, not collection** — and no telemetry, staging or otherwise, is
ever activated merely to populate the launch dashboard.

## 1. What already exists (and stays dormant)

Backend telemetry v1.0 (`POST /v1/telemetry/events`, merged 2026-08-11) and the
mobile client (10 of 12 allowlisted events, sealed event types, two-pass privacy
guard, offline queue) are **built and off**. Phase 2 is therefore mostly a
governance exercise: the engineering surface area of activation is a build flag
and a deploy — which is exactly why the governance must come first.

## 2. Activation prerequisites (all required, in order)

1. **Product decision record** — scope: which Tier-3 KPIs (LS-20…LS-23) activate,
   over what population, reviewed on what cadence, with a kill criterion.
   Recorded in the style of the existing decision registers (FAC/IM precedent):
   authority, date, per-item scope.
2. **Privacy review** — against the contract allowlist and the state-only
   ceiling; confirms the granularity caps (LS-17/LS-21 step-index-only rule; no
   red-flag oracle) are enforced in the analysis plan, not just the client.
3. **Store declaration update first** — Play data-safety / App Store privacy
   labels updated to declare the collection **before** any build ships with
   `TELEMETRY_PRODUCTION_APPROVED=true`. Declarations may never lag reality.
4. **Engineering activation plan** — staged rollout, verification that the
   staging-proven pipeline behaves identically in production, and a documented
   rollback (flag off = collection stops; queued events expire).
5. **LS-14 re-run** — the privacy-control evidence gate re-verified on the
   activation build (declarations now expected to say "collects", consistently).

## 3. State-level usage (LS-23) — extra prerequisite

`admin_area_code` is contractually state-level (ISO 3166-2:NG) and the client
currently — correctly — sends nothing because the artifact→code mapping is
unconfirmed. Before the field is populated: the facilities owner confirms the
mapping, a fixture test pins it, and the same approval record covers it.
**LGA-level geography is not a phase-2 item and has no path in this plan.**

## 4. Retention (LS-B1) — blocked; candidate methods for future evaluation

No retention measurement exists or may be built until Product + privacy review
approve a method. Candidates to evaluate **on paper first**, in rough order of
privacy cost:

| Option | Sketch | Privacy note |
|---|---|---|
| R-A | Store-level proxies: Play Console returning-user / update-uptake aggregates | No app change, no identifier; coarsest signal |
| R-B | On-device-only counter: the app locally tracks "sessions this month" and telemetry reports only a coarse bucket (1 / 2–3 / 4+) with no identifier | No cross-session ID leaves the device; bucket is k-anonymous by design; still requires contract change + approval |
| R-C | Rotating pseudonymous install ID with server-side aggregation and scheduled deletion | Weakest option privacy-wise; evaluate only if R-A/R-B prove insufficient, with explicit retention limits |

Each option requires its own contract-version change (v1.1+), privacy review,
and store-declaration update. **None is endorsed here; all are unimplemented.**

## 5. Crash reporting (relates to LS-13's vitals tile — not analytics)

Two paths, decided independently of product analytics:

- **Default path (no decision needed, already in effect):** the internal
  tracks are live, so the console sources are active now — **TestFlight
  per-build sessions/crashes** (iOS) and **Play Console Android vitals**
  (crash/ANR; `INSUFFICIENT_DATA` at the current 5-tester cohort), manually
  captured into the dashboard (LS-25). This is the MVP's designated crash
  source.
- **Optional path (decision needed):** enable Sentry as a **crash sink only** —
  provision a DSN, review `sentry_event_sanitiser` output on real crashes in
  staging, update the privacy policy's data-processor disclosure and store
  declarations, then flip its gates. Sentry remains excluded from every product
  KPI: it is diagnostics, **never** product analytics, and no funnel, usage or
  engagement number may ever be derived from it.

## 6. Library engagement (LS-B3)

Only becomes a metric if a health-library feature ships. If that happens, the
dormant `library_article_view` event (article-ID granularity, no free text, no
search-query capture — "what users are asking" stays out of analytics) goes
through the same §2 pipeline as any other activation. Until then the KPI stays
marked **unavailable**.

## 7. Explicitly out of scope, permanently under this architecture

LGA-level usage · free-text health feedback in analytics · any per-user health
profile · telemetry that can reconstruct red-flag status per user · any claim of
verified facility availability derived from usage data.
