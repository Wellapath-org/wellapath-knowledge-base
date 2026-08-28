#!/usr/bin/env python3
"""Build the committed dry-run publication plans.

    python3 tools/build_publication_plans.py                     # write every plan
    python3 tools/build_publication_plans.py --check              # fail if a committed plan differs
    python3 tools/build_publication_plans.py --artifact question_flow --version 1.1
    python3 tools/build_publication_plans.py --artifact kb --version 2.4 --stdout

Writes `publication/plans/<artifact>.<country>.v<version>.dryrun.json`.

A plan is a *report on a named artifact version*, so the artifact and version are always
explicit: there is no "publish everything" mode and no default target. Generating a plan
performs no upload, publication, activation or deployment, and modifies no artifact byte.

The whole run happens inside `pubkit.safety.no_side_effects`, which refuses a socket, a
subprocess or a write outside the staging directory and the plan output directory. That is
belt and braces — the tooling contains no such code — but it means the guarantee is enforced
rather than asserted.

Standard library only, no network.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pubkit import inventory
from pubkit.governance import DecisionRegister
from pubkit.pin import load_pinned_contract
from pubkit.plan import build_plan
from pubkit.safety import no_side_effects
from pubkit.staging import DEFAULT_STAGING_ROOT
from vocab.artifact_io import dump_report_bytes, repo_path, write_bytes

PLAN_DIR = repo_path("publication", "plans")
REGISTER = repo_path("publication", "governance", "decision_register_v1.json")

#: The artifacts this step generates committed plans for: the two blocked candidates.
#:
#: Plans exist for these two because they are the ones under governance pressure, and a
#: committed plan is how "still blocked, still for these reasons" becomes something CI can
#: check. Any governed artifact can be planned on demand with --artifact/--version.
COMMITTED_PLAN_TARGETS = (
    ("token_dictionary", "2.0"),
    ("question_flow", "1.1"),
)


def plan_path(entry):
    return os.path.join(PLAN_DIR, "%s.dryrun.json" % entry["object_key"][: -len(".json")])


def generate(targets, staging_root=None):
    """Build plans for `targets`, returning `[(entry, plan, bytes)]`."""
    contract_pin, contract_schema = load_pinned_contract()
    entries = inventory.discover()
    inventory_reasons = inventory.check_inventory(entries)
    if inventory_reasons:
        raise SystemExit(
            "the governed inventory is not sound; refusing to plan:\n"
            + "\n".join("  %s at %s: %s" % (r["code"], r["path"], r["detail"]) for r in inventory_reasons)
        )

    register = DecisionRegister.from_file(REGISTER)

    built = []
    for artifact_id, artifact_version in targets:
        entry = inventory.find(entries, artifact_id, artifact_version)
        if entry is None:
            raise SystemExit(
                "no governed artifact %s@%s exists in this repository" % (artifact_id, artifact_version)
            )
        plan, _reasons = build_plan(
            artifact_id,
            artifact_version,
            entry,
            register,
            contract_pin,
            contract_schema,
            entries,
            staging_root=staging_root,
        )
        built.append((entry, plan, dump_report_bytes(plan)))
    return built


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--artifact", help="artifact id to plan (default: the committed targets)")
    parser.add_argument("--version", help="artifact version to plan")
    parser.add_argument("--check", action="store_true", help="fail if a committed plan differs")
    parser.add_argument("--stdout", action="store_true", help="print the plan instead of writing it")
    args = parser.parse_args(argv)

    if bool(args.artifact) != bool(args.version):
        parser.error("--artifact and --version must be given together: a plan targets one named version")

    targets = [(args.artifact, args.version)] if args.artifact else list(COMMITTED_PLAN_TARGETS)

    # Writes are permitted only into the staging area and the plan directory. Anything else —
    # a socket, a subprocess, a stray file — aborts the run.
    with no_side_effects(allowed_write_roots=(DEFAULT_STAGING_ROOT, PLAN_DIR)):
        built = generate(targets)

    if args.stdout:
        for _entry, _plan, data in built:
            sys.stdout.write(data.decode("utf-8"))
        return 0

    failures = 0
    for entry, _plan, data in built:
        path = plan_path(entry)
        relative = os.path.relpath(path, repo_path())
        if args.check:
            if not os.path.exists(path):
                print("MISSING %s" % relative)
                failures += 1
                continue
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
