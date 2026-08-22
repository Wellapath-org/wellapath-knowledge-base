# IM-003 Step 9 — Product Disposition and Clinical Rule Requirements

**Phase:** I2 / W3 Step 9 · **Owner:** Knowledge Base / Data Engineering
**Source:** I2/W3 IM-003 Safety Review — Decision Record, 22 August 2026
**Authority of every disposition below:** **Product** — see reviewer identity

| Record | Path |
|---|---|
| Vendored decision record | `baseline/im003_decision_record_v1/IM003_SAFETY_REVIEW_DECISION_RECORD_2026-08-22.vendored.md` |
| Structured disposition | `reports/im003_disposition_v1.json` |
| Validators | `python3 tools/validate_im003_disposition.py` (72 checks, 28 mutation proofs) |
| Blocker registry (unchanged) | `reports/im003_safety_blockers_v1.json` |

---

## 1. Reviewer identity — the Step 9A authoritative record

| Field | Value |
|---|---|
| **Product reviewer** | **Ayodele John Oluwaseyi** |
| Product reviewer role/title | Co-Founder & CEO, WellaPath |
| Product review date | 2026-08-22 |
| **Clinical reviewer** | **null** — `not_assigned` |
| Clinical approval | **false** |
| **Effective authority** | **`product`** — never `clinical` or `clinical_and_product` |

The source record's combined wording — *"Reviewer role: Clinical Reviewer +
Product Lead"* — is retained only as a faithful record of the source text and
is **superseded** by the fields above. It does **not** mean a Clinical
reviewer participated: none did, and none is assigned.

All six Product decisions (IM003-PD-001…006) are attributed to
**Ayodele John Oluwaseyi** in the stated Product role. All seven clinical
items remain **open requirements, not decisions** — none is a
Product-approved clinical rule.

Enforced by validation, each with a mutation proof: name/title/date must be
present and non-blank; effective authority must be exactly `product`; the
combined wording must not imply clinical participation; the clinical reviewer
must stay `null`/`not_assigned` together (no fabricated reviewer, no
`assigned` status without an identity); the Product reviewer must not be
described as a qualified Clinical reviewer without a separate explicit
record; the Step 9 identity-deferral note must not return; clinical approval
must stay false.

## 2. Required classification

| Item | State |
|---|---|
| IM003-SB-001 | **OPEN** |
| D004 | **PENDING** |
| IM-003 | **DISABLED** |
| Mobile PR #76 merge authorization | **FALSE** |
| Product disposition | **RECORDED** |
| Clinical rule | **REQUIRED, NOT APPROVED** |
| Clinical approval | **FALSE** |
| User-facing internal evaluation | **BLOCKED** |
| External beta | **BLOCKED** |
| Production | **BLOCKED** |

The generator refuses to write at all if the live blocker registry or decision
package contradicts this classification.

## 3. Product decisions (the only decisions here)

| ID | Decision |
|---|---|
| IM003-PD-001 | Dynamic re-branching is supported **in principle** — not at the cost of safety predictability. |
| IM003-PD-002 | **Re-ranking alone must never cause urgency de-escalation.** |
| IM003-PD-003 | IM-003 urgency monotonicity is **required** unless Clinical approves an explicit de-escalation rule. |
| IM003-PD-004 | User explanations communicate **care urgency**, never internal condition ranking or diagnosis. No emergency→urgent explanatory copy is approved. |
| IM003-PD-005 | IM-003 stays **excluded from user-facing internal evaluation**. |
| IM003-PD-006 | Constrained alternatives may be **investigated in tests** — not pre-approved, not activated by this decision. |

## 4. Open clinical requirements (questions, not decisions)

| ID | Clinical must define |
|---|---|
| IM003-CR-001 | When a ranked condition has enough support for its urgency to affect the final assessment. |
| IM003-CR-002 | Whether and when urgency may de-escalate after additive evidence. |
| IM003-CR-003 | Whether urgency considers one condition, multiple qualifying conditions, or a calibrated threshold. |
| IM003-CR-004 | Whether S10 is clinically plausible and in scope. |
| IM003-CR-005 | Whether the lassa_fever → malaria ranking transition is clinically appropriate. |
| IM003-CR-006 | Whether Lassa fever at score 26 / rank 3 requires emergency urgency. |
| IM003-CR-007 | Required population-specific and ranking-competition regression cases. |

None of the three urgency mechanisms (first-ranked-only, highest-among-ranked,
score/confidence threshold) is selected or approved. Selecting one is a
**clinical definition task** and must not happen in Product review.

## 5. Provisional safety invariant — IM003-INV-001

> **For IM-003, adding evidence must not lower the assessment's established
> urgency solely as a consequence of condition re-ranking.**

- Status: **provisional, pending an explicit clinical rule**. Not clinically
  approved.
- Scope: **IM-003 adaptive re-branching only.** It is deliberately **not**
  generalized to all WellaPath behaviour; generalization requires separate
  clinical approval.
- Clinical may supersede it with an explicit, validated de-escalation rule;
  IM-003 must not introduce one implicitly through ranking behaviour.
- Validation fails if the invariant is omitted, weakened (any of its elements
  — additive evidence, no lowering, established urgency, re-ranking as sole
  cause — removed), generalized, or called clinically approved.

## 6. Required regression case classes (IM003-RC-01…10)

1. Emergency condition rank 1 → rank 2/3 while its score is **unchanged**
2. Emergency condition rank 1 → lower rank while its score **increases**
3. Emergency condition **newly entering** the ranking after additive evidence
4. **Multiple** simultaneous emergency-default conditions
5. Emergency + urgent and emergency + non-urgent **ranking competition**
6. **Red-flag and non-red-flag** versions of otherwise similar evidence
7. **Boundary cases** around whatever clinical qualification/score boundary is approved
8. **Repeated re-branching** across several answer cycles
9. Paediatric, pregnancy and other **population-specific** cases
10. Any **clinically approved de-escalation** cases, if ever permitted

> The suite must assert **displayed urgency directly**. Ranking stability
> alone is insufficient.

## 7. Authorization boundaries

**Authorized:** further analysis · clinical review · regression-case design ·
safety-rule specification · development of proposals/evidence for later review.

**Not authorized:** implementing a chosen urgency aggregation rule · merging
Mobile PR #76 · publication · IM-003 activation · user-facing internal
evaluation of the adaptive behaviour · external beta · production deployment.

**Investigation permission is not activation permission** — enforced as a
validated field, with a mutation proof.

## 8. What this step changed — and did not

Changed: this document, the vendored record, `reports/im003_disposition_v1.json`,
the generator/validator pair, the IM-003 check suite wiring, progress notes.

Not changed: any clinical artifact, weight or urgency default; scoring, ranking
or red-flag logic; question candidates; runtime behaviour; publication or
distribution state; the blocker registry and decision package (still open /
pending, byte-identical); Mobile and Backend. Mobile PR #76 remains **open and
unmerged** at `13be0d49…`.
