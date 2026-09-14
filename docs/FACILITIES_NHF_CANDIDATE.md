# Nationwide facilities candidate — NHF source, Steps 1 and 2

> **Candidate only.** `candidate/facilities.ng.v2.0.json` is unapproved and unpublished
> (`release_status` and `publication_status` both `candidate_unapproved`, `may_publish: false`).
> `facilities.ng.v1.1.json` remains the active artifact and is byte identical.
> Nothing was uploaded, published, activated or deployed, and `/config` is unchanged.

> **Headline finding (Step 2).** The source writes latitude and longitude the wrong way round
> for whole states. 9,911 rows are refused on that ground; **FCT, Kano, Katsina, Kwara, Niger,
> Taraba and Zamfara have no surviving record**, and FCT and Kano are served by facilities 1.1
> today. Nothing was exchanged. See §6.

```bash
python3 tools/run_facilities_checks.py     # everything: regenerate-and-compare, validate, test
```

Companion documents: `docs/FACILITIES_2_0_CHANGELOG.md` (what changed against 1.1) and
`mobile_handoff/facilities_v2/README.md` (every field, for the consumer).

---

## 1. What the source actually is

The supplied file is `nigeria_health_facilities.csv`, preserved unchanged at
`facilities/source/nigeria_health_facilities.csv` (20,913,558 bytes, sha256
`e598cecc…becb3`). Full record: `facilities/source/nhf_provenance_v1.json`.

**What is established:** the bytes, their structure (a title line, a 90-column header, 31,390
uniform data rows), and the dataset's own internal audit timestamps, which put the snapshot no
earlier than **2026-07-21T13:15:26** (source-local, zone undeclared). That instant is carried
in the artifact as `_metadata.source.snapshot_last_updated_at`; the source declares no version.

**What is not, and is recorded as not:**

| Question | Answer |
|---|---|
| Publishing organisation | **Not established.** The file names none — no publisher field, no copyright line, no contact. The brief calls it "NHF"; the data does not. |
| Licence or reuse permission | **Not established.** Nothing accompanied the data. **This alone blocks publication**, independent of any technical readiness. |
| Delivery URL | None. The only technical evidence of origin is a macOS `WhereFroms` attribute naming **Apple Numbers**, so the file passed through a spreadsheet rather than arriving as a pristine upstream export. |
| Data dictionary | None supplied. Mitigated: every `*_id` column has a `*_name` column beside it, and each id maps to exactly one name — verified, not assumed. **But** `lga_id` is scoped to the LGA *name*, not the state (§6). |
| Contact fields intended for public use | **Not established.** See §5. |
| Completeness / accuracy | **Not established.** Every row carries `verify_note: "Auto-approved via bulk import"`. No record in this dataset was individually verified — and §6 shows what that means in practice. |

Per the brief's Step 1 rule, these are reported as blockers. The pipeline was still built,
because building it invents nothing and publishes nothing; the candidate it produces cannot
leave `candidate_unapproved` until the licence and organisation are established in writing.

---

## 2. "Nationwide" is a claim the data does not support

| | |
|---|---|
| States with a surviving record | **27** (of 36 + FCT) |
| States with no row in the source | **Adamawa, Kebbi, Sokoto** |
| States with rows in the source but no surviving record | **FCT, Kano, Katsina, Kwara, Niger, Taraba, Zamfara** — every row refused, almost all as transposed (§6); Jigawa (5) and Kaduna (10) are nearly empty for the same reason |
| Distinct LGA names in the candidate | **461 of Nigeria's 774** (693 in the source; 230 state/LGA pairs lost entirely to refusal) |
| Spelling variant found | `Akwa-Ibom`, normalised to `Akwa Ibom` through the explicit state table |

A user in Sokoto, or in Kano, gets an empty locator. The artifact states both gaps in its own
`_metadata` (`states_absent`, `states_with_no_emitted_records`, `coverage_claim`) rather
than leaving a reader to discover them.

---

## 3. What was built

31,390 source rows → **20,696 emitted**, **10,694 quarantined**, and the two numbers add up.
No row was silently discarded.

