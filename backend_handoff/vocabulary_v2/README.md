# Backend Handoff — Symptom Vocabulary 2.0 (candidate)

**From:** Knowledge Base / Data Engineering
**Phase:** I2 / W2 Step 1
**Action required from Backend right now:** **none.** Read and acknowledge.

---

## 1. Bottom line

A candidate `token_dictionary` v2.0 exists in the knowledge-base repository. It
is **not uploaded to R2**, **not approved**, and **must not be wired into
`/config`**. The live manifest is unchanged and must stay that way.

This package exists so that when approval does come, nothing has to be guessed.

---

## 2. Candidate artifact

| Field | Value |
|---|---|
| Artifact ID | `token_dictionary` (**unchanged** — do not rename) |
| Version | `2.0` |
| Schema version | `2.0` |
| Filename | `token_dictionary.ng.v2.0.json` |
| Repository path | `candidate/token_dictionary.ng.v2.0.json` |
| SHA256 | `07f935967acb1d5515cb53ffd1c8e39b59b8daf85c67cf36fa3e25094e34cd2d` |
| Bytes | `339948` |
| Content type | `application/json`, charset UTF-8 |
| Compression | none at rest; SHA256 is always of the uncompressed bytes |
| Release status | `candidate_unapproved` |
| Release date | `null` |
| Uploaded to R2 | **no** |
| Rollback target | `token_dictionary.ng.v1.1.json`, sha256 `0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019` |

The hash is reproducible. `python3 tools/build_vocabulary_v2.py --check`
regenerates the artifact and fails if the committed bytes differ — so the value
above is not a transcription you have to trust.

---

## 3. Live manifest status

**Unchanged.** `GET /config` still serves:

```ts
token_dictionary: {
  version: '1.1',
  url: `${config.artifactBaseUrl}/token_dictionary.ng.v1.1.json`,
  hash: 'sha256:0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019',
  release_date: '2026-04-05',
  country: 'ng',
},
```

W2 Step 1 changed nothing in `wellapath-backend`. No file in that repository was
touched.

---

## 4. Manifest format

Unchanged by schema 2.0. Same entry shape as the four existing artifacts:
`{ version, url, hash, release_date, country }`, with `hash` as
`sha256:<64 lowercase hex>` of the uncompressed bytes.

The proposed future block is recorded in `candidate/manifest.candidate.json`
under `proposed_config_block`. That file is explicitly marked
`IS_LIVE_MANIFEST: false`. **Do not apply it.**

---

## 5. Version negotiation

There is no client-side negotiation, and schema 2.0 does not introduce any.
Mobile fetches whatever URL `/config` names. Consequences:

- Uploading v2.0 to R2 changes nothing on its own; clients keep getting 1.1
  until `/config` changes.
- Rollback is a one-block `/config` edit, not an app release.
- The shipped Mobile build can load v2.0 with **no code change** — it reads only
  `symptom_tokens` and `red_flag_tokens`, both byte identical to 1.1.

Full detail: `docs/VOCABULARY_VERSION_NEGOTIATION.md`.

---

## 6. Validation command

```bash
cd wellapath-knowledge-base
python3 tools/run_w2_checks.py
```

Runs 11 checks: report freshness, artifact reproducibility, schema conformance,
45 content validators, 26 compatibility checks, and 91 unit tests. Standard
library only — no `pip install`, no network.

To validate the artifact alone:

```bash
python3 tools/validate_vocabulary.py candidate/token_dictionary.ng.v2.0.json --json
```

If you prefer your own tooling, `schema/token_dictionary.v2.schema.json` is
standard JSON Schema draft 2020-12 and validates under Ajv.

---

## 7. Publication eligibility

**Not eligible.** Gate status:

| Gate | State |
|---|---|
| Change classification contains no blocking class | ✅ passed (`search_only_metadata` only) |
| Clinical review of schema 2.0 recorded | ❌ not performed |
| Engineering-lead approval recorded | ❌ not recorded |
| 239-case Top-50 regression re-run against kb 2.4 | ❌ not re-run |
| Uploaded to R2 | ❌ no |
| **May wire into `/config`** | ❌ **no** |

`reports/baseline_diff_v1.json` carries this as a machine-readable
`publication_decision` block with `may_publish: false`.

---

## 8. What Backend does when approval arrives

Unchanged from `docs/ARTIFACT_RELEASE_PROCESS.md` in the backend repository. In
particular, these steps are **not** waived:

1. Fetch the file from R2, confirm HTTP 200.
2. **Recompute the SHA256 yourself.** Never copy the hash above into
   `config.ts` without independently reproducing it.
3. Confirm `token_dictionary.ng.v1.1.json` still returns 200 with its original
   hash — proves no overwrite.
4. Diff v2.0 against v1.1 and confirm the change matches what was described:
   the six token arrays are byte identical; only the new keys `tokens`,
   `body_areas`, `complaint_groups`, `search_index` are added.
5. Validate referential integrity — every kb 2.4 and rules 2.2 token must
   resolve. `python3 tools/check_compatibility.py` already asserts this; re-run
   it or reproduce it independently.
6. Update only the `token_dictionary` block. Leave the other three alone.

---

## 9. What Backend must NOT do

- Do not add server-side symptom processing, symptom search, or normalization.
  Resolution runs on-device. The backend distributes artifacts; it does not
  execute clinical logic.
- Do not store symptom-level data. Nothing in schema 2.0 changes the no-PHI
  posture, and the vocabulary contains only token identifiers already published
  in v1.1.
- Do not expose a "vocabulary search" endpoint. That would move clinical
  inference server-side, which the locked architecture forbids.
- Do not wire the candidate into `/config`.

---

## 10. Questions this package should already answer

| Question | Answer |
|---|---|
| Does the artifact ID change? | No. Still `token_dictionary`. |
| Does the manifest shape change? | No. |
| Does content type or compression change? | No. |
| Will old clients break? | No. Proven — they read two keys, both unchanged. |
| Do I need to deploy anything? | No. |
| What is the rollback target? | `token_dictionary.ng.v1.1.json`, hash above. `docs/VOCABULARY_ROLLBACK.md`. |
| When do I act? | When the engineering lead confirms approval, per §8. |
