#!/usr/bin/env python3
"""Unit tests for the I3 Step 2 publication tooling.

    python3 testing/publication/test_publication.py
    python3 testing/publication/test_publication.py -v

Standard library `unittest` only, matching every other suite in this repository.

The tests that matter most are the ones that would be easy to write as comments instead:

  * `SideEffectTests` runs real plan generation inside `pubkit.safety.no_side_effects`, which
    refuses a socket, a subprocess or a write outside the staging directory. "The dry-run path
    cannot upload" is asserted by executing it under instrumentation, not by inspection.
  * `ByteIdentityTests` hashes every frozen artifact before and after a full generation run.
  * `DeterminismTests` generates each plan twice and requires byte-identical output.
  * `StateCollapseTests` walks every forbidden implication one at a time.
  * `NoAuthorizationTests` asserts the outcome this whole step exists to preserve: nothing is
    published, active, approved, eligible or authorized, in the plans, in the fixtures, in the
    receipts and in the register.
"""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from pubkit import contract, eligibility, inventory, keys, lifecycle, origin, pin, rollback  # noqa: E402
from pubkit.governance import DecisionRegister, GovernanceClaim, validate_record  # noqa: E402
from pubkit.integrity import measure, sha256_of_bytes, verify_bytes  # noqa: E402
from pubkit.manifest import validate_against_vendored_schema, validate_manifest  # noqa: E402
from pubkit.plan import PLAN_EVALUATION_DATE, PLAN_EVALUATION_INSTANT, build_plan  # noqa: E402
from pubkit.reasons import ALL_REASON_CODES, BACKEND_REASON_CODES, KB_REASON_CODES, reason  # noqa: E402
from pubkit.safety import SideEffectAttempted, imported_cloud_sdks, no_side_effects  # noqa: E402
from pubkit.staging import DEFAULT_STAGING_ROOT, StagingArea, StagingEscape  # noqa: E402
from vocab.artifact_io import load_json  # noqa: E402
from vocab.schema_check import ANNOTATION_ONLY_KEYWORDS, UnsupportedKeyword  # noqa: E402
from vocab.schema_check import _SUPPORTED as _SUPPORTED_KEYWORDS  # noqa: E402
from vocab.schema_check import validate as schema_validate  # noqa: E402


def repo(*parts):
    return os.path.join(ROOT, *parts)


PLAN_PATHS = (
    "publication/plans/token_dictionary.ng.v2.0.dryrun.json",
    "publication/plans/question_flow.ng.v1.1.dryrun.json",
)


def load_plans():
    return [load_json(repo(*path.split("/"))) for path in PLAN_PATHS]


def build_plans_in_memory(staging_root=None):
    """Generate both plans without writing them, for determinism and side-effect tests."""
    contract_pin, contract_schema = pin.load_pinned_contract()
    entries = inventory.discover()
    register = DecisionRegister.from_file(
        repo("publication", "governance", "decision_register_v1.json")
    )
    built = []
    for artifact_id, version in (("token_dictionary", "2.0"), ("question_flow", "1.1")):
        entry = inventory.find(entries, artifact_id, version)
        plan, _reasons = build_plan(
            artifact_id,
            version,
            entry,
            register,
            contract_pin,
            contract_schema,
            entries,
            staging_root=staging_root,
        )
        built.append(plan)
    return built


# ---------------------------------------------------------------------------------------------


class SchemaValidatorHardeningTests(unittest.TestCase):
    """`schema_check.validate(extra_keywords=...)` exists for this step, so it is proved here.

    The property that matters is narrow and absolute: the parameter may widen which keywords
    are *tolerated*, and may never widen which instances are *accepted*. An unrestricted
    version would let a caller name `multipleOf` or `contains` — real assertions this validator
    does not implement — and silently drop the constraint while reporting success.
    """

    def test_the_allowlist_is_closed_and_minimal(self):
        self.assertEqual(ANNOTATION_ONLY_KEYWORDS, frozenset(["definitions", "contract_version"]))

    def test_an_unlisted_keyword_is_refused_even_when_asked_for(self):
        for keyword in ("multipleOf", "contains", "dependentRequired", "if", "unevaluatedProperties"):
            with self.assertRaises(UnsupportedKeyword, msg=keyword):
                schema_validate(1, {"type": "integer"}, extra_keywords=frozenset([keyword]))

    def test_a_supported_assertion_cannot_be_switched_off_through_the_parameter(self):
        # Naming a supported keyword is refused outright; and even the assertions themselves are
        # driven by `if "<keyword>" in schema`, never by the allowlist, so there is no path.
        for keyword in ("required", "enum", "pattern", "minimum", "type"):
            with self.assertRaises(UnsupportedKeyword, msg=keyword):
                schema_validate({}, {"type": "object", "required": ["a"]},
                                extra_keywords=frozenset([keyword]))
        self.assertEqual(
            len(schema_validate({}, {"type": "object", "required": ["a"]},
                                extra_keywords=ANNOTATION_ONLY_KEYWORDS)),
            1,
        )

    def test_an_unimplemented_assertion_still_raises_under_the_allowed_set(self):
        with self.assertRaises(UnsupportedKeyword):
            schema_validate(
                7, {"type": "integer", "multipleOf": 5}, extra_keywords=ANNOTATION_ONLY_KEYWORDS
            )

    def test_the_allowed_keywords_change_no_validation_outcome(self):
        """Adversarial content under each allowed keyword must not move a single error."""
        schema = {
            "type": "object",
            "required": ["a"],
            "additionalProperties": False,
            "properties": {"a": {"type": "integer", "minimum": 3}},
        }
        instances = [{}, {"a": 1}, {"a": 5}, {"a": 5, "b": 1}, {"a": "x"}]
        baseline = [schema_validate(i, schema) for i in instances]

        for keyword in sorted(ANNOTATION_ONLY_KEYWORDS):
            noisy = dict(schema)
            # Content deliberately shaped like a constraint, to prove it is not read as one.
            noisy[keyword] = {"a": {"type": "string", "minimum": 999}, "required": ["zzz"]}
            widened = [
                schema_validate(i, noisy, extra_keywords=ANNOTATION_ONLY_KEYWORDS)
                for i in instances
            ]
            self.assertEqual(widened, baseline, keyword)

    def test_refs_into_definitions_are_still_applied_in_full(self):
        # Tolerating `definitions` must not turn it into a place constraints go to die.
        schema = {
            "definitions": {"positive": {"type": "integer", "minimum": 1}},
            "type": "object",
            "properties": {"n": {"$ref": "#/definitions/positive"}},
        }
        self.assertEqual(
            schema_validate({"n": 5}, schema, extra_keywords=ANNOTATION_ONLY_KEYWORDS), []
        )
        self.assertEqual(
            len(schema_validate({"n": 0}, schema, extra_keywords=ANNOTATION_ONLY_KEYWORDS)), 1
        )
        self.assertEqual(
            len(schema_validate({"n": "x"}, schema, extra_keywords=ANNOTATION_ONLY_KEYWORDS)), 1
        )

    def test_the_vendored_contract_needs_exactly_the_allowed_set(self):
        _pin_record, schema = pin.load_pinned_contract()
        unknown = set(schema) - _SUPPORTED_KEYWORDS
        self.assertEqual(unknown, set(ANNOTATION_ONLY_KEYWORDS))


