#!/usr/bin/env python3
"""
E8.1 Case Bank generator for WellaPath CDSS.

Builds testing/case_bank_v1.json from:
  - kb.ng.v2.3.json          (50 conditions: symptoms, red_flags, modifiers, urgency_default)
  - rules.ng.v2.1.json       (global + condition-specific red flag rules)
  - mobile_handoff/condition_top5_symptom_tokens.json  (top-5 distinctive tokens/condition)

IMPORTANT — how expected_urgency is derived (this is the spec, NOT a copy of the engine):
The expected values below come from the knowledge base + rules spec and the agreed
escalation policy. They are intentionally independent of the engine implementation so that
the test run can catch engine bugs. Priority order used to derive expected_urgency:

  1. global red flag token present            -> emergency   (source: global_red_flag)
  2. condition-specific red flag token present -> emergency   (source: condition_specific_red_flag)
  3. demographic effect 'escalate_emergency'   -> emergency   (source: demographic_escalation)
  4c. demographic 'increase_urgency' + a seasonal modifier applied -> urgent
        (Case-04 "Option B" policy: this combination is URGENT, not EMERGENCY)
  4a. demographic 'increase_urgency' alone     -> escalate ONE tier from the default
        (self_care->non_urgent, non_urgent->urgent, urgent->urgent [capped])
  5. otherwise                                 -> the condition's urgency_default

NOTE: effects 'routine_caution', 'monitor_and_escalate', 'increase_base_weight' do NOT
change the urgency tier in the engine (increase_base_weight only affects scoring/top
condition). Cases that attach such a modifier therefore keep the default urgency, and
are labelled so.
"""
import json, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

with open(os.path.join(ROOT, "kb.ng.v2.3.json")) as f:
    KB = json.load(f)
with open(os.path.join(ROOT, "rules.ng.v2.1.json")) as f:
    RULES = json.load(f)
# Vendored copy of mobile_handoff/condition_top5_symptom_tokens.json (from the still-open
# feat/e9-symptom-token-mapping / PR #9). Replace with the real path once PR #9 merges.
with open(os.path.join(HERE, "condition_top5_symptom_tokens.vendored.json")) as f:
    TOP5 = json.load(f)

conditions = {c["condition_id"]: c for c in KB["conditions"]}
top5 = {t["condition_id"]: [s["token"] for s in t["top5_symptoms"]] for t in TOP5}

GLOBAL_RED_FLAGS = sorted({r["token"] for r in RULES["rules"] if r["applies_to"] == ["all"]})
# condition_id -> list of its condition-specific red flag tokens
COND_RED_FLAGS = collections.defaultdict(list)
for r in RULES["rules"]:
    if r["applies_to"] != ["all"]:
        for cid in r["applies_to"]:
            COND_RED_FLAGS[cid].append(r["token"])

TIER_UP = {"self_care": "non_urgent", "non_urgent": "urgent", "urgent": "urgent", "emergency": "emergency"}

def escalate_one(u):
    return TIER_UP.get(u, u)

def pick_demo(cond, preferred_effects):
    """Return (modifier_token, effect) for the first demographic modifier whose effect
    is in preferred_effects, else the first modifier, else (None, None)."""
    mods = cond.get("demographic_modifiers", [])
    for m in mods:
        if m["effect"] in preferred_effects:
            return m["modifier"], m["effect"]
    if mods:
        return mods[0]["modifier"], mods[0]["effect"]
    return None, None

def has_seasonal(cond):
    return bool(cond.get("seasonal_modifiers"))

def season_token(cond):
    s = cond.get("seasonal_modifiers", [])
    return s[0]["season"] if s else None

cases = []
counter = [0]
def add(target, desc, tokens, demo, season, exp_urg, exp_top, safety, note=None, exp_source=None):
    counter[0] += 1
    c = {
        "case_id": f"CB_{counter[0]:03d}",
        "condition_target": target,
        "description": desc,
        "input_tokens": tokens,
        "demographic_tokens": demo,
        "season": season,
        "expected_urgency": exp_urg,
        "expected_top_condition": exp_top,
        "safety_critical": safety,
    }
    if exp_source:
        c["expected_urgency_source"] = exp_source
    if note:
        c["note"] = note
    cases.append(c)

