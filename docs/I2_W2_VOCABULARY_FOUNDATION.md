# I2 / W2 — Symptom Vocabulary 2.0 Foundation

**Phase:** I2 — Clinical Input Layer
**Workstream:** W2 — Symptom Vocabulary & Search 2.0, Step 1 (contract-defining)
**Owner:** Knowledge Base / Data Engineering
**Status:** foundation complete · candidate unpublished · nothing clinically approved

---

## 1. Scope

Establish the backward-compatible, versioned vocabulary foundation that Backend
and Mobile can build against without guessing, and resolve the Top-50 case-bank
baseline.

**Deliberately out of scope:** broad symptom expansion. No alias, body-area
association, complaint group, severity/duration descriptor or reviewer name was
added. The schema holds them; nothing fills them yet, because no approved
catalogue exists in this repository and guessing would put unreviewed clinical
content into a distributed artifact. `docs/VOCABULARY_EXPANSION_REQUEST.md` is
the route in.

---

## 2. Frozen baseline

Recorded from the committed bytes. No frozen artifact was re-serialized,
reformatted or rewritten.

| Artifact | Version | SHA256 | Bytes |
|---|---|---|---|
| `token_dictionary.ng.v1.1.json` | 1.1 | `0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019` | 8,820 |
| `kb.ng.v2.4.json` | 2.4 | `6c00d8257f8417e86bd5e237630bf8a4623ad72e2e46b1b071dd447c067cec2b` | 102,118 |
| `rules.ng.v2.2.json` | 2.2 | `1d27e854cba95b179577a88f92445400f494a7fe8e6a53a60fcaa98b3870d1c4` | 29,082 |
| `facilities.ng.v1.1.json` | 1.1 | `25684c714367abf2f3c305c8a5597b5f7eb0d11baaf658c5b9e2f8f5e2982398` | 1,695,844 |
| `testing/case_bank_v1.json` | 1.0 | `c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834` | 138,988 |

All five match the E9.1 freeze recorded in `progress.md` and in the backend's
`docs/SECURITY_CHECKLIST.md`. Byte identity is asserted in CI.

### Baseline numbers

| Metric | Value |
|---|---|
| Total tokens | 295 |
| symptom / red_flag / duration / body_area / demographic / severity | 164 / 65 / 10 / 18 / 26 / 12 |
| Referenced tokens | 240 |
| Unused tokens (no consumer anywhere) | 55 |
| Duplicate normalized labels | 0 |
| Cross-category duplicate tokens | 0 |
| Token ID format violations | 0 |
| Tokens whose change would affect red flags | 50 |
| Tokens whose change would affect scoring | 163 |

Full detail: `reports/baseline_freeze_v1.json`,
`reports/token_reference_graph_v1.json`.

### One pre-existing defect found, recorded, not fixed

Three IMCI severity tier keys used by `pneumonia_children.severity_levels` —
`pneumonia`, `severe_pneumonia`, `very_severe_disease` — do not resolve against
`token_dictionary` 1.1. `schema/kb_schema_v1.0.json` lists all four IMCI keys as
valid *and* states that severity keys must be values from `severity_tokens`;
only `no_pneumonia` is actually in the dictionary. The schema contradicts itself.

**Assessed impact on behaviour: none.** Scoring reads
`conditions[].symptoms[].token`; red-flag evaluation reads `rules[].token`. No
engine path resolves a severity tier *key* against the dictionary.

**Not fixed here.** Both remedies — adding three tokens, or correcting the kb
schema — are vocabulary or frozen-artifact changes needing clinical review, and
W2 Step 1 changes neither. Recorded in
`reports/baseline_freeze_v1.json` → `known_baseline_findings`, and the
reference check fails on any *new* unresolved reference so this cannot become
cover for a future one. **Follow-up needed.**

---

## 3. Schema decision