class ContractPinTests(unittest.TestCase):
    def test_pin_verifies(self):
        self.assertEqual(pin.check_pin(), [])

    def test_vendored_schema_matches_the_pinned_digest(self):
        pin_record, _schema = pin.load_pinned_contract()
        self.assertEqual(
            pin_record["vendored"]["sha256"],
            "66fa3a94f17c2765eb1eca29208d2494c4c1b7be57eae61856bdb34761082ce9",
        )
        self.assertEqual(
            pin_record["backend"]["merge_commit"], "fc40ac3e7d59cfed8e2584b78136c9704f7ab8cd"
        )

    def test_mirror_matches_the_schema(self):
        _pin_record, schema = pin.load_pinned_contract()
        descriptor = schema["definitions"]["artifact_descriptor"]
        self.assertEqual(set(descriptor["required"]), set(contract.REQUIRED_DESCRIPTOR_KEYS))
        self.assertEqual(
            set(descriptor["properties"]), set(contract.ALLOWED_DESCRIPTOR_KEYS)
        )

    def test_unsupported_major_is_refused(self):
        wrapper = {
            "manifest_version": "2.0.0",
            "generated_at": PLAN_EVALUATION_INSTANT,
            "artifacts": [],
        }
        valid, reasons = validate_manifest(wrapper)
        self.assertFalse(valid)
        self.assertIn("MANIFEST_VERSION_UNSUPPORTED", [item["code"] for item in reasons])


class ReasonCodeTests(unittest.TestCase):
    def test_namespaces_are_disjoint(self):
        self.assertEqual(set(BACKEND_REASON_CODES) & set(KB_REASON_CODES), set())

    def test_backend_codes_are_verbatim(self):
        # A code the Backend does not have would be meaningless to it; one it has that we lack
        # would be a rejection we cannot report. Both are drift.
        self.assertEqual(len(BACKEND_REASON_CODES), 32)
        self.assertIn("DOWNGRADE_NOT_AUTHORIZED", BACKEND_REASON_CODES)

    def test_unknown_code_raises(self):
        with self.assertRaises(Exception):
            reason("NOT_A_REAL_CODE", "x", "y")

    def test_kb_codes_never_appear_in_a_descriptor(self):
        for plan in load_plans():
            text = json.dumps(plan["descriptor"])
            for code in KB_REASON_CODES:
                self.assertNotIn(code, text)


class IntegrityTests(unittest.TestCase):
    def test_digest_is_computed_from_exact_bytes(self):
        data = b'{"a": 1}'
        self.assertEqual(
            sha256_of_bytes(data),
            "sha256:" + __import__("hashlib").sha256(data).hexdigest(),
        )

    def test_hash_mismatch_is_reported(self):
        reasons = verify_bytes(b"abc", "sha256:" + "0" * 64, 3, "x")
        self.assertEqual([item["code"] for item in reasons], ["HASH_MISMATCH"])

    def test_byte_count_mismatch_is_reported(self):
        data = b"abc"
        reasons = verify_bytes(data, sha256_of_bytes(data), 4, "x")
        self.assertEqual([item["code"] for item in reasons], ["BYTE_COUNT_MISMATCH"])

    def test_both_mismatches_are_reported_together(self):
        codes = [item["code"] for item in verify_bytes(b"abc", "sha256:" + "0" * 64, 9, "x")]
        self.assertEqual(codes, ["HASH_MISMATCH", "BYTE_COUNT_MISMATCH"])


class ObjectKeyTests(unittest.TestCase):
    def test_real_artifact_keys_are_accepted(self):
        for key in (
            "kb.ng.v2.4.json",
            "rules.ng.v2.2.json",
            "token_dictionary.ng.v1.1.json",
            "token_dictionary.ng.v2.0.json",
            "question_flow.ng.v1.1.json",
            "facilities.ng.v1.1.json",
        ):
            self.assertEqual(origin.validate_object_key(key, "k"), [], key)

    def test_clinical_vocabulary_is_not_mistaken_for_a_credential(self):
        # "token" means a symptom token here, and token_dictionary is a published artifact.
        self.assertEqual(origin.validate_object_key("token_dictionary.ng.v1.1.json", "k"), [])
        self.assertEqual(origin.validate_object_key("secretion_notes.ng.v1.0.json", "k"), [])

    def test_unsafe_keys_are_refused_by_name(self):
        expectations = {
            "latest.json": "KB_KEY_MUTABLE_ALIAS",
            "kb.ng.vlatest.json": "KB_KEY_MUTABLE_ALIAS",
            "../kb.ng.v1.0.json": "KB_KEY_PATH_TRAVERSAL",
            "/kb.ng.v1.0.json": "KB_KEY_ABSOLUTE_PATH",
            "kb.ng.v1.0.json?X-Amz-Signature=x": "KB_KEY_EMBEDS_SECRET",
            "kb.secret.ng.v1.0.json": "KB_KEY_EMBEDS_SECRET",
            "kb ng v1.0.json": "KB_KEY_UNSAFE_CHARACTER",
            "kḃ.ng.v1.0.json": "KB_KEY_AMBIGUOUS_NORMALIZATION",
        }
        for key, expected in expectations.items():
            codes = [item["code"] for item in origin.validate_object_key(key, "k")]
            self.assertIn(expected, codes, "%s -> %s" % (key, codes))

    def test_key_must_encode_its_identity(self):
        codes = [
            item["code"]
            for item in keys.check_key_agrees_with_identity(
                "question_flow.ng.v1.0.json", "question_flow", "1.1", "ng", "k"
            )
        ]
        self.assertIn("KB_KEY_VERSION_DISAGREEMENT", codes)

    def test_rebinding_a_key_to_different_bytes_is_an_overwrite(self):
        register = keys.IdentityRegister()
        register.register("kb.ng.v2.4.json", "kb", "2.4", "sha256:" + "a" * 64, "p")
        codes = [
            item["code"]
            for item in register.register("kb.ng.v2.4.json", "kb", "2.4", "sha256:" + "b" * 64, "p")
        ]
        self.assertIn("KB_KEY_OVERWRITE_DIFFERENT_BYTES", codes)

    def test_two_identities_cannot_share_a_key(self):
        register = keys.IdentityRegister()
        digest = "sha256:" + "c" * 64
        register.register("kb.ng.v2.4.json", "kb", "2.4", digest, "p")
        codes = [
            item["code"]
            for item in register.register("kb.ng.v2.4.json", "kb", "2.5", digest, "p")
        ]
        self.assertIn("KB_KEY_IDENTITY_COLLISION", codes)

    def test_arbitrary_origins_and_secrets_in_urls_are_refused(self):
        cases = {
            "https://cdn.example.com/kb.ng.v2.4.json": "ORIGIN_NOT_APPROVED",
            "http://pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev/kb.ng.v2.4.json": "ORIGIN_NOT_HTTPS",
            "https://u:p@pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev/kb.ng.v2.4.json": "ORIGIN_HAS_CREDENTIALS",
            "https://pub-8bc2ba0d7e7647799d89662d70f23c45.r2.dev/kb.ng.v2.4.json?t=1": "ORIGIN_HAS_QUERY",
        }
        for url, expected in cases.items():
            codes = [item["code"] for item in origin.validate_artifact_url(url, "kb.ng.v2.4.json", "u")]
            self.assertIn(expected, codes, url)


