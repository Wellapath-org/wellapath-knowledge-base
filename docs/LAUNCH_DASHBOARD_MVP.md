# WellaPath Launch Dashboard — MVP Specification v1

**Date:** 2026-09-21 · **Author:** Knowledge Base / Data Engineering
**Constraint honoured throughout:** the MVP consumes **only** non-user-derived or
already-permitted evidence — GitHub CI/release evidence, Render `/health` /
`/version` / `/config`, facilities artifact identity, Play Console / App Store
Connect reports or manual exports, sanitized tester feedback (fictional
scenarios), physical-device testing, and the blocker/decision register. **No new
in-app telemetry, no collection endpoint, no analytics enablement, no change to
Mobile, Backend, Sentry, store declarations or production infrastructure.**

---

## 1. Form of the MVP

A **weekly evidence snapshot in this repository** — not a live service.

- `reports/launch_scorecard/snapshot_YYYY-MM-DD.md` — the filled dashboard (one per refresh).
- `reports/launch_scorecard/inputs/` — the raw evidence for that snapshot: `gh` CLI output, `curl` probe logs, hash-comparison output, store exports (manual download), tester-round records (already sanitized; schema-valid).
- The snapshot is committed by PR like every other KB artifact, so each refresh is reviewed, attributable and immutable.

This is deliberately boring: a repo-native scorecard is auditable, needs no
infrastructure, and cannot leak what it never collects. A rendered/published
page can be layered on later without changing any definition here.

## 2. Information architecture (9 panels)

Panel order is the reading order for a launch meeting: verdict first, evidence after.

| # | Panel | KPIs | Refresh |
|---|---|---|---|
| 1 | **Launch Gate Summary** — the decision scorecard (§4): each gate GO / HOLD with the single blocking reason | roll-up | weekly + at gate |
| 2 | **Build & Release Integrity** — CI status, release artifact identity (version, build, AAB hash, manifest match, signing) | LS-01, LS-02 | weekly / per RC |
| 3 | **Backend Runtime** — `/health` probe log, `/version` parity, `/config` reachability | LS-03, LS-04 | probes daily; panel weekly |
| 4 | **Data Artifacts** — served-artifact identity vs KB pins; active facilities = v1.1; candidate states (all `candidate_unapproved` listed as exactly that); coverage sub-metrics with the mandatory phrasing (45 verified phones, Lagos only; **no availability/doctor/service/open-now claims**) | LS-05 | weekly + per publication event |
| 5 | **Quality Gates** — clinical regression (239-case, CB_211 pinned), full suites, KB validators | LS-06, LS-07 | per PR / per RC |
| 6 | **Device Reliability** — physical low-end matrix results, timing budgets. *Crash-free sessions is a separate, currently-empty tile that reads "source: Play vitals — available once a store track is live; Sentry is off and is not an analytics source."* | LS-08 (+ LS-13 vitals when live) | per RC |
| 7 | **Tester Evidence** — completion rate, median time, dead-end rate, helpfulness distribution, top sanitized issue codes | LS-09…LS-12 | per testing round |
| 8 | **Store & Distribution** — console checklist burn-down; once live: installs, update uptake, vitals (manual export) | LS-13 | weekly |
| 9 | **Blockers & Decisions** — the blocker register (owner, gate it blocks, target date) and the running decision log (what was decided, by whom, when — in the style of the existing FAC/IM decision records) | LS-15 | weekly |

Panels 2–6 and 8–9 work **today**. Panel 7 fills at the first tester round.
Nothing on any panel waits for telemetry.

## 3. Data-source & privacy matrix

| Source | What it feeds | Access path | Privacy class | User data? | Status today |
|---|---|---|---|---|---|
| GitHub Actions / releases (mobile + KB repos) | LS-01, LS-02, LS-06, LS-07 | `gh` CLI, read-only | P0 | none | **Available now** |
| Render `/health`, `/version`, `/config` (staging; prod when it exists) | LS-03, LS-04, LS-05 | `curl`, unauthenticated read | P0 | none | **Available now** |
| KB artifact pins & check suites | LS-05, LS-07, LS-14 | in-repo scripts | P0 | none | **Available now** |
| Release binaries (AAB/IPA) | LS-02, LS-14 (telemetry/Sentry-off verification) | documented rebuild/inspect procedure | P0 | none | **Available now** |
| Physical-device test sessions | LS-08 | structured checklist, filed to `inputs/` | P0 | none (testers run scripts, no accounts) | **Available now** |
| Tester scorecard records | LS-09…LS-12 | sanitized records conforming to `schema/tester_feedback.v1.schema.json` | P2 | pseudonymous testers; **fictional scenarios only; no real symptoms or personal medical information — prohibited by schema and process** | **Available at first round** |
| Play Console / App Store Connect | LS-13; crash rate via Android vitals when live | manual export → `inputs/` | P1 | aggregate only, held by the store | **Partial** — console checklist now; reports once a track is live |
| Staging telemetry export (Tier 2 only) | LS-16…LS-19 | per-round export by Engineering Lead from the staging backend | P2 | internal testers only, allowlisted events, fictional inputs | Available per round (already permitted) |
| Production telemetry | Tier 3 (dormant) | **none — collection off** | P3 | would be allowlisted, state-ceiling | **Blocked pending phase-2 approval** |
| Sentry | — | — | — | — | **Off (no DSN). Not an analytics source; not on this dashboard.** Enabling it is a phase-2 decision. |
| LGA geography, free-text health content, cross-session identifiers | — | — | PX | — | **Prohibited / blocked** (see KPI register PX table) |

