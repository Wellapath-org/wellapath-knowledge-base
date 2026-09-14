# Mobile handoff — Facilities 2.0, GRID3 lineage (CANDIDATE, not for release)

**Status: `candidate_unapproved` / `may_publish: false`. Not served, not
uploaded, not approved. facilities 1.1 remains the artifact your build loads.
This handoff exists for contract review only.**

Two candidates, one distribution target:

- **Served candidate (what a manifest would point your loader at):**
  `candidate/facilities.ng.v2.0-grid3.served.json` —
  `03a58e67d94bb1d7c88cc5e690472b167a82cc9f95d4f7afe937d8f5d1cebd75`,
  51,022 records, **8,749,444 bytes raw (gzip-9 2,216,713)**, compact JSON.
  Record shape verified against your PR #79 parser at `854377c0`:
  `{id, name, state, city_area, latitude, longitude}` — every omitted optional
  key (`type`, `emergency_capable`, `phone`, `opening_hours`, `lga`) parses as
  null in your parser, which is the intended meaning. Top-level
  `schema_version: "2.0"`. The manifest sha256 is over these raw bytes,
  matching your loader's raw-body verification; gzip is a measurement only.
  Full contract evidence: `docs/FACILITIES_GRID3_SERVED.md`.
- **Master/audit candidate (never for distribution):**
  `candidate/facilities.ng.v2.0-grid3.json` —
  `03a5bf2d52759103ed08b34fd2f9d0934c85322317301582e9e61cbfa8abb14a`,
  69,032,692 bytes, full per-record `source_record` provenance
  (`schema/facilities_grid3.v2.schema.json`). Trace any served record to it
  (and to the licensed GRID3 source row) through `id` = `ng_g3_<globalid>`.

## What is different from the artifact you load today (1.1)

1. **Coverage** — all 36 states + FCT (1.1: Lagos, FCT, Kano). State/LGA/manual
   location search works nationwide: `state` is normalized to the canonical 37
   names, `(state, lga)` is the area key (844 pairs), and every record has
   in-state coordinates for distance ranking.
2. **`type` is null on every record** until Product approves FAC-D001. A null
   type is **not** a vocabulary member: never filter it out, never render an
   empty result list because of it. Until FAC-D001, type-based filters
   (self-care → pharmacies, urgent → hospitals/clinics) have nothing to match —
   surface distance-ranked results instead. Note even after FAC-D001, this
   source maps no record to `pharmacy`, `clinic` or `laboratory`.
3. **`emergency_capable` is null on every record** (FAC-D002). Prioritisation
   may only ever apply to `true`; there is none. Emergency flow: nearest
   results, honest wording, never an empty list, never a capability badge.
4. **`phone` and `opening_hours` are null on every record** (FAC-D003). Do not
   render call buttons or hours chips for 2.0 records. 1.1's 45 verified Lagos
   phones are not in this lineage.
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

The served candidate is **8.7 MB raw / 2.2 MB gzip** (vs 1.1's 1.7 MB raw) —
171.5 bytes/record, within reasonable low-end budgets; the 69 MB figure
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
