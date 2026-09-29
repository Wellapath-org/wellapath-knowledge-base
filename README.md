# WellaPath Knowledge Base

Versioned clinical JSON artifacts powering WellaPath — a clinical decision support system (CDSS) for frontline health workers in Nigeria.

WellaPath's mobile app runs its decision engine entirely on the device, consuming the artifacts in this repository: a knowledge base of weighted symptom profiles for 50 conditions, red-flag safety rules, a controlled symptom token vocabulary, and a health-facility directory. Artifacts are immutable once published — every change ships as a new versioned file — so the app can pin, cache, and roll back clinical content independently of app releases.

## What's inside

- **Knowledge base** (`kb.ng.v1.0` → `kb.ng.v2.3`) — the full Nigeria knowledge base covering 50 conditions, each with a condition ID, default urgency tier, base weight, weighted symptom tokens, and red flags. Individual condition files live in `conditions/` (one `*.ng.v2.0.json` per condition); the three-condition pilot set (malaria, acute diarrhoea, childhood pneumonia) is preserved in `pilot/`.
- **Red-flag rules** (`rules.ng.v1.0` → `rules.ng.v2.1`) — 76 rules total: 13 global danger-sign rules plus 63 condition-specific rules, all validated against the token dictionary. Red flags always override scoring in the engine.
- **Token dictionary** (`token_dictionary.ng.v1.0` / `v1.1`) — the controlled vocabulary of 295 symptom tokens for all 50 conditions. All tokens are `lowercase_snake_case`, with no duplicates across categories; every token referenced by the KB or rules must exist here.
- **Facilities directory** (`facilities.ng.v1.0` / `v1.1`) — 5,344 health facilities across Lagos, FCT, and Kano, built from GRID3 and HDX/OSM open datasets (CC BY 4.0). `facilities/` contains the build script (`source/build_e5.py`), source CSVs, the facility schema, and a cleaning log documenting how the data was normalized.
- **Locked schemas** (`schema/`) — JSON schema definitions for the knowledge base and rules artifacts, including locked principles: no PHI fields, no diagnostic language in explanation templates ("may be consistent with" phrasing), enum-locked urgency tiers, and artifact immutability after publish.
- **Case bank** (`testing/`) — a 234-case pre-beta validation set spanning all 50 conditions (4+ cases each, all 13 global red-flag rules, 150 safety-critical cases). Expected outcomes are derived from the spec — not copied from the engine — so runs can catch real engine bugs. `build_case_bank.py` regenerates the bank deterministically; see `testing/README.md` for the derivation rules and runner contract.
- **Source sheets** (`source/`) — the Excel workbooks and CSVs the artifacts were built from (schema lock, token dictionary, condition mapping, KB source, facility phone enrichment).

## Artifact conventions

- **Immutable versioning.** Published files are never overwritten; changes bump the version in the filename (`kb.ng.v2.2.json` → `kb.ng.v2.3.json`). Each artifact carries a `_metadata` block with its version, schema version, country code, and release date.
- **No PHI.** Artifacts contain clinical reference data only — no name, DOB, phone, email, or address fields. Combined with on-device scoring in the mobile app, patient data never needs to reach a server for an assessment.
- **Single vocabulary.** Every symptom token in the KB and rules resolves to the token dictionary, keeping the engine, the case bank, and the clinical content in lockstep.
- **Safety first.** Red-flag rules are evaluated before scoring and cannot be outvoted by symptom weights.

## Tech stack

- Plain, schema-validated JSON artifacts (no runtime dependencies for consumers)
- Python 3 tooling for deterministic builds (`testing/build_case_bank.py`, `facilities/source/build_e5.py`)
- Open data sources: GRID3 Nigeria Health Facilities v2.0, HDX/OSM Nigeria health facilities

## Getting started

The artifacts are consumed as static JSON — clone and read. To regenerate the derived artifacts:

```bash
git clone https://github.com/Wellapath-org/wellapath-knowledge-base.git
cd wellapath-knowledge-base

# Regenerate the validation case bank (byte-identical, deterministic)
cd testing && python3 build_case_bank.py

# Rebuild the facilities artifact from the source CSVs
cd ../facilities/source && python3 build_e5.py
```

## Project structure

```
kb.ng.v*.json                  # Knowledge base artifact (50 conditions)
rules.ng.v*.json               # Red-flag rules artifact (13 global + 63 condition-specific)
token_dictionary.ng.v*.json    # Symptom token vocabulary (295 tokens)
facilities.ng.v*.json          # Health facility directory (Lagos, FCT, Kano)
conditions/                    # Per-condition KB files (v2.0, one per condition)
pilot/                         # Original 3-condition pilot artifacts
schema/                        # Locked JSON schemas for KB and rules
testing/                       # 234-case validation bank + deterministic generator
facilities/                    # Facility build script, source CSVs, schema, cleaning log
source/                        # Excel/CSV source sheets behind the artifacts
```
