# Facilities changelog — 1.1 → 2.0 (GRID3 lineage, candidate)

Candidate `candidate/facilities.ng.v2.0-grid3.json`
(`03a5bf2d52759103ed08b34fd2f9d0934c85322317301582e9e61cbfa8abb14a`, 51,022
records, 69,032,692 bytes) against the active `facilities.ng.v1.1.json`
(`25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398`, 5,344
records, 1,695,844 bytes). **The candidate is unapproved and unpublished; 1.1
remains active.** Numbers from `reports/facilities_grid3_comparison_v1.json`.

## Gained

- **Nationwide coverage: 3 states → all 36 states + FCT** (1.1 covers Lagos,
  FCT and Kano only). Adamawa 1,561 · Kebbi 1,207 · Sokoto 937 — the three
  states the NHFR export lacked are present.
- **5,344 → 51,022 records** (4,332 exact name+state overlaps with 1.1).
- **Single-source provenance:** every record traces to one hash-pinned,
  CC BY 4.0-licensed GRID3 row through `source_record` (objectid, globalid,
  name/coordinate source, snapshot date). 1.1 is a GRID3+OSM fusion with manual
  enrichment; a fused record cannot say where each field came from — every 2.0
  record can.
- **Verified licence and attribution chain:** publisher-verbatim licence
  statement preserved, legal code vendored, citation embedded in the artifact.
- Ward names, ownership_type detail, facility_level_option carried per record.

## Held back (null in the candidate; populated in 1.1)

- **`type`** — 1.1 ships a mapped type; the candidate holds null until Product
  approves FAC-D001 (the proposed table equals what 1.1 already uses).
- **`emergency_capable`** — 1.1 derives it from `type == 'hospital'`; the
  candidate holds null (FAC-D002); the derivation was an inference and this
  lineage does not repeat it silently.
- **`phone`** — 1.1 carries phones including 45 hand-verified Lagos numbers;
  the candidate carries none (FAC-D003). GRID3 publishes no contact data and
  nothing was joined in from any other source. **This is a real user-facing
  regression against 1.1 and is stated, not smoothed over.**
- **`opening_hours`** — same position as phone.

## Changed

- **Identifiers:** `ng_<state>_<n>` → `ng_g3_<globalid>`; the two lineages
  cannot be confused, and ids survive re-exports (globalid is the source's
  stable key). A 1.1→2.0 id crosswalk does not exist and would need its own
  evidence-backed matching decision.
- **Size:** 1.7 MB → 69 MB raw (3.8 MB gzip). Open engineering item before any
  activation (`docs/FACILITIES_GRID3_DECISIONS.md`, "Also open").
- **Snapshot discipline:** 1.1's sources list two update dates; the candidate
  pins one declared version (v2.0) and one snapshot date (2024-11-11) on every
  record.

## Explicitly not done

No coordinate swapped, snapped, moved or invented; no value from the NHFR
internal export or the PR #40/#41 candidate; no type inferred from names; no
absent value coerced to false or zero; no merge of near-duplicate records
(410 groups listed for review); no change to `/config`, R2, Backend, Mobile,
or the active 1.1/1.0 artifacts (byte-identical, hash-checked).
