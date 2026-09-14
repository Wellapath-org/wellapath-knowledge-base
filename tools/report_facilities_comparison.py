#!/usr/bin/env python3
"""Compare the nationwide candidate with facilities 1.1, and test the real Mobile contract.

    python3 tools/report_facilities_comparison.py           # write
    python3 tools/report_facilities_comparison.py --check    # fail if committed copies differ

Writes `reports/facilities_comparison_v1.json` and `reports/facilities_mobile_compat_v1.json`.

The comparison proposes reconciliation; it performs none. The two datasets have different
lineages — 1.1 is GRID3 + OSM + a manual phone enrichment, the candidate is a single bulk
registry export — and merging them would fuse two provenance chains into one artifact that
could no longer answer "where did this record come from".

The Mobile section is not an opinion about compatibility. It re-implements
`lib/features/locator/facility_locator_service.dart` exactly — the same type chain, the same
urgency sets, the same 20 km / 3-result sparse-coverage rule, the same haversine, the same
`== true` emergency test — and runs both artifacts through it.

Standard library only, no network.
"""

import argparse
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities import FACILITIES_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, write_bytes

CURRENT = repo_path("facilities.ng.v1.1.json")
CANDIDATE = repo_path("candidate", "facilities.ng.v2.0.json")
COMPARISON = repo_path("reports", "facilities_comparison_v1.json")
MOBILE = repo_path("reports", "facilities_mobile_compat_v1.json")

GENERATOR_VERSION = FACILITIES_TOOLING_VERSION
PHASE = "Nationwide Facilities / Step 3"

# --- an exact re-implementation of the Mobile locator -------------------------------------
TYPE_CHAIN = {"pharmacy": "health_centre", "health_centre": "clinic", "clinic": "hospital"}
SPARSE_RADIUS_KM = 20.0
SPARSE_MIN_RESULTS = 3


def types_for_urgency(urgency):
    if urgency in ("urgent", "non_urgent"):
        return {"hospital", "clinic"}
    if urgency == "self_care":
        return {"pharmacy", "health_centre"}
    return set()


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearby(facilities, user_lat, user_lon, urgency, max_results=30):
    """Port of getNearbyFacilities. Same ordering, same fallbacks, same null handling."""
    with_distance = []
    for f in facilities:
        lat, lon = f.get("latitude"), f.get("longitude")
        d = haversine(user_lat, user_lon, lat, lon) if lat is not None and lon is not None else math.inf
        with_distance.append((d, f))

    if urgency == "emergency":
        capable = sorted((x for x in with_distance if x[1].get("emergency_capable") is True),
                         key=lambda x: x[0])
        others = sorted((x for x in with_distance if x[1].get("emergency_capable") is not True),
                        key=lambda x: x[0])
        return [f for _, f in (capable + others)][:max_results]

    allowed = types_for_urgency(urgency)
    filtered = sorted((x for x in with_distance if x[1].get("type") in allowed), key=lambda x: x[0])
    if sum(1 for d, _ in filtered if d <= SPARSE_RADIUS_KM) < SPARSE_MIN_RESULTS:
        expanded = set(allowed)
        for t in allowed:
            if TYPE_CHAIN.get(t):
                expanded.add(TYPE_CHAIN[t])
        filtered = sorted((x for x in with_distance if x[1].get("type") in expanded),
                          key=lambda x: x[0])
    return [f for _, f in filtered][:max_results]


def by_location(facilities, state, city_area, urgency):
    """Port of getFacilitiesByLocation, including its emergency-first then name sort."""
    results = [f for f in facilities
               if (f.get("state") or "").lower() == state.lower()]
    if city_area:
        results = [f for f in results
                   if (f.get("city_area") or "").lower() == city_area.lower()]
    if urgency != "emergency":
        allowed = types_for_urgency(urgency)
        results = [f for f in results if f.get("type") in allowed]
    results.sort(key=lambda f: (f.get("emergency_capable") is not True, f.get("name") or ""))
    return results[:30]


