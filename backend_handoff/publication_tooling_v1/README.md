# KB implementation note — publication tooling against manifest contract 1.0.0

**Written on the Knowledge Base side. The `wellapath-backend` repository is unmodified by this
step, including its `docs/handoffs/KB_PUBLICATION_HANDOFF.md`.** This note is the KB's response
to that handoff; it is not an edit of it.

This note asks the Backend to do nothing and instructs Mobile to implement nothing.

---

## What was built

I3 Step 2 built deterministic, offline, fail-closed Knowledge Base tooling that *prepares*
governed artifacts and Backend-contract-compatible descriptors. It inventories, validates,
hashes, packages into a disposable staging directory and emits dry-run publication plans.

It performs no upload, publication, activation or deployment, and there is no code path that
could: `tools/pubkit/` contains no upload command, no cloud SDK, no HTTP client and no
credential handling. Full documentation: `docs/PUBLICATION_LIFECYCLE.md`.

Nothing was published, activated or made eligible. Vocabulary 2.0 and Question Flow 1.1 remain
unpublished, inactive and unauthorized.

---

## What was consumed from the Backend, and how it is pinned

| | |
|---|---|
| Merge commit | `fc40ac3e7d59cfed8e2584b78136c9704f7ab8cd` |
| Contract version | `1.0.0` |
| Schema | `docs/contracts/manifest.v1.schema.json` |
| Schema SHA256 | `66fa3a94f17c2765eb1eca29208d2494c4c1b7be57eae61856bdb34761082ce9` (6,375 bytes) |
| Handoff SHA256 | `90e28e165e512c3765abb40f91e617c14f9027d78d1435dcea5ad6406e7f4ed8` |
| Vendored at | `contracts/backend/manifest.v1.schema.json` (byte-for-byte) |
| Pin record | `contracts/backend/PIN.json` |

All four hashes were verified against the Backend's remote `develop` before any work began, and
are re-verified on every run by `tools/verify_contract_pin.py`. Any drift fails closed and the
tooling refuses to generate anything.

`tools/pubkit/contract.py`, `manifest.py`, `eligibility.py`, `integrity.py` and `origin.py` are
deliberate **ports** of `src/manifest/*.ts` at that commit, not independent designs. The pin
verifier cross-checks the Python mirror against the vendored schema — required keys, optional
keys, enums, regex patterns — so a mirror that quietly drifted would fail even though the schema
hash stayed valid.

Every descriptor is validated by **both** the port and the vendored schema, and a disagreement
is a hard failure rather than a preference for whichever passed.

---

## What the Backend may find useful

### 1. A blocked-candidates manifest with real hashes

`publication/fixtures/compat/kb_blocked_candidates.manifest.json`

