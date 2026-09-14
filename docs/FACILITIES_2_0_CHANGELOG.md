# Facilities 2.0 candidate — changelog against facilities 1.1

> **Candidate only.** `candidate/facilities.ng.v2.0.json` is `candidate_unapproved`,
> `may_publish: false`. `facilities.ng.v1.1.json` is the active artifact, is byte identical
> (`25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398`) and is the rollback
> target. Nothing was uploaded, published, activated or wired into `/config`.

> **Headline.** The source writes latitude and longitude the wrong way round for whole
> states. 9,911 rows were refused on that ground. **FCT and Kano — both served by facilities
> 1.1 — have no records in this candidate.** See §5.

| | facilities 1.1 (active) | facilities 2.0 (candidate) |
|---|---|---|
| File | `facilities.ng.v1.1.json` | `candidate/facilities.ng.v2.0.json` |
| SHA-256 | `25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398` | `e8bc4d72054b71004ed91af169432789830274f7db8ef25e8de5d4ffab9cd791` |
| Bytes | 1,695,844 | 23,318,064 (×13.8) |
| Records | 5,344 | **20,696** (×3.87) |
| Schema | 1.0 (`facilities/facility_schema_v1.0.md`) | 2.0 (`schema/facilities.v2.schema.json`, `f716f184f6cb4f7ba3e28aba8598ea0bb883cd05c5805bdd5c6a714394f59837`) |
| States with records | 3 (Lagos, FCT, Kano) | 27; **FCT and Kano lost**; Adamawa, Kebbi, Sokoto absent from the source; Katsina, Kwara, Niger, Taraba, Zamfara emptied by refusal |
| Source | GRID3 v2.0 + HOTOSM + 45 manually verified Lagos phones | one bulk registry export, `nigeria_health_facilities.csv` (`e598cecc…becb3`, 31,390 rows, snapshot ≤ 2026-07-21T13:15:26) |
| Licence | CC BY 4.0 / ODbL, recorded | **not established** |
| Generated | 2026-07-26 | `2026-09-14T00:00:00Z` (fixed constant), generator `tools/build_facilities_candidate.py` 1.1.0 |
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
| `facility_id` | `ng_<state>_<nnn>` | `ng_nhf_<source id>` | New lineage; **no id is shared** between the two artifacts, so they can never be confused |
| `name` | title-cased by hand | source spelling, NFC, whitespace collapsed | ALL-CAPS names are carried as such; re-casing corrupts acronyms |
| `type` | enum of 4 (populated) | **null on every record** | Behavioural change. Source has no facility-kind column. Product decision pending; vocabulary declared in `_metadata.unresolved_fields.type_vocabulary` |
| `state` | 3 values | 27 values | `Akwa-Ibom` → `Akwa Ibom` normalised; FCT would stay `FCT` (no FCT record survives, §5) |
| `city_area` | LGA or free text | always the LGA name | Same field, tighter meaning |
| `latitude` / `longitude` | non-null | **non-null, and plausible for the state claimed** | Rows without a usable pair, or with a pair that is transposed or not in the state, are quarantined |
| `phone` | E.164 or null | E.164 or null | 97.3% populated (1.1: 45 of 5,344). Public-use intent **not established** |
| `opening_hours` | free text or null | enum `24_hours` / `12_hours` / `8_hours` / `other` / null | Only the source's clean values are mapped; the free-text tail is null and listed |
| `emergency_capable` | boolean, never null | **null on every record** | Behavioural change. 1.1 derived it from `type == 'hospital'`; no source field supports it |

### Added (not read by the current Mobile build)

`lga`, `ward`, `address`, `facility_level` (Primary/Secondary/Tertiary), `ownership`,
`ownership_type`, `operational_status`, `registration_status`, `license_status`, `beds`,
`services` (five Yes/No/null flags, each bound to one source column), `source_record`
(`source_id`, `source_unique_id`, `state_id`, `lga_id`, `ward_id`, `source_updated_at`).

### Removed

Nothing. No 1.1 field was dropped.

## 3. Pipeline policies that shape the record set

