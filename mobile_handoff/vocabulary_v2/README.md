# Mobile Handoff — Symptom Vocabulary 2.0 (candidate)

**From:** Knowledge Base / Data Engineering
**Phase:** I2 / W2 Step 1
**Action required from Mobile right now:** **none for the vocabulary.** One
unrelated ask in §9 (the case bank) that is worth doing this week.

---

## 1. Bottom line

- The candidate vocabulary is **not published and not clinically approved**. Do
  not ship a build that depends on it.
- **Your current build already loads it correctly, with no code change.** That
  is measured, not assumed — see §3.
- This package is here so the contract is not guessed. Types, normalization
  rules, the ambiguity model and fixtures are all included.

---

## 2. Artifact

| Field | Value |
|---|---|
| Artifact ID | `token_dictionary` (unchanged) |
| Version | `2.0` |
| Schema version | `2.0` |
| Location | `candidate/token_dictionary.ng.v2.0.json` (knowledge-base repo) |
| SHA256 | `07f935967acb1d5515cb53ffd1c8e39b59b8daf85c67cf36fa3e25094e34cd2d` |
| Bytes | `339948` |
| Release status | `candidate_unapproved` |
| Tokens | 295 — **identical set to v1.1**, zero added, zero removed |
| Rollback target | `token_dictionary.ng.v1.1.json` |

---

## 3. Backward compatibility — why your current build is fine

`lib/core/engine/red_flag_evaluator.dart` reads exactly two keys of the token
dictionary:

```dart
final symptomTokensList = tokenDictionary['symptom_tokens'];
final redFlagTokensList = tokenDictionary['red_flag_tokens'];
```

Nothing else in `lib/` reads the artifact. Both arrays are **byte identical** to
v1.1, as are the other four legacy arrays. Everything schema 2.0 adds lives under
new top-level keys your build never reads.

Asserted by `tools/check_compatibility.py`:

- `legacy_arrays_identical`
- `mobile_surface_identical`
- `mobile_valid_input_token_set_unchanged`
- plus a Python test that reproduces the Dart token-set construction verbatim

**No Mobile code update is required to load the candidate.** An update is
required only to *use* the new metadata.

---

## 4. Schema at a glance

```jsonc
{
  "_metadata": { "version": "2.0", "schema_version": "2.0", "release_status": "candidate_unapproved", ... },

  // schema 1.0 surface — byte identical to v1.1, keep reading these
  "symptom_tokens":     [ "abdominal_cramps", ... ],   // 164
  "red_flag_tokens":    [ "abnormal_bleeding", ... ],  //  65
  "duration_tokens":    [ ... ],                       //  10
  "body_area_tokens":   [ ... ],                       //  18
  "demographic_tokens": [ ... ],                       //  26
  "severity_tokens":    [ ... ],                       //  12

  // new in schema 2.0
  "body_areas":       [ { "body_area_id": "chest", "canonical_label": "Chest", "display_safe": false } ],
  "complaint_groups": [],                              // empty — none approved yet
  "tokens": [
    {
      "token_id": "chest_pain",
      "category": "symptom_tokens",
      "clinical_identity": { "canonical_token_id": "chest_pain", "status": "active",
                             "replaced_by": null, "scoring_eligible": true,
                             "introduced_in_artifact_version": "1.0" },
      "display":  { "canonical_label": "Chest pain", "label_source": "derived_from_token_id",
                    "label_review_status": "unreviewed", "display_safe": false, "locale": "en-NG" },
      "search":   { "normalized_form": "chest pain", "aliases": [], "search_only": true },
      "associations": { "body_areas": [], "complaint_groups": [],
                        "severity_descriptors": [], "duration_descriptors": [] },
      "review":   { "review_status": "not_reviewed", "clinical_reviewer": null,
                    "review_date": null, "provenance": "migrated_from_..." }
    }
  ],
  "search_index": { "normalization_version": "1.0.0", "resolver_version": "1.0.0",
                    "normalized_forms": { "chest pain": ["chest_pain"], ... } }
}
```

