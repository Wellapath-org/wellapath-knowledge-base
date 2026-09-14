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
"""

__all__ = ["mappings", "normalize"]

FACILITIES_TOOLING_VERSION = "1.1.0"
