# Vocabulary Ambiguity & Match Resolution Specification

**Status:** contract for `token_dictionary` schema 2.0
**Resolver version:** `1.0.0`
**Reference implementation:** `tools/vocab/resolve.py`
**Conformance fixtures:** `testing/vocabulary/fixtures/search/ambiguity_cases_v1.json`

---

## 1. The rule this document exists to enforce

> An ambiguous input is never resolved to a clinical token, and never scored.

The vocabulary reports what a query *could* mean. Choosing between candidates is
the approved Mobile question flow's job, driven by a human answering a question.
It is not the vocabulary's job, and it is emphatically not the backend's — the
architecture places no clinical inference server-side.

---

## 2. The five match states

```
exact_canonical  ->  exact_alias  ->  normalized  ->  ambiguous  ->  no_match
```

Evaluated in precedence order; the first that produces candidates wins.

| Status | Condition | `resolved_token_id` | `scoring_eligible` |
|---|---|---|---|
| `exact_canonical` | Query equals a stable token ID, byte for byte | the token ID | `true` |
| `exact_alias` | Query equals an authored alias string, byte for byte, and that alias belongs to exactly one token | the owning token ID | `true` |
| `normalized` | `normalize(query)` matches exactly one entry in the index | the matching token ID | `true` |
| `ambiguous` | An exact-alias or normalized match yields **two or more** candidates | `null` | `false` |
| `no_match` | Nothing matched | `null` | `false` |

`scoring_eligible` is `true` **if and only if** `resolved_token_id` is non-null.
That invariant is asserted in the resolver and tested directly. An engine that
honours it cannot score an unresolved ambiguity.

Matching is **whole-string equality** at every stage. There is no substring,
prefix, or edit-distance matching anywhere.

---

## 3. Result shape

```jsonc
{
  "query": "chest pain",              // as supplied, unmodified
  "query_normalized": "chest pain",   // per the normalization spec
  "status": "normalized",             // one of the five above
  "resolved_token_id": "chest_pain",  // null unless exactly one candidate
  "scoring_eligible": true,           // null resolved_token_id => false
  "resolver_version": "1.0.0",
  "candidates": [
    {
      "token_id": "chest_pain",
      "category": "symptom_tokens",
      "matched_via": "canonical_token_id",  // canonical_token_id | canonical_label | alias
      "safe_display_label": null,           // null unless display_safe is true
      "display_safe": false,
      "status": "active",                   // active | deprecated
      "replaced_by": null
    }
  ]
}
```

### `safe_display_label`

Null whenever the token's label has not been clinically approved. A consumer
building a disambiguation prompt must use its own approved display map when this
is null, and **must never fall back to rendering the raw token ID** — `csm` and
`vhf_suspected` are not words a caregiver can act on.

In the W2 Step 1 candidate, every label is mechanically derived and unreviewed,
so `safe_display_label` is null for all 295 tokens.

---

## 4. Candidate ordering

Candidates are sorted by, in order:

1. **`matched_via` rank** — `canonical_token_id` (0) < `canonical_label` (1) < `alias` (2).
2. **Category rank** — the plain lexicographic order of the category key:
   `body_area_tokens`, `demographic_tokens`, `duration_tokens`,
   `red_flag_tokens`, `severity_tokens`, `symptom_tokens`.
3. **`token_id`** ascending, by codepoint.

The ordering is total, stable and reproducible: no ties can remain, so two
implementations cannot disagree.

### Why the ordering carries no clinical priority

It would be easy — and wrong — to sort red flags first so the "dangerous" option
appears at the top. That would be server-side clinical inference embedded in a
retrieval contract, and it would train users to pick the first option, turning a
retrieval convenience into a triage decision nobody reviewed. Category rank is
therefore plain alphabetical order of the category *name*, which is arbitrary by
construction and visibly so.

Ordering also has no effect on outcome. It is presentation order for a list the
user chooses from; it never collapses an ambiguity, and `resolved_token_id`
stays `null` regardless of how the list is sorted.

**No ordering input is ever a diagnosis probability, a condition score, a
severity weight, or any other clinical quantity.**

---

## 5. Consumer obligations

A consumer of this contract must:

1. **Not auto-select on `ambiguous`.** Present the candidates; let the user pick.
2. **Not score an unresolved query.** Only feed the engine a token where
   `scoring_eligible` is `true`.
3. **Not fall back to "first candidate"** as a shortcut on `ambiguous`.
4. **Not display a candidate whose `display_safe` is `false`** using vocabulary
   text; use the consumer's own approved display map.
5. **Not auto-substitute `replaced_by`.** A deprecation pointer is a migration
   aid for authors and the picker, not a runtime rewrite. Substituting silently
   changes clinical meaning without review.
6. **Treat `no_match` as "not understood"**, never as "no symptom present". They
   are different clinical statements.

---

## 6. Worked examples

Against the real candidate vocabulary:

| Query | Status | Resolved | Note |
|---|---|---|---|
| `chest_pain` | `exact_canonical` | `chest_pain` | the token ID itself |
| `Chest Pain` | `normalized` | `chest_pain` | case + separator |
| `chest-pain` | `normalized` | `chest_pain` | hyphen folds to a space |
| `no fever` | `no_match` | — | negation preserved; does **not** reach `fever` |
| `fevers` | `no_match` | — | no stemming |
| `feve` | `no_match` | — | no prefix matching |
| `fver` | `no_match` | — | no fuzzy matching |
| `zzzznotatoken` | `no_match` | — | unknown term |
| `` (empty) | `no_match` | — | |

The real vocabulary currently has **zero ambiguous normalized forms** — 295
tokens, no label collisions, no aliases. Ambiguity is therefore demonstrated
against a clearly labelled synthetic non-clinical vocabulary
(`testing/vocabulary/fixtures/search/synthetic_vocabulary_v1.json`), which never
enters a release artifact:

| Query | Status | Resolved | Candidates |
|---|---|---|---|
| `shared quux` | `ambiguous` | `null` | `zorble_alpha`, `zorble_beta` |
| `SHARED  QUUX!` | `ambiguous` | `null` | same — reached via normalization |
| `beta only` | `exact_alias` | `zorble_beta` | unique alias |
| `quibble widget` | `ambiguous` | `null` | one token's label collides with another's ID form |
| `quibble_widget` | `exact_canonical` | `quibble_widget` | the exact ID beats the colliding label |

---

## 7. Why aliases can collide at all

Two tokens sharing an alias is **permitted**, because the alternative is worse.
Forbidding collisions would push authors to attach a shared phrase to exactly
one token — silently deciding, at authoring time and without a clinician, which
meaning a user "really" intended. Allowing the collision surfaces the ambiguity
to the person who actually knows: the user.

What is forbidden:

- an alias duplicated **within one entry** after normalization (a no-op that
  only inflates the index) — hard validation failure;
- an alias equal to **its own** entry's canonical form — same;
- an alias that **shadows another token's canonical form**, i.e. typing token A's
  canonical name produces an ambiguity involving token B — hard validation
  failure unless an approved expansion request records the ambiguity as
  intended.

All three are enforced by `tools/validate_vocabulary.py` (group `C.metadata`)
and each has a dedicated invalid fixture.

---

## 8. Conformance

```bash
python3 testing/vocabulary/test_vocabulary_v2.py
```

`AmbiguityTests` and `SearchFixtureTests` cover the full contract, including
that ordering is deterministic across index rebuilds and that only
single-candidate statuses are ever scoreable.
