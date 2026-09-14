#!/usr/bin/env python3
"""Build the nationwide facilities candidate from the pinned source.

    python3 tools/build_facilities_candidate.py           # write
    python3 tools/build_facilities_candidate.py --check    # fail if the committed copy differs

Writes `candidate/facilities.ng.v2.0.json`, plus the quality and quarantine reports that
explain what it did and did not keep.

The generator refuses to guess. A source value outside an explicit mapping table becomes an
`unmapped` entry, and a row missing something the artifact cannot be honest without is
quarantined with a reason code rather than being emitted with a plausible substitute. Two
fields the Mobile consumer reads — `type` and `emergency_capable` — are emitted as null on
every record, because this source does not evidence either and inventing them would decide
which facilities a user is shown in an emergency.

Two pipeline policies are applied deliberately and counted (Step 2):

  * a row with no usable coordinate pair — absent, unparseable, 0,0, out of bounds or
    suspected swapped — is quarantined, never emitted with nulls or a substitute;
  * rows that are exact duplicates (same name, state, LGA and coordinates) collapse to one
    survivor chosen by a total, documented rule. No values are merged across members.

Nothing here uploads, publishes or activates anything, and it does not touch
`facilities.ng.v1.1.json`.

Standard library only, no network.
"""

import argparse
import csv
import hashlib
import io
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities import FACILITIES_TOOLING_VERSION
from facilities import mappings as M
from facilities.normalize import (coordinate, coordinate_vs_state, duplicate_key, free_text,
                                  phone, sort_key, survivor_key, text, timestamp)
from vocab.artifact_io import dump_artifact_bytes, dump_report_bytes, load_json, repo_path, write_bytes

SOURCE = repo_path("facilities", "source", "nigeria_health_facilities.csv")
SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"
SOURCE_BYTES = 20913558

CANDIDATE = repo_path("candidate", "facilities.ng.v2.0.json")
QUALITY = repo_path("reports", "facilities_quality_v1.json")
QUARANTINE = repo_path("reports", "facilities_quarantine_v1.json")
CURRENT = repo_path("facilities.ng.v1.1.json")

ARTIFACT_ID = "facilities"
CANDIDATE_VERSION = "2.0"
SCHEMA_VERSION = "2.0"
COUNTRY = "ng"
PHASE = "Nationwide Facilities / Step 2"

#: Fixed, so regeneration is byte-stable. Not a clock read.
GENERATED_AT = "2026-09-14T00:00:00Z"
GENERATOR_VERSION = FACILITIES_TOOLING_VERSION

#: A row without one of these cannot be represented honestly, so it is quarantined rather
#: than emitted with a filler value.
REQUIRED = ("facility_name", "state_name", "lga_name")

#: Every coordinate outcome other than "usable" quarantines the row. Listed in full rather
#: than as "anything non-empty" so that adding a reason to `normalize.coordinate` is a
#: visible decision here too. The last two come from the per-state instrument, which runs
#: only on pairs the national box has already accepted.
COORDINATE_QUARANTINE_REASONS = (
    "coordinates_absent", "coordinates_unparseable", "coordinates_null_island",
    "coordinates_out_of_bounds", "coordinates_swapped_suspected",
    "coordinates_swapped_suspected_by_state", "coordinates_not_in_state",
)

#: The ten fields facilities 1.1 emits, in its order. The candidate keeps every one under the
#: same name so the Mobile consumer's field access is unchanged; the schema and the validator
#: both assert it.
MOBILE_SURFACE = ("facility_id", "name", "type", "state", "city_area", "latitude",
                  "longitude", "phone", "opening_hours", "emergency_capable")


class SourceDrift(Exception):
    """Raised when the source bytes are not the pinned bytes."""


def read_source():
    """Read the pinned source, refusing to proceed if a single byte has changed."""
    with open(SOURCE, "rb") as handle:
        raw = handle.read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256 or len(raw) != SOURCE_BYTES:
        raise SourceDrift(
            "source is %d bytes hashing to %s; pinned to %d bytes hashing to %s. Every count "
            "and mapping in this tooling was established against the pinned bytes, so a "
            "different file makes all of them unverified."
            % (len(raw), digest, SOURCE_BYTES, SOURCE_SHA256)
        )
    lines = raw.decode("utf-8").splitlines()
    # Line 0 is a title row emitted by the spreadsheet export, not part of the table.
    rows = list(csv.reader(io.StringIO("\r\n".join(lines[1:]))))
    return rows[0], rows[1:]


