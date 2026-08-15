# Vocabulary 2.0 Catalogue Governance

How a proposed vocabulary item travels from "someone suggested it" to "published
in a versioned artifact" — and everywhere it is stopped along the way.

> **Nothing in the review package is approved.** Every reviewer decision is
> `pending`, every proposal is publication-blocked, and the candidate artifact
> is byte-identical to the one merged at `dceecde2`. This package exists so
> reviewers can decide, not to record a decision already made.

---

## 1. What this package is

| Artifact | Contents |
|---|---|
| `review/catalogue_v1/catalogue_review_v1.json` | 25 proposals in 8 batches, each with provenance, one primary class, risk flags and two pending decisions |
| `review/catalogue_v1/display_label_review_v1.json` | One review row for **all 295** canonical tokens |
| `review/catalogue_v1/impact_report_v1.json` | Counts by class, section, batch and approval state |
| `review/catalogue_v1/risk_summary_v1.json` | Every blocker, every unresolved flag, every carried-forward issue |
| `schema/catalogue_review.schema.json` | The proposal and decision contract |
| `tools/build_catalogue_review.py` | Deterministic generator (`--check` mode) |
| `tools/validate_catalogue.py` | Fail-closed validators |
| `testing/test_catalogue_review.py` | 57 checks including the pending dry run |

Inputs are committed and provenance-bearing:
`mobile_handoff/picker_scoring_gap_tokens.json`,
`mobile_handoff/red_flag_display_map.json`,
`proposals/catalogue_v1/mobile_display_labels.vendored.json`,
`proposals/catalogue_v1/roadmap_examples.json`, plus the frozen clinical
artifacts.

---

## 2. Reviewer responsibilities

| Role | Decides | Cannot decide |
|---|---|---|
| **Clinical reviewer** | Whether a phrase and a token describe the same clinical concept; whether an ambiguity set is safe; whether a label is clinically accurate and non-misleading | Product wording preferences; release timing |
| **Product reviewer** | Whether the wording is right for the audience; whether a label is comprehensible and non-stigmatising; whether a complaint grouping matches how users think | Whether two tokens are clinically equivalent |
| **Engineering lead** | Whether a blocking class may proceed once clinical and product have approved; whether regression evidence is sufficient | Clinical equivalence |
| **Knowledge Base / Data** | Generates artifacts from approved decisions; never authors an approval | Any approval |

**Both** clinical and product decisions are required on every proposal. An
approval by one alone leaves the item blocked.

---

## 3. Risk classes

Every proposal carries **exactly one** primary class. Six are non-blocking;
the rest block publication and require clinical review. This mirrors
`VOCABULARY_CHANGE_CLASSIFICATION.md`.

| Class | Blocks publication |
|---|---|
| `display_label_only` | No |
| `search_alias` | No |
| `ambiguous_search_term` | No |
| `complaint_group_metadata` / `body_area_metadata` / `severity_metadata` / `duration_metadata` | No |
| `canonical_token_addition` / `rename` / `merge` / `deprecation` | **Yes** |
| `clinical_token_identity` | **Yes** |
| `scoring_affecting_association` | **Yes** |
| `red_flag_affecting_association` | **Yes** |
| `insufficient_evidence_do_not_propose` | **Yes** (it is a question, not a proposal) |

Secondary risk flags may be `no`, `yes` or **`unresolved`**. `unresolved` is a
legitimate answer and blocks approval. **It must not be downgraded to `no` to
clear a batch** — that is the single easiest way to launder an unreviewed risk,
and `validate_catalogue.py` recomputes eligibility so the downgrade would have
to be argued in a diff rather than slipped through.

---

## 4. The alias vs. token-identity boundary

An alias is a **search phrase that resolves to exactly one existing canonical
token**. It has no entry of its own, no `scoring_eligible` flag, and no data
path to a score.

A proposal stops being an alias the moment it would **connect two existing
canonical scoring tokens**. At that point it changes which conditions a user can
reach, which is a clinical-token-identity decision.

Before an alias may be approved, each of these must be answered `no` — or the
proposal is blocked:

erases laterality · erases anatomical location · erases severity · erases
duration · erases negation · merges adult and paediatric · merges
pregnancy-specific and general · merges symptom and diagnosis · changes scoring
eligibility · alters red-flag reachability · connects two existing scoring
tokens.

### The worked example: `breathlessness` → `shortness_of_breath`

`mobile_handoff/picker_scoring_gap_tokens.json` proposes this as an alias. It is
not one:

| Token | KB weights |
|---|---|
| `breathlessness` | `lower_respiratory_infection` (7) |
| `shortness_of_breath` | `sari` (9), `asthma` (8), `cardio_symptoms` (7) |

Both are existing canonical scoring tokens. Mapping one to the other changes the
condition set a user can reach across **four conditions**. It is therefore
classified `clinical_token_identity`, is publication-blocked, and **has not been
implemented**. Both tokens remain independent and active.

This is the pattern to apply to any future "just an alias" proposal: check what
each side already scores before believing the label.

---

## 5. Ambiguity policy

An ambiguous term maps to two or more candidates and **must never auto-resolve**.
The resolver returns `ambiguous` with a null token; the user chooses, or nothing
is selected.

