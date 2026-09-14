# Facilities 2.0 — GRID3-lineage candidate

**Status: `candidate_unapproved` / `may_publish: false`. Nothing published,
uploaded or activated. facilities 1.1 remains the active artifact.**

The Facilities 2.0 effort pivoted away from the NHFR internal export (PRs #40/#41,
kept open as research/audit evidence, source authorization incomplete) to the
**separately published, licence-documented GRID3 NGA Health Facilities v2.0**
source — the same source facilities 1.0/1.1 were built from, already committed
and hash-pinned in this repository.

| Fact | Value |
|---|---|
| Candidate | `candidate/facilities.ng.v2.0-grid3.json` |
| Lineage / version / schema | `grid3` / 2.0 / 2.0 (`schema/facilities_grid3.v2.schema.json`) |
| Records | **51,022** — every source row emitted, 0 quarantined |
| Size | 69,032,692 bytes (gzip 3,810,741) |
| SHA-256 | `03a5bf2d52759103ed08b34fd2f9d0934c85322317301582e9e61cbfa8abb14a` |
| Coverage | **All 36 states + FCT**, including Adamawa (1,561), Kebbi (1,207), Sokoto (937) |
| Source | `facilities/source/GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv`, `154f3c9b…f180`, 13,613,859 bytes, 51,022 rows |
| Licence | **CC BY 4.0**, verified at the publisher and preserved: `facilities/source/grid3_licence_evidence_v1.json` |
| Attribution | Required; notice at `facilities/ATTRIBUTION_GRID3.md`, embedded in the artifact metadata |
| Snapshot | Declared v2.0; every row `last_updated` 2024-11-11 |

## Step 1 — the permitted source, verified not assumed

The prior note ("CC BY 4.0" in the v1.0 metadata) was **not** relied on. The
licence was re-verified at the publisher's own metadata endpoint and preserved
verbatim, with the CC BY 4.0 legal code vendored
(`facilities/source/CC-BY-4.0.legalcode.txt`, hash-pinned). The publisher's terms:
*"Users are free to use, copy, distribute, transmit, and adapt the work for
commercial and non-commercial purposes, without restriction, as long as clear
attribution of the source is provided."* Modification and redistribution of
derived data — including through a public mobile app — are therefore permitted,
conditional on attribution. Copyright: The Trustees of Columbia University;
producer CIESIN; DOI `10.7916/kv1n-0743`.

The committed CSV is tied to the published dataset by record count (51,022 both
sides), identical attribute schema and order, the constant snapshot date, and
record-level value identity on the published stable identifier — each check
recorded with its URL in the evidence file. **Licensing clearance is a source
gate only; it is not Product, Clinical or Engineering approval.**

## Step 2 — strict source isolation

The pipeline can open exactly two files (`tools/facilities_grid3/source.py`
`ALLOWED_INPUTS`): the GRID3 CSV (sole data source) and `facilities.ng.v1.1.json`
(comparison report only — no value reaches the candidate). The NHFR export and
every PR #40/#41 output are **forbidden inputs**: the input door refuses them
structurally, none is tracked on this branch, the emitted bytes are scanned for
twelve NHFR markers (0 hits), and the validator independently re-derives every
record's values from the GRID3 CSV. GRID3's own `nhfr_uid`/`nhfr_facility_code`
columns are the publisher's licensed cross-reference and are carried **from the
GRID3 file**; nothing was read from any NHFR export, and no GRID3 record was
joined against or enriched from one. Proof: `reports/facilities_grid3_isolation_v1.json`.

## Step 3 — what the candidate contains

The record shape is the schema-2.0 consumer contract (Mobile PR #79 / Backend
PR #36): same field names and types, `ng_g3_<globalid>` ids so the three
lineages (1.x, NHFR, GRID3) can never be confused. Only GRID3-supported values
are populated: name, state, LGA (`city_area`/`lga`), ward, coordinates,
`facility_level`, ownership fields, record-level provenance
(`source_record.*` with objectid, globalid, name/coordinate source and the
constant snapshot date). **Null on every record, deliberately:** `type` (mapping
proposed, not applied — FAC-D001), `phone`, `opening_hours`,
`emergency_capable`, `address`, the three status fields, `beds`, and every
service flag. The source's explicit `Unknown` is carried as the string
`"unknown"`, which is a different statement from null. Nothing is inferred from
facility names.

## Step 4 — data quality, measured

`reports/facilities_grid3_quality_v1.json` and
`reports/facilities_grid3_quarantine_v1.json`:

- **51,022 = 51,022 emitted + 0 quarantined.** Every quarantine category
  (invalid name, unparseable coordinates, null island, out of bounds, unknown
  state, state-position mismatch, exact duplicate) is enforced and empty — the
  source is that clean: 0 blank names, 0 blank LGAs, 0 invalid coordinate pairs.
- **Coordinates are accepted exactly as published or refused** — no swap, snap,
  move or fabrication exists in this lineage (`coordinate_transformation` is the
  schema constant `none`). State-position consistency is checked with
  `state_position_consistency_v1`, a conservative within-dataset anomaly rule;
  0 rows flagged.
- **Duplicates:** exact-match rule found 0 groups; 410 near-duplicate groups
  (same name+state+LGA, different coordinates, 827 rows) are **listed for
  review, not merged** (FAC-D006).
- **844 distinct (state, LGA) pairs**; identifiers unique on all three axes
  (facility_id, OBJECTID, globalid); snapshot constant verified on all rows.
- **Size:** ~69 MB raw / ~3.8 MB gzip vs 1.1's 1.7 MB — the Mobile handoff
  carries the low-end-device guidance and this is an open engineering item
  before any activation.
- **Against 1.1** (`reports/facilities_grid3_comparison_v1.json`): 5,344 → 51,022
  records; 1.1 states Lagos 2,690 / Kano 2,040 / FCT 614 vs candidate 2,798 /
  1,723 / 652; 4,332 exact name+state overlaps; 1.1 keeps four populated fields
  the candidate holds null (type, emergency_capable, phone, opening_hours).

## Verification

`python3 tools/run_facilities_grid3_checks.py` — generator determinism (7
outputs byte-reproducible), 41 fail-closed validator checks, 33-test suite with
schema-mutation proofs. All green, alongside W2 23/23, W3 30/30, IM-003 27/27,
publication 9/9.

## What publication still requires

FAC-D001…D006 (`docs/FACILITIES_GRID3_DECISIONS.md`) with Product/Clinical/
Engineering sign-off as marked; re-measured Mobile compatibility; the artifact
size decision; and the publication lifecycle itself. The manifest
(`candidate/facilities_grid3.manifest.candidate.json`) carries every gate
`false` except the licensing fact, and rollback bound to 1.1 by hash.