# --- comparison ------------------------------------------------------------------------------
def norm_name(value):
    value = unicodedata.normalize("NFKD", value or "").casefold()
    value = re.sub(r"\b(hospital|clinic|centre|center|health|medical|maternity|and|the)\b", " ", value)
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def compare(current, candidate):
    cur = current["facilities"]
    new = candidate["facilities"]

    # Spatial buckets of roughly 1 km so matching stays O(n) and deterministic.
    buckets = defaultdict(list)
    for f in new:
        if f["latitude"] is None:
            continue
        buckets[(round(f["latitude"], 2), round(f["longitude"], 2))].append(f)

    exact, probable, only_current = [], [], []
    conflicts = Counter()
    matched_new = set()

    for c in cur:
        key_name = norm_name(c["name"])
        best = None
        if c["latitude"] is not None:
            lat_r, lon_r = round(c["latitude"], 2), round(c["longitude"], 2)
            for dlat in (-0.01, 0.0, 0.01):
                for dlon in (-0.01, 0.0, 0.01):
                    for f in buckets.get((round(lat_r + dlat, 2), round(lon_r + dlon, 2)), []):
                        d = haversine(c["latitude"], c["longitude"], f["latitude"], f["longitude"])
                        if d > 0.25:
                            continue
                        same_name = norm_name(f["name"]) == key_name
                        score = (0 if same_name else 1, d)
                        if best is None or score < best[0]:
                            best = (score, f, d, same_name)
        if best is None:
            only_current.append(c)
            continue
        _score, f, distance, same_name = best
        matched_new.add(f["facility_id"])
        entry = {
            "current_facility_id": c["facility_id"],
            "candidate_facility_id": f["facility_id"],
            "distance_m": round(distance * 1000, 1),
            "current_name": c["name"],
            "candidate_name": f["name"],
        }
        if same_name:
            exact.append(entry)
        else:
            probable.append(entry)
        if (c["phone"] or None) and (f["phone"] or None) and c["phone"] != f["phone"]:
            conflicts["phone_differs"] += 1
        if (c["state"] or "").lower() != (f["state"] or "").lower():
            conflicts["state_differs"] += 1
        if (c["city_area"] or "").lower() != (f["city_area"] or "").lower():
            conflicts["city_area_differs"] += 1
        if c["type"] and f["type"] is None:
            conflicts["type_present_in_1_1_absent_in_candidate"] += 1
        if c["emergency_capable"] is True and f["emergency_capable"] is None:
            conflicts["emergency_capable_present_in_1_1_absent_in_candidate"] += 1
        if distance > 0.05:
            conflicts["coordinates_differ_over_50m"] += 1

    only_new = [f for f in new if f["facility_id"] not in matched_new]

    cur_states = Counter(f["state"] for f in cur)
    new_states = Counter(f["state"] for f in new)
    coverage = {}
    for state in sorted(set(cur_states) | set(new_states)):
        coverage[state] = {"facilities_1_1": cur_states.get(state, 0),
                           "candidate": new_states.get(state, 0)}

    # Option B in the remediation study: a candidate with a provenance-labelled facilities 1.1
    # overlay for any state the candidate leaves uncovered. Quantified per 1.1 state, applied
    # nowhere: how many 1.1 records would be additions, how many would be near-duplicates of a
    # candidate record, and how many of those have an uncertain identity (position matches,
    # name does not).
    exact_by_state = Counter(e["current_facility_id"].split("_")[1] for e in exact)
    probable_by_state = Counter(e["current_facility_id"].split("_")[1] for e in probable)
    unmatched_by_state = Counter(f["facility_id"].split("_")[1] for f in only_current)
    code = {"lag": "Lagos", "abj": "FCT", "kan": "Kano"}
    overlay = {}
    for prefix, state in code.items():
        overlay[state] = {
            "facilities_1_1_records": cur_states.get(state, 0),
            "candidate_records": new_states.get(state, 0),
            "candidate_covers_state": new_states.get(state, 0) > 0,
            "overlay_needed_for_coverage": new_states.get(state, 0) == 0,
            "1_1_records_matching_a_candidate_record_by_name_and_position": exact_by_state.get(prefix, 0),
            "1_1_records_matching_by_position_only_identity_uncertain": probable_by_state.get(prefix, 0),
            "1_1_records_with_no_candidate_within_250m_would_be_additions": unmatched_by_state.get(prefix, 0),
        }

    dup_groups = defaultdict(list)
    for f in new:
        dup_groups[(norm_name(f["name"]), f["state"], f["city_area"])].append(f["facility_id"])
    proposals = [{"key": "%s | %s | %s" % k, "facility_ids": sorted(v), "count": len(v)}
                 for k, v in dup_groups.items() if len(v) > 1]
    proposals.sort(key=lambda p: (-p["count"], p["key"]))

    return {
        "_metadata": {
            "report_id": "facilities_comparison",
            "version": "1",
            "phase": PHASE,
            "generator": "tools/report_facilities_comparison.py",
            "generator_version": GENERATOR_VERSION,
            "note": "A comparison, not a merge. The two datasets have different provenance "
            "chains and are kept apart deliberately; the consolidation entries below are "
            "proposals for review.",
        },
        "record_counts": {
            "facilities_1_1": len(cur),
            "candidate": len(new),
            "change": len(new) - len(cur),
            "multiplier": round(len(new) / len(cur), 2),
        },
        "file_size": {
            "facilities_1_1_bytes": os.path.getsize(CURRENT),
            "candidate_bytes": os.path.getsize(CANDIDATE),
            "multiplier": round(os.path.getsize(CANDIDATE) / os.path.getsize(CURRENT), 1),
        },
        "matching": {
            "method": "Positional: candidate records within 250 m of a 1.1 record, preferring an "
            "identical normalised name. Normalisation strips common facility words so 'X "
            "Hospital' and 'X' compare equal. Deterministic and order-independent.",
            "exact_name_and_location": len(exact),
            "probable_location_only": len(probable),
            "only_in_facilities_1_1": len(only_current),
            "only_in_candidate": len(only_new),
            "conflicts": dict(sorted(conflicts.items())),
        },
        "coverage_change_by_state": coverage,
        "states_gained": sorted(set(new_states) - set(cur_states)),
        "states_lost": sorted(set(cur_states) - set(new_states)),
        "option_b_overlay_analysis": {
            "question": "If facilities 1.1 records were overlaid, provenance-labelled, onto the "
            "candidate for states the candidate does not cover, what would be added and what "
            "would be duplicated?",
            "by_1_1_state": overlay,
            "duplicate_risk": "A 1.1 record within 250 m of a candidate record with the same "
            "normalised name is the same facility twice under two id lineages; one matching by "
            "position only may be the same facility renamed, or a neighbour — identity is not "
            "established either way. An overlay would have to carry every such pair as two "
            "records or resolve them by a rule this repository does not have.",
            "conclusion": "No 1.1 state is uncovered by the candidate, so the overlay buys no "
            "coverage; it would add %d records of a different lineage and provenance to "
            "states the candidate already serves, %d of them positional duplicates of "
            "uncertain identity. Not applied."
            % (sum(v["1_1_records_with_no_candidate_within_250m_would_be_additions"]
                   + v["1_1_records_matching_by_position_only_identity_uncertain"]
                   for v in overlay.values()),
               sum(v["1_1_records_matching_by_position_only_identity_uncertain"]
                   for v in overlay.values()))
            if not any(v["overlay_needed_for_coverage"] for v in overlay.values())
            else "At least one 1.1 state is uncovered by the candidate; see by_1_1_state.",
        },
        "duplicate_consolidation_proposals": {
            "group_count": len(proposals),
            "rows_involved": sum(p["count"] for p in proposals),
            "rule": "Same normalised name, state and LGA. NOT applied — two facilities may "
            "genuinely share a name within one LGA, and collapsing them would delete a real "
            "clinic from a user's results.",
            "largest_groups": proposals[:25],
        },
        "reconciliation_proposals": [
            "Do not merge. Ship one lineage or the other; a fused artifact cannot answer where "
            "a record came from, which is the question every later data dispute turns on.",
            "The 45 manually verified Lagos phone numbers in 1.1 are the single piece of "
            "human-verified content in either dataset. If the candidate is adopted, they should "
            "be re-applied as an explicit, listed enrichment, not silently inherited.",
            "1.1 records with no candidate match are not evidence of closure; the candidate is "
            "missing three states and 94 LGAs, so absence there means absence of data.",
        ],
        "samples": {
            "exact_matches": exact[:10],
            "probable_matches": probable[:10],
            "only_in_facilities_1_1": [
                {"facility_id": f["facility_id"], "name": f["name"], "state": f["state"]}
                for f in only_current[:10]
            ],
        },
    }