### Fields that are search-only and MUST NOT affect scoring

Everything under `search`, `associations` and `display`:

| Field | Class |
|---|---|
| `search.normalized_form` | search-only |
| `search.aliases` | search-only |
| `associations.body_areas` | search-only (picker routing) |
| `associations.complaint_groups` | search-only (grouping) |
| `associations.severity_descriptors` | search-only — **does not set severity** |
| `associations.duration_descriptors` | search-only — **does not set duration** |
| `display.*` | display-only |
| `search_index.*` | search-only |

Only `token_id` reaches the engine, and only when a match resolved to exactly
one candidate. `kb.severity_levels` remains the sole clinical severity
mechanism, and it is untouched.

---

## 5. What is empty, and why

Every optional metadata field is empty in this candidate: no aliases, no body-area
associations, no complaint groups, no severity/duration descriptors, no reviewer
names.

That is deliberate. No approved catalogue for any of them exists in this
repository yet, and filling them with plausible guesses would put unreviewed
clinical content into a distributed artifact. `docs/VOCABULARY_EXPANSION_REQUEST.md`
is how real content gets in, and it names `red_flag_display_map.json` as the
recommended first batch.

**Practical consequence:** the candidate does not yet replace your
`symptom_display_map.dart`. `display_safe` is `false` for all 295 tokens, so
keep using your own approved display map and treat `safe_display_label` as null.

---

## 6. Typed definitions

`vocabulary_types.dart` in this directory. Plain data classes, no dependencies
beyond `dart:core`. Copy to `lib/core/vocabulary/` and adjust the header for
local lint rules.

Two deliberate choices worth noting:

- `VocabularyMatchResult.scoringEligible` is **recomputed** from
  `resolvedTokenId != null` rather than read from the wire. The invariant is
  what makes the contract safe, so it is derived rather than trusted.
- `vocabularyMatchStatusFromJson` maps an unrecognised status to `noMatch`.
  Fail closed: treating an unknown state as resolved would score something
  nobody validated.

---

## 7. Normalization and ambiguity

Full contracts: `docs/VOCABULARY_NORMALIZATION_SPEC.md`,
`docs/VOCABULARY_AMBIGUITY_SPEC.md`.

**You may not need to implement normalization at all.** The artifact ships
`search_index.normalized_forms`, so the common path is: normalize the query,
look the string up. Only the query side needs a local `normalize()`.

Pipeline summary — variant-fold, NFKC, casefold, delete apostrophes, punctuation
to spaces (digit-internal `.` and `/` survive, digit-internal `,` is deleted),
collapse whitespace. Hyphens become **spaces, not nothing**.

Explicitly absent: stemming, plural folding, spelling correction, edit distance,
substring/prefix matching, stopword removal, diacritic stripping.

**Five match states**, in precedence order:

| Status | `resolvedTokenId` | `scoringEligible` |
|---|---|---|
| `exact_canonical` | token ID | true |
| `exact_alias` | token ID | true |
| `normalized` | token ID | true |
| `ambiguous` | **null** | **false** |
| `no_match` | null | false |

### Obligations

1. On `ambiguous`, present the candidates and let the user choose. Do not take
   `candidates.first`.
2. Never score a token unless `scoringEligible` is true.
3. Never display a candidate whose `displaySafe` is false using vocabulary text;
   use your own display map. **Never render a raw token ID to a caregiver.**
4. Never auto-substitute `replacedBy`.
5. `no_match` means "not understood", not "symptom absent".

Candidate ordering is `(matchedVia, category name, tokenId)` — a fixed
lexicographic sort carrying **no clinical priority**. Sorting red flags first
would be clinical inference in a retrieval contract and would train users to
pick the first option.

---

## 8. Offline behaviour and forward compatibility

