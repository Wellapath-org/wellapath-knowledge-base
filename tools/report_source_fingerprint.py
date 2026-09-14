#!/usr/bin/env python3
"""Fingerprint the supplied facilities source CSV so a candidate upstream export can be
compared against it reproducibly, without credentials and without altering a byte.

    python3 tools/report_source_fingerprint.py           # write
    python3 tools/report_source_fingerprint.py --check    # fail if the report is stale

Writes `facilities/source/nhf_source_fingerprint_v1.json`.

Everything in the report is computed from the committed CSV bytes (pinned by digest) and,
for the identifier cross-reference, from the committed GRID3 CSV (also pinned). Nothing is
fetched, nothing is guessed, and the CSV is opened read-only. The point of the report is
AUTH-09: when the source owner supplies a pristine export, these figures decide whether it
is the same snapshot as the copy this repository was handed — or, if they diverge, where.

Standard library only, no network.
"""

import csv
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab.artifact_io import dump_report_bytes, repo_path, sha256_file, write_bytes

SOURCE = repo_path("facilities", "source", "nigeria_health_facilities.csv")
GRID3 = repo_path("facilities", "source", "GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv")
OUTPUT = repo_path("facilities", "source", "nhf_source_fingerprint_v1.json")

SOURCE_SHA256 = "e598cecc24de7cea213118dfd88cb581754029f2dc9086618728989b6c3becb3"

#: The registry facility-code shape shared with GRID3's nhfr_facility_code column.
CODE_SHAPE = re.compile(r"^\d{2}/\d{2}/\d/\d/\d/\d{4}$")

SAMPLE_EACH_END = 10


class SourceDrift(RuntimeError):
    pass


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def segment_shapes(values):
    counts = {}
    for value in values:
        shape = "/".join(str(len(seg)) for seg in value.split("/"))
        counts[shape] = counts.get(shape, 0) + 1
    return {shape: counts[shape] for shape in sorted(counts)}


def canonical_row(header, row):
    """A row canonicalized independently of quoting, BOM and surrounding whitespace."""
    return "\x1f".join("%s=%s" % (name, (row.get(name) or "").strip()) for name in header)


def read_rows():
    digest = sha256_file(SOURCE)
    if digest != SOURCE_SHA256:
        raise SourceDrift("source CSV does not match the pinned digest: %s" % digest)
    with open(SOURCE, newline="", encoding="utf-8") as handle:
        title = handle.readline().rstrip("\r\n")
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames)
        rows = list(reader)
    return title, header, rows


