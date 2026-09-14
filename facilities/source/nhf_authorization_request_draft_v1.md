# DRAFT — data-use authorization request to the Nigeria Health Facility Registry

**Status: DRAFT, NOT SENT.** Prepared 2026-09-14 for founder review. Nothing in this
repository sends it. Before sending: founder review of the whole text, Legal review of the
permissions asked for, and founder confirmation of the chain-of-custody paragraph, which is
written from repository evidence and must be corrected from first-hand knowledge if wrong.

- **To:** Nigeria Health Facility Registry, Federal Ministry of Health — hfr@health.gov.ng
  (published contact on https://hfr.fmohconnect.gov.ng/, captured 2026-09-14)
- **From:** WellaPath — to be sent from the organisation's own domain. (The earlier NHFR
  in-portal API request was never resubmitted because the organisation domain was
  unverified; that prerequisite applies here too.)
- **Subject:** Request for permission to use Nigeria Health Facility Registry data in the
  WellaPath mobile application

---

Dear Nigeria Health Facility Registry team,

WellaPath is a Nigerian digital-health product that helps users understand symptoms and
find nearby health facilities. We are writing to request written permission to use data
from the Nigeria Health Facility Registry, and to establish a properly authorized data
relationship with the Registry rather than rely on an undocumented copy.

**1. The dataset we hold.** We were supplied a CSV export of facility records that our
analysis indicates derives from the NHFR. We do not have documentation of how it was
exported, so we are asking you to confirm or refute its origin. Its fingerprint:

- SHA-256: `e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3`
- Size: 20,913,558 bytes; 31,390 data rows; 90 columns
  (`id, unique_id, state_unique_id, registration_no, … dhis2_synced`)
- Facility codes in the `NN/NN/N/N/N/NNNN` shape (e.g. `01/01/1/1/2/0020`)
- Internal audit timestamps from 2026-05-18T16:06:51 to 2026-07-21T13:15:26
- Coverage: 33 states + FCT; no records for Adamawa, Kebbi or Sokoto
- Every row carries `verify_note` / `validate_note` "Auto-approved via bulk import"

A fuller machine-readable fingerprint (state counts, null pattern, per-state coordinate
medians, canonical sample hashes) is attached so your team can identify the exact export.

**2. What we ask permission for.** Written confirmation of whether, and on what terms,
WellaPath may:

1. use this data (or, preferably, a fresh export or API feed supplied by you);
2. transform it — normalise values, deduplicate records, correct apparent
   coordinate-orientation errors under a documented, auditable rule, and drop internal
   workflow columns;
3. redistribute the derived facility dataset through WellaPath's content-delivery
   network to our public mobile applications, including offline caching on users'
   devices;
4. display facility phone numbers to the public in the app, including tap-to-call — or
   confirmation of which contact fields, if any, are intended for public display;
5. display facility coordinates (as a map location and for distance ranking) and
   operational days/hours to the public;
6. do the above in a free public app operated by a commercial entity, with any
   attribution the Ministry requires displayed exactly as you specify.

**3. What we ask you to provide.**

1. The name and office of the authority able to grant the above, so the permission we
   receive is one the Ministry stands behind;
2. the licence text or terms that apply, or a written grant if no standard terms exist;
3. the required attribution text, or confirmation that none is required;
4. the declared version or export date of the snapshot we hold, or a fresh export /
   API access under your normal approval process (we are glad to apply through
   https://hfr.fmohconnect.gov.ng/developers);
5. a data dictionary, in particular the meanings of `facility_type_id`,
   `facility_level_option_id`, `facility_level_options_category_id`,
   `operational_hours`, the service Yes/No columns, and the workflow fields whose
   value is "Auto-approved via bulk import";
6. confirmation of how the copy we hold was exported, by whom and under what
   authorization — or, if you cannot establish that, a pristine export we can adopt in
   its place, which we would prefer in any case.

**4. A data-quality observation you may want.** In the copy we hold, the latitude and
longitude values appear exchanged for whole northern states (FCT, Kano, Katsina, Kwara,
Niger, Taraba, Zamfara and others): the values placed in each column match the state's
known position only when read the other way round. We can share the full analysis; if the
error is present in the Registry itself rather than introduced in our copy's export path,
your team may wish to correct it at source.

We will not publish or redistribute any NHFR-derived data until we have your written
permission. Thank you for your work maintaining the Registry.

Kind regards,

Ayodele John Oluwaseyi
Co-Founder & CEO, WellaPath

*Attachment: `nhf_source_fingerprint_v1.json` (machine-readable fingerprint of the copy
we hold).*
