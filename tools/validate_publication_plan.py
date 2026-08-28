#!/usr/bin/env python3
"""Validate the committed dry-run publication plans.

    python3 tools/validate_publication_plan.py
    python3 tools/validate_publication_plan.py --json

Checks, for every plan under `publication/plans/`:

  * it satisfies `schema/publication_plan.v1.schema.json`, whose safety-critical fields are
    pinned by `const` — so a plan claiming an upload, a publication, an activation, eligibility
    or a granted approval fails here rather than being read as a report of one;
  * its descriptor satisfies contract 1.0.0 by both routes, and the two routes agree;
  * its integrity fields are the real digest and byte count of the artifact it names, recomputed
    from the bytes on disk rather than trusted from the plan;
  * its object key is safe, immutable, and encodes the identity it claims;
  * every governance claim it makes is refused, and refused with a reason;
  * it is ineligible in every environment, not only the one it targets;
  * it carries no credential, token, presigned URL or query parameter anywhere in its text;
  * its blocking reasons all carry known reason codes.

It then PHI-scans the whole `publication/` and `contracts/` trees. Those are committed JSON
that this step introduced, and `tools/verify_no_clinical_change.py` does not cover them — it
scans the trees the W3 question work produced. Rather than widen that tool's scan (and its
report) from here, this one imports its pattern list, so there is a single definition of what
counts as PHI and the two scans cannot drift apart.

Standard library only, no network.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pubkit import inventory
from pubkit.integrity import measure
from pubkit.keys import check_key_agrees_with_identity
from pubkit.manifest import validate_against_vendored_schema, validate_manifest
from pubkit.origin import validate_object_key
from pubkit.pin import load_pinned_contract
from pubkit.reasons import ALL_REASON_CODES
from verify_no_clinical_change import PHI_PATTERNS
from vocab.artifact_io import load_json, repo_path
from vocab.schema_check import validate as schema_validate

PLAN_DIR = repo_path("publication", "plans")
PLAN_SCHEMA = repo_path("schema", "publication_plan.v1.schema.json")

#: Patterns that must never appear anywhere in a plan's serialized text. Deliberately broad —
#: a false positive here costs a rename, a false negative costs a leaked credential.
SECRET_PATTERNS = (
    (r"(?i)\bAKIA[0-9A-Z]{16}\b", "an AWS-style access key id"),
    (r"(?i)\bx-amz-(signature|credential|security-token)\b", "a presigned-URL parameter"),
    (r"(?i)\b(aws_secret_access_key|r2_secret|secret_access_key)\b", "a secret key name"),
    (r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}", "a bearer token"),
    (r"(?i)\bghp_[A-Za-z0-9]{20,}", "a GitHub token"),
    (r"https://[^\"\s]*\?[^\"\s]*", "a URL carrying a query string"),
    (r"https://[^\"\s/]*:[^\"\s/@]*@", "a URL embedding credentials"),
)


class _Result(list):
    def add(self, name, passed, detail=""):
        self.append({"check": name, "passed": bool(passed), "detail": detail})
        return passed


#: Trees this step introduced, scanned with the same PHI patterns the W3 content-safety scan
#: uses. `.md` is included: documentation quotes decision rationale out of clinical records.
CONTENT_SAFETY_TREES = (("publication", (".json", ".md")), ("contracts", (".json", ".md")))

#: The one reviewed exception, matched exactly rather than by file or by pattern.
#:
#: `negative_fixtures.compat.json` contains a URL with `user:pass@` because it is the fixture
#: that proves a credential-bearing URL is REJECTED — the string is the test input for
#: `ORIGIN_HAS_CREDENTIALS`, and no URL can demonstrate that case without containing an `@`.
#: The credentials are the literal words "user" and "pass". Excluding the whole file would
#: stop scanning ~12KB of fixtures to silence one known string; excluding the string keeps
#: everything else scanned and keeps the exception visible.
ALLOWED_MATCHES = {
    (
        "publication/fixtures/compat/negative_fixtures.compat.json",
        "email address",
        "pass@pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev",
    ): "the ORIGIN_HAS_CREDENTIALS negative fixture; literal placeholder credentials in a "
    "case that asserts such URLs are refused",
}


def scan_content_safety():
    """PHI-scan the trees this step introduced. A hit is a failure, not a warning."""
    results = _Result()
    hits = []
    scanned = 0
    allowed = []

    for tree, suffixes in CONTENT_SAFETY_TREES:
        root = repo_path(tree)
        if not os.path.isdir(root):
            continue
        for directory, _subdirectories, names in os.walk(root):
            for name in sorted(names):
                if not name.endswith(suffixes):
                    continue
                path = os.path.join(directory, name)
                relative = os.path.relpath(path, repo_path()).replace(os.sep, "/")
                scanned += 1
                with open(path, encoding="utf-8", errors="replace") as handle:
                    text = handle.read()
                for label, pattern in PHI_PATTERNS:
                    for match in pattern.finditer(text):
                        key = (relative, label, match.group(0))
                        if key in ALLOWED_MATCHES:
                            allowed.append(key)
                            continue
                        hits.append("%s: %s -> %s" % (relative, label, match.group(0)))

    results.add(
        "publication/ and contracts/ contain no PHI-shaped content (%d files scanned, %d "
        "reviewed exceptions)" % (scanned, len(allowed)),
        not hits,
        "; ".join(hits[:6]),
    )
    results.add(
        "the content-safety scan actually looked at something",
        scanned >= 10,
        "%d files scanned" % scanned,
    )
    return results


def validate_plan(path, entries, schema, contract_schema):
    results = _Result()
    relative = os.path.relpath(path, repo_path())
    plan = load_json(path)

    with open(path, "rb") as handle:
        raw_text = handle.read().decode("utf-8")

    # --- plan schema ------------------------------------------------------------------------
    errors = schema_validate(plan, schema)
    results.add("%s: satisfies the publication plan schema" % relative, not errors, "; ".join(errors[:4]))

    # --- descriptor against the contract, both routes -----------------------------------------
    descriptor = plan["descriptor"]
    wrapper = {
        "manifest_version": "1.0.0",
        "generated_at": plan["_metadata"]["evaluated_at"],
        "artifacts": [descriptor],
    }
    ported_valid, ported_reasons = validate_manifest(wrapper)
    schema_reasons = validate_against_vendored_schema(wrapper, contract_schema)
    results.add(
        "%s: descriptor is accepted by the ported Backend validator" % relative,
        ported_valid,
        "; ".join("%s %s" % (r["code"], r["path"]) for r in ported_reasons[:4]),
    )
    results.add(
        "%s: descriptor is accepted by the vendored Backend schema" % relative,
        not schema_reasons,
        "; ".join(r["detail"] for r in schema_reasons[:4]),
    )
    results.add(
        "%s: both contract routes agree" % relative,
        ported_valid == (not schema_reasons) and plan["contract_validation"]["validators_agree"],
    )

    # --- integrity, recomputed rather than trusted ----------------------------------------------
    entry = inventory.find(entries, plan["target"]["artifact_id"], plan["target"]["artifact_version"])
    if entry is None:
        results.add("%s: names a governed artifact" % relative, False, "artifact not in inventory")
    else:
        _data, digest, byte_count = measure(os.path.join(inventory.REPO_ROOT, entry["repository_path"]))
        results.add(
            "%s: declared sha256 is the real digest of the artifact bytes" % relative,
            plan["integrity"]["sha256"] == digest == descriptor["sha256"],
            "plan %s, recomputed %s" % (plan["integrity"]["sha256"], digest),
        )
        results.add(
            "%s: declared byte_count is the real size of the artifact bytes" % relative,
            plan["integrity"]["byte_count"] == byte_count == descriptor["byte_count"],
            "plan %s, recomputed %s" % (plan["integrity"]["byte_count"], byte_count),
        )
        results.add(
            "%s: content type was determined from the bytes" % relative,
            plan["integrity"]["content_type"] == "application/json",
        )

    # --- object key ------------------------------------------------------------------------------
    key = plan["object_key"]["proposed"]
    key_reasons = validate_object_key(key, "object_key") + check_key_agrees_with_identity(
        key,
        plan["target"]["artifact_id"],
        plan["target"]["artifact_version"],
        plan["target"]["country"],
        "object_key",
    )
    results.add(
        "%s: object key is safe, immutable and encodes its identity" % relative,
        not key_reasons,
        "; ".join(r["code"] for r in key_reasons),
    )
    results.add("%s: object key equals the descriptor's" % relative, key == descriptor["object_key"])

    # --- governance ---------------------------------------------------------------------------------
    claims = plan["governance"]["claims"]
    results.add(
        "%s: every governance claim is refused" % relative,
        all(claim["granted"] is False for claim in claims),
    )
    results.add(
        "%s: every refused claim carries at least one reason" % relative,
        all(claim["reasons"] for claim in claims),
    )
    results.add(
        "%s: no clinical reviewer is assigned or inferred" % relative,
        plan["governance"]["clinical_reviewer_assigned"] is False
        and all(
            claim["decision_ref"] is None
            for claim in claims
            if claim["kind"] == "clinical_approval"
        ),
    )

    # --- lifecycle and eligibility ------------------------------------------------------------------
    states = plan["lifecycle"]["states"]
    results.add(
        "%s: no externally-established lifecycle state is asserted" % relative,
        all(
            states[state] is False
            for state in ("uploaded", "published", "approved", "active", "eligible_for_environment")
        ),
    )
    results.add(
        "%s: ineligible in every environment, not only the targeted one" % relative,
        all(
            plan["eligibility_by_environment"][environment]["eligible_for_environment"] is False
            for environment in ("development", "staging", "production")
        ),
    )
    results.add(
        "%s: performed no upload, publication, activation or deployment" % relative,
        all(
            plan["operations_performed"][flag] is False
            for flag in (
                "upload_performed",
                "publication_performed",
                "activation_performed",
                "deployment_performed",
                "storage_write_performed",
                "network_access_performed",
                "canonical_bytes_modified",
            )
        ),
    )

    # --- reason codes -------------------------------------------------------------------------------
    unknown = sorted(
        {
            item["code"]
            for item in plan["blocking_reasons"]
            if item["code"] not in ALL_REASON_CODES
        }
    )
    results.add(
        "%s: every blocking reason carries a known reason code" % relative,
        not unknown,
        ", ".join(unknown),
    )

    # --- secrets ---------------------------------------------------------------------------------------
    found = []
    for pattern, description in SECRET_PATTERNS:
        if re.search(pattern, raw_text):
            found.append(description)
    results.add(
        "%s: contains no credential, token, presigned URL or query parameter" % relative,
        not found,
        "; ".join(found),
    )

    return results


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    _contract_pin, contract_schema = load_pinned_contract()
    schema = load_json(PLAN_SCHEMA)
    entries = inventory.discover()

    if not os.path.isdir(PLAN_DIR):
        print("no plans directory at %s" % os.path.relpath(PLAN_DIR, repo_path()))
        return 1

    plans = sorted(name for name in os.listdir(PLAN_DIR) if name.endswith(".dryrun.json"))
    if not plans:
        print("no dry-run plans found; expected at least the two blocked candidates")
        return 1

    results = []
    for name in plans:
        results.extend(validate_plan(os.path.join(PLAN_DIR, name), entries, schema, contract_schema))
    results.extend(scan_content_safety())

    failed = [item for item in results if not item["passed"]]

    if args.json:
        print(json.dumps({"checks": results, "total": len(results), "failed": len(failed)}, indent=2))
    else:
        for item in failed:
            print("FAIL %s\n     %s" % (item["check"], item["detail"]))
        print("%d of %d plan checks passed across %d plans" % (len(results) - len(failed), len(results), len(plans)))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
