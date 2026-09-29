# Lagos facility phone enrichment v1 — withdrawn from public distribution

`source/lagos_facility_phone_enrichment_v1.csv` has been removed from this
public repository by forward commit. No history was rewritten, and no branch
was force-pushed. A checksum-verified private copy is retained outside every
Git working tree.

**This is not a privacy remediation.** No personal-data breach was
established. The file is withdrawn because its **redistribution terms were
never captured** — see *Why* below.

## Why

The file was derived from a Nigeria Health Facility Registry (NHFR) export.
That export carries no licence, no terms-of-use statement and no licence
column. The registry's own site publishes no terms; its only rights statement
is a reservation of all rights by the Federal Ministry of Health. So the
position is not merely unknown — the presumed owner publicly reserves all
rights, and written permission is required before redistribution.

Removing the contact columns would **not** resolve this. The licensing
question attaches to the derived records themselves, not only to the contact
values, so the facility-level crosswalk also stays private until NHFR
redistribution terms are established in writing.

## Schema of the withdrawn file

Seven columns, all populated on every row:

| Column | Description |
|---|---|
| `facility_id` | WellaPath facility identifier (`ng_lag_NNN`) |
| `wellapath_name` | Facility name as carried in the WellaPath artifact |
| `city_area` | Area within Lagos |
| `hfr_name` | Facility name as recorded in the NHFR export |
| `phone` | Facility telephone number from the NHFR export |
| `email` | Facility email address from the NHFR export |
| `hfr_facility_code` | NHFR facility code, used as the join key |

No column carries a personal name, a staff name, a job title or an officer
attribution. The NHFR officer/workflow contact columns (`verified_email`,
`verified_mobile`, `validated_email`, `validated_mobile`, `published_email`,
`published_mobile`, `verified_id`) are empty across all 31,390 rows of the
upstream export and were never carried into this file.

## Aggregate counts

| Metric | Value |
|---|---:|
| Rows | 45 |
| States covered | 1 (Lagos) |
| Telephone numbers | 45 |
| Email addresses | 45 |
| Distinct email domains | 7 |
| — on free consumer mail domains | 36 |
| — on other domains | 9 |
| Named natural persons | 0 |
| Bytes | 5,411 |

Whether a facility address on a free consumer domain is organisational or
belongs to a proprietor is **undetermined**, and is not inferred in either
direction from the address format alone.

## Checksum

Of the withdrawn file, as it stood at its last public commit:

```
sha256  02961839c18e52ed6eeac30dd6a80df496399abc48d9794c744bf45eb32562cc
blob    33988ad0b924e7d00a020eede8b823ec315673ec
bytes   5411
```

## Generator instructions

To reproduce the file, you need NHFR redistribution permission first. Given
that, and a copy of the NHFR export:

```bash
export WELLAPATH_PRIVATE_DATA=~/wellapath-private-data

python3 scripts/audit/nhfr_crosswalk.py \
  --wellapath facilities.ng.v1.1.json \
  --out /tmp/facility-audit
```

The join is `hfr_facility_code` against the NHFR `unique_id` column, restricted
to `state_name = 'Lagos'`, keeping only rows where a WellaPath record matched
and the NHFR row carried a populated `phone_number`. Output the seven columns
above. Write the result outside every Git working tree.

## Related

The 45 telephone numbers also reached the shipped artifact
`facilities.ng.v1.1.json`, which carries them on the same 45 `facility_id`
values. Withdrawing this file does not remove them from that artifact. That is
recorded here so it is not overlooked; it is a separate decision, pending the
same NHFR licensing determination, and no production artifact is being changed
during this cleanup.
