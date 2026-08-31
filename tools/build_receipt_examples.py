#!/usr/bin/env python3
"""Build the non-operative receipt examples.

    python3 tools/build_receipt_examples.py           # write
    python3 tools/build_receipt_examples.py --check    # fail if the committed copies differ

Writes `publication/receipts/*.example.json`.

These are shape definitions, not records. Every example is bound to a real artifact identity
and a real hash — so the shape is exercised against something concrete rather than against
`"..."` — but every one declares `operative: false` and, where it records a decision, that
decision is `refused`. There is no example of a successful upload, publication or activation,
because forging one would produce a file that looks exactly like the thing a future operator
tool will emit, sitting in the directory that tool will write to.

The rollback example is the one that records `granted`, and only because a rollback receipt's
whole purpose is to demonstrate the version-and-hash binding on both ends. It too is
`operative: false` and `rollback_performed: false`, and it describes a return to an existing
governed artifact rather than any state change.

Standard library only, no network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pubkit import inventory
from vocab.artifact_io import dump_report_bytes, repo_path, write_bytes
from vocab.schema_check import validate as schema_validate
from vocab.artifact_io import load_json

OUTPUT_DIR = repo_path("publication", "receipts")
SCHEMA = repo_path("schema", "publication_receipt.v1.schema.json")

DECLARATION = (
    "DRY-RUN EXAMPLE — NOT A RECORD OF ANY OPERATION. No upload, publication, activation or "
    "rollback has occurred. This document exists to define the shape a future authorized "
    "operation would record."
)

SIGNING_GAP = (
    "Contract 1.0.0 defines no receipt or manifest signing. This repository holds no signing "
    "key, no key custody procedure and no verification path, and invents none: an unsigned "
    "receipt is a statement by whoever wrote the file, and a home-made signature would look "
    "like assurance without being any. Establishing a trust mechanism is new infrastructure "
    "and needs its own decision."
)

UNASSIGNED_ACTOR = {
    "identity": None,
    "title": None,
    "role": "unassigned",
    "authority_type": "none",
}


def _artifact(entry):
    return {
        "artifact_id": entry["artifact_id"],
        "artifact_version": entry["artifact_version"],
        "sha256": entry["descriptor_sha256"],
        "byte_count": entry["byte_count"],
        "object_key": entry["object_key"],
        "country": entry["country"],
    }


def _version_ref(entry):
    return {"artifact_version": entry["artifact_version"], "sha256": entry["descriptor_sha256"]}


def build(entries):
    question_flow = inventory.find(entries, "question_flow", "1.1")
    token_dictionary_2 = inventory.find(entries, "token_dictionary", "2.0")
    token_dictionary_1 = inventory.find(entries, "token_dictionary", "1.1")

    upload = {
        "receipt_type": "upload",
        "receipt_id": "EXAMPLE-UPLOAD-0001",
        "receipt_schema_version": "1.0.0",
        "operative": False,
        "non_operative_declaration": DECLARATION,
        "actor": dict(UNASSIGNED_ACTOR),
        "occurred_at": None,
        "environment": "staging",
        "artifact": _artifact(token_dictionary_2),
        "decision_references": [
            "no publication authorization exists for token_dictionary@2.0",
            "publication/plans/token_dictionary.ng.v2.0.dryrun.json",
        ],
        "signing": {"signed": False, "mechanism": None, "gap": SIGNING_GAP},
        "upload_performed": False,
        "origin": None,
        "verified_after_upload": {
            "performed": False,
            "method": "A real upload is verified by re-reading the stored object and "
            "re-deriving sha256 and byte_count from the bytes actually returned. An ETag, a "
            "Content-Length or a success status is not verification: none of them is the "
            "content.",
        },
        "note": "Upload is a separate, explicitly authorized operation that does not exist in "
        "this repository. The origin is null because no destination has been decided and "
        "writing one would make a proposal look like a plan of record.",
    }

    publication = {
        "receipt_type": "publication_decision",
        "receipt_id": "EXAMPLE-PUBLICATION-0001",
        "receipt_schema_version": "1.0.0",
        "operative": False,
        "non_operative_declaration": DECLARATION,
        "actor": dict(UNASSIGNED_ACTOR),
        "occurred_at": None,
        "environment": "staging",
        "artifact": _artifact(question_flow),
        "decision_references": [
            "publication/governance/decision_register_v1.json",
            "IM001-ORD-GLOBAL-001 (Product authority over option ordering only)",
            "IM001-DECISION-SET-COMPLETE (a completed decision set, not an authorization)",
            "IM003-DISPOSITION-001 (Product disposition; clinical approval false)",
        ],
        "signing": {"signed": False, "mechanism": None, "gap": SIGNING_GAP},
        "publication_performed": False,
        "decision": "refused",
        "predecessor": _version_ref(inventory.find(entries, "question_flow", "1.0")),
        "approvals_at_decision": {"product": "pending", "clinical": "pending"},
        "blockers_at_decision": [
            {"id": "IM001-CLIN-FLAG-001", "status": "open"},
            {"id": "IM003-SB-001", "status": "open"},
        ],
        "note": "Refused. Clinical approval is not granted, no Clinical reviewer is assigned, "
        "two safety blockers are open, and no publication authorization record exists. The "
        "decision is recorded as refused rather than omitted: a refusal that leaves no trace "
        "is indistinguishable from a question nobody asked.",
    }

    activation = {
        "receipt_type": "activation",
        "receipt_id": "EXAMPLE-ACTIVATION-0001",
        "receipt_schema_version": "1.0.0",
        "operative": False,
        "non_operative_declaration": DECLARATION,
        "actor": dict(UNASSIGNED_ACTOR),
        "occurred_at": None,
        "environment": "staging",
        "artifact": _artifact(question_flow),
        "decision_references": [
            "no activation authorization exists for question_flow@1.1",
            "im_001_resolved: true is a decision-set completion and authorizes no activation",
        ],
        "signing": {"signed": False, "mechanism": None, "gap": SIGNING_GAP},
        "activation_performed": False,
        "decision": "refused",
        "deactivated": None,
        "activation_authorization_ref": None,
        "note": "Refused. Activation requires an explicit activation authorization bound to "
        "this artifact and version; none exists. `deactivated` is null because nothing was "
        "active to replace — a fact worth recording rather than an empty field.",
    }

    rollback = {
        "receipt_type": "rollback",
        "receipt_id": "EXAMPLE-ROLLBACK-0001",
        "receipt_schema_version": "1.0.0",
        "operative": False,
        "non_operative_declaration": DECLARATION,
        "actor": dict(UNASSIGNED_ACTOR),
        "occurred_at": None,
        "environment": "staging",
        "artifact": _artifact(token_dictionary_2),
        "decision_references": [
            "docs/VOCABULARY_ROLLBACK.md",
            "publication/plans/token_dictionary.ng.v2.0.dryrun.json",
        ],
        "signing": {"signed": False, "mechanism": None, "gap": SIGNING_GAP},
        "rollback_performed": False,
        "decision": "refused",
        "rolled_back_from": _version_ref(token_dictionary_2),
        "rolled_back_to": _version_ref(token_dictionary_1),
        "hash_bound": True,
        "note": "Refused, and it would be refused even if publication had happened: "
        "token_dictionary 2.0 declares content schema 2.0 while 1.1 declares 1.0, so the "
        "return crosses a content-schema boundary that contract 1.1.0 has no policy for. Both "
        "ends are hash-bound anyway, which is what makes the refusal precise rather than vague.",
    }

    return [
        ("upload_receipt.example.json", upload),
        ("publication_decision_receipt.example.json", publication),
        ("activation_receipt.example.json", activation),
        ("rollback_receipt.example.json", rollback),
    ]


def main(argv):
    check = "--check" in argv
    schema = load_json(SCHEMA)
    entries = inventory.discover()

    failures = 0
    for filename, receipt in build(entries):
        errors = schema_validate(receipt, schema)
        if errors:
            print("SCHEMA FAILURE in %s:" % filename)
            for error in errors:
                print("  %s" % error)
            failures += 1
            continue

        data = dump_report_bytes(receipt)
        path = os.path.join(OUTPUT_DIR, filename)
        relative = os.path.relpath(path, repo_path())

        if check:
            if not os.path.exists(path):
                print("MISSING %s" % relative)
                failures += 1
            else:
                with open(path, "rb") as handle:
                    committed = handle.read()
                if committed != data:
                    print("DRIFT %s is not reproducible from its generator" % relative)
                    failures += 1
                else:
                    print("OK %s" % relative)
        else:
            write_bytes(path, data)
            print("wrote %s (%d bytes)" % (relative, len(data)))

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
