# facilities.ng.v1.1.json — OSM lineage and ODbL determination

Traced by re-executing `facilities/source/build_e5.py` against the two tracked
source CSVs and capturing the internal `_source` tag the build strips before
writing. **The rebuild reproduces the shipped `facility_id` set exactly**
(5,344 of 5,344), so the attribution below is derived, not estimated.

No conclusion here rests on the filename.

**Applies unchanged to v1.2.** `facilities.ng.v1.2.json` has the same 5,344
records with the same identifiers and coordinates — it differs from v1.1 only
in that 45 NHFR-derived telephone values are removed and a licence block is
added. The 896/5,344 OSM split and the Derivative Database determination carry
over exactly. v1.2 is the version that declares the licence.

## Which records came from HOT/OSM

**896 of 5,344 shipped records — 16.8%.**

| State | GRID3 | OSM |
|---|---:|---:|
| Lagos | 2,278 | 412 |
| FCT | 543 | 71 |
| Kano | 1,627 | 413 |
| **Total** | **4,448** | **896** |

By type, OSM is not a marginal contributor — it is the only contributor for
two of the five categories:

| Type | Total | From OSM | Share |
|---|---:|---:|---:|
| clinic | 50 | 50 | **100%** |
| pharmacy | 92 | 92 | **100%** |
| hospital | 924 | 754 | **81.6%** |
| health_centre | 4,278 | 0 | 0% |
| maternity | 0 | 0 | — |

## Which fields came from OSM

For those 896 records, substantially every substantive field:

| Shipped field | OSM origin |
|---|---|
| `name` | `name`, title-cased, whitespace collapsed |
| `type` | mapped from `amenity`, falling back to `healthcare` |
| `state` | `adm1_name`, normalised |
| `city_area` | `addr_city`, else `addr_full`, else `adm2_name` |
| `latitude` / `longitude` | copied, rounded to 7 decimal places |
| `phone` / `opening_hours` | read from OSM; null for every shipped record |
| `facility_id` | assigned by WellaPath |
| `emergency_capable` | derived by WellaPath from `type` |

## Was OSM data copied directly?

**Yes.** Coordinates are copied and rounded, not recomputed. Names are copied
and case-normalised. Nothing is redrawn or re-surveyed.

## Was it combined, filtered or modified?

**All three.** State-filtered to Lagos/FCT/Kano; type-mapped with 21 OSM
records excluded as unmappable; coordinate-validated; name-normalised; 456 OSM
records discarded as duplicates of GRID3 records; and the survivors merged
into a single table with 4,448 GRID3 records, then assigned WellaPath
identifiers.

## Derivative Database, Collective Database or Produced Work?

**A Derivative Database** under ODbL 1.0 §1.0.

* Not a **Produced Work**: a produced work is something *generated from* the
  database — a map image, a report, a rendering. We ship the database itself.
* Not a **Collective Database**: that requires the OSM database to be included
  *in an unmodified form* alongside independent databases. Here OSM records
  are modified (retyped, renamed, filtered, deduplicated) and merged into one
  table with GRID3 records. They are not separable and not unmodified.
* Therefore **Derivative**: a database based upon the Database, with
  modification and adaptation.

CC BY 4.0 on the GRID3 portion does not conflict. CC BY imposes attribution,
not share-alike, so GRID3 material may sit inside an ODbL-licensed derivative
database provided GRID3 is attributed — which `DATA_SOURCES.md` does.

## Is the complete machine-readable derivative already offered?

**Yes, already — this is the important practical finding.**
`facilities.ng.v1.1.json` is a plain JSON file tracked at the root of this
public repository and served to the application. Any recipient can obtain the
whole database, at no charge, in machine-readable form. ODbL §4.6 is satisfied
in substance today.

What was missing is not the data. It is the **licence declaration and the
attribution notice**. That is the entire gap.

## Two compliant options

### Option 1 — license the facility database under ODbL, with attribution

Declare `facilities.ng.v1.1.json` to be offered under ODbL 1.0, attribute
OpenStreetMap contributors and GRID3, and state the modifications. The
database is already published, so nothing new must be distributed.

* Records changed: **0**
* Artifact bytes changed: **0** (the notice lives in `DATA_SOURCES.md` and the
  app's data-sources surface; the artifact's `_metadata.sources` already
  records both licences and both source URLs)
* Application code licensing: **unaffected** — the code is not part of the
  database
* Product impact: an attribution surface must become visible to users before
  public release

### Option 2 — regenerate without HOT/OSM-derived records or fields

* Records lost: **896 (16.8%)**
* **All 50 clinics and all 92 pharmacies disappear**, along with 754 of 924
  hospitals, leaving 170
* The `self_care` urgency path (pharmacies and health centres) loses its
  pharmacy half entirely; the `urgent` path (hospitals and clinics) loses all
  clinics and 82% of hospitals
* Requires a new artifact version, a new build, revalidation and a store
  submission

## Recommendation

**Option 1.** It is by a wide margin the smaller production change: zero
records, zero artifact bytes, one notice file and one visible attribution
surface. Option 2 would delete a sixth of the dataset and two entire facility
categories from a clinical-decision-support product in order to avoid writing
an attribution notice that the licence would require anyway.

The one real obligation Option 1 adds is that the database stays publicly
available under ODbL. It already is.