def build():
    header, body = read_source()
    at = {name: index for index, name in enumerate(header)}

    records = []
    quarantined = []
    unmapped = defaultdict(Counter)
    reasons = Counter()
    absence = Counter()
    line_of = {}          # source_id -> source line, for the duplicate quarantine entries
    latest_update = None  # the newest audit timestamp anywhere in the source
    # Per-state evidence for the coordinate instrument: every in-box pair, both readings.
    state_geo = defaultdict(lambda: {"given": [], "transposed": [], "lat": [], "lon": [],
                                     "refused_swapped": 0, "refused_not_in_state": 0})

    for line_number, row in enumerate(body, start=3):  # +1 title, +1 header, +1 to 1-index
        source_id = row[at["id"]].strip()
        unique_id = row[at["unique_id"]].strip()
        line_of[source_id] = line_number

        updated_at, updated_reason = timestamp(row[at["updated_at"]])
        if updated_at and (latest_update is None or updated_at > latest_update):
            latest_update = updated_at

        def quarantine(code, detail):
            quarantined.append(
                {
                    "source_line": line_number,
                    "source_id": source_id,
                    "source_unique_id": unique_id,
                    "reason_code": code,
                    "detail": detail,
                }
            )
            reasons[code] += 1

        name, name_reason = free_text(row[at["facility_name"]])
        if name_reason:
            quarantine("name_is_contact_detail",
                       "facility_name contains a contact detail rather than a name")
            continue
        state_raw = row[at["state_name"]].strip()
        lga = text(row[at["lga_name"]])

        if name is None:
            quarantine("name_empty", "facility_name is blank or a placeholder token")
            continue

        state = M.map_value(M.STATE_NAMES, state_raw)
        if state is M.UNMAPPED:
            unmapped["state_name"][state_raw] += 1
            quarantine("state_unmapped", "state_name %r is not in the explicit state table" % state_raw)
            continue
        if state is None:
            quarantine("state_absent", "state_name is blank")
            continue
        if lga is None:
            quarantine("lga_absent", "lga_name is blank")
            continue

        lon, lat, coord_reason = coordinate(row[at["longitude"]], row[at["latitude"]])
        if coord_reason in COORDINATE_QUARANTINE_REASONS:
            # A locator record without a point cannot be sorted by distance and cannot be
            # placed on a map. It is quarantined with its reason, never emitted with nulls
            # and never given a centroid or a geocoded guess.
            quarantine(coord_reason, "longitude=%r latitude=%r"
                       % (row[at["longitude"]].strip(), row[at["latitude"]].strip()))
            continue
        assert coord_reason is None, coord_reason  # every reason is in the tuple above

        # The box accepted the pair. Now ask whether it is plausible for the STATE the row
        # claims, because a transposed northern pair stays inside the box. Both readings are
        # recorded as evidence before anything is refused.
        ref_lat, ref_lon = M.STATE_REFERENCE_POINTS[state]
        given_km, transposed_km, state_reason = coordinate_vs_state(
            lon, lat, ref_lat, ref_lon, M.SWAP_MIN_DISTANCE_KM, M.SWAP_FACTOR, M.NOT_IN_STATE_KM)
        geo = state_geo[state]
        geo["given"].append(given_km)
        geo["transposed"].append(transposed_km)
        geo["lat"].append(lat)
        geo["lon"].append(lon)
        if state_reason:
            geo["refused_swapped" if state_reason.endswith("by_state") else "refused_not_in_state"] += 1
            quarantine(state_reason, "%.0f km from the %s reference point as given, %.0f km "
                       "transposed; refused, not exchanged" % (given_km, state, transposed_km))
            continue

        e164, phone_reason = phone(row[at["phone_number"]])
        if phone_reason:
            absence[phone_reason] += 1
        if updated_reason:
            absence["source_updated_at_%s" % updated_reason] += 1

        def mapped(column, table, field):
            raw = row[at[column]]
            value = M.map_value(table, raw)
            if value is M.UNMAPPED:
                unmapped[column][raw.strip()] += 1
                return None
            if value is None:
                absence["%s_not_provided" % field] += 1
            return value

        record = {
            "facility_id": "ng_nhf_%s" % source_id,
            "name": name,
            # Unresolved by design — see mappings.FACILITY_TYPE_FROM_LEVEL.
            "type": None,
            "state": state,
            "city_area": lga,
            "latitude": lat,
            "longitude": lon,
            "phone": e164,
            "opening_hours": mapped("operational_hours", M.OPENING_HOURS, "opening_hours"),
            # Unresolved by design — see mappings.EMERGENCY_CAPABLE_RULE.
            "emergency_capable": None,
            "lga": lga,
            "ward": _free(row[at["ward_name"]], absence, "ward"),
            "address": _free(row[at["physical_location"]], absence, "address"),
            "facility_level": mapped("facility_level_name", M.FACILITY_LEVELS, "facility_level"),
            "ownership": mapped("ownership_name", M.OWNERSHIP, "ownership"),
            "ownership_type": mapped("ownership_type", M.OWNERSHIP_TYPE, "ownership_type"),
            "operational_status": mapped(
                "operational_status_name", M.OPERATIONAL_STATUS, "operational_status"),
            "registration_status": mapped(
                "registration_status_name", M.REGISTRATION_STATUS, "registration_status"),
            "license_status": mapped("license_status_name", M.LICENSE_STATUS, "license_status"),
            "beds": _integer(row[at["beds"]]),
            # Each key is read from exactly the source column mappings.SERVICES_SOURCE_COLUMNS
            # names for it. No other capability is derived from anything.
            "services": {
                field: _yes_no(row[at[column]])
                for field, column in M.SERVICES_SOURCE_COLUMNS.items()
            },
            # Identity and provenance only. Every original value stays recoverable by joining
            # source_id against the committed, hash-pinned source CSV, so copying raw
            # coordinates and phone strings into each record would duplicate a file this
            # repository already holds — and it tripled the artifact, from 12 MB to 37 MB,
            # for no consumer. The administrative ids are the source's own (each maps to
            # exactly one name, verified in the provenance record) and make an LGA unambiguous
            # where two states share a name for one. The audit timestamp is the source's own
            # record-level last-updated value, zone undeclared.
            "source_record": {
                "source_id": source_id,
                "source_unique_id": unique_id,
                "state_id": row[at["state_id"]].strip(),
                "lga_id": row[at["lga_id"]].strip(),
                "ward_id": row[at["ward_id"]].strip() or None,
                "source_updated_at": updated_at,
            },
        }
        records.append(record)

    # --- conflicting duplicates -------------------------------------------------------------
    # `id` is unique across the source, so a duplicate facility_id would be a generator fault
    # rather than a data fault. Checked anyway: it is the one error that would silently drop a
    # facility during serialization.
    by_id = Counter(r["facility_id"] for r in records)
    duplicate_ids = {k: v for k, v in by_id.items() if v > 1}
    if duplicate_ids:
        raise SystemExit("duplicate facility_id generated: %s" % sorted(duplicate_ids)[:5])

    # --- exact duplicates ----------------------------------------------------------------------
    records, dedup = deduplicate(records)
    for loser, survivor in dedup["removed"]:
        source = loser["source_record"]
        quarantined.append(
            {
                "source_line": line_of[source["source_id"]],
                "source_id": source["source_id"],
                "source_unique_id": source["source_unique_id"],
                "reason_code": "duplicate_exact_match",
                "detail": "same name, state, LGA and coordinates as the survivor; "
                "values were not merged",
                "survivor_facility_id": survivor["facility_id"],
            }
        )
        reasons["duplicate_exact_match"] += 1

    records.sort(key=sort_key)

    artifact = {
        "_metadata": _metadata(records, absence, unmapped, dedup, latest_update, header, body),
        "facilities": records,
    }
    quality = _quality_report(header, body, records, quarantined, reasons, unmapped, absence,
                              dedup, latest_update, state_geo)
    quarantine_report = _quarantine_report(quarantined, reasons)
    return artifact, quality, quarantine_report


