# Publication lifecycle and tooling — I3 Step 2

> **This document describes tooling that prepares. It authorizes nothing.**
> Vocabulary 2.0 and Question Flow 1.1 are unpublished, inactive and unauthorized for
> activation. Clinical approval is false. No Clinical reviewer is assigned.
> `IM001-CLIN-FLAG-001` and `IM003-SB-001` are open. IM-003 is disabled. Publication,
> activation and Mobile implementation authorization are all false. Mobile PR #76 remains
> unauthorized to merge. Nothing in this step changed any of that.

---

## 1. What the tooling does, and what it cannot do

It inventories governed artifacts, validates them, hashes them from exact bytes, packages them
into a disposable staging directory, assembles Backend-contract-compatible descriptors,
resolves governance evidence, and emits deterministic dry-run publication plans.

It does not upload, publish, activate, deploy, write to R2, or change an artifact byte — and
there is no code path in `tools/pubkit/` that could. There is no upload command, no cloud SDK,
no HTTP client and no credential handling anywhere in the package. That is not a policy layered
on top of a capability; the capability was never built.

`tools/pubkit/safety.py` makes the absence checkable rather than merely stated. It patches the
socket layer, the subprocess launcher and `open()` for the duration of a block and records any
attempt. `testing/publication/test_publication.py` runs real plan generation inside it and
fails if a socket, a subprocess or a write outside the staging directory is even attempted.

| Command | What it does |
|---|---|
| `python3 tools/run_publication_checks.py` | Runs everything below. This is what CI runs. |
| `python3 tools/verify_contract_pin.py` | Proves the pinned Backend contract is unchanged, the mirror still agrees with it, and the fixtures validate identically under both routes. |
| `python3 tools/build_governance_register.py [--check]` | Transcribes this repository's decision records into a machine-readable register, hash-bound to each source. |
| `python3 tools/build_publication_plans.py [--check]` | Writes the committed dry-run plans. `--artifact X --version Y` plans any governed artifact on demand; `--stdout` prints instead of writing. |
| `python3 tools/build_publication_fixtures.py [--check]` | Writes the compatibility and negative fixture sets. |
| `python3 tools/build_receipt_examples.py [--check]` | Writes the non-operative receipt examples. |
| `python3 tools/validate_publication_plan.py` | Validates every committed plan, recomputes its digests from real bytes, and PHI/secret-scans `publication/` and `contracts/`. |
| `python3 tools/validate_publication_fixtures.py [--mutations]` | Runs all 110 negative fixtures and the 11 mutation proofs. |
| `python3 tools/report_publication_freeze.py [--check]` | Records and re-verifies the 44 frozen artifacts. |
| `python3 testing/publication/test_publication.py` | 129 unit tests. |

---

## 2. The nine states, and why they never collapse

```
generated → validated → packaged → present → uploaded → published → approved → active → eligible_for_environment
```

The arrows are reading order. **They are not implication.** No state in this tooling is ever
derived from another.

| State | Means | Established by |
|---|---|---|
| `generated` | Bytes exist and a named generator reproduces them | This repository |
| `validated` | Those bytes satisfy the artifact's own schema and checks | This repository |
| `packaged` | A verified copy exists in the disposable staging area | This repository |
| `present` | A descriptor exists and is structurally sound | This repository |
| `uploaded` | The bytes exist at the immutable key on the approved origin | Infrastructure |
| `published` | Release status is `published`, with a publication date | Governance |
| `approved` | Every required approval is granted against a decision record | Governance |
| `active` | Activation is explicitly active AND explicitly authorized | Governance |
| `eligible_for_environment` | Everything the environment requires holds at once | Backend, per environment |

What does **not** follow:

- `generated` does not mean `validated` — unvalidated bytes are just bytes.
- `validated` does not mean `packaged`.
- `packaged` does not mean `uploaded` — packaging writes to a local disposable directory.
- storage presence does not mean `published` — bytes at a key are bytes at a key.
- `published` does not mean `approved` — publication is a release act, approval is a governance act.
- `approved` does not mean `active` — approval permits activation, it does not perform it.
- `active` does not mean `eligible` — activation is global, eligibility is per environment.
- candidate existence does not mean eligibility.
- **a git commit, a merged pull request, a green CI run, a passing test suite or a completed
  decision set grants none of them.**

