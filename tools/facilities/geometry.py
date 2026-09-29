"""State-membership geometry from the repository's GRID3 facility points.

This repository holds no state polygons. What it does hold — committed, hash-pinned, licensed
CC BY 4.0 and already the basis of facilities 1.1 — is the GRID3 NGA Health Facilities v2.0
export: 51,022 geolocated facilities labelled with their state, across all 36 states and the
FCT (facilities/source_research.md, Source 1; citation CIESIN, Columbia University (2024),
https://doi.org/10.7916/kv1n-0743). Fifty thousand labelled points are an empirical boundary:
a location whose nearest facilities are all in state X is inside X, and a location whose
nearest same-state facility is 50 km away is not in that state.

That is the whole instrument. It never places, moves or corrects a point on its own; it
answers "is this pair plausibly inside the state the row claims?" with one of four words, and
`orientation` turns two of those answers (the pair as given, the pair with latitude and
longitude exchanged) into one of the four outcomes the remediation study records.

Everything here is deterministic: ties in neighbour distance break on (state, OBJECTID),
cells are visited in a fixed order, and the calibration subsample is every Nth point rather
than a random draw. Standard library only.
"""

import csv
import hashlib
from collections import defaultdict

from facilities.normalize import (NIGERIA_MAX_LAT, NIGERIA_MAX_LON, NIGERIA_MIN_LAT,
                                  NIGERIA_MIN_LON, haversine_km)
from vocab.artifact_io import repo_path

GRID3_PATH = repo_path("facilities", "source",
                       "GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv")
GRID3_SHA256 = "154f3c9b2d4edb0744a6ce2b07ad921a467aea7699fa22aa4c258c788f52a180"
GRID3_CITATION = ("GRID3 NGA Health Facilities v2.0 — CIESIN, Columbia University (2024), "
                  "https://doi.org/10.7916/kv1n-0743, CC BY 4.0")

#: GRID3 spells one state differently from this repository's state list.
GRID3_STATE_NAMES = {"Fct": "FCT"}

#: The membership test. A point is INSIDE its declared state when its K nearest GRID3
#: facilities are all in that state and the nearest is within NEIGHBOUR_RADIUS_KM; it is
#: OUTSIDE when those K are all in other states, or when the nearest facility of the declared
#: state is more than SAME_STATE_MAX_KM away (a real facility sits among its state's other
#: facilities; 50 km of nothing means the point is somewhere else, including outside Nigeria's
#: populated area). A point whose nearest facility is in the declared state and at least
#: MAJORITY_MIN of K are, is INSIDE_MAJORITY — the reading of a genuine facility near a state
#: line. Anything else is UNCERTAIN.
K_NEIGHBOURS = 5
NEIGHBOUR_RADIUS_KM = 25.0
SAME_STATE_MAX_KM = 50.0
MAJORITY_MIN = 3

#: Spatial index cell size. 0.1 degrees is 11.1 km of latitude and no less than 10.8 km of
#: longitude anywhere in Nigeria, so after visiting rings 0..r every point within
#: r * RING_KM of the query has been seen. RING_KM is deliberately below 10.8.
CELL_DEGREES = 0.1
RING_KM = 10.0

INSIDE_STRICT, INSIDE_MAJORITY, OUTSIDE, UNCERTAIN = (
    "inside_strict", "inside_majority", "outside", "uncertain")
OUT_OF_BOX = "outside_nigeria_box"

ACCEPTED_UNCHANGED = "accepted_unchanged"
ACCEPTED_AFTER_SWAP = "accepted_after_verified_swap"
QUARANTINED_AMBIGUOUS = "quarantined_ambiguous"
QUARANTINED_INVALID = "quarantined_invalid"

RULE_ID = "coordinate_orientation_v1"


def in_box(lat, lon):
    return NIGERIA_MIN_LAT <= lat <= NIGERIA_MAX_LAT and NIGERIA_MIN_LON <= lon <= NIGERIA_MAX_LON