class StateCollapseTests(unittest.TestCase):
    def base(self):
        states = {state: False for state in lifecycle.LIFECYCLE_STATES}
        states.update(generated=True, validated=True, packaged=True, present=True)
        return states

    def test_kb_observable_states_are_accepted(self):
        states, reasons = lifecycle.state_of(self.base())
        self.assertEqual(reasons, [])
        self.assertTrue(states["generated"])

    def test_no_externally_established_state_may_be_asserted(self):
        for state in lifecycle.EXTERNALLY_ESTABLISHED_STATES:
            observations = self.base()
            observations[state] = True
            _states, reasons = lifecycle.state_of(observations)
            self.assertIn("KB_STATE_COLLAPSE", [item["code"] for item in reasons], state)

    def test_an_unobserved_state_is_not_a_false_state(self):
        for state in lifecycle.LIFECYCLE_STATES:
            observations = self.base()
            del observations[state]
            _states, reasons = lifecycle.state_of(observations)
            self.assertIn("KB_STATE_COLLAPSE", [item["code"] for item in reasons], state)

    def test_unknown_governance_values_fail_closed(self):
        for value in (None, "yes", 1, [], {}):
            observations = self.base()
            observations["approved"] = value
            _states, reasons = lifecycle.state_of(observations)
            self.assertIn("KB_STATE_COLLAPSE", [item["code"] for item in reasons], repr(value))

    def test_the_state_set_is_closed(self):
        observations = self.base()
        observations["merged_pr"] = True
        _states, reasons = lifecycle.state_of(observations)
        self.assertIn("KB_STATE_COLLAPSE", [item["code"] for item in reasons])

    def test_every_forbidden_implication_is_documented(self):
        for earlier, later, why in lifecycle.FORBIDDEN_IMPLICATIONS:
            self.assertIn(earlier, lifecycle.LIFECYCLE_STATES)
            self.assertIn(later, lifecycle.LIFECYCLE_STATES)
            self.assertTrue(why.strip())