The rule the code enforces is the strong one: **the five externally-established states can
never be asserted true by this tooling at all.** A repository cannot observe whether an object
is in a bucket or whether a person approved something. A plan claiming one is not reporting an
observation, it is inventing one. `schema/publication_plan.v1.schema.json` pins all five to
`const: false`, so such a plan fails its schema.

Absent, null, malformed, unknown or conflicting governance fails closed. An *unobserved* state
is not a false state — it is a state nobody checked, and `lifecycle.state_of` refuses it rather
than defaulting it in either direction.

---

## 3. Contract pinning and drift detection

The Backend repository is the sole authority for manifest contract 1.0.0. This repository
vendors it so it can validate offline, and never redesigns, extends or loosens it.

| | |
|---|---|
| Repository | `Wellapath-org/wellapath-backend` |
| Merge commit | `bbaeadd6075eb37fd51acbe04101f939e52c7d48` |
| Contract version | **`1.1.0`** (supported major: 1) |
| Source path | `docs/contracts/manifest.v1.schema.json` |
| Vendored at | `contracts/backend/manifest.v1.schema.json` |
| Schema SHA256 | `948299bc1ca87592e372d4ce889bdd2424a6cfc3d34c7660453dfe7d60d5038a` (7,806 bytes) |
| KB handoff SHA256 | `45fe9d886fb6d13ec3087cd11610eb38074a3b38edf20b1bd180bc024681887c` |
| Pin record | `contracts/backend/PIN.json` (pin version 2.0.0) |
| Superseded | contract `1.0.0` at `fc40ac3e7d59cfed8e2584b78136c9704f7ab8cd`, schema `66fa3a94…082ce9` (6,375 bytes) — retained as **labelled legacy test material** at `contracts/backend/legacy/manifest.v1.0.0.schema.json` |

### What 1.1.0 changed, and why it is a minor

1.1.0 adds the optional approval field `decision_scope` and tightens one previously unsafe
claim: **a `granted` approval that declares no `artifact_publication` scope no longer counts.**
Three reason codes are new: `APPROVAL_SCOPE_MISSING`, `APPROVAL_SCOPE_UNKNOWN`,
`APPROVAL_SCOPE_MISMATCH`.

It is a minor rather than a patch because it changes what the evaluator accepts, and a minor
rather than a major because the supported major is unchanged and descriptors making no
granted-approval claim stay valid. Note the asymmetry, which is the honest reason the version
moved: a 1.1.0 descriptor carrying `decision_scope` is **invalid** against 1.0.0, whose approval
record is `additionalProperties: false`. Additive forwards, breaking backwards.

The tightening exists because of this repository. In I3 Step 2A the KB reported that a decision
scoped to display wording and ordering could occupy an artifact-publication approval slot and,
once unrelated conditions lifted, carry an artifact to `approved`. The Backend fixed both the
fixture and the contract. Under 1.1.0 that substitution is not merely ineffective — it is
**unrepresentable**, rejected at validation as well as denied at eligibility.

The vendored file is a **byte-for-byte** copy. It is never reformatted or re-serialised.

`tools/verify_contract_pin.py` checks four things offline, and **fails closed on every one**:

1. the pin is present, well-formed, and declares `fail_closed` for every failure mode;
2. the vendored schema still hashes to the pinned digest and is the pinned size;
3. **the Python mirror in `tools/pubkit/contract.py` still agrees with the vendored schema** —
   the same required keys, optional keys, enums and regex patterns. This is the check that
   would otherwise rot silently: a hash proves the *file* is unchanged, and says nothing about
   whether the code reading it still means the same thing. A mirror that quietly gained a
   release status would keep the hash perfectly valid while accepting descriptors the Backend
   rejects;
4. the compatibility fixtures validate identically under both the ported validator and the
   vendored schema.