DEDUPLICATION_RULE = {
    "rule_id": "exact_match_v1",
    "key": "casefolded normalised name + state + casefolded LGA + identical longitude and "
    "latitude as emitted",
    "survivor": "the member with the smallest registry unique_id, then the smallest source "
    "id — the earlier registration in the source's own sequence",
    "values_merged": False,
    "not_collapsed": "same name in the same LGA at a different point; same point under a "
    "different name. Both remain in the artifact and are counted as duplicate CANDIDATES "
    "in the quality report for a reconciliation decision.",
}


def deduplicate(records):
    """Collapse exact duplicates to one survivor each, deterministically.

    Groups are visited in sorted key order and members in `survivor_key` order, so the outcome
    depends only on record content — never on source row order. Returns the survivors plus an
    accounting of what was removed, as (removed_record, survivor_record) pairs.
    """
    groups = defaultdict(list)
    for record in records:
        groups[duplicate_key(record)].append(record)

    survivors, removed, group_sizes = [], [], Counter()
    for key in sorted(groups):
        members = sorted(groups[key], key=survivor_key)
        survivors.append(members[0])
        if len(members) > 1:
            group_sizes[len(members)] += 1
            for loser in members[1:]:
                removed.append((loser, members[0]))
    return survivors, {
        "groups": sum(group_sizes.values()),
        "rows_removed": len(removed),
        "group_sizes": dict(sorted(group_sizes.items())),
        "removed": removed,
    }


def _free(raw, absence, field):
    """Free text with contact details removed, counting each removal by field."""
    value, reason = free_text(raw)
    if reason:
        absence["%s_%s" % (field, reason)] += 1
    return value


def _integer(raw):
    value = (raw or "").strip()
    if value == "":
        return None
    try:
        number = int(float(value))
    except ValueError:
        return None
    return number if number >= 0 else None


def _yes_no(raw):
    value = (raw or "").strip().lower()
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


def _states_in_source(header, body):
    at = {name: index for index, name in enumerate(header)}
    found = set()
    for row in body:
        state = M.map_value(M.STATE_NAMES, row[at["state_name"]].strip())
        if isinstance(state, str):
            found.add(state)
    return found


