# facilities.ng.v1.2 — activation plan

**Not executed.** This is the plan; nothing in it has been performed. The
live pointer still serves v1.1.

## Verified current state, 2026-09-29

| | |
|---|---|
| `/config` facilities version | **1.1** |
| `/config` facilities url | `…r2.dev/facilities.ng.v1.1.json` |
| `/config` facilities hash | `sha256:25684c71…2398` |
| Served bytes vs repo `facilities.ng.v1.1.json` | **identical** |
| Phones populated in the live artifact | **45** |
| Declared sources in the live artifact | 3, **one with `license: null`** |
| `facilities.ng.v1.2.json` on the artifact host | **HTTP 404 — not published** |

So the 45 unlicensed telephone numbers **are still being served in
production** and will remain so until this plan runs. That is the exposure
activation closes.

## Would changing the live pointer alter builds 211 and 215?

**Yes.** This is the single most important fact here.

`StagedArtifactLoader` takes the url, version and hash **entirely from
`/config`**. No build pins a facilities version; the only version literals in
`lib/` are a doc comment and the token-dictionary pin. So on their next
launch, builds 211 and 215 would fetch v1.2, verify its hash and cache it —
without a new build and without a store submission.

That cuts both ways:

* **In favour.** Repointing removes the unlicensed values from existing
  internal testers' devices. It is the only way to do that without shipping a
  new build.
* **Against.** It changes data under builds that were tested against v1.1,
  and neither 211 nor 215 carries the attribution footer (merged after them).
  They would render ODbL data with no in-app attribution — no worse than
  today, since they already render v1.1 that way, but not yet compliant.

**Recommendation: repoint anyway.** Removing unlicensed contact data from
live clients is the more urgent of the two, and the attribution gap is
unchanged rather than worsened. Build 216 closes it.

## Current-client compatibility

v1.2 is schema-identical to v1.1. Same ten record fields, same 5,344
records, same identifiers, coordinates, types and states, same 924
`emergency_capable` hospitals.

| Change | Client effect |
|---|---|
| `phone` null on 45 records | `facility_card.dart` renders the Call button under `if (phone != null)`, so the button simply does not appear. No crash, no empty control |
| Two new `_metadata` keys (`licence`, `supersession`) | Metadata is read by key; unknown keys are ignored |
| `sources` reduced from 3 to 2 | Not read by any client path |

The only user-visible change is that **45 Lagos facilities lose their Call
button.** That is the intended outcome, not a defect: those numbers had no
redistribution permission. Everything else — search, distance ranking,
red-flag hospital ordering, offline cache — behaves identically.

## Activation steps

Do not start until the artifact is independently approved.

1. **Stage.** Upload `facilities.ng.v1.2.json` to the artifact host beside
   v1.1. Do not touch `/config`.
2. **Verify the staged URL.**
   ```bash
   curl -s https://<host>/facilities.ng.v1.2.json | shasum -a 256
   # must equal 94f162e492fa91f7d9d3cf2ca33fcf0598a031a2510aa900aa717a581bdb7788
   ```
   Confirm the byte count is 1,698,125 and that the response is not a cached
   404 or an HTML error page.
3. **Verify content at the URL** — 5,344 records, **zero telephone values and
   zero email values** (both by populated-field count and by a regex sweep of
   the whole served body), zero `opening_hours` values, 924
   `emergency_capable: true`, `_metadata.version == "1.2"`, the `licence`
   block present, and the expected ten record fields. Also check the
   `Content-Type` and cache headers, and that TLS validates.
4. **Repoint `/config`** to the v1.2 url, version `1.2`, hash
   `sha256:94f162e4…b7788`. Change nothing else in `/config`.
5. **Confirm from a client.** Launch a build on a clean install, confirm it
   downloads v1.2, the hash verifies, the locator lists facilities, and the
   Call button is absent on a Lagos facility that previously had one.
6. **Confirm the contact-free rollback is staged** (see below). Do not rely
   on v1.1.
7. **Remove v1.1 from public serving** once v1.2 is verified on existing
   builds — see "Removing v1.1 from public serving" below.

## Rollback — v1.0, never v1.1

**v1.1 must not be the rollback target.** Rolling back to it would re-serve
the 45 unlicensed telephone numbers, which is the exact condition this
activation exists to end. A rollback must not undo the licensing fix.

The rollback artifact is **v1.0**, the verified lineage v1.2 was generated
from:

