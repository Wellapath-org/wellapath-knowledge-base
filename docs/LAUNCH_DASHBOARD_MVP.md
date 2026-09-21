# WellaPath Launch Dashboard — MVP Specification v1

**Date:** 2026-09-21 (rev. 2 — build 211 live on both internal tracks; production backend verified) · **Author:** Knowledge Base / Data Engineering
**Constraint honoured throughout:** the MVP consumes **only** non-user-derived or
already-permitted evidence — GitHub CI/release evidence, the live production
endpoints `https://api.wellapath.org/health|version|config` (plus staging),
facilities artifact identity, Play Console / App Store Connect (TestFlight)
console values captured manually, sanitized tester feedback (fictional
scenarios), physical-device testing, and the blocker/decision register. **No new
in-app telemetry, no collection endpoint, no analytics enablement, no change to
Mobile, Backend, Sentry, store declarations or infrastructure.** Telemetry is
never switched on merely to populate a panel (KPI register, Tier-2 standing rule).

Every reading on every panel carries an **observation state** —
`ZERO_OBSERVED` / `INSUFFICIENT_DATA` / `REPORTING_DELAY` / `UNMEASURABLE`
(defined in `LAUNCH_SCORECARD_GAP_ANALYSIS.md` §2). A blank console cell is
transcribed as its state, never as 0.

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
| 3 | **Backend Runtime** — **production `api.wellapath.org`** probe log (`/health` 200 verified 2026-09-21), `/version` parity (0.3.0/production ↔ 211), `/config` reachability + raw-body fingerprint; staging as secondary row | LS-03, LS-04 | probes daily; panel weekly |
| 4 | **Data Artifacts** — production `/config` manifest vs KB pins (**current: 4/4 hashes byte-match; facilities 1.1 `25684c71…2398` active; no `facilities_v2` key**); candidate states (all `candidate_unapproved` listed as exactly that); coverage sub-metrics with the mandatory phrasing (45 verified phones, Lagos only; **no availability/doctor/service/open-now claims**). Facilities 2.0 is **not a launch dependency** | LS-05 | weekly + per publication event |
| 5 | **Quality Gates** — clinical regression (239-case, CB_211 pinned), full suites, KB validators | LS-06, LS-07 | per PR / per RC |
| 6 | **Device Reliability** — physical low-end matrix results, timing budgets (iPhone 15 install/launch of 211 recorded; **Android 211 matrix OPEN**), plus the store crash tile: TestFlight sessions/crashes for 211 and Android vitals, each with its observation state. *Sentry is off and is never an analytics source.* | LS-08, LS-25 | per RC / weekly |
| 7 | **Tester Evidence** — completion rate, median time, dead-end rate, helpfulness distribution, top sanitized issue codes | LS-09…LS-12 | per testing round |
| 8 | **Store & Distribution** — the three separated stages (13a internal distribution **COMPLETE** · 13b public listing **INCOMPLETE** · 13c public review **NOT STARTED**); internal-track adoption & tester participation; tester device/OS distribution | LS-13, LS-24, LS-26 | weekly |
| 9 | **Blockers & Decisions** — the blocker register (owner, gate it blocks, target date) and the running decision log (what was decided, by whom, when — in the style of the existing FAC/IM decision records) | LS-15 | weekly |

Panels 2–6 and 8–9 are populated **today** (panel 6's store crash tile and
parts of panel 8 may read `INSUFFICIENT_DATA`/`REPORTING_DELAY` while the
5-tester cohort accrues — that is the honest reading, not a gap in the
dashboard). Panel 7 fills at the first tester round. Nothing on any panel
waits for telemetry, and no telemetry is enabled to fill one.

## 3. Data-source & privacy matrix

