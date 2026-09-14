# Mobile Handoff — Facilities 2.0 (candidate)

**From:** Knowledge Base / Data Engineering
**Phase:** Nationwide Facilities / Step 3
**Action required from Mobile right now:** **none.** Do not ship a build that depends on
this artifact, and do not implement against it yet. It is here so the contract is not guessed
when the decisions in §9 are made.

---

## 1. Bottom line

- The candidate is **not published and not approved**, and the source's licence and
  publishing organisation are **not established** — a blocking gate on its own
  (`docs/FACILITIES_SOURCE_AUTHORIZATION_CHECKLIST.md`). Build 210 is frozen.
- **Coverage now matches v1.1.** Every state v1.1 serves (Lagos, FCT, Kano) has records. The
  source writes latitude and longitude the wrong way round for whole northern states; 10,862
  records in this candidate carry the pair exchanged under a strict, audited rule, and say so
  on the record (§4, `source_record.coordinate_transformation`).
- **Your current build loads it without crashing and returns nothing for three of four
  urgency paths**, because `type` is null and your filter drops null. That is measured (§6).
  The contract for the next build is in §7 and is the opposite behaviour.
- Search, distance sorting and filtering stay **on-device**. Nothing here asks the app to
  transmit a coordinate, a search string, a location history or any health datum.

## 2. Artifact

| Field | Value |
|---|---|
| Artifact ID | `facilities` (unchanged) |
| Version | `2.0` |
| Schema | `2.0` — `schema/facilities.v2.schema.json` (`fc96d9142c9e669af6c02d6bb4e186fef025aa5a841fc65da4da2aff394c2e24`) |
| Location | `candidate/facilities.ng.v2.0.json` (knowledge-base repo) |
| SHA-256 | `8fb80d3d2bb491f25946c3741c201966fd52bb373aa3d71cc72162521dbb6da2` |
| Bytes | 36,077,142 (facilities 1.1: 1,695,844 — **21.3×**) |
| Records | **29,028** (facilities 1.1: 5,344) |
| States with records | 34 (33 + FCT). **Adamawa, Kebbi, Sokoto** have no rows in the source |
| `release_status` / `publication_status` | `candidate_unapproved` (both pinned by schema `const`) |
| `may_publish` | `false` |
| Manifest entry | `candidate/facilities.manifest.candidate.json`, `IS_LIVE_MANIFEST: false` |
| Rollback target | `facilities.ng.v1.1.json`, `25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398` |
| Typed definitions | `facility_types.dart` in this directory |

## 3. Top-level shape

```jsonc
{
  "_metadata": {
    "artifact_id": "facilities", "version": "2.0", "schema_version": "2.0", "country": "ng",
    "release_status": "candidate_unapproved", "publication_status": "candidate_unapproved",
    "may_publish": false, "release_date": null, "generated_at": "2026-09-14T12:00:00Z",
    "total_facilities": 29028,
    "states_covered": [ "Abia", ... 34 ], "states_absent": [ "Adamawa", "Kebbi", "Sokoto" ],
    "states_with_no_emitted_records": [],
    "coverage_claim": "NOT nationwide. ...",
    "source": { "sha256": "e598cecc…", "licence": null, "organization": null, ... },
    "deduplication": { "rule_id": "exact_match_v1", "rows_removed": 323, "values_merged": false, ... },
    "coordinate_remediation": { "rule_id": "coordinate_orientation_v1",
                                "accepted_unchanged": 18210, "accepted_after_verified_swap": 11141,
                                "quarantined_ambiguous": 1442, "quarantined_invalid": 67,
                                "records_corrected_in_artifact": 10862, ... },
    "unresolved_fields": { "type": "...", "emergency_capable": "...",
                           "type_vocabulary": ["hospital","clinic","health_centre","pharmacy","laboratory","other"],
                           "consumer_contract": "..." },
    ...
  },
  "facilities": [ { ...one object per facility, see §4... } ]
}
```

Records are sorted by `(state, city_area, casefold(name), source_id)` — a total order, so the
file is byte-stable across regenerations. Sort on-device as you do today.

## 4. Every field

`N` in the Null column means the field can be `null`; `—` means it never is.

### The ten fields your current build reads (unchanged names)