| Deliverable | Path |
|---|---|
| Source bytes (unchanged) | `facilities/source/nigeria_health_facilities.csv` |
| Provenance record | `facilities/source/nhf_provenance_v1.json` |
| Canonical schema | `schema/facilities.v2.schema.json` |
| Generator | `tools/build_facilities_candidate.py` (+ `tools/facilities/`) |
| Candidate artifact | `candidate/facilities.ng.v2.0.json` |
| Candidate manifest entry | `candidate/facilities.manifest.candidate.json` (`tools/build_facilities_manifest.py`) |
| Data-quality report | `reports/facilities_quality_v1.json` |
| Quarantine report | `reports/facilities_quarantine_v1.json` |
| Comparison with 1.1 | `reports/facilities_comparison_v1.json` |
| Mobile compatibility | `reports/facilities_mobile_compat_v1.json` (`tools/report_facilities_comparison.py`) |
| Changelog against 1.1 | `docs/FACILITIES_2_0_CHANGELOG.md` |
| Mobile handoff | `mobile_handoff/facilities_v2/README.md`, `facility_types.dart` |
| Validator | `tools/validate_facilities_candidate.py` |
| Tests | `testing/facilities/test_facilities.py` |
| Publication dry-run plan | `publication/plans/facilities.ng.v2.0.dryrun.json` |

### Why version 2.0

Not assumed — assessed. The schema is *additive*: all ten fields facilities 1.1 emits are
present under the same names and types, so the Mobile consumer's field access is unchanged.
That alone would argue for a minor bump. What makes it major is behaviour: `type` and
`emergency_capable` are null on every record, so a consumer reading the same shape gets
different results. A shape-compatible artifact that changes what the app shows is not a minor
version.

### Pipeline policies (Step 2)

| Policy | Rule | Rows |
|---|---|---|
| **Coordinate quarantine — national box** | absent, unparseable, 0,0, outside the Nigeria box, or plausible only if transposed → quarantined with that reason. Never emitted with nulls, never given a substitute | 639 (524 absent, 106 suspected transposed, 5 null island, 4 out of bounds) |
| **Coordinate quarantine — per-state yardstick** | more than 150 km from the claimed state's reference point as given and at least 2× closer transposed → refused as transposed; more than 300 km under either reading → refused as not in state. **Never exchanged** | **9,911** transposed, 81 not in state |
| **Exact-duplicate collapse** | same casefolded name + state + casefolded LGA + identical coordinates → one survivor, the smallest registry `unique_id`. **No values merged.** Each removed row is in the quarantine report with its `survivor_facility_id` | 62 pairs → 62 rows removed |
| Name guard | blank, placeholder, or a contact detail in place of a name | 1 |

