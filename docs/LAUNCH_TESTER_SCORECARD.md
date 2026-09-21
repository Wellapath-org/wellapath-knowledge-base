# WellaPath Launch Tester Scorecard v1 — Fictional Scenarios Only

**Date:** 2026-09-21 · **Author:** Knowledge Base / Data Engineering
**Record contract:** `schema/tester_feedback.v1.schema.json`
**Feeds:** KPIs LS-09…LS-12 (`docs/LAUNCH_KPI_REGISTER.md`), dashboard panel 7.

## 1. Non-negotiable rules

1. **Fictional scenarios only.** Testers act out the provided scenario cards.
   A tester must **never** enter their own symptoms, their family's symptoms, or
   any real health situation. The session brief states this in writing before
   every round, and each record carries the attestation
   `contains_no_real_health_data: true` — a record without it is invalid.
2. **No personal medical information anywhere** — not in ratings, not in free
   text, not in observer notes. Free text describes **app behaviour** ("the
   button did nothing", "the map was blank"), never bodies.
3. **Pseudonymous testers.** Records carry a round-scoped pseudonym
   (`T01`, `T02`…). The pseudonym↔person mapping, if kept at all for logistics,
   stays with the QA Coordinator outside this repository and outside the dashboard.
4. **Sanitization before entry.** A named sanitizer reads every record before it
   enters `reports/launch_scorecard/inputs/`, removes anything personal or
   health-real (and rejects the record if removal would gut it), and signs the
   `sanitization` block. Unsanitized records never enter the repo.
5. This process collects **product usability evidence**. It is not a clinical
   study, produces no clinical claims, and no scenario outcome is medical advice.

## 2. Scenario cards

Cards are versioned in `testing/launch_scenarios/` (created at first round) and
pinned per round so results are comparable. Card families for round 1 — each an
**entirely fictional persona**, written to exercise a specific product path, not
to describe any real person:

| Card | Exercises | Sketch (fictional) |
|---|---|---|
| SC-01 | Core journey, common condition path | Adult persona with a scripted fever/chills selection set |
| SC-02 | Core journey, child flow | Caregiver persona, scripted under-5 selections |
| SC-03 | **Red-flag interrupt** comprehension | Scripted selection set that triggers a global red flag; measures whether the tester understands the urgency screen |
| SC-04 | Follow-up question depth | Scripted multi-symptom set reaching the 5-question path limit |
| SC-05 | Locator, phone-verified region | Find a facility in Lagos; observe call affordance |
| SC-06 | Locator, non-enriched region | Find a facility in a scripted non-Lagos state; **no call affordance expected** — tests graceful behaviour, not availability |
| SC-07 | Offline / poor connectivity | Airplane-mode launch and mid-session network loss |
| SC-08 | Emergency path | Scripted emergency entry; 112 prominence |

Scenario selection sets are drawn from the same fictional style as the committed
case bank and synthetic fixtures (`ZZTest…` convention) — never from real user
reports.

## 3. Per-session scorecard (what the tester + observer record)

For each card run:

- **Tasks** (per card, predefined): outcome `completed | abandoned | blocked | error`,
  duration in seconds, `dead_end` flag (locator tasks), observer note (sanitized).
- **Ratings** (1–5): helpfulness ("the result told me what to do next"),
  clarity of wording, confidence in next step, perceived speed/performance.
  For SC-03 additionally: `understood_urgency` yes/no — a "no" here is a launch
  signal regardless of averages (LS-12 failure condition).
- **Issues:** coded (`ISS-CRASH`, `ISS-FREEZE`, `ISS-UI`, `ISS-COPY`,
  `ISS-NAV`, `ISS-DATA`, `ISS-OFFLINE`, `ISS-OTHER`) + severity
  (`blocker | major | minor`) + sanitized description.
- **Device context:** model, Android version/API, RAM, network condition —
  device facts only, nothing about the person.

## 4. Round output

A round produces: schema-valid records → `reports/launch_scorecard/inputs/`,
the four Tier-1 tester KPIs (LS-09…LS-12), a top-issues table by code and
severity, and a sanitization sign-off line naming sanitizer and date. The QA
Coordinator owns collection; Product owns interpretation.
