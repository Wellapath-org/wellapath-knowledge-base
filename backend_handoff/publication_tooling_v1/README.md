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

**Re-pinned to contract 1.1.0 in I3 Step 2C.**

| | |
|---|---|
| Merge commit | `bbaeadd6075eb37fd51acbe04101f939e52c7d48` |
| Contract version | **`1.1.0`** |
| Schema | `docs/contracts/manifest.v1.schema.json` |
| Schema SHA256 | `948299bc1ca87592e372d4ce889bdd2424a6cfc3d34c7660453dfe7d60d5038a` (7,806 bytes) |
| Handoff SHA256 | `45fe9d886fb6d13ec3087cd11610eb38074a3b38edf20b1bd180bc024681887c` |
| Vendored at | `contracts/backend/manifest.v1.schema.json` (byte-for-byte) |
| Pin record | `contracts/backend/PIN.json` (pin version 2.0.0) |
| Superseded | `1.0.0` at `fc40ac3e…`, retained as labelled legacy test material |

All hashes were recomputed from the Backend bytes before any edit and are re-verified on every
run by `tools/verify_contract_pin.py`. Any drift fails closed and the tooling refuses to
generate anything.

The KB port now implements the 1.1.0 approval-scope rules identically, and proves it by
executing **the Backend's own `tests/fixtures/manifest/negative-fixtures.json` at `bbaeadd6`**:
all 39 cases fail at their declared stage with their declared reason code, including every
`APPROVAL_SCOPE_*` case.

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

**(a) Artifact identity for Vocabulary 2.0 — CLOSED.** The Backend adopted `token_dictionary`
at `bbaeadd6` and recorded the reasoning in its own
`tests/fixtures/manifest/approval-scope-reconciliation.fixture.json`
(`artifact_identity_finding: same_artifact_family`). The original finding follows.

**(a, as reported)** The Backend fixture uses
`artifact_id: "vocabulary"` with `object_key: "vocabulary.ng.v2.0.json"`. In this repository the
artifact is `token_dictionary`: the candidate file is `candidate/token_dictionary.ng.v2.0.json`,
its generator is `tools/build_vocabulary_v2.py`, and the published lineage it succeeds is
`token_dictionary.ng.v1.1.json` — which is the key currently in `GET /config`. The KB uses
`token_dictionary`, because renaming an artifact line across a version boundary would break the
predecessor relationship and the `/config` continuity. **Recommendation: the Backend fixture
adopts `token_dictionary`.**

**(b) Product approval status for Question Flow 1.1 — a fixture defect, now CLOSED by the
Backend.** Reported under I3 Step 2A; fixed by the Backend in contract 1.1.0. The account below
is the original finding, retained because it is why the contract moved. Current status:
`publication/fixtures/compat/approval_scope_reconciliation_v2.json`.

> **Closed.** At `bbaeadd6` the Backend fixture sets `approvals.product.status: "pending"` with
> `decision_scope: null`, matching the KB byte for byte, and contract 1.1.0 adds `decision_scope`
> so the substitution is now **unrepresentable** rather than merely ineffective. Replaying the
> old encoding under 1.1.0 fails validation with `APPROVAL_SCOPE_MISSING`. No KB action
> outstanding.

The Backend fixture sets `approvals.product.status: "granted"` with `decision_ref: "IM-001 —
Product decisions complete; activation remains unauthorized"`. The KB emits `"pending"`.

*What the fixture appears to mean.* The `decision_ref` text describes **decision-set
completion** — the scoped IM-001 display decision. That reading is supported by the KB's
records: `IM001-ORD-GLOBAL-001` approves a deterministic option-ordering rule and its own
`approval_does_not_authorize` list includes "publication of any candidate" and "production or
beta activation"; `im_001_resolved: true` records that the Product *decision set* is complete,
with a machine-readable scope saying it means only that.

*Why the encoding is nevertheless a defect.* `approvals.product` is not a scoped field. Contract
1.0.0 defines it as artifact-level Product approval, and `evaluateDescriptor` reads it — and
only it, for the product role — to compute `approved`. A scoped display decision placed there
is a category error, not a narrower claim.

*The proof, run against the Backend's own eligibility semantics.* As shipped, both encodings are
ineligible. But that is not the same as being correct:

| Encoding | as shipped | with clinical granted, blockers resolved, published, activated |
|---|---|---|
| KB (`product: pending` + resolved gate) | `approved: false`, `eligible: false` | **`approved: false`, `eligible: false`** |
| Backend fixture (`product: granted`) | `approved: false`, `eligible: false` | **`approved: true`, `eligible: true`** |