EMERGENCY_CONDITIONS = [cid for cid, c in conditions.items() if c["urgency_default"] == "emergency"]

# ---- 4 cases per condition (200 base) -----------------------------------------
for cid, cond in conditions.items():
    default = cond["urgency_default"]
    t5 = top5[cid]
    name = cond["condition_name"]

    # 1. Standard presentation, no modifiers -> urgency_default
    add(cid, f"{name}: standard presentation, adult, no modifiers",
        t5[:], [], None, default, cid,
        safety=(default == "emergency"),
        exp_source="urgency_default")

    # 2. With a relevant demographic modifier
    demo_tok, effect = pick_demo(cond, {"increase_urgency", "escalate_emergency"})
    if demo_tok is None:
        demo_tok, effect = pick_demo(cond, {"routine_caution", "monitor_and_escalate", "increase_base_weight"})
    if demo_tok is None:
        # no demographic modifiers at all -> repeat standard as a second variation
        add(cid, f"{name}: standard presentation, subset of symptoms",
            t5[:3], [], None, default, cid,
            safety=(default == "emergency"), exp_source="urgency_default",
            note="condition has no demographic modifiers")
    else:
        # Source rule: any effect the engine's urgency determiner acts on (Priority 3
        # escalate_emergency, Priority 4a increase_urgency) reports source
        # 'demographic_escalation' -- EVEN WHEN the escalated value equals the default
        # (e.g. capped at 'urgent', or an emergency-default condition). Effects the
        # determiner ignores (routine_caution / monitor_and_escalate / increase_base_weight)
        # fall through to Priority 5 and keep source 'urgency_default'.
        if effect == "escalate_emergency":
            exp = "emergency"; src = "demographic_escalation"; note = "escalate_emergency (Priority 3)"
        elif effect == "increase_urgency":
            exp = escalate_one(default); src = "demographic_escalation"
            note = "increase_urgency (Priority 4a), one tier up from default (may be capped)"
        else:
            exp = default; src = "urgency_default"; note = f"'{effect}' does not change urgency tier"
        add(cid, f"{name}: with demographic modifier '{demo_tok}'",
            t5[:4], [demo_tok], None, exp, cid,
            safety=(exp == "emergency"), exp_source=src, note=note)

    # 3. With a condition-specific red flag (or global if none) -> emergency.
    # expected_top_condition is null on all red-flag cases: urgency is red-flag-driven
    # and independent of which condition scores top. If the red-flag token is ALSO a
    # global danger sign, the global pass (Priority 1) fires first, so source is
    # global_red_flag (this is the case for road_traffic_injury_minor's circulatory_collapse).
    crf = COND_RED_FLAGS.get(cid, [])
    if crf:
        rf = crf[0]
        rf_global = rf in GLOBAL_RED_FLAGS
        add(cid, f"{name}: with {'global' if rf_global else 'condition-specific'} red flag '{rf}'",
            t5[:3] + [rf], [], None, "emergency", None,
            safety=True,
            exp_source="global_red_flag" if rf_global else "condition_specific_red_flag",
            note="red-flag token is also a global danger sign — global pass fires first" if rf_global else None)
    else:
        rf = "seizures"
        add(cid, f"{name}: with global danger sign '{rf}' (no condition-specific rule exists)",
            t5[:3] + [rf], [], None, "emergency", None,
            safety=True, exp_source="global_red_flag",
            note="condition relies on global danger signs only")

    # 4. With a global danger sign layered on a real presentation -> emergency
    add(cid, f"{name}: real presentation + global danger sign 'inability_to_drink'",
        t5[:3] + ["inability_to_drink"], [], None, "emergency", None,
        safety=True, exp_source="global_red_flag")