On any drift: **stop.** Do not regenerate plans. Re-read the Backend contract at its new
commit, confirm the ported semantics still hold, then update the pin and the vendored bytes in
one reviewed change. A new 1.x minor is additive by the Backend's own rule, and this repository
still refuses it until the pin is deliberately updated — silently accepting an unpinned
contract would defeat the pin.

### Why the contract is validated twice

Every descriptor is checked by **both** the port of the Backend's hand-written validator
(`tools/pubkit/manifest.py`) **and** the Backend's published schema. They are meant to agree.
A disagreement is a hard failure (`KB_CONTRACT_KB_PASSES_BACKEND_FAILS`), not a preference for
whichever passed — a descriptor only one of them accepts must never be handed over.

### Making a draft-07 schema executable, without weakening the validator

The vendored contract is draft-07 and keeps its subschemas under `definitions`, alongside a
custom `contract_version` annotation. `tools/vocab/schema_check.py` implements a draft-2020-12
subset and raises on any keyword it does not implement, so it needs to be told those two are
tolerable.

That is `validate(..., extra_keywords=...)`, and it is **closed, not open**: a caller may only
name keywords listed in `ANNOTATION_ONLY_KEYWORDS`, which contains exactly `definitions` and
`contract_version`, and asking to tolerate anything else raises. The restriction is the entire
safety property. An unrestricted version would let a caller name `multipleOf`, `contains` or
`dependentRequired` — real assertions this validator does not implement — and the constraint
they express would be silently dropped while validation reported success, which is worse than
not validating at all.

Two further properties make it safe rather than merely restricted:

- **It cannot switch off a supported constraint.** Every assertion in the module is driven by an
  explicit `if "<keyword>" in schema` test, never by the allowlist, so naming an
  already-supported keyword changes nothing — and is refused anyway, since the allowlist is
  asserted disjoint from the supported set at import.
- **`definitions` does not become a place constraints go to die.** `$ref` resolution walks the
  raw schema dict, so refs into `definitions` are still applied in full.

`SchemaValidatorHardeningTests` proves all of it, including that adversarial content placed
under either allowed keyword moves not a single validation error.

### Where the KB is deliberately stricter

Extra *rejections* are always contract-safe: they shrink what this repository is willing to
emit, never widen what the Backend will accept. The KB additionally refuses mutable-alias keys,
path traversal, absolute paths, unsafe characters, ambiguous normalisation, embedded secrets,
version/hash disagreement and identity collisions; and it refuses to evaluate eligibility
without an explicit evaluation instant, because a dry run that read a wall clock could not be
reproducible.

---

## 4. Deterministic packaging

Two runs over the same tree produce **byte-identical** plans. Nothing reads a clock, an
environment variable, a random value or a path outside the repository.

- The evaluation instant is the declared constant `2026-08-28T00:00:00Z`, recorded in every
  plan. Eligibility depends on time (expiry), so a plan generated from a clock would differ
  between runs and `--check` could not distinguish a real change from the passage of an
  afternoon.
- `created_at` comes from the artifact's own recorded `generated_at`.
- The staging directory's path never enters the output — it is temporary, machine-specific, and
  recording it would make the plan non-deterministic for no benefit. `staging_path_recorded` is
  `false` and a test asserts the path does not appear anywhere in the plan.
- The governance register's label is derived from its repository-relative path rather than
  passed in, because it appears inside reason paths that reach committed plans.

Packaging copies bytes into `.publication-staging/` — git-ignored, created on entry, removed on
exit including on failure. Every write goes through `StagingArea.write`, which refuses any path
that does not *resolve* inside it, symlinks and `..` included. The canonical source is re-hashed
after every packaging operation, so "we did not modify the artifact" is a measurement.

---

## 5. The immutable object key

Convention, unchanged from the Backend's: `<artifact>.<country>.v<version>.json`, flat at the
bucket root. `kb.ng.v2.4.json`, `question_flow.ng.v1.1.json`.