| Field | JSON type | Null | Values / format | Notes |
|---|---|---|---|---|
| `facility_id` | string | — | `ng_nhf_<digits>` | Stable. **Disjoint from 1.1's `ng_lag_001` style ids** — no id exists in both artifacts |
| `name` | string | — | ≥ 1 char, NFC, single-spaced | Source casing kept; some names are ALL CAPS. Apply display casing on-device if you want it |
| `type` | null | **always null** | future enum: `hospital`, `clinic`, `health_centre`, `pharmacy`, `laboratory`, `other` | **Null is not a member of the enum.** See §7. Parse defensively (`facilityTypeFromJson`) |
| `state` | string | — | one of the 34 covered states | `Akwa Ibom` (no hyphen), `FCT`. Compare case-insensitively as today |
| `city_area` | string | — | the LGA name | 1.1 mixed LGA and free text; 2.0 is always the LGA |
| `latitude` | number | **—** | 4.0 … 14.0 | Non-null on every record and **verified inside the declared state**. Your null path is still correct and simply unexercised |
| `longitude` | number | **—** | 2.5 … 15.0 | Same |
| `phone` | string | N | `^\+234[789][01]\d{8}$` | Normalised, never invented. Public-use intent is not established: **do not offer a `tel:` action until Product records a basis** (FAC-D003) |
| `opening_hours` | string | N | `24_hours` \| `12_hours` \| `8_hours` \| `other` | Closed enum, not free text as in 1.1. Treat an unknown string as `other` |
| `emergency_capable` | null | **always null** | — | See §7. No record carries verified positive evidence |

### Added in 2.0 (ignore until you need them)

| Field | JSON type | Null | Values | Notes |
|---|---|---|---|---|
| `lga` | string | — | = `city_area` | Explicit name for what `city_area` holds |
| `ward` | string | N | free text | Source value; often `"Unknown"` |
| `address` | string | N | free text | Contact-shaped values removed |
| `facility_level` | string | N | `Primary` \| `Secondary` \| `Tertiary` | Tier of care, **not** a facility kind |
| `ownership` | string | N | `Public` \| `Private` | |
| `ownership_type` | string | N | `local_government`, `state_government`, `federal_government`, `private_for_profit`, `private_not_for_profit`, `military_paramilitary` | |
| `operational_status` | string | N | `functional`, `non_functional`, `closed`, `under_renovation`, `unknown` | `"unknown"` = the source said Unknown; `null` = the source said nothing |
| `registration_status` | string | N | `registered`, `provisionally_registered`, `pending_registration`, `registration_suspended`, `registration_cancelled`, `unknown` | most are `unknown` |
| `license_status` | string | N | `licensed`, `not_licensed`, `license_cancelled`, `unknown` | most are `unknown` |
| `beds` | integer | N | ≥ 0 | |
| `services` | object | — | the five flags below | Always present; each flag is tri-state |
| `services.onsite_laboratory` | boolean | N | | Each flag is read from exactly one source Yes/No column. **null means "the source did not say", never "no"** |
| `services.onsite_imaging` | boolean | N | | |
| `services.onsite_pharmacy` | boolean | N | | |
| `services.mortuary` | boolean | N | | |
| `services.ambulance` | boolean | N | | Not the same claim as emergency capability. Do not treat it as one |
| `source_record` | object | — | the nine provenance fields below | Always present. Identity and provenance only; nothing here is for display |
| `source_record.source_id` | string | — | digits | Joins to the pinned source CSV |
| `source_record.source_unique_id` | string | — | e.g. `01/01/1/2/2/0023` | The registry's own code |
| `source_record.state_id` | string | — | digits | One id per state |
| `source_record.lga_id` | string | — | digits | **Name-scoped, not state-scoped** (§5). Never key on it alone |
| `source_record.ward_id` | string | N | digits | |
| `source_record.source_updated_at` | string | N | `YYYY-MM-DDTHH:MM:SS`, **no zone** | The source's audit timestamp; the zone is not declared, so none is claimed |
| `source_record.coordinate_transformation` | string | — | `none` \| `swap_lat_lon` | `swap_lat_lon` (10,862 records): the source's latitude and longitude were exchanged under `coordinate_orientation_v1` because as given the pair was outside the declared state and exchanged it was strictly inside. Informational; **never re-exchange on-device** |
| `source_record.source_latitude` | number | N | | The source's latitude column, present only when the transformation is not `none` |
| `source_record.source_longitude` | number | N | | The source's longitude column, present only when the transformation is not `none` |

Unknown keys may appear in later versions. Ignore them; do not reject the artifact.

## 5. Keying and normalisation you must respect

- **LGA identity is `(state, city_area)`.** Six LGA names exist in two states each
  (Nasarawa, Obi, Ifelodun, Irepodun, Surulere, Bassa) and the source gives each name a single
  `lga_id`. Filtering by `city_area` without `state` conflates them.
- `state` and `city_area` are trimmed, single-spaced, NFC. Compare with `toLowerCase()` as
  today; no LGA has two spellings within a state.
- `facility_id` values are unique and stable across regenerations. They are not sequential.

## 6. Behaviour of your **current** locator — measured

`reports/facilities_mobile_compat_v1.json` runs both artifacts through an exact port of
`lib/features/locator/facility_locator_service.dart` (wellapath-mobile `13be0d49`). The
Mobile repository was not modified.