| | |
|---|---|
| File | `facilities.ng.v1.0.json` |
| sha256 | `1c7b939199ab4465156f4cb336910eea120fcaa70f8b1c0743fc9f7a7c03009e` |
| Bytes | 1,695,059 |
| Records | 5,344 |
| Telephone values | **0** |
| Email values | **0** |
| `emergency_capable: true` | **924** |
| Record fields | **identical to v1.2** |
| Declared sources | 2, **both licensed**, none null |

It is schema-compatible with every existing build, contact-free, checksum
verified, and covered by the corrected attribution position in
`DATA_SOURCES.md` and the README. It lacks v1.2's `licence` metadata block,
which is why it is the fallback and not the primary.

**Stage v1.0 at a versioned URL before repointing to v1.2**, so the rollback
target exists at the moment it might be needed.

| If | Then |
|---|---|
| The staged v1.2 hash does not match | **Stop.** Do not repoint. Re-upload; a mismatch means a truncated or altered upload |
| A client fails to parse v1.2 | Repoint `/config` to **v1.0**, not v1.1 |
| The locator misbehaves after repointing | Repoint to **v1.0**. Clients re-download on next launch; the cache is keyed by version |
| Rollback is needed at all | Record it, and treat it as a blocker on the licensing work rather than a resting state |

Rollback is a single `/config` edit. No build, no store submission, no data
migration — v1.0 and v1.2 carry identical records, identifiers, coordinates
and hospital ordering.

## Removing v1.1 from public serving

Required, not optional: while v1.1 remains fetchable, the unlicensed values
remain publicly distributed regardless of what `/config` points at.

1. Confirm `/config` no longer references v1.1 in any field.
2. Confirm the v1.0 rollback artifact is staged and fetchable.
3. Confirm v1.2 has been verified on existing internal builds.
4. Delete `facilities.ng.v1.1.json` from the artifact host.
5. Verify its previous URL returns **404 or 410**, allowing for CDN cache
   expiry, and re-check after the cache window.
6. Retain exactly one checksum-verified private evidence copy, outside every
   Git working tree.
7. Separately, forward-remove `facilities.ng.v1.1.json` from the public
   repository. No history rewrite.

## Config refresh and cache behaviour — inspected, not assumed

Read from `boot_controller.dart` and `staged_artifact_loader.dart`.

| Question | Finding |
|---|---|
| When is `/config` refreshed? | **Every launch.** `BootController` calls `fetchConfig` first; the Hive copy is used **only** when that call fails |
| Configuration-cache TTL? | **None.** There is no staleness window — a cached config is an offline fallback, not a cache |
| Does an online launch always check for a new version? | **Yes.** Activation therefore reaches a device on its next online launch |
| Is the artifact cache keyed by version or overwritten? | **Keyed by version** — `'${cacheKey}_v${version}'`, so v1.1 and v1.2 are separate entries |
| Are old artifact files deleted after successful activation? | **No.** The only `delete` removes *the same version's* entry when its hash fails. There is no sweep |
| Behaviour on checksum or download failure | **Fails closed.** A cached entry failing its hash is deleted and re-downloaded; downloaded bytes failing the hash are rejected, retried once, then raise. Unverified bytes are never used |
| Offline after one successful v1.2 load | Works. The versioned entry and the parsed facility list are both present, and the cached config names v1.2 |

### Limitation to record

**Activation does not remove v1.1 from tester devices.** Because the cache is
keyed by version and nothing sweeps old entries, the v1.1 raw JSON — including
the 45 telephone numbers — **remains in each device's Hive `artifact_cache`
box indefinitely**, until the app is uninstalled or its data cleared.

What activation does achieve: v1.1 stops being *used* (the parsed facility
list under `facilities_data` is overwritten on the next successful load), and
once removed from the host it stops being *served* to anyone new.

No cleanup code is being added during this activation. If the retained local
copies need clearing, that is a separate, reviewed change in a later build.

**Do not state that every device copy was removed.** It was not.

## Build 216

Not to be created yet. When it is, it should carry:

* the locator attribution footer (merged to mobile `develop`), which makes
  216 the first build that displays the ODbL and CC BY 4.0 attribution the
  licences require;
* whatever the clinical launch gate requires — that gate is still open and is
  independent of this work.

Sequencing note: activation (steps 1–6) needs no build and should not wait
for 216. Build 216 closes the attribution gap; activation closes the
unlicensed-data gap. Doing activation first is right, because live clients
stop receiving unlicensed contact data sooner.

**Builds 211 and 215 remain internal-testing only.** They are not promoted
externally, and they are not deleted. The earliest external candidate is 216
or higher, using this artifact and carrying the attribution.
