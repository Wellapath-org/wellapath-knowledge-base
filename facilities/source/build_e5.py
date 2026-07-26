import csv
import json
import math
import hashlib
import re
import sys

GRID3_FILE = "GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv"
OSM_FILE = "hotosm_nga_health_facilities.csv"
OUT_FILE = "facilities.ng.v1.0.json"

TARGET_STATES = {"lagos", "lagos state", "fct", "federal capital territory", "abuja", "kano", "kano state"}

def normalize_state(raw):
    if not raw:
        return None
    s = raw.strip().lower()
    if s in ("lagos", "lagos state"):
        return "Lagos"
    if s in ("fct", "federal capital territory", "abuja"):
        return "FCT"
    if s in ("kano", "kano state"):
        return "Kano"
    return None

def title_case(name):
    if not name:
        return None
    name = re.sub(r"\s+", " ", name.strip())
    if not name:
        return None
    return name.title()

GRID3_TYPE_MAP = {
    "general hospital": "hospital",
    "teaching/tertiary hospital": "hospital",
    "teaching/tertiary\xa0hospital": "hospital",
    "specialized hospital": "hospital",
    "primary health center": "health_centre",
    "primary health clinic": "health_centre",
    "health post": "health_centre",
}

OSM_TYPE_MAP = {
    "hospital": "hospital",
    "clinic": "clinic",
    "doctors": "clinic",
    "doctor": "clinic",
    "medical_centre": "clinic",
    "pharmacy": "pharmacy",
    "chemist": "pharmacy",
    "drugstore": "pharmacy",
    "health_centre": "health_centre",
    "health_post": "health_centre",
    "dispensary": "health_centre",
    "primary_health_care": "health_centre",
    "phc": "health_centre",
    "maternity": "maternity",
    "maternity_home": "maternity",
    "maternity_clinic": "maternity",
}

VALID_TYPES = {"hospital", "clinic", "pharmacy", "health_centre", "maternity"}

LAT_MIN, LAT_MAX = 4.0, 14.0
LON_MIN, LON_MAX = 2.5, 15.0

log = {
    "grid3_raw": 0,
    "grid3_state_filtered": 0,
    "osm_raw": 0,
    "osm_state_filtered": 0,
    "type_mismatch_grid3": 0,
    "type_mismatch_osm": 0,
    "type_mismatch_examples": {},
    "coord_excluded": 0,
    "no_name_excluded": 0,
    "duplicates_removed": 0,
}

def record_type_mismatch(source, raw_value):
    key = f"{source}:{raw_value}"
    log["type_mismatch_examples"][key] = log["type_mismatch_examples"].get(key, 0) + 1

def valid_coord(lat, lon):
    if lat is None or lon is None:
        return False
    if lat == 0 or lon == 0:
        return False
    if not (LAT_MIN <= lat <= LAT_MAX):
        return False
    if not (LON_MIN <= lon <= LON_MAX):
        return False
    return True

def to_float(v):
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None

