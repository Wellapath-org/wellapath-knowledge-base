/// E9 — clarifying questions that decide whether a milder "near-miss" symptom
/// selection should also raise a global red flag token.
///
/// The data engineer's `red_flag_display_map.json` classifies each red flag's
/// near-misses into two groups, and the engineering lead ruled on both:
///
///  * **escalate-safe** (e.g. `confusion` -> `altered_consciousness`): the red
///    flag token is added to the picker directly, so a caregiver selecting
///    either one reaches the red flag. No question needed — handled by the
///    display map, not this file.
///  * **needs-clarifying-question** (e.g. `difficulty_breathing` ->
///    `breathlessness_at_rest`): do NOT auto-escalate. Ask one question; only
///    a "yes" adds the red flag token.
///
/// The distinction matters clinically. `difficulty_breathing` covers everything
/// from mild breathlessness upward — aliasing it to a red flag would fire an
/// emergency for a large share of ordinary respiratory presentations. Asking
/// keeps the emergency path for the people who need it.
class RedFlagClarifier {
  const RedFlagClarifier({
    required this.triggerTokens,
    required this.redFlagToken,
    required this.questionText,
  });

  /// Any of these being selected raises the question.
  final List<String> triggerTokens;

  /// Added to the assessment only on an explicit "yes".
  final String redFlagToken;

  final String questionText;
}

/// Question text is the data engineer's own wording from the map's `note`
/// field, kept verbatim so the clinical phrasing is not paraphrased in transit.
const List<RedFlagClarifier> kRedFlagClarifiers = [
  RedFlagClarifier(
    triggerTokens: ['difficulty_breathing', 'shortness_of_breath'],
    redFlagToken: 'breathlessness_at_rest',
    questionText:
        'Is it hard to breathe even when resting, not just on activity?',
  ),
  RedFlagClarifier(
    triggerTokens: ['poor_feeding', 'poor_appetite'],
    redFlagToken: 'inability_to_drink',
    questionText: 'Is the person completely unable to drink or feed anything?',
  ),
  RedFlagClarifier(
    triggerTokens: ['bleeding', 'nosebleed'],
    redFlagToken: 'abnormal_bleeding',
    questionText: 'Is the bleeding heavy, or does it not stop?',
  ),
];