## 4. Launch Decision Scorecard

One row per gate; a gate is **GO** only when every listed condition is
evidence-green in the current snapshot. HOLD requires naming the blocking
item(s) from panel 9. Current status reflects the repositories as of 2026-09-21.

| Gate | Conditions (all required) | Current status |
|---|---|---|
| **G1 · Internal testing** (Play internal track) | LS-01, LS-02, LS-06, LS-07, LS-14 green · console items for internal track done (incl. Play App Signing at first upload) | **HOLD** — console-gated steps + support email / privacy-policy URL (Founder) |
| **G2 · Tester rounds valid** | LS-09…LS-12 collected schema-valid · round used fictional scenario cards only · sanitization sign-off recorded | **NOT STARTED** — first round pending G1 |
| **G3 · External beta** | G1+G2 green · **CB_211 adjudicated (Option B vs C — Clinical)** · case-bank clinical sign-off or a recorded decision that engineering-lead approval is the bar · IM-002 implementation status confirmed in the shipped build | **HOLD** — CB_211 open; clinical sign-off absent |
| **G4 · Store submission** | G3 green · RC-BLK-005/006 closed · data-safety declarations re-verified against actual (off) telemetry/Sentry state (LS-14) | **HOLD** — upstream gates |
| **G5 · Production launch** | G4 green · LS-03/04/05 green on production infrastructure · LS-08 green on the launch RC · LS-15 = 0 open gating blockers | **HOLD** — upstream gates |
| **G6 · Facilities 2.0 activation** *(separate from launch; only if Product puts it in scope)* | FAC-D002 clinical wording approved · Mobile-compat re-measurement · Engineering sign-off · publication lifecycle followed | **HOLD** — FAC-D002 pending; **launch does not wait for this** (v1.1 is the active artifact) |
| **G7 · Production analytics** *(post-launch, optional)* | Phase-2 approval record exists (`LAUNCH_PHASE2_ANALYTICS.md` §2) · store declarations updated **before** enablement · Tier-3 KPIs activated only as approved | **HOLD** — no approval requested yet; intentionally last |

**No gate may be overridden silently.** An override is a recorded Product
decision on panel 9, in the style of the existing decision registers.

## 5. Refresh procedure (runbook, ~30 min/week)

1. `gh run list` / `gh release view` on both repos → panel 2 (+ LS-01 window stats).
2. `curl` `/health` (log line with timestamp + latency), `/version`, `/config`; run the hash-comparison script against KB pins → panels 3–4.
3. Pull latest CI results for the regression + suites → panel 5.
4. If a release candidate was cut: file the device-matrix checklist and binary-verification results → panels 2, 6.
5. If a tester round closed: validate records against the schema, confirm the sanitization sign-off, compute LS-09…LS-12 → panel 7.
6. Download any new Play Console / ASC report → `inputs/`, update panel 8.
7. Walk the blocker register with owners; update panel 9; recompute panel 1.
8. Commit `snapshot_YYYY-MM-DD.md` + inputs; open the PR; Product reads panel 1.

## 6. Recommendation to Product (what you can use immediately)

**Adopt panels 1–6, 8–9 now** — they run entirely on evidence that already
exists, and they are sufficient to run an honest launch gate this week. Panel 7
activates the day the first tester round completes under the tester scorecard.

Concretely, Product gets, today: build/release integrity, backend/runtime
health, artifact identity (including proof the served data is exactly v1.1),
clinical-regression and privacy-control status, low-end device readiness, store
checklist burn-down, and a single GO/HOLD summary against the real blockers
(CB_211, console items, clinical sign-off) instead of unmeasurable aspirations.

What Product should **not** expect from the MVP: any production user behaviour
(completion, navigation, ratings, geography) — that is Tier 3, dormant until a
phase-2 approval Product itself controls; retention (blocked pending an approved
privacy-safe method); anything about facility availability, doctors, services or
opening status (unsupported by data and deliberately so per FAC-D003); and
crash-free sessions until either a store track is live (Play vitals) or a
separate Sentry-enable decision is taken.
