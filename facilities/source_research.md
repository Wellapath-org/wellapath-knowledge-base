# E5.1 — Facility Source Research
**WellaPath Nigeria CDSS — Phase E5**
Repo: `wellapath-knowledge-base/facilities/source_research.md`
Date: 2026-04-06

---

## Summary

Five sources were investigated. Two provided the usable data that
built `facilities.ng.v1.0.json`. Two (NPHCDA, PCN) have no public
bulk download. The NHFR API (hfr.fmohconnect.gov.ng/developers) was
assessed and an access request was submitted — no response received
before the MVP deadline, so the GRID3 + OSM approach was used. NHFR
API access remains the recommended upgrade path for v1.1.

---

## Source 1 — GRID3 NGA Health Facilities v2.0 ★ PRIMARY

| Field | Detail |
|---|---|
| URL | https://data.grid3.org/datasets/GRID3::grid3-nga-health-facilities-/explore |
| Access | Free CSV download — no registration required |
| Format | CSV |
| National coverage | ~39,000 facilities across all 36 states and FCT |
| Fields available | facility_name, facility_level_option, state, lga, ward, latitude, longitude |
| Last updated | November 2024 |
| License | CC BY 4.0 |
| Reliability | **5/5** |

**Assessment:** Best available source. Produced by CIESIN at Columbia
University incorporating 2024 Nigeria Health Facility Registry (HFR)
updates. Covers all 36 states and FCT. GPS-verified coordinates.
Actively maintained.

**Known limitation:** `facility_level_option` is the only type field.
Values used: Primary Health Center, Primary Health Clinic, Health Post
→ `health_centre`; General Hospital, Teaching/Tertiary Hospital,
Specialized Hospital → `hospital`. No clinic, pharmacy, or maternity
tags exist in this source — those come from OSM. 746 records with
value `Unknown` were excluded.

**Citation:** CIESIN, Columbia University (2024). GRID3 NGA Health
Facilities v2.0. https://doi.org/10.7916/kv1n-0743

---

## Source 2 — HDX Nigeria Health Facilities (OSM Export) ★ SECONDARY

| Field | Detail |
|---|---|
| URL | https://data.humdata.org/dataset/hotosm_nga_health_facilities |
| Access | Free CSV download — no registration required |
| Format | CSV |
| Coverage | OSM-tagged amenity/healthcare nodes nationally |
| Fields available | name, amenity, healthcare, adm1_name, adm2_name, addr_city, latitude, longitude, phone, opening_hours |
| Last updated | February 2025 |
| License | ODbL (OpenStreetMap) |
| Reliability | **4/5** |

**Assessment:** Primary source for clinic and pharmacy records, which
are absent from GRID3. Lagos and Abuja have strong OSM coverage.
Kano has sparser coverage, particularly for pharmacies. Used for type
diversity (clinic, pharmacy) and to supplement GRID3 facility counts.
456 OSM records deduplicated against GRID3 records (GRID3 preferred).

---

## Source 3 — NHFR API (hfr.fmohconnect.gov.ng)

| Field | Detail |
|---|---|
| URL | https://hfr.fmohconnect.gov.ng/developers |
| Access | API key required — request form available |
| Format | REST JSON / FHIR R4 |
| Coverage | All facility types nationally including pharmacies and labs |
| License | Government — access granted per request |
| Reliability | **5/5 (assessed)** |

**Assessment:** Best possible source — direct from FMOH, live data,
queryable by state and type. API key request submitted before E5
execution. No response received within the build window. **This is
the recommended primary source for facilities.ng.v1.1.json** once
access is granted.

---

## Source 4 — NPHCDA

| Field | Detail |
|---|---|
| URL | https://nphcda.gov.ng |
| Access | No bulk download — web portal aggregates only |
| Reliability | **2/5** |

**Assessment:** No individual facility coordinates available publicly.
GRID3 v2.0 already incorporates NPHCDA PHC data via the HFR.

---

## Source 5 — PCN (Pharmacy Council of Nigeria)

| Field | Detail |
|---|---|
| URL | https://pcn.gov.ng |
| Access | Individual premises lookup only — no bulk export |
| Reliability | **2/5** |

**Assessment:** No GPS coordinates or bulk download. Used for
pharmacy type verification only. Formal data sharing agreement
recommended for E7 national expansion.

---

## Recommended Upgrade Path

| Priority | Action |
|---|---|
| 1 | Obtain NHFR API key and rebuild as facilities.ng.v1.1.json |
| 2 | Add maternity coverage via OSM `birthing_center` tag mapping |
| 3 | Pursue PCN data sharing agreement for licensed pharmacy coordinates |
| 4 | Expand to all 36 states in E7 using GRID3 national file |
