// Expanded for E9 (issue #25 / #26): the picker previously exposed only 18
// unique tokens (~11% of the 164-token vocabulary), leaving 19 of the KB's
// 50 conditions completely unreachable and several more (cardio_symptoms,
// sari, hypertension, tuberculosis_suspected, diabetes) reachable only via
// weak, generic shared tokens rather than their real distinguishing
// symptoms. This map now covers every token needed to reach all 24 of
// those conditions, sourced from the data engineer's
// wellapath-knowledge-base mobile_handoff mapping (PR #9).
//
// Two display-name collisions from that mapping were resolved here since
// kSymptomDisplayMap keys must be unique: 'fast_breathing' (adult) vs the
// existing 'fast_breathing_child' both suggested "Fast breathing", and
// 'itchy_eyes' vs 'eye_itchiness' both suggested "Itchy eyes" — see the
// distinct labels below.
const Map<String, String> kSymptomDisplayMap = {
  'Headache': 'headache',
  'Fever': 'fever',
  'Chills': 'chills',
  'Body pain': 'body_pain',
  'Weakness': 'weakness',
  'Nausea': 'nausea',
  'Sweating': 'sweating',
  'Cough': 'cough',
  'Fast breathing': 'fast_breathing_child',
  'Watery stool': 'watery_stool',
  'Vomiting': 'vomiting',
  'Abdominal cramps': 'abdominal_cramps',
  'Dizziness': 'dizziness',
  'Fatigue': 'fatigue',
  'Wrist pain': 'pain',
  'Swollen hands': 'swelling',
  'Dark urine': 'dark_urine',
  'Feeling sick or queasy': 'nausea',
  'Muscle pain': 'body_pain',
  'Seizures': 'seizures',
  'Stomach pain': 'abdominal_pain',
  'Bitten by an animal': 'animal_bite',
  'Back pain': 'back_pain',
  'Bad breath': 'bad_breath',
  'Swelling in both feet/legs': 'bilateral_oedema',
  'Mark left by a bite': 'bite_mark',
  'Bleeding': 'bleeding',
  'Blisters on the skin': 'blistering',
  'Blood in urine': 'blood_in_urine',
  'Blurry vision': 'blurred_vision',
  'Boils on the skin': 'boils',
  'Burnt / charred skin': 'charred_skin',
  'Chest pain': 'chest_pain',
  'Tightness in the chest': 'chest_tightness',
  'Cough lasting more than 2-3 weeks': 'chronic_cough',
  'Diarrhoea lasting more than 2 weeks': 'chronic_diarrhoea',
  'Confusion / not thinking clearly': 'confusion',
  'Diarrhoea / watery stool': 'diarrhoea',
  'Difficulty breathing': 'difficulty_breathing',
  'Difficulty swallowing': 'difficulty_swallowing',
  'Unusually thirsty': 'excessive_thirst',
  'Breathless with activity or exercise': 'exertional_breathlessness',
  'Discharge from the eye': 'eye_discharge',
  'Itchy, irritated eyes': 'eye_itchiness',
  'Eye pain': 'eye_pain',
  'Red eyes': 'eye_redness',
  'Rapid breathing (adult)': 'fast_breathing',
  'Fast breathing (in a newborn baby)': 'fast_breathing_neonate',
  "Fear of water / can't swallow liquids": 'fear_of_water',
  'Urinating more often than usual': 'frequent_urination',
  'General weakness': 'general_weakness',
  'Head pain': 'head_pain',
  'Itchy raised bumps on the skin (hives)': 'hives',
  'Hoarse or rough voice': 'hoarse_voice',
  'Unusually irritable or fussy': 'irritability',
  'Itchy eyes': 'itchy_eyes',
  'Itchy rash': 'itchy_rash',
  'Joint pain': 'joint_pain',
  'Swelling in the leg': 'leg_swelling',
  'Unusually sleepy or low energy': 'lethargy',
  'Feeling light-headed': 'light_headedness',
  'Weakness in an arm or leg': 'limb_weakness',
  'Difficulty moving normally': 'limited_movement',
  'Swelling in one spot': 'local_swelling',
  'Low energy': 'low_energy',
  'Mild cough': 'mild_cough',
  'Mild headache': 'mild_headache',
  'Mild sore throat': 'mild_sore_throat',
  'Mild swelling': 'mild_swelling',
  'Sores in the mouth': 'mouth_sores',
  'Stiff muscles': 'muscle_stiffness',
  'Feeling like you might faint': 'near_fainting',
  'Fever in a newborn baby': 'neonatal_fever',
  'Sweating heavily at night': 'night_sweats',
  "Cough that's worse at night": 'nocturnal_cough',
  'Nosebleed': 'nosebleed',
  'Headache on one side of the head': 'one_sided_headache',
  'White patches in the mouth (thrush)': 'oral_thrush',
  'Pain at the burn site': 'pain_at_burn',
  'Pain when chewing': 'pain_on_chewing',
  'Fast or pounding heartbeat (palpitations)': 'palpitations',
  "Ongoing tiredness that doesn't go away": 'persistent_fatigue',
  "Fever that doesn't go away": 'persistent_fever',
  'Poor appetite': 'poor_appetite',
  'Feeding poorly (baby or young child)': 'poor_feeding',
  'Poor growth (not gaining weight/height)': 'poor_growth',
  'Headache that feels like pressure': 'pressure_headache',
  'Drooping eyelid': 'ptosis',
  'Pus coming from the skin': 'pus_discharge',
  'Getting infections again and again': 'recurrent_infections',
  'Struggling with everyday activities': 'reduced_daily_function',
  'Repeated infections': 'repeated_infections',
  'Runny nose': 'runny_nose',
  'Shortness of breath': 'shortness_of_breath',
  'Redness of the skin': 'skin_redness',
  'Swelling of the skin': 'skin_swelling',
  'Sneezing': 'sneezing',
  'Feeling like the room is spinning': 'spinning_sensation',
  'Swelling that is spreading': 'spreading_swelling',
  'Noisy, harsh sound when breathing in': 'stridor',
  'Swollen eyelids': 'swollen_eyelids',
  'Swollen gums': 'swollen_gums',
  'Swollen neck': 'swollen_neck',
  'A grey-white coating in the throat': 'throat_membrane',
  'Throbbing headache': 'throbbing_headache',
  'Tiredness': 'tiredness',
  'Toothache': 'toothache',
  'Feeling unsteady on your feet': 'unsteadiness',
  'Losing weight without trying': 'weight_loss',
  'Wheeze / whistling sound when breathing': 'wheeze',
  'Wound where the bite happened': 'wound_at_bite',

  // --- E9: the 13 global red flag tokens ---
  // Display names supplied by the data engineer
  // (wellapath-knowledge-base mobile_handoff/red_flag_display_map.json).
  // Before this, 12 of the 13 universal danger signs were absent from this
  // map entirely and could not be selected by any UI path — the case bank
  // exercises the rules by feeding tokens straight to the engine, so it
  // could not see the gap. 'Seizures' was already present.
  'Not able to drink or feed at all': 'inability_to_drink',
  'Confusion or unresponsiveness (not their normal self)':
      'altered_consciousness',
  'Struggling to breathe even while sitting still / at rest':
      'breathlessness_at_rest',
  'Collapsed — cold, clammy skin, very weak or fainting':
      'circulatory_collapse',
  'Too weak to stand, sit up, or feed without help': 'prostration',
  'Heavy or uncontrolled bleeding': 'abnormal_bleeding',
  'Blue or grey lips, tongue, or face': 'blue_lips_face',
  'Severe dehydration — sunken eyes, no tears, not passing urine, very drowsy':
      'severe_dehydration',
  'Hard to wake, very drowsy, or not responding normally':
      'impaired_consciousness',
  'Working very hard to breathe — nostrils flaring, chest pulling in, or can\'t speak a full sentence':
      'respiratory_distress',
  'Cold hands and feet, fast weak pulse, very drowsy or fainting': 'shock',
  'Severe allergic reaction — face/throat swelling, widespread hives, and trouble breathing together':
      'anaphylaxis_signs',
};

