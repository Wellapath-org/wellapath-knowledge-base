# Facilities 2.0 — GRID3-lineage candidate

**Status: `candidate_unapproved` / `may_publish: false`. Nothing published,
uploaded or activated. facilities 1.1 remains the active artifact.**

The Facilities 2.0 effort pivoted away from the NHFR internal export (PRs #40/#41,
kept open as research/audit evidence, source authorization incomplete) to the
**separately published, licence-documented GRID3 NGA Health Facilities v2.0**
source — the same source facilities 1.0/1.1 were built from, already committed
and hash-pinned in this repository.

> **Served projection:** this 69.5 MB artifact is the INTERNAL AUDIT/MASTER
> candidate and is not designated for mobile distribution. The compact
> distribution shape is `candidate/facilities.ng.v2.0-grid3.served.json`
> (9.8 MB raw / 2.3 MB gzip, 51,022 records, equally unapproved) —
> `docs/FACILITIES_GRID3_SERVED.md`.

| Fact | Value |
|---|---|
| Candidate (master/audit) | `candidate/facilities.ng.v2.0-grid3.json` |
| Lineage / version / schema | `grid3` / 2.0 / 2.0 (`schema/facilities_grid3.v2.schema.json`) |
| Records | **51,022** — every source row emitted, 0 quarantined |
| Size | 69,535,390 bytes (gzip 3,835,281) |
| SHA-256 | `92300c1624668d1af77ddbb0d37f0104d08aa5484ec7af8e792234c912930d7a` |
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
constant snapshot date). **`type` is populated under the approved FAC-D001
mapping (2026-09-15)** — hospital 1,245 · health_centre 44,868, computed from
`facility_level_option` alone, with the source's explicit Unknown staying null
on 4,909 records that remain visible and searchable. **Null on every record,
deliberately:** `phone`, `opening_hours`, `emergency_capable` (FAC-D002 wording
pending Clinical), `address`, the three status fields, `beds`, and every
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
- **Size:** master ~69.5 MB raw (internal only); the distribution shape is the
  9.8 MB served projection (`docs/FACILITIES_GRID3_SERVED.md`), which the
  Mobile handoff's low-end-device guidance covers.
- **Against 1.1** (`reports/facilities_grid3_comparison_v1.json`): 5,344 → 51,022
  records; 1.1 states Lagos 2,690 / Kano 2,040 / FCT 614 vs candidate 2,798 /
  1,723 / 652; 4,332 exact name+state overlaps; 1.1 keeps three populated
  fields the candidate holds null (emergency_capable, phone, opening_hours —
  the type gap closed with FAC-D001).

## Verification

`python3 tools/run_facilities_grid3_checks.py` — generator determinism (9
outputs byte-reproducible), 45 master validator checks, 21 served-projection
checks, 63-test suite with schema-mutation proofs. All green, alongside W2
23/23, W3 30/30, IM-003 27/27, publication 9/9.

## Decisions and what publication still requires

The Founder/Product decision record of **2026-09-15**
(`facilities/facilities_grid3_decision_register_v1.json`, vendored verbatim in
`baseline/facilities_grid3_decisions_v1/`) approved FAC-D001 (type mapping —
applied), FAC-D003 (phones/hours unavailable), FAC-D004 (GRID3 coordinates
as published), FAC-D005 (quarantine policy), FAC-D006 (conservative
duplicates) and nationwide coverage ("nationwide" = geographic state coverage,
not completeness). **Still required:** FAC-D002's Clinical approval of the
final user-facing emergency wording (the Product direction is approved;
`emergency_capable` stays null); re-measured Mobile compatibility; Engineering
sign-off; and the publication lifecycle itself. The manifest
(`candidate/facilities_grid3.manifest.candidate.json`) records the decided
gates true, everything else — including `may_publish` — false, and rollback
bound to 1.1 by hash.
