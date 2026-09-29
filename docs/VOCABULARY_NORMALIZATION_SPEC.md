# Vocabulary Normalization Specification

**Status:** contract for `token_dictionary` schema 2.0
**Normalization version:** `1.0.0`
**Reference implementation:** `tools/vocab/normalize.py`
**Conformance fixtures:** `testing/vocabulary/fixtures/search/search_cases_v1.json`

Mobile and Backend must reproduce this function exactly. Where an implementation
and this document disagree, that is a defect in one of them — not a licence to
diverge.

The generated artifact ships `search_index.normalized_forms`, so the common case
needs no re-implementation at all: normalize the query, look the string up. A
consumer only needs its own `normalize()` for the query side.

---

## 1. Signature

```
normalize(value: String) -> String
```

Properties, all covered by tests in `testing/vocabulary/test_vocabulary_v2.py`:

| Property | Meaning |
|---|---|
| Pure | Output depends only on the input string. No locale, clock, randomness, dictionary or network. |
| Total | Every string input yields a string output. Never throws on content. |
| Idempotent | `normalize(normalize(x)) == normalize(x)`. |
| Deterministic | Identical input yields identical output on every platform and every run. |

A non-string input is a programming error and raises.

---

## 2. Pipeline

Applied in this order. Each step is individually tested.

### Step 1 — Variant folding (before and after NFKC)

Three character classes are folded to an ASCII representative:

| Class | Codepoints | Folds to |
|---|---|---|
| Apostrophe-like | `U+2018` `U+2019` `U+201B` `U+02B9` `U+02BB` `U+02BC` `U+00B4` `U+0060` | `'` (U+0027) |
| Dash-like | `U+2010`–`U+2015`, `U+2212`, `U+FE58`, `U+FE63` | `-` (U+002D) |
| Space-like | `U+00A0` `U+1680` `U+2000`–`U+200A` `U+200B` `U+202F` `U+205F` `U+3000` `U+FEFF` | ` ` (U+0020) |

The fold runs **on both sides of NFKC**. Some of these characters are themselves
decomposed by NFKC into forms the map would no longer recognise — `U+00B4 ACUTE
ACCENT` becomes `SPACE` + `U+0301 COMBINING ACUTE ACCENT`, for instance — so a
fold applied only afterwards silently misses them. The map is idempotent on its
own output, so running it twice is safe.

### Step 2 — Unicode NFKC

Standard `NFKC` normalization. Folds fullwidth forms (`ＦＥＶＥＲ` → `FEVER`),
compatibility ligatures, and most exotic spaces.

### Step 3 — Case folding

`str.casefold()` (Python) / `toLowerCase()` with full Unicode case folding.
Unicode-aware, not ASCII-only: `ß` → `ss`.

### Step 4 — Apostrophe deletion

ASCII `'` is **deleted with no replacement**, so `Ludwig's angina` and
`Ludwig’s angina` both give `ludwigs angina`.

### Step 5 — Punctuation pass

Character by character:

| Character | Rule |
|---|---|
| Letter or digit (any script) | kept |
| `.` **directly between two ASCII digits** | kept — decimal point, `38.5` |
| `/` **directly between two ASCII digits** | kept — ratio / blood pressure, `140/90` |
| `,` **directly between two ASCII digits** | **deleted** — thousands separator, `1,000` → `1000` |
| anything else | replaced by a **single space** |

Note `-` falls into the last row: hyphens become **spaces, not nothing**.
Deleting them would turn `chest-pain` into `chestpain`, which matches no token.

### Step 6 — Whitespace collapse

Runs of whitespace collapse to one ASCII space; leading and trailing whitespace
is stripped.

---

## 3. Token IDs

```
normalize_token_id(token_id) = normalize(token_id.replace("_", " "))
```

The underscore is the word separator in `lowercase_snake_case`, so it becomes a
space before the standard pipeline runs. `chest_pain` → `chest pain`.

This is the value stored in `tokens[].search.normalized_form`, and the validator
regenerates and compares it, so it can never drift.

---

## 4. What normalization deliberately does NOT do

Every item here is a safety property, not an omission.

| Not done | Why |
|---|---|
| **Stemming / lemmatization** | `fevers` must not silently become `fever`. Plural handling is authored data, not an algorithm. |
| **Plural folding** | Same. Where a plural is clinically safe, it is added as an explicit reviewed alias. |
| **Spelling correction** | `fver` must not become `fever`. A typo resolving to a clinical token is a mis-triage waiting to happen. |
| **Edit-distance / fuzzy matching** | Anywhere in the pipeline or the resolver. Ambiguity is reported, never guessed. |
| **Substring or prefix matching** | `feve` must not match `fever`; `i have a fever today` must not match `fever`. Matching is whole-string equality only. |
| **Stopword removal** | Removing `no`, `not`, `without` would erase negation. |
| **Synonym expansion** | Synonyms are authored aliases with provenance and review, never inferred. |
| **Diacritic stripping** | See below. |

### Negation, laterality, severity, duration, age, pregnancy

These all survive normalization verbatim, because they are ordinary words the
pipeline never removes:

```
"no fever"      -> "no fever"        (never resolves to `fever`)
"without pain"  -> "without pain"
"left arm"      -> "left arm"
"severe pain"   -> "severe pain"
"3 days"        -> "3 days"
"2 years old"   -> "2 years old"
"pregnant"      -> "pregnant"
```

Combined with whole-string matching, `no fever` cannot resolve to `fever`:
the normalized query is `no fever`, which is not a key in the index. It returns
`no_match`.

### Deferred: diacritic folding

Diacritics are **preserved**. `naïve` normalizes to `naïve`, not `naive`.

Folding them would improve recall for Nigerian-language input, and the validator
would catch any alias collision it caused rather than letting it pass silently.
It is deferred anyway because it is a locale-gated, clinically reviewed decision
about which scripts to fold and where, and W2 Step 1 is the schema foundation,
not a retrieval-tuning exercise. Enabling it later requires a
`normalization_version` bump, a regenerated `search_index`, and a new artifact
version — it is not a silent change.

---

## 5. Versioning

`search_index.normalization_version` records the version that generated the
index; the validator asserts it matches the tooling. Any behaviour change to
`normalize()` requires:

1. a `normalization_version` bump;
2. a regenerated `search_index`;
3. a new artifact version;
4. a re-run of the search fixtures, with every changed expectation reviewed.

A normalization change is classified `search_only_metadata` — unless it changes
which token a previously unambiguous query resolves to, which makes it
`clinical_token_identity` and blocks publication. See
`docs/VOCABULARY_CHANGE_CLASSIFICATION.md`.

---

## 6. Conformance

An implementation conforms if it reproduces every expectation in
`testing/vocabulary/fixtures/search/search_cases_v1.json`. Each case records the
query, the expected normalized form, and what it is testing.

```bash
python3 testing/vocabulary/test_vocabulary_v2.py
```
