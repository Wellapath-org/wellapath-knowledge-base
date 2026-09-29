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
3. **Verify content at the URL** — 5,344 records, 0 populated phones, 924
   `emergency_capable: true`, `_metadata.version == "1.2"`.
4. **Repoint `/config`** to the v1.2 url, version `1.2`, hash
   `sha256:94f162e4…b7788`. Change nothing else in `/config`.
5. **Confirm from a client.** Launch a build on a clean install, confirm it
   downloads v1.2, the hash verifies, the locator lists facilities, and the
   Call button is absent on a Lagos facility that previously had one.
6. **Leave v1.1 on the host.** It is the rollback target.
7. **Later, separately:** forward-remove `facilities.ng.v1.1.json` from the
   public repository, once v1.2 has been stable in production and no
   rollback is expected. Keep `docs/FACILITIES_V1_2_ROLLBACK.md` as the
   record. No history rewrite.

## Rollback

| If | Then |
|---|---|
| The staged hash does not match | **Stop.** Do not repoint. Re-upload; a mismatch means a truncated or altered upload |
| A client fails to parse v1.2 | Repoint `/config` back to v1.1. It is unchanged on the host throughout |
| The locator misbehaves after repointing | Repoint to v1.1. Clients re-download on next launch; the cache is keyed by version |
| Rollback is needed for more than a few hours | Record it. Serving v1.1 re-exposes the 45 unlicensed values, which is the condition this artifact exists to end |

Rollback is a single `/config` edit. No build, no store submission, no data
migration — the two artifacts differ only in 45 null-versus-populated fields
and their metadata.

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
