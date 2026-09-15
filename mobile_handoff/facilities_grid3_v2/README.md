# Mobile handoff — Facilities 2.0, GRID3 lineage (CANDIDATE, not for release)

**Status: `candidate_unapproved` / `may_publish: false`. Not served, not
uploaded, not approved. facilities 1.1 remains the artifact your build loads.
This handoff exists for contract review only.**

Two candidates, one distribution target:

- **Served candidate (what a manifest would point your loader at):**
  `candidate/facilities.ng.v2.0-grid3.served.json` —
  `44eabf634dc8be93595e1c9627b25d6eeb71f4ad7e0897d1ac0e08194523086c`,
  51,022 records, **9,804,802 bytes raw (gzip-9 2,256,033)**, compact JSON.
  Record shape verified against your PR #79 parser at `854377c0`:
  `{id, name, state, city_area, latitude, longitude, type?}` — `type` is
  present only with an FAC-D001-approved value; every omitted optional key
  (`type` where unmapped, `emergency_capable`, `phone`, `opening_hours`,
  `lga`) parses as null in your parser, which is the intended meaning. Top-level
  `schema_version: "2.0"`. The manifest sha256 is over these raw bytes,
  matching your loader's raw-body verification; gzip is a measurement only.
  Full contract evidence: `docs/FACILITIES_GRID3_SERVED.md`.
- **Master/audit candidate (never for distribution):**
  `candidate/facilities.ng.v2.0-grid3.json` —
  `92300c1624668d1af77ddbb0d37f0104d08aa5484ec7af8e792234c912930d7a`,
  69,535,390 bytes, full per-record `source_record` provenance
  (`schema/facilities_grid3.v2.schema.json`). Trace any served record to it
  (and to the licensed GRID3 source row) through `id` = `ng_g3_<globalid>`.

## What is different from the artifact you load today (1.1)

1. **Coverage** — all 36 states + FCT (1.1: Lagos, FCT, Kano). State/LGA/manual
   location search works nationwide: `state` is normalized to the canonical 37
   names, `(state, lga)` is the area key (844 pairs), and every record has
   in-state coordinates for distance ranking.
2. **`type` is populated under FAC-D001 (approved 2026-09-15).** The exact
   source-value → type mapping, applied from `facility_level_option` only
   (never the name):

   | Source `facility_level_option` | Records | `type` on the wire |
   |---|---|---|
   | General Hospital | 1,120 | `hospital` |
   | Teaching/Tertiary Hospital | 87 | `hospital` |
   | Specialized Hospital | 38 | `hospital` |
   | Primary Health Center | 22,239 | `health_centre` |
   | Primary Health Clinic | 13,903 | `health_centre` |
   | Health Post | 8,726 | `health_centre` |
   | unknown | 4,909 | key omitted → parses as null/unspecified |

   Totals on the wire: `hospital` 1,245 · `health_centre` 44,868 · omitted
   4,909. A null/unspecified type is **not** a vocabulary member: never filter
   it out, never render an empty result list because of it (your
   `filterForUrgency` already guarantees this). This source maps **no** record
   to `pharmacy`, `clinic`, `laboratory` or `other` — the self-care pharmacy
   filter has nothing to match; surface distance-ranked results instead.
   Mapping any further value requires a new Product decision.
3. **`emergency_capable` stays absent/unknown** — FAC-D002's Product direction
   is approved: keep the **112 action first and prominent**; prioritize a
   facility **only when `emergency_capable == true`** (there are none); null
   must **never** mean emergency-capable; with no verified emergency-capable
   facility, show nearby facilities by distance **without claiming emergency
   capability**; the interface must clearly state that emergency capability is
   **not verified**. The final user-facing wording still requires Clinical
   approval — FAC-D002 is not fully approved and the field is not populated.
4. **`phone` and `opening_hours` are unavailable** (FAC-D003, approved as
   unavailable). Render **no call buttons and no "open now" actions** for
   GRID3 v2 records. 1.1's 45 verified Lagos phones are not in this lineage;
   reconsideration requires a separately authorized source.
5. **Identifiers changed:** `ng_g3_<globalid>`. Do not join 2.0 ids against
   1.1 ids or any NHFR id; there is no crosswalk.
6. **`"unknown"` vs null:** the string `"unknown"` means the source explicitly
   said Unknown (facility_level, ownership, ownership_type); null means the
   source has no such data. Render "Unknown" only for the former; render
   nothing for null.

## Attribution — a launch requirement, not a nicety

The source licence (CC BY 4.0) requires attribution wherever the data is used.
The facility-search feature must display, at minimum:

> Data: GRID3 NGA Health Facilities v2.0, CIESIN/Columbia University — CC BY 4.0

linking to `https://doi.org/10.7916/kv1n-0743` and
`https://creativecommons.org/licenses/by/4.0`. Full notice:
`facilities/ATTRIBUTION_GRID3.md`. An immutable published artifact cannot gain
attribution afterwards, so this ships with first publication or the publication
does not happen.

## Size and low-end devices (do not wire downloads yet)

The served candidate is **9.8 MB raw / 2.3 MB gzip** (vs 1.1's 1.7 MB raw) —
192.2 bytes/record, within reasonable low-end budgets; the 69 MB figure
belongs to the internal master only and never reaches a device. One national
artifact is the recommendation (sharding evaluated and set aside:
`docs/FACILITIES_GRID3_SERVED.md`). Treat gzip as the transfer bound and raw
bytes as the on-device parse/storage bound. Wiring a download still requires
every open approval.

## What Mobile must NOT do

- Ship, download or cache this candidate in any build (it is unapproved).
- Reconstruct `type`, emergency capability, phones or hours from names or any
  other source.
- Treat `source_record.nhfr_uid` as a join key to any NHFR export.
- Modify anything in `wellapath-mobile` on account of this handoff — it is
  contract review only.