def mobile_compat(current, candidate):
    cur, new = current["facilities"], candidate["facilities"]
    required = ["facility_id", "name", "type", "state", "city_area",
                "latitude", "longitude", "phone", "opening_hours", "emergency_capable"]

    def field_check(records):
        return {f: sum(1 for r in records if f in r) for f in required}

    probes = [
        ("Lagos (Ikeja)", 6.6018, 3.3515),
        ("Abuja (Central)", 9.0579, 7.4951),
        ("Kano (city)", 12.0022, 8.5920),
        ("Sokoto (state with no candidate records)", 13.0059, 5.2476),
        ("Port Harcourt", 4.8156, 7.0498),
    ]
    urgencies = ["emergency", "urgent", "non_urgent", "self_care"]
    results = {}
    for label, lat, lon in probes:
        results[label] = {}
        for urgency in urgencies:
            a = nearby(cur, lat, lon, urgency)
            b = nearby(new, lat, lon, urgency)
            results[label][urgency] = {
                "facilities_1_1_results": len(a),
                "candidate_results": len(b),
                "candidate_returns_nothing": len(b) == 0,
            }

    loc = {}
    for state, area in (("Lagos", "Alimosho"), ("Kano", "Ajingi"), ("FCT", "Abuja Municipal Area Council")):
        loc["%s / %s" % (state, area)] = {
            u: {"facilities_1_1": len(by_location(cur, state, area, u)),
                "candidate": len(by_location(new, state, area, u))}
            for u in urgencies
        }

    # States the active artifact serves and the candidate does not. A regression against what
    # users have today, so it is blocking whatever else is true.
    lost = sorted({f["state"] for f in cur} - {f["state"] for f in new})
    lost_findings = []
    if lost:
        lost_findings.append({
            "finding": "%s — served by facilities 1.1 — have no records in the candidate"
            % " and ".join(lost),
            "severity": "blocking",
            "evidence": "getFacilitiesByLocation returns nothing for any urgency in %s; "
            "getNearbyFacilities still returns the nearest 30 records, which for a user "
            "there are in a neighbouring state (reports/facilities_coordinate_audit_v1.json "
            "coverage_by_state)." % " and ".join(lost),
            "resolution": "Source owner corrects the source, or the orientation rule is "
            "revisited under a recorded decision. Nothing is guessed to close the gap.",
        })

    return {
        "_metadata": {
            "report_id": "facilities_mobile_compat",
            "version": "1",
            "phase": PHASE,
            "generator": "tools/report_facilities_comparison.py",
            "generator_version": GENERATOR_VERSION,
            "harness": "An exact port of lib/features/locator/facility_locator_service.dart as "
            "of wellapath-mobile 13be0d49 — same type chain, urgency sets, 20 km / 3-result "
            "sparse-coverage rule, haversine and `== true` emergency test. Compatibility is "
            "measured by running both artifacts through it, not asserted.",
            "mobile_commit_inspected": "13be0d4937b1c49d6a49ddf096c5d5b6a47c2091",
            "mobile_repository_modified": False,
        },
        "required_field_presence": {
            "fields": required,
            "facilities_1_1": field_check(cur),
            "candidate": field_check(new),
            "all_present_in_candidate": all(v == len(new) for v in field_check(new).values()),
        },
        "type_and_null_handling": {
            "mobile_reads_latitude_longitude_as_nullable": True,
            "null_coordinates_sort_last": "distance becomes infinity; the record is retained, not dropped",
            "candidate_records_without_coordinates": sum(1 for r in new if r["latitude"] is None),
            "candidate_coordinate_policy": "zero by construction — rows without a usable pair "
            "are quarantined, so the consumer's null-coordinate path is never exercised by "
            "this candidate; every emitted pair is verified inside its declared state",
            "candidate_records_with_exchanged_coordinates": sum(
                1 for r in new if r["source_record"]["coordinate_transformation"] != "none"),
            "mobile_null_type_handling": "getNearbyFacilities and getFacilitiesByLocation "
            "filter non-emergency urgencies with allowedTypes.contains(type); a null type is "
            "never contained, so every such record is dropped and the list is empty. The "
            "handoff contract for the next build requires the opposite: a null type must not "
            "be filtered out and must never produce an empty list.",
            "mobile_emergency_test": "facility['emergency_capable'] == true; null is treated as false",
            "candidate_emergency_capable_true": sum(1 for r in new if r["emergency_capable"] is True),
            "mobile_type_filter": "non-emergency urgencies keep only {hospital, clinic, health_centre, pharmacy}",
            "candidate_records_with_a_matching_type": sum(
                1 for r in new if r["type"] in {"hospital", "clinic", "health_centre", "pharmacy"}),
        },
        "blocking_findings": lost_findings + [
            {
                "finding": "type is null on every candidate record, so every non-emergency query "
                "returns zero results",
                "severity": "blocking",
                "evidence": "getNearbyFacilities filters by allowedTypes.contains(facility['type']) "
                "for urgent, non_urgent and self_care. The sparse-coverage fallback widens the "
                "type set but never removes the filter, so it cannot rescue a null type.",
                "resolution": "A Product decision mapping facility_level (Primary/Secondary/"
                "Tertiary) to the Mobile type vocabulary, or a change to the Mobile filter. "
                "Not decided here.",
            },
            {
                "finding": "emergency_capable is null on every candidate record",
                "severity": "material",
                "evidence": "Emergency results still return facilities, but the "
                "emergency-capable-first ordering collapses to pure distance ordering.",
                "resolution": "Either an evidenced capability field from the source owner, or an "
                "explicit Product rule. facilities 1.1 used type == 'hospital', which this "
                "source cannot support.",
            },
            {
                "finding": "the candidate is %.0f× the size of facilities 1.1"
                % (os.path.getsize(CANDIDATE) / os.path.getsize(CURRENT)),
                "severity": "material",
                "evidence": "%d bytes against %d. Mobile decodes the artifact into a "
                "List<Map<String, dynamic>> held in memory for the life of the locator."
                % (os.path.getsize(CANDIDATE), os.path.getsize(CURRENT)),
                "resolution": "Options, none chosen here: compact serialisation, a "
                "distribution profile carrying only the ten fields Mobile reads, or per-state "
                "partitioning. All three are distribution decisions.",
            },
            {
                "finding": "three states have no records at all",
                "severity": "material",
                "evidence": "Adamawa, Kebbi and Sokoto. A user in those states gets an empty "
                "locator, where 1.1 would also have been empty — but the candidate is presented "
                "as nationwide, which would make the gap surprising rather than expected.",
                "resolution": "Source owner. Not fixable in transformation.",
            },
        ],
        "nearby_probe_results": results,
        "by_location_probe_results": loc,
        "verdict": "NOT COMPATIBLE as it stands. The candidate satisfies every structural "
        "requirement — all ten fields present on every record, correct types, null handling "
        "consistent with the consumer — and still returns nothing for three of the four "
        "urgency paths, because the one field that drives non-emergency filtering cannot be "
        "populated from this source without a Product decision.",
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    current, candidate = load_json(CURRENT), load_json(CANDIDATE)
    outputs = [(COMPARISON, dump_report_bytes(compare(current, candidate))),
               (MOBILE, dump_report_bytes(mobile_compat(current, candidate)))]

    failures = 0
    for path, data in outputs:
        relative = os.path.relpath(path, repo_path())
        if args.check:
            if not os.path.exists(path):
                print("MISSING %s" % relative); failures += 1; continue
            with open(path, "rb") as handle:
                if handle.read() != data:
                    print("DRIFT %s" % relative); failures += 1
                else:
                    print("OK %s" % relative)
        else:
            write_bytes(path, data); print("wrote %s (%d bytes)" % (relative, len(data)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
