enum QuestionType { severity, duration, additionalSymptoms, redFlagClarifier }

class FollowupQuestion {
  final QuestionType type;
  final String questionText;
  final List<String> options;

  /// Set only on [QuestionType.redFlagClarifier]: the global red flag token
  /// added to the assessment when the user answers yes.
  final String? redFlagToken;

  const FollowupQuestion({
    required this.type,
    required this.questionText,
    this.options = const [],
    this.redFlagToken,
  });
}
