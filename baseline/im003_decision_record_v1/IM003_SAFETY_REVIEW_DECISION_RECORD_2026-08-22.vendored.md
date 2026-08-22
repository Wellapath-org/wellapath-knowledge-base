<!--
  VENDORED HUMAN DECISION RECORD — DO NOT EDIT.

  Supplied by the engineering lead in the I2/W3 Step 9 brief as chat text on
  22 August 2026 (no file artifact existed; this file IS the transcription of
  record). Named reviewer identity was NOT supplied with the record and is
  deferred: "for the reviewer name and product list we can add it later."
  Until a named, qualified Clinical reviewer is recorded, nothing in this
  record is clinical approval, and every disposition derived from it carries
  Product authority only.

  Authoritative KB baseline at receipt: 83cd52583a14ec9fb656fae6be18ec0df3877a70
  Mobile PR #76 at receipt: OPEN, unmerged, head 13be0d4937b1c49d6a49ddf096c5d5b6a47c2091
-->

I2/W3 IM-003 Safety Review — Decision Record

Safety blocker: IM003-SB-001
Review status: OPEN — CLINICAL RULE REQUIRED
D004: PENDING
IM-003: DISABLED
Mobile PR #76: DO NOT MERGE
Reviewer role: Clinical Reviewer + Product Lead
Review date: 22 August 2026

Overall determination

IM003-SB-001 is not resolved.

Step 8A establishes a material safety concern: additive re-branching can cause the displayed urgency to decrease even though an emergency-default condition remains credibly represented in the ranked result.

In S10, lassa_fever does not disappear and its score does not decrease. It remains at score 26 with an emergency default, but moves from rank 1 to rank 3 because newly accumulated evidence increases other conditions' scores. The system then changes the displayed urgency from emergency to urgent because urgency is derived only from the first-ranked condition.

That behaviour should not be accepted as safe without an explicit clinical rule governing urgency across ranked conditions.

The broader results reinforce the need for that rule: 63 measured scenarios produced 25 urgency changes and 31 top-condition changes. Although 24 urgency changes were escalations and only one was a de-escalation, a single credible emergency→urgent transition is sufficient to require clinical resolution before activation.

This review therefore does not authorize implementation, merging, publication, activation, beta exposure, or production deployment.

Clinical decisions

1. Emergency → urgent while an emergency condition remains credibly ranked

Decision: NOT ACCEPTABLE UNDER THE CURRENT RULE.

An emergency-to-urgent transition should not occur merely because additive evidence causes another condition with a lower default urgency to become rank 1 while the previously identified emergency-default condition remains credibly ranked.

The important distinction is between:

evidence that genuinely makes the emergency hypothesis no longer clinically credible; and

evidence that merely causes another condition to obtain a higher ranking score.

S10 demonstrates the latter on the evidence supplied.

Required follow-up: Clinical must define what makes a ranked emergency condition sufficiently credible to affect final urgency.

Resolves IM003-SB-001: No.
Changes D004: No; D004 remains pending.

2. Urgency monotonicity under additive evidence

Decision: PROVISIONALLY REQUIRED AS A SAFETY INVARIANT FOR IM-003.

For the purposes of IM-003, additional symptom evidence should not reduce an already-established urgency unless Clinical explicitly defines and validates circumstances in which de-escalation is safe.

This is deliberately narrower than declaring that all future WellaPath assessment logic must always be mathematically monotonic.

The current evidence supports a safety requirement for IM-003 adaptive re-branching:

Adding evidence must not lower the assessment's established urgency solely as a consequence of condition re-ranking.

Clinical may subsequently approve an explicit de-escalation mechanism, but IM-003 should not implicitly introduce one through ranking behaviour.

Required follow-up: Convert this provisional invariant into an explicit clinically approved rule and regression requirement.

Resolves IM003-SB-001: No.
Changes D004: No.

3. Source of final urgency

Decision: CLINICAL RULE REQUIRED — DO NOT SELECT AN ALGORITHM IN PRODUCT REVIEW.

I do not approve any of the three proposed mechanisms at this stage:

first-ranked condition only;

highest urgency among ranked conditions;

score/confidence threshold.

The evidence demonstrates that first-ranked condition only is insufficiently safe for IM-003 as currently exercised, because ranking movement can indirectly de-escalate urgency.

However, automatically taking the highest urgency of every ranked condition could introduce systematic over-triage. A score/confidence threshold similarly requires clinical calibration that cannot be invented by Product.

The required clinical question is:

When does a ranked condition have sufficient clinical support that its urgency classification must contribute to the final assessment urgency?

Clinical should define that rule first. Engineering can then implement it deterministically.

Resolves IM003-SB-001: No.
Changes D004: No.

4. Clinical plausibility of S10

Decision: NOT ESTABLISHED BY THE EVIDENCE PROVIDED.

The supplied transition identifies S10 and its ranking outcome but does not provide the complete symptom/demographic evidence needed to make a defensible clinical determination about plausibility or intended-population applicability.

It should therefore not be dismissed as an unrealistic edge case on the information presently available.

Required follow-up: Clinical reviewer must inspect the complete S10 evidence vector, demographics, triggering answers and assessment context.

Resolves IM003-SB-001: No.

5. lassa_fever → malaria ranking transition

Decision: NO CLINICAL APPROVAL GIVEN.

The numerical transition is demonstrated:

lassa_fever 26 → rank 3
malaria 25 → 52 → rank 1

But score movement alone does not establish that the resulting ranking is clinically appropriate.

Product should not infer clinical correctness from the scoring output.

Required follow-up: Clinical review of the S10 evidence against the intended meaning of the condition scoring/ranking model.

Resolves IM003-SB-001: No.

