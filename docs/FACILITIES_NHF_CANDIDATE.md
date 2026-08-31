# Nationwide facilities candidate — NHF source, Step 1

> **Candidate only.** `candidate/facilities.ng.v2.0.json` is unapproved and unpublished.
> `facilities.ng.v1.1.json` remains the active artifact and is byte identical.
> Nothing was uploaded, published, activated or deployed, and `/config` is unchanged.

```bash
python3 tools/run_facilities_checks.py     # everything
```

---

## 1. What the source actually is

The supplied file is `nigeria_health_facilities.csv`, preserved unchanged at
`facilities/source/nigeria_health_facilities.csv` (20,913,558 bytes, sha256
`e598cecc…becb3`). Full record: `facilities/source/nhf_provenance_v1.json`.

**What is established:** the bytes, their structure (a title line, a 90-column header, 31,390
uniform data rows), and the dataset's own internal audit timestamps, which put the snapshot no
earlier than 2026-07-21.

**What is not, and is recorded as not:**

| Question | Answer |
|---|---|
| Publishing organisation | **Not established.** The file names none — no publisher field, no copyright line, no contact. The brief calls it "NHF"; the data does not. |
| Licence or reuse permission | **Not established.** Nothing accompanied the data. **This alone blocks publication**, independent of any technical readiness. |
| Delivery URL | None. The only technical evidence of origin is a macOS `WhereFroms` attribute naming **Apple Numbers**, so the file passed through a spreadsheet rather than arriving as a pristine upstream export. |
| Data dictionary | None supplied. Mitigated: every `*_id` column has a `*_name` column beside it, and each id maps to exactly one name across all 31,390 rows — verified, not assumed. |
| Contact fields intended for public use | **Not established.** See §5. |
| Completeness / accuracy | **Not established.** Every row carries `verify_note: "Auto-approved via bulk import"`. No record in this dataset was individually verified. |

---

## 2. "Nationwide" is a claim the data does not support

| | |
|---|---|
| States with records | **33 of 36**, plus the FCT |
| **States with no records at all** | **Adamawa, Kebbi, Sokoto** |
| Distinct LGA names | **680 of Nigeria's 774** |
| Spelling variant found | `Akwa-Ibom`, normalised to `Akwa Ibom` through the explicit state table |

This is the headline finding. A user in Sokoto gets an empty locator. The artifact states the
gap in its own `_metadata.coverage_claim` rather than leaving a reader to discover it.

---

## 3. What was built

31,390 source rows → **31274 emitted**, **116 quarantined**, and the two numbers add up. No row was
silently discarded.

| Deliverable | Path |
|---|---|
| Source bytes (unchanged) | `facilities/source/nigeria_health_facilities.csv` |
| Provenance record | `facilities/source/nhf_provenance_v1.json` |
| Canonical schema | `schema/facilities.v2.schema.json` |
| Generator | `tools/build_facilities_candidate.py` |
| Candidate artifact | `candidate/facilities.ng.v2.0.json` |
| Data-quality report | `reports/facilities_quality_v1.json` |
| Quarantine report | `reports/facilities_quarantine_v1.json` |
| Comparison with 1.1 | `reports/facilities_comparison_v1.json` |
| Mobile compatibility | `reports/facilities_mobile_compat_v1.json` |
| Publication dry-run plan | `publication/plans/facilities.ng.v2.0.dryrun.json` |

### Why version 2.0

Not assumed — assessed. The schema is *additive*: all ten fields facilities 1.1 emits are
present under the same names and types, so the Mobile consumer's field access is unchanged.
That alone would argue for a minor bump. What makes it major is behaviour: `type` and
`emergency_capable` are null on every record, so a consumer reading the same shape gets
different results. A shape-compatible artifact that changes what the app shows is not a minor
version.

---

## 4. The two fields that are deliberately empty

These are the substance of this step, and neither is a defect in the tooling.

**`type` — null on every record, blocking.** Mobile filters non-emergency results by `type`
against `{hospital, clinic, health_centre, pharmacy}`. This source has no such column. What it
has is `facility_level` — Primary, Secondary, Tertiary — which is a *tier of care*, not a kind
of facility: a Primary facility may be a health centre, a clinic or a dispensary, and the
source does not say which. Mapping tier to kind decides which facilities a user is shown for
self-care versus urgent care, so it is a Product decision. `tools/facilities/mappings.py`
carries the table as deliberately empty, and a test fails if it is filled in.

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

**One personal email address was found typed into a facility's `physical_location` field** and
is not in the candidate. The value was dropped and the removal counted
(`address_contact_detail_in_free_text_field: 1`); the facility itself is legitimate and was
kept. Free-text fields are now screened for contact-shaped values, and the quarantine report
does not reproduce them.

---

## 6. Data quality

| Measure | Count |
|---|---|
| Emitted | 31274 |
| With coordinates | 30750 |
| Without coordinates (kept; Mobile sorts them last) | 524 |
| With a valid normalised phone | 29823 |
| Quarantined — suspected swapped coordinates | 106 |
| Quarantined — outside Nigeria | 4 |
| Quarantined — exactly 0,0 | 5 |
| Quarantined — name empty or a contact detail | 1 |
| Same name + state + LGA (duplicate *candidates*, not merged) | 1094 groups |
| Identical coordinates (duplicate *candidates*, not merged) | 1877 groups |

