# E9 Symptom Picker Expansion — Data Engineer Handoff (Issue #25)

Deliverable for the mobile engineer's `symptom_display_map.dart` expansion work.

## Files

- `symptom_display_body_area_map.csv` / `.json` — full mapping for all 164 symptom tokens in `token_dictionary.ng.v1.1.json`: `token | display_name | body_area | ambiguous | note`.
- `condition_top5_symptom_tokens.json` — for all 50 conditions in `kb.ng.v2.3.json`: `condition_id`, `condition_name`, and top 5 symptom tokens by weight. Use this to prioritise which tokens unlock the 19 unreachable conditions first.

## Scope note

`symptom_display_map.dart` lives in the mobile app repo, not here, so this mapping was **not diffed against the existing file** — it covers all 164 tokens rather than only the gap. Diff against the current `.dart` file to see what's actually new.

## Findings to flag during implementation

- **Zero tokens map to "Arms."** Nothing in the 164-token vocabulary is arm-specific; the closest candidate (`limb_weakness`) doesn't specify a limb and was mapped to `General`. The Arms zone in the body diagram currently has no tokens to route to it.
- **61 of 164 tokens (37%) flagged `ambiguous: true`**, for one of three reasons (see each row's `note`):
  1. No body location in the token itself (`pain`, `swelling`, `bleeding`).
  2. Near-duplicate tokens meaning almost the same thing (`head_pain`/`headache`, `eye_redness`/`red_eyes`, `breathlessness`/`shortness_of_breath`/`difficulty_breathing`).
  3. Clinical terms unlikely to be recognised by a lay user without extra description (`koplik_spots`, `ptosis`, `throat_membrane`, `stridor`, `chest_indrawing`, `petechial_rash`).
- Body area for a few tokens (e.g. `lower_abdominal_pain`) is a judgment call between two plausible zones (`Abdomen` vs `Pelvis`) — flagged in the notes column.