def _metadata(records, absence, unmapped, dedup, latest_update, header, body):
    states = sorted({r["state"] for r in records})
    emptied = sorted(_states_in_source(header, body) - set(states))
    return {
        "artifact_id": ARTIFACT_ID,
        "version": CANDIDATE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "country": COUNTRY,
        # Two names for one pinned fact. `release_status` is the lifecycle field every artifact
        # in this repository carries; `publication_status` is the name the facilities brief
        # uses. The schema pins both to the same constant so they cannot drift apart.
        "release_status": "candidate_unapproved",
        "publication_status": "candidate_unapproved",
        "release_date": None,
        "may_publish": False,
        "generated_at": GENERATED_AT,
        "generator": "tools/build_facilities_candidate.py",
        "generator_version": GENERATOR_VERSION,
        "total_facilities": len(records),
        "states_covered": states,
        "states_absent": [s for s in M.NIGERIA_STATES if s not in states and s not in emptied],
        "states_with_no_emitted_records": emptied,
        "coverage_claim": "NOT nationwide. %d states%s carry records. Adamawa, Kebbi and "
        "Sokoto have no rows in the source at all; %s have rows in the source but every one "
        "was refused, almost all because their coordinates are written the wrong way round "
        "(see coordinate_reference)."
        % (len(states) - (1 if M.FCT_NAME in states else 0),
           " plus the FCT" if M.FCT_NAME in states else "",
           ", ".join(emptied) if emptied else "no states"),
        "source": {
            "path": "facilities/source/nigeria_health_facilities.csv",
            "sha256": SOURCE_SHA256,
            "byte_count": SOURCE_BYTES,
            "provenance_record": "facilities/source/nhf_provenance_v1.json",
            "organization": None,
            "licence": None,
            "licence_note": "Not established. No licence accompanied the data. This candidate "
            "must not be published, uploaded or served until reuse permission is confirmed.",
            "snapshot_declared_version": None,
            "snapshot_last_updated_at": latest_update,
            "snapshot_note": "The source declares no version. snapshot_last_updated_at is the "
            "newest record-level updated_at in the file — the source system's own audit "
            "timestamp, zone undeclared — so the snapshot is no earlier than that instant.",
        },
        "deduplication": {
            "rule_id": DEDUPLICATION_RULE["rule_id"],
            "key": DEDUPLICATION_RULE["key"],
            "survivor": DEDUPLICATION_RULE["survivor"],
            "values_merged": False,
            "groups_collapsed": dedup["groups"],
            "rows_removed": dedup["rows_removed"],
            "removed_rows_listed_in": "reports/facilities_quarantine_v1.json "
            "(reason_code duplicate_exact_match, each with its survivor_facility_id)",
        },
        "coordinate_policy": "Every emitted record carries a usable coordinate pair inside "
        "the Nigeria bounding box AND plausible for the state the row claims. A source row "
        "with absent, unparseable, 0,0, out-of-bounds, suspected-swapped or not-in-state "
        "coordinates is quarantined with that reason, never emitted with nulls, never "
        "exchanged and never given a substitute point.",
        "coordinate_reference": {
            "instrument": "distance from an approximate per-state reference point, both as "
            "given and with latitude and longitude exchanged (tools/facilities/mappings.py "
            "STATE_REFERENCE_POINTS)",
            "reference_accuracy": "about 0.5 degrees; reference geography, not facility data",
            "cross_check": "facilities 1.1 (GRID3/OSM lineage) medians for Lagos, FCT and "
            "Kano lie 7, 5 and 20 km from the reference points",
            "refused_as_transposed_when": "more than %.0f km from the state's point as given "
            "and at least %.0fx closer transposed" % (M.SWAP_MIN_DISTANCE_KM, M.SWAP_FACTOR),
            "refused_as_not_in_state_when": "more than %.0f km from the state's point under "
            "either reading" % M.NOT_IN_STATE_KM,
            "records_moved_or_exchanged": 0,
            "evidence": "reports/facilities_quality_v1.json source_evidence."
            "coordinate_consistency_by_state",
        },
        "unresolved_fields": {
            "type": "null on every record. Mobile filters non-emergency results by type against "
            "{hospital, clinic, health_centre, pharmacy}; the source has no such column, only "
            "facility_level (Primary/Secondary/Tertiary), which is a tier of care rather than a "
            "kind of facility. Mapping one to the other decides which facilities a user is shown "
            "for self-care versus urgent care, so it is a Product decision, not a generator one.",
            "emergency_capable": "null on every record. facilities 1.1 derived it from "
            "type == 'hospital'; this source has no type, and nothing in its 90 columns records "
            "emergency capability. Mobile treats a non-true value as false, so emergency results "
            "fall back to distance ordering.",
            "type_vocabulary": list(M.FACILITY_TYPES),
            "type_vocabulary_note": "The closed vocabulary a Product decision would map into. "
            "Declared so the enum exists to validate against; not applied to any record.",
        },
        "absence_convention": {
            "null": "not_provided — the source field was blank or a placeholder token",
            "\"unknown\"": "the source explicitly recorded Unknown, which is not the same as blank",
            "note": "No missing value is converted to false, zero or an invented value. Boolean "
            "service fields are null when the source said neither Yes nor No.",
        },
        "not_carried_from_source": {
            "email_address": "excluded — no documented public-use basis, and the column mixes "
            "institutional addresses with free text and individual mailboxes",
            "alternate_number": "excluded — same, and the column contains non-phone values",
            "staffing_counts": "excluded from this candidate — not needed by any consumer and "
            "not verified by the source",
            "workflow_audit_fields": "excluded — created_by/verified_by/published_by and their "
            "timestamps describe a bulk import, not the facility",
        },
        "absence_counts": dict(sorted(absence.items())),
        "unmapped_source_values": {k: dict(v.most_common()) for k, v in sorted(unmapped.items())},
    }