| Source | What it feeds | Access path | Privacy class | User data? | Status today |
|---|---|---|---|---|---|
| GitHub Actions / releases (mobile + KB repos) | LS-01, LS-02, LS-06, LS-07 | `gh` CLI, read-only | P0 | none | **Available now** |
| Production endpoints `https://api.wellapath.org/health|version|config` (+ staging secondary) | LS-03, LS-04, LS-05 | `curl`, unauthenticated read | P0 | none | **Live and verified** (2026-09-21: /health ok · /version 0.3.0/production · /config 4/4 hash match, facilities 1.1 active) |
| KB artifact pins & check suites | LS-05, LS-07, LS-14 | in-repo scripts | P0 | none | **Available now** |
| Release binaries (AAB/IPA) | LS-02, LS-14 (telemetry/Sentry-off verification) | documented rebuild/inspect procedure | P0 | none | **Available now** |
| Physical-device test sessions | LS-08 | structured checklist, filed to `inputs/` | P0 | none (testers run scripts, no accounts) | **Available now** |
| Tester scorecard records | LS-09…LS-12 | sanitized records conforming to `schema/tester_feedback.v1.schema.json` | P2 | pseudonymous testers; **fictional scenarios only; no real symptoms or personal medical information — prohibited by schema and process** | **Available at first round** |
| Google Play Console (internal-testing track live, 5 testers) | LS-13, LS-24 (tester list, installs on release), LS-25 (Android vitals crash/ANR), LS-26 (device/OS, above threshold) | manual console capture → `inputs/` | P1 | aggregate only, held by the store | **Live** — participation/adoption capturable now; statistics lag ≈ 24–48 h (`REPORTING_DELAY`); vitals with 5 testers reads `INSUFFICIENT_DATA` |
| App Store Connect / TestFlight (internal testing live, build 211) | LS-13, LS-24 (testers, per-build installs), LS-25 (per-build **sessions + crashes** — TestFlight testers consent to this), LS-26 (tester devices) | manual console capture → `inputs/` | P1 | aggregate/tester-level in console only; only aggregates enter the repo | **Live** — metrics lag up to ~24 h; App Analytics does not cover TestFlight (sessions come from TestFlight build metrics only) |
| Staging telemetry export (Tier 2 only) | LS-16…LS-19 | per-round export by Engineering Lead from the staging backend | P2 | internal testers only, allowlisted events, fictional inputs | Available per round (already permitted) |
| Production telemetry | Tier 3 (dormant) | **none — collection off** | P3 | would be allowlisted, state-ceiling | **Blocked pending phase-2 approval** |
| Sentry | — | — | — | — | **Off (no DSN). Not an analytics source; not on this dashboard.** Enabling it is a phase-2 decision. |
| LGA geography, free-text health content, cross-session identifiers | — | — | PX | — | **Prohibited / blocked** (see KPI register PX table) |

### 3.1 Store values: manually captured now vs future API integration

**Manually captured now** (console UI → transcribed/screenshotted into
`inputs/`, with capture date and observation state):

- Play: internal-tester list size and acceptance; installs on active devices for the 211 release; Android vitals crash/ANR panel (state usually `INSUFFICIENT_DATA` at n=5); statistics device/OS rows where above Play's small-count threshold.
- TestFlight/ASC: tester count and status; per-build installs, sessions, crashes for 211; tester device models/OS versions.

**Would require future API integration — explicitly NOT built in this MVP** (a
phase-2-adjacent engineering decision; read-only, but still an integration with
credentials to manage): Google Play Developer / Play Developer Reporting API
for automated vitals + statistics pulls; App Store Connect API for automated
TestFlight metrics. Until such a decision, the manual weekly capture is the
mechanism, and its ~30-minute cost is accepted.

## 4. Launch Decision Scorecard

One row per gate; a gate is **GO** only when every listed condition is
evidence-green in the current snapshot. HOLD requires naming the blocking
item(s) from panel 9. Current status reflects the repositories as of 2026-09-21.