class EligibilityTests(unittest.TestCase):
    def descriptor(self, **overrides):
        base = {
            "artifact_id": "fixture_artifact",
            "artifact_version": "1.1",
            "schema_version": "wellapath.artifact/1",
            "content_type": "application/json",
            "sha256": "sha256:" + "d" * 64,
            "byte_count": 10,
            "object_key": "fixture_artifact.ng.v1.1.json",
            "release_status": "published",
            "activation_status": "active",
            "activation_authorized": True,
            "activation_decision_ref": "FIXTURE",
            "target_environments": ["staging"],
            "publication_decision_ref": "FIXTURE",
            "approvals": {
                "product": {"required": True, "status": "granted", "decision_ref": "P", "approved_at": None},
                "clinical": {"required": True, "status": "granted", "decision_ref": "C", "approved_at": None},
            },
            "blockers": [],
            "predecessor": None,
            "rollback_target": None,
            "created_at": "2026-08-01T00:00:00Z",
            "published_at": "2026-08-01T00:00:00Z",
            "deprecated": False,
            "expires_at": None,
            "country": "ng",
        }
        base.update(overrides)
        return base

    def evaluate(self, descriptor, environment="staging", app_build=100):
        return eligibility.evaluate_descriptor(
            descriptor, environment, app_build=app_build, now=PLAN_EVALUATION_INSTANT
        )

    def test_a_fully_governed_descriptor_is_eligible(self):
        states, reasons = self.evaluate(self.descriptor())
        self.assertTrue(states["eligible_for_environment"], reasons)

    def test_published_does_not_mean_approved(self):
        states, _ = self.evaluate(
            self.descriptor(
                approvals={
                    "product": {"required": True, "status": "granted", "decision_ref": "P", "approved_at": None},
                    "clinical": {"required": True, "status": "pending", "decision_ref": None, "approved_at": None},
                }
            )
        )
        self.assertTrue(states["published"])
        self.assertFalse(states["approved"])
        self.assertFalse(states["eligible_for_environment"])

    def test_product_cannot_substitute_for_clinical(self):
        states, reasons = self.evaluate(
            self.descriptor(
                approvals={
                    "product": {"required": True, "status": "granted", "decision_ref": "P", "approved_at": None},
                    "clinical": {"required": True, "status": "pending", "decision_ref": None, "approved_at": None},
                }
            )
        )
        self.assertFalse(states["approved"])
        self.assertIn("APPROVAL_NOT_GRANTED", [item["code"] for item in reasons])

    def test_approved_does_not_mean_active(self):
        states, _ = self.evaluate(self.descriptor(activation_status="inactive"))
        self.assertTrue(states["approved"])
        self.assertFalse(states["active"])

    def test_active_does_not_mean_eligible(self):
        states, _ = self.evaluate(self.descriptor(), environment="production")
        self.assertTrue(states["active"])
        self.assertFalse(states["eligible_for_environment"])

    def test_an_open_blocker_denies_eligibility(self):
        states, reasons = self.evaluate(
            self.descriptor(blockers=[{"id": "IM003-SB-001", "status": "open"}])
        )
        self.assertFalse(states["eligible_for_environment"])
        self.assertIn("BLOCKER_UNRESOLVED", [item["code"] for item in reasons])

    def test_unknown_approval_status_is_never_coerced(self):
        states, reasons = self.evaluate(
            self.descriptor(
                approvals={
                    "product": {"required": True, "status": "auto", "decision_ref": "P", "approved_at": None},
                    "clinical": {"required": True, "status": "granted", "decision_ref": "C", "approved_at": None},
                }
            )
        )
        self.assertFalse(states["approved"])
        self.assertIn("APPROVAL_STATUS_UNKNOWN", [item["code"] for item in reasons])

    def test_eligibility_refuses_to_read_a_clock(self):
        # A dry run that depended on wall-clock time could not be reproducible, and an expiry
        # check that silently used "now" would give different answers on different days.
        with self.assertRaises(ValueError):
            eligibility.evaluate_descriptor(self.descriptor(), "staging", now=None)

    def test_a_candidate_is_never_selected_implicitly(self):
        manifest = {
            "artifacts": [
                self.descriptor(
                    release_status="candidate",
                    published_at=None,
                    activation_status="inactive",
                    activation_authorized=False,
                    activation_decision_ref=None,
                )
            ]
        }
        selected, reasons = eligibility.select_active_descriptor(
            manifest, "fixture_artifact", "staging", app_build=100, now=PLAN_EVALUATION_INSTANT
        )
        self.assertIsNone(selected)
        self.assertIn("NO_ACTIVE_ARTIFACT", [item["code"] for item in reasons])

    def test_a_downgrade_needs_a_hash_bound_rollback_target(self):
        current = self.descriptor(artifact_version="2.0", sha256="sha256:" + "e" * 64)
        proposed = self.descriptor(artifact_version="1.1")
        codes = [item["code"] for item in eligibility.authorize_transition(current, proposed)]
        self.assertEqual(codes, ["DOWNGRADE_NOT_AUTHORIZED"])

        current["rollback_target"] = {"artifact_version": "1.1", "sha256": proposed["sha256"]}
        self.assertEqual(eligibility.authorize_transition(current, proposed), [])


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.register = DecisionRegister.from_file(
            repo("publication", "governance", "decision_register_v1.json")
        )
        self.entries = inventory.discover()
        self.question_flow = inventory.find(self.entries, "question_flow", "1.1")

    def resolve(self, kind, artifact_id="question_flow", version="1.1", digest=None):
        return self.register.resolve(
            GovernanceClaim(kind, artifact_id, version, digest or self.question_flow["descriptor_sha256"]),
            PLAN_EVALUATION_DATE,
        )

    def test_every_register_record_is_usable(self):
        self.assertEqual(self.register.invalid, [])
        self.assertGreaterEqual(len(self.register.records), 3)

    def test_nothing_is_granted_for_any_artifact(self):
        for artifact_id, version in (("question_flow", "1.1"), ("token_dictionary", "2.0")):
            entry = inventory.find(self.entries, artifact_id, version)
            for kind in (
                "product_approval",
                "clinical_approval",
                "publication_authorization",
                "activation_authorization",
                "mobile_implementation_authorization",
            ):
                granted, ref, reasons = self.resolve(
                    kind, artifact_id, version, entry["descriptor_sha256"]
                )
                self.assertFalse(granted, "%s %s@%s" % (kind, artifact_id, version))
                self.assertIsNone(ref)
                self.assertTrue(reasons)

    def test_im_001_resolved_is_not_an_authorization(self):
        for kind in ("publication_authorization", "activation_authorization"):
            _granted, _ref, reasons = self.resolve(kind)
            self.assertIn(
                "KB_DECISION_SET_IS_NOT_AUTHORIZATION", [item["code"] for item in reasons], kind
            )

    def test_product_authority_cannot_satisfy_a_clinical_claim(self):
        _granted, _ref, reasons = self.resolve("clinical_approval")
        self.assertIn("KB_DECISION_AUTHORITY_WRONG", [item["code"] for item in reasons])

    def test_no_clinical_record_exists_at_all(self):
        for record, _path in self.register.records:
            self.assertNotEqual(record["authority_type"], "clinical")

    def test_no_clinical_reviewer_is_assigned(self):
        document = load_json(repo("publication", "governance", "decision_register_v1.json"))
        state = document["governance_state"]["clinical_reviewer"]
        self.assertFalse(state["assigned"])
        self.assertIsNone(state["reviewer"])
        self.assertFalse(state["product_reviewer_is_qualified_clinical_reviewer"])

    def test_both_blockers_are_open(self):
        document = load_json(repo("publication", "governance", "decision_register_v1.json"))
        statuses = {blocker["id"]: blocker["status"] for blocker in document["blockers"]}
        self.assertEqual(statuses["IM001-CLIN-FLAG-001"], "open")
        self.assertEqual(statuses["IM003-SB-001"], "open")

    def test_a_prose_only_approval_resolves_to_nothing(self):
        record, _path = self.register.records[0]
        broken = json.loads(json.dumps(record))
        broken["decision_reference"] = {"path": "docs/SOMEONE_SAID_SO.md"}
        codes = [item["code"] for item in validate_record(broken, "r")]
        self.assertIn("KB_DECISION_PROSE_ONLY", codes)

    def test_an_approval_for_other_bytes_does_not_carry_across(self):
        _granted, _ref, reasons = self.resolve("product_approval", digest="sha256:" + "f" * 64)
        self.assertIn("KB_DECISION_HASH_MISMATCH", [item["code"] for item in reasons])


class RollbackTests(unittest.TestCase):
    def setUp(self):
        self.entries = inventory.discover()

    def test_a_version_only_target_is_unbound(self):
        codes = [
            item["code"]
            for item in rollback.check_rollback_target(
                {"artifact_version": "1.0"}, "question_flow", "1.1", "1.1", self.entries
            )
        ]
        self.assertEqual(codes, ["KB_ROLLBACK_UNBOUND_VERSION_ONLY"])

    def test_a_target_outside_the_inventory_is_refused(self):
        codes = [
            item["code"]
            for item in rollback.check_rollback_target(
                {"artifact_version": "0.9", "sha256": "sha256:" + "1" * 64},
                "question_flow",
                "1.1",
                "1.1",
                self.entries,
            )
        ]
        self.assertIn("KB_ROLLBACK_TARGET_NOT_IN_INVENTORY", codes)

    def test_a_cross_artifact_target_is_refused(self):
        codes = [
            item["code"]
            for item in rollback.check_rollback_target(
                {
                    "artifact_id": "token_dictionary",
                    "artifact_version": "1.0",
                    "sha256": "sha256:" + "2" * 64,
                },
                "question_flow",
                "1.1",
                "1.1",
                self.entries,
            )
        ]
        self.assertIn("KB_ROLLBACK_CROSS_ARTIFACT", codes)

    def test_no_rollback_is_proposed_for_a_first_version(self):
        self.assertIsNone(rollback.propose_predecessor(self.entries, "kb", "1.0"))

    def test_both_candidate_rollbacks_cross_a_schema_boundary(self):
        # A real finding, not a synthetic one: token_dictionary 2.0 declares content schema 2.0
        # while 1.1 declares 1.0, and question_flow 1.1 declares 1.1 while 1.0 declares 1.0.
        for artifact_id, version, schema_version in (
            ("token_dictionary", "2.0", "2.0"),
            ("question_flow", "1.1", "1.1"),
        ):
            target = rollback.propose_predecessor(self.entries, artifact_id, version)
            codes = [
                item["code"]
                for item in rollback.check_rollback_target(
                    target, artifact_id, version, schema_version, self.entries
                )
            ]
            self.assertIn("KB_ROLLBACK_SCHEMA_INCOMPATIBLE", codes, artifact_id)