| Decision | Value | Why |
|---|---|---|
| Artifact ID | `token_dictionary`, **unchanged** | Backend keys `/config` on it, Mobile reads `artifacts['token_dictionary']`, and a backend regression test asserts it. Renaming to `vocabulary` breaks three things for a cosmetic gain. |
| Schema version | 1.0 → **2.0** | Fields added. |
| Artifact version | 1.1 → **2.0** | Repository policy (`kb_schema_v1.0.json`): "Major bump for schema changes, minor for content changes". A schema change forces the major. |
| Filename | `token_dictionary.ng.v2.0.json` | `<artifact_id>.<country>.v<version>.json` convention. |
| Location | `candidate/` | The root is the published-artifact directory. An unapproved file there is one careless upload from shipping. |

The version was derived from repository policy, not taken from the brief.

### Structure — additive, dual representation

The six schema 1.0 token arrays are carried forward **byte identical**, and
everything new sits under four new top-level keys:

```
_metadata                     extended, legacy _metadata preserved verbatim
symptom_tokens ... severity_tokens    unchanged — the schema 1.0 surface
body_areas                    NEW — derived from body_area_tokens
complaint_groups              NEW — empty, none approved
tokens                        NEW — per-token entries
search_index                  NEW — generated inverted index
```

Each `tokens[]` entry separates **clinical identity** from **search** and
**display**:

| Block | Class | May affect scoring |
|---|---|---|
| `clinical_identity` | clinical | yes — this is the only such block |
| `display` | display-only | no |
| `search` | search-only | no |
| `associations` | search-only | no |
| `review` | clinical (governance) | no |

**Aliases cannot become scoring tokens.** An alias is a string inside
`search.aliases`. It has no `token_id` and no `scoring_eligible` flag, so there
is no data path from an alias to a score. That is structural, not a convention.

Field-by-field semantics — type, required, allowed values, normalization,
uniqueness, max length, ordering, duplicate behaviour, case/Unicode/punctuation/
whitespace handling, validation failures, backward compatibility, and the four
governance flags (clinical-or-search, Mobile-may-display, rules-may-reference,
may-affect-scoring) — are in `schema/token_dictionary_schema_v2.0.json`.
The machine-validatable contract is `schema/token_dictionary.v2.schema.json`
(JSON Schema draft 2020-12).

---

## 4. Migration method

Generated by `tools/build_vocabulary_v2.py`. Never hand-edited.

**Deterministic:** fixed generation timestamp, no clock or randomness, stable
iteration over the source arrays, canonical serialization
(`indent=2`, `ensure_ascii`, no trailing newline — the convention the existing
artifacts already follow). Two runs produce identical bytes and an identical
SHA256.

**Lossless, and proved rather than asserted:** `project_to_v1_1()` rebuilds the
six token arrays **from the new `tokens[]` entries alone** and reproduces
`token_dictionary.ng.v1.1.json` **byte for byte**. It runs at build time — a
candidate that fails the projection never reaches disk — and again in the test
suite. A passing projection proves `tokens[]` encodes the source without loss.

**Derived values** (mechanical, reproducible, none of it clinical authoring):

- `display.canonical_label` — from the token ID, stamped
  `derived_from_token_id` / `unreviewed` / `display_safe: false`;
- `search.normalized_form` — `normalize(token_id)`;
- `clinical_identity.introduced_in_artifact_version` — by diffing
  `token_dictionary.ng.v1.0.json` against v1.1 (evidence, not guesswork);
- `body_areas` — from the existing `body_area_tokens`;
- `search_index.normalized_forms` — generated from `tokens[]`.

**Left empty deliberately:** aliases, all four association arrays, complaint
groups, and every reviewer field. See §1.

**Result:** 295 → 295 tokens. Zero added, zero removed, zero renamed, zero
merged, zero deprecated. `kb.ng.v2.4.json` and `rules.ng.v2.2.json` untouched.

---

## 5. Normalization and ambiguity

Full contracts: `docs/VOCABULARY_NORMALIZATION_SPEC.md`,
`docs/VOCABULARY_AMBIGUITY_SPEC.md`.