def _cell(lat, lon):
    return int(lat // CELL_DEGREES), int(lon // CELL_DEGREES)


def _ring(ci, cj, ring):
    if ring == 0:
        return [(ci, cj)]
    cells = []
    for di in range(-ring, ring + 1):
        for dj in range(-ring, ring + 1):
            if max(abs(di), abs(dj)) == ring:
                cells.append((ci + di, cj + dj))
    return cells


class StateGeometry:
    """GRID3 facility points, indexed for deterministic nearest-neighbour queries."""

    def __init__(self, points, unparseable=0):
        #: (lat, lon, state, objectid), sorted so every derived structure is order-stable.
        self.points = sorted(points, key=lambda p: p[3])
        self.unparseable_rows = unparseable
        self._cells = defaultdict(list)
        self._state_cells = defaultdict(list)
        self.by_uid, self.by_code = {}, {}
        for lat, lon, state, objectid, uid, code in self.points:
            cell = _cell(lat, lon)
            self._cells[cell].append((lat, lon, state, objectid))
            self._state_cells[(state, cell[0], cell[1])].append((lat, lon, objectid))
            if uid:
                self.by_uid[uid] = (lat, lon, state)
            if code:
                self.by_code[code] = (lat, lon, state)
        self.states = sorted({p[2] for p in self.points})

    @classmethod
    def load(cls, path=GRID3_PATH):
        with open(path, "rb") as handle:
            raw = handle.read()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != GRID3_SHA256:
            raise ValueError("GRID3 export hashes to %s, pinned %s; every calibration figure "
                             "below was established against the pinned bytes" % (digest, GRID3_SHA256))
        points, unparseable = [], 0
        for row in csv.DictReader(raw.decode("utf-8-sig").splitlines()):
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
            except (TypeError, ValueError):
                unparseable += 1
                continue
            state = GRID3_STATE_NAMES.get(row["state"], row["state"])
            points.append((lat, lon, state, int(row["OBJECTID"]),
                           row.get("nhfr_uid") or None, row.get("nhfr_facility_code") or None))
        return cls(points, unparseable)

    # --- queries -------------------------------------------------------------------------------
    def nearest(self, lat, lon, k=K_NEIGHBOURS, max_ring=4, exclude_objectid=None):
        """The k nearest points as (km, state, objectid), deterministic under ties."""
        ci, cj = _cell(lat, lon)
        found = []
        for ring in range(max_ring + 1):
            for cell in _ring(ci, cj, ring):
                for plat, plon, state, objectid in self._cells.get(cell, ()):
                    if objectid == exclude_objectid:
                        continue
                    found.append((haversine_km(lat, lon, plat, plon), state, objectid))
            if len(found) >= k:
                found.sort()
                if found[k - 1][0] <= ring * RING_KM:
                    return found[:k]
        found.sort()
        return found[:k]

    def nearest_same_state_km(self, lat, lon, state, max_ring=6, exclude_objectid=None):
        ci, cj = _cell(lat, lon)
        best = None
        for ring in range(max_ring + 1):
            for cell in _ring(ci, cj, ring):
                for plat, plon, objectid in self._state_cells.get((state, cell[0], cell[1]), ()):
                    if objectid == exclude_objectid:
                        continue
                    d = haversine_km(lat, lon, plat, plon)
                    if best is None or d < best:
                        best = d
            if best is not None and best <= ring * RING_KM:
                return best
        return best if best is not None else float("inf")

    def membership(self, lat, lon, state, exclude_objectid=None):
        """One of inside_strict / inside_majority / outside / uncertain, or outside_nigeria_box."""
        if not in_box(lat, lon):
            return OUT_OF_BOX
        nn = self.nearest(lat, lon, exclude_objectid=exclude_objectid)
        same = [s == state for _, s, _ in nn]
        close = len(nn) == K_NEIGHBOURS and nn[0][0] <= NEIGHBOUR_RADIUS_KM
        if close and all(same):
            return INSIDE_STRICT
        if close and not any(same):
            return OUTSIDE
        if self.nearest_same_state_km(lat, lon, state, exclude_objectid=exclude_objectid) > SAME_STATE_MAX_KM:
            return OUTSIDE
        if close and same[0] and sum(same) >= MAJORITY_MIN:
            return INSIDE_MAJORITY
        return UNCERTAIN

    def orientation(self, lat, lon, state):
        """Decide the pair as given against the pair exchanged. Returns
        (outcome, evidence, membership_as_given, membership_exchanged).

        The rule, in full:
          * as given INSIDE_STRICT                                   -> accepted unchanged
          * as given INSIDE_MAJORITY and exchanged OUTSIDE/out of box -> accepted unchanged
            (a facility near a state line; only one orientation is plausible)
          * as given OUTSIDE/out of box and exchanged INSIDE_STRICT   -> accepted after swap
          * as given OUTSIDE/out of box and exchanged OUTSIDE/out of box -> invalid
          * anything else — both plausible, either uncertain          -> ambiguous
        Correction demands the strict reading; acceptance as given does not, because a
        correction alters source data and acceptance does not.
        """
        given = self.membership(lat, lon, state)
        exchanged = self.membership(lon, lat, state)
        given_out = given in (OUTSIDE, OUT_OF_BOX)
        exchanged_out = exchanged in (OUTSIDE, OUT_OF_BOX)
        if given == INSIDE_STRICT:
            return ACCEPTED_UNCHANGED, "as_given_inside_strict", given, exchanged
        if given == INSIDE_MAJORITY and exchanged_out:
            return ACCEPTED_UNCHANGED, "as_given_inside_majority_exchanged_outside", given, exchanged
        if given_out and exchanged == INSIDE_STRICT:
            return ACCEPTED_AFTER_SWAP, "as_given_outside_exchanged_inside_strict", given, exchanged
        if given_out and exchanged_out:
            return QUARANTINED_INVALID, "both_orientations_outside", given, exchanged
        return QUARANTINED_AMBIGUOUS, "ambiguous:%s/%s" % (given, exchanged), given, exchanged

    def declared_state_of(self, uid, code):
        """The state GRID3 records for the same NHFR facility, or None when not joinable."""
        match = self.by_uid.get(uid) or self.by_code.get(code)
        return match[2] if match else None

    def grid3_point_of(self, uid, code):
        match = self.by_uid.get(uid) or self.by_code.get(code)
        return (match[0], match[1]) if match else None

    def calibration(self, every=17):
        """Leave-one-out membership of GRID3's own points, on a fixed subsample."""
        counts = defaultdict(int)
        for lat, lon, state, objectid, _uid, _code in self.points[::every]:
            counts[self.membership(lat, lon, state, exclude_objectid=objectid)] += 1
        return {"subsample": "every %dth point by OBJECTID" % every,
                "points": sum(counts.values()), "membership": dict(sorted(counts.items()))}

    def describe(self):
        return {
            "rule_id": RULE_ID,
            "instrument": "k-nearest-neighbour state membership over the repository's GRID3 "
            "facility points; no polygons, no centroids, no median distances",
            "reference_points": {
                "path": "facilities/source/GRID3_NGA_health_facilities_v2_0_3759985312699330018.csv",
                "sha256": GRID3_SHA256,
                "points_indexed": len(self.points),
                "rows_without_coordinates_skipped": self.unparseable_rows,
                "states": len(self.states),
                "citation": GRID3_CITATION,
                "licence_basis": "CC BY 4.0, recorded in facilities.ng.v1.1.json _metadata.sources "
                "and facilities/source_research.md; used here as reference geometry with attribution",
            },
            "thresholds": {
                "k_neighbours": K_NEIGHBOURS,
                "neighbour_radius_km": NEIGHBOUR_RADIUS_KM,
                "same_state_max_km": SAME_STATE_MAX_KM,
                "majority_min_of_k": MAJORITY_MIN,
            },
            "membership": {
                INSIDE_STRICT: "all k nearest GRID3 facilities are in the declared state and the nearest is within the radius",
                INSIDE_MAJORITY: "the nearest is in the declared state and at least majority_min of k are; a facility near a state line",
                OUTSIDE: "all k nearest are in other states, or the nearest facility of the declared state is beyond same_state_max_km",
                UNCERTAIN: "none of the above",
                OUT_OF_BOX: "outside the Nigeria bounding box",
            },
            "outcomes": {
                ACCEPTED_UNCHANGED: "as given inside_strict; or inside_majority with the exchanged pair outside",
                ACCEPTED_AFTER_SWAP: "as given outside (or out of box) AND exchanged inside_strict; latitude and longitude are exchanged and the source values are kept on the record",
                QUARANTINED_AMBIGUOUS: "both orientations plausible, either uncertain, or GRID3 records a different state for the same facility",
                QUARANTINED_INVALID: "both orientations outside the declared state",
            },
            "determinism": "neighbour ties break on (distance, state, OBJECTID); cells are visited in a fixed order; calibration uses a fixed subsample",
        }