**Suspected swapped coordinates are refused, not swapped.** 106 rows are implausible as given
and plausible with latitude and longitude exchanged. Swapping them would be a guess about which
of two fields the source got wrong, and a wrong guess moves a facility hundreds of kilometres.

**Duplicates are reported, not resolved.** Two facilities sharing a name within one LGA may be
a duplicate or two genuine facilities; collapsing them would delete a real clinic from a user's
results.

---

## 7. Mobile compatibility — measured, not asserted

`reports/facilities_mobile_compat_v1.json` runs both artifacts through a port of
`lib/features/locator/facility_locator_service.dart` at wellapath-mobile `13be0d49` — the same
type chain, urgency sets, 20 km / 3-result sparse-coverage rule, haversine and `== true`
emergency test. **The Mobile repository was not modified.**

**Verdict: NOT COMPATIBLE as it stands.** Every structural requirement is met — all ten fields
on every record, correct types, null handling consistent with the consumer — and three of the
four urgency paths return **zero results**, because `type` drives the filter and cannot be
populated from this source without a Product decision. Emergency queries still work, with
ordering degraded to pure distance.

| Finding | Severity |
|---|---|
| `type` null → every non-emergency query returns nothing | **blocking** |
| `emergency_capable` null → emergency ordering degrades to distance | material |
| Artifact is **18×** the size of 1.1 (31.0 MB vs 1.70 MB), held in memory | material |
| Three states have no records | material |

Size options, none chosen here: compact serialisation (~22.5 MB), a distribution profile with
only the ten fields Mobile reads (~10.3 MB), or per-state partitioning. All are distribution
decisions.

---

## 8. Comparison with facilities 1.1

| | 1.1 | Candidate |
|---|---|---|
| Records | 5,344 | 31274 |
| Bytes | 1,695,844 | 30961471 |
| States | 3 | 34 |

Matching by position (within 250 m, preferring identical normalised names): **429** exact,
**1187** probable, **3728** only in 1.1, **30312** only in the candidate. No state present in 1.1 is
lost.

**The two datasets are not merged.** They have different provenance chains — 1.1 is GRID3 + OSM
plus a manual phone enrichment; the candidate is a single bulk registry export — and a fused
artifact could no longer answer where a record came from, which is the question every later
data dispute turns on. The 45 manually verified Lagos phone numbers in 1.1 are the only
human-verified content in either dataset; if the candidate is adopted they should be re-applied
as an explicit, listed enrichment rather than silently inherited.

---

## 9. Coverage by state

| State | Facilities | LGAs |
|---|---|---|
| Abia | 756 | 17 |
| Akwa Ibom | 733 | 31 |
| Anambra | 1352 | 21 |
| Bauchi | 689 | 20 |
| Bayelsa | 76 | 1 |
| Benue | 1670 | 23 |
| Borno | 343 | 23 |
| Cross River | 1157 | 18 |
| Delta | 861 | 25 |
| Ebonyi | 415 | 13 |
| Edo | 458 | 18 |
| Ekiti | 582 | 16 |
| Enugu | 929 | 16 |
| FCT | 664 | 6 |
| Gombe | 743 | 11 |
| Imo | 1498 | 27 |
| Jigawa | 1053 | 27 |
| Kaduna | 1113 | 23 |
| Kano | 1441 | 44 |
| Katsina | 425 | 24 |
| Kogi | 1138 | 21 |
| Kwara | 847 | 16 |
| Lagos | 1521 | 20 |
| Nasarawa | 665 | 13 |
| Niger | 822 | 25 |
| Ogun | 1081 | 20 |
| Ondo | 861 | 17 |
| Osun | 1676 | 30 |
| Oyo | 1593 | 33 |
| Plateau | 1591 | 17 |
| Rivers | 893 | 23 |
| Taraba | 948 | 16 |
| Yobe | 498 | 17 |
| Zamfara | 182 | 14 |

---

## 10. Unresolved decisions

| # | Decision | Owner | Blocking |
|---|---|---|---|
| 1 | **Licence / reuse permission for the source** | Legal + engineering lead | **Publication** |
| 2 | **Source organisation and chain of custody** — who produced this, and is the spreadsheet-exported copy authoritative? | Engineering lead | Provenance |
| 3 | **`facility_level` → Mobile `type` mapping** | Product | **Mobile use** |
| 4 | **`emergency_capable` rule**, or an evidenced field from the source owner | Product | Emergency ordering |
| 5 | **Public-use basis for `phone_number`**, before any `tel:` action | Product | Public presentation |
| 6 | Three missing states and 94 missing LGAs | Source owner | Coverage |
| 7 | Artifact size / distribution profile | Engineering lead | Delivery |
| 8 | Duplicate consolidation (1229 groups) | Product + data | Quality |
| 9 | Whether to re-apply 1.1's 45 verified phone numbers | Product | Quality |
| 10 | `facility_type_id`, `facility_level_option_id`, `facility_level_options_category_id` — present with no name column and no dictionary | Source owner | Interpretation |

Nothing in this step grants Product approval, publication authorization or activation
authorization, and none is recorded.
