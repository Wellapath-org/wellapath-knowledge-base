# Attribution — GRID3 NGA Health Facilities v2.0

WellaPath's Facilities 2.0 (GRID3 lineage) candidate is a derived work of:

> **Center for Integrated Earth System Information (CIESIN), Columbia University 2024. GRID3 NGA - Health Facilities v2.0. New York: GRID3. https://doi.org/10.7916/kv1n-0743. Accessed 20 July 2026.**

Copyright 2024. The Trustees of Columbia University in the City of New York.

The source dataset is licensed under the **Creative Commons Attribution 4.0
International License (CC BY 4.0)** — https://creativecommons.org/licenses/by/4.0
(legal code: https://creativecommons.org/licenses/by/4.0/legalcode, vendored at
`facilities/source/CC-BY-4.0.legalcode.txt`). The licence statement as published
by GRID3 is preserved verbatim in
`facilities/source/grid3_licence_evidence_v1.json`.

**Modifications were made.** Modifications by WellaPath: field projection into the
schema-2.0 consumer contract; text normalization (NFC, control characters removed,
whitespace collapsed); state-name normalization ('Fct' → 'FCT'); ownership_type
token normalization; explicit source 'Unknown' carried as the string 'unknown';
exact-duplicate policy and quarantine policy as recorded in the artifact's
`_metadata`. No coordinate was moved, swapped, snapped or invented; no value was
added from any other source. The full change record is
`docs/FACILITIES_GRID3_CHANGELOG.md`.

GRID3 does not endorse WellaPath or this derived work.

## Where this notice must appear

1. **Artifact metadata** — embedded at `_metadata.source.attribution` of
   `candidate/facilities.ng.v2.0-grid3.json` (enforced by
   `tools/validate_facilities_grid3_candidate.py`).
2. **The consuming app** — the facility-search feature must display this
   attribution (a "Data: GRID3 NGA Health Facilities v2.0, CIESIN/Columbia
   University, CC BY 4.0" line with a link to the DOI and licence satisfies it).
   This is a launch requirement recorded in the Mobile handoff
   (`mobile_handoff/facilities_grid3_v2/README.md`); it cannot be added after an
   immutable artifact version is published, so it ships with, not after, first
   publication.