6. Does Lassa fever at 26/rank 3 require emergency urgency?

Decision: REQUIRES CLINICAL DETERMINATION.

The available evidence establishes that lassa_fever remains unchanged at score 26 and carries an emergency default. It does not establish whether score 26 constitutes sufficient clinical credibility to force emergency urgency.

That threshold is exactly the missing clinical policy exposed by Step 8A.

Until that policy exists, the system must not assume that falling from rank 1 to rank 3 makes the emergency implication irrelevant.

Resolves IM003-SB-001: No.

7. Scope of the IM-003 block

Decision: ADAPTIVE RE-BRANCHING REMAINS BLOCKED; A CONSTRAINED SUBSET MAY BE EVALUATED SEPARATELY BUT NOT ACTIVATED BY THIS DECISION.

There is no need to prohibit investigation of structurally constrained variants.

A subset may be brought back for separate review if Engineering can demonstrate that it cannot:

reduce established urgency;

suppress or bypass applicable red flags;

remove clinically material evidence;

change clinical semantics through ranking alone; or

otherwise introduce an unreviewed de-escalation path.

Such a subset would require its own evidence and explicit approval. This decision does not pre-authorize it.

8. Additional clinical regression cases

Decision: ADDITIONAL SAFETY REGRESSION COVERAGE REQUIRED.

Before IM-003 is reconsidered, the regression set should include at minimum:

emergency condition rank 1 → rank 2/3 while its score is unchanged;

emergency condition rank 1 → lower rank while its score increases;

emergency condition entering the ranking after additive evidence;

multiple simultaneous emergency-default conditions;

emergency + urgent and emergency + non-urgent ranking competition;

red-flag and non-red-flag versions of otherwise similar evidence;

cases around whatever clinical qualification/score boundary is ultimately approved;

repeated re-branching across several answer cycles;

paediatric, pregnancy and other population-specific cases where applicable;

cases demonstrating any clinically approved de-escalation behaviour, if de-escalation is ultimately permitted.

The final regression suite must test displayed urgency, not merely ranking stability.

Product decisions

1. Is dynamic re-branching desirable?

Decision: YES IN PRINCIPLE; NOT AT THE COST OF SAFETY PREDICTABILITY.

Dynamic re-branching has a legitimate product benefit: later user answers can make subsequent questioning more relevant.

That benefit does not justify allowing ranking mechanics to silently weaken an already-established safety disposition.

Product therefore continues to support IM-003 as a concept, subject to the clinical safety rule being resolved.

2. Is urgency monotonicity a required Product safety invariant?

Decision: YES FOR IM-003 UNLESS CLINICAL EXPLICITLY APPROVES A DE-ESCALATION RULE.

From the user's perspective, it is problematic for an assessment to establish emergency urgency and then silently become merely urgent because another condition overtakes the first condition in an internal ranking.

Product therefore requires:

Re-ranking alone must never cause urgency de-escalation.

This requirement does not prevent Clinical from defining a legitimate evidence-based de-escalation mechanism separately.

3. User explanation when urgency changes

Decision: EXPLAIN ESCALATION, NOT INTERNAL CONDITION RANKING.

WellaPath should not tell users that urgency changed because "malaria replaced lassa_fever as the top condition", or otherwise expose diagnostic-looking ranking logic.

Where additional answers cause an escalation, acceptable product language would be along the lines of:

Based on the additional information you provided, we recommend getting care more urgently.

The interface should communicate the care recommendation, not an inferred diagnosis or internal ranking.

No emergency→urgent explanatory copy is approved because the underlying clinical circumstances in which such de-escalation would be safe have not yet been defined.

4. Internal evaluation

Decision: KEEP IM-003 EXCLUDED FROM USER-FACING INTERNAL EVALUATION.

Engineering/clinical investigation may continue in controlled test environments, but the adaptive behaviour should remain disabled in any evaluation where users could rely upon its urgency result.

This remains true until the clinical urgency aggregation/de-escalation rule is approved and the resulting implementation passes the required regression suite.

Decision summary

Item | Decision
Emergency → urgent in S10 | Not acceptable under current rule
IM-003 urgency monotonicity | Required provisionally
Rank-1-only urgency | Not approved for IM-003
Replacement urgency algorithm | Requires Clinical definition
S10 clinical plausibility | Clinical review required
Lassa → malaria ranking validity | Clinical review required
Rank-3 Lassa requiring emergency | Clinical rule required
IM-003 adaptive re-branching | Blocked
Constrained subset investigation | Permitted for review/testing only
Dynamic re-branching product value | Supported in principle
User-facing urgency explanation | Care-oriented, non-diagnostic
Internal user-facing evaluation | Blocked
IM003-SB-001 | OPEN
D004 | PENDING
Mobile PR #76 | UNMERGED

Evidence reviewed

This decision is based on the supplied Step 8A evidence:

63 measured scenarios;

25 urgency changes;

24 escalations;

1 de-escalation;

31 top-condition changes;

0 red-flag changes;

S10 baseline lassa_fever 26 / emergency at rank 1;

S10 expanded malaria 52 / urgent at rank 1;

lassa_fever 26 / emergency retained at rank 3;

displayed urgency changing emergency → urgent;

urgency source remaining urgency_default;

no red-flag transition.

No broader clinical validation evidence was supplied with this decision request, so the unresolved clinical questions above are deliberately not inferred from general medical knowledge.

Authorization boundaries

AUTHORIZED: further analysis, clinical review, regression-case design, safety-rule specification, and development of proposals/evidence for subsequent review.

NOT AUTHORIZED: implementation of a chosen urgency aggregation rule, merge of Mobile PR #76, publication, activation of IM-003, user-facing internal evaluation of the adaptive behaviour, external beta, or production deployment.
