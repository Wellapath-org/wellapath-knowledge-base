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
from pubkit import manifest as manifest_module  # noqa: E402
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
            "948299bc1ca87592e372d4ce889bdd2424a6cfc3d34c7660453dfe7d60d5038a",
        )
        self.assertEqual(pin_record["vendored"]["byte_count"], 7806)
        self.assertEqual(
            pin_record["backend"]["merge_commit"], "bbaeadd6075eb37fd51acbe04101f939e52c7d48"
        )
        self.assertEqual(pin_record["contract"]["contract_version"], "1.1.0")

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

    #: The Backend's REASON_CODES, verbatim and in order, at
    #: bbaeadd6075eb37fd51acbe04101f939e52c7d48 (contract 1.1.0).
    #:
    #: Order is not behaviour, which is exactly why it needs a test: nothing else in this
    #: repository would notice it changing, and the module's own promise is that drift shows up
    #: as a visible diff against the Backend. A silently reordered list makes that diff
    #: meaningless the next time someone compares the two files.
    BACKEND_REASON_CODES_AT_PIN = (
        "MANIFEST_MALFORMED", "MANIFEST_VERSION_UNSUPPORTED", "UNKNOWN_REQUIRED_FEATURE",
        "UNKNOWN_FIELD", "MISSING_REQUIRED_FIELD", "MALFORMED_FIELD",
        "UNSUPPORTED_ARTIFACT_SCHEMA", "CONTENT_TYPE_UNSUPPORTED", "OBJECT_KEY_INVALID",
        "ORIGIN_NOT_APPROVED", "ORIGIN_NOT_HTTPS", "ORIGIN_HAS_CREDENTIALS", "ORIGIN_HAS_QUERY",
        "DUPLICATE_IDENTITY", "RELATIONSHIP_CYCLE", "INVALID_ROLLBACK_TARGET",
        "APPROVAL_STATUS_UNKNOWN", "APPROVAL_SCOPE_MISSING", "APPROVAL_SCOPE_UNKNOWN",
        "APPROVAL_SCOPE_MISMATCH", "HASH_MISMATCH", "BYTE_COUNT_MISMATCH", "NOT_PUBLISHED",
        "APPROVAL_MISSING", "APPROVAL_NOT_GRANTED", "BLOCKER_UNRESOLVED",
        "ACTIVATION_NOT_AUTHORIZED", "NOT_ACTIVE", "ENVIRONMENT_NOT_AUTHORIZED",
        "APP_BUILD_INCOMPATIBLE", "DESCRIPTOR_EXPIRED", "DESCRIPTOR_DEPRECATED",
        "NO_ACTIVE_ARTIFACT", "MULTIPLE_ACTIVE", "DOWNGRADE_NOT_AUTHORIZED",
    )

    def test_the_code_list_matches_the_backend_exactly_and_in_order(self):
        self.assertEqual(tuple(BACKEND_REASON_CODES), self.BACKEND_REASON_CODES_AT_PIN)

    def test_the_scope_codes_sit_where_the_backend_puts_them(self):
        codes = list(BACKEND_REASON_CODES)
        self.assertEqual(
            codes[codes.index("APPROVAL_STATUS_UNKNOWN") + 1 : codes.index("HASH_MISMATCH")],
            ["APPROVAL_SCOPE_MISSING", "APPROVAL_SCOPE_UNKNOWN", "APPROVAL_SCOPE_MISMATCH"],
        )

    def test_backend_codes_are_verbatim(self):
        # A code the Backend does not have would be meaningless to it; one it has that we lack
        # would be a rejection we cannot report. Both are drift.
        self.assertEqual(len(BACKEND_REASON_CODES), 35)
        self.assertIn("DOWNGRADE_NOT_AUTHORIZED", BACKEND_REASON_CODES)
        for code in ("APPROVAL_SCOPE_MISSING", "APPROVAL_SCOPE_UNKNOWN", "APPROVAL_SCOPE_MISMATCH"):
            self.assertIn(code, BACKEND_REASON_CODES, code)

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
                "product": {
                    "required": True, "status": "granted", "decision_ref": "P",
                    "approved_at": None, "decision_scope": ["artifact_publication"],
                },
                "clinical": {
                    "required": True, "status": "granted", "decision_ref": "C",
                    "approved_at": None, "decision_scope": ["artifact_publication"],
                },
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
                    "product": {
                        "required": True, "status": "granted", "decision_ref": "P",
                        "approved_at": None, "decision_scope": ["artifact_publication"],
                    },
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
                    "product": {
                        "required": True, "status": "granted", "decision_ref": "P",
                        "approved_at": None, "decision_scope": ["artifact_publication"],
                    },
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
                    "clinical": {
                        "required": True, "status": "granted", "decision_ref": "C",
                        "approved_at": None, "decision_scope": ["artifact_publication"],
                    },
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
                granted, ref, reasons, _scopes = self.resolve(
                    kind, artifact_id, version, entry["descriptor_sha256"]
                )
                self.assertFalse(granted, "%s %s@%s" % (kind, artifact_id, version))
                self.assertIsNone(ref)
                self.assertTrue(reasons)

    def test_im_001_resolved_is_not_an_authorization(self):
        for kind in ("publication_authorization", "activation_authorization"):
            _granted, _ref, reasons, _scopes = self.resolve(kind)
            self.assertIn(
                "KB_DECISION_SET_IS_NOT_AUTHORIZATION", [item["code"] for item in reasons], kind
            )

    def test_product_authority_cannot_satisfy_a_clinical_claim(self):
        _granted, _ref, reasons, _scopes = self.resolve("clinical_approval")
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
        _granted, _ref, reasons, _scopes = self.resolve("product_approval", digest="sha256:" + "f" * 64)
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
        # Exactly the two safety blockers, both open. Nothing else belongs in this channel.
        self.assertEqual(statuses, {"IM001-CLIN-FLAG-001": "open", "IM003-SB-001": "open"})

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
        # The superseded contract is legacy test material, still pinned and still quotable.
        known.add(pin_record["legacy"]["sha256"])
        # Historical bindings: the v1 reconciliation record's own digest, cited by the Backend,
        # and the digest of the Backend fixture v2 binds to. Both are facts about the past.
        for path in ("publication/fixtures/compat/approval_scope_reconciliation_v1.json",):
            with open(repo(*path.split("/")), "rb") as handle:
                known.add(__import__("hashlib").sha256(handle.read()).hexdigest())
        v2 = load_json(
            repo("publication", "fixtures", "compat", "approval_scope_reconciliation_v2.json")
        )
        known.add(v2["backend_binding"]["blocked_candidates_fixture"]["sha256"])

        for relative, text in self.documents():
            for digest in set(re.findall(r"\b[0-9a-f]{64}\b", text)):
                self.assertIn(digest, known, "%s quotes unknown digest %s" % (relative, digest))

    def test_every_quoted_commit_is_a_pinned_commit(self):
        import re

        pin_record, _schema = pin.load_pinned_contract()
        known = {
            pin_record["backend"]["merge_commit"],
            pin_record["backend"]["supersedes_merge_commit"],
            pin_record["legacy"]["backend_merge_commit"],
            "c1b07944ea0b231914943ac17b2265441e53b85c",
            "2325e3f9e876a40d32e6e3ff0b5b77e19c7e309a",
        }
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
        from validate_publication_fixtures import COMPAT_MUTATION_PROOFS, MUTATION_PROOFS

        return {
            "compat_fixtures": len(compat["cases"]),
            "kb_fixtures": len(kb["cases"]),
            "total_fixtures": len(compat["cases"]) + len(kb["cases"]),
            "frozen_artifacts": freeze["frozen_artifact_count"],
            "mutation_proofs": len(MUTATION_PROOFS) + len(COMPAT_MUTATION_PROOFS),
            "unit_tests": _count_tests(),
        }

    def test_the_counts_are_what_this_step_actually_built(self):
        counts = self.counts()
        self.assertEqual(counts["compat_fixtures"], 50)
        self.assertEqual(counts["kb_fixtures"], 70)
        self.assertEqual(counts["total_fixtures"], 120)
        self.assertEqual(counts["frozen_artifacts"], 48)
        self.assertEqual(counts["mutation_proofs"], 14)

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


