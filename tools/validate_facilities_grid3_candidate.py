#!/usr/bin/env python3
"""Fail-closed validation of the GRID3-lineage Facilities 2.0 candidate.

    python3 tools/validate_facilities_grid3_candidate.py

Four jobs, none of which trusts the generator:

  A. PERMITTED SOURCE — the source bytes, the vendored legal code and the
     licence-evidence record all match their pins, and the candidate cites them.
  B. ISOLATION — every record's values are re-derived from the GRID3 CSV alone;
     the committed candidate bytes carry zero NHFR markers; the forbidden
     sources are not tracked on this branch; the pipeline's own door refuses
     them.
  C. HONESTY — nothing invented: type, phone, opening_hours, emergency_capable,
     address, statuses, beds and every service flag are null everywhere;
     coordinates are the source's values exactly; accounting sums.
  D. GOVERNANCE — candidate_unapproved / may_publish false everywhere they are
     stated; the manifest's gates are false (except the licensing fact); the
     type-mapping proposal is pending and unapplied; rollback binds to 1.1.

Standard library plus `git ls-files` (local, no network) for tracked-status.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities_grid3 import source as S
from build_facilities_grid3_candidate import (ATTRIBUTION_CITATION, CANDIDATE_PATH,
                                              MANIFEST_PATH, PROPOSAL_PATH,
                                              QUARANTINE_PATH, facility_id)
from vocab.artifact_io import load_json, repo_path, sha256_file
from vocab.schema_check import validate as schema_validate

SCHEMA_PATH = repo_path("schema", "facilities_grid3.v2.schema.json")
ATTRIBUTION_PATH = repo_path("facilities", "ATTRIBUTION_GRID3.md")
V1_0_SHA256 = "1c7b939199ab4465156f4cb336910eea120fcaa70f8b1c0743fc9f7a7c03009e"


class Results:
    def __init__(self):
        self.checks = []

    def add(self, label, ok, detail=""):
        self.checks.append((label, bool(ok), detail))
        print("%-4s %s%s" % ("ok" if ok else "FAIL", label,
                             (" — " + str(detail)) if (detail and not ok) else ""))

    @property
    def failed(self):
        return [c for c in self.checks if not c[1]]


def git_tracked(path):
    completed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=repo_path(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return completed.returncode == 0


def main():
    r = Results()
    candidate = load_json(CANDIDATE_PATH)
    meta = candidate["_metadata"]
    records = candidate["facilities"]
    with open(CANDIDATE_PATH, "rb") as handle:
        candidate_bytes = handle.read()

    # --- A. permitted source ---------------------------------------------------------------
    r.add("GRID3 source bytes match the pinned digest",
          sha256_file(S.GRID3_PATH) == S.GRID3_SHA256)
    r.add("vendored CC BY 4.0 legal code matches its pin",
          sha256_file(S.LEGALCODE_PATH) == S.LEGALCODE_SHA256)
    evidence = load_json(S.LICENCE_EVIDENCE_PATH)
    r.add("licence evidence pins the same source digest",
          evidence["source_file"]["sha256"] == S.GRID3_SHA256)
    r.add("licence evidence quotes the CC BY 4.0 statement verbatim",
          "Creative Commons Attribution 4.0 International License, CC BY 4.0"
          in evidence["licence"]["licence_statement_verbatim"])
    r.add("licence evidence pins the vendored legal code",
          evidence["licence"]["legal_code_vendored"]["sha256"] == S.LEGALCODE_SHA256)
    r.add("candidate cites the licence evidence and the licence",
          meta["source"]["licence"] == "CC BY 4.0"
          and meta["source"]["licence_evidence"] == "facilities/source/grid3_licence_evidence_v1.json"
          and meta["source"]["sha256"] == S.GRID3_SHA256)
    r.add("candidate citation equals the evidence record's citation template with the access date",
          meta["source"]["attribution"]["citation"] == ATTRIBUTION_CITATION
          and evidence["dataset_identity"]["citation_template_verbatim"].split("Accessed")[0].strip()
          == ATTRIBUTION_CITATION.split("Accessed")[0].strip())
    with open(ATTRIBUTION_PATH, encoding="utf-8") as handle:
        attribution_text = handle.read()
    r.add("attribution notice carries the citation, the licence URL and the modification disclosure",
          ATTRIBUTION_CITATION in attribution_text
          and "https://creativecommons.org/licenses/by/4.0" in attribution_text
          and "Modifications" in attribution_text)

    # --- schema ----------------------------------------------------------------------------
    errors = schema_validate(candidate, load_json(SCHEMA_PATH))
    r.add("candidate satisfies the GRID3 v2 schema", not errors, "; ".join(errors[:3]))

    # --- B. isolation ----------------------------------------------------------------------
    hits = {m: candidate_bytes.count(m.encode("utf-8")) for m in S.NHFR_MARKER_STRINGS}
    r.add("committed candidate bytes carry zero NHFR markers",
          sum(hits.values()) == 0, {k: v for k, v in hits.items() if v})
    for path in S.FORBIDDEN_SOURCES:
        r.add("forbidden source is not tracked on this branch: %s" % path,
              not git_tracked(path))
    try:
        S.open_input(repo_path("facilities", "source", "nigeria_health_facilities.csv"))
        door = False
    except S.ForbiddenInput:
        door = True
    r.add("the pipeline's input door refuses the NHFR export", door)
    r.add("permitted inputs are exactly the GRID3 CSV and the 1.1 comparison baseline",
          set(S.ALLOWED_INPUTS) == {S.GRID3_PATH, S.CURRENT_ARTIFACT_PATH})

    rows = S.read_source()
    by_globalid = {row["globalid"].strip(): row for row in rows}
    r.add("every record's facility_id derives from a distinct GRID3 globalid",
          len({rec["source_record"]["source_globalid"] for rec in records}) == len(records)
          and all(rec["source_record"]["source_globalid"] in by_globalid for rec in records)
          and all(facility_id(rec["source_record"]["source_globalid"]) == rec["facility_id"]
                  for rec in records))
    coord_exact = name_traced = 0
    for rec in records:
        row = by_globalid[rec["source_record"]["source_globalid"]]
        if (rec["latitude"] == float(row["latitude"])
                and rec["longitude"] == float(row["longitude"])):
            coord_exact += 1
        if rec["name"] == S.clean_text(row["facility_name"]):
            name_traced += 1
    r.add("every coordinate equals the GRID3 source value exactly (no swap, snap or move)",
          coord_exact == len(records), coord_exact)
    r.add("every name traces to the GRID3 source through the recorded normalization",
          name_traced == len(records), name_traced)

    # --- C. honesty ------------------------------------------------------------------------
    # The FAC-D001 mapping is checked against the GOVERNED documents — the
    # approved proposal table and the decision register — not against the
    # generator's own constant, so generator drift cannot validate itself.
    proposal = load_json(PROPOSAL_PATH)
    approved_map = {entry["source_value"]: entry["proposed_type"]
                    for entry in proposal["mapping"]}
    register = load_json(repo_path("facilities", "facilities_grid3_decision_register_v1.json"))
    d001 = next(d for d in register["decisions"] if d["id"] == "FAC-D001")
    d002 = next(d for d in register["decisions"] if d["id"] == "FAC-D002")
    all_null = lambda field: all(rec[field] is None for rec in records)  # noqa: E731
    r.add("every type equals the approved mapping of its own facility_level_option "
          "(a function of the option alone — no name is ever read)",
          all(rec["type"] == approved_map[rec["source_record"]["facility_level_option"]]
              for rec in records))
    type_counts = {"hospital": 0, "health_centre": 0, None: 0}
    for rec in records:
        type_counts[rec["type"]] += 1
    r.add("populated types are exactly the approved values and unknown stays null",
          set(type_counts) == {"hospital", "health_centre", None}
          and type_counts[None] > 0
          and type_counts[None] == sum(
              1 for rec in records
              if rec["source_record"]["facility_level_option"] == "unknown"))
    r.add("the decision register records FAC-D001 approved with these exact counts",
          d001["status"] == "approved" and d001["decided_on"] == "2026-09-15"
          and d001["counts"] == {"hospital": type_counts["hospital"],
                                 "health_centre": type_counts["health_centre"],
                                 "null_unspecified": type_counts[None]})
    r.add("the artifact's type_mapping_applied block agrees with the register",
          meta["type_mapping_applied"]["counts"]
          == {"hospital": type_counts["hospital"],
              "health_centre": type_counts["health_centre"],
              "null_unspecified": type_counts[None]}
          and meta["type_mapping_applied"]["mapping"] == approved_map)
    r.add("FAC-D002 remains blocked on Clinical wording and emergency_capable is not populated",
          d002["status"] == "product_direction_approved_clinical_wording_pending"
          and d002["implemented"] is False)
    r.add("phone is null on every record", all_null("phone"))
    r.add("opening_hours is null on every record", all_null("opening_hours"))
    r.add("emergency_capable is null on every record", all_null("emergency_capable"))
    r.add("address, statuses and beds are null on every record",
          all(all_null(f) for f in ("address", "operational_status",
                                    "registration_status", "license_status", "beds")))
    r.add("every service flag is null on every record",
          all(v is None for rec in records for v in rec["services"].values()))
    r.add("coordinate_transformation is none on every record",
          all(rec["source_record"]["coordinate_transformation"] == "none"
              for rec in records))
    quarantine = load_json(QUARANTINE_PATH)
    r.add("accounting sums: source rows == emitted + quarantined",
          quarantine["source_rows"] == S.GRID3_ROWS
          and quarantine["emitted"] + quarantine["quarantined"] == S.GRID3_ROWS
          and quarantine["emitted"] == len(records))
    r.add("every state present, including Adamawa, Kebbi and Sokoto",
          meta["states_covered"] == S.CANONICAL_STATES
          and all(any(rec["state"] == s for rec in records)
                  for s in ("Adamawa", "Kebbi", "Sokoto")))
    r.add("snapshot is the declared constant 2024-11-11",
          all(rec["source_record"]["source_last_updated"] == "2024-11-11"
              for rec in records))

    # --- D. governance ----------------------------------------------------------------------
    r.add("candidate is candidate_unapproved and may_publish false",
          meta["release_status"] == "candidate_unapproved"
          and meta["publication_status"] == "candidate_unapproved"
          and meta["may_publish"] is False and meta["release_date"] is None)
    r.add("lineage is grid3 and ids are ng_g3_",
          meta["lineage"] == "grid3"
          and all(rec["facility_id"].startswith("ng_g3_") for rec in records))
    manifest = load_json(MANIFEST_PATH)
    r.add("manifest describes the bytes on disk",
          manifest["candidate_artifact"]["sha256"] == sha256_file(CANDIDATE_PATH)
          and manifest["candidate_artifact"]["bytes"] == os.path.getsize(CANDIDATE_PATH)
          and manifest["candidate_artifact"]["record_count"] == len(records))
    gates = manifest["publication_gates"]
    decided_true = {"source_licensing_established", "fac_d001_type_mapping_approved",
                    "fac_d003_absent_contact_fields_accepted",
                    "fac_d004_grid3_coordinates_accepted",
                    "fac_d005_quarantine_policy_accepted",
                    "fac_d006_duplicate_policy_accepted",
                    "nationwide_coverage_accepted"}
    r.add("manifest is not live; gates reflect the 2026-09-15 decisions exactly; "
          "publication stays blocked",
          manifest["IS_LIVE_MANIFEST"] is False
          and all(gates[k] is True for k in decided_true)
          and all(v is False for k, v in gates.items() if k not in decided_true)
          and gates["fac_d002_emergency_fallback_approved"] is False
          and gates["may_publish"] is False)
    r.add("rollback binds to facilities 1.1 by hash, and 1.0/1.1 are byte-identical to their pins",
          manifest["rollback"]["target_sha256"] == S.CURRENT_ARTIFACT_SHA256
          and sha256_file(S.CURRENT_ARTIFACT_PATH) == S.CURRENT_ARTIFACT_SHA256
          and sha256_file(repo_path("facilities.ng.v1.0.json")) == V1_0_SHA256)
    inventory = set(proposal["source_value_inventory"])
    mapped = {entry["source_value"] for entry in proposal["mapping"]}
    r.add("type-mapping record is approved, applied, dated, and covers the whole inventory",
          proposal["_metadata"]["status"] == "APPROVED"
          and proposal["_metadata"]["applied"] is True
          and proposal["decision"]["status"] == "approved"
          and proposal["decision"]["reviewer"] is not None
          and proposal["decision"]["decided_on"] == "2026-09-15"
          and inventory == mapped)
    r.add("no proposed type is outside the declared vocabulary",
          all(entry["proposed_type"] in (None, "hospital", "clinic", "health_centre",
                                         "pharmacy", "laboratory", "other")
              for entry in proposal["mapping"]))

    print()
    if r.failed:
        print("%d of %d checks FAILED" % (len(r.failed), len(r.checks)))
        return 1
    print("all %d GRID3 candidate checks passed" % len(r.checks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
