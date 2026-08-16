# Vendored question-flow sources

These are **verbatim copies** of Dart source from `wellapath-mobile`, taken at
commit `a269168e2ed9b3b1c0453797dce5c9f303366854` (branch `develop`).

They are here because the current question flow has **no versioned artifact**.
Its authoritative definition is this source, so freezing a baseline means
hashing these bytes rather than hand-transcribing values into a report — and
hand-transcription is exactly how a baseline stops matching the thing it claims
to freeze.

`tools/qflow/dartparse.py` parses these copies. It recognises only the literal
forms these files actually use and **raises** on anything else, so a future edit
it cannot read fails loudly instead of silently shrinking the baseline.

## Rules

- **Do not edit these files.** They are copies, not sources. Editing one makes
  the baseline describe something that does not exist.
- **Do not import them into a build.** They are `.vendored.dart` and are not
  part of any Dart package here.
- To refresh: re-copy from the mobile commit you are pinning to, re-run
  `python3 tools/report_question_baseline.py` and
  `python3 tools/build_question_candidate.py`, and record the new commit in
  `tools/qflow/__init__.py`.

## Provenance

| Vendored file | Mobile path |
|---|---|
| `followup_question_map.vendored.dart` | `lib/core/constants/followup_question_map.dart` |
| `red_flag_clarifiers.vendored.dart` | `lib/core/constants/red_flag_clarifiers.dart` |
| `symptom_display_map.vendored.dart` | `lib/core/constants/symptom_display_map.dart` |
| `question_engine.vendored.dart` | `lib/features/assessment/question_engine.dart` |
| `assessment_controller.vendored.dart` | `lib/features/assessment/assessment_controller.dart` |
| `followup_screen.vendored.dart` | `lib/features/assessment/followup_screen.dart` |
| `followup_question.vendored.dart` | `lib/features/assessment/models/followup_question.dart` |

Hashes are recorded in `reports/question_baseline_freeze_v1.json` under
`sources.files` and in the candidate's `_metadata.source.vendored_files`.
