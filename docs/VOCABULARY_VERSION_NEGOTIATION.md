# Vocabulary Version Negotiation

**Status:** contract for `token_dictionary` schema 2.0
**Applies to:** Backend (`GET /config`), Mobile (artifact loading)

---

## 1. How negotiation actually works today

There is no client-side version negotiation, and schema 2.0 does not add any.
The mechanism, as built:

1. Mobile calls `GET /config` and caches the response
   (`ConfigService.fetchConfig`, `StorageService.getLastKnownConfig`).
2. The response contains an `artifacts` map. Each entry carries `version`,
   `url`, `hash`, `release_date`, `country`.
3. Mobile reads `config['artifacts']['token_dictionary']['url']` and downloads
   that file (`lib/features/assessment/loading_screen.dart`).
4. Mobile never parses or compares a version string to decide what to accept.

**The manifest decides which version every client gets.** A client cannot
request a different one, and a new artifact reaches nobody until the backend
wires it into `/config`.

Two consequences that matter here:

- Publishing `token_dictionary.ng.v2.0.json` to R2 changes nothing on its own.
  Clients keep receiving 1.1 until `/config` changes.
- Rollback is a `/config` edit, not a client release. See
  `docs/VOCABULARY_ROLLBACK.md`.

---

## 2. Can the shipped Mobile build load a schema 2.0 artifact?

**Yes, with no code change.** This is measured, not assumed.

`lib/core/engine/red_flag_evaluator.dart` reads exactly two keys of the token
dictionary and nothing else:

```dart
final symptomTokensList = tokenDictionary['symptom_tokens'];
if (symptomTokensList is List) {
  validTokens.addAll(symptomTokensList.whereType<String>());
}
final redFlagTokensList = tokenDictionary['red_flag_tokens'];
if (redFlagTokensList is List) {
  validTokens.addAll(redFlagTokensList.whereType<String>());
}
```

A repository-wide search finds no other read of the artifact. So the compatibility
requirement reduces to: *keep `symptom_tokens` and `red_flag_tokens` unchanged.*

The candidate does. Both arrays are byte identical to 1.1, along with the other
four legacy arrays. Everything schema 2.0 adds sits under new top-level keys
(`tokens`, `body_areas`, `complaint_groups`, `search_index`) that the shipped
build simply never reads.

Verified by:

| Check | Where |
|---|---|
| `legacy_arrays_identical` | `tools/check_compatibility.py` |
| `mobile_surface_identical` | `tools/check_compatibility.py` |
| `mobile_valid_input_token_set_unchanged` | `tools/check_compatibility.py` |
| `test_simulated_old_consumer_reads_the_candidate` | reproduces the Dart logic in Python |

**No Mobile code update is required to load the candidate.** A Mobile update is
required only to *use* the new metadata.

---

## 3. Version semantics

| Field | Value | Meaning |
|---|---|---|
| `_metadata.artifact_id` | `token_dictionary` | Unchanged. Backend keys `/config` on it; Mobile reads `artifacts['token_dictionary']`; `tests/regression/existing-endpoints.test.ts` asserts it. |
| `_metadata.version` | `2.0` | Artifact version. Appears in the filename. |
| `_metadata.schema_version` | `2.0` | Structural contract version. |
| Filename | `token_dictionary.ng.v2.0.json` | `<artifact_id>.<country>.v<version>.json`, per repository convention. |

### Why 2.0 and not 1.2

Repository policy, from `schema/kb_schema_v1.0.json`:

> "Major bump for schema changes, minor for content changes"

and from `token_dictionary.ng.v1.1.json` `_metadata.rules`:

> "Once locked, tokens cannot be renamed without a schema version bump"

This release changes the schema (adds fields and top-level keys), so
`schema_version` goes 1.0 → 2.0, which forces the artifact major: 1.1 → **2.0**.

`artifact_id` deliberately does **not** change to something like `vocabulary`.
Renaming it would break two consumers and a regression test for a cosmetic gain.

---

## 4. Compatibility matrix

| Consumer reads | 1.1 | 2.0 candidate | Notes |
|---|---|---|---|
| `symptom_tokens` | ✅ | ✅ | byte identical |
| `red_flag_tokens` | ✅ | ✅ | byte identical |
| `duration_tokens`, `body_area_tokens`, `demographic_tokens`, `severity_tokens` | ✅ | ✅ | byte identical |
| `tokens` | — | ✅ | new; absent in 1.1 |
| `body_areas`, `complaint_groups`, `search_index` | — | ✅ | new; absent in 1.1 |

| Scenario | Outcome |
|---|---|
| Shipped Mobile (schema 1.0 reader) + 1.1 artifact | works — current production |
| Shipped Mobile (schema 1.0 reader) + 2.0 artifact | **works, unchanged behaviour** |
| Updated Mobile (schema 2.0 reader) + 2.0 artifact | works, gains search metadata |
| Updated Mobile (schema 2.0 reader) + 1.1 artifact | **must degrade gracefully — see below** |

### The one case needing new Mobile code

A schema 2.0-aware Mobile build may receive a **1.1** artifact — during a
rollback, or from a stale cached `/config`. It must handle that:

```dart
final tokens = artifact['tokens'];
if (tokens is! List) {
  // schema 1.0 artifact: fall back to the legacy arrays and the existing
  // display map. No vocabulary search, no aliases. Do NOT throw, do NOT
  // block the assessment — offline triage must still work.
}
```

Branch on **the presence of the `tokens` key**, not on a parsed version string.
Structural detection cannot be defeated by a version string that is missing,
malformed, or newer than the client knows about.

### Forward compatibility

A consumer must **ignore unknown top-level keys and unknown object properties**
rather than rejecting the artifact. The JSON Schema sets
`additionalProperties: false` to validate artifacts *this repository generates*;
it does not license a consumer to reject an artifact carrying a field it has not
yet been taught.

---

## 5. Integrity

Unchanged by schema 2.0. Every manifest entry carries
`hash: "sha256:<64 hex>"` of the **uncompressed** artifact bytes. Content type is
`application/json`, charset UTF-8, stored uncompressed at rest; transport
compression is the CDN's business and never affects the hash.

Per `wellapath-backend/docs/ARTIFACT_RELEASE_PROCESS.md`, the backend engineer
independently recomputes the hash before wiring it. That step is not waived here.

---

## 6. Publication sequence

Not yet started. For reference, the order is:

1. Clinical review of schema 2.0 and the candidate → recorded in
   `_metadata.clinical_review` with reviewer, date and evidence.
2. Engineering-lead approval.
3. 239-case Top-50 regression re-run against kb 2.4 → see
   `reports/case_bank_status_v1.json`.
4. `release_status` → `approved_unpublished`, `release_date` set, artifact
   rebuilt, hash recomputed.
5. Upload to R2 as a **new** object. Never overwrite an existing version.
6. Confirm `token_dictionary.ng.v1.1.json` still returns HTTP 200 with its
   original hash.
7. Backend independently verifies the hash, then updates the
   `token_dictionary` block in `/config`.
8. Verify staging `/config`.

**Steps 1–8 have not been performed. The live manifest is unchanged.**
