"""The GRID3 source: pinned identity, reading, normalization, and the
within-dataset state-consistency instrument.

This module is the ONLY place the pipeline touches source data, and it can
open exactly the files in ALLOWED_INPUTS. The NHFR internal export and every
artifact derived from it are not inputs, not fallbacks and not enrichments;
tools/validate_facilities_grid3_candidate.py re-proves that from the emitted
bytes rather than trusting this comment.

Standard library only, no network.
"""

import csv
import math
import unicodedata

from vocab.artifact_io import repo_path, sha256_file

GRID3_PATH = repo_path("facilities", "source",
                       "GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv")
GRID3_SHA256 = "154f3c9b2d4edb0744a6ce2b07ad921a467aea7699fa22aa4c258c788f52a180"
GRID3_ROWS = 51022

LICENCE_EVIDENCE_PATH = repo_path("facilities", "source", "grid3_licence_evidence_v1.json")
LEGALCODE_PATH = repo_path("facilities", "source", "CC-BY-4.0.legalcode.txt")
LEGALCODE_SHA256 = "9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411"

CURRENT_ARTIFACT_PATH = repo_path("facilities.ng.v1.1.json")
CURRENT_ARTIFACT_SHA256 = "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398"

#: Every file the pipeline may read, with the role each plays. The comparison
#: baseline contributes numbers to the COMPARISON REPORT only; no value from it
#: reaches the candidate.
ALLOWED_INPUTS = {
    GRID3_PATH: "sole data source",
    CURRENT_ARTIFACT_PATH: "comparison baseline (report only; contributes no value to the candidate)",
}

#: The NHFR internal export and the artifacts derived from it (PRs #40/#41).
#: None of these may be read, joined against, or reproduced in this lineage.
FORBIDDEN_SOURCES = [
    "nigeria_health_facilities.csv",
    "facilities/source/nigeria_health_facilities.csv",
    "candidate/facilities.ng.v2.0.json",
    "candidate/facilities.manifest.candidate.json",
    "reports/facilities_quality_v1.json",
    "reports/facilities_quarantine_v1.json",
    "reports/facilities_coordinate_audit_v1.json",
    "reports/facilities_comparison_v1.json",
    "reports/facilities_mobile_compat_v1.json",
]

#: NHFR-internal workflow and contact fields. None may appear as a key or a
#: value anywhere in the candidate; the validator scans the serialized bytes.
NHFR_MARKER_STRINGS = [
    "Auto-approved via bulk import",
    "Auto-published via bulk import",
    "CREATE FACILITY (BULK IMPORT)",
    "ng_nhf_",
    "state_unique_id",
    "registration_no",
    "alternate_number",
    "email_address",
    "verify_note",
    "validate_note",
    "publish_note",
    "swap_lat_lon",
]

#: Canonical state spellings (36 states + FCT), the projection's normalization
#: target. GRID3 spells the capital territory 'Fct'; everything else already
#: matches.
CANONICAL_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue",
    "Borno", "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT",
    "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi",
    "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo",
    "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
]
STATE_NORMALIZATION = {"Fct": "FCT"}

#: Source-faithful ownership_type tokens. for_profit / not_for_profit carry no
#: private_ prefix: the source pairs 'For Profit' with Public ownership on 4
#: rows and 'Not For Profit' with Public on 10, so a private_ prefix would
#: assert a pairing the source contradicts.
OWNERSHIP_TYPE_MAP = {
    "Local Government": "local_government",
    "State Government": "state_government",
    "Federal Government": "federal_government",
    "For Profit": "for_profit",
    "Not For Profit": "not_for_profit",
    "Military & Paramilitary formations": "military_paramilitary",
    "Unknown": "unknown",
}

#: Nigeria bounding box, as in schema 2.0 and facilities 1.x.
LAT_MIN, LAT_MAX = 4.0, 14.0
LON_MIN, LON_MAX = 2.5, 15.0

EARTH_DIAMETER_KM = 12742.0


class SourceDrift(RuntimeError):
    pass