The Backend's own `tests/fixtures/manifest/blocked-candidates.manifest.json` had to use
placeholder digests (`sha256` of a seed string, `byte_count` of that string's length) because
the Backend cannot see these bytes. The KB version carries the real ones:

| Artifact | Version | sha256 | byte_count | object_key |
|---|---|---|---|---|
| `token_dictionary` | 2.0 | `sha256:07f935967acb1d5515cb53ffd1c8e39b59b8daf85c67cf36fa3e25094e34cd2d` | 339,948 | `token_dictionary.ng.v2.0.json` |
| `question_flow` | 1.1 | `sha256:3ea534b0797f382ec895e56accfd631d37fd61ae1bb2ecf173a666d5b888c02b` | 155,532 | `question_flow.ng.v1.1.json` |

Both are `release_status: candidate`, `activation_status: inactive`,
`activation_authorized: false`, `published_at: null`, `publication_decision_ref: null`, with
both approvals `pending`. `question_flow` carries `IM001-CLIN-FLAG-001` and `IM003-SB-001`, both
open. **These descriptors name no uploaded object and must never be added to any live manifest.**

### 2. Cross-repository negative fixtures in the Backend's own format

`publication/fixtures/compat/negative_fixtures.compat.json` — 41 cases in the same `base` /
`target` / `context` / `cases` shape as `tests/fixtures/manifest/negative-fixtures.json`, with
the same override keys and the same `stage` / `expected_code` vocabulary. It is data, not
Python, so `tests/unit/manifest-fixtures.test.ts` can execute it unchanged against the Backend's
own implementation.

If the Backend runs it and any case fails for a different reason than declared, the two
implementations have diverged — which is exactly what the shared format exists to surface. The
baseline it mutates is `kb_baseline.manifest.json`, whose `artifact_id` is `fixture_artifact`
(unmistakably synthetic) but whose hashes are real repository digests.

### 3. Two discrepancies worth reconciling

Neither changes any outcome — both candidates are ineligible under either reading — but the two
repositories' fixtures differ, deliberately, and the difference should be settled by a person
rather than by whichever file someone reads first.

**(a) Artifact identity for Vocabulary 2.0.** The Backend fixture uses
`artifact_id: "vocabulary"` with `object_key: "vocabulary.ng.v2.0.json"`. In this repository the
artifact is `token_dictionary`: the candidate file is `candidate/token_dictionary.ng.v2.0.json`,
its generator is `tools/build_vocabulary_v2.py`, and the published lineage it succeeds is
`token_dictionary.ng.v1.1.json` — which is the key currently in `GET /config`. The KB uses
`token_dictionary`, because renaming an artifact line across a version boundary would break the
predecessor relationship and the `/config` continuity. **Recommendation: the Backend fixture
adopts `token_dictionary`.**

**(b) Product approval status for Question Flow 1.1.** The Backend fixture sets
`approvals.product.status: "granted"` with `decision_ref: "IM-001 — Product decisions complete;
activation remains unauthorized"`. The KB emits `"pending"`.

The KB has the underlying records and they do not support a granted Product approval *of the
artifact*. `reports/im001_option_order_decision_v1.json` records `IM001-ORD-GLOBAL-001`, which
approves a deterministic option-ordering rule and whose own `approval_does_not_authorize` list
includes "publication of any candidate" and "production or beta activation". Separately,
`im_001_resolved: true` records that the Product *decision set* is complete, with a
machine-readable scope stating it means only that.

Treating either as Product approval of the artifact for publication is precisely the
decision-set-completion-substituted-for-authorization error the contract's fail-closed design
is meant to prevent, so the KB refuses it (`KB_DECISION_SET_IS_NOT_AUTHORIZATION`) and emits
`pending`. **Recommendation: the Backend fixture adopts `pending`, or a genuine Product
publication-approval record is created — but that is a governance act, not a fixture edit.**

---

## Where the Knowledge Base is deliberately stricter

Extra *rejections* are contract-safe: they shrink what the KB will emit, never widen what the
Backend will accept. None of these needs Backend support.

- **Object keys** additionally refused by name: mutable aliases (including `vlatest`), path
  traversal, absolute paths, non-NFC/non-ASCII spellings, characters outside `[a-z0-9._]`,
  key/identity version disagreement, one key claimed by two identities, one key rebound to
  different bytes, and `?`/`&`/`#`/`=`/`%`/`x-amz-` or a credential word as a segment.
  (`token` and `key` are **not** credential words here — `token_dictionary` is a real artifact.)
- **Eligibility refuses to read a wall clock.** The Backend's `evaluateDescriptor` defaults
  `now` to real time; the KB port raises without an explicit instant, because a dry run that
  depended on when it ran could not be reproducible.
- **Governance evidence** must bind to a hash-bound decision record. Prose is not evidence.
- **Reason-code namespaces are disjoint.** `KB_*` codes are Knowledge Base findings about
  *preparing* an artifact and are never written into a descriptor; a test asserts this.

---

## Gaps this note inherits and does not close

- **No Clinical reviewer is assigned.** Until one is, no clinical approval can exist for any
  artifact. The KB holds no clinical decision record at all — not a pending one, not a
  placeholder — and assigns nobody.
- **Publication and activation authorization do not exist** for any artifact.
- **`IM001-CLIN-FLAG-001` and `IM003-SB-001` are open.** IM-003 remains disabled.
- **Manifest and receipt signing do not exist.** Contract 1.0.0 has none, this repository holds
  no signing key, no key custody and no verification path, and invents no substitute. If signing
  is required it is new infrastructure and needs its own decision. Receipt schemas record the
  gap explicitly in every example's `signing.gap`.
- **No upload mechanism exists**, deliberately. If one is ever scaffolded it must be isolated
  from the dry-run tooling, require a separate explicit command, require explicit environment
  and authorization inputs, refuse without a publication authorization, and hold no usable
  credentials in tests.
- **Cross-schema rollback has no policy.** Both candidates' proposed rollbacks cross a content
  schema boundary (`token_dictionary` 2.0→1.1 crosses schema 2.0→1.0; `question_flow` 1.1→1.0
  crosses 1.1→1.0), so both plans carry `rollback_target: null` with the refusal recorded.
  Contract 1.0.0 defines no policy for this and the KB invents none.

---

## Trigger to go further

An explicit engineering-lead and founder authorization naming publication of a specific artifact
version, plus an assigned Clinical reviewer and a recorded Clinical approval, plus adjudication
of both open blockers. Until all of those exist, this tooling's correct output is the one it
currently produces: a plan that says no, and says why.