Resolution works from the artifact file alone: no network, no sidecar, no
server call. Asserted by `test_offline_load_needs_only_the_artifact_file`.

Branch on **the presence of the `tokens` key**, not on a parsed version string:

```dart
final artifact = VocabularyArtifact.fromJson(json);
if (!artifact.hasVocabularyMetadata) {
  // schema 1.0 artifact — rollback, or a stale cached /config.
  // Fall back to the legacy arrays and the existing display map.
  // Do NOT throw. Do NOT block the assessment. Offline triage must still work.
}
```

Ignore unknown keys and unknown object properties rather than rejecting the
artifact.

---

## 9. The one thing worth doing this week — the case bank

Unrelated to the vocabulary, but it resolves the recorded "six skipped Top-50
case-bank tests".

**The canonical case bank was never missing.** It is committed at
`wellapath-knowledge-base/testing/case_bank_v1.json` — 239 cases, v1.0, SHA256
`c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834`. What is
missing is a copy at your default fixture path. The skip is a correctly reported
missing input, not a silent pass.

```bash
cd wellapath-mobile
mkdir -p test/fixtures
cp ../wellapath-knowledge-base/testing/case_bank_v1.json test/fixtures/case_bank_v1.json
shasum -a 256 test/fixtures/case_bank_v1.json
# must print c7bdc434a33d341e21e015f0defe567274d7f6271c332352b19ba21e7d998834

flutter test test/engine/case_bank_validation_test.dart
```

Or without copying:

```bash
flutter test test/engine/case_bank_validation_test.dart \
  --dart-define=CASE_BANK_PATH=/absolute/path/to/wellapath-knowledge-base/testing/case_bank_v1.json
```

Notes before you run it:

- The bank now has **239** cases; the last recorded run covered 234 against
  **kb 2.3**. Pin the run to **kb 2.4 / rules 2.2** — the E9.1 freeze.
- Three cases carry `expected_urgency_source: "observe"`. Record actual output;
  do not grade them.
- Any under-triage on a `safety_critical: true` case is a release blocker.
  Surface it immediately.
- Do not "fix" a case to match the engine. A mismatch is a finding.

Full status, including what is and is not clinically approved:
`reports/case_bank_status_v1.json`.

---

## 10. Fixture package

| File | Contents |
|---|---|
| `testing/vocabulary/fixtures/search/search_cases_v1.json` | 34 queries against the **real** vocabulary with expected status, normalized form, resolved token and candidate list |
| `testing/vocabulary/fixtures/search/ambiguity_cases_v1.json` | 11 queries covering the ambiguity contract |
| `testing/vocabulary/fixtures/search/synthetic_vocabulary_v1.json` | Clearly labelled **synthetic non-clinical** vocabulary the ambiguity cases run against |
| `testing/vocabulary/fixtures/invalid/` | 21 invalid artifacts, one defect each, with the validator check each must trip |

Every query in `search_cases_v1.json` is an existing token ID or a mechanical
variation of one. No clinically meaningful synonym was invented to pad coverage —
a made-up mapping like `"belly ache" -> abdominal_pain` would be an unreviewed
clinical claim disguised as a test.

Ambiguity is demonstrated against the synthetic vocabulary because the real one
currently has **zero** ambiguous forms: 295 tokens, no label collisions, no
aliases. The synthetic file carries `SYNTHETIC_FIXTURE: true` and a warning
banner, and never enters a release artifact.

Use these as golden fixtures for your Dart implementation. If your resolver
reproduces all 45 expectations, it conforms.

---

## 11. Do not

- Do not ship a build depending on the candidate before approval is confirmed.
- Do not let any `search`, `associations` or `display` value influence scoring,
  red flags, urgency or ranking.
- Do not auto-resolve an `ambiguous` result.
- Do not render a raw token ID to a caregiver.
- Do not send symptom tokens or user query text to the backend. Resolution is
  on-device; the no-PHI posture is unchanged.
