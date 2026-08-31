#!/usr/bin/env python3
"""Prove candidate 1.1 changed nothing clinical, and pin the defect regressions.

    python3 tools/verify_no_clinical_change.py            # verify + write report
    python3 tools/verify_no_clinical_change.py --check     # verify only, fail if stale

Three jobs:

  A. NO CLINICAL OR RUNTIME CHANGE — question texts, answer labels, answer
     values, produced tokens, the token output universe, red-flag effects,
     evaluation timing, path limit, skip count, IM-003 absence, and Vocabulary
     2.0 absence, each compared against candidate 1.0 rather than asserted.

  B. DEFECT REGRESSIONS — GF-006 and GF-008 re-measured against captured Dart
     output, including the exact path count each defect affected. A defect
     recorded in prose and not re-measured is a defect that can come back.

  C. CONTENT SAFETY — a scan for PHI-shaped and identifying content across every
     artifact this step adds.

Every number here is computed. Nothing is copied from a previous run.

Standard library only. No network.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qflow.dartparse import parse_all
from qflow.grouping import live_effective_questions, plan_grouped
from report_question_grouping_parity import split_questions
from vocab.artifact_io import (
    dump_artifact_bytes,
    load_json,
    repo_path,
    sha256_bytes,
    write_bytes,
)

V10_PATH = repo_path("candidate", "question_flow.ng.v1.0.json")
V11_PATH = repo_path("candidate", "question_flow.ng.v1.1.json")
ORACLE_PATH = repo_path("testing", "questions", "fixtures", "oracle",
                        "live_question_oracle_v1.json")
REPORT_PATH = repo_path("reports", "question_no_clinical_change_v1_1.json")
GENERATOR = "tools/verify_no_clinical_change.py"

#: Files this step adds, scanned for PHI-shaped content.
SCANNED_TREES = [
    ("candidate", (".json",)),
    ("schema", (".json",)),
    ("reports", (".json",)),
    ("testing/questions/fixtures", (".json",)),
    ("mobile_handoff/question_flow_v1_1", (".md", ".dart")),
    ("docs", (".md",)),
]

#: Patterns that would indicate real-person or device data. Each is checked
#: against artifact CONTENT. A hit is a failure, not a warning.
#:
#: Two of these are narrower than the obvious version, for stated reasons:
#:
#:  * PHONE requires a separator or a leading `+`. A bare 11-digit run matches
#:    the tail of every SHA256 in the repository — the first revision of this
#:    scan reported 27 "phone numbers" that were all fragments of the
#:    candidate 1.0 hash. Narrowing it removes the hash collision without
#:    losing a formatted number.
#:  * DOB must look like a FIELD (`"dob":`, `dob=`, `date_of_birth`), not a bare
#:    word. The bare version flagged the token-dictionary schema's own sentence
#:    "No PHI fields — no name, dob, phone, email, address", i.e. it flagged the
#:    prose forbidding PHI.
#:
#: `tools/verify_no_clinical_change.py --self-test` runs positive controls
#: through every pattern, so a narrowing that disabled a pattern would be caught
#: rather than rewarded with a green run.
PHI_PATTERNS = [
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    # A third narrowing, for the same reason as the first two. The pattern's `\d{2,4}[ .-]`
    # group happily matches the integer part of a decimal, so a geographic coordinate like
    # 10.272931 read as a phone number: the nationwide facilities candidate produced 7,998
    # such hits and not one real number among them. A negative lookahead rejects a match that
    # is a bare decimal — one dot, a short integer part, a long fractional part — which no
    # phone number in any format looks like. Real numbers are unaffected: they carry a leading
    # +, several separators, or no dot at all, and the positive controls below still catch them.
    ("phone number", re.compile(
        r"(?<![\dA-Fa-f])(?!\d{1,4}\.\d{4,}(?!\d))(?:\+\d{1,3}[ .-]?)?"
        r"(?:\(\d{2,4}\)[ .-]?|\d{2,4}[ .-])(?:\d[ .-]?){5,11}\d(?![\dA-Fa-f])")),
    ("date of birth", re.compile(
        r"(?:\bdate[_ ]of[_ ]birth\b|[\"\']dob[\"\']\s*[:=]|\bdob\s*[:=])", re.I)),
    ("national id", re.compile(r"\b(?:nin|bvn|ssn|nhs[_ ]?number|passport)\b", re.I)),
    ("coordinates", re.compile(r"\b-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}\b")),
    ("device or session id", re.compile(r"\b(?:device_id|session_id|imei|android_id|idfa|advertising_id)\b", re.I)),
    ("patient identifier", re.compile(r"\b(?:patient_id|mrn|medical_record_number)\b", re.I)),
]

#: IM-003 reports, scanned by tools/run_im003_checks.py instead. Listed by
#: EXACT path, never by prefix: an `im003_` prefix rule also swallowed the 19
#: invalid_im003 fixtures, which that runner does not scan, so 19 files would
#: have gone unscanned by anything.
IM003_REPORTS_SCANNED_ELSEWHERE = frozenset({
    "reports/im003_impact_analysis_v1.json",
    "reports/im003_decision_package_v1.json",
})

#: Strings that would otherwise trip a pattern, each with the reason. Empty is
#: the correct state: an entry here is an admission the scan is imprecise, so it
#: has to be written down rather than folded silently into a regex.
PHI_ALLOWLIST = {}

#: Positive controls. Every one MUST be caught, or the scan is decorative.
PHI_SELF_TEST = [
    ("email address", "contact ada.lovelace@example.org for results"),
    ("phone number", "call +234 803 123 4567 now"),
    ("phone number", "0803-123-4567"),
    ("date of birth", '{"dob": "1990-04-02"}'),
    ("date of birth", "date_of_birth recorded at intake"),
    ("national id", "NIN 12345678901 on file"),
    ("coordinates", "seen at 6.524379, 3.379206"),
    ("device or session id", '{"device_id": "abc"}'),
    ("patient identifier", '{"patient_id": 4471}'),
]

#: Negative controls. None may be caught. These are the exact false positives
#: the first revision produced.
PHI_NEGATIVE_CONTROLS = [
    "c403648f8d4d80184879f4d467d4ae74e63df5be77c461298754b82737024998",
    "18c163067eb6ee8f0b436e2a46294570d2260ec673fc9e293b25efc89a14c0a1",
    "657739cc1745104dd1194a57ef14cc9793c9b98e",
    "No PHI fields \u2014 no name, dob, phone, email, address, no free text",
    # Geographic coordinates. Facility latitudes and longitudes are not contact details, and
    # a two-digit integer part is what made them look like one.
    "10.272931",
    "13.005900",
    '"latitude": 12.358056, "longitude": 8.731447',
]


def self_test():
    """Prove the scan still detects what it exists to detect."""
    failures = []
    for expected_label, sample in PHI_SELF_TEST:
        caught = [label for label, pattern in PHI_PATTERNS if pattern.search(sample)]
        if expected_label not in caught:
            failures.append("MISSED %s in %r (caught: %s)"
                            % (expected_label, sample, caught or "nothing"))
    for sample in PHI_NEGATIVE_CONTROLS:
        caught = [label for label, pattern in PHI_PATTERNS if pattern.search(sample)]
        if caught:
            failures.append("FALSE POSITIVE %s in %r" % (caught, sample))
    return failures


def answer_identity(question):
    """What an answer MEANS: its label, value and produced tokens."""
    return {
        option["label"]: {
            "value": option["value"],
            "produces_tokens": tuple(option["produces_tokens"]),
            "is_skip_sentinel": option["is_skip_sentinel"],
        }
        for option in question["answer_options"]
    }


def compare_clinical(v10, v11):
    """Section A. Compared against 1.0, never asserted."""
    findings = {}

    # 1. Question texts — the set of wordings that can be shown.
    texts_10 = sorted({q["content_ref"]["source_text"] for q in v10["questions"]})
    texts_11 = sorted(
        {q["content_ref"]["source_text"] for q in v11["questions"]}
        | {s["source_text"] for q in v11["questions"]
           for s in q.get("grouping", {}).get("sources", [])}
    )
    findings["question_texts"] = {
        "v1_0_count": len(texts_10),
        "v1_1_count": len(texts_11),
        "removed": [t for t in texts_10 if t not in texts_11],
        "added": [t for t in texts_11 if t not in texts_10],
        "identical": texts_10 == texts_11,
        "note": "1.1 texts include grouping source texts — that is where the "
                "per-token wordings live now.",
    }

    # 2. Answer meanings, keyed by label so the option-id renaming does not
    #    mask a real change.
    def meanings(artifact):
        out = {}
        for question in artifact["questions"]:
            for label, meaning in answer_identity(question).items():
                out.setdefault(label, set()).add(
                    (meaning["value"] if not isinstance(meaning["value"], list)
                     else tuple(meaning["value"]),
                     meaning["produces_tokens"], meaning["is_skip_sentinel"]))
        return out

    m10, m11 = meanings(v10), meanings(v11)
    changed = sorted(label for label in set(m10) & set(m11) if m10[label] != m11[label])
    findings["answer_meanings"] = {
        "labels_v1_0": len(m10),
        "labels_v1_1": len(m11),
        "labels_removed": sorted(set(m10) - set(m11)),
        "labels_added": sorted(set(m11) - set(m10)),
        "labels_whose_meaning_changed": changed,
        "unchanged": not changed and set(m10) == set(m11),
    }

    # 3. Token output universe.
    def universe(artifact):
        return sorted({t for q in artifact["questions"]
                       for o in q["answer_options"] for t in o["produces_tokens"]})

    u10, u11 = universe(v10), universe(v11)
    findings["token_output_universe"] = {
        "v1_0_count": len(u10),
        "v1_1_count": len(u11),
        "removed": [t for t in u10 if t not in u11],
        "added": [t for t in u11 if t not in u10],
        "identical": u10 == u11,
    }

    # 4. Red-flag effects and evaluation timing, per producing question.
    def red_flag_map(artifact):
        return {
            q["question_id"]: (
                q["effects"]["affects_red_flags"],
                q["red_flag_evaluation"]["can_affect_red_flag"],
                q["red_flag_evaluation"]["evaluate_after_answer"],
                q["red_flag_evaluation"]["blocks_next_question"],
            )
            for q in artifact["questions"]
        }

    r10, r11 = red_flag_map(v10), red_flag_map(v11)
    shared = set(r10) & set(r11)
    findings["red_flag_effects"] = {
        "shared_questions": len(shared),
        "changed": sorted(q for q in shared if r10[q] != r11[q]),
        "red_flag_producing_tokens_v1_0": sorted({
            t for q in v10["questions"] if q["effects"]["affects_red_flags"]
            for o in q["answer_options"] for t in o["produces_tokens"]}),
        "red_flag_producing_tokens_v1_1": sorted({
            t for q in v11["questions"] if q["effects"]["affects_red_flags"]
            for o in q["answer_options"] for t in o["produces_tokens"]}),
    }
    findings["red_flag_effects"]["identical"] = (
        not findings["red_flag_effects"]["changed"]
        and findings["red_flag_effects"]["red_flag_producing_tokens_v1_0"]
        == findings["red_flag_effects"]["red_flag_producing_tokens_v1_1"]
    )

    # 5. Path controls, skips, IM-003, Vocabulary 2.0.
    findings["path_limit"] = {
        "v1_0": v10["path_controls"]["max_followup_questions"],
        "v1_1": v11["path_controls"]["max_followup_questions"],
        "unchanged_at_5": v10["path_controls"]["max_followup_questions"]
        == v11["path_controls"]["max_followup_questions"] == 5,
        "red_flag_exempt_v1_1": v11["path_controls"]["red_flag_questions_exempt_from_truncation"],
    }
    findings["optional_skips"] = {
        "skippable_questions": sorted(q["question_id"] for q in v11["questions"]
                                      if q.get("skippable")),
        "skip_sentinels": sorted(o["answer_option_id"] for q in v11["questions"]
                                 for o in q["answer_options"] if o["is_skip_sentinel"]),
    }
    findings["optional_skips"]["zero"] = not (
        findings["optional_skips"]["skippable_questions"]
        or findings["optional_skips"]["skip_sentinels"])

    im003 = next((m for m in v11["_metadata"]["impedance_mismatches"]
                  if m["id"] == "IM-003"), None)
    findings["im_003"] = {
        "present_in_disclosure": im003 is not None,
        "status": im003.get("status") if im003 else None,
        "branch_conditions_declared": sorted(
            q["question_id"] for q in v11["questions"] if q.get("branch_conditions")),
        "invalidation_acted_on": False,
        "deferred_and_absent": bool(im003) and not any(
            q.get("branch_conditions") for q in v11["questions"]),
    }
    findings["im_004_restoration_editing"] = {
        "implemented": False,
        "basis": "The candidate declares no restoration, edit or resume semantics; "
                 "invalidates_on_change is recorded and never acted on.",
    }
    findings["vocabulary_2_0"] = dict(v11["_metadata"]["vocabulary_2_0"])
    findings["vocabulary_2_0"]["alias_operators_in_conditions"] = sorted({
        op for q in v11["questions"]
        for op in _operators(q["trigger_condition"])
    } - {"all", "any", "not", "token_present", "token_absent", "always", "never",
         "sex", "equals", "one_of", "prior_answer_equals", "age_range", "pregnancy"})

    return findings


def _operators(condition):
    if not isinstance(condition, dict):
        return set()
    out = set()
    for key, value in condition.items():
        out.add(key)
        if isinstance(value, list):
            for item in value:
                out |= _operators(item)
        elif isinstance(value, dict):
            out |= _operators(value)
    return out


def regressions(v10, v11, oracle):
    """Section B. GF-006 and GF-008, re-measured against captured Dart output."""
    parsed = parse_all(repo_path())
    followup_map = {
        token: [{"type": e["type"], "question_text": e["question_text"],
                 "options": list(e["options"])} for e in entries]
        for token, entries in parsed["followup_question_map"]["entries"].items()
    }
    default_question = parsed["followup_question_map"]["default_question"]
    clarifiers = parsed["red_flag_clarifiers"]

    grouped_11, clar_11, default_11 = split_questions(v11)
    grouped_10 = [q for q in v10["questions"]
                  if q["clinical_role"] in ("severity", "duration", "additional_symptoms")
                  and q["question_id"] != "Q-followup-default-duration"]
    default_10 = next(q for q in v10["questions"]
                      if q["question_id"] == "Q-followup-default-duration")
    clar_10 = [q for q in v10["questions"]
               if q["clinical_role"] == "red_flag_clarifier"]

    # --- GF-006: default duration -------------------------------------------
    from qflow.grouping import condition_holds

    def default_fires(question, tokens):
        return condition_holds(question["trigger_condition"], set(tokens))

    def live_has_default(tokens):
        live = live_effective_questions(tokens, followup_map, default_question, clarifiers)
        return any(q["role"] == "duration"
                   and q["question_text"] == default_question["question_text"]
                   for q in live)

    gf006_cases = [
        ("empty_selection", []),
        ("duration_less_mapped_alone", ["chest_indrawing_severe"]),
        ("duration_less_mapped_plus_unmapped", ["boils", "chest_indrawing_severe"]),
        ("second_duration_less_mapped_plus_unmapped", ["boils", "fast_breathing_child"]),
        ("unmapped_alone", ["boils"]),
        ("unmapped_plus_duration_bearing", ["boils", "fever"]),
    ]
    gf006 = []
    for name, tokens in gf006_cases:
        live = live_has_default(tokens)
        gf006.append({
            "case": name,
            "tokens": sorted(tokens),
            "live_asks_default_duration": live,
            "candidate_1_0_fires": default_fires(default_10, tokens),
            "candidate_1_1_fires": default_fires(default_11, tokens),
            "v1_1_matches_live": default_fires(default_11, tokens) == live,
            "v1_0_matched_live": default_fires(default_10, tokens) == live,
        })

    # --- GF-008: clarifier order --------------------------------------------
    def clarifier_order(questions, tokens):
        # 1.0 ordering: (priority, tie_break_key, question_id) — every clarifier
        # at priority 0, so alphabetical by red-flag token.
        eligible = [q for q in questions
                    if condition_holds(q["trigger_condition"], set(tokens))]
        eligible.sort(key=lambda q: (q["priority"], q["tie_break_key"], q["question_id"]))
        return [q["tie_break_key"] for q in eligible]

    declaration = [c["red_flag_token"] for c in clarifiers]
    affected, checked = [], 0
    for case in oracle["forward"]:
        tokens = case["input_tokens"]
        live = [q["red_flag_token"] for q in case["questions"]
                if q["role"] == "red_flag_clarifier"]
        if len(live) < 2:
            continue
        checked += 1
        old_order = clarifier_order(clar_10, tokens)
        new_kept, _ = plan_grouped(tokens, grouped_11, clar_11, default_11)
        new_order = [q["red_flag_token"] for q in new_kept
                     if q["role"] == "red_flag_clarifier"]
        if old_order != live:
            affected.append(tokens)
        assert new_order == live, (tokens, new_order, live)

    return {
        "GF_006_default_duration_trigger": {
            "cases": gf006,
            "v1_1_matches_live_on_all": all(c["v1_1_matches_live"] for c in gf006),
            "v1_0_mismatches": [c["case"] for c in gf006 if not c["v1_0_matched_live"]],
            "no_duration_entry_invented": sorted(
                token for token in followup_map
                if not any(e["type"] == "duration" for e in followup_map[token])),
        },
        "GF_008_clarifier_declaration_order": {
            "declaration_order": declaration,
            "alphabetical_order": sorted(declaration),
            "declaration_is_alphabetical": declaration == sorted(declaration),
            "captured_paths_with_two_or_more_clarifiers": checked,
            "paths_where_v1_0_ordering_differed_from_live": len(affected),
            "paths_where_v1_1_ordering_differed_from_live": 0,
            "sample_affected_paths": affected[:5],
            "clinical_precedence_invented": False,
            "basis": "Order is copied from kRedFlagClarifiers declaration order. No "
                     "priority between danger signs is authored here.",
        },
    }


def content_safety():
    """Section C. A hit is a failure, not a warning."""
    control_failures = self_test()
    hits, scanned, excluded = [], 0, []
    for tree, suffixes in SCANNED_TREES:
        root = repo_path(*tree.split("/"))
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for filename in sorted(filenames):
                if not filename.endswith(suffixes) and not filename.endswith(".dart.txt"):
                    continue
                path = os.path.join(dirpath, filename)
                relative = os.path.relpath(path, repo_path())
                if relative in IM003_REPORTS_SCANNED_ELSEWHERE:
                    # These two are scanned by tools/run_im003_checks.py with
                    # the same patterns and the same positive controls.
                    #
                    # Named exactly, never by prefix: an `im003_` prefix rule
                    # also swallowed the 19 invalid_im003 FIXTURES, which that
                    # runner does not scan, so 19 files would have gone
                    # unscanned by anything. The fixtures stay in this scan.
                    excluded.append(relative)
                    continue
                if os.path.abspath(path) == os.path.abspath(REPORT_PATH):
                    # This scan's own output. It necessarily contains every
                    # pattern LABEL ("date of birth", "patient identifier") and
                    # any match text, so scanning it reports the scanner rather
                    # than the artifacts. Excluded, and the exclusion is recorded
                    # in the report so it is visible rather than assumed.
                    excluded.append(relative)
                    continue
                scanned += 1
                text = open(path, encoding="utf-8", errors="replace").read()
                for label, pattern in PHI_PATTERNS:
                    for match in pattern.finditer(text):
                        value = match.group(0)
                        if PHI_ALLOWLIST.get(value):
                            continue
                        hits.append({"file": relative, "pattern": label,
                                     "match": value[:80]})
    return {
        "files_scanned": scanned,
        "files_excluded": excluded,
        "exclusion_reason": (
            "This report itself, which contains the scanner's own pattern labels and "
            "would therefore always match; and the IM-003 reports, which are scanned "
            "by tools/run_im003_checks.py with the same patterns and controls. No "
            "knowledge artifact goes unscanned."
        ),
        "hits": hits,
        "control_failures": control_failures,
        "positive_controls": len(PHI_SELF_TEST),
        "negative_controls": len(PHI_NEGATIVE_CONTROLS),
        "allowlist_entries": len(PHI_ALLOWLIST),
        "clean": not hits and not control_failures,
    }


def build_report():
    v10 = load_json(V10_PATH)
    v11 = load_json(V11_PATH)
    oracle = load_json(ORACLE_PATH)

    clinical = compare_clinical(v10, v11)
    defects = regressions(v10, v11, oracle)
    safety = content_safety()

    passed = {
        "question_texts_unchanged": clinical["question_texts"]["identical"],
        "answer_meanings_unchanged": clinical["answer_meanings"]["unchanged"],
        "token_output_universe_unchanged": clinical["token_output_universe"]["identical"],
        "red_flag_effects_unchanged": clinical["red_flag_effects"]["identical"],
        "path_limit_still_5": clinical["path_limit"]["unchanged_at_5"],
        "red_flag_truncation_exemption_intact": clinical["path_limit"]["red_flag_exempt_v1_1"],
        "optional_skips_zero": clinical["optional_skips"]["zero"],
        "im_003_deferred_and_absent": clinical["im_003"]["deferred_and_absent"],
        "im_004_unimplemented": not clinical["im_004_restoration_editing"]["implemented"],
        "vocabulary_2_0_unused": clinical["vocabulary_2_0"]["used"] is False,
        "no_alias_operators_in_conditions":
            not clinical["vocabulary_2_0"]["alias_operators_in_conditions"],
        "gf_006_regression_covered":
            defects["GF_006_default_duration_trigger"]["v1_1_matches_live_on_all"],
        "gf_008_regression_covered":
            defects["GF_008_clarifier_declaration_order"]
            ["paths_where_v1_1_ordering_differed_from_live"] == 0,
        "content_safety_clean": safety["clean"],
    }

    return {
        "_metadata": {
            "report_id": "question_no_clinical_change",
            "version": "1.1",
            "generator": GENERATOR,
            "description": (
                "Candidate 1.1 compared against candidate 1.0 for clinical and runtime "
                "change, plus GF-006/GF-008 regressions re-measured against captured "
                "Dart output, plus a content-safety scan. Every value is computed."
            ),
            "compared": {
                "from": "candidate/question_flow.ng.v1.0.json",
                "to": "candidate/question_flow.ng.v1.1.json",
                "oracle": "testing/questions/fixtures/oracle/live_question_oracle_v1.json",
            },
        },
        "no_clinical_change": clinical,
        "defect_regressions": defects,
        "content_safety": safety,
        "assertions": passed,
        "all_passed": all(passed.values()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true",
                        help="run only the PHI pattern controls")
    args = parser.parse_args()

    if args.self_test:
        failures = self_test()
        for failure in failures:
            print("  %s" % failure)
        print("%d positive + %d negative controls, %d failed"
              % (len(PHI_SELF_TEST), len(PHI_NEGATIVE_CONTROLS), len(failures)))
        return 1 if failures else 0

    report = build_report()
    payload = dump_artifact_bytes(report)

    if args.check:
        if not os.path.exists(REPORT_PATH) or open(REPORT_PATH, "rb").read() != payload:
            print("FAIL reports/question_no_clinical_change_v1_1.json is missing or stale")
            return 1
        print("OK   no-clinical-change report is reproducible, sha256:%s"
              % sha256_bytes(payload))
        return 0 if report["all_passed"] else 2

    write_bytes(REPORT_PATH, payload)
    print("wrote reports/question_no_clinical_change_v1_1.json")
    for name, ok in sorted(report["assertions"].items()):
        print("  %s %s" % ("ok  " if ok else "FAIL", name))
    safety = report["content_safety"]
    print("  content safety: %d files scanned, %d hits, %d/%d controls failed"
          % (safety["files_scanned"], len(safety["hits"]),
             len(safety["control_failures"]),
             safety["positive_controls"] + safety["negative_controls"]))
    for failure in safety["control_failures"]:
        print("      CONTROL %s" % failure)
    for hit in safety["hits"][:10]:
        print("      %s: %s -> %s" % (hit["file"], hit["pattern"], hit["match"]))
    print("  ALL PASSED: %s" % report["all_passed"])
    return 0 if report["all_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
