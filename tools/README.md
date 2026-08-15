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

## Rules

- **Never hand-edit a generated file.** Change the generator and rebuild.
- **Never edit a frozen artifact.** `token_dictionary.ng.v1.1.json`,
  `kb.ng.v2.4.json`, `rules.ng.v2.2.json`, `facilities.ng.v1.1.json` and
  `testing/case_bank_v1.json` are byte-checked in CI.
- **Never set a review or approval field by tooling.** Only a human approval
  record may populate a reviewer name, review date or evidence link.
- Run `tools/classify_vocabulary_diff.py` before opening any vocabulary PR and
  paste the output into the description.
