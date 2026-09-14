# Facilities 2.0 candidate — changelog against facilities 1.1

> **Candidate only.** `candidate/facilities.ng.v2.0.json` is `candidate_unapproved`,
> `may_publish: false`. `facilities.ng.v1.1.json` is the active artifact, is byte identical
> (`25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398`) and is the rollback
> target. Nothing was uploaded, published, activated or wired into `/config`.

| | facilities 1.1 (active) | facilities 2.0 (candidate, Step 3) |
|---|---|---|
| File | `facilities.ng.v1.1.json` | `candidate/facilities.ng.v2.0.json` |
| SHA-256 | `25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398` | `8fb80d3d2bb491f25946c3741c201966fd52bb373aa3d71cc72162521dbb6da2` |
| Bytes | 1,695,844 | 36,077,142 (×21.3) |
| Records | 5,344 | **29,028** (×5.43) |
| Schema | 1.0 (`facilities/facility_schema_v1.0.md`) | 2.0 (`schema/facilities.v2.schema.json`, `fc96d9142c9e669af6c02d6bb4e186fef025aa5a841fc65da4da2aff394c2e24`) |
| States with records | 3 (Lagos, FCT, Kano) | 34 (33 + FCT). **No 1.1 state lost.** Adamawa, Kebbi, Sokoto absent from the source |
| Source | GRID3 v2.0 + HOTOSM + 45 manually verified Lagos phones | one bulk registry export, `nigeria_health_facilities.csv` (`e598cecc…becb3`, 31,390 rows, snapshot ≤ 2026-07-21T13:15:26) |
| Licence | CC BY 4.0 / ODbL, recorded | **not established** — nine checklist items missing |
| Generated | 2026-07-26 | `2026-09-14T12:00:00Z` (fixed constant), generator `tools/build_facilities_candidate.py` 1.2.0 |
| Manifest entry | live `/config` | `candidate/facilities.manifest.candidate.json` (`IS_LIVE_MANIFEST: false`) |

Regenerate and verify everything with one command: `python3 tools/run_facilities_checks.py`.

---

## 1. Why 2.0, not 1.2

The schema is additive — all ten 1.1 fields are present under the same names — but two of
them change behaviour. `type` and `emergency_capable` are null on every record, and the
Mobile consumer filters and orders on both. A shape-compatible artifact that changes what the
app shows is a major version.

## 2. Field-level changes

### Unchanged in name and meaning (the Mobile surface)

| Field | 1.1 | 2.0 | Change |
|---|---|---|---|
| `facility_id` | `ng_<state>_<nnn>` | `ng_nhf_<source id>` | New lineage; **no id is shared** between the two artifacts |
| `name` | title-cased by hand | source spelling, NFC, whitespace collapsed | ALL-CAPS names are carried as such; re-casing corrupts acronyms |
| `type` | enum of 4 (populated) | **null on every record** | Behavioural change. Source has no facility-kind column. Product decision FAC-D001 pending; vocabulary declared, **null is not a member** |
| `state` | 3 values | 34 values | `Akwa-Ibom` → `Akwa Ibom` normalised; FCT stays `FCT` |
| `city_area` | LGA or free text | always the LGA name | Same field, tighter meaning |
| `latitude` / `longitude` | non-null | **non-null, verified inside the declared state; 10,862 records carry the source pair exchanged** under `coordinate_orientation_v1` | Rows without a usable pair, or ambiguous/invalid for their state, are quarantined |
| `phone` | E.164 or null | E.164 or null | 96.8% populated (1.1: 45 of 5,344). Public-use intent **not established** |
| `opening_hours` | free text or null | enum `24_hours` / `12_hours` / `8_hours` / `other` / null | Only the source's clean values are mapped |
| `emergency_capable` | boolean, never null | **null on every record** | Behavioural change. 1.1 derived it from `type == 'hospital'`; no source field supports it. No verified positive record exists |

### Added (not read by the current Mobile build)

`lga`, `ward`, `address`, `facility_level`, `ownership`, `ownership_type`,
`operational_status`, `registration_status`, `license_status`, `beds`, `services` (five
Yes/No/null flags, each bound to one source column), `source_record` (`source_id`,
`source_unique_id`, `state_id`, `lga_id`, `ward_id`, `source_updated_at`,
`coordinate_transformation`, `source_latitude`, `source_longitude`).

### Removed

Nothing. No 1.1 field was dropped.

## 3. Pipeline policies that shape the record set