| Policy | Rule | Rows in the pinned source |
|---|---|---|
| Coordinate quarantine — national box | absent, unparseable, 0,0, outside Nigeria, or inside only if transposed | 639 (524, 0, 5, 4, 106) |
| Coordinate quarantine — per-state yardstick | > 150 km from the state's reference point as given and ≥ 2× closer transposed → **transposed**; > 300 km under either reading → **not in state**. Refused, **never exchanged** | **9,911** transposed, 81 not in state |
| Exact-duplicate collapse | same casefolded name + state + casefolded LGA + identical coordinates → one survivor, the smallest registry `unique_id`; **no values merged** | 62 pairs → 62 rows removed, each listed with its survivor |
| Name guard | blank, placeholder, or a contact detail in place of a name → quarantined | 1 |
| Nothing invented | unmapped values → reported; absent → null; `Unknown` → `"unknown"` | see `_metadata.absence_counts`, `_metadata.unmapped_source_values` |

Row accounting: 31,390 source rows = 20,696 emitted + 10,694 quarantined. A test fails if it
does not balance.

## 4. Coverage and quality deltas

| Measure | 1.1 | 2.0 |
|---|---|---|
| States with records | 3 | 27 (no FCT) |
| Distinct LGA names | — | 461 of 774 |
| State/LGA pairs in the source with no surviving record | — | 230 |
| Records without coordinates | 0 | 0 (by policy) |
| Records without phone | 5,299 | 561 (2.7%) |
| Records without opening hours | 5,344 | 216 (1.0%) |
| Records without `type` | 0 | 20,696 (100%) |
| Records without `emergency_capable` | 0 | 20,696 (100%) |
| Positional match with 1.1 (≤ 250 m) | — | 429 exact-name, 1,179 probable; 3,736 1.1 records unmatched; 19,741 new |

Full numbers: `reports/facilities_quality_v1.json`, `reports/facilities_comparison_v1.json`.

## 5. Source findings recorded in this version

- **Latitude and longitude are transposed for whole states.** Measured against an
  approximate per-state reference point (cross-checked: facilities 1.1's GRID3-derived
  medians for Lagos, FCT and Kano lie 7, 5 and 20 km from the points), every in-box row of
  FCT, Kano, Katsina, Kwara, Niger, Taraba and Zamfara, and ~95% of Jigawa and Kaduna, is
  far from its state as given and close to it transposed. The bounding box is blind to this
  — a northern transposition stays inside Nigeria — which is why Step 1 saw only the 106
  southern cases. The rows are refused with both distances recorded; **nothing is exchanged**,
  because whether to apply the correction is a decision, not a normalisation. Where a state's
  latitude and longitude are numerically close (Bauchi, Gombe, Yobe, Borno, Kogi) the
  instrument is uncertain and says so per state.
- **`lga_id` is name-scoped.** Six homonymous LGA names (Nasarawa, Obi, Ifelodun, Irepodun,
  Surulere, Bassa) carry one id in two states each. `(state, city_area)` is the only
  unambiguous LGA key; `source_record.lga_id` alone is not.
- **`facility_type_id` is a near-copy of `facility_level`** (157 disagreements, no name
  column). Cross-tab published; not interpreted as a facility kind.
- Every source row is `Auto-approved via bulk import`. No record was individually verified.

## 6. Revisions since the Step 1 candidate (commit `4afffe1`)

| | Step 1 | Step 2 |
|---|---|---|
| Records | 31,274 | 20,696 |
| Coordinate validation | national box only | box + per-state yardstick |
| Rows without coordinates | 524 emitted with nulls | quarantined |
| Transposed northern coordinates | emitted as given (undetected) | 9,911 refused |
| Exact duplicates | reported only | collapsed (62 among the surviving rows) |
| `source_record` | 2 fields | 6 fields (+ admin ids, + `source_updated_at`) |
| `_metadata` | — | + `publication_status`, `deduplication`, `coordinate_policy`, `coordinate_reference`, `states_with_no_emitted_records`, snapshot last-updated, type vocabulary |
| Manifest entry | none | `candidate/facilities.manifest.candidate.json` |

## 7. Rollback

The candidate has never been active, so there is nothing to roll back *from*. If it is ever
activated and withdrawn, the consumer returns to `facilities.ng.v1.1.json` at the hash above;
the manifest entry binds that target by version, hash and byte count. Because 2.0 nulls two
fields 1.1 populates and serves fewer states than 1.1 in two cases, a consumer that has
adapted to 2.0 must still read 1.1 correctly — `mobile_handoff/facilities_v2/README.md` §7
states the requirement.

## 8. What this version does not do

No upload, no publication, no activation, no `/config` change, no telemetry, no service
filter beyond the five source-bound flags, no Emergency Hub change, no merge of the 1.1 and
2.0 lineages, no exchange of any coordinate pair, and no approval of any kind — product,
clinical or publication.
