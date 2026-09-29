# Vocabulary Rollback & Last-Known-Good

**Status:** contract for `token_dictionary` schema 2.0
**Rollback target:** `token_dictionary.ng.v1.1.json`
**Target SHA256:** `0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019`

---

## 1. Nothing needs rolling back right now

The candidate is not published. `/config` still serves `token_dictionary` 1.1.
This document is the procedure to have in place **before** anything ships, not a
response to an incident.

---

## 2. Why rollback is cheap here

Two properties, both structural:

1. **Versioned immutable artifacts.** `token_dictionary.ng.v1.1.json` is never
   overwritten. It stays at its URL with its original hash forever, so rolling
   back means pointing at a file that is already there and already correct.
2. **The manifest chooses the version.** Clients do not negotiate; they fetch
   whatever URL `/config` gives them. Reverting one block in `config.ts` reverts
   every client on its next config fetch. No app release, no store review.

The candidate records its own rollback target in `_metadata.rollback_target`,
and `tools/validate_vocabulary.py` asserts that the recorded hash matches the
baseline file on disk — so the pointer cannot silently rot.

---

## 3. Rollback procedure

**Owner:** backend engineer, on the engineering lead's instruction.

1. **Revert the `/config` block.** In `wellapath-backend/src/routes/config.ts`,
   restore the `token_dictionary` entry to:

   ```ts
   token_dictionary: {
     version: '1.1',
     url: `${config.artifactBaseUrl}/token_dictionary.ng.v1.1.json`,
     hash: 'sha256:0cc47ad9537c0bd4c6ef3aec8f1931eb9b4c62103a8809d16544f94a90b5c019',
     release_date: '2026-04-05',
     country: 'ng',
   },
   ```

2. **Do not delete the 2.0 object from R2.** Deleting it breaks integrity checks
   for any client still holding a cached `/config` pointing at it, and destroys
   the evidence needed to diagnose the failure. Artifacts are immutable in both
   directions.

3. **Verify.** Confirm `token_dictionary.ng.v1.1.json` returns HTTP 200 and its
   original hash, then confirm staging `/config` reports version `1.1`.

4. **Record.** Note the rollback and its cause in the backend `PROGRESS.md` and
   in this repository's `progress.md`.

---

## 4. Client behaviour during rollback

| Client state | Behaviour |
|---|---|
| Schema 1.0 reader (shipped build) | Unaffected. It reads `symptom_tokens` and `red_flag_tokens`, identical in both versions. |
| Schema 2.0 reader, fresh config | Receives 1.1, finds no `tokens` key, falls back to the legacy arrays and its own display map. Search metadata unavailable; triage unaffected. |
| Schema 2.0 reader, stale cached config | Keeps using cached 2.0 until its next successful config fetch. Safe: 2.0 and 1.1 carry the same token set and the same clinical meaning. |
| Offline | Keeps using its last-known-good cached artifact. Assessment continues to work — that is the point of offline-first. |

A schema 2.0-aware Mobile build **must** branch on the presence of the `tokens`
key rather than on a version string, and must never throw or block an assessment
when it is absent. See `docs/VOCABULARY_VERSION_NEGOTIATION.md` §4.

---

## 5. Last-known-good

Unchanged by schema 2.0:

- Mobile caches the `/config` response (`StorageService.getLastKnownConfig`) and
  boots from it when the network is unavailable
  (`BootStatus.offline` in `lib/features/boot/boot_controller.dart`).
- Downloaded artifacts remain on-device for offline assessment.
- Because both versions carry an identical token set, a device holding 2.0 while
  the server has rolled back to 1.1 has **no clinical divergence** — the accepted
  input tokens, the scored tokens and the red-flag tokens are the same set.

---

## 6. Rolling back the repository itself

The candidate is generated, not hand-written, so reverting it is a `git revert`
of the PR. Nothing else has to be undone:

- No frozen artifact was modified — asserted byte-for-byte by
  `tools/check_compatibility.py` and by the test suite.
- No live manifest was touched.
- Every file added by W2 Step 1 is a report, a fixture, a tool, a document, or
  the unpublished candidate.

Verify after any revert:

```bash
python3 tools/run_w2_checks.py
```
