# Facilities 2.0 — data withheld from this repository

Five artifacts in the facilities 2.0 pipeline are **not** distributed here.
The code, tests, schema, reports and documentation that operate on them all
are.

| Withheld artifact | Size | What it holds |
|---|---:|---|
| `facilities/source/nigeria_health_facilities.csv` | 20.9 MB | The NHFR source export, 31,390 rows |
| `candidate/facilities.ng.v2.0.json` | 36.1 MB | 29,028 facility-level candidate records |
| `reports/facilities_coordinate_audit_v1.json` | 4.5 MB | 11,141 per-record coordinate corrections |
| `reports/facilities_quarantine_v1.json` | 829 KB | 2,362 per-record rejections |
| `reports/facilities_comparison_v1.json` | 19 KB | Per-record match samples |

## Why

**Licensing, not privacy.** No personal-data breach was established: these
files carry no named individuals, and the NHFR officer contact columns
(`verified_email`, `verified_mobile`, `validated_email`, `validated_mobile`,
`published_email`, `published_mobile`, `verified_id`) are empty across all
31,390 source rows.

The problem is that **NHFR redistribution terms were never captured**. The
registry publishes no licence and no terms of use, and its only public rights
statement reserves all rights to the Federal Ministry of Health. Permission
must be obtained in writing before these bytes, or facility-level records
derived from them, may be redistributed. A prepared request is at
`facilities/source/nhf_authorization_request_draft_v1.md`; the gate is tracked
in `docs/FACILITIES_SOURCE_AUTHORIZATION_CHECKLIST.md`.

Removing contact columns would not resolve this. The licensing question
attaches to the derived records themselves, not only to the contact values.

This is distinct from the two sources that **are** retained here:
`GRID3_NGA_health_facilities_v2_0_*.csv` (CC BY 4.0) and
`hotosm_nga_health_facilities.csv` (ODbL). Licensed public datasets stay
tracked; what is withheld is the source whose terms are unestablished.

## Running the pipeline

Point `WELLAPATH_PRIVATE_DATA` at a directory holding a private copy:

```bash
export WELLAPATH_PRIVATE_DATA=~/wellapath-private-data/facilities-2.0
python3 tools/run_facilities_checks.py        # all 6 checks, 111 tests
```

The layout mirrors the repository (`candidate/…`, `reports/…`,
`facilities/source/…`); a flat directory of basenames also resolves.

**Unset, every check skips cleanly and exits 0** — a public clone is not a
broken clone. `tools/facilities/private_data.py` does the resolution, and
`repo_path()` in the generator tools routes withheld paths through it.

Keep the private copy outside every Git working tree and outside cloud-synced
folders. On macOS, `~/Documents` and `~/Desktop` are usually iCloud-synced and
do not qualify.