| Path | 1.1 | 2.0 candidate | Why |
|---|---|---|---|
| `emergency` (nearby) | 30 results, emergency-capable first | 30 results, **pure distance order** | `emergency_capable` is null everywhere |
| `urgent` / `non_urgent` / `self_care` (nearby) | 30 | **0** | `allowedTypes.contains(type)` never contains null; the sparse-coverage fallback widens the set but never drops the filter |
| by location, `FCT / Abuja Municipal Area Council`, emergency | 30 | **30** | FCT recovered |
| by location, `Kano / Ajingi`, emergency | 30 | **26** | Kano recovered |

**Verdict: NOT COMPATIBLE as it stands**, for one blocking reason — the null-type filter.
Coverage is no longer a finding.

## 7. The contract for the next build — null type and emergency ordering

These are the rules the artifact's own metadata states (`_metadata.unresolved_fields.consumer_contract`).
Implement them **only** after the decisions in §9 are recorded; they are stated now so that
the decision is made against a known contract.

1. **Unknown facility types must not be filtered out.** A record whose `type` is `null` is
   "kind not stated", not "wrong kind". Every urgency path must include it. Do not map null to
   any member of the vocabulary, and do not infer a kind from `name`, `facility_level` or
   `services`.
2. **A missing type must never create an empty result list.** If a type filter would leave
   zero results, the filter is wrong, not the data: fall through to the unfiltered,
   distance-ordered list and say so in the UI if you must, but never show nothing.
3. **Emergency-capable prioritisation may occur only for records with verified positive
   evidence** — `emergency_capable == true`. Null is not "capable" and not "incapable"; it
   carries no ordering weight. Never derive capability from `services.ambulance`,
   `facility_level`, `type` or `name`.
4. **Where no verified emergency-capable record exists** — which is every record in this
   candidate — **the consumer requires an explicit Product/Clinical fallback decision**
   (FAC-D002 in `docs/FACILITIES_DECISIONS_REQUIRED.md`). Until it is recorded, the only
   defensible behaviour is distance order. Data Engineering must not invent one and has not.

Test against `facilityTypeFromJson(null) == null` and `emergencyCapable == true`, never
`!= false`.

## 8. Backward compatibility and rollback

- Field access is unchanged for all ten 1.1 fields. A build that reads 2.0 must **still read
  1.1 correctly**: in 1.1, `type` is a non-null string, `emergency_capable` is a non-null
  boolean, `opening_hours` is free text, and `facility_id` is `ng_<state>_<nnn>`. Branch on
  `_metadata.schema_version == "2.0"` (or the presence of `services`), never on a parsed
  version number, and never throw on either shape.
- Rollback target is `facilities.ng.v1.1.json` at the hash in §2. The candidate has never been
  active, so nothing has to roll back today.
- Do not cache a `/config` entry for 2.0: none exists.

## 9. Gates and decisions before any of this ships

Gates, all false today (`candidate/facilities.manifest.candidate.json`): source authorization
checklist (nine items, all missing) · Product `type` mapping (FAC-D001) · `emergency_capable`
fallback (FAC-D002, Product + Clinical) · phone public-use basis (FAC-D003) · acceptance of the
coordinate rule (FAC-D004) · Product, Clinical and Engineering-lead approval · upload · `/config`
wiring · `may_publish`.

## 10. Sorting and filtering expectations (on-device)

- Distance: haversine from the user's point, as now. Every record has a point, and every
  point is verified inside its state.
- Name search: match on `name` after your own normalisation; consider also matching
  `city_area` and `state` so a user can type an LGA.
- Filters: `state`, `city_area`, `facility_level`, `ownership`, `opening_hours`,
  `operational_status` are safe to filter on. `type` is safe to filter on **only** under rule
  1 of §7. `services.*` flags may be **displayed** only when `true` or `false`; **do not filter
  on a null** as if it were false, and do not add a service filter to the UI on the strength
  of this data alone — that is an unverified service filter, which this handoff does not
  authorise.
- Never transmit the user's coordinates, the query string or any result set.

## 11. Do not

- Do not ship a build that depends on the candidate.
- Do not infer `type` or `emergency_capable` on-device from `name`, `facility_level` or
  `services`. If Product decides a mapping, it will arrive in the artifact.
- Do not drop a record because its `type` is null; do not show an empty list because of it.
- Do not treat `services.ambulance == true` as emergency capability.
- Do not offer `tel:` on `phone` before the public-use basis is recorded.
- Do not key an LGA on `lga_id`.
- Do not exchange latitude and longitude on-device. Emitted pairs are already oriented.
- Do not send coordinates, search text, location history or any health datum anywhere.