A key binds four things — artifact id, artifact version, content type (via the `.json` suffix),
and content identity. The first three are in the key string. **The hash is bound by
registration rather than by being embedded**, and that is a deliberate trade: a key carrying its
own digest would be self-verifying but would break the convention the Backend, Mobile and R2
already use. Registering the (key → identity → digest) triple makes the binding checkable
without changing the address, which is what "never reused for changed content" actually
requires.

Rejected, each with its own reason code:

| Rejected | Code |
|---|---|
| mutable aliases (`latest`, `current`, `stable`, `live`, `prod`, …, and `vlatest`) | `KB_KEY_MUTABLE_ALIAS` |
| path traversal or separators | `KB_KEY_PATH_TRAVERSAL` |
| absolute paths | `KB_KEY_ABSOLUTE_PATH` |
| non-NFC or non-ASCII spellings | `KB_KEY_AMBIGUOUS_NORMALIZATION` |
| characters outside `[a-z0-9._]` | `KB_KEY_UNSAFE_CHARACTER` |
| version/hash disagreement with the descriptor | `KB_KEY_VERSION_DISAGREEMENT` |
| one key claimed by two identities | `KB_KEY_IDENTITY_COLLISION` |
| one key rebound to different bytes | `KB_KEY_OVERWRITE_DIFFERENT_BYTES` |
| `?`, `&`, `#`, `=`, `%`, `x-amz-`, or a credential word as a segment | `KB_KEY_EMBEDS_SECRET` |
| arbitrary origins, plain HTTP, credentials or query strings in a URL | `ORIGIN_*` |

**"token" and "key" are deliberately absent from the credential word list.** In this domain a
token is a clinical symptom token and `token_dictionary.ng.v1.1.json` is a published artifact;
treating either word as credential-shaped would reject real keys. Query-string secrets — the
case that actually matters — are caught structurally instead: an immutable key contains no `?`,
`&`, `#`, `=` or `%` at all. Credential words are matched as whole segments, never as
substrings, because this repository's vocabulary contains words like "secretion".

Nothing here creates, alters or contacts a bucket. `IdentityRegister` is an in-memory record of
one tooling run; it knows nothing about what exists in storage and never claims to.

---

## 6. Governance evidence resolution

Every approval or authorization claim must resolve to an **authoritative decision record**
binding: a stable decision ID, an authority type, a reviewer *identity and title*, a decision
date, an explicit status, artifact identity and version, artifact hash where applicable, a
rationale, a hash-bound decision reference, an explicit scope, and supersession/revocation
status.

Refused, each with its own reason code:

| Refused | Code |
|---|---|
| prose-only approval (no hash-bound record) | `KB_DECISION_PROSE_ONLY` |
| missing reviewer identity or title | `KB_DECISION_REVIEWER_MISSING` |
| missing or unknown authority | `KB_DECISION_AUTHORITY_MISSING` |
| unknown decision status | `KB_DECISION_STATUS_UNKNOWN` |
| a real decision whose status is not `approved` | `KB_DECISION_NOT_APPROVED` |
| approval for another artifact | `KB_DECISION_ARTIFACT_MISMATCH` |
| approval for another version | `KB_DECISION_VERSION_MISMATCH` |
| approval for other bytes | `KB_DECISION_HASH_MISMATCH` |
| expired / revoked / superseded | `KB_DECISION_EXPIRED` / `_REVOKED` / `_SUPERSEDED` |
| **Product approval substituted for Clinical** | `KB_DECISION_AUTHORITY_WRONG` |
| **decision-set completion substituted for authorization** | `KB_DECISION_SET_IS_NOT_AUTHORIZATION` |
| claim outside the record's stated scope | `KB_DECISION_SCOPE_MISSING` / `_EXCEEDED` |
| open safety blocker | `KB_SAFETY_BLOCKER_OPEN` |
| no record at all | `KB_DECISION_RECORD_MISSING` |

`publication/governance/decision_register_v1.json` is **derived, never authored**. Every record
it holds is transcribed from a decision file that already exists in this repository and is bound
to it by path and sha256. A generator that reads existing records can restate them and fail when
they change; it has no way to invent an approval nobody gave.

Two absences are recorded as absences rather than filled in:

