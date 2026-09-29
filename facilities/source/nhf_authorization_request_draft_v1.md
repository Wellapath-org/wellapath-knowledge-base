# FINAL DRAFT — data-use authorisation request to the Nigeria Health Facility Registry

**Status: FINAL DRAFT, NOT SENT. Prepared for founder review.** Nothing in
this repository sends it.

Before sending: founder review of the whole text, Legal review of the
permissions requested, and founder confirmation of the chain-of-custody
paragraph — it is written from repository evidence and must be corrected from
first-hand knowledge if wrong.

**Nothing attached to this request contains a facility telephone number or
email address, and the export itself is not attached.** The fingerprint
(`nhf_source_fingerprint_v1.json`) carries column names, null patterns, state
counts and hashes only — verified to hold zero contact values.

## Channels

`hfr@health.gov.ng` was tried and **bounced**. Send through whichever of these
is functioning, and retain delivery evidence (bounce message, delivery
receipt, portal acknowledgement, stamped hard copy). If every channel fails,
record each failure with its date and keep this draft ready.

| Channel | Route |
|---|---|
| NHFR portal enquiry | https://hfr.fmohconnect.gov.ng/ contact or developer form |
| DHPRS | Department of Health Planning, Research and Statistics, FMoH — the department NHFR sits under |
| FMoH general correspondence | Official letter on WellaPath letterhead to the Permanent Secretary, Federal Ministry of Health, Abuja |
| In person | DHPRS registry, FMoH headquarters, with a stamped receipt copy |

Send from WellaPath's own verified domain. **This request must not block the
licensed-source candidate**, which proceeds on GRID3 and OpenStreetMap
regardless of the answer.

---

**Subject:** Request for written permission to use Nigeria Health Facility
Registry data in the WellaPath mobile application

Dear Nigeria Health Facility Registry team,

WellaPath is a Nigerian digital-health product that helps people understand
symptoms and find nearby health facilities. It is a clinical decision support
tool; it does not diagnose.

We are writing to request **written permission** to use data from the Nigeria
Health Facility Registry, and to put our use of it on a properly authorised
footing rather than rely on an undocumented copy. We would rather ask and be
refused than proceed without your position on the record.

## 1. The copy we hold

We were supplied a CSV export of facility records that our analysis indicates
derives from the NHFR. We hold no documentation of how it was exported, so we
ask you to confirm or refute its origin. Its fingerprint:

* SHA-256 `e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3`
* 20,913,558 bytes; 31,390 data rows; 90 columns
* Facility codes in the `NN/NN/N/N/N/NNNN` shape
* Internal audit timestamps from 2026-05-18 to 2026-07-21
* Coverage: 33 states and the FCT; no records for Adamawa, Kebbi or Sokoto

A fuller machine-readable fingerprint is attached so your team can identify
the exact export. **It contains no facility contact details.**

We are treating this copy as unlicensed. It is held privately, it is not
published, and no product currently distributes any value taken from it.

## 2. Permissions requested

We ask for written confirmation of whether, and on what terms, WellaPath may:

1. **use NHFR facility identity and location data** — facility name,
   identifier, facility code, state, LGA, ward and coordinates;
2. **process and normalise it** — standardise values, deduplicate records,
   correct apparent coordinate-orientation errors under a documented and
   auditable rule, and drop internal workflow columns;
3. **bundle a selected offline subset** in a free mobile application, cached
   on the user's device so the app works without a network connection;
4. **display ownership, facility level, operational status,
   operational days/hours and service fields** to users;
5. **display contact information** — facility phone numbers, alternate
   numbers, email addresses and websites — **labelled with its source and its
   verification status**, so a user always sees that a value comes from the
   Registry and whether it has been independently verified;
6. **maintain derived crosswalks** between NHFR identifiers and WellaPath's
   own facility identifiers, for reconciliation and updates;
7. **publish the provenance and attribution** the Registry requires, including
   source, version and access date;
8. **redistribute the resulting offline facility artifact** through
   WellaPath's content-delivery network to our public mobile applications;
9. **use the data commercially**, should WellaPath later introduce paid
   services, on the understanding that **no use will imply endorsement by the
   Federal Ministry of Health, the Registry or the Government of Nigeria.**

## 3. What we ask the Registry to state

1. **The governing licence or written permission** — the licence text that
   applies, or a written grant if no standard terms exist, and the name and
   office of the authority able to give it.
2. **Required attribution** — the exact wording and where it must appear, or
   confirmation that none is required.
3. **Permitted modifications** — which transformations are acceptable, and
   whether any field must be carried unaltered or not at all.
4. **Redistribution rules** — whether onward distribution to end users, and
   offline caching on their devices, is permitted, and on what conditions.
5. **Update frequency** — how often the Registry is updated, and how we should
   obtain refreshed data (a fresh export, or API access through
   https://hfr.fmohconnect.gov.ng/developers).
6. **Correction process** — how we report an apparent error in a record, and
   how corrections propagate back to the Registry.
7. **Whether facility contact and ambulance fields may be displayed** — in
   particular phone numbers (`phone_number`, `alternate_number`),
   `email_address`, `website`, `ambulance_services`, and
   operational days/hours — and under what labelling. We will not display
   any of these without your explicit confirmation.

We would also welcome a **data dictionary**, in particular for
`facility_type_id`, `facility_level_option_id`,
`facility_level_options_category_id`, `operational_hours`, the service Yes/No
columns, and the workflow fields recorded as "Auto-approved via bulk import".

## 4. Undertakings

Whatever the answer:

* We will not publish or redistribute the export, or facility-level records
  derived from it, without written permission.
* We will not present any Registry value as verified unless the Registry says
  it is, and we will never describe a facility as emergency-capable on the
  strength of a registry listing alone.
* We will display attribution exactly as the Registry specifies.
* We will not imply Government or Ministry endorsement of WellaPath.
* If permission is refused, we will confirm in writing that the copy has been
  destroyed and that no derived value remains in any product.

We would be grateful for a response, including a refusal. A clear "no" is more
useful to us than silence, and we will act on it.

Yours faithfully,

**[Founder name], [title]**
WellaPath
[organisation email on WellaPath's verified domain] · [telephone]

---

## Delivery record — complete on sending

| Channel | Date sent | Method | Evidence retained | Outcome |
|---|---|---|---|---|
| hfr@health.gov.ng | 2026-09 | email | bounce message | **failed — mailbox unavailable** |
| | | | | |
| | | | | |

If every channel fails, record each failure above, keep this draft ready, and
proceed with the licensed-source candidate.
