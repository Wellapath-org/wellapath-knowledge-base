"""Nationwide facilities candidate tooling (Nationwide Facilities / Step 2).

Standard library only, matching every other generator in this repository. The source is a
20.9 MB CSV, so the generator streams and sorts rather than holding intermediate copies.

The design rule throughout: **nothing is guessed.** A source value this code has not been
told how to interpret does not get a default — it goes to the unmapped report and, where the
field matters, the row is quarantined. That is why the mapping tables below are exhaustive
over the values actually present, and why two fields the Mobile consumer wants are emitted as
null rather than filled in.

Step 2 added two pipeline policies, both explicit and both counted: a row without a usable
coordinate pair is quarantined rather than emitted with nulls, and rows that are exact
duplicates of one another (same name, state, LGA and coordinates) are collapsed to one by a
documented, deterministic survivor rule. Neither policy invents a value.

Step 3 added the coordinate-orientation rule (`geometry.py`): the source writes latitude and
longitude the wrong way round for whole states, and each pair is now tested against the state
the row claims, as given and exchanged, using the repository's GRID3 facility points as the
boundary. A pair is corrected only when it is outside its state as given and strictly inside
it exchanged; the source values stay on the record and every correction is listed.
"""

__all__ = ["geometry", "mappings", "normalize"]

FACILITIES_TOOLING_VERSION = "1.2.0"