- **No Clinical decision record exists**, because no Clinical reviewer is assigned. Not a
  pending one, not a placeholder — none. Every clinical claim resolves to
  `KB_DECISION_RECORD_MISSING`, which is the truthful answer. This tooling does not assign a
  reviewer and does not infer clinical approval from any Product decision.
- **No publication or activation authorization record exists** for any artifact.

### The approval-scope ruling (I3 Step 2A)

Four distinct facts, carried in four different contract fields. Conflating any two is the
specific failure this section exists to prevent.

| Concept | Status | Contract field that carries it |
|---|---|---|
| `product_display_decision` (scope: display wording and ordering only) | **complete** | descriptor `references[]` + `governance.product_approval_scope`; the decision is scoped `product_display` in the register |
| `artifact_publication_product_approval` | **pending** | `approvals.product.status` + `approvals.product.decision_scope` |
| `clinical_approval` | **pending** | `approvals.clinical.status` + `approvals.clinical.decision_scope` |
| `publication_authorization` | **false** | `publication_decision_ref` |
| `activation_authorization` | **false** | `activation_authorized` + `activation_decision_ref` |

Every plan carries this as `governance.product_approval_scope`, and
`schema/publication_plan.v1.schema.json` pins each `grants_*` field and each status, so a plan
that claimed the display decision granted approval would fail its schema rather than merely
contradict its own prose.

**Where the completion is recorded, and why it moved.** Under contract 1.0.0 the KB carried it
as a `blocker_record` with `status: "resolved"` — chosen because `evaluateDescriptor` computes
`approved` exclusively from `approvals` and reads `blockers` in a loop that can only deny, so a
resolved blocker was *structurally* incapable of being read as approval.

Contract 1.1.0 removed the need for that workaround, and the Backend objected to it on a
ground worth taking: the blocker list is the safety channel, and a completed decision sitting in
it inverts its meaning for a person scanning for what is unresolved, even while the evaluator
correctly ignores it. Both points are right. The completion is now carried in the descriptor's
`references` and in `governance.product_approval_scope`, and the safety comes from
`decision_scope` instead — which is stronger, because it makes the substitution unrepresentable
rather than merely ineffective. Both repositories now emit the same product approval slot, byte
for byte.

**How a substitution fails now.** Placing the IM-001 decision in `approvals.product` requires
declaring its scope. Declaring the true scope (`product_display`) fails validation with
`APPROVAL_SCOPE_MISMATCH`; declaring none fails with `APPROVAL_SCOPE_MISSING`; declaring
something invented fails with `APPROVAL_SCOPE_UNKNOWN`. There is no spelling that works.

`publication/fixtures/compat/approval_scope_reconciliation_v2.json` proves this by computation
rather than assertion — including replaying the historical defective encoding under 1.1.0 and
showing it now fails validation outright. `tools/validate_publication_plan.py` re-derives the
central claim at check time.

**Reconciliation history is preserved, not rewritten.**
`approval_scope_reconciliation_v1.json` remains exactly as committed
(`36efa4e9…e194ee`, 8,578 bytes), bound to Backend `fc40ac3e`, where the defect genuinely
existed. The Backend cites that record by hash. Rewriting it to read as though the Backend was
always correct would erase the evidence that the correction was needed, and with it the reason
the contract moved to 1.1.0.

### `im_001_resolved` is not an authorization

`im_001_resolved: true` means every Product display decision in the IM-001 set has been
recorded. It is a statement about a backlog reaching zero, not a permission. Its own record
carries a machine-readable `im_001_resolved_scope` whose `does_not_mean` list names six
exclusions, and this tooling binds and validates that scope: any claim resolved against the
decision-set record is refused with `KB_DECISION_SET_IS_NOT_AUTHORIZATION`, whichever way the
scope is written, so the reported reason names the specific confusion rather than a generic
scope failure.

---

## 7. The dry-run plan format

`schema/publication_plan.v1.schema.json`. Every committed plan validates against it.

A plan answers one question about one named artifact version: *if publication were authorized,
what exactly would be published, and what is currently stopping it?* It is a report. There is no
"publish everything" mode and no default target.

