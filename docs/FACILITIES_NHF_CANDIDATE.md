# Nationwide facilities candidate — NHF source, Steps 1 to 3

> **Candidate only.** `candidate/facilities.ng.v2.0.json` is unapproved and unpublished
> (`release_status` and `publication_status` both `candidate_unapproved`, `may_publish: false`).
> `facilities.ng.v1.1.json` remains the active artifact and is byte identical.
> Nothing was uploaded, published, activated, deployed or handed to Backend/Mobile, and
> `/config` is unchanged.

```bash
python3 tools/run_facilities_checks.py     # everything: regenerate-and-compare, validate, test
```

Companion documents:

| Document | What it is |
|---|---|
| `docs/FACILITIES_COORDINATE_REMEDIATION.md` | The Step 3 study: the orientation rule, its evidence, per-state coverage, options A/B/C and the recommendation |
| `docs/FACILITIES_2_0_CHANGELOG.md` | What changed against 1.1 and across the three steps |
| `docs/FACILITIES_DECISIONS_REQUIRED.md` | The exact Product / Clinical / engineering decisions still needed |
| `docs/FACILITIES_SOURCE_AUTHORIZATION_CHECKLIST.md` | The written evidence required before publication (nine items, all missing) |
| `mobile_handoff/facilities_v2/README.md` | Every field, for the consumer, with the null-type and emergency-ordering contract |

---

## 1. What the source actually is

The supplied file is `nigeria_health_facilities.csv`, preserved unchanged at
`facilities/source/nigeria_health_facilities.csv` (20,913,558 bytes, sha256
`e598cecc…becb3`). Full record: `facilities/source/nhf_provenance_v1.json`.

**What is established:** the bytes, their structure (a title line, a 90-column header, 31,390
uniform data rows), and the dataset's own internal audit timestamps, which put the snapshot no
earlier than **2026-07-21T13:15:26** (source-local, zone undeclared).

**What is not, and is recorded as not:**

| Question | Answer |
|---|---|
| Publishing organisation | **Not established.** The file names none. (AUTH-01) |
| Licence or reuse permission | **Not established.** Nothing accompanied the data. **This alone blocks publication.** (AUTH-02…05) |
| Delivery / chain of custody | None. The copy passed through Apple Numbers (macOS `WhereFroms`); not a pristine upstream export. (AUTH-09) |
| Snapshot version | None declared. (AUTH-06) |
| Data dictionary | None. Three id columns have no name column; `lga_id` is name-scoped. (AUTH-07) |
| Contact fields intended for public use | **Not established.** See §5. |
| Completeness / accuracy | **Not established.** Every row is `Auto-approved via bulk import`; whole states have latitude and longitude transposed (§6). |

The pipeline was still built, because building it invents nothing and publishes nothing; the
candidate cannot leave `candidate_unapproved` until the checklist is satisfied in writing.

---

## 2. Coverage

| | |
|---|---|
| States with records | **34** — 33 states plus the FCT |
| States with no row in the source | **Adamawa, Kebbi, Sokoto** |
| States emptied by refusal | **none** (Step 2 had emptied seven; the Step 3 rule recovers all of them) |
| v1.1 states present | Lagos 1,502 · **FCT 632** (v1.1: 614) · **Kano 1,293** (v1.1: 2,040) |
| Distinct LGA names | **679 of 774** (693 in the source; 8 state/LGA pairs lost entirely to quarantine) |

Per state, before and after correction: `docs/FACILITIES_COORDINATE_REMEDIATION.md` §5. The
artifact states its own gaps in `_metadata.states_absent`, `states_with_no_emitted_records` and
`coverage_claim`.

---

## 3. What was built

31,390 source rows → **29,028 emitted**, **2,362 quarantined**, and the two numbers add up.