# ---------- STEP 2 + 3: GRID3 ----------
grid3_records = []
with open(GRID3_FILE, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        log["grid3_raw"] += 1
        state = normalize_state(row.get("state", ""))
        if state is None:
            continue
        log["grid3_state_filtered"] += 1

        raw_type = (row.get("facility_level_option") or "").strip().lower()
        raw_type = raw_type.replace("\xa0", " ")
        mapped_type = GRID3_TYPE_MAP.get(raw_type)
        if mapped_type is None:
            log["type_mismatch_grid3"] += 1
            record_type_mismatch("GRID3", raw_type or "(empty)")
            continue

        lat = to_float(row.get("latitude"))
        lon = to_float(row.get("longitude"))

        name = title_case(row.get("facility_name"))

        grid3_records.append({
            "name": name,
            "type": mapped_type,
            "state": state,
            "city_area": row.get("lga") or None,
            "latitude": lat,
            "longitude": lon,
            "phone": row.get("phone") or None,
            "opening_hours": row.get("opening_hours") or None,
            "_source": "GRID3",
        })

# ---------- STEP 2 + 3: OSM ----------
osm_records = []
with open(OSM_FILE, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        log["osm_raw"] += 1
        state = normalize_state(row.get("adm1_name", ""))
        if state is None:
            continue
        log["osm_state_filtered"] += 1

        raw_type = (row.get("amenity") or "").strip().lower()
        if not raw_type:
            raw_type = (row.get("healthcare") or "").strip().lower()
        mapped_type = OSM_TYPE_MAP.get(raw_type)
        if mapped_type is None:
            log["type_mismatch_osm"] += 1
            record_type_mismatch("OSM", raw_type or "(empty)")
            continue

        lat = to_float(row.get("latitude"))
        lon = to_float(row.get("longitude"))

        name = title_case(row.get("name"))

        city_area = row.get("addr_city") or row.get("addr_full") or row.get("adm2_name") or None

        osm_records.append({
            "name": name,
            "type": mapped_type,
            "state": state,
            "city_area": city_area,
            "latitude": lat,
            "longitude": lon,
            "phone": row.get("phone") or row.get("contact:phone") or None,
            "opening_hours": row.get("opening_hours") or None,
            "_source": "OSM",
        })

# ---------- STEP 4: coordinate validation ----------
def filter_coords(records):
    kept = []
    excluded = 0
    for r in records:
        if valid_coord(r["latitude"], r["longitude"]):
            kept.append(r)
        else:
            excluded += 1
    return kept, excluded

grid3_records, ex1 = filter_coords(grid3_records)
osm_records, ex2 = filter_coords(osm_records)
log["coord_excluded"] = ex1 + ex2

# ---------- STEP 5: clean + no-name removal ----------
def remove_no_name(records):
    kept = []
    removed = 0
    for r in records:
        if not r["name"]:
            removed += 1
            continue
        kept.append(r)
    return kept, removed

grid3_records, rn1 = remove_no_name(grid3_records)
osm_records, rn2 = remove_no_name(osm_records)
log["no_name_excluded"] = rn1 + rn2

# ---------- STEP 5: dedup (keep GRID3, discard OSM within 0.005 deg + same name) ----------
def name_key(name):
    return re.sub(r"\s+", " ", name.strip().lower())

grid3_by_state = {}
for r in grid3_records:
    grid3_by_state.setdefault(r["state"], []).append(r)

deduped_osm = []
dup_count = 0
for o in osm_records:
    o_key = name_key(o["name"])
    is_dup = False
    for g in grid3_by_state.get(o["state"], []):
        if name_key(g["name"]) != o_key:
            continue
        dlat = g["latitude"] - o["latitude"]
        dlon = g["longitude"] - o["longitude"]
        dist = math.sqrt(dlat * dlat + dlon * dlon)
        if dist <= 0.005:
            is_dup = True
            break
    if is_dup:
        dup_count += 1
    else:
        deduped_osm.append(o)

log["duplicates_removed"] = dup_count
osm_records = deduped_osm

all_records = grid3_records + osm_records

# ---------- STEP 6: assign facility_id ----------
STATE_CODE = {"Lagos": "lag", "FCT": "abj", "Kano": "kan"}
STATE_ORDER = ["Lagos", "FCT", "Kano"]

# deterministic order: state, then GRID3 before OSM, then by name
all_records.sort(key=lambda r: (STATE_ORDER.index(r["state"]), 0 if r["_source"] == "GRID3" else 1, r["name"]))

counters = {"Lagos": 0, "FCT": 0, "Kano": 0}
for r in all_records:
    counters[r["state"]] += 1
    r["facility_id"] = f"ng_{STATE_CODE[r['state']]}_{counters[r['state']]:03d}"

# ---------- STEP 7: emergency_capable ----------
for r in all_records:
    if r["type"] == "hospital":
        r["emergency_capable"] = True
    elif r["type"] == "maternity":
        r["emergency_capable"] = True
    elif r["opening_hours"] == "24/7":
        r["emergency_capable"] = True
    else:
        r["emergency_capable"] = False

# ---------- final facility objects (10 fields, drop _source) ----------
facilities = []
for r in all_records:
    facilities.append({
        "facility_id": r["facility_id"],
        "name": r["name"],
        "type": r["type"],
        "state": r["state"],
        "city_area": r["city_area"],
        "latitude": round(r["latitude"], 7),
        "longitude": round(r["longitude"], 7),
        "phone": r["phone"],
        "opening_hours": r["opening_hours"],
        "emergency_capable": r["emergency_capable"],
    })

# ---------- STEP 8: build artifact ----------
artifact = {
    "_metadata": {
        "artifact_id": "facilities",
        "version": "1.0",
        "schema_version": "1.0",
        "country": "ng",
        "release_date": "2026-04-06",
        "total_facilities": len(facilities),
        "states_covered": ["Lagos", "FCT", "Kano"],
        "sources": [
            {
                "name": "GRID3 NGA Health Facilities v2.0",
                "url": "https://data.grid3.org/datasets/GRID3::grid3-nga-health-facilities-/explore",
                "last_updated": "2024-11",
                "license": "CC BY 4.0",
                "reliability": 5
            },
            {
                "name": "HDX Nigeria Health Facilities (OSM Export)",
                "url": "https://data.humdata.org/dataset/hotosm_nga_health_facilities",
                "last_updated": "2025-02",
                "license": "ODbL",
                "reliability": 4
            }
        ],
        "coordinate_bounds": {
            "lat_min": 4.0, "lat_max": 14.0,
            "lon_min": 2.5, "lon_max": 15.0,
            "all_valid": True
        },
        "urgency_filter_logic": {
            "emergency": "Show emergency_capable=true facilities first",
            "urgent": "Show hospitals and clinics",
            "non_urgent": "Show hospitals, clinics, and health_centres",
            "self_care": "Show pharmacies and health_centres"
        },
        "type_enum": ["hospital", "clinic", "pharmacy", "health_centre", "maternity"]
    },
    "facilities": facilities
}

with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(artifact, f, ensure_ascii=False, indent=2)

# ---------- STEP 9: sha256 ----------
with open(OUT_FILE, "rb") as f:
    file_bytes = f.read()
sha256 = hashlib.sha256(file_bytes).hexdigest()

# ---------- STEP 10: exit criteria ----------
ec_results = {}

ec_results["EC1"] = artifact["_metadata"]["total_facilities"] == len(artifact["facilities"])

ids = [f["facility_id"] for f in facilities]
ec_results["EC2"] = len(ids) == len(set(ids))

ec_results["EC3"] = all(f["type"] in VALID_TYPES for f in facilities)

ec_results["EC4"] = all(
    LAT_MIN <= f["latitude"] <= LAT_MAX and LON_MIN <= f["longitude"] <= LON_MAX
    for f in facilities
)

ec_results["EC5"] = all(isinstance(f["emergency_capable"], bool) for f in facilities)

states_present = {f["state"] for f in facilities}
ec_results["EC6"] = {"Lagos", "FCT", "Kano"} <= states_present

ec_results["EC7"] = len(facilities) > 0

try:
    with open(OUT_FILE, encoding="utf-8") as f:
        json.load(f)
    ec_results["EC8"] = True
except Exception:
    ec_results["EC8"] = False

REQUIRED_FIELDS = {"facility_id", "name", "type", "state", "city_area", "latitude",
                   "longitude", "phone", "opening_hours", "emergency_capable"}
ec_results["EC9"] = all(set(f.keys()) == REQUIRED_FIELDS for f in facilities)

ec_results["EC10"] = all(f["name"] and f["name"].strip() for f in facilities)

# ---------- STEP 11: summary ----------
by_state = {"Lagos": 0, "FCT": 0, "Kano": 0}
by_type = {"hospital": 0, "clinic": 0, "pharmacy": 0, "health_centre": 0, "maternity": 0}
emergency_count = 0
for f in facilities:
    by_state[f["state"]] += 1
    by_type[f["type"]] += 1
    if f["emergency_capable"]:
        emergency_count += 1

total_type_mismatch = log["type_mismatch_grid3"] + log["type_mismatch_osm"]
pass_count = sum(1 for v in ec_results.values() if v)

print("=" * 70)
print("PIPELINE LOG")
print("=" * 70)
print(f"GRID3 raw rows: {log['grid3_raw']}, after state filter: {log['grid3_state_filtered']}")
print(f"OSM raw rows: {log['osm_raw']}, after state filter: {log['osm_state_filtered']}")
print(f"Type mismatch excluded (GRID3): {log['type_mismatch_grid3']}")
print(f"Type mismatch excluded (OSM): {log['type_mismatch_osm']}")
print("Type mismatch raw value breakdown (top 15):")
for k, v in sorted(log["type_mismatch_examples"].items(), key=lambda x: -x[1])[:15]:
    print(f"    {k}: {v}")
print(f"Coordinate-error exclusions: {log['coord_excluded']}")
print(f"No-name exclusions: {log['no_name_excluded']}")
print(f"Duplicates removed (OSM discarded in favor of GRID3): {log['duplicates_removed']}")
print()
print("=" * 70)
print("EXIT CRITERIA")
print("=" * 70)
for k in ["EC1","EC2","EC3","EC4","EC5","EC6","EC7","EC8","EC9","EC10"]:
    print(f"{k}: {'PASS' if ec_results[k] else 'FAIL'}")
print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"TOTAL FACILITIES: {len(facilities)}")
print(f"BY STATE: Lagos={by_state['Lagos']}, FCT={by_state['FCT']}, Kano={by_state['Kano']}")
print(f"BY TYPE: hospital={by_type['hospital']}, clinic={by_type['clinic']}, pharmacy={by_type['pharmacy']}, health_centre={by_type['health_centre']}, maternity={by_type['maternity']}")
print(f"EMERGENCY CAPABLE: {emergency_count}/{len(facilities)}")
print(f"RECORDS EXCLUDED (coord errors): {log['coord_excluded']}")
print(f"RECORDS EXCLUDED (type mismatch): {total_type_mismatch}")
print(f"DUPLICATES REMOVED: {log['duplicates_removed']}")
print(f"SHA-256: sha256:{sha256}")
print(f"EXIT CRITERIA: {pass_count}/10 PASS")
print()
print(f"Output file size: {len(file_bytes)} bytes ({len(file_bytes)/1024/1024:.2f} MB)")
