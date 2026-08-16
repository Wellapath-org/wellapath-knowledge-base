import '../../core/constants/followup_question_map.dart';
import '../../core/constants/red_flag_clarifiers.dart';
import 'models/followup_question.dart';

class QuestionEngine {
  const QuestionEngine._();

  static List<FollowupQuestion> generateQuestions(List<String> symptomTokens) {
    FollowupQuestion? severityQuestion;
    FollowupQuestion? durationQuestion;
    String? additionalQuestionText;
    final List<String> additionalOptions = [];
    bool needsDefaultDuration = false;

    for (final token in symptomTokens) {
      final questions = kFollowupQuestionMap[token];
      if (questions == null) {
        needsDefaultDuration = true;
        continue;
      }
      for (final question in questions) {
        switch (question.type) {
          case QuestionType.severity:
            severityQuestion ??= question;
          case QuestionType.duration:
            durationQuestion ??= question;
          case QuestionType.redFlagClarifier:
            // Not authored in kFollowupQuestionMap — generated below.
            break;
          case QuestionType.additionalSymptoms:
            additionalQuestionText ??= question.questionText;
            for (final option in question.options) {
              if (!additionalOptions.contains(option)) {
                additionalOptions.add(option);
              }
            }
        }
      }
    }

    if (needsDefaultDuration) {
      durationQuestion ??= kDefaultFollowupQuestion;
    }

    // A clarifier is asked only when a near-miss token was selected and the
    // red flag itself was not — if the user already picked the red flag
    // directly there is nothing left to clarify.
    final Set<String> selected = symptomTokens.toSet();
    final List<FollowupQuestion> clarifiers = [
      for (final clarifier in kRedFlagClarifiers)
        if (!selected.contains(clarifier.redFlagToken) &&
            clarifier.triggerTokens.any(selected.contains))
          FollowupQuestion(
            type: QuestionType.redFlagClarifier,
            questionText: clarifier.questionText,
            options: const ['Yes', 'No'],
            redFlagToken: clarifier.redFlagToken,
          ),
    ];

    final List<FollowupQuestion> result = [
      // Clarifiers first: they decide whether this is an emergency, which
      // matters more than severity or duration detail.
      ...clarifiers,
      ?severityQuestion,
      ?durationQuestion,
      if (additionalOptions.isNotEmpty)
        FollowupQuestion(
          type: QuestionType.additionalSymptoms,
          questionText: additionalQuestionText!,
          options: additionalOptions,
        ),
    ];

    return result.length > 5 ? result.sublist(0, 5) : result;
  }
}