Normalization is pure, total, idempotent and deterministic: variant-fold (on both
sides of NFKC), NFKC, casefold, delete apostrophes, punctuation to single spaces
with digit-internal `.` and `/` preserved and digit-internal `,` deleted, collapse
whitespace. Hyphens become **spaces, not nothing**.

Absent by design: stemming, plural folding, spelling correction, edit distance,
substring/prefix matching, stopword removal, diacritic stripping. Negation,
laterality, severity, duration, age and pregnancy words all survive verbatim.

Matching is **whole-string equality**, so `no fever` cannot reach `fever`.

Five match states — `exact_canonical`, `exact_alias`, `normalized`, `ambiguous`,
`no_match`. `resolved_token_id` is non-null only when exactly one candidate
survives, and `scoring_eligible` is true if and only if `resolved_token_id` is
non-null. An ambiguous input therefore cannot be scored.

Candidate ordering is `(matched_via, category name, token_id)` — a fixed
lexicographic sort with **no clinical priority**. Ranking red flags first would
be server-side clinical inference inside a retrieval contract, and would train
users to pick the first option.

---

## 6. Case-bank status

**The canonical case bank was never missing.**

It is committed in this repository at `testing/case_bank_v1.json` — 239 cases,
v1.0, E8.1, covering all 50 conditions, 150 safety-critical cases and all 13
global red-flag rules. Git provenance runs from `ba7815e` (PR #13) through
`c974100` (PR #19).

What is missing is a copy at the *mobile* repository's default fixture path,
`test/fixtures/case_bank_v1.json`. That is a distribution gap between two
repositories, not absent case data. Mobile's harness skips rather than fails when
the file is absent, and says so in its own header — a correctly reported missing
input, not a silent pass.

Nothing was restored, reinterpreted or invented; the file is byte identical to
the E9.1 freeze. The copy command is in the Mobile handoff §9.

Keeping four things apart, as `reports/case_bank_status_v1.json` does:

| Dimension | Status |
|---|---|
| Harness readiness | ✅ ready — exists in mobile, on `develop` and three other branches |
| Case-data availability | ✅ available — 239 cases, this repository, hash verified |
| Clinical approval | ⚠️ **engineering-approved and spec-derived, NOT recorded as clinician-signed-off.** The case bank schema has no reviewer field at all. |
| Executable regression result | ❌ **stale** — last recorded run was 234 cases against kb **2.3**; the bank now has 239 and the freeze is kb **2.4** |

### What this means for W2

The candidate **cannot** regress clinical output through this bank, because it
changes no clinical input: kb 2.4, rules 2.2 and the accepted token set are all
byte identical, proven by `tools/check_compatibility.py`.

But *cannot regress by construction* is not *proven unchanged by execution*, and
this document does not claim the latter.

> **Existing Top-50 behaviour is proven unchanged structurally, not by an
> executed 239-case run against kb 2.4. It is NOT certified.**

This does not block W2 Step 1, which publishes nothing. It **does** block any
future vocabulary change classified beyond search-only metadata.

---

## 7. Compatibility results

26 checks in `tools/check_compatibility.py`, all passing.

| Claim | Evidence |
|---|---|
| All kb 2.4 token references resolve | symptoms, red_flags, severity values, demographic modifiers |
| All rules 2.2 token references resolve | all 75 rules, including all 13 global red-flag rules |
| All question-flow token references resolve | 239 case-bank inputs and demographics |
| No scoring weight changed | `kb.ng.v2.4.json` byte identical |
| No red-flag trigger changed | `rules.ng.v2.2.json` and `kb.ng.v2.4.json` byte identical |
| No condition ranking changed by the migration | kb bytes and the accepted input token set both unchanged |
| No question behaviour changed | accepted token set unchanged |
| Mobile can ignore every new field | see below |

### Old-consumer compatibility — measured, not assumed

`lib/core/engine/red_flag_evaluator.dart` reads exactly two keys of the token
dictionary — `symptom_tokens` and `red_flag_tokens` — as lists, keeping only
string members. A repository-wide search finds no other read.

Both arrays are byte identical to v1.1. **The shipped Mobile build loads the
candidate with no code change and behaves identically.** A Python test
reproduces the Dart token-set construction verbatim and compares.

**No Mobile code update is required to load the candidate.** An update is
required only to *use* the new metadata. The one case that does need new code:
a schema 2.0-aware build receiving a **1.1** artifact (rollback, or stale cached
config) must branch on the presence of the `tokens` key — not on a parsed version
string — and degrade to the legacy arrays without throwing.
`docs/VOCABULARY_VERSION_NEGOTIATION.md` §4.

---

## 8. Change classification

`tools/classify_vocabulary_diff.py` assigns every difference exactly one class,
and the class decides who must approve it. Blocking classes:
`clinical_token_identity`, `red_flag_affecting`, `scoring_rule_affecting`,
`question_flow_affecting`, `deprecation_removal`. A token-identity change
escalates to inherit the strongest clinical role the token plays, read from the
frozen consumers at classification time.

**Result for this migration:** `search_only_metadata` only — "new top-level keys
added". No blocking class.

A clean classification is **not** an approval.
`reports/baseline_diff_v1.json` carries a separate `publication_decision` block
with `may_publish: false`.

---

## 9. Publication status

| Gate | State |
|---|---|
| Classification gate | ✅ passed |
| Schema + content validation (45 checks) | ✅ passed |
| Compatibility (26 checks) | ✅ passed |
| Test suite (91 tests) | ✅ passed |
| Clinical review of schema 2.0 | ❌ not performed |
| Engineering-lead approval | ❌ not recorded |
| 239-case regression against kb 2.4 | ❌ not re-run |
| Uploaded to R2 | ❌ no |
| **Live `/config` manifest** | ✅ **UNCHANGED** |
| **May publish** | ❌ **no** |

No file in `wellapath-backend` or `wellapath-mobile` was modified by this work.

---

## 10. Blocked clinical inputs

Needed before W2 can move past the foundation:

1. **Approved source catalogue for aliases and vocabulary expansion.** None
   exists. Recommended first batch: promote the merged
   `mobile_handoff/red_flag_display_map.json` labels and body areas for 12
   global red-flag tokens, with clinical sign-off on each label. Small, already
   reviewed once for a related purpose, and it addresses a recorded beta gap.
2. **Clinical reviewer metadata** for any label or alias promoted to
   `display_safe`.
3. **Clinical sign-off, or an explicit decision, on case bank v1.0.** It is
   engineering-approved; no clinician approval is recorded, and the schema has
   no field for one.
4. **Decision on the three IMCI severity tier keys** (§2).
5. **Approval for the `breathlessness` → `shortness_of_breath` alias proposal**
   (PR #24). Both are live scoring tokens; this is a `clinical_token_identity`
   change, not a search tweak.

---

## 11. Downstream contracts

| Consumer | Package |
|---|---|
| Backend | `backend_handoff/vocabulary_v2/README.md` |
| Mobile | `mobile_handoff/vocabulary_v2/README.md` + `vocabulary_types.dart` |

Both state plainly that no action is required now beyond the case-bank copy.

---

## 12. Verification

```bash
python3 tools/run_w2_checks.py
```

11 checks: report freshness, artifact reproducibility, manifest freshness,
fixture freshness, schema conformance, 45 content validators, 26 compatibility
checks, 91 unit tests. Standard library only — no `pip install`, no network.

Every generated file is regenerable and checked for staleness, so a hand-edit
turns CI red instead of shipping.

---

## 13. Rollback

`docs/VOCABULARY_ROLLBACK.md`. Since nothing is published, rollback of this
change is a `git revert` of the PR: no frozen artifact was modified and no live
manifest was touched.