class ApprovalScopeContractTests(unittest.TestCase):
    """Contract 1.1.0's approval-scope rules, ported and proved behaviourally identical."""

    def approval(self, **overrides):
        base = {
            "required": True,
            "status": "granted",
            "decision_ref": "REF",
            "approved_at": None,
            "decision_scope": ["artifact_publication"],
        }
        base.update(overrides)
        return base

    def validate(self, approval):
        return [item["code"] for item in manifest_module._validate_approval(approval, "a")]

    def evaluate(self, approval):
        return [
            item["code"] for item in eligibility._evaluate_approval_scope(approval, "a", "product")
        ]

    def test_decision_scope_is_structurally_optional(self):
        _pin, schema = pin.load_pinned_contract()
        record = schema["definitions"]["approval_record"]
        self.assertNotIn("decision_scope", record["required"])
        self.assertIn("decision_scope", record["properties"])
        self.assertEqual(set(record["required"]), set(contract.REQUIRED_APPROVAL_KEYS))
        self.assertEqual(contract.OPTIONAL_APPROVAL_KEYS, ("decision_scope",))

    def test_a_non_granted_approval_needs_no_scope(self):
        for status in ("pending", "denied", "not_required"):
            approval = self.approval(status=status, decision_ref=None, decision_scope=None)
            self.assertEqual(self.validate(approval), [], status)
            approval.pop("decision_scope")
            self.assertEqual(self.validate(approval), [], "%s (key absent)" % status)

    def test_a_non_granted_approval_never_contributes_to_approved(self):
        for status in ("pending", "denied", "not_required"):
            approval = self.approval(status=status, decision_ref="REF", decision_scope=None)
            descriptor = {
                "artifact_id": "x", "artifact_version": "1.0", "sha256": "sha256:" + "a" * 64,
                "byte_count": 1, "release_status": "published", "published_at": "2026-08-01T00:00:00Z",
                "approvals": {"product": approval, "clinical": self.approval()},
                "blockers": [], "activation_status": "active", "activation_authorized": True,
                "activation_decision_ref": "R", "target_environments": ["staging"],
                "deprecated": False, "expires_at": None,
            }
            states, _ = eligibility.evaluate_descriptor(
                descriptor, "staging", now=PLAN_EVALUATION_INSTANT
            )
            self.assertFalse(states["approved"], status)

    def test_missing_scope_on_granted_fails_with_scope_missing(self):
        self.assertEqual(self.validate(self.approval(decision_scope=None)), ["APPROVAL_SCOPE_MISSING"])
        absent = self.approval()
        absent.pop("decision_scope")
        self.assertEqual(self.validate(absent), ["APPROVAL_SCOPE_MISSING"])
        self.assertEqual(self.evaluate(self.approval(decision_scope=None)), ["APPROVAL_SCOPE_MISSING"])

    def test_unknown_scope_fails_with_scope_unknown(self):
        self.assertEqual(
            self.validate(self.approval(decision_scope=["auto_approved"])), ["APPROVAL_SCOPE_UNKNOWN"]
        )
        self.assertEqual(
            self.evaluate(self.approval(decision_scope=["auto_approved"])), ["APPROVAL_SCOPE_UNKNOWN"]
        )

    def test_mismatched_scope_fails_with_scope_mismatch(self):
        for scope in (["product_display"], ["clinical_content_review"], ["artifact_activation"]):
            self.assertEqual(
                self.validate(self.approval(decision_scope=scope)), ["APPROVAL_SCOPE_MISMATCH"], scope
            )
            self.assertEqual(
                self.evaluate(self.approval(decision_scope=scope)), ["APPROVAL_SCOPE_MISMATCH"], scope
            )

    def test_a_correctly_scoped_granted_approval_passes(self):
        self.assertEqual(self.validate(self.approval()), [])
        self.assertEqual(self.evaluate(self.approval()), [])
        self.assertEqual(
            self.validate(self.approval(decision_scope=["product_display", "artifact_publication"])),
            [],
        )

    def test_validation_failure_prevents_eligibility_treating_it_as_approved(self):
        """A scope fault is structural: rejected at validation AND denied at eligibility.

        Both, not either. A descriptor evaluated in isolation must fail closed rather than
        inherit a guarantee from a validation pass that may never have run.
        """
        descriptor = json.loads(json.dumps(load_plans()[1]["descriptor"]))
        descriptor["approvals"]["product"] = self.approval(decision_scope=["product_display"])
        descriptor["approvals"]["clinical"] = self.approval()
        wrapper = {
            "manifest_version": "1.1.0",
            "generated_at": PLAN_EVALUATION_INSTANT,
            "artifacts": [descriptor],
        }
        valid, reasons = validate_manifest(wrapper)
        self.assertFalse(valid)
        self.assertIn("APPROVAL_SCOPE_MISMATCH", [r["code"] for r in reasons])

        states, ereasons = eligibility.evaluate_descriptor(
            descriptor, "staging", now=PLAN_EVALUATION_INSTANT
        )
        self.assertFalse(states["approved"])
        self.assertIn("APPROVAL_SCOPE_MISMATCH", [r["code"] for r in ereasons])

    def test_the_schema_is_deliberately_looser_than_the_validator(self):
        """The conditional scope rule lives in the validator; draft-07 cannot express it.

        Asserted rather than assumed, because the whole asymmetric comparison in plan.py rests
        on it. If the Backend ever adds an if/then and the schema starts catching this, the
        comparison should be revisited — and this test is what will say so.
        """
        _pin, schema = pin.load_pinned_contract()
        record = schema["definitions"]["approval_record"]
        self.assertNotIn("if", record)
        self.assertNotIn("allOf", record)
        descriptor = json.loads(json.dumps(load_plans()[1]["descriptor"]))
        descriptor["approvals"]["product"] = {
            "required": True, "status": "granted", "decision_ref": "D",
            "approved_at": None, "decision_scope": None,
        }
        wrapper = {
            "manifest_version": "1.1.0",
            "generated_at": PLAN_EVALUATION_INSTANT,
            "artifacts": [descriptor],
        }
        valid, reasons = validate_manifest(wrapper)
        self.assertFalse(valid)
        self.assertIn("APPROVAL_SCOPE_MISSING", [r["code"] for r in reasons])
        # ... and the schema alone lets it through, which is why the comparison is asymmetric.
        self.assertEqual(validate_against_vendored_schema(wrapper, schema), [])

    def test_the_comparison_fails_only_in_the_unsafe_direction(self):
        from pubkit.plan import _validate_descriptor

        pin_record, schema = pin.load_pinned_contract()

        # KB stricter: granted with no scope. Rejected by the port, accepted by the schema.
        stricter = json.loads(json.dumps(load_plans()[1]["descriptor"]))
        stricter["approvals"]["product"] = {
            "required": True, "status": "granted", "decision_ref": "D",
            "approved_at": None, "decision_scope": None,
        }
        result = _validate_descriptor(stricter, schema, pin_record)
        self.assertTrue(result["kb_stricter_than_schema"])
        self.assertFalse(result["kb_looser_than_schema"])
        self.assertNotIn(
            "KB_CONTRACT_KB_PASSES_BACKEND_FAILS", [r["code"] for r in result["reasons"]]
        )

        # Sound descriptor: both routes accept, neither direction flagged.
        sound = load_plans()[1]["descriptor"]
        result = _validate_descriptor(sound, schema, pin_record)
        self.assertTrue(result["validators_agree"])
        self.assertFalse(result["kb_stricter_than_schema"])
        self.assertFalse(result["kb_looser_than_schema"])
        self.assertEqual(result["reasons"], [])

    def test_the_ported_codes_match_the_backend_vocabulary(self):
        _pin, schema = pin.load_pinned_contract()
        declared = None
        for branch in schema["definitions"]["approval_record"]["properties"]["decision_scope"]["oneOf"]:
            if branch.get("type") == "array":
                declared = branch["items"]["enum"]
        self.assertEqual(set(declared), set(contract.APPROVAL_SCOPES))
        self.assertEqual(contract.ARTIFACT_APPROVAL_SLOT_SCOPE, "artifact_publication")