class StagingTests(unittest.TestCase):
    def test_a_traversal_write_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with StagingArea(root=directory, name="p") as staging:
                with self.assertRaises(StagingEscape):
                    staging.write("../escaped.json", b"x")
                with self.assertRaises(StagingEscape):
                    staging.write("/tmp/escaped.json", b"x")

    def test_the_staging_area_is_removed_on_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            with StagingArea(root=directory, name="p") as staging:
                staging.write("a.json", b"x")
                path = staging.path
                self.assertTrue(os.path.isdir(path))
            self.assertFalse(os.path.exists(path))

    def test_the_staging_area_is_removed_even_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = None
            try:
                with StagingArea(root=directory, name="p") as staging:
                    path = staging.path
                    raise RuntimeError("boom")
            except RuntimeError:
                pass
            self.assertFalse(os.path.exists(path))

    def test_the_staging_root_is_git_ignored(self):
        with open(repo(".gitignore"), encoding="utf-8") as handle:
            self.assertIn(".publication-staging/", handle.read())
        self.assertTrue(DEFAULT_STAGING_ROOT.endswith(".publication-staging"))


class SideEffectTests(unittest.TestCase):
    """The dry-run path executed under instrumentation, not merely inspected."""

    def test_no_cloud_sdk_is_importable_into_this_run(self):
        self.assertEqual(imported_cloud_sdks(), [])

    def test_plan_generation_attempts_no_network_subprocess_or_stray_write(self):
        with tempfile.TemporaryDirectory() as staging_root:
            with no_side_effects(allowed_write_roots=(staging_root,), raise_on_attempt=True) as recorder:
                plans = build_plans_in_memory(staging_root=staging_root)
            self.assertEqual(recorder.attempts, [])
        self.assertEqual(len(plans), 2)

    def test_the_guard_itself_catches_a_socket(self):
        import socket

        with no_side_effects(raise_on_attempt=False) as recorder:
            with self.assertRaises(SideEffectAttempted):
                socket.create_connection(("example.invalid", 443))
        self.assertEqual([item["code"] for item in recorder.attempts], ["KB_NETWORK_ATTEMPTED"])

    def test_the_guard_itself_catches_a_subprocess(self):
        import subprocess

        with no_side_effects(raise_on_attempt=False) as recorder:
            with self.assertRaises(SideEffectAttempted):
                subprocess.Popen(["rclone", "copy", "kb.ng.v2.4.json", "r2:bucket"])
        self.assertEqual([item["code"] for item in recorder.attempts], ["KB_SUBPROCESS_ATTEMPTED"])

    def test_the_guard_itself_catches_a_write_outside_the_permitted_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            with no_side_effects(raise_on_attempt=False) as recorder:
                with self.assertRaises(SideEffectAttempted):
                    open(os.path.join(directory, "x"), "w")
            self.assertEqual([item["code"] for item in recorder.attempts], ["KB_STAGING_ESCAPE"])

    def test_the_guard_restores_everything_it_patched(self):
        import socket
        import subprocess

        original = (socket.socket, socket.create_connection, subprocess.Popen, open)
        with no_side_effects():
            pass
        self.assertEqual((socket.socket, socket.create_connection, subprocess.Popen, open), original)


class ByteIdentityTests(unittest.TestCase):
    def frozen(self):
        return load_json(repo("reports", "publication_freeze_v1.json"))

    def test_every_frozen_artifact_matches_its_recorded_digest(self):
        report = self.frozen()
        for group in report["groups"].values():
            for item in group:
                _data, digest, byte_count = measure(repo(*item["path"].split("/")))
                self.assertEqual(digest, "sha256:%s" % item["sha256"], item["path"])
                self.assertEqual(byte_count, item["byte_count"], item["path"])

    def test_generating_plans_changes_no_frozen_byte(self):
        report = self.frozen()
        before = {
            item["path"]: measure(repo(*item["path"].split("/")))[1]
            for group in report["groups"].values()
            for item in group
        }
        with tempfile.TemporaryDirectory() as staging_root:
            build_plans_in_memory(staging_root=staging_root)
        after = {
            item["path"]: measure(repo(*item["path"].split("/")))[1]
            for group in report["groups"].values()
            for item in group
        }
        self.assertEqual(before, after)

    def test_the_known_frozen_hashes_are_the_ones_ci_already_asserts(self):
        report = self.frozen()
        digests = {
            item["path"]: item["sha256"] for group in report["groups"].values() for item in group
        }
        self.assertEqual(
            digests["kb.ng.v2.4.json"],
            "6c00d8257f8417e86bd5e237630bf8a4623ad72e2e46b1b071dd447c067cec2b",
        )
        self.assertEqual(
            digests["rules.ng.v2.2.json"],
            "1d27e854cba95b179577a88f92445400f494a7fe8e6a53a60fcaa98b3870d1c4",
        )
        self.assertEqual(
            digests["token_dictionary.ng.v1.1.json"],
            "0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019",
        )
        self.assertEqual(
            digests["facilities.ng.v1.1.json"],
            "25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398",
        )
        self.assertEqual(
            digests["testing/case_bank_v1.json"],
            "c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834",
        )


class DeterminismTests(unittest.TestCase):
    def test_two_runs_produce_identical_plans(self):
        with tempfile.TemporaryDirectory() as first_root:
            first = build_plans_in_memory(staging_root=first_root)
        with tempfile.TemporaryDirectory() as second_root:
            second = build_plans_in_memory(staging_root=second_root)
        self.assertEqual(
            json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True)
        )

    def test_the_staging_path_never_reaches_the_output(self):
        with tempfile.TemporaryDirectory() as staging_root:
            plans = build_plans_in_memory(staging_root=staging_root)
        for plan in plans:
            self.assertNotIn(staging_root, json.dumps(plan))
            self.assertFalse(plan["packaging"]["staging_path_recorded"])

    def test_the_committed_plans_match_a_fresh_generation(self):
        with tempfile.TemporaryDirectory() as staging_root:
            fresh = build_plans_in_memory(staging_root=staging_root)
        for generated, committed in zip(fresh, load_plans()):
            self.assertEqual(
                json.dumps(generated, sort_keys=True), json.dumps(committed, sort_keys=True)
            )

    def test_the_evaluation_instant_is_a_constant_not_a_clock(self):
        for plan in load_plans():
            self.assertEqual(plan["_metadata"]["evaluated_at"], PLAN_EVALUATION_INSTANT)


