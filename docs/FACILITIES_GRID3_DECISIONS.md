# Facilities 2.0 (GRID3) — decisions required before activation

> **DECIDED 2026-09-15 (Founder/Product decision record).** Formal register:
> `facilities/facilities_grid3_decision_register_v1.json`; verbatim record:
> `baseline/facilities_grid3_decisions_v1/FACILITIES_2_0_DECISION_RECORD_2026-09-15.vendored.md`.
> Outcomes: **FAC-D001 approved and applied** (hospital 1,245 · health_centre
> 44,868 · null 4,909) · **FAC-D002 Product direction approved, Clinical
> wording pending — the only open FAC item; `emergency_capable` stays null** ·
> **FAC-D003 approved as unavailable** · **FAC-D004, FAC-D005, FAC-D006
> approved** · **nationwide coverage accepted** ("nationwide" = geographic
> state coverage, not completeness). Nothing below is clinical approval, and
> publication remains blocked (`candidate_unapproved` / `may_publish: false`).
> The text below is retained as the original Engineering recommendations the
> decisions ruled on.

Concise recommendations from Engineering, as put to Product. Each names its
decider. The candidate cannot leave `candidate_unapproved` until every item
carries a recorded decision — see the register for what is now recorded.

## FAC-D001 — safe facility-type mapping (Product)

`type` is null on all 51,022 records. The deterministic proposal
(`proposals/facilities_grid3/type_mapping_proposal_v1.json`) maps the source's
`facility_level_option`:

| Source value | Rows | Proposed |
|---|---|---|
| General Hospital | 1,120 | `hospital` |
| Teaching/Tertiary Hospital | 87 | `hospital` |
| Specialized Hospital | 38 | `hospital` |
| Primary Health Center | 22,239 | `health_centre` |
| Primary Health Clinic | 13,903 | `health_centre` ⚠ flagged: `clinic` is arguable — explicit Product choice |
| Health Post | 8,726 | `health_centre` |
| unknown | 4,909 | stays null |

**Recommendation: approve the table above.** It is the mapping facilities
1.0/1.1 already ship (E5's `GRID3_TYPE_MAP`), so 2.0 stays consistent with live
behaviour; 46,113 records gain a type, 4,909 stay null. On approval the
candidate is **regenerated** with the table — never hand-edited. Note the
vocabulary members `clinic`, `pharmacy` and `laboratory` will have zero or few
members from this source; Mobile's self-care filter (pharmacies) will return
nothing from this dataset — carried into the Mobile handoff.

## FAC-D002 — emergency fallback with `emergency_capable = null` (Product + Clinical)

GRID3 records no emergency capability; none was invented; there is no record
prioritisation may legally apply to. **Recommendation:** for emergency urgency,
fall back to distance-sorted results **without any emergency filter**, showing
`facility_level` (Secondary/Tertiary first is a Product option once FAC-D001
lands, since "hospital" then becomes derivable) — but never an empty list, and
never a false "emergency-capable" badge. Clinical must sign the user-facing
wording because an emergency screen that cannot promise capability must say so.

## FAC-D003 — phone and opening hours remain unavailable (Product)

GRID3 publishes neither; the candidate carries neither; nothing was imported
from any other source — including 1.1's 45 hand-verified Lagos phones, which
belong to the 1.x enrichment lineage, not to GRID3. **Recommendation: accept
null/absent for 2.0 launch.** Call buttons and hours chips must not render.
If phones return later, they arrive as a separately licensed, separately
provenanced enrichment with its own decision — not by joining the unauthorized
NHFR export, whose identifiers GRID3 happens to share.

## FAC-D004 — accept GRID3 coordinates without NHFR enrichment (Engineering)

Every coordinate equals the published GRID3 value exactly; the validator proves
it record by record, and `coordinate_transformation` is the schema constant
`none`. There is no swap rule in this lineage and no NHFR-corrected pair
anywhere. **Recommendation: accept.** GRID3's points are the same instrument
facilities 1.1 already uses, and the coordinate-orientation defect belonged to
the NHFR export, not to GRID3 (0 rows flagged by `state_position_consistency_v1`).

## FAC-D005 — invalid/coordinate-less rows remain quarantined (Engineering)

The policy exists and is enforced; this snapshot happens to need none of it
(0 rows quarantined — the source has no invalid or missing coordinates).
**Recommendation: accept the policy as the standing rule** so a future snapshot
with defects refuses rows instead of shipping them.

## FAC-D006 — conservative duplicate handling (Product)

Exact duplicates (name+state+LGA+coordinates): 0 found; the collapse rule
stands ready. 410 near-duplicate groups (same name+state+LGA, different
coordinates; 827 rows) are **listed, not merged** — two clinics may share a
name. **Recommendation: ship them unmerged**; a merge would need evidence no
source supplies. The listing is in the quality report for Product to scan.

## Adamawa, Kebbi and Sokoto — actual GRID3 results

The three states the NHFR export lacked entirely are fully present here:
**Adamawa 1,561 · Kebbi 1,207 · Sokoto 937** records, all with valid in-state
coordinates. **Recommendation:** treat nationwide coverage as achieved by this
source; no supplementary source is needed for state presence. Caveats that
stand regardless: the dataset is self-described as *non-exhaustive and
non-validated*, and its snapshot is 2024-11-11 — currency, not presence, is the
open question, and it belongs to the routine-refresh discussion, not to this
candidate.

## Also open (Engineering, before any activation)

- **Artifact size:** ~69 MB raw / ~3.8 MB gzip vs 1.1's 1.7 MB. A served
  projection (drop `source_record`, or ship per-state files) is worth deciding
  before Mobile ships downloads to low-end devices.
- **Mobile compatibility re-measurement** against the actual Mobile PR #79
  reader once FAC-D001 is decided.
