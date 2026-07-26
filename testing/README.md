# E8.1 Case Bank — Data Engineer Deliverable

Definitive pre-beta validation set for the WellaPath CDSS engine across all 50 conditions.

## Files

- **`case_bank_v1.json`** — the deliverable. 234 test cases.
- `build_case_bank.py` — deterministic generator. Re-run to regenerate byte-identical output.
- `condition_top5_symptom_tokens.vendored.json` — vendored copy of the E9 handoff file (from the still-open PR #9 / `feat/e9-symptom-token-mapping`). Swap for the real `mobile_handoff/` path once PR #9 merges.

## Case schema

```json
{
  "case_id": "CB_001",
  "condition_target": "malaria",
  "description": "Malaria: standard presentation, adult, no modifiers",
  "input_tokens": ["fever", "chills", "headache", "sweating", "body_pain"],
  "demographic_tokens": [],
  "season": null,
  "expected_urgency": "urgent",
  "expected_top_condition": "malaria",
  "safety_critical": false,
  "expected_urgency_source": "urgency_default"
}
```

## Coverage (meets E8.1 exit criteria 1–4, 6)

| Requirement | Target | This bank |
|---|---|---|
| Total cases | ≥ 200 | **234** |
| Conditions covered | 50 (≥3 each) | **50 (4+ each)** |
| Emergency conditions | 10 (≥5 each) | **10 (≥5 each)** |
| Global red flag rules tested | 13 | **13** (single-token cases CB_213–225) |
| Safety-critical cases | — | **150** |

Edge cases (CB_212–234): empty input, all 13 global danger signs individually, single-token,
SAM vs MAM comparison, seasonal present vs absent, the Case-04 policy anchor, conflicting
two-condition inputs, and a global-danger-sign override of a low-acuity condition.

## How `expected_urgency` was derived — READ THIS

Expected values are **spec-derived, not copied from the engine**, so the run can actually
catch engine bugs. Priority order (see `build_case_bank.py` header for full detail):

1. global red flag token → `emergency`
2. condition-specific red flag token → `emergency`
3. demographic `escalate_emergency` → `emergency`
4c. demographic `increase_urgency` **+ seasonal** → `urgent` (Case-04 **Option B** policy)
4a. demographic `increase_urgency` alone → escalate one tier from default
5. otherwise → `urgency_default`

`routine_caution` / `monitor_and_escalate` / `increase_base_weight` do **not** change the
urgency tier.

## Caveats the runner must respect

- **`expected_urgency_source: "observe"`** (3 cases) — no asserted expected value. Record
  actual output for human review; do **not** mark pass/fail.
- **`expected_top_condition` on standard cases** assumes the condition's own top-5 tokens make
  it the top scorer. If the engine returns a different top condition, that is a **real finding**
  (cf. the headache token-reachability gap, Issue #8) — not a case-bank error.
- **Priority-4c cases** encode the Option B policy (increase_urgency + seasonal → urgent). The
  updated 4c engine source was reported by engineering but not independently verified at build
  time. If the engine still returns `emergency` for these, that is the discrepancy to resolve —
  flag it, don't silently "fix" the case bank to match.

## Runner output (mobile engineer)

Per exit criteria 5–8, write results to `testing/case_bank_results_v1.json` recording per case:
`actual_urgency`, `actual_top_condition`, `pass`/`fail`, and on fail `under_triage` vs
`over_triage`. **Any under-triage on a `safety_critical: true` case is a release blocker** —
surface it immediately, do not wait for the full run.
