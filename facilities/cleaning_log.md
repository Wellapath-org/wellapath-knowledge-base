# E5.3 — Dataset Cleaning Log
**WellaPath Nigeria CDSS — Phase E5**
Repo: `wellapath-knowledge-base/facilities/cleaning_log.md`
Date: 2026-04-06
Built by: Claude Code (terminal) + data engineer
Script: `facilities/source/build_e5.py`

---

## Source Files

| File | Records | Source |
|---|---|---|
| `GRID3_NGA_health_facilities_v2_0_*.csv` | ~39,000 national | GRID3 v2.0, Nov 2024 |
| `hotosm_nga_health_facilities.csv` | ~7,537 national | HDX OSM Export, Feb 2025 |

---

## Pipeline Log

### State Filtering
| Source | Raw rows | After state filter (Lagos/FCT/Kano) |
|---|---|---|
| GRID3 | Full national | Retained for 3 states |
| OSM | 7,537 | Retained for 3 states |

State normalisation applied:
- "Lagos", "Lagos State" → `Lagos`
- "FCT", "Federal Capital Territory", "Abuja" → `FCT`
- "Kano", "Kano State" → `Kano`

### Type Mapping and Exclusions

**GRID3** — type field: `facility_level_option`

| Source value | Mapped to | Count |
|---|---|---|
| Primary Health Center | `health_centre` | majority |
| Primary Health Clinic | `health_centre` | — |
| Health Post | `health_centre` | — |
| General Hospital | `hospital` | — |
| Teaching/Tertiary Hospital | `hospital` | — |
| Specialized Hospital | `hospital` | — |
| **Unknown** | **excluded** | **725** |

**OSM** — type field: `amenity` or `healthcare` tag

| Source value | Mapped to |
|---|---|
| hospital | `hospital` |
| clinic, doctors, medical_centre | `clinic` |
| pharmacy, chemist | `pharmacy` |
| health_centre, health_post, dispensary, primary_health_care, phc | `health_centre` |
| maternity, maternity_home, maternity_clinic | `maternity` |
| laboratory, alternative, optometrist, dentist, yes, centre | **excluded** (21 records) |

**Total type-mismatch exclusions: 746** (725 GRID3 Unknown + 21 OSM unmapped)

### Coordinate Validation
- Bounds applied: lat 4.0–14.0, lon 2.5–15.0
- **Records excluded: 0** — all retained records had valid coordinates

### Name Cleaning
- Applied Python `.title()` normalisation to all names
- Collapsed multiple internal spaces with `re.sub(r"\s+", " ", name)`
- **Records excluded for no name: 0**

### Deduplication
- Method: name match (normalised lowercase) + proximity within 0.005°
  (~500m), GRID3 preferred over OSM
- **OSM records discarded as duplicates: 456**

### Phone and Opening Hours
- Neither GRID3 nor OSM exports carry phone or opening_hours data
  for the majority of Nigerian facilities in this dataset
- All 5,344 records: `phone: null`, `opening_hours: null`
- No values were fabricated or assumed
- `emergency_capable` is therefore determined by type only (hospital
  and maternity → true)

### Facility ID Assignment
- Sequential per state, GRID3 records ordered before OSM within each
  state, then alphabetical by name
- `ng_lag_001` to `ng_lag_2690` (Lagos)
- `ng_abj_001` to `ng_abj_614` (FCT)
- `ng_kan_001` to `ng_kan_2040` (Kano)

---

## Final Dataset

| Metric | Value |
|---|---|
| Total facilities | 5,344 |
| Lagos | 2,690 |
| FCT | 614 |
| Kano | 2,040 |
| hospital | 924 |
| clinic | 50 |
| pharmacy | 92 |
| health_centre | 4,278 |
| maternity | 0 |
| emergency_capable: true | 924 (17%) |
| phone populated | 0 |
| opening_hours populated | 0 |
| city_area populated | 5,344 (100%) |
| Coordinate errors | 0 |
| Duplicates removed | 456 |
| Type-mismatch exclusions | 746 |

---

## Known Limitations

1. **No phone or opening_hours data** — upgrade to NHFR API in v1.1
2. **No maternity records** — OSM `birthing_center` tag not in
   mapping spec; add in v1.1
3. **Pharmacy coverage sparse in Kano** — OSM coverage for pharmacies
   in northern states is limited; 92 pharmacies nationally of which
   the majority are in Lagos
4. **FCT count lower than Lagos and Kano** — 614 reflects actual
   facility density relative to Lagos (2,690) and Kano (2,040), not
   a data gap; FCT is geographically smaller with concentrated urban
   healthcare infrastructure
5. **GRID3 `Unknown` type excluded** — 725 records dropped due to
   unresolvable type; investigate in v1.1 whether additional type
   fields in GRID3 can resolve these

---

## Upgrade Path to v1.1

Once NHFR API access is obtained:
1. Query by state for Lagos, FCT, Kano
2. Map NHFR fields to WellaPath schema (phone and opening_hours will
   be populated)
3. Merge with existing records — NHFR takes priority over GRID3
4. Add maternity type mapping from NHFR facility categories
5. Version bump to `facilities.ng.v1.1.json` — same schema, richer data
