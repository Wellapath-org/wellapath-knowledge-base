# Facilities 2.0 (GRID3) — served projection

**Status: `candidate_unapproved` / `may_publish: false` — both candidates.
Nothing published, uploaded or activated; facilities 1.1 remains active;
Backend and Mobile are unchanged.**

Three artifacts, three roles, named apart everywhere:

| Role | File | Bytes | Purpose |
|---|---|---|---|
| Source | `facilities/source/GRID3_NGA_health_facilities_v2_0_…csv` | 13,613,859 | licensed GRID3 CSV, hash-pinned, never served |
| **Master / audit candidate** | `candidate/facilities.ng.v2.0-grid3.json` | 69,032,692 | full per-record `source_record` provenance and the isolation proof; internal only, **not designated for mobile distribution** |
| **Served candidate** | `candidate/facilities.ng.v2.0-grid3.served.json` | **8,749,444** (gzip‑9 **2,216,713**) | the compact projection a manifest would point Mobile at, once every approval exists |

Served identity: SHA-256
`03a58e67d94bb1d7c88cc5e690472b167a82cc9f95d4f7afe937d8f5d1cebd75`,
51,022 records, 171.5 bytes/record, **−87.3 % vs the master**, 5.2× the active
1.1 artifact for 9.5× the records and 12.3× the states. Both engineering
targets met: raw ≤ 15 MB ✓, gzip ≤ 5 MB ✓ (`reports/facilities_grid3_size_v1.json`,
generated and `--check`-guarded, gzip level 9 fixed and documented).

## The served record — every field decision verified, not assumed

Verified against **Mobile PR #79 at `wellapath-mobile` `854377c0`**
(`lib/core/facilities_v2/facilities_v2_parser.dart`, `facilities_v2_search.dart`,
`facilities_v2_loader.dart`, read-only):

```json
{"id":"ng_g3_<globalid>","name":"…","state":"…","city_area":"…","latitude":…,"longitude":…}
```

- **`id`, not `facility_id`** — the parser consumes `raw['id']` and rejects a
  record without it. The value is the stable facility_id
  (`ng_g3_` + GRID3 `globalid`), which **doubles as the record-level source
  reference**: it joins 1:1 to the master record and to the licensed source row.
- **`name`, `latitude`, `longitude`** — parser-required; values byte-equal to
  the master, which the served validator re-proves against both the master and
  the GRID3 CSV itself.
- **`state` + `city_area`** — the whole search surface: `byState` matches
  `state` by normalized equality; `byArea` matches `lga`/`city_area` by
  equality but only `city_area` and `name` by containment, and the master's
  `lga` equals `city_area` on every record — so `city_area` alone preserves
  every match `lga` could have produced, near state boundaries included
  (current-location search is pure distance over coordinates and does not
  consult state at all).
- **Omitted because an absent key is verifiably null:** the parser reads every
  optional key with `raw[...]`, so a missing key parses identically to an
  explicit null — `type` → *unspecified* (never filtered out, by the verified
  null-type search guarantee), `emergency_capable` → *unknown* (never true),
  `phone`/`opening_hours` → null (additionally approval-gated behind
  `FacilitiesV2Presentation`, both flags default false). So the decision-gated
  fields **remain null to the consumer while absent from the wire**, and the
  served schema (`schema/facilities_grid3_served.v2.schema.json`,
  `additionalProperties: false`) makes premature population schema-invalid.
  FAC-D001 approval means a schema revision plus regeneration, not an edit.
- **Omitted because unconsumed keys cost device memory:** any other key is
  retained per record in the parser's opaque `provenance` map — so the served
  record carries none: no `source_record`, no `lga` (redundant), no per-record
  `country` (constant; stated once in `_metadata`, where licence, citation,
  modification disclosure, source hash and generation info also live exactly
  once).
- **Top-level `schema_version: "2.0"`** — the parser reads it at the top level
  and refuses the artifact without it.

## Hash and transport contract

The PR #79 loader verifies **sha256 over the raw downloaded body**
(`StagedArtifactLoader.verifyArtifactHash(rawBody, manifest.sha256)`), and the
Backend PR #36 manifest carries `sha256` as the required integrity field.
Neither contract hashes or delivers a compressed representation, so the served
artifact is compact **raw JSON** (no whitespace, ensure_ascii, no trailing
newline) and **gzip is a measurement only** — 2.2 MB is the expected transfer
cost under ordinary HTTP compression, 8.7 MB the on-device parse/storage bound.

## Traceability — proven, not designed

`tools/validate_facilities_grid3_served.py` (18 fail-closed checks):
independently **reprojects the committed master with its own code and requires
byte identity** with the committed served artifact; proves all 51,022 records
appear exactly once with no duplicate ids; joins every `id` to a distinct GRID3
source row with exact name and coordinate equality; simulates the verified
PR #79 acceptance rules (0 records would be rejected); scans the record bytes
for forbidden fields and the twelve NHFR markers (0 hits); recomputes every
size-report figure; and re-checks the 1.0/1.1 pins and every publication block.

## Sharding evaluation — evaluated, not implemented

Per-state served sizes measured: largest Lagos 469 KB, smallest Bayelsa 75 KB
(`per_state_served_bytes` in the size report).

| | A. One national artifact | B. National index + state shards | C. State shards only |
|---|---|---|---|
| Boundary current-location search | whole country in memory — nothing to miss | needs neighbour-shard logic | wrong or missing results without it |
| Nationwide manual search | complete | index must duplicate search fields (≈ the national artifact again) | requires N downloads or partial results |
| Offline | one cached file, all-or-nothing and verifiable | partial-coverage states to reason about | worst: per-state gaps invisible to the user |
| Cache/rollback | one hash, the existing loader flow, rollback = 1.1 | 38 artifacts + manifest schema changes | 37 artifacts + manifest schema changes |
| Downloads | 1 request, ~2.2 MB transfer | 1 + k requests | up to 37 requests |
| PR #79 compatibility | **works today** — single-artifact manifest, raw-body hash | loader/manifest rework in Mobile AND Backend | same rework |

**Recommendation: A — the compact national artifact.** At 8.7 MB raw / 2.2 MB
gzip it is within reasonable low-end budgets, it is the only option the
verified PR #79 loader and PR #36 manifest support without modification, and
it has the simplest offline, cache and rollback story. Revisit sharding only
if a future dataset outgrows the 15 MB raw target.

## Attribution

The served artifact carries, once, in `_metadata.source` (schema-pinned
consts): the citation — *"Center for Integrated Earth System Information
(CIESIN), Columbia University 2024. GRID3 NGA - Health Facilities v2.0. New
York: GRID3. https://doi.org/10.7916/kv1n-0743. Accessed 20 July 2026."* — the
CC BY 4.0 link, and the modification disclosure. **The mobile app must display
the attribution in the facility-locator feature** (a "Data: GRID3 NGA Health
Facilities v2.0, CIESIN/Columbia University — CC BY 4.0" line linking the DOI
and licence satisfies it; full notice `facilities/ATTRIBUTION_GRID3.md`). That
is a first-publication launch requirement recorded in the Mobile handoff —
documented here, **not implemented in Mobile by this task**.

## What this does not change

PRs #40/#41 untouched; PR #42 updated in place, unmerged. No Backend or Mobile
file modified (the Mobile repo was read, never written). No R2 upload, no
`/config` change, no staging/production activation, no build 211. `type`
remains unpopulated pending FAC-D001; every FAC decision in
`docs/FACILITIES_GRID3_DECISIONS.md` remains open.