# ---- emergency conditions: +1 extra each (>=5 total) --------------------------
for cid in EMERGENCY_CONDITIONS:
    cond = conditions[cid]; t5 = top5[cid]; name = cond["condition_name"]
    add(cid, f"{name}: real presentation + global danger sign 'circulatory_collapse'",
        t5[:3] + ["circulatory_collapse"], [], None, "emergency", None,
        safety=True, exp_source="global_red_flag")

# ---- edge cases ---------------------------------------------------------------
# Empty input
add(None, "Edge: empty input — engine must not crash, returns safe default",
    [], [], None, "non_urgent", None, safety=False,
    exp_source="empty_default", note="matches E3.5 Case 12 behaviour")

# Each of the 13 global red flag tokens alone -> emergency
for tok in GLOBAL_RED_FLAGS:
    add(None, f"Edge: single global danger sign '{tok}' with no other input -> emergency",
        [tok], [], None, "emergency", None, safety=True,
        exp_source="global_red_flag", note="tests one of the 13 global rules")

# Single non-red-flag token only
add("malaria", "Edge: single common symptom 'fever' only",
    ["fever"], [], None, None, None, safety=False,
    exp_source="observe", note="expected_top/urgency indeterminate without scorer — observe actual")

# SAM vs MAM comparison on acute_diarrhoea
add("acute_diarrhoea", "Edge: diarrhoea + SEVERE malnutrition (SAM) -> emergency",
    ["watery_stool", "vomiting"], ["severe_malnutrition_sam"], None, "emergency", "acute_diarrhoea",
    safety=True, exp_source="demographic_escalation", note="SAM = escalate_emergency")
add("acute_diarrhoea", "Edge: diarrhoea + MODERATE malnutrition (MAM) -> urgent (NOT emergency)",
    ["watery_stool", "vomiting"], ["moderate_malnutrition_mam"], None, "urgent", "acute_diarrhoea",
    safety=False, exp_source="demographic_escalation",
    note="MAM = increase_urgency, one tier up from non_urgent default; must NOT be emergency")

# Seasonal present vs absent (cough_common_cold: default self_care, children_under_5 = increase_urgency)
add("cough_common_cold", "Edge: cold + under-5 demographic, NO season -> non_urgent (one tier up from self_care)",
    ["runny_nose", "mild_cough"], ["children_under_5"], None, "non_urgent", "cough_common_cold",
    safety=False, exp_source="demographic_escalation", note="increase_urgency alone, no seasonal")
add("cough_common_cold", "Edge: cold + under-5 demographic + harmattan season -> urgent (Priority 4c)",
    ["runny_nose", "mild_cough"], ["children_under_5"], "harmattan_season", "urgent", "cough_common_cold",
    safety=False, exp_source="demographic_escalation",
    note="increase_urgency + seasonal = Priority 4c -> urgent under Option B")

# Case-04 policy anchor (the reviewed decision)
add("malaria", "Edge: malaria + under-5 + rainy season, NO danger sign -> urgent (Case-04 Option B)",
    ["fever", "chills", "headache", "weakness"], ["children_under_5"], "rainy_season", "urgent", "malaria",
    safety=False, exp_source="demographic_escalation",
    note="Case-04 policy: URGENT not EMERGENCY when no danger sign present")
add("malaria", "Edge: malaria + under-5 alone, NO season -> urgent (default already urgent, capped)",
    ["fever", "chills", "headache", "weakness"], ["children_under_5"], None, "urgent", "malaria",
    safety=False, exp_source="demographic_escalation",
    note="increase_urgency (Priority 4a) fires; escalate_one(urgent)=urgent (capped, value unchanged) — source is still demographic_escalation")

# Conflicting symptoms across two conditions -> top condition observed, urgency indeterminate
add(None, "Edge: conflicting tokens from malaria + acute_diarrhoea -> observe top condition",
    ["fever", "chills", "watery_stool", "vomiting"], [], None, None, None,
    safety=False, exp_source="observe", note="two-condition overlap; observe scorer behaviour")
add(None, "Edge: conflicting tokens from cardio + dizziness -> observe top condition",
    ["chest_pain", "dizziness", "palpitations"], [], None, None, None,
    safety=False, exp_source="observe", note="observe scorer behaviour")