Its safety-critical fields are pinned by `const`, not merely typed as boolean — so the guarantee
belongs to the contract of the file and not only to the code that writes it:

```
_metadata.is_operative              const false
operations_performed.*              const false  (upload, publication, activation, deployment,
                                                  storage write, network access, canonical mutation)
eligible_for_environment            const false
eligible_in_any_environment         const false
lifecycle.states.uploaded           const false
lifecycle.states.published          const false
lifecycle.states.approved           const false
lifecycle.states.active             const false
lifecycle.states.eligible_for_...   const false
descriptor.activation_authorized    const false
descriptor.activation_status        const "inactive"
descriptor.published_at             null
governance.claims[].granted         const false
governance.clinical_reviewer_assigned  const false
object_key.url                      null
conclusion.publishable              const false
conclusion.activatable              const false
blocking_reasons                    minItems 1
```

`url` is `null` deliberately. An artifact that has never been uploaded has no URL, and recording
the address it *would* have is how a proposal becomes mistaken for a fact.

Every environment is evaluated, not only the one the descriptor targets, so a plan cannot be
read as ineligible merely because of an environment mismatch.

### The `target_environments` placeholder

Contract 1.0.0 requires `target_environments` to be a non-empty array; there is no way to say
"none". The declared `["staging"]` is therefore **structural**, records no deployment decision,
and the plan says so in its `references`. The descriptor is ineligible in staging exactly as it
is everywhere else, on governance grounds.

---

## 8. Receipts and audit

`schema/publication_receipt.v1.schema.json` defines four receipts for future, separately
authorized operations: **upload**, **publication decision**, **activation** and **rollback**.

Each binds the same spine: actor (identity, title, role, authority), timestamp, environment,
artifact version, hash, byte count, immutable key, and decision references. Rollback
additionally binds both ends by version *and* hash; activation binds what it deactivated,
because a receipt naming only the arrival cannot be audited backwards.

Only dry-run examples exist, in `publication/receipts/`. Every one declares `operative: false`
and a `non_operative_declaration`, both pinned by `const` — **a forged successful receipt is a
schema failure, not merely a policy violation.** Every `*_performed` flag is false, every
`occurred_at` is null, and every recorded decision is `refused`. There is no example of a
successful upload, publication or activation: forging one would put a file that looks exactly
like a real operator's output into the directory a real operator tool will write to.

### The signing gap

**These receipts are unsigned, and the manifest contract has no signing.** This repository holds
no signing key, no key custody procedure and no verification path, and invents none. An unsigned
receipt is a statement by whoever wrote the file. A home-made signature would look like
assurance without being any. Establishing a trust mechanism is new infrastructure and needs its
own decision. The gap is recorded in every receipt's `signing.gap`, in the pin's
`representability.gaps`, and here.

---

## 9. Rollback preparation

A rollback target is an *operational pointer*: when it is used, something will serve the bytes
it names. So it must name an exact version **and** the exact sha256 of that version's bytes, and
must resolve in the governed inventory.

Refused: unbound version-only targets (`KB_ROLLBACK_UNBOUND_VERSION_ONLY`), targets absent from
the inventory (`_TARGET_NOT_IN_INVENTORY`), hash mismatches (`_HASH_MISMATCH`), cycles and
self-references (`_CYCLE`), cross-artifact targets (`_CROSS_ARTIFACT`), content-schema
incompatibility (`_SCHEMA_INCOMPATIBLE`), and targets whose approval has lapsed
(`_TARGET_UNAUTHORIZED`).

Rolling back to content whose approval has lapsed is not automatically wrong — returning to
something superseded is often the whole point — but it is not automatically right either, and
contract 1.0.0 defines no policy for it. Until one exists the answer is refusal with a named
reason rather than a guess in either direction.

**Both candidates' proposed rollbacks are currently refused, and for a real reason.**
`token_dictionary` 2.0 declares content schema 2.0 while 1.1 declares 1.0; `question_flow` 1.1
declares 1.1 while 1.0 declares 1.0. Each return crosses a content-schema boundary a consumer
that upgraded its parser could not read. Both plans therefore carry `rollback_target: null`
rather than an unusable pointer, with the refusal recorded. This is a finding for whoever
eventually authorizes publication, not a defect in the tooling.

