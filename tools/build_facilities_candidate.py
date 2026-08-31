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

from facilities import mappings as M
from facilities.normalize import coordinate, free_text, phone, sort_key, text
from vocab.artifact_io import dump_artifact_bytes, dump_report_bytes, repo_path, write_bytes

SOURCE = repo_path("facilities", "source", "nigeria_health_facilities.csv")
SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"
SOURCE_BYTES = 20913558

CANDIDATE = repo_path("candidate", "facilities.ng.v2.0.json")
QUALITY = repo_path("reports", "facilities_quality_v1.json")
QUARANTINE = repo_path("reports", "facilities_quarantine_v1.json")

ARTIFACT_ID = "facilities"
CANDIDATE_VERSION = "2.0"
SCHEMA_VERSION = "2.0"
COUNTRY = "ng"

#: Fixed, so regeneration is byte-stable. Not a clock read.
GENERATED_AT = "2026-08-31T00:00:00Z"
GENERATOR_VERSION = "1.0.0"

#: A row without one of these cannot be represented honestly, so it is quarantined rather
#: than emitted with a filler value.
REQUIRED = ("facility_name", "state_name", "lga_name")


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

    for line_number, row in enumerate(body, start=3):  # +1 title, +1 header, +1 to 1-index
        source_id = row[at["id"]].strip()
        unique_id = row[at["unique_id"]].strip()

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
        if coord_reason in ("coordinates_swapped_suspected", "coordinates_out_of_bounds",
                            "coordinates_null_island", "coordinates_unparseable"):
            quarantine(coord_reason, "longitude=%r latitude=%r"
                       % (row[at["longitude"]].strip(), row[at["latitude"]].strip()))
            continue
        if coord_reason:
            absence[coord_reason] += 1

        e164, phone_reason = phone(row[at["phone_number"]])
        if phone_reason:
            absence[phone_reason] += 1

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
            "services": {
                "onsite_laboratory": _yes_no(row[at["onsite_laboratory"]]),
                "onsite_imaging": _yes_no(row[at["onsite_imaging"]]),
                "onsite_pharmacy": _yes_no(row[at["onsite_pharmarcy"]]),
                "mortuary": _yes_no(row[at["mortuary_services"]]),
                "ambulance": _yes_no(row[at["ambulance_services"]]),
            },
            # Identity only. Every original value stays recoverable by joining source_id
            # against the committed, hash-pinned source CSV, so copying raw coordinates and
            # phone strings into each record would duplicate a file this repository already
            # holds — and it tripled the artifact, from 12 MB to 37 MB, for no consumer.
            "source_record": {"source_id": source_id, "source_unique_id": unique_id},
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

    records.sort(key=sort_key)

    artifact = {
        "_metadata": _metadata(records, absence, unmapped),
        "facilities": records,
    }
    quality = _quality_report(header, body, records, quarantined, reasons, unmapped, absence)
    quarantine_report = _quarantine_report(quarantined, reasons)
    return artifact, quality, quarantine_report


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


def _metadata(records, absence, unmapped):
    states = sorted({r["state"] for r in records})
    return {
        "artifact_id": ARTIFACT_ID,
        "version": CANDIDATE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "country": COUNTRY,
        "release_status": "candidate_unapproved",
        "release_date": None,
        "may_publish": False,
        "generated_at": GENERATED_AT,
        "generator": "tools/build_facilities_candidate.py",
        "generator_version": GENERATOR_VERSION,
        "total_facilities": len(records),
        "states_covered": states,
        "states_absent": [s for s in M.NIGERIA_STATES if s not in states],
        "coverage_claim": "NOT nationwide. 33 of 36 states plus the FCT are represented. "
        "Adamawa, Kebbi and Sokoto have no records in the source at all.",
        "source": {
            "path": "facilities/source/nigeria_health_facilities.csv",
            "sha256": SOURCE_SHA256,
            "byte_count": SOURCE_BYTES,
            "provenance_record": "facilities/source/nhf_provenance_v1.json",
            "organization": None,
            "licence": None,
            "licence_note": "Not established. No licence accompanied the data. This candidate "
            "must not be published, uploaded or served until reuse permission is confirmed.",
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


def _quality_report(header, body, records, quarantined, reasons, unmapped, absence):
    at = {name: index for index, name in enumerate(header)}
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

    return {
        "_metadata": {
            "report_id": "facilities_quality",
            "version": "1",
            "phase": "Nationwide Facilities / Step 1",
            "generator": "tools/build_facilities_candidate.py",
            "generator_version": GENERATOR_VERSION,
            "source_sha256": SOURCE_SHA256,
            "note": "Profile of the source and of what the generator produced from it. No row "
            "was silently discarded: every row is either in the candidate or in the quarantine "
            "report with a reason code.",
        },
        "row_accounting": {
            "source_rows": len(body),
            "emitted": len(records),
            "quarantined": len(quarantined),
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
            "states_absent": [s for s in M.NIGERIA_STATES if s not in by_state],
            "fct_present": M.FCT_NAME in by_state,
            "by_state": dict(sorted(by_state.items())),
            "lga_names_distinct": len({r["city_area"] for r in records}),
            "lga_names_expected_nationally": 774,
            "lgas_per_state": {k: len(v) for k, v in sorted(lgas_by_state.items())},
        },
        "categorical_counts": {
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
        },
        "duplicates": {
            "same_name_state_lga_groups": sum(1 for v in name_dupes.values() if v > 1),
            "same_name_state_lga_extra_rows": sum(v - 1 for v in name_dupes.values() if v > 1),
            "identical_coordinate_groups": sum(1 for v in coord_dupes.values() if v > 1),
            "identical_coordinate_extra_rows": sum(v - 1 for v in coord_dupes.values() if v > 1),
            "note": "Reported, not resolved. Two facilities sharing a name within one LGA may be "
            "a duplicate or may be two genuine facilities; consolidating them is a reconciliation "
            "decision, not a normalization one.",
        },
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
            "phase": "Nationwide Facilities / Step 1",
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
            "coordinates_unparseable": "longitude/latitude present but not numeric",
            "coordinates_null_island": "coordinates are exactly 0,0",
            "coordinates_out_of_bounds": "coordinates outside the Nigeria bounding box",
            "coordinates_swapped_suspected": "implausible as given, plausible if the two fields "
            "were exchanged; NOT swapped automatically, because that is a guess about which "
            "field the source got wrong",
            "name_is_contact_detail": "facility_name holds an email address or URL rather than "
            "a name; the row cannot be presented to a user and the value is not repeated here",
        },
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
