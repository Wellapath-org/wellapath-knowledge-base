
## red_flag_display_map.json (E9 beta blocker)

Display + picker-routing mapping for the **12 global red-flag tokens** that are currently unreachable through the symptom picker (only `seizures` was added). Without this, a caregiver cannot report these danger signs and the red flag never fires — an under-triage hole.

Per entry: `token`, `display_name` (caregiver-facing plain English), `body_area` (E9 picker vocabulary), `near_miss_tokens` (existing picker tokens a caregiver might select instead), and `note`.

**Read the `note` field before wiring these up.** Each note says whether a near-miss is **escalate-safe** (e.g. `confusion` → `altered_consciousness`) or **needs a clarifying question** (e.g. `difficulty_breathing` → `breathlessness_at_rest`, `dehydration` → `severe_dehydration`). Auto-firing emergency on every near-miss would convert an under-triage gap into an over-triage one — the notes mark exactly where that risk is.

**Flagged gap:** `blue_lips_face` (cyanosis) has **no accurate near-miss** in the current picker. Recommend adding an explicit "Blue lips or face" picker option — otherwise this danger sign stays effectively unreportable even after this mapping.