class NoAuthorizationTests(unittest.TestCase):
    """The outcome this whole step exists to preserve."""

    def test_no_plan_reports_an_operation(self):
        for plan in load_plans():
            for flag in (
                "upload_performed",
                "publication_performed",
                "activation_performed",
                "deployment_performed",
                "storage_write_performed",
                "network_access_performed",
                "canonical_bytes_modified",
            ):
                self.assertIs(plan["operations_performed"][flag], False, flag)

    def test_no_plan_is_eligible_in_any_environment(self):
        for plan in load_plans():
            self.assertIs(plan["eligible_for_environment"], False)
            self.assertIs(plan["eligible_in_any_environment"], False)
            for environment in ("development", "staging", "production"):
                self.assertIs(
                    plan["eligibility_by_environment"][environment]["eligible_for_environment"],
                    False,
                    environment,
                )

    def test_no_descriptor_is_published_active_or_authorized(self):
        for plan in load_plans():
            descriptor = plan["descriptor"]
            self.assertIn(descriptor["release_status"], ("draft", "candidate"))
            self.assertEqual(descriptor["activation_status"], "inactive")
            self.assertIs(descriptor["activation_authorized"], False)
            self.assertIsNone(descriptor["activation_decision_ref"])
            self.assertIsNone(descriptor["published_at"])
            self.assertIsNone(descriptor["publication_decision_ref"])
            for role in ("product", "clinical"):
                self.assertNotEqual(descriptor["approvals"][role]["status"], "granted", role)
                self.assertIsNone(descriptor["approvals"][role]["decision_ref"], role)

    def test_question_flow_carries_both_open_blockers(self):
        plan = load_plans()[1]
        self.assertEqual(plan["target"]["artifact_id"], "question_flow")
        statuses = {item["id"]: item["status"] for item in plan["descriptor"]["blockers"]}
        # The OPEN set is exactly the two safety blockers. The list also carries completed
        # gates as resolved entries, which is how a passed gate is recorded without any risk of
        # it reading as an approval — but nothing resolved may creep into the open set.
        self.assertEqual(
            {k for k, v in statuses.items() if v == "open"},
            {"IM001-CLIN-FLAG-001", "IM003-SB-001"},
        )
        self.assertEqual(statuses["IM001-PRODUCT-DISPLAY-DECISIONS"], "resolved")

    def test_vocabulary_2_0_invents_no_missing_decision(self):
        plan = load_plans()[0]
        self.assertEqual(plan["target"]["artifact_id"], "token_dictionary")
        self.assertEqual(plan["target"]["artifact_version"], "2.0")
        for claim in plan["governance"]["claims"]:
            self.assertIs(claim["granted"], False)
            self.assertIn(
                "KB_DECISION_RECORD_MISSING", [item["code"] for item in claim["reasons"]], claim["kind"]
            )

    def test_no_receipt_example_is_operative(self):
        directory = repo("publication", "receipts")
        names = sorted(name for name in os.listdir(directory) if name.endswith(".json"))
        self.assertEqual(len(names), 4)
        for name in names:
            receipt = load_json(os.path.join(directory, name))
            self.assertIs(receipt["operative"], False, name)
            self.assertIn("DRY-RUN EXAMPLE", receipt["non_operative_declaration"], name)
            self.assertIsNone(receipt["occurred_at"], name)
            self.assertIs(receipt["signing"]["signed"], False, name)
            self.assertIsNone(receipt["signing"]["mechanism"], name)
            self.assertTrue(receipt["signing"]["gap"].strip(), name)
            performed = [key for key in receipt if key.endswith("_performed")]
            for key in performed:
                self.assertIs(receipt[key], False, "%s %s" % (name, key))

    def test_no_receipt_forges_a_successful_operation(self):
        directory = repo("publication", "receipts")
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            receipt = load_json(os.path.join(directory, name))
            if "decision" in receipt:
                self.assertEqual(receipt["decision"], "refused", name)

    def test_the_blocked_candidate_fixture_matches_the_plans(self):
        fixture = load_json(
            repo("publication", "fixtures", "compat", "kb_blocked_candidates.manifest.json")
        )
        descriptors = {item["artifact_id"]: item for item in fixture["artifacts"]}
        for plan in load_plans():
            self.assertEqual(descriptors[plan["target"]["artifact_id"]], plan["descriptor"])

    def test_the_candidate_is_not_at_the_repository_root(self):
        # The root is the directory published artifacts are uploaded from. This tooling must
        # not have moved a candidate there, and does not.
        self.assertFalse(os.path.exists(repo("token_dictionary.ng.v2.0.json")))
        self.assertFalse(os.path.exists(repo("question_flow.ng.v1.1.json")))

    def test_no_generated_file_carries_a_credential(self):
        patterns = ("AKIA", "X-Amz-Signature", "aws_secret_access_key", "ghp_", "BEGIN PRIVATE KEY")
        roots = (repo("publication"), repo("contracts"))
        for root in roots:
            for directory, _subdirectories, names in os.walk(root):
                for name in names:
                    path = os.path.join(directory, name)
                    with open(path, encoding="utf-8", errors="replace") as handle:
                        text = handle.read()
                    for pattern in patterns:
                        # The fixtures name X-Amz-Signature in a *rejection* case, which is the
                        # opposite of leaking one; exclude only that file, by name.
                        if name in ("negative_fixtures.compat.json", "kb_stage_fixtures_v1.json"):
                            continue
                        self.assertNotIn(pattern, text, "%s in %s" % (pattern, path))


def _count_tests():
    """How many tests this module defines, counted rather than remembered.

    The documentation states this number, and a number kept by hand in prose drifts the moment
    a test is added — usually silently, because nothing recomputes it.
    """
    module = sys.modules[__name__]
    total = 0
    for name in dir(module):
        attribute = getattr(module, name)
        if isinstance(attribute, type) and issubclass(attribute, unittest.TestCase):
            total += sum(1 for item in dir(attribute) if item.startswith("test_"))
    return total