Nothing here changes an active version or a clinical artifact byte.

---

## 10. Secret handling

- No credential, token, presigned URL, signed query parameter or bucket secret appears anywhere
  in this step's output. `tools/validate_publication_plan.py` scans every plan for
  AWS-style key ids, `x-amz-*` parameters, secret key names, bearer tokens, GitHub tokens, URLs
  with query strings and URLs with embedded credentials.
- The approved origin (`pub-8bc2...r2.dev`) is already public in the Backend repository's tests,
  docs and `.env.example`. Naming it exposes nothing new and it is not a credential.
- Environment variables are referred to by name only, never by value. This step introduces none.
- `publication/` and `contracts/` are PHI-scanned with the same pattern list
  `tools/verify_no_clinical_change.py` uses, imported rather than copied so the two definitions
  cannot drift. One reviewed exception is recorded by exact string: the
  `ORIGIN_HAS_CREDENTIALS` negative fixture contains `user:pass@…`, because no URL can
  demonstrate that rejection without containing an `@`.

---

## 11. Negative fixtures and mutation proofs

**110 negative fixtures**, each declaring the stage it must fail at and the exact reason code it
must fail for. A case does not pass by failing; it passes only by failing *where and how it says
it will*. A guard that starts refusing the right thing for the wrong reason is a behaviour
change, and the runner makes that visible.

| Suite | Stage | Cases |
|---|---|---|
| compat | validation | 30 |
| compat | eligibility | 15 |
| compat | selection | 3 |
| compat | integrity | 2 |
| kb | contract_pin | 7 |
| kb | generation | 1 |
| kb | artifact_schema | 1 |
| kb | integrity | 3 |
| kb | object_key | 10 |
| kb | governance | 19 |
| kb | lifecycle | 7 |
| kb | rollback | 7 |
| kb | write_safety | 5 |

**11 mutation proofs.** Each deliberately breaks one safety-critical guard and requires the
fixture depending on it to *stop passing*. A guard nobody can break was never guarding anything,
and a fixture that still passes with its guard removed is testing the absence of a bug rather
than the presence of a check. The proofs cover the mutable-alias rule, the request-marker rule,
the credential-word rule, the lifecycle externally-established-state refusal, the governance
authority mapping, the closed status set, the pin's fail-closed policy check, and the four
contract-1.1.0 approval-scope guards (the required-slot clause, the closed scope vocabulary, the
missing-scope rule at validation, and scope evaluation at eligibility).

---

## 12. Cross-repository compatibility

`publication/fixtures/compat/negative_fixtures.compat.json` is written in the **Backend's own
fixture format** — the same `base` / `target` / `context` / `cases` shape, the same override
keys, the same `stage` and `expected_code` vocabulary as
`wellapath-backend/tests/fixtures/manifest/negative-fixtures.json`. It is data, not Python, so
the Backend's existing runner can execute it unchanged. A fixture set only proves two
implementations agree if both can actually run it.

`publication/fixtures/compat/kb_blocked_candidates.manifest.json` is the Knowledge Base
counterpart to the Backend's `blocked-candidates.manifest.json`, which had to use placeholder
digests because the Backend cannot see these bytes. The KB version carries the real identities,
the real sha256 digests over the real candidate bytes, and the true governance state. Its
descriptors are extracted verbatim from the committed plans, so the fixture and the plans cannot
disagree.

`kb_baseline.manifest.json` is synthetic and obviously so: `artifact_id` is `fixture_artifact`,
which is not and never will be a real artifact, while its hashes are the real digests of real
repository files so integrity cases run against bytes that exist. A baseline built on a real
identity with approvals granted would be a file that reads like an approval record, and this
repository has enough of those to not want a convincing fake among them.

---

## 13. Backend integration responsibilities

The Backend, not the Knowledge Base:

- owns the manifest contract and is its sole authority;
- independently re-derives `sha256` and `byte_count` from the bytes it fetches, and rejects
  mismatches regardless of what any descriptor, ETag or `Content-Length` claims;
