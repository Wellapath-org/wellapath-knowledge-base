# Mobile Handoff — Facilities 2.0 (candidate)

**From:** Knowledge Base / Data Engineering
**Phase:** Nationwide Facilities / Step 2
**Action required from Mobile right now:** **none.** Do not ship a build that depends on
this artifact. It is here so the contract is not guessed when the time comes.

---

## 1. Bottom line

- The candidate is **not published and not approved**, and the source's licence and
  publishing organisation are **not established** — a blocking gate on its own. Build 210 is
  frozen; this is for a later build only, and only after the gates in §9.
- **Two things your users have today are missing from it.** The source writes latitude and
  longitude the wrong way round for whole northern states; those rows are refused, and as a
  result **FCT and Kano — both in facilities 1.1 — have no records at all** (§6).
- **Your current build loads it without crashing and returns nothing for three of four
  urgency paths.** That is measured (§6), not assumed. The fix is a Product decision, not a
  Mobile change.
- Search, distance sorting and filtering stay **on-device**. Nothing in this artifact or this
  handoff asks the app to transmit a coordinate, a search string, a location history or any
  health datum. That posture is unchanged.

## 2. Artifact

| Field | Value |
|---|---|
| Artifact ID | `facilities` (unchanged) |
| Version | `2.0` |
| Schema | `2.0` — `schema/facilities.v2.schema.json` (`f716f184f6cb4f7ba3e28aba8598ea0bb883cd05c5805bdd5c6a714394f59837`) |
| Location | `candidate/facilities.ng.v2.0.json` (knowledge-base repo) |
| SHA-256 | `e8bc4d72054b71004ed91af169432789830274f7db8ef25e8de5d4ffab9cd791` |
| Bytes | 23,318,064 (facilities 1.1: 1,695,844 — **13.8×**) |
| Records | **20,696** (facilities 1.1: 5,344) |
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
    "may_publish": false, "release_date": null, "generated_at": "2026-09-14T00:00:00Z",
    "total_facilities": 20696,
    "states_covered": [ "Abia", ... 27 ],
    "states_absent": [ "Adamawa", "Kebbi", "Sokoto" ],                     // no rows in the source
    "states_with_no_emitted_records": [ "FCT", "Kano", "Katsina", "Kwara", "Niger", "Taraba", "Zamfara" ],
    "coverage_claim": "NOT nationwide. ...",
    "source": { "sha256": "e598cecc…", "licence": null, "organization": null,
                "snapshot_last_updated_at": "2026-07-21T13:15:26", ... },
    "deduplication": { "rule_id": "exact_match_v1", "rows_removed": 62, "values_merged": false, ... },
    "coordinate_policy": "...", "coordinate_reference": { "records_moved_or_exchanged": 0, ... },
    "unresolved_fields": { "type": "...", "emergency_capable": "...",
                           "type_vocabulary": ["hospital","clinic","health_centre","pharmacy","laboratory","other"] },
    ...
  },
  "facilities": [ { ...one object per facility, see §4... } ]
}
```

Records are sorted by `(state, city_area, casefold(name), source_id)` — a total order, so the
file is byte-stable across regenerations. Do not rely on the order for anything user-facing;
sort on-device as you do today.

## 4. Every field

`N` in the Null column means the field can be `null`; `—` means it never is.

### The ten fields your current build reads (unchanged names)

| Field | JSON type | Null | Values / format | Notes |
|---|---|---|---|---|
| `facility_id` | string | — | `ng_nhf_<digits>` | Stable. **Disjoint from 1.1's `ng_lag_001` style ids** — no id exists in both artifacts |
| `name` | string | — | ≥ 1 char, NFC, single-spaced | Source casing kept; some names are ALL CAPS. Apply display casing on-device if you want it |
| `type` | null | **always null** | future enum: `hospital`, `clinic`, `health_centre`, `pharmacy`, `laboratory`, `other` | See §6. The enum is declared in `_metadata.unresolved_fields.type_vocabulary`; parse defensively (`facilityTypeFromJson` in the Dart file) |
| `state` | string | — | one of the 27 covered states | `Akwa Ibom` (no hyphen). Compare case-insensitively as today. **No `FCT` or `Kano` record exists in this build** |
| `city_area` | string | — | the LGA name | 1.1 mixed LGA and free text; 2.0 is always the LGA |
| `latitude` | number | **—** | 4.0 … 14.0 | Non-null on every record by policy, and within 300 km of the state's reference point. Your null path (`distance = infinity`) is still correct and simply unexercised |
| `longitude` | number | **—** | 2.5 … 15.0 | Same |
| `phone` | string | N | `^\+234[789][01]\d{8}$` | Normalised, never invented. Public-use intent is not established: **do not offer a `tel:` action until Product records a basis** |
| `opening_hours` | string | N | `24_hours` \| `12_hours` \| `8_hours` \| `other` | Closed enum, not free text as in 1.1. Treat an unknown string as `other` |
| `emergency_capable` | null | **always null** | — | See §6. Your `== true` test treats it as false, which is the safe direction |

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
| `source_record` | object | — | the six provenance fields below | Always present. Identity and provenance only; nothing here is for display |
| `source_record.source_id` | string | — | digits | Joins to the pinned source CSV |
| `source_record.source_unique_id` | string | — | e.g. `01/01/1/2/2/0023` | The registry's own code |
| `source_record.state_id` | string | — | digits | One id per state |
| `source_record.lga_id` | string | — | digits | **Name-scoped, not state-scoped** (§5). Never key on it alone |
| `source_record.ward_id` | string | N | digits | |
| `source_record.source_updated_at` | string | N | `YYYY-MM-DDTHH:MM:SS`, **no zone** | The source's audit timestamp; the zone is not declared, so none is claimed |

Unknown keys may appear in later versions. Ignore them; do not reject the artifact.

## 5. Keying and normalisation you must respect

- **LGA identity is `(state, city_area)`.** Six LGA names exist in two states each
  (Nasarawa, Obi, Ifelodun, Irepodun, Surulere, Bassa) and the source gives each name a single
  `lga_id`. Filtering by `city_area` without `state` conflates them.
- `state` and `city_area` are trimmed, single-spaced, NFC. Compare with `toLowerCase()` as
  today; no LGA has two spellings within a state.
- `facility_id` values are unique and stable across regenerations. They are not sequential.

## 6. Expected behaviour of your current locator — measured

`reports/facilities_mobile_compat_v1.json` runs both artifacts through an exact port of
`lib/features/locator/facility_locator_service.dart` (wellapath-mobile `13be0d49`). The
Mobile repository was not modified.

| Path | 1.1 | 2.0 candidate | Why |
|---|---|---|---|
| `emergency` (nearby) | 30 results, emergency-capable first | 30 results, **pure distance order** | `emergency_capable` is null everywhere |
| `urgent` / `non_urgent` / `self_care` (nearby) | 30 | **0** | filter is `allowedTypes.contains(type)`; `type` is null; the sparse-coverage fallback widens the type set but never drops the filter |
| by location, `FCT / Abuja Municipal Area Council` | 30 / 10 / 10 / 30 | **0 for every urgency** | no FCT record exists |
| by location, `Kano / Ajingi` | 30 / 0 / 0 / 30 | **0 for every urgency** | no Kano record exists |

**Verdict: NOT COMPATIBLE as it stands.** Two blocking findings:

1. `type` is null on every record — a Product decision on how (or whether) to map
   `facility_level` into the type vocabulary, or a change to the filter. Nothing in this
   repository decides that.
2. **FCT and Kano** — served by facilities 1.1 — have no records. The source writes their
   latitude and longitude the **wrong way round** (Kano city at 8.5N 12.0E instead of 12.0N
   8.5E — inside Nigeria, 500 km away in Taraba). The pipeline refuses such rows rather than
   exchanging the values; 9,911 rows were refused this way across FCT, Kano, Katsina, Kwara,
   Niger, Taraba, Zamfara and most of Jigawa, Kaduna and Benue. A user in Abuja asking for
   "nearby" gets the 30 nearest surviving records, which are in Nasarawa or Kogi. Resolution
   is the source owner's, or a recorded decision to apply the correction — not a Mobile change.

Also plan for: the artifact is 13.8× the size of 1.1 and your locator holds the decoded list
in memory; and users in Adamawa, Kebbi and Sokoto will see an empty locator because the
source has no rows there.

## 7. Backward compatibility and rollback

- Field access is unchanged for all ten 1.1 fields. A build that reads 2.0 must **still read
  1.1 correctly**: in 1.1, `type` is a non-null string, `emergency_capable` is a non-null
  boolean, `opening_hours` is free text, and `facility_id` is `ng_<state>_<nnn>`. Branch on
  the presence of `_metadata.schema_version == "2.0"` (or of the `services` key), never on a
  parsed version number, and never throw on either shape.
- Rollback target is `facilities.ng.v1.1.json` at the hash in §2. The candidate has never been
  active, so nothing has to roll back today. If it is ever activated, rolling back **restores
  FCT and Kano** — treat that as a reason to keep 1.1 loadable, not a footnote.
- Do not cache a `/config` entry for 2.0: none exists.

## 8. Sorting and filtering expectations (on-device)

- Distance: haversine from the user's point, as now. Every record has a point, and every
  point is plausible for its state.
- Name search: match on `name` after your own normalisation; consider also matching
  `city_area` and `state` so a user can type an LGA.
- Filters: `state`, `city_area`, `facility_level`, `ownership`, `opening_hours`,
  `operational_status` are safe to filter on. `services.*` flags may be **displayed** only
  when `true` or `false`; **do not filter on a null** as if it were false, and do not add a
  service filter to the UI on the strength of this data alone — that is an unverified service
  filter, which this handoff does not authorise.
- Never transmit the user's coordinates, the query string or any result set. Nothing here
  requires it.

## 9. Gates before any of this ships

All false today, recorded in `candidate/facilities.manifest.candidate.json`:
source licence · source organisation · Product `type` mapping · `emergency_capable` rule ·
phone public-use basis · Mobile compatibility · Product approval · Clinical approval ·
Engineering-lead approval · upload · `/config` wiring · `may_publish`.

## 10. Do not

- Do not ship a build that depends on the candidate.
- Do not infer `type` or `emergency_capable` on-device from `name`, `facility_level` or
  `services`. If Product decides a mapping, it will arrive in the artifact.
- Do not treat `services.ambulance == true` as emergency capability.
- Do not offer `tel:` on `phone` before the public-use basis is recorded.
- Do not key an LGA on `lga_id`.
- Do not exchange latitude and longitude on-device for any record. Refused rows are not in
  the artifact; kept rows are plausible as given.
- Do not send coordinates, search text, location history or any health datum anywhere.