class DocumentationTests(unittest.TestCase):
    """Documentation states hashes and counts. Those are claims, so they are checked.

    A digest transcribed into prose is exactly the kind of thing that goes stale silently: it
    looks authoritative, nothing recomputes it, and a single wrong character makes a handoff
    document point at bytes that do not exist.
    """

    DOCS = (
        "docs/PUBLICATION_LIFECYCLE.md",
        "backend_handoff/publication_tooling_v1/README.md",
        "publication/README.md",
    )

    def documents(self):
        for relative in self.DOCS:
            path = repo(*relative.split("/"))
            if os.path.exists(path):
                with open(path, encoding="utf-8") as handle:
                    yield relative, handle.read()

    def test_every_quoted_digest_belongs_to_something_real(self):
        import re

        entries = inventory.discover()
        pin_record, _schema = pin.load_pinned_contract()
        freeze = load_json(repo("reports", "publication_freeze_v1.json"))

        known = {entry["sha256"] for entry in entries}
        known |= {item["sha256"] for group in freeze["groups"].values() for item in group}
        known.add(pin_record["vendored"]["sha256"])
        known.add(pin_record["backend"]["handoff_sha256"])

        for relative, text in self.documents():
            for digest in set(re.findall(r"\b[0-9a-f]{64}\b", text)):
                self.assertIn(digest, known, "%s quotes unknown digest %s" % (relative, digest))

    def test_every_quoted_commit_is_a_pinned_commit(self):
        import re

        pin_record, _schema = pin.load_pinned_contract()
        known = {pin_record["backend"]["merge_commit"], "c1b07944ea0b231914943ac17b2265441e53b85c"}
        for relative, text in self.documents():
            for commit in set(re.findall(r"\b[0-9a-f]{40}\b", text)):
                self.assertIn(commit, known, "%s quotes unknown commit %s" % (relative, commit))

    #: `document -> {number that must appear: what it counts}`. Stated per document rather than
    #: swept across all of them: the handoff quotes the compat count (41) because that is the
    #: file it hands over, while the lifecycle doc quotes the total (99) because it tabulates
    #: every suite. A blanket rule would demand both numbers in both places.
    DOCUMENTED_COUNTS = {
        "docs/PUBLICATION_LIFECYCLE.md": (
            "total_fixtures",
            "frozen_artifacts",
            "mutation_proofs",
            "unit_tests",
        ),
        "backend_handoff/publication_tooling_v1/README.md": ("compat_fixtures",),
    }

    def counts(self):
        compat = load_json(
            repo("publication", "fixtures", "compat", "negative_fixtures.compat.json")
        )
        kb = load_json(repo("publication", "fixtures", "negative", "kb_stage_fixtures_v1.json"))
        freeze = load_json(repo("reports", "publication_freeze_v1.json"))
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from validate_publication_fixtures import MUTATION_PROOFS

        return {
            "compat_fixtures": len(compat["cases"]),
            "kb_fixtures": len(kb["cases"]),
            "total_fixtures": len(compat["cases"]) + len(kb["cases"]),
            "frozen_artifacts": freeze["frozen_artifact_count"],
            "mutation_proofs": len(MUTATION_PROOFS),
            "unit_tests": _count_tests(),
        }

    def test_the_counts_are_what_this_step_actually_built(self):
        counts = self.counts()
        self.assertEqual(counts["compat_fixtures"], 41)
        self.assertEqual(counts["kb_fixtures"], 60)
        self.assertEqual(counts["total_fixtures"], 101)
        self.assertEqual(counts["frozen_artifacts"], 44)
        self.assertEqual(counts["mutation_proofs"], 7)

    def test_every_documented_count_matches_reality(self):
        counts = self.counts()
        for relative, text in self.documents():
            for name in self.DOCUMENTED_COUNTS.get(relative, ()):
                # `assertIn` on a whole document would print the document on failure, which
                # buries the one fact the reader needs. Assert on a boolean instead.
                self.assertTrue(
                    str(counts[name]) in text,
                    "%s should state %s = %d" % (relative, name, counts[name]),
                )


class ApprovalScopeTests(unittest.TestCase):
    """The I3 Step 2A ruling: four distinct concepts, never substitutable for one another.

        product_display_decision                 complete, display wording and ordering only
        artifact_publication_product_approval    pending
        clinical_approval                        pending
        publication / activation authorization   false
    """

    RECONCILIATION = ("publication", "fixtures", "compat", "approval_scope_reconciliation_v1.json")

    def record(self):
        return load_json(repo(*self.RECONCILIATION))

    def question_flow_plan(self):
        return load_plans()[1]

    def test_the_four_concepts_are_represented_separately(self):
        scope = self.question_flow_plan()["governance"]["product_approval_scope"]
        self.assertEqual(scope["product_display_decision"]["status"], "complete")
        self.assertEqual(
            scope["product_display_decision"]["scope"], "display_wording_and_ordering_only"
        )
        self.assertEqual(scope["artifact_publication_product_approval"]["status"], "pending")
        self.assertEqual(scope["clinical_approval"]["status"], "pending")
        self.assertIs(scope["publication_authorization"]["granted"], False)
        self.assertIs(scope["activation_authorization"]["granted"], False)

    def test_the_display_decision_grants_nothing(self):
        display = self.question_flow_plan()["governance"]["product_approval_scope"][
            "product_display_decision"
        ]
        for field in (
            "grants_artifact_publication_product_approval",
            "grants_clinical_approval",
            "grants_publication_authorization",
            "grants_activation_authorization",
        ):
            self.assertIs(display[field], False, field)

    def test_each_concept_names_the_contract_field_that_carries_it(self):
        scope = self.question_flow_plan()["governance"]["product_approval_scope"]
        self.assertEqual(
            scope["artifact_publication_product_approval"]["contract_representation"],
            "approvals.product.status",
        )
        self.assertEqual(
            scope["clinical_approval"]["contract_representation"], "approvals.clinical.status"
        )
        self.assertIn("resolved", scope["product_display_decision"]["contract_representation"])

    def test_the_completed_gate_is_a_resolved_blocker_not_an_approval(self):
        descriptor = self.question_flow_plan()["descriptor"]
        gates = [b for b in descriptor["blockers"] if b["id"] == "IM001-PRODUCT-DISPLAY-DECISIONS"]
        self.assertEqual(len(gates), 1)
        self.assertEqual(gates[0]["status"], "resolved")
        self.assertIn("NOT AN APPROVAL", gates[0]["reference"])
        # And the approval field it must not be confused with is untouched.
        self.assertEqual(descriptor["approvals"]["product"]["status"], "pending")
        self.assertIsNone(descriptor["approvals"]["product"]["decision_ref"])

    def test_a_resolved_blocker_cannot_make_a_descriptor_approved(self):
        """The structural proof, run against the contract's own semantics.

        Adding resolved blockers — any number, saying anything — must not move `approved`.
        """
        descriptor = json.loads(json.dumps(self.question_flow_plan()["descriptor"]))
        descriptor["approvals"]["clinical"] = {
            "required": True, "status": "granted", "decision_ref": "X", "approved_at": None,
        }
        before, _ = eligibility.evaluate_descriptor(
            descriptor, "staging", now=PLAN_EVALUATION_INSTANT
        )
        descriptor["blockers"] = [
            {"id": "ANY-GATE-%d" % i, "status": "resolved", "reference": "product approved"}
            for i in range(5)
        ]
        after, _ = eligibility.evaluate_descriptor(
            descriptor, "staging", now=PLAN_EVALUATION_INSTANT
        )
        self.assertIs(before["approved"], False)
        self.assertIs(after["approved"], False)
        self.assertIs(after["eligible_for_environment"], False)

    def test_the_reconciliation_record_claims_all_hold(self):
        claims = self.record()["claims"]
        for name in (
            "im_001_display_decision_completion_remains_true",
            "artifact_publication_product_approval_remains_pending",
            "clinical_approval_remains_pending",
            "both_representations_are_ineligible_in_every_environment",
            "no_evaluator_can_substitute_completion_for_approval",
        ):
            self.assertIs(claims[name], True, name)

    def test_the_backend_encoding_is_recorded_as_a_defect(self):
        record = self.record()
        self.assertEqual(record["verdict"]["backend_granted_product_is"], "fixture_defect")
        self.assertIs(record["claims"]["backend_encoding_substitutes_completion_for_approval"], True)
        self.assertIs(record["verdict"]["blocking_this_merge"], False)

    def test_both_encodings_are_ineligible_as_shipped(self):
        compared = self.record()["encodings_compared"]
        for name, side in compared.items():
            for environment in ("development", "staging", "production"):
                self.assertIs(
                    side["as_shipped"][environment]["eligible_for_environment"], False,
                    "%s/%s" % (name, environment),
                )

    def test_the_kb_encoding_alone_survives_the_controlled_probe(self):
        compared = self.record()["encodings_compared"]
        kb = compared["knowledge_base"]["with_unrelated_conditions_lifted"]
        backend = compared["backend_fixture"]["with_unrelated_conditions_lifted"]
        for environment in ("development", "staging", "production"):
            self.assertIs(kb[environment]["approved"], False, environment)
            self.assertIs(kb[environment]["eligible_for_environment"], False, environment)
        self.assertIs(backend["staging"]["approved"], True)

    def test_the_kb_descriptor_still_validates_against_contract_1_0_0(self):
        _pin_record, schema = pin.load_pinned_contract()
        for plan in load_plans():
            wrapper = {
                "manifest_version": "1.0.0",
                "generated_at": PLAN_EVALUATION_INSTANT,
                "artifacts": [plan["descriptor"]],
            }
            valid, reasons = validate_manifest(wrapper)
            self.assertTrue(valid, reasons)
            self.assertEqual(validate_against_vendored_schema(wrapper, schema), [])


