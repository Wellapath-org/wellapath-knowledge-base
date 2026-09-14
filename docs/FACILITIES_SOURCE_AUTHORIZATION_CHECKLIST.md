# Facilities 2.0 — source authorization checklist

Machine-readable twin: `facilities/source/nhf_authorization_checklist_v1.json`. The validator
refuses a candidate whose `may_publish` is not `false` while any item is unsatisfied, and a
satisfied item without an evidence reference, a recorder and a date. Nothing in this repository
can satisfy an item; the evidence comes from the source owner, Legal or the engineering lead
and is recorded here **by reference**.

Applies to `facilities/source/nigeria_health_facilities.csv` (`e598cecc…becb3`) and every
candidate built from it.

| ID | Written evidence required | Status |
|---|---|---|
| AUTH-01 | **Source owner / publishing organisation** — a document or correspondence naming the organisation that produced and published the dataset, with an authoritative contact. The file names none. | missing |
| AUTH-02 | **Licence or written permission** — a licence text, or a written grant from the owner, covering WellaPath's use of this snapshot. | missing |
| AUTH-03 | **Permitted redistribution and modification** — the licence or grant states, or the owner confirms in writing, that a derived artifact (normalised, deduplicated, coordinate-corrected) may be redistributed. | missing |
| AUTH-04 | **Permitted public mobile-app use** — written confirmation that the data may be served to the public through a mobile app, including offline caching on the device. | missing |
| AUTH-05 | **Attribution requirements** — the exact attribution text required, or written confirmation that none is. Must be in the artifact before first publication; an immutable version cannot be amended. | missing |
| AUTH-06 | **Snapshot date / dataset version** — the owner's declared version or export date. The file declares none; the candidate carries only an inferred bound (newest `updated_at` 2026-07-21T13:15:26, zone undeclared). | missing |
| AUTH-07 | **Data dictionary or field definitions** — at minimum `facility_type_id`, `facility_level_option_id`, `facility_level_options_category_id`, `operational_hours`, the service Yes/No columns, and the workflow fields whose value is "Auto-approved via bulk import" on every row. | missing |
| AUTH-08 | **Authority** — evidence that whoever gives AUTH-02 to AUTH-05 is entitled to speak for the owner. | missing |
| AUTH-09 | **Chain of custody** — how the supplied copy travelled from the owner to this repository, or a fresh export obtained directly. The supplied copy passed through Apple Numbers; the coordinate transposition may have been introduced or preserved anywhere along that path. | missing |

**Until every row reads `satisfied`:** `release_status` and `publication_status` stay
`candidate_unapproved`, `may_publish` stays `false`, nothing is uploaded, and the candidate is
not handed to Backend or Mobile for anything but contract review.

**Recording evidence:** edit the JSON item — `status`, `evidence` (a resolvable reference:
document path in this repository, ticket, or correspondence id), `recorded_by` (name and
title), `recorded_on` (date) — and set `all_satisfied` only when every item is satisfied. The
validator checks the derivation.
