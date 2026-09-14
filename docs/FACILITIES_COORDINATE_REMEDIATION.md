# Facilities 2.0 — coordinate-orientation remediation study

> **Candidate only.** The candidate this study produces is `candidate_unapproved`,
> `may_publish: false`, unpublished, unactivated, and not handed to Backend or Mobile.
> `facilities.ng.v1.1.json` remains active and byte identical. Nothing in this study is an
> approval; its rule is applied in the candidate and awaits acceptance (FAC-D004).

```bash
python3 tools/run_facilities_checks.py     # regenerate-and-compare, validate (91 checks), test (104)
```

## 1. The question

The Step 2 candidate refused 9,911 rows whose latitude and longitude appeared transposed, and
in doing so emptied FCT, Kano, Katsina, Kwara, Niger, Taraba and Zamfara — two of them served
by v1.1 today. Can those rows be corrected on strong, reproducible evidence rather than
guessed, and does the result preserve coverage?

## 2. The boundary instrument — repository geometry, not centroids

This repository holds no state polygons, and none was downloaded. What it holds — committed,
hash-pinned (`154f3c9b…a180`), licensed **CC BY 4.0** and already the basis of facilities 1.1 —
is the **GRID3 NGA Health Facilities v2.0** export: **51,022 geolocated facilities labelled
with their state, across all 36 states and the FCT** (CIESIN, Columbia University, 2024,
https://doi.org/10.7916/kv1n-0743; `facilities/source_research.md`, Source 1). Fifty thousand
labelled points are an empirical boundary. `tools/facilities/geometry.py` indexes them and
answers one question — *is this pair plausibly inside the state the row claims?* — with one of
four words:

| Membership | Definition (k = 5, radius 25 km, same-state max 50 km, majority ≥ 3) |
|---|---|
| `inside_strict` | all 5 nearest GRID3 facilities are in the declared state and the nearest is within 25 km |
| `inside_majority` | the nearest is in the declared state and at least 3 of 5 are — a facility near a state line |
| `outside` | all 5 nearest are in other states, **or** the nearest facility *of the declared state* is more than 50 km away |
| `uncertain` | anything else |

Calibration, leave-one-out on every 17th GRID3 point (3,002 points): `inside_strict` 2,806
(93.5%), `inside_majority` 124 (4.1%), `uncertain` 67 (2.2%), `outside` 5 (0.17%). The
instrument reads its own points as inside their states; it is not producing "outside" by
accident.

Step 2's centroid table (`mappings.STATE_REFERENCE_POINTS`) decides nothing any more. It
survives only as an independent 300 km sanity invariant in the validator.

## 3. The decision algorithm — `coordinate_orientation_v1`

For every source row with a parseable, non-zero pair, compute the membership of the pair **as
given** `(lat, lon)` and of the pair **exchanged** `(lon, lat)`, each against the state the row
claims. Then, in this order:

1. If GRID3 records the **same NHFR facility** (joined on `nhfr_uid` = source `id`, or
   `nhfr_facility_code` = source `unique_id`) in a **different state** → the declared state is
   uncertain → **quarantined as ambiguous** (`declared_state_disagrees_with_grid3`).
2. As given `inside_strict` → **accepted unchanged**.
3. As given `inside_majority` **and** exchanged `outside` or outside the Nigeria box → **accepted
   unchanged** (a facility near a state line; only one orientation is plausible).
4. As given `outside` or outside the Nigeria box **and** exchanged `inside_strict` → **accepted
   after verified source-column swap**: latitude and longitude are exchanged; the source values
   are kept on the record (`source_record.source_latitude`, `source_longitude`) and
   `source_record.coordinate_transformation = "swap_lat_lon"`.
5. As given `outside`/out of box **and** exchanged `outside`/out of box → **quarantined as
   invalid** (`coordinates_not_in_state`).
6. Anything else — both plausible, either uncertain — → **quarantined as ambiguous**
   (`coordinates_orientation_ambiguous`), with both memberships recorded.

A correction demands the **strict** reading of the exchanged pair; acceptance as given does
not. A correction alters source data, acceptance does not. Nothing is snapped, moved, geocoded
or inferred; every emitted pair is a source pair or its exchange. Determinism: neighbour ties
break on (distance, state, OBJECTID); cells are visited in a fixed order; the calibration
subsample is fixed. The full description is embedded in
`reports/facilities_coordinate_audit_v1.json → algorithm`.

Rows with no pair (524), an unparseable pair (0) or 0,0 (5) are not orientable and are
quarantined as before.

## 4. Outcomes

| Outcome | Rows | Evidence classes |
|---|---|---|
| **Accepted unchanged** | **18,210** | `as_given_inside_strict` 17,842 · `as_given_inside_majority_exchanged_outside` 368 |
| **Accepted after verified swap** | **11,141** | `as_given_outside_exchanged_inside_strict` 11,141 |
| **Quarantined as ambiguous** | **1,442** | `outside/inside_majority` 580 · `uncertain/inside_strict` 245 · `outside/uncertain` 208 · `inside_majority/inside_strict` 156 · `uncertain/outside` 121 · declared state disagrees with GRID3 69 · other 63 |
| **Quarantined as invalid** | **67** | `both_orientations_outside` |
| Not orientable (missing / 0,0) | 529 | — |
| Empty name (before orientation) | 1 | — |
| **Total** | **31,390** | |

After exact-duplicate collapse (323 rows, 279 of them corrected rows) the candidate holds
**29,028 records, of which 10,862 carry `swap_lat_lon`**.

### Independent corroboration — the same facility in GRID3

GRID3 carries the NHFR facility id, so for joinable rows the *same facility's* independently
published point can be compared with each orientation. GRID3 is a different geocoding vintage,
so agreement is loose (20 km); it corroborates the rule's direction and decided nothing:

| Outcome | Joinable rows | GRID3 point within 20 km of the **emitted** pair | …of the **other** pair |
|---|---|---|---|
| Accepted unchanged | 6,003 | 4,121 (68.6%) | 505 (8.4%) |
| Accepted after swap | 5,611 | **3,005 (53.6%)** | **2 (0.04%)** |

For corrected rows, the independent point sits with the exchanged pair 1,500 times more often
than with the pair as given.

## 5. Coverage — before and after, every state

"Candidate (no correction)" is what a pipeline that refused every correction would emit.

| State | Source rows | Accepted unchanged | Accepted after verified swap | Quarantined ambiguous | Quarantined invalid | No coordinates | Duplicates | Candidate (no correction) | **Candidate** | v1.1 |
|---|---|---|---|---|---|---|---|---|---|---|
| Abia | 756 | 743 | 0 | 12 | 1 | 0 | 0 | 743 | **743** | 0 |
| Adamawa | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0 |
| Akwa Ibom | 733 | 727 | 0 | 6 | 0 | 0 | 2 | 725 | **725** | 0 |
| Anambra | 1352 | 1346 | 0 | 5 | 1 | 0 | 7 | 1339 | **1339** | 0 |
| Bauchi | 689 | 173 | 425 | 91 | 0 | 0 | 0 | 173 | **598** | 0 |
| Bayelsa | 76 | 76 | 0 | 0 | 0 | 0 | 0 | 76 | **76** | 0 |
| Benue | 1670 | 59 | 1515 | 68 | 28 | 0 | 2 | 59 | **1572** | 0 |
| Borno | 353 | 10 | 299 | 44 | 0 | 0 | 0 | 10 | **309** | 0 |
| Cross River | 1158 | 1133 | 0 | 24 | 1 | 0 | 0 | 1133 | **1133** | 0 |
| Delta | 861 | 828 | 0 | 33 | 0 | 0 | 3 | 825 | **825** | 0 |
| Ebonyi | 415 | 409 | 0 | 6 | 0 | 0 | 0 | 409 | **409** | 0 |
| Edo | 458 | 450 | 0 | 8 | 0 | 0 | 2 | 448 | **448** | 0 |
| Ekiti | 582 | 572 | 0 | 6 | 4 | 0 | 0 | 572 | **572** | 0 |
| Enugu | 935 | 921 | 0 | 8 | 1 | 5 | 0 | 921 | **921** | 0 |
| **FCT** | 664 | 0 | **632** | 32 | 0 | 0 | 0 | **0** | **632** | **614** |
| Gombe | 743 | 67 | 623 | 52 | 0 | 1 | 1 | 67 | **689** | 0 |
| Imo | 1498 | 1483 | 0 | 8 | 7 | 0 | 1 | 1482 | **1482** | 0 |
| Jigawa | 1053 | 0 | 866 | 187 | 0 | 0 | 216 | 0 | **650** | 0 |
| Kaduna | 1113 | 0 | 1065 | 48 | 0 | 0 | 1 | 0 | **1064** | 0 |
| **Kano** | 1441 | 0 | **1323** | 86 | 0 | 32 | 30 | **0** | **1293** | **2040** |
| **Katsina** | 425 | 0 | 416 | 9 | 0 | 0 | 0 | **0** | **416** | 0 |
| Kebbi | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0 |
| Kogi | 1138 | 265 | 758 | 115 | 0 | 0 | 30 | 255 | **993** | 0 |
| **Kwara** | 939 | 0 | 788 | 50 | 0 | 101 | 1 | **0** | **787** | 0 |
| Lagos | 1521 | 1503 | 0 | 15 | 3 | 0 | 1 | 1502 | **1502** | 2690 |
| Nasarawa | 665 | 307 | 256 | 102 | 0 | 0 | 7 | 302 | **556** | 0 |
| **Niger** | 826 | 0 | 690 | 92 | 3 | 41 | 0 | **0** | **690** | 0 |
| Ogun | 1081 | 895 | 0 | 7 | 0 | 179 | 0 | 895 | **895** | 0 |
| Ondo | 861 | 848 | 0 | 13 | 0 | 0 | 1 | 847 | **847** | 0 |
| Osun | 1676 | 1466 | 0 | 28 | 12 | 170 | 7 | 1459 | **1459** | 0 |
| Oyo | 1593 | 1577 | 0 | 14 | 2 | 0 | 1 | 1576 | **1576** | 0 |
| Plateau | 1591 | 1260 | 166 | 165 | 0 | 0 | 1 | 1259 | **1425** | 0 |
| Rivers | 895 | 882 | 0 | 11 | 2 | 0 | 1 | 881 | **881** | 0 |
| Sokoto | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** | 0 |
| **Taraba** | 948 | 0 | 921 | 25 | 2 | 0 | 5 | **0** | **916** | 0 |
| Yobe | 498 | 210 | 221 | 67 | 0 | 0 | 3 | 208 | **428** | 0 |
| **Zamfara** | 182 | 0 | 177 | 5 | 0 | 0 | 0 | **0** | **177** | 0 |
| **Total** | 31389 | 18210 | 11141 | 1442 | 67 | 529 | 323 | 18166 | **29028** | 5344 |

(One further source row has no name and is quarantined before it reaches a state.)

**No state served by v1.1 is missing.** FCT: 632 candidate records against 614 in v1.1.
Kano: 1,293 against 2,040 — v1.1 drew on GRID3 and OSM, which hold more Kano points than this
registry snapshot; that is a source-coverage difference, not a loss the pipeline caused. Lagos:
1,502 against 2,690, same reason. Adamawa, Kebbi and Sokoto have no rows in the source and
were never in v1.1.

The seven states Step 2 emptied are recovered entirely by verified swaps: none of them has a
single row that is inside its state as given. Jigawa's 216 duplicates are a source artefact
(rows repeated verbatim); Kano's 30 and Kogi's 30 likewise.

## 6. Options

**A. Corrected HFR-derived v2 candidate** — what this branch now holds. Coverage preserved for
every v1.1 state under a strict, audited, reproducible rule with independent corroboration;
1,442 ambiguous rows held rather than guessed. Still blocked by: source authorization (all nine
items missing), `type` null (FAC-D001 — three of four urgency paths return nothing in the
current build), `emergency_capable` null (FAC-D002), and acceptance of the rule itself
(FAC-D004).

**B. Corrected candidate + provenance-labelled v1.1 overlay for uncovered states** — evaluated
in `reports/facilities_comparison_v1.json → option_b_overlay_analysis`. **No v1.1 state is
uncovered, so the overlay buys no coverage.** It would add 4,387 records of a different
lineage to states the candidate already serves — 1,085 / 316 / 1,001 (Lagos / FCT / Kano)
with no candidate record within 250 m, plus 1,178 / 233 / 574 that match a candidate record by
position but not by name, whose identity is not established either way. Record-level
provenance would survive (each record keeps its lineage), but deduplication would not be
defensible: there is no rule in this repository that decides whether "X Hospital" at 180 m
from "X Medical Centre" is one facility or two. **Rejected.**

**C. Keep v1.1 active until an authoritative corrected source is obtained** — this is the
state of the world today and must remain so regardless of A: nothing here satisfies the
authorization checklist, and FAC-D001 is unmade.

### Recommendation

**Option C for the active artifact, Option A as the only candidate path.** Keep v1.1 active.
Carry the corrected candidate as the thing that is reviewed, because the study shows a safe,
coverage-preserving candidate *is* producible from this source: every correction is re-derived
from its source values by the validator, every ambiguity is held, the direction is corroborated
by an independent point for the same facility, and the rule is a single documented function.
What it does not show is that this source may be used at all, or how a null `type` should
route a user — and those, not geometry, are what keep it a candidate.

## 7. Limitations, stated

* The boundary is points, not polygons. A facility more than 25 km from any GRID3 facility, or
  within a few kilometres of a state line, reads as `uncertain`/`inside_majority` and may be
  held (580 rows are `outside` as given and only `inside_majority` exchanged — very probably
  transposed border facilities — and they stay quarantined because the rule demands strict).
* Where a state's latitude and longitude are numerically close (Nasarawa, Plateau, Bauchi,
  Gombe, Yobe, Kogi) a pair can be inside the state either way. Such a row is accepted **as
  given** if that reading is strict — the source's claim stands when it is consistent — and its
  swapped twin being also inside is not evidence against it. If the source is systematically
  transposed in such a state, those points are inside the state but tens of kilometres off;
  the corroboration table shows 505 unchanged rows whose GRID3 twin favours the other reading.
* Whether the transposition arose in the source system, its export, or the spreadsheet the
  supplied copy passed through is not established (AUTH-09).
* The 69 rows GRID3 places in a different state may be GRID3's error as easily as the source's;
  they are held, not decided.