| Deliverable | Path |
|---|---|
| Source bytes (unchanged) | `facilities/source/nigeria_health_facilities.csv` |
| Reference geometry (unchanged, CC BY 4.0) | `facilities/source/GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv` |
| Provenance record | `facilities/source/nhf_provenance_v1.json` |
| Source authorization checklist | `facilities/source/nhf_authorization_checklist_v1.json` |
| Canonical schema | `schema/facilities.v2.schema.json` |
| Generator | `tools/build_facilities_candidate.py` (+ `tools/facilities/{geometry,mappings,normalize}.py`) |
| Candidate artifact | `candidate/facilities.ng.v2.0.json` |
| Candidate manifest entry | `candidate/facilities.manifest.candidate.json` |
| Data-quality report | `reports/facilities_quality_v1.json` |
| Quarantine report | `reports/facilities_quarantine_v1.json` |
| Coordinate audit (every correction listed) | `reports/facilities_coordinate_audit_v1.json` |
| Comparison with 1.1, option-B overlay analysis | `reports/facilities_comparison_v1.json` |
| Mobile compatibility | `reports/facilities_mobile_compat_v1.json` |
| Validator / tests | `tools/validate_facilities_candidate.py` · `testing/facilities/test_facilities.py` |
| Publication dry-run plan | `publication/plans/facilities.ng.v2.0.dryrun.json` |

### Why version 2.0

The schema is additive — all ten 1.1 fields present under the same names — but `type` and
`emergency_capable` are null on every record, and the consumer filters and orders on both. A
shape-compatible artifact that changes what the app shows is not a minor version.

### Pipeline policies

| Policy | Rule | Rows |
|---|---|---|
| Not orientable | coordinates absent / 0,0 → quarantined, never substituted | 524 / 5 |
| **Orientation rule** `coordinate_orientation_v1` | see §6 | unchanged 18,210 · corrected 11,141 · ambiguous 1,442 · invalid 67 |
| Exact-duplicate collapse | same name + state + LGA + point → smallest registry `unique_id`; no values merged; each removed row listed with its survivor | 323 |
| Name guard | blank, placeholder or contact detail | 1 |

---

## 4. The two fields that are deliberately empty

**`type` — null on every record, blocking.** The source has no facility-kind column;
`facility_level` is a tier of care. Mapping tier to kind decides which facilities a user is
shown for self-care versus urgent care: Product decision **FAC-D001**. The vocabulary a
decision would map into is declared in `_metadata.unresolved_fields.type_vocabulary`, and
**null is not a member of it**. The consumer contract — a null type must not be filtered out
and must never produce an empty result list — is stated in the artifact metadata and in the
handoff. `facility_type_id` is a near-copy of the level and is reported, not interpreted.

**`emergency_capable` — null on every record, material.** No source column records emergency
capability; `ambulance_services` and `inpatient` are adjacent claims. No record carries
verified positive evidence, so prioritisation cannot apply to any; ordering falls back to
distance until Product and Clinical record a fallback decision (**FAC-D002**). Data Engineering
has not invented one.

---

## 5. Contact fields and privacy

`email_address` and `alternate_number` are excluded (no public-use basis, evident junk). The
seven officer/workflow contact columns are empty in every row. `phone_number` is carried,
normalised to E.164 and validated as a Nigerian mobile, because 1.1 already surfaces a phone;
public-use intent is not established and no `tel:` action should be offered before
**FAC-D003**. Free-text fields are screened for contact-shaped values (the one personal email
found in Step 1 sits in a row that is now quarantined earlier). The validator scans every key
at every depth for user, device, session, search, history, symptom, diagnosis, patient,
assessment or telemetry tokens; none exist.

---

## 6. Source findings

**Latitude and longitude are transposed for whole states.** The national bounding box (all
Step 1 checked) is blind to a northern transposition because both values stay inside Nigeria.
Step 2 saw it with a centroid yardstick and refused 9,911 rows, emptying seven states. Step 3
replaces the yardstick with the repository's GRID3 facility points (51,022, all 37 states,
CC BY 4.0) as an empirical boundary and tests each pair as given and exchanged against the
state the row claims. A pair is exchanged **only** when it is outside its state as given and
strictly inside it exchanged; the source values stay on the record and every correction is
listed. Both plausible, either uncertain, or GRID3 naming a different state for the same NHFR
facility → held as ambiguous. Both outside → invalid. The direction is corroborated at record
level: for corrected rows, the *same facility's* GRID3 point is within 20 km of the exchanged
pair 3,005 times and of the pair as given 2 times. Whether the transposition arose upstream or
in the spreadsheet the copy passed through is not established (AUTH-09). Full study:
`docs/FACILITIES_COORDINATE_REMEDIATION.md`.

