#!/usr/bin/env python3
"""Generate the facilities candidate manifest entry.

    python3 tools/build_facilities_manifest.py            # write
    python3 tools/build_facilities_manifest.py --check    # fail if it is stale

Writes `candidate/facilities.manifest.candidate.json`: one machine-readable record of what
the candidate IS — version, sha256, byte size, record count, generation time, source snapshot
and provenance — in the shape of the `/config` block the Backend serves, so the entry that
would be wired if the candidate were ever approved is visible now without wiring it.

This is NOT the live manifest. The live manifest is `GET /config` in wellapath-backend and is
unchanged. Every gate in this file is false, `may_publish` is false, and the file says so in
its own first fields. The digest is computed from the candidate bytes at generation time, so
the manifest cannot describe bytes other than the ones on disk, and `--check` fails if either
side moves.

Standard library only, no network.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from facilities import FACILITIES_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

CANDIDATE = repo_path("candidate", "facilities.ng.v2.0.json")
CURRENT = repo_path("facilities.ng.v1.1.json")
QUALITY = repo_path("reports", "facilities_quality_v1.json")
COMPAT = repo_path("reports", "facilities_mobile_compat_v1.json")
MANIFEST = repo_path("candidate", "facilities.manifest.candidate.json")

#: The approved public origin, already named in the Backend repository's tests, docs and
#: .env.example. Not a credential. Naming it exposes nothing new.
R2_BASE_URL = "https://pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev"


def build():
    candidate = load_json(CANDIDATE)
    meta = candidate["_metadata"]
    current_meta = load_json(CURRENT)["_metadata"]
    quality = load_json(QUALITY)
    compat = load_json(COMPAT)
    checklist = load_json(repo_path("facilities", "source", "nhf_authorization_checklist_v1.json"))
    digest = sha256_file(CANDIDATE)

    return {
        "manifest_id": "facilities_v2_candidate",
        "manifest_version": "1",
        "generator": "tools/build_facilities_manifest.py",
        "generator_version": FACILITIES_TOOLING_VERSION,
        "IS_LIVE_MANIFEST": False,
        "WARNING": (
            "This is a PROPOSED manifest block for a CANDIDATE artifact. It is not served by any "
            "endpoint. The live manifest is GET /config in wellapath-backend "
            "(src/routes/config.ts) and is UNCHANGED. The source licence is not established, "
            "which blocks publication independently of every other gate. Do not wire this block."
        ),
        "live_manifest": {
            "location": "wellapath-backend src/routes/config.ts -> GET /config .artifacts",
            "changed_by_this_step": False,
            "current_facilities_entry": {
                "version": current_meta["version"],
                "url": "%s/facilities.ng.v1.1.json" % R2_BASE_URL,
                "url_is_the_convention_not_an_observation": True,
                "hash": "sha256:%s" % sha256_file(CURRENT),
                "release_date": current_meta["release_date"],
                "country": current_meta["country"],
            },
        },
        "candidate_artifact": {
            "artifact_id": meta["artifact_id"],
            "version": meta["version"],
            "schema_version": meta["schema_version"],
            "schema_path": "schema/facilities.v2.schema.json",
            "schema_sha256": sha256_file(repo_path("schema", "facilities.v2.schema.json")),
            "filename": "facilities.ng.v2.0.json",
            "repository_path": "candidate/facilities.ng.v2.0.json",
            "sha256": digest,
            "hash": "sha256:%s" % digest,
            "bytes": os.path.getsize(CANDIDATE),
            "record_count": meta["total_facilities"],
            "content_type": "application/json",
            "charset": "utf-8",
            "compression": (
                "None at rest. The artifact is stored and served uncompressed, exactly as the "
                "current artifacts are; transport-level gzip/brotli is the CDN's business and the "
                "SHA256 is always of the uncompressed bytes."
            ),
            "release_status": meta["release_status"],
            "publication_status": meta["publication_status"],
            "may_publish": meta["may_publish"],
            "release_date": meta["release_date"],
            "country": meta["country"],
            "generated_at": meta["generated_at"],
            "generator": meta["generator"],
            "generator_version": meta["generator_version"],
            "uploaded_to_r2": False,
            "proposed_r2_url": "%s/facilities.ng.v2.0.json" % R2_BASE_URL,
            "proposed_r2_url_is_live": False,
        },
        "source": {
            "path": meta["source"]["path"],
            "sha256": meta["source"]["sha256"],
            "byte_count": meta["source"]["byte_count"],
            "provenance_record": meta["source"]["provenance_record"],
            "organization": meta["source"]["organization"],
            "licence": meta["source"]["licence"],
            "snapshot_declared_version": meta["source"]["snapshot_declared_version"],
            "snapshot_last_updated_at": meta["source"]["snapshot_last_updated_at"],
            "rows": quality["row_accounting"]["source_rows"],
            "coverage_claim": meta["coverage_claim"],
        },
        "pipeline_accounting": {
            "source_rows": quality["row_accounting"]["source_rows"],
            "emitted": quality["row_accounting"]["emitted"],
            "quarantined": quality["row_accounting"]["quarantined"],
            "quarantine_by_reason": quality["quarantine_reason_counts"],
            "exact_duplicates_collapsed": meta["deduplication"]["rows_removed"],
            "coordinate_remediation": {
                k: v for k, v in meta["coordinate_remediation"].items()
                if k in ("rule_id", "accepted_unchanged", "accepted_after_verified_swap",
                         "quarantined_ambiguous", "quarantined_invalid",
                         "records_corrected_in_artifact", "audit")
            },
            "reports": {
                "quality": "reports/facilities_quality_v1.json",
                "quarantine": "reports/facilities_quarantine_v1.json",
                "coordinate_audit": "reports/facilities_coordinate_audit_v1.json",
                "comparison_with_1_1": "reports/facilities_comparison_v1.json",
                "mobile_compatibility": "reports/facilities_mobile_compat_v1.json",
            },
        },
        "source_authorization": {
            "checklist": "facilities/source/nhf_authorization_checklist_v1.json",
            "all_satisfied": checklist["all_satisfied"],
            "items_missing": sorted(i["id"] for i in checklist["items"] if i["status"] != "satisfied"),
        },
        "proposed_config_block": {
            "_comment": "Shape matches the existing entries in src/routes/config.ts. NOT to be applied.",
            "facilities": {
                "version": meta["version"],
                "url": "${config.artifactBaseUrl}/facilities.ng.v2.0.json",
                "hash": "sha256:%s" % digest,
                "release_date": "<set at approval time — currently null>",
                "country": meta["country"],
            },
        },
        "rollback": {
            "target_version": current_meta["version"],
            "target_file": "facilities.ng.v1.1.json",
            "target_sha256": sha256_file(CURRENT),
            "target_byte_count": os.path.getsize(CURRENT),
            "target_url": "%s/facilities.ng.v1.1.json" % R2_BASE_URL,
            "target_untouched_by_this_work": True,
            "procedure": "mobile_handoff/facilities_v2/README.md (Rollback)",
            "note": "facilities 1.1 remains the active artifact. The candidate has never been "
            "active, so there is nothing to roll back FROM; this records what the consumer "
            "returns to if the candidate is ever activated and then withdrawn.",
        },
        "mobile_compatibility": {
            "verdict": compat["verdict"],
            "blocking_findings": [f["finding"] for f in compat["blocking_findings"]
                                  if f["severity"] == "blocking"],
            "report": "reports/facilities_mobile_compat_v1.json",
        },
        "publication_gates": {
            "source_authorization_checklist_satisfied": checklist["all_satisfied"],
            "source_licence_established": False,
            "source_organization_established": False,
            "product_type_mapping_decided": False,
            "emergency_capability_rule_decided": False,
            "phone_public_use_basis_established": False,
            "mobile_compatible_as_is": False,
            "product_approval_recorded": False,
            "clinical_approval_recorded": False,
            "engineering_lead_approval_recorded": False,
            "uploaded_to_r2": False,
            "may_wire_into_config": False,
            "may_publish": False,
        },
        "validation_command": "python3 tools/run_facilities_checks.py",
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    payload = dump_report_bytes(build())
    relative = os.path.relpath(MANIFEST, repo_path())
    if args.check:
        if not os.path.exists(MANIFEST) or open(MANIFEST, "rb").read() != payload:
            print("DRIFT %s is missing or stale" % relative)
            return 1
        print("OK %s" % relative)
        return 0
    write_bytes(MANIFEST, payload)
    print("wrote %s (%d bytes)" % (relative, len(payload)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