class SourceProvenanceTests(unittest.TestCase):
    """The five kinds of provenance stay distinct, and a hash never stands in for governance.

    The rule this enforces is the one that matters at ingestion: a matching sha256 proves the
    bytes are the bytes. It proves nothing about who approved them or where they came from. An
    ingester that reads hash agreement as governance evidence has skipped the governance check.
    """

    def plans(self):
        return load_plans()

    def test_the_hash_is_documented_as_identity_and_not_authorization(self):
        for plan in self.plans():
            identity = plan["source_provenance"]["artifact_byte_identity"]
            self.assertEqual(identity["field"], "descriptor.sha256")
            joined = " ".join(identity["does_not_establish"]).lower()
            for claim in ("approved", "authoris", "review", "commit"):
                self.assertIn(claim, joined, claim)

    def test_the_governance_register_is_bound_by_hash_not_by_path(self):
        import hashlib

        with open(repo("publication", "governance", "decision_register_v1.json"), "rb") as handle:
            digest = "sha256:%s" % hashlib.sha256(handle.read()).hexdigest()
        for plan in self.plans():
            self.assertEqual(plan["governance"]["register_sha256"], digest)
            self.assertEqual(
                plan["source_provenance"]["decision_record_provenance"]["register_sha256"], digest
            )
            self.assertEqual(
                plan["source_provenance"]["decision_record_provenance"]["bound_by"], "hash"
            )
            cited = [r for r in plan["descriptor"]["references"] if "governance register" in r]
            self.assertEqual(len(cited), 1)
            self.assertIn(digest.split(":")[1], cited[0])

    def test_no_mutable_branch_tip_is_cited(self):
        for plan in self.plans():
            self.assertIs(plan["source_provenance"]["repository_branch_state"]["cited"], False)

    def test_the_ingestion_boundary_is_recorded_explicitly(self):
        for plan in self.plans():
            boundary = plan["source_provenance"]["ingestion_boundary"]
            envelope = " ".join(boundary["must_be_supplied_by_the_ingestion_envelope"]).lower()
            self.assertIn("commit", envelope)
            never = " ".join(boundary["must_never_be_inferred"]).lower()
            self.assertIn("governance approval from a matching artifact hash", never)
            self.assertIn("source authorization from a matching artifact hash", never)

    def test_governance_cannot_be_inferred_from_a_valid_artifact_hash(self):
        """The behavioural form of the rule, not just the documented one.

        A descriptor whose hash and byte count are perfectly correct — verified against the
        real artifact bytes — must still be unapproved and ineligible, because nothing granted
        anything. If this ever passes, an ingester could treat integrity as authorization.
        """
        from pubkit.integrity import measure, verify_bytes

        entries = inventory.discover()
        for plan in self.plans():
            descriptor = plan["descriptor"]
            entry = inventory.find(
                entries, descriptor["artifact_id"], descriptor["artifact_version"]
            )
            data, digest, byte_count = measure(
                os.path.join(inventory.REPO_ROOT, entry["repository_path"])
            )
            # Integrity is genuinely, verifiably sound ...
            self.assertEqual(digest, descriptor["sha256"])
            self.assertEqual(byte_count, descriptor["byte_count"])
            self.assertEqual(
                verify_bytes(data, descriptor["sha256"], descriptor["byte_count"], "x"), []
            )
            # ... and the descriptor is still approved by nobody and eligible nowhere.
            for environment in ("development", "staging", "production"):
                states, _ = eligibility.evaluate_descriptor(
                    descriptor, environment, now=PLAN_EVALUATION_INSTANT
                )
                self.assertFalse(states["approved"], environment)
                self.assertFalse(states["eligible_for_environment"], environment)

    def test_a_register_edited_after_the_fact_breaks_its_binding(self):
        """The point of hash-binding the register: a path citation would not notice."""
        import hashlib
        import json as _json

        register = load_json(repo("publication", "governance", "decision_register_v1.json"))
        register["_metadata"]["note"] = "edited after the plan cited it"
        edited = "sha256:%s" % hashlib.sha256(
            (_json.dumps(register, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
        ).hexdigest()
        for plan in self.plans():
            self.assertNotEqual(plan["governance"]["register_sha256"], edited)

    def test_the_five_provenance_kinds_are_all_present_and_distinct(self):
        expected = {
            "artifact_byte_identity",
            "generator_input_identity",
            "decision_record_provenance",
            "publication_plan_provenance",
            "repository_branch_state",
            "ingestion_boundary",
        }
        for plan in self.plans():
            self.assertEqual(set(plan["source_provenance"]), expected)

    def test_generator_input_identity_lives_inside_the_artifact_bytes(self):
        """So it cannot drift from the artifact it describes."""
        entries = inventory.discover()
        for plan in self.plans():
            block = plan["source_provenance"]["generator_input_identity"]
            self.assertIs(block["covered_by_artifact_sha256"], True)
            self.assertIs(block["recorded_inside_artifact_metadata"], True)
            entry = inventory.find(
                entries, plan["target"]["artifact_id"], plan["target"]["artifact_version"]
            )
            artifact = load_json(repo(*entry["repository_path"].split("/")))
            metadata = artifact["_metadata"]
            self.assertTrue(
                "provenance" in metadata or "source" in metadata,
                "%s records no provenance inside its own bytes" % entry["repository_path"],
            )


class ContractProvenanceTests(unittest.TestCase):
    """A plan must describe the contract it was actually built and checked against.

    The defect this guards: `contract_validation.contract_version` and a descriptor reference
    were written as literals, the pin moved from 1.0.0 to 1.1.0, and the literals stayed. The
    plans went on advertising a contract they had never been near, and every schema check
    passed because the schema pinned the same stale literal.
    """

    def plans(self):
        return load_plans()

    def pin(self):
        return pin.load_pinned_contract()[0]

    def test_both_plans_name_the_active_contract_everywhere(self):
        pin_record = self.pin()
        for plan in self.plans():
            for block in ("contract_pin", "contract_validation"):
                self.assertEqual(
                    plan[block]["contract_version"],
                    pin_record["contract"]["contract_version"],
                    block,
                )
                self.assertEqual(plan[block].get("schema_sha256"), pin_record["vendored"]["sha256"])
                self.assertEqual(
                    plan[block].get("schema_byte_count"), pin_record["vendored"]["byte_count"]
                )
            self.assertEqual(
                plan["contract_pin"]["backend_merge_commit"],
                pin_record["backend"]["merge_commit"],
            )
            self.assertEqual(
                plan["contract_validation"]["backend_merge_commit"],
                pin_record["backend"]["merge_commit"],
            )

    def test_the_active_values_are_the_expected_ones(self):
        for plan in self.plans():
            self.assertEqual(plan["contract_pin"]["contract_version"], "1.1.0")
            self.assertEqual(plan["contract_validation"]["contract_version"], "1.1.0")
            self.assertEqual(
                plan["contract_validation"]["backend_merge_commit"],
                "bbaeadd6075eb37fd51acbe04101f939e52c7d48",
            )
            self.assertEqual(
                plan["contract_validation"]["schema_sha256"],
                "948299bc1ca87592e372d4ce889bdd2424a6cfc3d34c7660453dfe7d60d5038a",
            )
            self.assertEqual(plan["contract_validation"]["schema_byte_count"], 7806)

    def test_no_current_plan_cites_legacy_contract_material(self):
        for plan in self.plans():
            text = json.dumps(plan)
            for marker in plan_module_for_provenance().LEGACY_CONTRACT_MARKERS:
                self.assertNotIn(marker, text, marker)

    def test_a_clean_plan_passes_its_own_provenance_check(self):
        pin_record = self.pin()
        for plan in self.plans():
            self.assertEqual(
                plan_module_for_provenance().check_plan_provenance(plan, pin_record), []
            )

    def test_every_provenance_fault_has_its_own_reason_code(self):
        from pubkit.plan import check_plan_provenance

        pin_record = self.pin()
        base = self.plans()[1]
        cases = {
            "KB_PROVENANCE_VERSION_MISMATCH":
                ("contract_validation", "contract_version", "1.0.0"),
            "KB_PROVENANCE_COMMIT_MISMATCH":
                ("contract_validation", "backend_merge_commit", "a" * 40),
            "KB_PROVENANCE_SCHEMA_HASH_MISMATCH":
                ("contract_validation", "schema_sha256", "b" * 64),
            "KB_PROVENANCE_SCHEMA_BYTES_MISMATCH":
                ("contract_validation", "schema_byte_count", 1),
        }
        for expected, (block, field, value) in cases.items():
            broken = json.loads(json.dumps(base))
            broken[block][field] = value
            codes = [r["code"] for r in check_plan_provenance(broken, pin_record)]
            self.assertIn(expected, codes, expected)

    def test_a_stale_plan_is_caught_against_the_live_pin(self):
        """Internal consistency is not enough: a plan can agree with itself and be stale."""
        from pubkit.plan import check_plan_provenance

        pin_record = self.pin()
        stale = json.loads(json.dumps(self.plans()[1]))
        for block in ("contract_pin", "contract_validation"):
            stale[block]["contract_version"] = "1.0.0"
        codes = [r["code"] for r in check_plan_provenance(stale, pin_record)]
        # Self-consistent, so no VERSION_MISMATCH ...
        self.assertNotIn("KB_PROVENANCE_VERSION_MISMATCH", codes)
        # ... but stale against the pin, and claiming a pass it did not earn.
        self.assertIn("KB_PROVENANCE_STALE_PLAN", codes)
        self.assertIn("KB_PROVENANCE_VALIDATED_AGAINST_NON_PIN", codes)

    def test_generation_refuses_to_write_an_inconsistent_plan(self):
        """The guard is at generation too, not only at validation.

        A plan that misdescribes what it was checked against must never reach disk, because it
        is precisely the plan a reader would trust.
        """
        import tempfile

        from pubkit.plan import ProvenanceError, build_plan

        contract_pin, contract_schema = pin.load_pinned_contract()
        tampered = json.loads(json.dumps(contract_pin))
        # A pin whose two halves disagree: the descriptor will cite the contract version while
        # the summary cites the merge commit, and the cross-check must catch the split.
        tampered["contract"]["contract_version"] = "9.9.9"

        entries = inventory.discover()
        entry = inventory.find(entries, "question_flow", "1.1")
        register = DecisionRegister.from_file(
            repo("publication", "governance", "decision_register_v1.json")
        )
        with tempfile.TemporaryDirectory() as staging:
            with self.assertRaises(ProvenanceError) as caught:
                build_plan("question_flow", "1.1", entry, register, tampered, contract_schema,
                           entries, staging_root=staging)
        self.assertTrue(
            any(r["code"].startswith("KB_PROVENANCE_") for r in caught.exception.reasons)
        )

    def test_the_plan_schema_does_not_pin_a_stale_literal(self):
        """The schema must not carry its own copy of the contract version as a `const`.

        A `const` there is a second hand-maintained place for the version to go stale — and it
        is what let the defect through: the schema pinned 1.0.0 and validated a plan claiming
        1.0.0 while the pin said 1.1.0.
        """
        schema = load_json(repo("schema", "publication_plan.v1.schema.json"))
        for block in ("contract_pin", "contract_validation"):
            node = schema["properties"][block]["properties"]["contract_version"]
            self.assertNotIn("const", node, block)
            self.assertIn("pattern", node, block)

    def test_no_repository_commit_is_hand_maintained_in_a_descriptor(self):
        """The old KB-lineage reference went stale three merges running; it is gone."""
        import re

        for plan in self.plans():
            for ref in plan["descriptor"]["references"]:
                for commit in re.findall(r"\b[0-9a-f]{40}\b", ref):
                    self.assertEqual(
                        commit,
                        self.pin()["backend"]["merge_commit"],
                        "descriptor cites commit %s, which is not the pinned contract commit"
                        % commit,
                    )


def plan_module_for_provenance():
    from pubkit import plan as plan_module

    return plan_module


class FixtureSelectorTests(unittest.TestCase):
    """The 1.1.0 `other_descriptor_overrides` selector must resolve to exactly one identity.

    Every refusal below is a mutation that would otherwise be applied to a descriptor nobody
    named, while the case still reported a pass — which is worse than a failing fixture,
    because it looks like coverage.
    """

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "vpf_under_test", os.path.join(ROOT, "tools", "validate_publication_fixtures.py")
        )
        self.vpf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.vpf)
        baseline = load_json(
            repo("publication", "fixtures", "compat", "kb_baseline.manifest.json")
        )
        self.artifacts = baseline["artifacts"]
        self.selector = {
            "artifact_id": "fixture_artifact",
            "artifact_version": "1.0",
            # A marker that appears nowhere in the baseline, so "which descriptor was
            # mutated?" has one answer. `deprecated: False` would collide with a descriptor
            # that already carries it, and the test would pass or fail for the wrong reason.
            "overrides": {"min_app_build": 4242},
        }

    def apply(self, artifacts, selector):
        return self.vpf._apply_other_descriptor_overrides(artifacts, selector, "test")

    def refusal(self, artifacts, selector):
        with self.assertRaises(self.vpf.SelectorError) as caught:
            self.apply(artifacts, selector)
        return str(caught.exception).split(":")[0]

    def test_a_unique_identity_is_selected(self):
        result = self.apply(self.artifacts, self.selector)
        marked = [d for d in result if d.get("min_app_build") == 4242]
        self.assertEqual(len(marked), 1)
        self.assertEqual(marked[0]["artifact_version"], "1.0")

    def test_the_legacy_bare_map_format_is_refused_with_a_stable_reason(self):
        self.assertEqual(
            self.refusal(self.artifacts, {"min_app_build": 4242}), self.vpf.SELECTOR_LEGACY_SHAPE
        )
        self.assertEqual(
            self.refusal(self.artifacts, "fixture_artifact@1.0"), self.vpf.SELECTOR_LEGACY_SHAPE
        )

    def test_an_incomplete_selector_is_refused(self):
        for missing in self.vpf.SELECTOR_KEYS:
            partial = {k: v for k, v in self.selector.items() if k != missing}
            self.assertEqual(
                self.refusal(self.artifacts, partial), self.vpf.SELECTOR_LEGACY_SHAPE, missing
            )

    def test_an_unknown_selector_key_is_refused(self):
        typo = dict(self.selector, artifact_verison="1.0")
        self.assertEqual(self.refusal(self.artifacts, typo), self.vpf.SELECTOR_UNKNOWN_KEY)

    def test_an_identity_matching_nothing_is_refused(self):
        absent = dict(self.selector, artifact_version="7.7")
        self.assertEqual(self.refusal(self.artifacts, absent), self.vpf.SELECTOR_NO_MATCH)

    def test_an_ambiguous_identity_is_refused_rather_than_resolved(self):
        duplicated = list(self.artifacts) + [dict(self.artifacts[0], country="zz")]
        self.assertEqual(self.refusal(duplicated, self.selector), self.vpf.SELECTOR_AMBIGUOUS)

    def test_selection_does_not_depend_on_descriptor_ordering(self):
        forward = self.apply(self.artifacts, self.selector)
        reverse = self.apply(list(reversed(self.artifacts)), self.selector)
        pick = lambda result: [d for d in result if d["artifact_version"] == "1.0"][0]
        self.assertEqual(
            json.dumps(pick(forward), sort_keys=True), json.dumps(pick(reverse), sort_keys=True)
        )

    def test_an_extra_descriptor_cannot_silently_redirect_a_mutation(self):
        # A new descriptor with a different identity is simply ignored ...
        extended = list(self.artifacts) + [dict(self.artifacts[0], artifact_version="9.9")]
        marked = [d for d in self.apply(extended, self.selector) if d.get("min_app_build") == 4242]
        self.assertEqual([d["artifact_version"] for d in marked], ["1.0"])
        # ... and one that collides with the selected identity is refused, not chosen between.
        colliding = list(self.artifacts) + [dict(self.artifacts[0])]
        self.assertEqual(self.refusal(colliding, self.selector), self.vpf.SELECTOR_AMBIGUOUS)

    def test_the_input_manifest_is_not_mutated_in_place(self):
        before = json.dumps(self.artifacts, sort_keys=True)
        self.apply(self.artifacts, self.selector)
        self.assertEqual(json.dumps(self.artifacts, sort_keys=True), before)

    def test_every_committed_case_uses_the_1_1_0_selector_shape(self):
        document = load_json(
            repo("publication", "fixtures", "compat", "negative_fixtures.compat.json")
        )
        used = 0
        for case in document["cases"]:
            selector = case.get("other_descriptor_overrides")
            if selector is None:
                continue
            used += 1
            self.assertEqual(set(selector), set(self.vpf.SELECTOR_KEYS), case["name"])
        self.assertGreater(used, 0, "no committed case exercises the selector")


