#!/usr/bin/env python3
"""Generate the candidate manifest.

    python3 tools/build_candidate_manifest.py            # write the manifest
    python3 tools/build_candidate_manifest.py --check    # fail if it is stale

This is NOT the live manifest. The live manifest is the `artifacts` object
served by the backend's `GET /config`, defined in
`wellapath-backend/src/routes/config.ts`. This file is a proposed block in that
same shape, so the backend engineer can see exactly what would be wired if and
when the candidate is approved — without anything being wired now.

The manifest carries the artifact's hash, generated from the candidate bytes, so
it cannot drift from the artifact it describes.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vocab import VOCAB_TOOLING_VERSION
from vocab.artifact_io import dump_report_bytes, load_json, repo_path, sha256_file, write_bytes

CANDIDATE = repo_path("candidate", "token_dictionary.ng.v2.0.json")
MANIFEST = repo_path("candidate", "manifest.candidate.json")

R2_BASE_URL = "https://pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev"


def build():
    candidate = load_json(CANDIDATE)
    metadata = candidate["_metadata"]
    digest = sha256_file(CANDIDATE)

    return {
        "manifest_id": "token_dictionary_v2_candidate",
        "manifest_version": "1",
        "generator": "tools/build_candidate_manifest.py",
        "generator_version": VOCAB_TOOLING_VERSION,
        "IS_LIVE_MANIFEST": False,
        "WARNING": (
            "This is a PROPOSED manifest block for a CANDIDATE artifact. It is not served by any "
            "endpoint. The live manifest is GET /config in wellapath-backend "
            "(src/routes/config.ts) and is UNCHANGED by W2 Step 1. Do not wire this block until "
            "clinical review and engineering-lead approval are recorded."
        ),
        "live_manifest": {
            "location": "wellapath-backend src/routes/config.ts -> GET /config .artifacts",
            "changed_by_w2_step_1": False,
            "current_token_dictionary_entry": {
                "version": "1.1",
                "url": "%s/token_dictionary.ng.v1.1.json" % R2_BASE_URL,
                "hash": "sha256:%s" % sha256_file(repo_path("token_dictionary.ng.v1.1.json")),
                "release_date": "2026-04-05",
                "country": "ng",
            },
        },
        "candidate_artifact": {
            "artifact_id": metadata["artifact_id"],
            "version": metadata["version"],
            "schema_version": metadata["schema_version"],
            "filename": "token_dictionary.ng.v2.0.json",
            "repository_path": "candidate/token_dictionary.ng.v2.0.json",
            "sha256": digest,
            "hash": "sha256:%s" % digest,
            "bytes": os.path.getsize(CANDIDATE),
            "content_type": "application/json",
            "charset": "utf-8",
            "compression": (
                "None at rest. The artifact is stored and served uncompressed, exactly as the "
                "current artifacts are; transport-level gzip/brotli is the CDN's business and the "
                "SHA256 is always of the uncompressed bytes."
            ),
            "release_status": metadata["release_status"],
            "release_date": metadata["release_date"],
            "country": metadata["country"],
            "generated_at": metadata["generated_at"],
            "uploaded_to_r2": False,
            "proposed_r2_url": "%s/token_dictionary.ng.v2.0.json" % R2_BASE_URL,
            "proposed_r2_url_is_live": False,
        },
        "proposed_config_block": {
            "_comment": "Shape matches the existing entries in src/routes/config.ts. NOT to be applied yet.",
            "token_dictionary": {
                "version": metadata["version"],
                "url": "${config.artifactBaseUrl}/token_dictionary.ng.v2.0.json",
                "hash": "sha256:%s" % digest,
                "release_date": "<set at approval time — currently null>",
                "country": metadata["country"],
            },
        },
        "rollback": {
            "target_version": metadata["rollback_target"]["version"],
            "target_file": metadata["rollback_target"]["file"],
            "target_sha256": metadata["rollback_target"]["sha256"],
            "target_url": "%s/token_dictionary.ng.v1.1.json" % R2_BASE_URL,
            "procedure": "docs/VOCABULARY_ROLLBACK.md",
        },
        "publication_gates": {
            "clinical_review_recorded": metadata["clinical_review"]["status"] == "reviewed",
            "engineering_lead_approval_recorded": False,
            "top50_regression_executed_against_kb_2_4": False,
            "uploaded_to_r2": False,
            "may_wire_into_config": False,
        },
        "validation_command": "python3 tools/run_w2_checks.py",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    payload = dump_report_bytes(build())

    if args.check:
        if not os.path.exists(MANIFEST) or open(MANIFEST, "rb").read() != payload:
            print("FAIL candidate/manifest.candidate.json is missing or stale")
            return 1
        print("OK   candidate manifest is current")
        return 0

    write_bytes(MANIFEST, payload)
    print("wrote candidate/manifest.candidate.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
