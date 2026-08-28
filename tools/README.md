# Vocabulary tooling (I2 / W2)

Standard-library Python 3.9+ only. No `pip install`, no network, no config.
That matches every other generator in this repository
(`testing/build_case_bank.py`, `facilities/source/build_e5.py`) and keeps the
artifacts reproducible on any machine.

## The one command

```bash
python3 tools/run_w2_checks.py
```

Runs everything below and exits non-zero on any failure. This is what CI runs.

## Generators

Each writes a committed file and each takes `--check`, which regenerates in
memory and fails if the committed copy differs. That is what makes hand-editing
a CI failure rather than a silent divergence.

| Command | Writes |
|---|---|
| `python3 tools/report_baseline.py` | `reports/baseline_freeze_v1.json` |
| `python3 tools/report_token_references.py` | `reports/token_reference_graph_v1.json` |
| `python3 tools/report_case_bank_status.py` | `reports/case_bank_status_v1.json` |
| `python3 tools/build_vocabulary_v2.py` | `candidate/token_dictionary.ng.v2.0.json` |
| `python3 tools/build_candidate_manifest.py` | `candidate/manifest.candidate.json` |
| `python3 tools/build_search_fixtures.py` | `testing/vocabulary/fixtures/search/*.json` |
| `python3 tools/build_invalid_fixtures.py` | `testing/vocabulary/fixtures/invalid/*.json` |
| `python3 tools/classify_vocabulary_diff.py --write` | `reports/baseline_diff_v1.json`, `reports/migration_report_v1.json` |

## Checkers

| Command | What it proves |
|---|---|
| `python3 tools/validate_vocabulary.py [path]` | 45 checks: schema conformance, identity, display/search metadata, references and deprecation, generation determinism, baseline preservation, provenance honesty. `--json` for machine output, `--no-baseline` for synthetic fixtures. |
| `python3 tools/check_compatibility.py` | 26 checks: frozen artifacts byte identical, every kb 2.4 / rules 2.2 / question-flow reference resolves, old-consumer surface unchanged, candidate unpublished. `--write` also emits `reports/compatibility_v1.json`. |
| `python3 tools/classify_vocabulary_diff.py` | Assigns every difference a clinical-safety class and decides whether clinical review is required. |
| `python3 testing/vocabulary/test_vocabulary_v2.py` | 91 unit tests. `-v` for verbose. |

## Library

`tools/vocab/`

| Module | Role |
|---|---|
| `normalize.py` | Reference normalization. Contract: `docs/VOCABULARY_NORMALIZATION_SPEC.md`. |
| `resolve.py` | Reference resolver and the five-state match model. Contract: `docs/VOCABULARY_AMBIGUITY_SPEC.md`. |
| `artifact_io.py` | Canonical serialization (`indent=2`, `ensure_ascii`, no trailing newline) and hashing. |
| `schema_check.py` | Dependency-free JSON Schema draft 2020-12 subset validator. Raises on any keyword it does not implement rather than skipping it — a validator that silently ignores a constraint is worse than none. |

---

# Publication tooling (I3 / Step 2)

Same conventions: standard-library Python 3 only, no `pip install`, no network, no config.
Full documentation: `docs/PUBLICATION_LIFECYCLE.md`.

> This tooling **prepares**. It performs no upload, publication, activation or deployment, and
> there is no code path in `tools/pubkit/` that could — no upload command, no cloud SDK, no
> HTTP client, no credential handling. Vocabulary 2.0 and Question Flow 1.1 remain unpublished,
> inactive and unauthorized.

## The one command

```bash
python3 tools/run_publication_checks.py
```

Runs everything below and exits non-zero on any failure. This is what CI runs.

## Generators

Each writes a committed file and each takes `--check`.

| Command | Writes |
|---|---|
| `python3 tools/build_governance_register.py` | `publication/governance/decision_register_v1.json` |
| `python3 tools/build_publication_plans.py` | `publication/plans/*.dryrun.json` |
| `python3 tools/build_publication_fixtures.py` | `publication/fixtures/compat/*.json`, `publication/fixtures/negative/*.json` |
| `python3 tools/build_receipt_examples.py` | `publication/receipts/*.example.json` |
| `python3 tools/report_publication_freeze.py` | `reports/publication_freeze_v1.json` |

`build_publication_plans.py` also takes `--artifact X --version Y` to plan any governed
artifact on demand, and `--stdout` to print instead of writing. There is no "plan everything"
mode: a plan targets one named version.

## Checkers

| Command | What it proves |
|---|---|
| `python3 tools/verify_contract_pin.py` | The pinned Backend contract 1.0.0 is byte identical, the Python mirror still agrees with the vendored schema (keys, enums, patterns), and the fixtures validate identically under both the ported validator and the schema. Fails closed on any drift. |
| `python3 tools/validate_publication_plan.py` | Every plan satisfies its schema, validates under both contract routes, carries digests recomputed from real bytes, refuses every governance claim, is ineligible in all three environments, and leaks no credential. Also PHI-scans `publication/` and `contracts/`. |
| `python3 tools/validate_publication_fixtures.py` | All 101 negative fixtures fail **at their declared stage with their declared reason code**. `--mutations` additionally breaks 7 safety-critical guards and requires the fixtures depending on them to stop passing. |
| `python3 testing/publication/test_publication.py` | 89 unit tests, including plan generation executed inside a guard that fails if a socket, a subprocess or a write outside the staging directory is attempted. |

## Library

`tools/pubkit/`

| Module | Role |
|---|---|
| `pin.py` | Loads and drift-checks the pinned contract. The only supported way to read it. |
| `contract.py` | Mirror of the Backend's `contract.ts` constants at the pinned commit. |
| `manifest.py` | Port of `validate.ts`. Also runs the vendored schema, and fails if the two disagree. |
| `eligibility.py` | Port of `eligibility.ts`. Refuses to read a wall clock. |
| `integrity.py` | sha256 and byte count from exact bytes, always read in binary. |
| `origin.py` | Port of `origin.ts`, plus the KB's named key rejections. |
| `keys.py` | The immutable key proposal and the identity/digest register. |
| `governance.py` | Decision-record validation and claim resolution. Fail-closed. |
| `lifecycle.py` | The nine states and the implications that do not hold. |
| `inventory.py` | Discovers governed artifacts from the filesystem. |
| `rollback.py` | Version-and-hash-bound rollback target checking. |
| `plan.py` | Dry-run plan assembly. |
| `staging.py` | The disposable staging area; the only write path. |
| `safety.py` | Instrumented refusal of network, subprocess and stray writes. |
| `reasons.py` | Two disjoint reason-code namespaces: the Backend's, and the KB's. |

## Rules

- **Never hand-edit a generated file.** Change the generator and rebuild.
- **Never edit a frozen artifact.** `token_dictionary.ng.v1.1.json`,
  `kb.ng.v2.4.json`, `rules.ng.v2.2.json`, `facilities.ng.v1.1.json` and
  `testing/case_bank_v1.json` are byte-checked in CI.
- **Never set a review or approval field by tooling.** Only a human approval
  record may populate a reviewer name, review date or evidence link.
- Run `tools/classify_vocabulary_diff.py` before opening any vocabulary PR and
  paste the output into the description.
- **Never set an approval, authorization or activation field by tooling.** The publication
  governance register is *derived* from decision records that already exist in this repository
  and is hash-bound to them; a generator that reads existing records cannot invent an approval
  nobody gave. Adding a decision is a governance act, not a code change.
- **Never move a candidate to the repository root.** The root is the directory published
  artifacts are uploaded from.