**`lga_id` is name-scoped.** Six homonymous LGA names (Nasarawa, Obi, Ifelodun, Irepodun,
Surulere, Bassa) carry one id in two states each; five single Enugu-labelled rows carry Abia
LGAs (all 0,0, quarantined). `(state, city_area)` is the only unambiguous LGA key.

---

## 7. Data quality

| Measure | Count |
|---|---|
| Emitted | 29,028 |
| With coordinates, verified inside the state | 29,028 (100%) |
| …of which the source pair exchanged under the rule | 10,862 |
| With a valid normalised phone | 28,090 (96.8%) |
| With opening hours | 28,772 (99.1%) |
| `type` / `emergency_capable` populated | 0 (by decision) |
| Quarantined — orientation ambiguous | 1,442 |
| Quarantined — coordinates absent | 524 |
| Quarantined — exact duplicate | 323 |
| Quarantined — not in the state claimed | 67 |
| Quarantined — exactly 0,0 | 5 |
| Quarantined — name empty | 1 |
| Remaining same name + state + LGA groups (candidates, not merged) | 673 |
| Remaining identical-coordinate groups (candidates, not merged) | 1,540 |

---

## 8. Mobile compatibility — measured, not asserted

`reports/facilities_mobile_compat_v1.json` runs both artifacts through a port of
`facility_locator_service.dart` at wellapath-mobile `13be0d49`. The Mobile repository was not
modified.

**Verdict: NOT COMPATIBLE as it stands**, for one blocking reason:

| Finding | Severity |
|---|---|
| `type` null → the current build's `allowedTypes.contains(type)` drops every record; three of four urgency paths return nothing | **blocking** (FAC-D001, and the §7 contract in the handoff) |
| `emergency_capable` null → emergency ordering is pure distance | material (FAC-D002) |
| Artifact is **21.3×** the size of 1.1, held in memory | material |
| Three states have no rows in the source | material |

Coverage is no longer a finding: FCT and Kano by-location queries return results.

---

## 9. Comparison with facilities 1.1

| | 1.1 | Candidate |
|---|---|---|
| Records | 5,344 | 29,028 |
| Bytes | 1,695,844 | 36,077,142 |
| States | 3 | 34 |
| States lost | — | **none** |

Positional match (≤ 250 m, preferring identical normalised names): **957** exact, **1,985**
probable, **2,402** only in 1.1, **27,054** only in the candidate. The two lineages are not
merged; option B (a provenance-labelled 1.1 overlay) is quantified in the comparison report and
rejected — it buys no coverage and would add 4,387 records, 1,985 of uncertain identity.

---

## 10. Unresolved decisions

| # | Decision | Owner | Blocking |
|---|---|---|---|
| 1 | **Source authorization** — nine checklist items, all missing | Legal + engineering lead + source owner | **Publication** |
| 2 | **FAC-D001 `type` mapping**, or the null-type consumer contract | Product | **Mobile use** |
| 3 | **FAC-D002 `emergency_capable` fallback** | Product + Clinical | Emergency ordering |
| 4 | **FAC-D003 public use of `phone`** | Product | Public presentation |
| 5 | **FAC-D004 acceptance of `coordinate_orientation_v1`** | Engineering lead | Whether corrected rows may stand |
| 6 | FAC-D005 reinstating the 1,442 ambiguous and 524 coordinate-less rows for name search | Product | Coverage |
| 7 | FAC-D006 looser duplicate consolidation (673 name groups, 1,540 point groups) | Product + data | Quality |
| 8 | Three states with no rows and 95 missing LGA names | Source owner | Coverage |
| 9 | Artifact size / distribution profile (36 MB) | Engineering lead | Delivery |
| 10 | Whether to re-apply 1.1's 45 verified phone numbers | Product | Quality |
| 11 | `facility_type_id` and the two option-id columns — no dictionary | Source owner | Interpretation |

Nothing in this work grants Product approval, clinical approval, publication authorization or
activation authorization, and none is recorded.