def grid3_codes():
    with open(GRID3, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        codes = set()
        uids = set()
        for row in reader:
            code = (row.get("nhfr_facility_code") or "").strip()
            uid = (row.get("nhfr_uid") or "").strip()
            if code:
                codes.add(code)
            if uid:
                uids.add(uid)
    return codes, uids


def build():
    title, header, rows = read_rows()

    null_counts = {name: 0 for name in header}
    state_counts = {}
    unique_ids = []
    numeric_ids = []
    created, updated = [], []
    coord_by_state = {}
    zero_zero = 0
    coord_absent = 0

    for row in rows:
        for name in header:
            if not (row.get(name) or "").strip():
                null_counts[name] += 1
        state = (row.get("state_name") or "").strip()
        state_counts[state] = state_counts.get(state, 0) + 1
        unique_ids.append((row.get("unique_id") or "").strip())
        raw_id = (row.get("id") or "").strip()
        if raw_id.isdigit():
            numeric_ids.append(int(raw_id))
        for field, into in (("created_at", created), ("updated_at", updated)):
            value = (row.get(field) or "").strip().replace(" ", "T")
            if value:
                into.append(value)
        lat = (row.get("latitude") or "").strip()
        lon = (row.get("longitude") or "").strip()
        try:
            flat, flon = float(lat), float(lon)
        except ValueError:
            coord_absent += 1
            continue
        if flat == 0.0 and flon == 0.0:
            zero_zero += 1
            continue
        coord_by_state.setdefault(state, []).append((flat, flon))

    orientation = {}
    for state in sorted(coord_by_state):
        pairs = sorted(coord_by_state[state])
        lats = sorted(p[0] for p in pairs)
        lons = sorted(p[1] for p in pairs)
        mid = len(pairs) // 2
        orientation[state] = {
            "rows_with_coordinates": len(pairs),
            "median_latitude_as_given": round(lats[mid], 2),
            "median_longitude_as_given": round(lons[mid], 2),
        }

    by_uid = sorted(range(len(rows)), key=lambda i: unique_ids[i])
    sample_indexes = by_uid[:SAMPLE_EACH_END] + by_uid[-SAMPLE_EACH_END:]
    samples = [
        {
            "unique_id": unique_ids[i],
            "canonical_row_sha256": sha256_text(canonical_row(header, rows[i])),
        }
        for i in sample_indexes
    ]

    codes, uids = grid3_codes()
    uid_set = set(u for u in unique_ids if u)
    id_set = set(str(i) for i in numeric_ids)

    constant_columns = {
        name: (rows[0].get(name) or "").strip()
        for name in ("verify_note", "validate_note", "publish_note",
                     "certificate_of_standard", "dhis2_synced")
        if len(set((r.get(name) or "").strip() for r in rows)) == 1
    }

    return {
        "_metadata": {
            "report_id": "nhf_source_fingerprint",
            "version": "1",
            "phase": "Nationwide Facilities / Step 4 (provenance investigation)",
            "generator": "tools/report_source_fingerprint.py",
            "note": "Reproducible identity of the supplied source CSV, for comparison against "
            "a candidate upstream export (authorization checklist item AUTH-09). Computed "
            "from committed bytes only; the CSV is never modified. Two files with the same "
            "sha256 are identical and need nothing below; two files that differ are located "
            "by header, row count, null pattern, state counts, identifier sets, timestamps "
            "and the per-state coordinate-orientation signature, in that order.",
        },
        "file": {
            "path": "facilities/source/nigeria_health_facilities.csv",
            "sha256": SOURCE_SHA256,
            "byte_count": os.path.getsize(SOURCE),
            "title_line": title,
            "row_count": len(rows),
            "column_count": len(header),
        },
        "columns": {
            "order": header,
            "header_sha256": sha256_text(",".join(header)),
        },
        "identifiers": {
            "unique_id": {
                "distinct": len(uid_set),
                "code_shape": CODE_SHAPE.pattern,
                "matching_code_shape": sum(1 for u in uid_set if CODE_SHAPE.match(u)),
                "segment_length_shape_counts": segment_shapes(uid_set),
                "sorted_set_sha256": sha256_text("\n".join(sorted(uid_set))),
            },
            "id": {
                "distinct": len(id_set),
                "numeric_min": min(numeric_ids),
                "numeric_max": max(numeric_ids),
                "sorted_set_sha256": sha256_text("\n".join(sorted(id_set))),
            },
            "state_unique_id_distinct": len(
                set((r.get("state_unique_id") or "").strip() for r in rows) - {""}
            ),
        },
        "grid3_cross_reference": {
            "grid3_file": "facilities/source/GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv",
            "grid3_sha256": sha256_file(GRID3),
            "grid3_nonblank_nhfr_facility_code": len(codes),
            "grid3_nonblank_nhfr_uid": len(uids),
            "unique_id_matching_grid3_nhfr_facility_code": len(uid_set & codes),
            "id_matching_grid3_nhfr_uid": len(id_set & uids),
            "note": "GRID3 v2.0 labels these columns NHFR_2024. The facility-code shape is "
            "identical between the two files; the exact-value overlap is bounded below by "
            "the two snapshots being roughly two years apart.",
        },
        "timestamps": {
            "created_at_min": min(created),
            "created_at_max": max(created),
            "updated_at_min": min(updated),
            "updated_at_max": max(updated),
            "zone_declared": False,
        },
        "null_pattern": {
            "empty_value_count_by_column": {name: null_counts[name] for name in header},
        },
        "state_counts": {state: state_counts[state] for state in sorted(state_counts)},
        "coordinate_signature": {
            "rows_without_a_parseable_pair": coord_absent,
            "rows_at_null_island": zero_zero,
            "per_state_medians_as_given": orientation,
            "note": "Medians are of the columns AS LABELLED in the source. In a correctly "
            "oriented Nigerian dataset the median latitude lies in roughly 4-14 and the "
            "median longitude in roughly 3-15 with latitude < longitude in most southern "
            "states. States whose two medians appear exchanged relative to their known "
            "position reproduce the transposition finding of Steps 2-3 "
            "(reports/facilities_coordinate_audit_v1.json).",
        },
        "constant_workflow_values": constant_columns,
        "canonical_samples": {
            "method": "rows sorted by unique_id; the first and last %d rows are each "
            "canonicalized as name=value pairs joined by 0x1F, values stripped of "
            "surrounding whitespace, and hashed sha256." % SAMPLE_EACH_END,
            "samples": samples,
        },
    }


def main(argv):
    check = "--check" in argv
    data = dump_report_bytes(build())
    relative = os.path.relpath(OUTPUT, repo_path())

    if check:
        if not os.path.exists(OUTPUT):
            print("MISSING %s" % relative)
            return 1
        with open(OUTPUT, "rb") as handle:
            committed = handle.read()
        if committed != data:
            print("DRIFT %s: the source or the report changed" % relative)
            return 1
        print("OK %s" % relative)
        return 0

    write_bytes(OUTPUT, data)
    print("wrote %s (%d bytes)" % (relative, len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