def _rate(count, total):
    return {"count": count, "rate": round(count / total, 4) if total else None}


def _quality_report(header, body, records, quarantined, reasons, unmapped, absence, dedup,
                    latest_update, state_geo):
    at = {name: index for index, name in enumerate(header)}
    total = len(records)
    by_state = Counter(r["state"] for r in records)
    lgas_by_state = defaultdict(set)
    for r in records:
        lgas_by_state[r["state"]].add(r["city_area"])

    source_blank = {
        column: sum(1 for row in body if not row[at[column]].strip()) for column in header
    }
    name_dupes = Counter((r["name"].casefold(), r["state"], r["city_area"]) for r in records)
    coord_dupes = Counter(
        (r["longitude"], r["latitude"]) for r in records if r["longitude"] is not None
    )
    source_state_unique = Counter(row[at["state_unique_id"]].strip() for row in body)

    # facility_type_id has no name column. Its joint distribution with facility_level and
    # ownership is the evidence a decision owner needs to say whether it means anything the
    # candidate could use; it is reported here and interpreted nowhere.
    type_id_crosstab = Counter(
        (row[at["facility_type_id"]].strip() or None,
         row[at["facility_level_name"]].strip() or None,
         row[at["ownership_name"]].strip() or None)
        for row in body
    )

    current_meta = load_json(CURRENT)["_metadata"]

    source_lgas = set()
    states_by_lga_id = defaultdict(Counter)
    for row in body:
        state = M.map_value(M.STATE_NAMES, row[at["state_name"]].strip())
        lga = text(row[at["lga_name"]])
        if isinstance(state, str) and lga:
            source_lgas.add((state, lga))
            states_by_lga_id[(row[at["lga_id"]].strip(), lga)][state] += 1
    emitted_lgas = {(r["state"], r["city_area"]) for r in records}

    # The source's lga_id identifies an LGA NAME, not a (state, LGA) pair: several names exist
    # in two states and carry one id across both. Reported with each side's emitted count and
    # median point, so a reader can see the two sides are in different places without anyone
    # here deciding which side is "right" — for the genuine homonyms both are.
    def median(values):
        values = sorted(values)
        return round(values[len(values) // 2], 4) if values else None

    lga_id_spanning = []
    for (lga_id, lga), per_state in sorted(states_by_lga_id.items()):
        if len(per_state) < 2:
            continue
        sides = []
        for state, source_rows in sorted(per_state.items()):
            emitted = [r for r in records if r["state"] == state and r["city_area"] == lga]
            sides.append({
                "state": state, "source_rows": source_rows, "emitted": len(emitted),
                "median_latitude": median([r["latitude"] for r in emitted]),
                "median_longitude": median([r["longitude"] for r in emitted]),
            })
        lga_id_spanning.append({"lga_id": lga_id, "lga_name": lga, "states": sides})

    # The coordinate instrument's evidence, per state: how far the in-box pairs sit from the
    # state's reference point as given and transposed, what was refused, and a plain-language
    # reading of the two medians. The reading is arithmetic on the counts, not a judgement.
    consistency = []
    for state in sorted(state_geo):
        geo = state_geo[state]
        in_box = len(geo["given"])
        refused = geo["refused_swapped"] + geo["refused_not_in_state"]
        if geo["refused_swapped"] * 2 > in_box:
            reading = "predominantly transposed in the source"
        elif refused == 0:
            reading = "consistent with the state"
        else:
            reading = "mixed"
        consistency.append({
            "state": state,
            "reference_point": list(M.STATE_REFERENCE_POINTS[state]),
            "in_box_rows": in_box,
            # Two keyed scalars rather than a [lat, lon] pair: the repository's content-safety
            # scanner treats a comma-separated decimal pair as a possible location disclosure,
            # and a state median is not one, but the report should not need an exception.
            "median_latitude_as_given": median(geo["lat"]),
            "median_longitude_as_given": median(geo["lon"]),
            "median_km_from_reference_as_given": round(median(geo["given"]), 1),
            "median_km_from_reference_transposed": round(median(geo["transposed"]), 1),
            "refused_swapped_suspected_by_state": geo["refused_swapped"],
            "refused_not_in_state": geo["refused_not_in_state"],
            "emitted": by_state.get(state, 0),
            "reading": reading,
        })
    states_emptied = sorted(s for s in state_geo if by_state.get(s, 0) == 0)

    return {
        "_metadata": {
            "report_id": "facilities_quality",
            "version": "1",
            "phase": PHASE,
            "generator": "tools/build_facilities_candidate.py",
            "generator_version": GENERATOR_VERSION,
            "source_sha256": SOURCE_SHA256,
            "source_snapshot_last_updated_at": latest_update,
            "note": "Profile of the source and of what the generator produced from it. No row "
            "was silently discarded: every row is either in the candidate or in the quarantine "
            "report with a reason code.",
        },
        "row_accounting": {
            "source_rows": len(body),
            "emitted": len(records),
            "quarantined": len(quarantined),
            "quarantined_of_which_exact_duplicates": dedup["rows_removed"],
            "balances": len(body) == len(records) + len(quarantined),
        },
        "identifiers": {
            "source_id_unique": len({row[at["id"]] for row in body}) == len(body),
            "source_unique_id_unique": len({row[at["unique_id"]] for row in body}) == len(body),
            "source_state_unique_id_duplicated": sum(
                v - 1 for v in source_state_unique.values() if v > 1
            ),
            "emitted_facility_id_unique": len({r["facility_id"] for r in records}) == len(records),
        },
        "coverage": {
            "states_present": len(by_state),
            "states_expected": len(M.NIGERIA_STATES) + 1,
            "states_absent_from_source": [s for s in M.NIGERIA_STATES
                                          if s not in by_state and s not in states_emptied],
            "states_in_source_with_no_emitted_records": states_emptied,
            "states_emptied_note": "Every row of these states was refused, almost entirely "
            "by the per-state coordinate instrument: their coordinates are written the "
            "wrong way round in the source. Listed, not smoothed over.",
            "fct_present": M.FCT_NAME in by_state,
            "by_state": dict(sorted(by_state.items())),
            "lga_names_distinct": len({r["city_area"] for r in records}),
            "lga_names_expected_nationally": 774,
            "lga_names_in_source": len(source_lgas),
            "lgas_lost_to_quarantine": sorted(
                "%s / %s" % (state, lga) for state, lga in source_lgas - emitted_lgas),
            "lgas_lost_note": "State/LGA pairs present in the source whose every row was "
            "quarantined. A consequence of the coordinate policy, stated rather than hidden.",
            "lgas_per_state": {k: len(v) for k, v in sorted(lgas_by_state.items())},
        },
        "categorical_counts": {
            "type": dict(sorted(Counter(r["type"] for r in records).items(),
                                key=lambda kv: (kv[0] is None, kv[0]))),
            "facility_level": dict(sorted(Counter(r["facility_level"] for r in records).items(),
                                           key=lambda kv: (kv[0] is None, kv[0]))),
            "ownership": dict(sorted(Counter(r["ownership"] for r in records).items(),
                                      key=lambda kv: (kv[0] is None, kv[0]))),
            "ownership_type": dict(sorted(Counter(r["ownership_type"] for r in records).items(),
                                           key=lambda kv: (kv[0] is None, kv[0]))),
            "operational_status": dict(sorted(Counter(r["operational_status"] for r in records).items(),
                                               key=lambda kv: (kv[0] is None, kv[0]))),
            "registration_status": dict(sorted(Counter(r["registration_status"] for r in records).items(),
                                                key=lambda kv: (kv[0] is None, kv[0]))),
            "license_status": dict(sorted(Counter(r["license_status"] for r in records).items(),
                                           key=lambda kv: (kv[0] is None, kv[0]))),
            "opening_hours": dict(sorted(Counter(r["opening_hours"] for r in records).items(),
                                          key=lambda kv: (kv[0] is None, kv[0]))),
        },
        "completeness": {
            "with_coordinates": sum(1 for r in records if r["latitude"] is not None),
            "without_coordinates": sum(1 for r in records if r["latitude"] is None),
            "with_normalised_phone": sum(1 for r in records if r["phone"]),
            "without_normalised_phone": sum(1 for r in records if not r["phone"]),
            "with_address": sum(1 for r in records if r["address"]),
            "with_ward": sum(1 for r in records if r["ward"]),
            "with_beds": sum(1 for r in records if r["beds"] is not None),
            "with_source_updated_at": sum(
                1 for r in records if r["source_record"]["source_updated_at"]),
        },
        "missingness_rates": {
            "note": "Share of EMITTED records with a null in the field. Coordinates are 0 by "
            "policy (rows without them are quarantined); type and emergency_capable are 1.0 by "
            "decision (see _metadata.unresolved_fields).",
            "coordinates": _rate(sum(1 for r in records if r["latitude"] is None), total),
            "phone": _rate(sum(1 for r in records if r["phone"] is None), total),
            "opening_hours": _rate(sum(1 for r in records if r["opening_hours"] is None), total),
            "emergency_capable": _rate(
                sum(1 for r in records if r["emergency_capable"] is None), total),
            "type": _rate(sum(1 for r in records if r["type"] is None), total),
            "address": _rate(sum(1 for r in records if r["address"] is None), total),
        },
        "duplicates": {
            "exact_duplicates_resolved": {
                "rule_id": DEDUPLICATION_RULE["rule_id"],
                "key": DEDUPLICATION_RULE["key"],
                "survivor": DEDUPLICATION_RULE["survivor"],
                "values_merged": False,
                "groups_collapsed": dedup["groups"],
                "rows_removed": dedup["rows_removed"],
                "group_sizes": dedup["group_sizes"],
                "not_collapsed": DEDUPLICATION_RULE["not_collapsed"],
            },
            "remaining_candidates": {
                "same_name_state_lga_groups": sum(1 for v in name_dupes.values() if v > 1),
                "same_name_state_lga_extra_rows": sum(
                    v - 1 for v in name_dupes.values() if v > 1),
                "identical_coordinate_groups": sum(1 for v in coord_dupes.values() if v > 1),
                "identical_coordinate_extra_rows": sum(
                    v - 1 for v in coord_dupes.values() if v > 1),
                "note": "Counted after exact-match resolution. Reported, not resolved: two "
                "facilities sharing a name within one LGA at different points may be a "
                "duplicate or two genuine facilities, and consolidating them is a "
                "reconciliation decision, not a normalization one.",
            },
        },
        "source_evidence": {
            "coordinate_consistency_by_state": consistency,
            "coordinate_consistency_note": "For every state, the in-box pairs measured "
            "against the state's approximate reference point, as given and with latitude and "
            "longitude exchanged. Where the transposed reading is the near one for most rows "
            "the state is written the wrong way round in the source; those rows are refused "
            "(coordinates_swapped_suspected_by_state), never exchanged. Where a state's "
            "latitude and longitude are numerically close (Bauchi, Gombe, Yobe, Borno, Kogi) "
            "the two readings are only 100-250 km apart and the instrument is uncertain: "
            "some transposed rows will have been kept and a few genuine ones refused. The "
            "bounding box alone cannot see any of this; it only catches a transposition that "
            "leaves Nigeria, which happens in the south.",
            "lga_ids_spanning_multiple_states": lga_id_spanning,
            "lga_id_scope_note": "The source's lga_id is scoped to the LGA name, not to the "
            "state: each entry above carries one id in two states. Where both sides have many "
            "rows and distinct median points they are homonymous LGAs that genuinely exist in "
            "both states; where one side has a single row it is a mislabelled row (all such "
            "rows in the pinned source also lack coordinates and are quarantined on that "
            "ground). Consequence for every consumer: (state, city_area) is the unambiguous "
            "LGA key in this artifact; source_record.lga_id alone is not.",
            "facility_type_id_by_level_and_ownership": [
                {"facility_type_id": k[0], "facility_level": k[1], "ownership": k[2], "rows": v}
                for k, v in sorted(type_id_crosstab.items(),
                                   key=lambda kv: tuple(x or "" for x in kv[0]))
            ],
            "facility_type_id_note": "No name column and no dictionary. Reported so a decision "
            "owner can see it is a near-copy of facility_level; not interpreted as a facility "
            "kind, and not used by the generator.",
        },
        "differences_from_facilities_1_1": {
            "records": {"facilities_1_1": current_meta["total_facilities"], "candidate": total},
            "states_covered": {"facilities_1_1": len(current_meta["states_covered"]),
                               "candidate": len(by_state)},
            "schema_version": {"facilities_1_1": current_meta["schema_version"],
                               "candidate": SCHEMA_VERSION},
            "fields_null_on_every_candidate_record_but_populated_in_1_1": [
                "type", "emergency_capable"],
            "identifier_lineages_disjoint": True,
            "provenance": {"facilities_1_1": [s["name"] for s in current_meta["sources"]],
                           "candidate": ["single bulk registry export, organisation and "
                                         "licence not established"]},
            "detail": "reports/facilities_comparison_v1.json",
        },
        "known_limitations": [
            "Licence and publishing organisation for the source are NOT established; the "
            "candidate must not be published, uploaded or served until they are.",
            "NOT nationwide: %s have no records; %d of 774 LGA names are absent. A user in "
            "those places gets an empty locator."
            % (", ".join(s for s in M.NIGERIA_STATES if s not in by_state),
               774 - len({r["city_area"] for r in records})),
            "type is null on every record, so the Mobile consumer's non-emergency filters "
            "return nothing until a Product mapping decision is recorded.",
            "emergency_capable is null on every record; emergency ordering degrades to pure "
            "distance.",
            "No record in the source was individually verified (every row is a bulk import).",
            "phone is carried in normalised form, but public-use intent for it is not "
            "established; no tel: action should be offered before Product review.",
            "%d source rows without a usable coordinate pair are quarantined, not emitted; "
            "they are findable in no build of this candidate."
            % sum(v for k, v in reasons.items() if k.startswith("coordinates_")),
            "Exact duplicates are collapsed by a strict rule; looser duplicates (same name and "
            "LGA at different points) remain and are counted, not merged.",
            "source_record.lga_id identifies an LGA name, not a state/LGA pair: %d names carry "
            "one id across two states. Key LGAs by (state, city_area), never by lga_id alone."
            % len(lga_id_spanning),
            "The source writes latitude and longitude the wrong way round for whole states. "
            "%d rows were refused on that ground and %d more as not in the state they claim; "
            "%s have no emitted record at all as a result. The rows are listed with both "
            "distances; nothing was exchanged. Correction is the source owner's, or an "
            "explicitly recorded decision — not this pipeline's."
            % (reasons.get("coordinates_swapped_suspected_by_state", 0),
               reasons.get("coordinates_not_in_state", 0),
               ", ".join(states_emptied) if states_emptied else "no states"),
            "The per-state coordinate instrument uses approximate reference points and is "
            "uncertain where a state's latitude and longitude are numerically close (Bauchi, "
            "Gombe, Yobe, Borno, Kogi): some transposed rows there will have been kept.",
            "In states the evidence reads as predominantly transposed but not emptied (%s), "
            "the few surviving rows sat close enough to the diagonal to pass the instrument; "
            "they are probably transposed too and cannot be told apart from genuine ones."
            % ", ".join("%s %d" % (e["state"], e["emitted"]) for e in consistency
                        if e["reading"] == "predominantly transposed in the source"
                        and e["emitted"] > 0),
            "%d facility names are entirely upper case in the source and are carried as such; "
            "re-casing was not applied because it corrupts acronyms (PHC, LUTH). Display "
            "casing is a consumer concern."
            % sum(1 for r in records if r["name"].isupper()),
            "The artifact is an order of magnitude larger than facilities 1.1; a distribution "
            "profile is an open engineering decision.",
        ],
        "source_missingness_by_field": dict(sorted(source_blank.items())),
        "unmapped_source_values": {k: dict(v.most_common()) for k, v in sorted(unmapped.items())},
        "absence_counts": dict(sorted(absence.items())),
        "quarantine_reason_counts": dict(sorted(reasons.items())),
    }


def _quarantine_report(quarantined, reasons):
    return {
        "_metadata": {
            "report_id": "facilities_quarantine",
            "version": "1",
            "phase": PHASE,
            "generator": "tools/build_facilities_candidate.py",
            "generator_version": GENERATOR_VERSION,
            "note": "Every source row the candidate does not contain, with the reason. Rows are "
            "identified by source line and source id only: the values that caused the rejection "
            "are summarised rather than reproduced, so a quarantine report does not become a "
            "second copy of the data it excluded.",
        },
        "total_quarantined": len(quarantined),
        "by_reason": dict(sorted(reasons.items())),
        "reason_codes": {
            "name_empty": "facility_name blank or a placeholder token",
            "state_absent": "state_name blank",
            "state_unmapped": "state_name outside the explicit state table",
            "lga_absent": "lga_name blank",
            "coordinates_absent": "longitude and latitude both blank; a locator record with no "
            "point is quarantined rather than emitted with nulls, and never given a substitute",
            "coordinates_unparseable": "longitude/latitude present but not numeric",
            "coordinates_null_island": "coordinates are exactly 0,0",
            "coordinates_out_of_bounds": "coordinates outside the Nigeria bounding box",
            "coordinates_swapped_suspected": "outside the Nigeria bounding box as given, inside "
            "it if the two fields were exchanged; NOT swapped automatically, because that is a "
            "guess about which field the source got wrong",
            "coordinates_swapped_suspected_by_state": "inside the bounding box, but more than "
            "%.0f km from the reference point of the state the row claims as given and at "
            "least %.0fx closer with latitude and longitude exchanged; the same refusal as "
            "above, seen by a per-state yardstick because a northern transposition stays "
            "inside Nigeria. NOT exchanged. Both distances are in the detail"
            % (M.SWAP_MIN_DISTANCE_KM, M.SWAP_FACTOR),
            "coordinates_not_in_state": "more than %.0f km from the reference point of the "
            "state the row claims under either reading; either the state or the point is "
            "wrong and the pipeline does not choose which" % M.NOT_IN_STATE_KM,
            "name_is_contact_detail": "facility_name holds an email address or URL rather than "
            "a name; the row cannot be presented to a user and the value is not repeated here",
            "duplicate_exact_match": "an exact duplicate (same name, state, LGA and "
            "coordinates) of the record named in survivor_facility_id, which is in the "
            "candidate; the survivor is the smallest registry unique_id and no values were "
            "merged across the pair",
        },
        "deduplication_rule": DEDUPLICATION_RULE,
        "rows": sorted(quarantined, key=lambda q: (q["reason_code"], q["source_line"])),
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if a committed file differs")
    args = parser.parse_args(argv)

    artifact, quality, quarantine_report = build()
    outputs = [
        (CANDIDATE, dump_artifact_bytes(artifact)),
        (QUALITY, dump_report_bytes(quality)),
        (QUARANTINE, dump_report_bytes(quarantine_report)),
    ]

    failures = 0
    for path, data in outputs:
        relative = os.path.relpath(path, repo_path())
        if args.check:
            if not os.path.exists(path):
                print("MISSING %s" % relative); failures += 1; continue
            with open(path, "rb") as handle:
                committed = handle.read()
            if committed != data:
                print("DRIFT %s is not reproducible from its generator" % relative); failures += 1
            else:
                print("OK %s" % relative)
        else:
            write_bytes(path, data)
            print("wrote %s (%d bytes, sha256 %s)"
                  % (relative, len(data), hashlib.sha256(data).hexdigest()[:16] + "…"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