class CrossVersionCompatibilityTests(unittest.TestCase):
    """1.0.0 → 1.1.0 compatibility, from committed fixtures only.

    Nothing here reads git history or reaches a remote, so these run identically in a shallow
    clone, an exported tree and a path containing spaces. A compatibility test that needs a
    full clone is one that will eventually stop being run.
    """

    def fixtures(self):
        return load_json(
            repo("publication", "fixtures", "compat", "legacy_contract_compatibility_v1.json")
        )

    def legacy_schema(self):
        return load_json(repo("contracts", "backend", "legacy", "manifest.v1.0.0.schema.json"))

    def active_schema(self):
        return pin.load_pinned_contract()[1]

    def under(self, schema, manifest):
        return schema_validate(
            manifest, schema, extra_keywords=contract.SCHEMA_ANNOTATION_KEYWORDS
        )

    def test_the_legacy_schema_is_present_and_pinned(self):
        pin_record, _ = pin.load_pinned_contract()
        legacy = pin_record["legacy"]
        self.assertEqual(legacy["contract_version"], "1.0.0")
        self.assertIn("LEGACY", legacy["status"].upper())
        with open(repo(*legacy["path"].split("/")), "rb") as handle:
            digest = __import__("hashlib").sha256(handle.read()).hexdigest()
        self.assertEqual(digest, legacy["sha256"])
        self.assertNotEqual(legacy["sha256"], pin_record["vendored"]["sha256"])

    def test_safe_legacy_descriptors_remain_consumable_under_1_1_0(self):
        case = self.fixtures()["cases"]["legacy_not_granted"]
        manifest = case["manifest"]
        self.assertEqual(self.under(self.legacy_schema(), manifest), [])
        self.assertEqual(self.under(self.active_schema(), manifest), [])
        valid, reasons = validate_manifest(manifest)
        self.assertTrue(valid, reasons)

    def test_a_legacy_granted_descriptor_without_publication_scope_is_rejected(self):
        case = self.fixtures()["cases"]["legacy_granted_without_scope"]
        manifest = case["manifest"]
        # Valid under the contract it was written for ...
        self.assertEqual(self.under(self.legacy_schema(), manifest), [])
        # ... and rejected under 1.1.0. This is the tightening, and the only behaviour change.
        valid, reasons = validate_manifest(manifest)
        self.assertFalse(valid)
        self.assertIn("APPROVAL_SCOPE_MISSING", [r["code"] for r in reasons])

    def test_non_granted_legacy_approvals_do_not_require_decision_scope(self):
        manifest = self.fixtures()["cases"]["legacy_not_granted"]["manifest"]
        for approval in manifest["artifacts"][0]["approvals"].values():
            self.assertNotIn("decision_scope", approval)
            self.assertNotEqual(approval["status"], "granted")
        valid, _ = validate_manifest(manifest)
        self.assertTrue(valid)

    def test_the_new_field_is_rejected_by_a_strict_legacy_consumer(self):
        """Why the version moved rather than staying 1.0.1."""
        manifest = self.fixtures()["cases"]["forward_scoped_descriptor"]["manifest"]
        self.assertEqual(self.under(self.active_schema(), manifest), [])
        legacy_errors = self.under(self.legacy_schema(), manifest)
        self.assertTrue(legacy_errors)
        self.assertTrue(
            any("decision_scope" in message for message in legacy_errors), legacy_errors
        )

    def test_unknown_contract_major_still_fails(self):
        manifest = self.fixtures()["cases"]["unsupported_major"]["manifest"]
        valid, reasons = validate_manifest(manifest)
        self.assertFalse(valid)
        self.assertIn("MANIFEST_VERSION_UNSUPPORTED", [r["code"] for r in reasons])

    def test_every_documented_expectation_is_the_measured_one(self):
        """The fixture states an expectation per case; each is re-derived, not trusted."""
        for name, case in self.fixtures()["cases"].items():
            manifest = case["manifest"]
            valid, reasons = validate_manifest(manifest)
            codes = [r["code"] for r in reasons]
            expected = case["expected_under_1_1_0"]
            if expected == "valid":
                self.assertTrue(valid, "%s: %s" % (name, codes))
            else:
                self.assertFalse(valid, name)
                self.assertIn(expected, codes, name)

    def test_the_fixtures_are_self_contained(self):
        # No git, no network: the file carries whole manifests, not references to history.
        for case in self.fixtures()["cases"].values():
            self.assertIn("artifacts", case["manifest"])
            self.assertTrue(case["manifest"]["artifacts"])

    def test_legacy_fixture_identities_are_not_real_artifacts(self):
        entries = inventory.discover()
        real = {entry["artifact_id"] for entry in entries}
        for case in self.fixtures()["cases"].values():
            for descriptor in case["manifest"]["artifacts"]:
                self.assertNotIn(descriptor["artifact_id"], real)


