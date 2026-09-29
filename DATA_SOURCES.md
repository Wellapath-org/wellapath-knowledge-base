# Data sources and attribution

The facility dataset WellaPath ships, `facilities.ng.v1.1.json`, is built from
two public sources. Both require attribution. This file is that attribution,
and it is a licence obligation, not documentation.

## GRID3 NGA Health Facilities v2.0

**Dataset** — GRID3 NGA Health Facilities, version 2.0 (November 2024).

**Citation** — Center for Integrated Earth System Information (CIESIN),
Columbia University (2024). *GRID3 NGA Health Facilities v2.0.* GRID3.

**Source** — https://data.grid3.org/datasets/GRID3::grid3-nga-health-facilities-/explore

**Licence** — Creative Commons Attribution 4.0 International (CC BY 4.0),
https://creativecommons.org/licenses/by/4.0/

**Contribution** — 4,448 of the 5,344 shipped records (83.2%), including all
4,278 health centres.

## HOTOSM Nigeria Health Facilities (OpenStreetMap)

**© OpenStreetMap contributors.**

**Dataset** — HOTOSM Nigeria Health Facilities, HDX export (February 2025),
produced with the Humanitarian OpenStreetMap Team's HOT Export Tool.

**Source** — https://data.humdata.org/dataset/hotosm_nga_health_facilities

**OpenStreetMap** — https://www.openstreetmap.org/copyright

**Licence** — Open Database License 1.0 (ODbL),
https://opendatacommons.org/licenses/odbl/1-0/

**Contribution** — 896 of the 5,344 shipped records (16.8%): all 50 clinics,
all 92 pharmacies, and 754 of the 924 hospitals.

## Modifications WellaPath made

The shipped dataset is **modified** from both sources. It is not a copy of
either. Specifically:

* restricted to Lagos, FCT and Kano, and state names normalised;
* source facility types mapped onto a five-value enumeration
  (`hospital`, `clinic`, `pharmacy`, `health_centre`, `maternity`), with 746
  records excluded as unmappable;
* coordinates validated against Nigeria's bounding box and rounded to seven
  decimal places;
* names title-cased and internal whitespace collapsed;
* 456 OpenStreetMap records discarded as duplicates of GRID3 records, matched
  on normalised name within ~500 m, GRID3 preferred;
* records merged into one table and assigned WellaPath identifiers;
* `emergency_capable` derived from facility type.

The full pipeline is `facilities/source/build_e5.py`, and the record-level
cleaning log is `facilities/cleaning_log.md`.

## No endorsement

GRID3, CIESIN, Columbia University, the Humanitarian OpenStreetMap Team,
OpenStreetMap contributors, the Government of Nigeria and the Federal Ministry
of Health **do not endorse WellaPath or this derived work.**

## Share-alike

Because OpenStreetMap records are modified and merged into it,
`facilities.ng.v1.1.json` is a **Derivative Database** under ODbL 1.0 §4.4,
and is offered under the Open Database License 1.0. The complete
machine-readable database is this repository's `facilities.ng.v1.1.json`,
available at no charge. See `docs/FACILITIES_ODBL_LINEAGE.md` for the
determination and the record-level evidence behind it.

The application code that reads this database is not part of the database and
is not licensed by this notice.

## Not a source of this dataset

The Nigeria Health Facility Registry (NHFR) export held privately is **not** a
source of `facilities.ng.v1.1.json`, with one exception recorded here for
completeness: 45 Lagos telephone numbers present in the shipped artifact were
taken from it. NHFR publishes no licence and reserves all rights, so that
material has no established redistribution basis and is pending a licensing
decision. See `source/LAGOS_PHONE_ENRICHMENT_v1_WITHDRAWN.md`.