| Policy | Rule | Rows in the pinned source |
|---|---|---|
| Not orientable | coordinates absent / unparseable / 0,0 → quarantined | 524 / 0 / 5 |
| **Orientation rule** `coordinate_orientation_v1` | membership of the pair as given and exchanged against the declared state, using the repository's GRID3 facility points (`docs/FACILITIES_COORDINATE_REMEDIATION.md`) | accepted unchanged **18,210** · accepted after verified swap **11,141** · ambiguous **1,442** · invalid **67** |
| Exact-duplicate collapse | same casefolded name + state + casefolded LGA + identical coordinates → smallest registry `unique_id` survives; **no values merged** | 322 groups, 323 rows (279 of them corrected rows) |
| Name guard | blank, placeholder, or a contact detail in place of a name → quarantined | 1 |
| Nothing invented | unmapped values → reported; absent → null; `Unknown` → `"unknown"` | see `_metadata.absence_counts`, `_metadata.unmapped_source_values` |

Row accounting: 31,390 source rows = 29,028 emitted + 2,362 quarantined. A test fails if it
does not balance.

## 4. Coverage and quality deltas

| Measure | 1.1 | 2.0 |
|---|---|---|
| States with records | 3 | 34 |
| Distinct LGA names | — | 679 of 774 |
| State/LGA pairs in the source with no surviving record | — | 8 |
| Records without coordinates | 0 | 0 (by policy) |
| Records without phone | 5,299 | 938 (3.2%) |
| Records without opening hours | 5,344 | 256 (0.9%) |
| Records without `type` | 0 | 29,028 (100%) |
| Records without `emergency_capable` | 0 | 29,028 (100%) |
| Positional match with 1.1 (≤ 250 m) | — | 957 exact-name, 1,985 probable; 2,402 1.1 records unmatched; 27,054 new |

Per state, including FCT (632 vs 614) and Kano (1,293 vs 2,040): `docs/FACILITIES_COORDINATE_REMEDIATION.md` §5.

## 5. Source findings recorded in this version

- **Latitude and longitude are transposed for whole states.** Every in-box row of the FCT,
  Kano, Katsina, Kwara, Taraba and Zamfara, and nearly every row of Jigawa, Kaduna, Niger and
  Benue, is outside its state as given and strictly inside it exchanged. Corrected under a
  strict rule with the source values kept on the record; corroborated by the *same facility's*
  independently published GRID3 point (within 20 km of the exchanged pair 3,005 times, of the
  pair as given 2 times, over 5,611 joinable rows). Whether the transposition arose upstream or
  in the spreadsheet the copy passed through is not established (AUTH-09).
- **`lga_id` is name-scoped.** Six homonymous LGA names carry one id in two states each.
  `(state, city_area)` is the only unambiguous LGA key.
- **`facility_type_id` is a near-copy of `facility_level`** (157 disagreements, no name
  column). Cross-tab published; not interpreted as a facility kind.
- Every source row is `Auto-approved via bulk import`. No record was individually verified.

## 6. Revisions across the three steps

| | Step 1 (`4afffe1`) | Step 2 (`4bb8e26`) | Step 3 |
|---|---|---|---|
| Records | 31,274 | 20,696 | **29,028** |
| Coordinate validation | national box only | box + centroid yardstick, refusing 9,911 | **GRID3 point-membership rule**, correcting 11,141 and holding 1,442 |
| FCT / Kano | present, mispositioned | **absent** | **632 / 1,293**, oriented |
| Rows without coordinates | 524 emitted with nulls | quarantined | quarantined |
| Exact duplicates | reported only | collapsed (62) | collapsed (323) |
| `source_record` | 2 fields | 6 fields | 9 fields (+ transformation, + source pair) |
| Manifest entry / audit / checklist | — | manifest | manifest + coordinate audit + source authorization checklist |

## 7. Rollback

The candidate has never been active, so there is nothing to roll back *from*. If it is ever
activated and withdrawn, the consumer returns to `facilities.ng.v1.1.json` at the hash above;
the manifest entry binds that target by version, hash and byte count. Because 2.0 nulls two
fields 1.1 populates, a consumer that has adapted to 2.0 must still read 1.1 correctly —
`mobile_handoff/facilities_v2/README.md` §8 states the requirement.

## 8. What this version does not do

No upload, no publication, no activation, no `/config` change, no telemetry, no service
filter beyond the five source-bound flags, no Emergency Hub change, no merge of the 1.1 and
2.0 lineages (option B evaluated and rejected), no coordinate invented, snapped or moved — only
exchanged under the audited rule — and no approval of any kind: product, clinical or
publication.