class ApprovalScopeTests(unittest.TestCase):
    """The I3 Step 2A ruling: four distinct concepts, never substitutable for one another.

        product_display_decision                 complete, display wording and ordering only
        artifact_publication_product_approval    pending
        clinical_approval                        pending
        publication / activation authorization   false
    """

    #: v1 is the historical record, bound to Backend fc40ac3e where the defect existed. It is
    #: read here — and asserted byte-identical elsewhere — because preserving it is part of the
    #: guarantee, not because it describes current behaviour.
    RECONCILIATION = ("publication", "fixtures", "compat", "approval_scope_reconciliation_v1.json")
    #: v2 is the current record, bound to Backend bbaeadd6.
    RECONCILIATION_V2 = (
        "publication", "fixtures", "compat", "approval_scope_reconciliation_v2.json",
    )

    def record(self):
        return load_json(repo(*self.RECONCILIATION))

    def record_v2(self):
        return load_json(repo(*self.RECONCILIATION_V2))

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
            "approvals.product.status + approvals.product.decision_scope",
        )
        self.assertEqual(
            scope["clinical_approval"]["contract_representation"],
            "approvals.clinical.status + approvals.clinical.decision_scope",
        )
        for role in ("artifact_publication_product_approval", "clinical_approval"):
            self.assertEqual(scope[role]["required_scope"], "artifact_publication", role)
        self.assertIn("references", scope["product_display_decision"]["contract_representation"])
        self.assertNotIn("artifact_publication",
                         scope["product_display_decision"]["contract_decision_scopes"])

    def test_the_completed_decision_is_not_in_the_safety_blocker_channel(self):
        """Under 1.1.0 the completion is traceability, not a resolved blocker.

        The blockers list is what a person scans to find what is unresolved. A completed
        decision sitting in it inverts that meaning for the reader even while the evaluator
        ignores it, and 1.1.0's `decision_scope` removes the reason it was ever put there.
        """
        descriptor = self.question_flow_plan()["descriptor"]
        self.assertEqual(
            {b["id"] for b in descriptor["blockers"]},
            {"IM001-CLIN-FLAG-001", "IM003-SB-001"},
        )
        self.assertTrue(all(b["status"] == "open" for b in descriptor["blockers"]))
        # The completion is still recorded, and still grants nothing.
        scope = self.question_flow_plan()["governance"]["product_approval_scope"]
        self.assertEqual(scope["product_display_decision"]["status"], "complete")
        self.assertEqual(
            scope["product_display_decision"]["contract_decision_scopes"], ["product_display"]
        )
        # And the approval field it must not be confused with is untouched.
        self.assertEqual(descriptor["approvals"]["product"]["status"], "pending")
        self.assertIsNone(descriptor["approvals"]["product"]["decision_ref"])
        self.assertIsNone(descriptor["approvals"]["product"]["decision_scope"])

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

    def test_the_v2_record_binds_the_exact_backend_fixture(self):
        """The binding is a hash of Backend bytes. CI cannot re-fetch it, so it is pinned here.

        Without this, the recorded binding could be edited to name any fixture at all and
        nothing would notice — the record would still 'verify' against itself.
        """
        binding = self.record_v2()["backend_binding"]
        self.assertEqual(binding["commit"], "bbaeadd6075eb37fd51acbe04101f939e52c7d48")
        self.assertEqual(binding["contract_version"], "1.1.0")
        self.assertEqual(
            binding["schema_sha256"],
            "948299bc1ca87592e372d4ce889bdd2424a6cfc3d34c7660453dfe7d60d5038a",
        )
        self.assertEqual(binding["schema_byte_count"], 7806)
        self.assertEqual(
            binding["blocked_candidates_fixture"]["path"],
            "tests/fixtures/manifest/blocked-candidates.manifest.json",
        )
        self.assertEqual(
            binding["blocked_candidates_fixture"]["sha256"],
            "5b0622e8efc57b09cd65c9d4964f740565c9863b9ba28729dba035c58fc3bbb7",
        )
        # The pinned schema hash must be the one the tooling actually loads.
        pin_record, _ = pin.load_pinned_contract()
        self.assertEqual(binding["schema_sha256"], pin_record["vendored"]["sha256"])

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