| Gate | Conditions (all required) | Current status |
|---|---|---|
| **G1 · Internal testing** (both internal tracks) | LS-01, LS-02, LS-06, LS-07, LS-14 green · internal-track console items done (incl. Play App Signing at first upload) | **GO — LIVE (2026-09-21).** Build 0.3.0+211 (`9269a87`) on the **Google Play internal track (5 testers)** and **TestFlight internal testing**; founder launch on physical iPhone 15 recorded. LS-13a complete. |
| **G2 · Tester rounds valid** | LS-09…LS-12 collected schema-valid · round used fictional scenario cards only · sanitization sign-off recorded · LS-24 adoption sufficient for the round · LS-26 includes ≥ 1 low-end Android device | **UNBLOCKED, NOT STARTED** — G1 is live; first structured round can begin now |
| **G3 · External beta** | G1+G2 green · **CB_211 adjudicated (Option B vs C — Clinical)** · case-bank clinical sign-off or a recorded decision that engineering-lead approval is the bar · IM-002 implementation status confirmed in the shipped build | **HOLD** — CB_211 open (RC-BLK-016); clinical sign-off absent |
| **G4 · Public store submission** (= LS-13c; distinct from the already-complete internal distribution 13a) | G3 green · RC-BLK-006 closed · public-listing items complete (LS-13b: assets, declarations, support email, privacy-policy URL) · data-safety declarations re-verified against actual (off) telemetry/Sentry state (LS-14). *RC-BLK-005 is closed — production endpoint live.* | **HOLD** — 13b incomplete; 13c not started; upstream G3 |
| **G5 · Public production launch** | G4 green · LS-03/04/05 green on production (**currently green: `api.wellapath.org` verified, 4/4 artifact hashes match, facilities 1.1 active**) · LS-08 green on the launch RC (**Android 211 matrix still open**) · LS-15 = 0 open gating blockers | **HOLD** — upstream gates; backend conditions already met |
| **G6 · Facilities 2.0 activation** *(separate from launch; only if Product puts it in scope)* | FAC-D002 clinical wording approved · Mobile-compat re-measurement · Engineering sign-off · publication lifecycle followed | **HOLD** — FAC-D002 pending; **launch does not wait for this** (v1.1 is the active, production-verified artifact) |
| **G7 · Production analytics** *(post-launch, optional)* | Phase-2 approval record exists (`LAUNCH_PHASE2_ANALYTICS.md` §2) · store declarations updated **before** enablement · Tier-3 KPIs activated only as approved | **HOLD** — no approval requested yet; intentionally last. Telemetry stays off in the shipped 211 build; Sentry stays DSN-less |

**No gate may be overridden silently.** An override is a recorded Product
decision on panel 9, in the style of the existing decision registers.

## 5. Refresh procedure (runbook, ~30 min/week)

1. `gh run list` / `gh release view` on both repos → panel 2 (+ LS-01 window stats).
2. `curl` **production** `https://api.wellapath.org/health|version|config` (log line with timestamp, latency, raw-body sha256 for `/config`), then staging; run the hash-comparison script against KB pins → panels 3–4.
3. Pull latest CI results for the regression + suites → panel 5.
4. If a release candidate was cut: file the device-matrix checklist and binary-verification results → panels 2, 6.
5. If a tester round closed: validate records against the schema, confirm the sanitization sign-off, compute LS-09…LS-12 → panel 7.
6. **Manual console capture** (per §3.1 — these values have no API integration in the MVP): Play internal-testing tester counts + 211 installs + vitals panel; TestFlight testers + 211 installs/sessions/crashes + tester devices. Transcribe each with its capture date and observation state (`ZERO_OBSERVED` vs `INSUFFICIENT_DATA` vs `REPORTING_DELAY` — never a bare 0 for a blank cell) → panels 6, 8.
7. Walk the blocker register with owners; update panel 9; recompute panel 1.
8. Commit `snapshot_YYYY-MM-DD.md` + inputs; open the PR; Product reads panel 1.

## 6. Recommendation to Product (what you can use immediately)

**Adopt panels 1–6, 8–9 now** — they run entirely on evidence that already
exists, and they are sufficient to run an honest launch gate this week. Panel 7
activates the day the first tester round completes under the tester scorecard —
and G2 is now unblocked, so scheduling that round is the highest-leverage next
step.

Concretely, Product gets, today: G1 recorded as **GO/live** on both internal
tracks; build/release integrity; verified production backend and artifact
identity (`api.wellapath.org` serving exactly facilities 1.1 and the frozen
clinical set, 4/4 hashes matched); clinical-regression and privacy-control
status; device readiness (iPhone 15 observation recorded, Android matrix open);
internal-track adoption and tester participation; TestFlight/vitals crash
evidence with honest observation states; the three-way store-readiness split
(internal complete / listing incomplete / review not started); and a GO/HOLD
summary against the real blockers (CB_211, listing items, clinical sign-off).

What Product should **not** expect from the MVP: any production in-app
behaviour (completion, navigation, ratings, geography) — that is Tier 3,
dormant until a phase-2 approval Product itself controls, and no telemetry is
ever enabled just to fill a panel; retention (blocked pending an approved
privacy-safe method); anything about facility availability, doctors, services
or opening status (unsupported by data and deliberately so per FAC-D003); and
Android "crash-free **sessions**" specifically — Play provides crash *rate*
but no session denominator without app telemetry (iOS sessions/crashes come
from TestFlight). Sentry remains engineering diagnostics only, never product
analytics, regardless of any future enablement.