# Global red flag overrides a mild presentation
add("cough_common_cold", "Edge: mild cold + global danger sign 'seizures' -> emergency (override)",
    ["runny_nose", "mild_cough", "seizures"], [], None, "emergency", None,
    safety=True, exp_source="global_red_flag", note="danger sign overrides low-acuity condition")

# ---- assemble + coverage metadata ---------------------------------------------
safety_cases = [c for c in cases if c["safety_critical"]]
covered = {c["condition_target"] for c in cases if c["condition_target"]}
per_condition = collections.Counter(c["condition_target"] for c in cases if c["condition_target"])

bank = {
    "_metadata": {
        "artifact_id": "case_bank",
        "version": "1.0",
        "phase": "E8.1",
        "country": "ng",
        "built_from": {
            "knowledge_base": "kb.ng.v2.3.json",
            "rules": "rules.ng.v2.1.json",
            "top5_tokens": "mobile_handoff/condition_top5_symptom_tokens.json (from feat/e9-symptom-token-mapping)",
        },
        "valid_against_rules": "v2.1 and v2.2 — v2.2 removes rf_147 (RTI circulatory_collapse), which is "
            "behaviourally inert: circulatory_collapse still returns emergency via global rf_006. CB_159 "
            "already reflects this (source global_red_flag).",
        "total_cases": len(cases),
        "safety_critical_cases": len(safety_cases),
        "conditions_covered": len(covered),
        "global_red_flag_tokens_tested": len(GLOBAL_RED_FLAGS),
        "expected_value_derivation": "See build_case_bank.py header. Expected values are spec-derived "
            "(KB urgency_default + red flag rules + Case-04 Option B escalation policy), independent of "
            "the engine implementation, so the run can catch engine bugs.",
        "known_caveats": [
            "expected_top_condition is null on all red-flag cases (source global_red_flag or "
            "condition_specific_red_flag): urgency is red-flag-driven and independent of which condition "
            "scores top. It is asserted only on non-red-flag cases.",
            "expected_urgency_source uses the engine's actual emitted value 'demographic_escalation' for "
            "Priority 3 (escalate_emergency) and Priority 4a (increase_urgency) cases, including when the "
            "escalated value equals the default (capped, or emergency-default conditions).",
            "expected_top_condition for 'standard' cases assumes the condition's own top-5 tokens make it "
            "the top scorer. If the engine returns a different top condition, that is a real finding "
            "(cf. the headache token-reachability gap, Issue #8), not a case-bank error.",
            "Cases with expected_urgency_source='observe' have no asserted expected value; the runner should "
            "record actual output for human review rather than pass/fail.",
            "Priority-4c cases (increase_urgency + seasonal -> urgent) encode the Case-04 Option B policy. "
            "The updated engine source for 4c was reported by engineering but not independently verified at "
            "build time; if the engine still returns emergency here, that is the discrepancy to resolve.",
        ],
    },
    "coverage": {
        "cases_per_condition": dict(sorted(per_condition.items())),
        "emergency_conditions": EMERGENCY_CONDITIONS,
        "global_red_flag_tokens": GLOBAL_RED_FLAGS,
    },
    "cases": cases,
}

out = os.path.join(HERE, "case_bank_v1.json")
with open(out, "w") as f:
    json.dump(bank, f, indent=2, ensure_ascii=False)

# ---- self-check against exit criteria -----------------------------------------
print(f"total cases:            {len(cases)}")
print(f"conditions covered:     {len(covered)} / 50")
print(f"safety-critical cases:  {len(safety_cases)}")
print(f"global RF tokens tested: {len(GLOBAL_RED_FLAGS)} / 13")
under3 = {k: v for k, v in per_condition.items() if v < 3}
print(f"conditions with <3 cases: {under3 if under3 else 'none'}")
emerg_under5 = {c: per_condition[c] for c in EMERGENCY_CONDITIONS if per_condition[c] < 5}
print(f"emergency conditions with <5 cases: {emerg_under5 if emerg_under5 else 'none'}")
print(f"written: {out}")