- An ambiguity set needs ≥ 2 distinct, resolvable members.
- It may not pre-select a candidate.
- A set containing a red-flag token is `red_flag_affecting` and blocks
  publication — escalating a near-miss to a red flag is a clinical decision.

The 12 near-miss sets in `red_flag_display_map.json` are exactly this case: e.g.
`confusion` / `lethargy` near `altered_consciousness`. Whether a near-miss
should escalate is for the clinical reviewer, not the resolver.

---

## 6. Local-language sourcing policy

**No local-language term appears in this package, and none may be added without
an attributable source.**

There is no authoritative Hausa, Yoruba, Igbo or Nigerian Pidgin vocabulary
source in this repository. Nothing was translated, inferred, or taken from a web
translation service. The gap is recorded as **OPEN** in the impact report.

To close it, a sourced catalogue is required — a named clinical or linguistic
authority, a dated user-research session, or a published health-communication
glossary — with the same provenance fields every other proposal carries.

---

## 7. Batch approval process

Batches exist so a low-risk label decision is never bundled into the same
approval switch as a token-identity decision.

| Batch | Tier | Count |
|---|---|---|
| `BATCH-01-display-labels` | low | 8 |
| `BATCH-02-search-aliases` | low | 0 |
| `BATCH-03-ambiguity` | medium | 0 |
| `BATCH-04-metadata` | medium | 0 |
| `BATCH-05-scoring-affecting` | blocking | 0 |
| `BATCH-06-red-flag-affecting` | blocking | 12 |
| `BATCH-07-token-identity` | blocking | 1 |
| `BATCH-08-evidence-gaps` | blocking | 4 |

Every batch states in the artifact what approval **would** and **would not**
authorize. Approving `BATCH-01` authorizes showing an approved label for a token
that already exists and already carries its weight. It does **not** set
`display_safe`, add a token, change a weight, or approve publication.

**Process:** review a batch → record each decision with a named reviewer, date
and rationale → re-run `python3 tools/run_w2_checks.py` → eligibility is
recomputed. Never hand-edit `publication_eligible`; the validator recomputes it
and fails on disagreement.

---

## 8. Publication prerequisites

An item is publishable only when **all** hold:

1. Clinical decision is `approved` or `approved_with_revision`, with a named reviewer.
2. Product decision likewise.
3. No risk flag is `unresolved`.
4. Provenance is complete, and any approval claim has a resolvable evidence link.
5. The primary class is non-blocking, or the engineering lead has separately signed off a blocking class.

Then, for the artifact as a whole: clinical review recorded on the candidate, a
regenerated versioned artifact, a re-run 239-case regression, engineering-lead
approval, R2 upload, and a live-manifest entry. Those gates live in
`candidate/manifest.candidate.json` and are all currently `false`.

**Display-safety has its own rule: no token becomes `display_safe` because a
label already exists** — not the derived canonical label, and not the label
shipping in Mobile today. 117 of the 295 tokens have a Mobile label; none of
them is thereby approved.

---

## 9. Rollback expectations

Nothing here is live, so there is nothing to roll back operationally. If a batch
is approved and later regretted:

- Revert the decision records and re-run the checks; eligibility recomputes to
  blocked.
- If an approved catalogue had already been built into a new artifact version,
  the rollback target is the previous published version — `token_dictionary` 1.1,
  sha256 `0cc47ad9…5c019` — via `VOCABULARY_ROLLBACK.md`. Consumers verify every
  artifact against its expected hash on each read, so reverting the manifest
  entry is sufficient.
- The candidate is never edited in place; a content change is a new version.

---

## 10. Instructions for Mobile after approval

Mobile's consumer is already implemented and inactive (merge `a269168`). After
an approved catalogue is published, Mobile needs **no new search logic**:

1. Wait for a published, versioned artifact and a live `/config` manifest entry.
   Do not consume the candidate.
2. Update the pinned artifact version and hash. `StagedArtifactLoader` verifies
   on every read.
3. Only tokens whose display decision is approved and whose `display_safe` is
   true may be shown. Until then keep `kSymptomDisplayMap`.
4. Aliases and metadata continue to be search-only; the canonical-token boundary
   is unchanged and must stay the only path into assessment state.
5. Re-run the 239-case regression. Approved content that changes reachability
   requires the case bank to be re-run before release, not after.
6. Enable the evaluation gate for internal evaluation only. Production stays
   blocked until separately approved.

**Do not implement `breathlessness` → `shortness_of_breath`** unless and until
that specific proposal is approved as a clinical-token-identity change with
regression evidence.

---

## 11. Carried-forward unresolved issues

Recorded in `risk_summary_v1.json`, none repaired in this step:

| ID | Status |
|---|---|
| Three IMCI tier keys — `pneumonia`, `severe_pneumonia`, `very_severe_disease` | unresolved |
| `breathlessness` vs `shortness_of_breath` | unresolved — decision required |
| Case-bank clinical sign-off | unresolved |
| CB_211 Option B vs C, due before external beta | unresolved (Option D holds it fail-closed) |
| Mobile issue #38 — malaria base weight in mixed presentation | unresolved |
| No documented scoring tie-break | absent by design — CB_232 margin was 5, so no tie-break was exercised |