/// Maps each selectable body area to the display names of relevant symptoms.
/// Keys must match the area strings used in body_area_screen.dart and
/// AssessmentController.setBodyArea(). A null or absent key shows all symptoms.
///
/// Tokens whose clinical body area is "General" (whole body / systemic —
/// e.g. weight_loss, night_sweats) don't correspond to any zone in the body
/// diagram, so each is listed under the body area(s) its own condition's
/// other, more specific symptoms already appear under — the same approach
/// this map already used for Fever/Chills/Weakness before E9. The 4 tokens
/// belonging only to fatigue_weakness (persistent_fatigue, general_weakness,
/// reduced_daily_function, low_energy) have no such sibling at all, so they
/// follow the existing Fatigue/Weakness placement (Legs/Back/Buttocks).
///
/// "Arms" has been removed: zero of the 164 symptom tokens in the KB's
/// vocabulary are arm-specific (confirmed against the full vocabulary, not
/// just the tokens added here) — see PROGRESS.md for the decision record.
/// The two symptoms it used to carry (Swollen hands, Wrist pain — both
/// already generic, location-less tokens) moved to Legs.
const Map<String, List<String>> kBodyAreaSymptoms = {
  // 'General' carries systemic danger signs that belong to no body part —
  // collapse, shock, severe dehydration. E9's symptom expansion avoided a
  // General zone by placing each systemic token under the areas its own
  // condition's other symptoms already used; these have no such sibling,
  // and a caregiver looking for 'collapsed, cold and clammy' will not think
  // 'Legs'. It is listed in the Search tab only — the body diagram has no
  // region to attach it to.
  'General': [
    'Not able to drink or feed at all',
    'Collapsed — cold, clammy skin, very weak or fainting',
    'Too weak to stand, sit up, or feed without help',
    'Heavy or uncontrolled bleeding',
    'Severe dehydration — sunken eyes, no tears, not passing urine, very drowsy',
    'Cold hands and feet, fast weak pulse, very drowsy or fainting',
    'Severe allergic reaction — face/throat swelling, widespread hives, and trouble breathing together',
  ],

  'Head': [
    // 'Seizures' maps to the `seizures` global red flag rule (rf_002, "Active
    // Seizures — this is a universal danger sign"). It was in
    // kSymptomDisplayMap but under no body area, so it was reachable only
    // through the picker's "Show all symptoms" fallback — a caregiver
    // looking under Head for convulsions would not find it. Listed first
    // because it is a danger sign, not an ordinary head symptom.
    'Seizures',
    'Headache',
    'Dizziness',
    'Fever',
    'Bad breath',
    'Bleeding',
    'Blurry vision',
    'Confusion / not thinking clearly',
    'Unusually thirsty',
    'Discharge from the eye',
    'Itchy, irritated eyes',
    'Eye pain',
    'Red eyes',
    "Fear of water / can't swallow liquids",
    'Head pain',
    'Itchy eyes',
    'Feeling light-headed',
    'Mild headache',
    'Sores in the mouth',
    'Feeling like you might faint',
    'Nosebleed',
    'Headache on one side of the head',
    'White patches in the mouth (thrush)',
    'Pain when chewing',
    "Fever that doesn't go away",
    'Headache that feels like pressure',
    'Drooping eyelid',
    'Getting infections again and again',
    'Runny nose',
    'Sneezing',
    'Feeling like the room is spinning',
    'Swollen eyelids',
    'Swollen gums',
    'Throbbing headache',
    'Toothache',
    'Feeling unsteady on your feet',
    'Losing weight without trying',
    'Confusion or unresponsiveness (not their normal self)',
    'Blue or grey lips, tongue, or face',
    'Hard to wake, very drowsy, or not responding normally',
  ],
  'Neck': [
    'Headache',
    'Fever',
    'Weakness',
    'Difficulty swallowing',
    'Hoarse or rough voice',
    'Mild sore throat',
    'Noisy, harsh sound when breathing in',
    'Swollen neck',
    'A grey-white coating in the throat',
  ],
  'Chest': [
    'Cough',
    'Fast breathing',
    'Fever',
    'Weakness',
    'Bleeding',
    'Chest pain',
    'Tightness in the chest',
    'Cough lasting more than 2-3 weeks',
    'Difficulty breathing',
    'Unusually thirsty',
    'Breathless with activity or exercise',
    'Rapid breathing (adult)',
    'Fast breathing (in a newborn baby)',
    'Unusually irritable or fussy',
    'Unusually sleepy or low energy',
    'Mild cough',
    'Fever in a newborn baby',
    'Sweating heavily at night',
    "Cough that's worse at night",
    'Fast or pounding heartbeat (palpitations)',
    'Feeding poorly (baby or young child)',
    'Shortness of breath',
    'Losing weight without trying',
    'Wheeze / whistling sound when breathing',
    'Struggling to breathe even while sitting still / at rest',
    'Working very hard to breathe — nostrils flaring, chest pulling in, or can\'t speak a full sentence',
  ],
  'Abdomen': [
    'Nausea',
    'Vomiting',
    'Abdominal cramps',
    'Watery stool',
    'Stomach pain',
    'Diarrhoea lasting more than 2 weeks',
    'Diarrhoea / watery stool',
    "Fever that doesn't go away",
    'Getting infections again and again',
    'Tiredness',
    'Losing weight without trying',
  ],
  'Legs': [
    'Weakness',
    'Fatigue',
    'Swollen hands',
    'Wrist pain',
    'Swelling in both feet/legs',
    'General weakness',
    'Swelling in the leg',
    'Low energy',
    "Ongoing tiredness that doesn't go away",
    'Poor appetite',
    'Poor growth (not gaining weight/height)',
    'Struggling with everyday activities',
    'Repeated infections',
    'Losing weight without trying',
  ],
  'Back': [
    'Weakness',
    'Fatigue',
    'Body pain',
    'Back pain',
    'General weakness',
    'Joint pain',
    'Weakness in an arm or leg',
    'Difficulty moving normally',
    'Low energy',
    'Stiff muscles',
    "Ongoing tiredness that doesn't go away",
    'Struggling with everyday activities',
  ],
  'Pelvis': [
    'Abdominal cramps',
    'Weakness',
    'Blood in urine',
    'Unusually thirsty',
    'Urinating more often than usual',
    'Tiredness',
  ],
  'Buttocks': [
    'Weakness',
    'Fatigue',
    'General weakness',
    'Low energy',
    "Ongoing tiredness that doesn't go away",
    'Struggling with everyday activities',
  ],
  'Skin symptoms': [
    'Sweating',
    'Fever',
    'Chills',
    'Bitten by an animal',
    'Mark left by a bite',
    'Bleeding',
    'Blisters on the skin',
    'Boils on the skin',
    'Burnt / charred skin',
    'Itchy raised bumps on the skin (hives)',
    'Itchy rash',
    'Swelling in one spot',
    'Mild swelling',
    'Pain at the burn site',
    'Pus coming from the skin',
    'Redness of the skin',
    'Swelling of the skin',
    'Swelling that is spreading',
    'Wound where the bite happened',
  ],
};
