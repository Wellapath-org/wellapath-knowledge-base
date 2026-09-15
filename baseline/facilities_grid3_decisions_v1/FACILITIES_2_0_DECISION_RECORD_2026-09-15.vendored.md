# VENDORED VERBATIM — Founder/Product decision record, received 2026-09-15

This file preserves the decision text exactly as received, following the
repository's precedent for vendored decision records (IM-003 2026-08-22,
IM-001 2026-08-24). The operational interpretation lives in
`facilities/facilities_grid3_decision_register_v1.json`; where the two could
be read differently, the register records the reconciliation and this file
stays untouched.

---

## Founder/Product decision record

The following Facilities 2.0 decisions are approved for implementation in the candidate:

### FAC-D001 — Facility-type mapping: APPROVED

Apply only the reviewed GRID3 mapping already documented in:

`proposals/facilities_grid3/type_mapping_proposal_v1.json`

Approved rules:

* The three documented Hospital source values → `hospital`.
* Primary Health Care Center → `health_centre`.
* Primary Health Care Clinic → `health_centre`.
* Health Post → `health_centre`.
* Unknown, missing or unsupported values → null/unspecified.

Do not infer type from facility names. Do not map any additional value without a new Product decision. Null/unspecified facilities must remain visible and searchable.

### FAC-D002 — Emergency fallback: PRODUCT DIRECTION APPROVED, CLINICAL WORDING PENDING

Approved Product behaviour:

* Keep the 112 action first and prominent.
* Prioritize a facility only when `emergency_capable == true`.
* Null must never mean emergency-capable.
* When no verified emergency-capable facility exists, show nearby facilities by distance without claiming emergency capability.
* The interface must clearly state that emergency capability is not verified.

Clinical approval of the final user-facing wording remains required. Do not mark FAC-D002 fully approved and do not populate `emergency_capable`.

### FAC-D003 — Phone and opening hours: APPROVED AS UNAVAILABLE

* Do not include phone numbers.
* Do not include opening hours.
* Do not display call or "open now" actions for GRID3 v2.
* These fields may be reconsidered only when a separately authorized source is approved.

### FAC-D004 — Coordinates: APPROVED

Use GRID3 coordinates exactly as published.

Do not swap, snap, move, enrich or replace them using the unauthorized NHFR CSV or another source.

### FAC-D005 — Invalid coordinates: APPROVED

Quarantine records with invalid, missing, null-island, out-of-Nigeria or otherwise schema-invalid coordinates.

Do not fabricate coordinates. The current zero-quarantine result is acceptable only while validation continues proving it.

### FAC-D006 — Duplicate handling: APPROVED

* Remove only exact deterministic duplicates.
* Preserve the 410 near-duplicate groups as separate facilities.
* Do not fuzzy-merge records without authoritative identity evidence.
* Keep the near-duplicate report for later source-quality review.

### Coverage decision: APPROVED

The GRID3 candidate's coverage of all 36 states and the FCT is accepted for the candidate. Adamawa, Kebbi and Sokoto are no longer blockers because the GRID3 source includes them.

"Nationwide" means geographic coverage across all states and FCT; it must not imply that every facility or service is listed.
