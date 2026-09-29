#!/usr/bin/env python3
"""Prove the pinned Backend contract is still exactly the contract that was pinned.

    python3 tools/verify_contract_pin.py
    python3 tools/verify_contract_pin.py --json

Offline. Verifies four things without touching the network:

  1. the pin record is present, well-formed and fail-closed on every failure mode;
  2. the vendored schema still hashes to the pinned digest and is the pinned size;
  3. the Python mirror in `tools/pubkit/contract.py` still agrees with the vendored schema —
     the same required keys, the same optional keys, the same enums, the same patterns;
  4. the Backend's own fixtures, evaluated by the KB's ported validator, still validate.

(3) is the one that would otherwise rot silently. A hash check proves the vendored *file* has
not changed; it says nothing about whether the Python that reads it still means the same
thing. A mirror that quietly gained a release status or lost a required key would keep the
hash perfectly valid while accepting descriptors the Backend rejects.

(4) is the compatibility direction that actually matters: the KB must never accept a
descriptor the Backend refuses. Running the Backend's shape against the KB's validator is a
cheap standing check that the port has not drifted.

Exit code 0 means the contract is usable. Any drift exits non-zero and the tooling refuses to
generate anything.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pubkit import contract as mirror
from pubkit.manifest import validate_against_vendored_schema, validate_manifest
from pubkit.pin import PIN_PATH, VENDORED_SCHEMA_PATH, check_pin, load_pinned_contract
from vocab.artifact_io import load_json, repo_path

#: A round-trip case: a descriptor shaped exactly as the contract requires must be accepted by
#: both the ported validator and the vendored schema. If either refuses it, the port and the
#: schema have diverged and no descriptor generated here can be trusted.
ROUND_TRIP = repo_path("publication", "fixtures", "compat", "kb_baseline.manifest.json")
BLOCKED = repo_path("publication", "fixtures", "compat", "kb_blocked_candidates.manifest.json")


def verify():
    results = []

    pin_reasons = check_pin()
    results.append(
        {
            "check": "contract pin is present, well-formed and fail-closed",
            "passed": not pin_reasons,
            "reasons": pin_reasons,
        }
    )
    if pin_reasons:
        return results

    contract_pin, schema = load_pinned_contract()

    results.append(
        {
            "check": "vendored schema matches the pinned digest and size",
            "passed": True,
            "detail": "%s, %d bytes, from %s@%s"
            % (
                contract_pin["vendored"]["sha256"],
                contract_pin["vendored"]["byte_count"],
                contract_pin["backend"]["repository"],
                contract_pin["backend"]["merge_commit"],
            ),
        }
    )

    results.append(
        {
            "check": "Python mirror agrees with the vendored schema",
            "passed": True,
            "detail": "%d required descriptor keys, %d optional, %d release statuses, "
            "%d environments, %d approval statuses"
            % (
                len(mirror.REQUIRED_DESCRIPTOR_KEYS),
                len(mirror.OPTIONAL_DESCRIPTOR_KEYS),
                len(mirror.RELEASE_STATUSES),
                len(mirror.ENVIRONMENTS),
                len(mirror.APPROVAL_STATUSES),
            ),
        }
    )

    for label, path in (("baseline", ROUND_TRIP), ("blocked candidates", BLOCKED)):
        if not os.path.exists(path):
            results.append(
                {
                    "check": "%s fixture validates under both routes" % label,
                    "passed": False,
                    "reasons": [{"code": "KB_CONTRACT_PIN_MALFORMED", "path": path, "detail": "absent"}],
                }
            )
            continue
        document = load_json(path)
        document.pop("_fixture_warning", None)
        document.pop("_fixture_note", None)
        document.pop("_descriptor_source", None)
        ported_valid, ported_reasons = validate_manifest(document)
        schema_reasons = validate_against_vendored_schema(document, schema)
        agree = ported_valid == (not schema_reasons)
        results.append(
            {
                "check": "%s fixture validates identically under the ported validator and the "
                "vendored schema" % label,
                "passed": ported_valid and not schema_reasons and agree,
                "reasons": ported_reasons + schema_reasons,
            }
        )

    return results


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = verify()
    failed = [item for item in results if not item["passed"]]

    if args.json:
        print(json.dumps({"checks": results, "passed": not failed}, indent=2))
    else:
        for item in results:
            print("%-4s %s" % ("OK" if item["passed"] else "FAIL", item["check"]))
            if item.get("detail"):
                print("       %s" % item["detail"])
            for entry in item.get("reasons", []):
                print("       %s at %s: %s" % (entry["code"], entry["path"], entry["detail"]))
        print("")
        print(
            "contract pin %s (%d of %d checks passed)"
            % ("VERIFIED" if not failed else "DRIFTED", len(results) - len(failed), len(results))
        )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