The coordinate policies reverse Step 1, which emitted 524 records with null coordinates for
Mobile to sort last and had no per-state check at all. The brief for this work asks for
invalid or missing coordinates to be quarantined; the rows are listed, and reinstatement is a
decision (§10, #11 and #13).

---

## 4. The two fields that are deliberately empty

These are the substance of the candidate, and neither is a defect in the tooling.

**`type` — null on every record, blocking.** Mobile filters non-emergency results by `type`
against `{hospital, clinic, health_centre, pharmacy}`. This source has no such column. What it
has is `facility_level` — Primary, Secondary, Tertiary — which is a *tier of care*, not a kind
of facility: a Primary facility may be a health centre, a clinic or a dispensary, and the
source does not say which. Mapping tier to kind decides which facilities a user is shown for
self-care versus urgent care, so it is a Product decision. `tools/facilities/mappings.py`
carries the table as deliberately empty, and a test fails if it is filled in. The closed
vocabulary a decision would map into — `hospital`, `clinic`, `health_centre`, `pharmacy`,
`laboratory`, `other` — is declared in `_metadata.unresolved_fields.type_vocabulary` so the
enum exists to validate against.

`facility_type_id` (values 1, 2, 3, no name column) was cross-tabulated against
`facility_level` and `ownership` in the quality report: it is a near-copy of the level with
157 disagreements. Evidence for the decision owner; not interpreted.

**`emergency_capable` — null on every record, material.** facilities 1.1 derived it from
`type == 'hospital'`. This source has no type, and none of its 90 columns records emergency
capability. `ambulance_services` and `inpatient` are adjacent but are not the same claim, and
treating either as emergency capability would put a facility at the top of an emergency list on
a guess.

---

## 5. Contact fields and privacy

`email_address` (6,966 populated) and `alternate_number` (5,999) are **excluded**: no
documented public-use basis, and both columns carry evident junk. The seven officer/workflow
contact columns — `verified_email`, `verified_mobile`, `validated_email`, `validated_mobile`,
`published_email`, `published_mobile`, `verified_id` — are empty in all 31,390 rows; had they
been populated they would have been staff contacts, not facility contacts, and would have been
excluded on that ground.

`phone_number` **is** carried, normalised to E.164 and validated as a Nigerian mobile, because
facilities 1.1 already surfaces a phone to users. Public-use intent is still not established,
so it is flagged for Product review before any public presentation or `tel:` action.

**One personal email address was found typed into a facility's `physical_location` field** in
Step 1. Free-text fields are screened for contact-shaped values and the removal is counted when
it fires; in this build the row carrying it is refused earlier, by the coordinate instrument,
so the scrub has nothing to count. The guard remains, tested at the function level, and the
quarantine report reproduces no field values.

The validator additionally scans every key at every depth of the artifact for user, device,
session, search, history, symptom, diagnosis, patient, assessment or telemetry tokens. None
exist; a test fails if one appears.

---

## 6. Source findings from Step 2

**Latitude and longitude are transposed for whole states.** The national bounding box, which
is all Step 1 checked, is blind to a transposition whenever both values happen to fall inside
Nigeria — true for most of the north (Kano city is 12.0N 8.5E; the other way round it is
8.5N 12.0E, still inside the box, 500 km away in Taraba). Only a per-state yardstick can see
it. `tools/facilities/mappings.py` now carries an approximate reference point per state
(±0.5°, reference geography rather than facility data), cross-checked against facilities 1.1's
independent GRID3-derived medians for Lagos, FCT and Kano (7, 5 and 20 km away). Measured
against those points, every in-box row of FCT, Kano, Katsina, Kwara, Niger, Taraba and Zamfara,
and ~95% of Jigawa and Kaduna, is far from its state as given and close to it transposed.

Those rows are **refused, never exchanged**, with both distances recorded in the quarantine
report. Exchanging them would be a correction with a strong evidential basis — but it is a
decision about altering source data, and this pipeline's rule is that it does not make one.
The evidence is tabulated per state in `reports/facilities_quality_v1.json` →
`source_evidence.coordinate_consistency_by_state`, with each state's median reading as given
and transposed, so the calibration is auditable. Where a state's latitude and longitude are
numerically close (Bauchi, Gombe, Yobe, Borno, Kogi) the two readings are only 100–250 km apart
and the instrument is uncertain: some transposed rows there will have been kept, and the
handful of survivors in the predominantly transposed states are probably transposed too.

**`lga_id` is name-scoped.** Eleven ids appear under two states each. Six are homonymous LGA
names that genuinely exist in both states — Nasarawa (Kano, Nasarawa), Obi (Benue, Nasarawa),
Ifelodun and Irepodun (Kwara, Osun), Surulere (Lagos, Oyo), Bassa (Kogi, Plateau) — with many
rows and distinct coordinate clusters on each side. Five are single rows labelled Enugu that
carry Abia LGA names; all five also carry 0,0 coordinates and are quarantined on that ground.
**Consequence:** `(state, city_area)` is the unambiguous LGA key; `source_record.lga_id` alone
is not, and the handoff says so. Recorded in the provenance record.

---

## 7. Data quality

| Measure | Count |
|---|---|
| Emitted | 20,696 |
| With coordinates, plausible for the state | 20,696 (100%, by policy) |
| With a valid normalised phone | 20,135 (97.3%) |
| With opening hours | 20,480 (99.0%) |
| `type` / `emergency_capable` populated | 0 (by decision) |
| Quarantined — transposed, seen by the per-state yardstick | 9,911 |
| Quarantined — coordinates absent | 524 |
| Quarantined — transposed, seen by the national box | 106 |
| Quarantined — not in the state claimed | 81 |
| Quarantined — exact duplicate | 62 |
| Quarantined — exactly 0,0 | 5 |
| Quarantined — outside Nigeria | 4 |
| Quarantined — name empty | 1 |
| Remaining same name + state + LGA groups (candidates, not merged) | 477 |
| Remaining identical-coordinate groups (candidates, not merged) | 983 |

**Suspected transposed coordinates are refused, not exchanged** — by either instrument.
Exchanging would be a guess about which of two fields the source got wrong for a single row,
and a decision about correcting source data at the scale of a state.

**Looser duplicates are reported, not resolved.** Two facilities sharing a name within one LGA
at different points may be a duplicate or two genuine facilities; collapsing them would delete a
real clinic from a user's results.

---

## 8. Mobile compatibility — measured, not asserted

`reports/facilities_mobile_compat_v1.json` runs both artifacts through a port of
`lib/features/locator/facility_locator_service.dart` at wellapath-mobile `13be0d49` — the same
type chain, urgency sets, 20 km / 3-result sparse-coverage rule, haversine and `== true`
emergency test. **The Mobile repository was not modified.**

**Verdict: NOT COMPATIBLE as it stands.**

| Finding | Severity |
|---|---|
| **FCT and Kano — served by 1.1 — have no records**; by-location queries there return nothing for every urgency | **blocking** |
| `type` null → every non-emergency query returns nothing | **blocking** |
| `emergency_capable` null → emergency ordering degrades to distance | material |
| Artifact is **13.8×** the size of 1.1 (23.3 MB vs 1.70 MB), held in memory | material |
| Three states have no rows in the source | material |

---

## 9. Comparison with facilities 1.1

| | 1.1 | Candidate |
|---|---|---|
| Records | 5,344 | 20,696 |
| Bytes | 1,695,844 | 23,318,064 |
| States | 3 | 27 |
| States lost | — | **FCT, Kano** |

Matching by position (within 250 m, preferring identical normalised names): **429** exact,
**1,179** probable, **3,736** only in 1.1, **19,741** only in the candidate.

**The two datasets are not merged.** They have different provenance chains — 1.1 is GRID3 + OSM
plus a manual phone enrichment; the candidate is a single bulk registry export — and a fused
artifact could no longer answer where a record came from. The 45 manually verified Lagos phone
numbers in 1.1 are the only human-verified content in either dataset; if the candidate is
adopted they should be re-applied as an explicit, listed enrichment rather than silently
inherited.

---

## 10. Unresolved decisions

| # | Decision | Owner | Blocking |
|---|---|---|---|
| 1 | **Licence / reuse permission for the source** | Legal + engineering lead | **Publication** |
| 2 | **Source organisation and chain of custody** — who produced this, and is the spreadsheet-exported copy authoritative? | Engineering lead | Provenance |
| 3 | **`facility_level` → Mobile `type` mapping** | Product | **Mobile use** |
| 4 | **`emergency_capable` rule**, or an evidenced field from the source owner | Product | Emergency ordering |
| 5 | **Public-use basis for `phone_number`**, before any `tel:` action | Product | Public presentation |
| 6 | Three states with no rows and 313 missing LGA names | Source owner | Coverage |
| 7 | Artifact size / distribution profile (23 MB) | Engineering lead | Delivery |
| 8 | Looser duplicate consolidation (477 name groups, 983 point groups) | Product + data | Quality |
| 9 | Whether to re-apply 1.1's 45 verified phone numbers | Product | Quality |
| 10 | `facility_type_id`, `facility_level_option_id`, `facility_level_options_category_id` — present with no name column and no dictionary | Source owner | Interpretation |
| 11 | Whether the 524 coordinate-less rows should be reinstated for name search (quarantined by policy, listed) | Product | Coverage |
| 12 | Uncertainty of the per-state instrument where latitude ≈ longitude (Bauchi, Gombe, Yobe, Borno, Kogi); state polygons would resolve it | Engineering lead | Quality |
| 13 | **Whether to apply the transposition to the 9,911 rows refused as `coordinates_swapped_suspected_by_state`** — restores FCT, Kano, Katsina, Kwara, Niger, Taraba, Zamfara and most of Jigawa, Kaduna and Benue; or return the file to the source owner for correction | Engineering lead + source owner | **Coverage; Mobile parity with 1.1** |

Nothing in this work grants Product approval, clinical approval, publication authorization or
activation authorization, and none is recorded.
