# E5.2 — Facility Schema v1.0 (LOCKED)
**WellaPath Nigeria CDSS — Phase E5**
Repo: `wellapath-knowledge-base/facilities/facility_schema_v1.0.md`
Date: 2026-04-06
Status: **LOCKED — field additions or renames require schema version
bump to v2.0 and engineering lead review**

---

## Facility Object Schema

```json
{
  "facility_id":       "ng_lag_001",
  "name":              "Lagos University Teaching Hospital",
  "type":              "hospital",
  "state":             "Lagos",
  "city_area":         "Surulere",
  "latitude":          6.5064,
  "longitude":         3.3602,
  "phone":             "+2348012345678",
  "opening_hours":     "24/7",
  "emergency_capable": true
}
```

---

## Field Definitions

### `facility_id`
- **Type:** string — required, unique
- **Format:** `ng_{state_code}_{sequential_number}` zero-padded to 3 digits
- **State codes:** `lag` = Lagos, `abj` = FCT, `kan` = Kano
- **Examples:** `ng_lag_001`, `ng_abj_042`, `ng_kan_007`
- **Rule:** Never reassign a retired ID. Sequential per state.

### `name`
- **Type:** string — required
- **Format:** Title case. No ALL CAPS. No trailing punctuation.

### `type`
- **Type:** string — required
- **Enum — 5 values only:**

| Value | Description |
|---|---|
| `hospital` | Secondary or tertiary — inpatient, emergency, surgical capacity |
| `clinic` | Outpatient — no full emergency capacity |
| `pharmacy` | Licensed pharmacy or patent medicine store |
| `health_centre` | Primary health centre / PHC / health post |
| `maternity` | Dedicated maternity or maternal-neonatal facility |

### `state`
- **Type:** string — required
- **Values:** `Lagos`, `FCT`, `Kano` (expand as states added)
- **Use `FCT`** for Federal Capital Territory — not "Abuja"

### `city_area`
- **Type:** string or null — required (null if unknown)
- **Format:** LGA or area name within the state

### `latitude` / `longitude`
- **Type:** float — required
- **Format:** Decimal degrees, minimum 4 decimal places
- **Nigeria bounds:** lat 4.0–14.0, lon 2.5–15.0
- **Rule:** Exclude any facility outside these bounds

### `phone`
- **Type:** string or null — required (null if unavailable)
- **Format:** `+234XXXXXXXXXX`

### `opening_hours`
- **Type:** string or null — required (null if unknown)
- **Format:** Free text — `"24/7"`, `"Mon-Fri 8am-5pm"` etc.

### `emergency_capable`
- **Type:** boolean — required, never null, default false
- **Tagging rules (applied in order):**

| Condition | Value |
|---|---|
| `type == "hospital"` | `true` |
| `type == "maternity"` | `true` |
| `opening_hours == "24/7"` | `true` |
| All other cases | `false` |

---

## Urgency-Based Filtering Logic (E6 mobile)

| CDSS urgency | Facility filter |
|---|---|
| `emergency` | `emergency_capable: true` first |
| `urgent` | `type` in `["hospital", "clinic"]` |
| `non_urgent` | `type` in `["hospital", "clinic", "health_centre"]` |
| `self_care` | `type` in `["pharmacy", "health_centre"]` |

---

## Artifact Versioning

- Filename: `facilities.{country}.v{major}.{minor}.json`
- **Minor bump** (v1.0 → v1.1): content changes — new facilities,
  corrected coordinates, updated phones
- **Major bump** (v1.0 → v2.0): schema field added, renamed, removed
- Never overwrite a versioned file — new version = new filename

---

## Known Limitations in v1.0

- `phone` is null for all 5,344 records — GRID3 and OSM exports do
  not carry phone data for most Nigerian facilities. Populate from
  NHFR API in v1.1.
- `opening_hours` is null for all 5,344 records — same reason.
  `emergency_capable` is therefore driven by type only in v1.0.
- `maternity` type count is 0 — neither GRID3 nor the OSM export
  used in this build tags maternity as a distinct type. OSM
  `birthing_center` tags exist but were not in the mapping spec.
  Add in v1.1 when NHFR API data is available.
