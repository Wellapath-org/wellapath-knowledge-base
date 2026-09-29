# Facilities 2.0 — decisions required before the candidate can be used

Data Engineering can implement any option below once it is recorded as a decision with an
owner, a date and a rationale, in the form the publication tooling resolves
(`docs/PUBLICATION_LIFECYCLE.md` §6). Data Engineering will not choose for Product or Clinical,
and has not: every field these decisions govern is null in the candidate today.

## FAC-D001 — Facility `type` (Product) — **blocks every non-emergency locator path**

**Fact.** The source has no facility-kind column. It has `facility_level` (Primary /
Secondary / Tertiary — a tier of care), `ownership`, `ownership_type` and five Yes/No service
flags. `facility_type_id` (1/2/3) is a near-copy of the level. The Mobile build filters
`urgent` / `non_urgent` on `{hospital, clinic}` and `self_care` on `{pharmacy, health_centre}`;
a null `type` matches nothing, so those paths return nothing.

**Decide one of:**

| Option | What Product records | What Data Engineering then does |
|---|---|---|
| D001-A | An explicit mapping table from `facility_level` (and, if wanted, `ownership_type`) to the vocabulary `{hospital, clinic, health_centre, pharmacy, laboratory, other}`, e.g. Tertiary→hospital, Secondary→hospital, Primary→health_centre | Fills `mappings.FACILITY_TYPE_FROM_LEVEL`; emits `type` per record; records the mapping's provenance as `product_decision:FAC-D001-A`; regenerates and re-measures compatibility |
| D001-B | "Do not map. The consumer must treat a null `type` as unknown: never filter it out, never produce an empty list because of it." | Nothing in the artifact; Mobile implements the contract in `mobile_handoff/facilities_v2/README.md` §6 |
| D001-C | D001-A **and** D001-B together: map what the level supports, and require the consumer to handle null for anything unmapped (`other`) | Both of the above |

**Not acceptable to Data Engineering:** inferring `type` from `name` ("…Hospital", "…Pharmacy")
or from the service flags. Both are guesses about a clinical routing decision.

## FAC-D002 — `emergency_capable` fallback (Product **and** Clinical) — **decides emergency ordering**

**Fact.** No source column records emergency capability. `ambulance_services`, `inpatient`,
`mortuary_services` and `facility_level` are adjacent claims, not that claim. Every record is
null; the Mobile build's `== true` test therefore prioritises nothing and emergency results are
pure distance order.

**Decide one of:**

| Option | What is recorded | What Data Engineering then does |
|---|---|---|
| D002-A | "Emergency ordering is by distance only until an authoritative capability field exists. No record is prioritised." (Product, with Clinical concurrence) | Nothing in the artifact; the handoff already states it |
| D002-B | A **Clinical-approved** rule over source fields, e.g. `facility_level == Tertiary AND services.ambulance == true` → `true`; everything else stays null (not false) | Implements the rule as `mappings.EMERGENCY_CAPABLE_RULE` with the decision id as provenance; emits `true` only where the rule is satisfied on evidenced values; re-measures |
| D002-C | Obtain an emergency-capability field from the source owner (AUTH-07) | Maps it when it arrives |

**Not acceptable to Data Engineering:** deriving `true` from `type` (as 1.1 did) once D001 maps
it, unless Clinical records that the mapping carries that meaning; deriving anything from
`name`; treating null as `false` in the artifact.

## FAC-D003 — Public use of `phone` (Product)

Nothing establishes that `phone_number` is a public contact. Decide whether the consumer may
offer a `tel:` action. Until recorded: display only, no action.

## FAC-D004 — Acceptance of `coordinate_orientation_v1` (Engineering lead)

The rule exchanges latitude and longitude for 11,141 source rows (10,862 in the artifact) on
the evidence in `docs/FACILITIES_COORDINATE_REMEDIATION.md`. It is applied in the candidate and
fully audited; it is not yet accepted by anyone. Decide: accept the rule as the candidate's
correction policy; or reject it and return the file to the source owner (AUTH-09), in which
case the candidate reverts to refusing those rows.

## FAC-D005 — The 1,442 ambiguous and 524 coordinate-less rows (Product)

Both sets are quarantined and listed. Decide whether either may be reinstated for name search
only (no map pin, no distance), or stays out until the source owner corrects them.

## FAC-D006 — Looser duplicates (Product + Data)

673 same-name/same-LGA groups and 1,540 same-point groups remain after exact-match collapse.
Decide whether a looser rule is wanted, and what it is.

## Clinical review points (Clinical)

1. FAC-D002 in full.
2. Whether any `type` mapping under FAC-D001 changes which facilities are shown for `urgent`
   in a way Clinical must sign off (it decides self-care vs urgent routing).