class RollbackPolicyGapTests(unittest.TestCase):
    """The cross-schema rollback refusals are correct fail-closed behaviour, and stay that way."""

    def test_both_plans_carry_a_null_rollback_target(self):
        for plan in load_plans():
            self.assertIsNone(plan["descriptor"]["rollback_target"])
            self.assertIsNone(plan["rollback"]["descriptor_rollback_target"])
            self.assertIs(plan["rollback"]["usable_as_rollback_target"], False)

    def test_no_version_only_or_inferred_rollback_is_emitted(self):
        for plan in load_plans():
            proposed = plan["rollback"]["proposed_target"]
            # A proposal exists (lineage is known) but it is never promoted into the descriptor,
            # and it is hash-bound even as a proposal — there is no version-only form anywhere.
            self.assertIsNotNone(proposed)
            self.assertIn("sha256", proposed)
            self.assertTrue(proposed["sha256"].startswith("sha256:"))
            self.assertIsNone(plan["descriptor"]["rollback_target"])

    def test_the_refusal_names_the_schema_boundary_gap(self):
        for plan in load_plans():
            codes = [r["code"] for r in plan["rollback"]["rejection_reasons"]]
            self.assertIn("KB_ROLLBACK_SCHEMA_INCOMPATIBLE", codes, plan["target"]["artifact_id"])
            detail = " ".join(r["detail"] for r in plan["rollback"]["rejection_reasons"])
            self.assertIn("content schema", detail)

    def test_neither_candidate_can_publish_or_activate(self):
        for plan in load_plans():
            self.assertIs(plan["conclusion"]["publishable"], False)
            self.assertIs(plan["conclusion"]["activatable"], False)
            self.assertIs(plan["eligible_in_any_environment"], False)

    def test_no_rollback_policy_is_invented(self):
        # The refusal must state that no policy exists, not supply one.
        for plan in load_plans():
            note = json.dumps(plan["rollback"])
            self.assertNotIn("policy_granted", note)
            self.assertIn("does not perform a rollback", note)


class ContractCompatibilityTests(unittest.TestCase):
    def test_both_compat_manifests_validate_under_both_routes(self):
        _pin_record, schema = pin.load_pinned_contract()
        for name in ("kb_baseline.manifest.json", "kb_blocked_candidates.manifest.json"):
            document = load_json(repo("publication", "fixtures", "compat", name))
            for key in ("_fixture_warning", "_fixture_note", "_descriptor_source"):
                document.pop(key, None)
            valid, reasons = validate_manifest(document)
            self.assertTrue(valid, "%s: %s" % (name, reasons))
            self.assertEqual(validate_against_vendored_schema(document, schema), [], name)

    def test_the_baseline_is_unmistakably_synthetic(self):
        document = load_json(repo("publication", "fixtures", "compat", "kb_baseline.manifest.json"))
        self.assertIn("SYNTHETIC FIXTURE", document["_fixture_warning"])
        for descriptor in document["artifacts"]:
            self.assertEqual(descriptor["artifact_id"], "fixture_artifact")

    def test_the_baseline_hashes_are_real_repository_bytes(self):
        document = load_json(repo("publication", "fixtures", "compat", "kb_baseline.manifest.json"))
        entries = inventory.discover()
        real = {entry["descriptor_sha256"] for entry in entries}
        for descriptor in document["artifacts"]:
            self.assertIn(descriptor["sha256"], real)

    def test_the_compat_fixtures_use_the_backend_fixture_format(self):
        document = load_json(
            repo("publication", "fixtures", "compat", "negative_fixtures.compat.json")
        )
        for key in ("base", "target", "context", "cases"):
            self.assertIn(key, document)
        allowed_keys = {
            "name",
            "stage",
            "expected_code",
            "manifest_overrides",
            "descriptor_overrides",
            "other_descriptor_overrides",
            "remove_descriptor_fields",
            "append_duplicate_of_target",
            "context_overrides",
            "bytes_utf8",
        }
        allowed_stages = {"validation", "eligibility", "selection", "integrity"}
        for case in document["cases"]:
            self.assertLessEqual(set(case), allowed_keys, case["name"])
            self.assertIn(case["stage"], allowed_stages, case["name"])
            self.assertIn(case["expected_code"], BACKEND_REASON_CODES, case["name"])

    def test_the_pinned_schema_hash_is_restated_in_the_compat_fixtures(self):
        document = load_json(
            repo("publication", "fixtures", "compat", "negative_fixtures.compat.json")
        )
        pin_record, _schema = pin.load_pinned_contract()
        self.assertEqual(document["contract_schema_sha256"], pin_record["vendored"]["sha256"])


class InventoryTests(unittest.TestCase):
    def test_the_inventory_is_sound(self):
        entries = inventory.discover()
        self.assertEqual(inventory.check_inventory(entries), [])
        self.assertGreaterEqual(len(entries), 16)

    def test_every_governed_filename_equals_its_object_key(self):
        for entry in inventory.discover():
            self.assertTrue(entry["filename_matches_object_key"], entry["repository_path"])

    def test_candidates_are_labelled_as_candidates(self):
        entries = inventory.discover()
        for artifact_id, version in (("token_dictionary", "2.0"), ("question_flow", "1.1")):
            entry = inventory.find(entries, artifact_id, version)
            self.assertEqual(entry["role"], "candidate")

    def test_repository_role_is_not_a_publication_claim(self):
        for entry in inventory.discover():
            if entry["role"] == "published_lineage":
                self.assertIn("not a publication status", entry["role_note"])


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1)