- computes eligibility per environment and refuses to serve anything not simultaneously
  published, approved, unblocked, activation-authorized, environment-targeted, unexpired,
  undeprecated and build-compatible;
- refuses a downgrade with no version-and-hash-bound `rollback_target`;
- decides whether and when to consume any manifest at all. Contract 1.0.0 is inactive: no route
  serves or consumes it.

Nothing in this step asks the Backend to do anything, changes anything in the Backend
repository, or wires anything into `GET /config`. The Backend-side handoff note is
`backend_handoff/publication_tooling_v1/README.md`, written on the KB side.

---

## 14. Future operator responsibilities

When publication is eventually authorized, the operator — **not this tooling** — must:

1. hold an explicit publication authorization bound to the exact artifact, version and hash;
2. hold an explicit activation authorization, separately, for activation;
3. confirm Clinical approval from an assigned Clinical reviewer, recorded as a decision record
   with reviewer identity, title, date, status and scope;
4. confirm every safety blocker is resolved, with an adjudication record;
5. upload through a separate, explicitly authorized command that does not exist yet — and which,
   per this design, must be isolated from the dry-run tooling, require explicit environment and
   authorization inputs, refuse without a publication authorization, and have no usable
   credentials in tests;
6. verify after upload by re-reading the stored object and re-deriving its digest and byte count
   from the bytes actually returned;
7. record an upload receipt, a publication decision receipt and (separately) an activation
   receipt;
8. never reuse an object key for changed content. Corrections are new versions.

---

## 15. Unresolved decisions and gaps

| Gap | Status |
|---|---|
| **No Clinical reviewer is assigned** | Open. Until one is, no clinical approval can exist for any artifact, and this tooling assigns nobody. |
| `IM001-CLIN-FLAG-001` | Open. Requires Clinical review before any activation decision involving `fast_breathing_child.severity`. |
| `IM003-SB-001` | Open. Awaiting clinical and product adjudication. IM-003 itself remains disabled. |
| Publication authorization | Does not exist for any artifact. |
| Activation authorization | Does not exist for any artifact. |
| Mobile implementation authorization | False. Mobile PR #76 remains unauthorized to merge. This tooling instructs Mobile to implement nothing. |
| **Manifest and receipt signing** | Does not exist in contract 1.0.0. No key, no custody, no verification path. New infrastructure, needs its own decision. |
| Upload mechanism | Not built, deliberately. No command, no cloud SDK, no credential handling. |
| Storage observability | This repository cannot see R2. `uploaded` is therefore never observable here, and is recorded false with that reason rather than left unset. |
| Cross-schema rollback policy | Contract 1.0.0 defines none. Both candidates' proposed rollbacks cross a content-schema boundary and are refused pending an explicit decision. |
| Artifact identity for Vocabulary 2.0 | The Backend's fixture calls it `vocabulary`; this repository's artifact is `token_dictionary` (the published lineage is `token_dictionary.ng.v1.1.json`). The KB uses its own true identity. Worth reconciling before either side builds on the other's fixture. |
| Product approval status for Question Flow 1.1 | **Resolved as a Backend fixture defect (I3 Step 2A).** The Backend fixture sets `approvals.product: granted` with a `decision_ref` whose text describes decision-set completion — but that field is artifact-level Product approval and feeds `approved`. As shipped it is ineligible only because clinical is pending and two blockers are open; lift those unrelated conditions and it becomes `approved: true` and `eligible: true` on the strength of a display-wording decision. The KB keeps `approvals.product` pending and carries the completed display decision as a resolved gate. **Backend follow-up required; not done here.** |
| Cross-schema rollback policy — restated | Confirmed correct fail-closed behaviour. Both plans carry `rollback_target: null`; the proposal that was refused is itself hash-bound, so there is no version-only or inferred form anywhere; the refusal names `KB_ROLLBACK_SCHEMA_INCOMPATIBLE`; and neither candidate can publish or activate without either a separately approved rollback policy or a schema-compatible exact target. No policy is invented here. |