class ForbiddenInput(RuntimeError):
    pass


def open_input(path):
    """The pipeline's only file-opening door. Anything not whitelisted is refused."""
    if path not in ALLOWED_INPUTS:
        raise ForbiddenInput("not a permitted pipeline input: %s" % path)
    return open(path, newline="", encoding="utf-8-sig")


def clean_text(value):
    """NFC-normalise, drop control characters, collapse whitespace (NBSP included).

    Casing is carried as the source has it; re-casing corrupts acronyms.
    Returns None for an empty result.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFC", value)
    text = "".join(" " if ch == " " else ch
                   for ch in text if unicodedata.category(ch) != "Cc")
    text = " ".join(text.split())
    return text or None


def read_source():
    digest = sha256_file(GRID3_PATH)
    if digest != GRID3_SHA256:
        raise SourceDrift("GRID3 source does not match the pinned digest: %s" % digest)
    with open_input(GRID3_PATH) as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != GRID3_ROWS:
        raise SourceDrift("GRID3 source has %d rows, expected %d" % (len(rows), GRID3_ROWS))
    return rows


def parse_coordinates(row):
    """(latitude, longitude) as floats, or (None, reason)."""
    try:
        lat = float(row["latitude"])
        lon = float(row["longitude"])
    except (TypeError, ValueError):
        return None, "coordinate_unparseable"
    if lat == 0.0 and lon == 0.0:
        return None, "null_island"
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None, "out_of_bounds"
    return (lat, lon), None


def haversine_km(lat1, lon1, lat2, lon2):
    rad = math.pi / 180.0
    a = (math.sin((lat2 - lat1) * rad / 2.0) ** 2
         + math.cos(lat1 * rad) * math.cos(lat2 * rad)
         * math.sin((lon2 - lon1) * rad / 2.0) ** 2)
    return EARTH_DIAMETER_KM * math.asin(math.sqrt(a))


class StateConsistency:
    """state_position_consistency_v1: a conservative within-dataset anomaly check.

    A point is flagged only when BOTH hold: none of its 10 nearest neighbouring
    facilities shares its declared state, AND the nearest same-state facility is
    more than 50 km away. Flagged rows are quarantined as ambiguous — the state
    label and the position disagree and the source does not say which is wrong —
    never relabelled and never moved. GRID3 is its own reference here (it is the
    only licensed geometry in the repository); the rule is deliberately an
    anomaly detector, not a boundary oracle, and its two thresholds are part of
    the rule's identity.
    """

    RULE_ID = "state_position_consistency_v1"
    NEIGHBOURS = 10
    SAME_STATE_KM = 50.0
    CELL_DEG = 0.1

    def __init__(self, points):
        #: points: list of (lat, lon, canonical_state)
        self.points = points
        self.buckets = {}
        for index, (lat, lon, _state) in enumerate(points):
            self.buckets.setdefault(self._cell(lat, lon), []).append(index)

    def _cell(self, lat, lon):
        return (int(lat / self.CELL_DEG), int(lon / self.CELL_DEG))

    def _ring(self, lat, lon, radius):
        base_lat, base_lon = self._cell(lat, lon)
        for d_lat in range(-radius, radius + 1):
            for d_lon in range(-radius, radius + 1):
                for index in self.buckets.get((base_lat + d_lat, base_lon + d_lon), ()):
                    yield index

    def is_consistent(self, index):
        lat, lon, state = self.points[index]
        neighbours = sorted(
            (haversine_km(lat, lon, self.points[j][0], self.points[j][1]), self.points[j][2])
            for j in self._ring(lat, lon, 1) if j != index
        )[: self.NEIGHBOURS]
        if not neighbours or any(s == state for _d, s in neighbours):
            return True
        same_state = [
            haversine_km(lat, lon, self.points[j][0], self.points[j][1])
            for j in self._ring(lat, lon, 5)
            if j != index and self.points[j][2] == state
        ]
        return bool(same_state) and min(same_state) <= self.SAME_STATE_KM