The Backend fixture's descriptor is protected today only by clinical approval being pending and
two blockers being open — conditions unrelated to the product field. Lift them and a
display-wording decision carries the artifact all the way to eligible. A field that is safe only
while something else happens to be in the way is a latent defect.

*What the KB did instead — and it needs no Backend support.* The contract **can** express the
distinction, so nothing was weakened to match the fixture:

- `approvals.product.status: "pending"` — artifact-publication Product approval, ungranted.
- `approvals.clinical.status: "pending"` — clinical approval, ungranted.
- a `blocker_record` `IM001-PRODUCT-DISPLAY-DECISIONS` with `status: "resolved"` — the completed
  display decision, scope stated in its `reference`.

A resolved blocker is the right home because it is *structurally* inert: `evaluateDescriptor`
computes `approved` exclusively from `approvals` and reads `blockers` in a loop that can only
deny. No evaluator following contract 1.0.0 can turn it into an approval. The safety is in the
shape of the contract rather than in a convention anyone has to remember.

**Backend follow-up — DONE by the Backend, not by this repository.** `approvals.product.status`
is now `"pending"` in `tests/fixtures/manifest/blocked-candidates.manifest.json`, and the
contract gained `decision_scope`, which is a stronger fix than the one suggested: it makes the
substitution unrepresentable rather than merely ineffective.

**Representation divergence — closed in I3 Step 2C, in the Backend's favour.** The KB had
carried the IM-001 completion as a resolved `blocker_record`. The Backend objected that the
blocker list is the safety channel, and a completed decision sitting in it inverts its meaning
for a person scanning for what is unresolved. That is right, and 1.1.0 removes the reason the
workaround existed, so the KB now carries the completion in the descriptor's `references` and in
`governance.product_approval_scope`. Both repositories emit the same product approval slot, byte
for byte. Neither side weakened.

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
- **Every decision this repository holds is scoped `product_display`.** None carries
  `artifact_publication`. That is the accurate record of what was decided, and under 1.1.0 it is
  what makes an artifact-publication approval built from these decisions unrepresentable.

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
- **The contract-1.0.0 schema is retained as labelled legacy test material** at
  `contracts/backend/legacy/`, used only to prove backward compatibility. It is never validated
  against as a real contract, and the pin refuses to let it masquerade as the active one.
- **Cross-schema rollback has no policy.** Both candidates' proposed rollbacks cross a content
  schema boundary (`token_dictionary` 2.0→1.1 crosses schema 2.0→1.0; `question_flow` 1.1→1.0
  crosses 1.1→1.0), so both plans carry `rollback_target: null` with the refusal recorded.
  Contract 1.0.0 defines no policy for this and the KB invents none.

---

## Backend deployment observation (read-only, I3 Step 2C)

Recorded because the re-pin consumed a Backend merge, and it is worth knowing whether that
merge reached a running environment. **Nothing was restarted, triggered or modified.**

**Finding: no deployment event observed from available evidence.**

That is a statement about the evidence, not a claim that no deployment happened. What was
checked, all read-only through the GitHub API at `bbaeadd6`:

| Source | Result |
|---|---|
| Repository deployments API | no records returned |
| Deployments filtered to `bbaeadd6` | none |
| Commit statuses on `bbaeadd6` | none (`total_count: 0`) |
| Repository environments | none (`total_count: 0`) |
| In-repo deploy configuration | none — no `render.yaml`; the only workflows are `ci.yml` and `docker.yml`, neither mentioning deploy or Render |
| GitHub check runs on `bbaeadd6` | `Docker Build: success`, `Lint & Build Check: success` |

A Render auto-deploy hook is configured in Render's own dashboard rather than in the
repository, and depending on its settings it may deploy without writing a GitHub Deployment
object or a commit status. Render's dashboard and API were not accessible here, so the absence
of a GitHub record is not evidence that no deploy occurred. It is only the absence of a record.

**What is verifiable either way:** the contract remains runtime-inactive at `bbaeadd6`. No file
under `src/routes/`, nor `src/app.ts` or `src/server.ts`, contains a single reference to
`manifest`. So whether or not a deployment ran, no route serves or consumes the manifest
contract, and `GET /config` is unchanged.

## Trigger to go further

An explicit engineering-lead and founder authorization naming publication of a specific artifact
version, plus an assigned Clinical reviewer and a recorded Clinical approval, plus adjudication
of both open blockers. Until all of those exist, this tooling's correct output is the one it
currently produces: a plan that says no, and says why.
