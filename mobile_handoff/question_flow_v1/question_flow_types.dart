// GENERATED CONTRACT TYPES — Adaptive Question Flow 1.0 (candidate)
//
// Source of truth: wellapath-knowledge-base
//   schema/question_flow.v1.schema.json
//   docs/W3_QUESTION_FLOW_CONTRACT.md
//   candidate/question_flow.ng.v1.0.json
//
// STATUS: the artifact these types describe is a CANDIDATE. It is not
// published, not clinically approved, and NOT consumed by any build. Do not
// wire this into a shipping build. It exists so the contract is not guessed.
//
// THE THREE RULES THAT MATTER
//   1. A red-flag-affecting answer is evaluated IMMEDIATELY, before the next
//      ordinary question is selected and before scoring.
//   2. A red-flag-affecting question is NEVER dropped to satisfy a length
//      limit. If they exceed the limit, the limit yields.
//   3. Editing an answer CLEARS its dependents and the tokens they produced.
//      Never keep a downstream answer and hope it still applies.

// ---------------------------------------------------------------------------
// Condition language — 13 operators, no others
// ---------------------------------------------------------------------------

/// The complete operator set. Anything else is a malformed artifact.
///
/// There is deliberately no regex, no free-text match, no fuzzy or
/// probabilistic operator. Branching is a pure function of on-device state.
enum ConditionOperator {
  all,
  any,
  not,
  equals,
  oneOf,
  tokenPresent,
  tokenAbsent,
  priorAnswerEquals,
  ageRange,
  sex,
  pregnancy,
  always,
  never,
}

const Map<String, ConditionOperator> kConditionOperators = <String, ConditionOperator>{
  'all': ConditionOperator.all,
  'any': ConditionOperator.any,
  'not': ConditionOperator.not,
  'equals': ConditionOperator.equals,
  'one_of': ConditionOperator.oneOf,
  'token_present': ConditionOperator.tokenPresent,
  'token_absent': ConditionOperator.tokenAbsent,
  'prior_answer_equals': ConditionOperator.priorAnswerEquals,
  'age_range': ConditionOperator.ageRange,
  'sex': ConditionOperator.sex,
  'pregnancy': ConditionOperator.pregnancy,
  'always': ConditionOperator.always,
  'never': ConditionOperator.never,
};

/// The only fields a condition may read.
enum ConditionField { sex, ageToken, bodyArea, assessmentPhase }

/// Everything a condition is allowed to see. Nothing else is in scope —
/// no session, no network, no device identifiers.
class QuestionAssessmentState {
  const QuestionAssessmentState({
    this.tokens = const <String>{},
    this.answers = const <String, String>{},
    this.sex,
    this.ageToken,
    this.ageYears,
    this.pregnancy,
    this.bodyArea,
    this.assessmentPhase = 'followup',
  });

  final Set<String> tokens;

  /// question_id -> answer_option_id.
  final Map<String, String> answers;

  /// Null means UNANSWERED, which is not the same as "no". An unanswered
  /// sex/pregnancy/age satisfies neither branch of its condition, so a gated
  /// question is not asked rather than wrongly asked.
  final String? sex;
  final String? ageToken;
  final int? ageYears;
  final bool? pregnancy;
  final String? bodyArea;
  final String assessmentPhase;
}

// ---------------------------------------------------------------------------
// Question model
// ---------------------------------------------------------------------------

enum QuestionFlowType { singleSelect, multiSelect, scaleSelect, yesNo }

enum QuestionClinicalRole {
  redFlagClarifier,
  severity,
  duration,
  additionalSymptoms,
  demographic,
  bodyArea,
  symptomPicker,
}

/// Where a question sits in the assessment lifecycle. These are DISTINCT
/// states, not shades of "unanswered" — collapsing them is how a skipped
/// question becomes indistinguishable from a refused one.
enum QuestionAnswerState {
  /// trigger_condition is false. No answer state is stored at all.
  notApplicable,

  /// Presented, awaiting an answer.
  unanswered,

  /// Answered normally.
  answered,

  /// Optional and explicitly skipped. Produces NO clinical token.
  skipped,

  /// Cleared because an upstream answer changed. Back to unanswered.
  invalidatedByEdit,
}

class QuestionAnswerOption {
  const QuestionAnswerOption({
    required this.answerOptionId,
    required this.label,
    required this.producesTokens,
    required this.isSkipSentinel,
    this.value,
  });

  final String answerOptionId;
  final String label;

  /// Tokens this answer contributes. A skip sentinel MUST produce none.
  final List<String> producesTokens;

  final bool isSkipSentinel;
  final Object? value;

  factory QuestionAnswerOption.fromJson(Map<String, dynamic> json) {
    return QuestionAnswerOption(
      answerOptionId: json['answer_option_id'] as String,
      label: json['label'] as String,
      producesTokens: ((json['produces_tokens'] as List<dynamic>?) ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false),
      isSkipSentinel: json['is_skip_sentinel'] as bool? ?? false,
      value: json['value'],
    );
  }
}

class RedFlagEvaluationHook {
  const RedFlagEvaluationHook({
    required this.canAffectRedFlag,
    required this.evaluateAfterAnswer,
    required this.blocksNextQuestion,
  });

  final bool canAffectRedFlag;

  /// Evaluate red flags immediately after this answer is captured.
  final bool evaluateAfterAnswer;

  /// Do not select or present the next ordinary question until evaluation
  /// completes. If a red flag fires, branching stops here.
  final bool blocksNextQuestion;

  factory RedFlagEvaluationHook.fromJson(Map<String, dynamic> json) {
    return RedFlagEvaluationHook(
      // Fail safe: an unreadable hook is treated as red-flag-affecting, so the
      // engine evaluates too often rather than too late.
      canAffectRedFlag: json['can_affect_red_flag'] as bool? ?? true,
      evaluateAfterAnswer: json['evaluate_after_answer'] as bool? ?? true,
      blocksNextQuestion: json['blocks_next_question'] as bool? ?? true,
    );
  }
}

class QuestionEffects {
  const QuestionEffects({
    required this.producesTokens,
    required this.affectsScoring,
    required this.affectsRedFlags,
  });

  final List<String> producesTokens;
  final bool affectsScoring;
  final bool affectsRedFlags;

  factory QuestionEffects.fromJson(Map<String, dynamic> json) {
    return QuestionEffects(
      producesTokens: ((json['produces_tokens'] as List<dynamic>?) ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false),
      affectsScoring: json['affects_scoring'] as bool? ?? false,
      affectsRedFlags: json['affects_red_flags'] as bool? ?? true,
    );
  }
}

class FlowQuestion {
  const FlowQuestion({
    required this.questionId,
    required this.questionType,
    required this.clinicalRole,
    required this.sourceText,
    required this.contentApproved,
    required this.required,
    required this.skippable,
    required this.answerOptions,
    required this.triggerCondition,
    required this.priority,
    required this.tieBreakKey,
    required this.pathLengthContribution,
    required this.redFlagEvaluation,
    required this.effects,
    required this.invalidatesOnChange,
  });

  final String questionId;
  final QuestionFlowType questionType;
  final QuestionClinicalRole clinicalRole;

  /// Verbatim source text, carried for traceability. Render APPROVED content;
  /// this is not approved copy until contentApproved is true (it is false for
  /// every question in the current candidate).
  final String sourceText;
  final bool contentApproved;

  final bool required;

  /// A required question must never be skippable. The artifact is validated
  /// for this, and a consumer should treat a violation as a load failure.
  final bool skippable;

  final List<QuestionAnswerOption> answerOptions;

  /// Raw condition tree. Evaluate with the shared evaluator; never with an
  /// expression parser or anything that can execute code.
  final Map<String, dynamic> triggerCondition;

  /// Ordering is (priority, tieBreakKey, questionId). Never map order.
  final int priority;
  final String tieBreakKey;

  final int pathLengthContribution;
  final RedFlagEvaluationHook redFlagEvaluation;
  final QuestionEffects effects;

  /// Question IDs whose answers must be CLEARED when this answer changes.
  final List<String> invalidatesOnChange;

  factory FlowQuestion.fromJson(Map<String, dynamic> json) {
    final Map<String, dynamic> content =
        (json['content_ref'] as Map<String, dynamic>?) ?? <String, dynamic>{};
    return FlowQuestion(
      questionId: json['question_id'] as String,
      questionType: switch (json['question_type']) {
        'multi_select' => QuestionFlowType.multiSelect,
        'scale_select' => QuestionFlowType.scaleSelect,
        'yes_no' => QuestionFlowType.yesNo,
        _ => QuestionFlowType.singleSelect,
      },
      clinicalRole: switch (json['clinical_role']) {
        'red_flag_clarifier' => QuestionClinicalRole.redFlagClarifier,
        'severity' => QuestionClinicalRole.severity,
        'duration' => QuestionClinicalRole.duration,
        'additional_symptoms' => QuestionClinicalRole.additionalSymptoms,
        'body_area' => QuestionClinicalRole.bodyArea,
        'symptom_picker' => QuestionClinicalRole.symptomPicker,
        _ => QuestionClinicalRole.demographic,
      },
      sourceText: content['source_text'] as String? ?? '',
      contentApproved: content['content_approved'] as bool? ?? false,
      required: json['required'] as bool? ?? true,
      skippable: json['skippable'] as bool? ?? false,
      answerOptions: ((json['answer_options'] as List<dynamic>?) ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(QuestionAnswerOption.fromJson)
          .toList(growable: false),
      triggerCondition:
          (json['trigger_condition'] as Map<String, dynamic>?) ?? <String, dynamic>{'never': true},
      priority: (json['priority'] as num?)?.toInt() ?? 9999,
      tieBreakKey: json['tie_break_key'] as String? ?? (json['question_id'] as String),
      pathLengthContribution: (json['path_length_contribution'] as num?)?.toInt() ?? 1,
      redFlagEvaluation: RedFlagEvaluationHook.fromJson(
        (json['red_flag_evaluation'] as Map<String, dynamic>?) ?? <String, dynamic>{},
      ),
      effects: QuestionEffects.fromJson(
        (json['effects'] as Map<String, dynamic>?) ?? <String, dynamic>{},
      ),
      invalidatesOnChange: ((json['invalidates_on_change'] as List<dynamic>?) ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false),
    );
  }

  /// The declared deterministic sort key. Use this and nothing else.
  Comparable<Object> get orderKey => _OrderKey(priority, tieBreakKey, questionId);
}

class _OrderKey implements Comparable<Object> {
  const _OrderKey(this.priority, this.tieBreakKey, this.questionId);

  final int priority;
  final String tieBreakKey;
  final String questionId;

  @override
  int compareTo(Object other) {
    if (other is! _OrderKey) return 0;
    final int byPriority = priority.compareTo(other.priority);
    if (byPriority != 0) return byPriority;
    final int byTieBreak = tieBreakKey.compareTo(other.tieBreakKey);
    if (byTieBreak != 0) return byTieBreak;
    return questionId.compareTo(other.questionId);
  }
}

class QuestionPathControls {
  const QuestionPathControls({
    required this.maxQuestionsPerAssessment,
    required this.maxFollowupQuestions,
    required this.redFlagQuestionsExemptFromTruncation,
    required this.truncationAllowed,
  });

  final int maxQuestionsPerAssessment;
  final int maxFollowupQuestions;

  /// Always true. A red-flag-affecting question is never dropped to satisfy a
  /// length limit; if they exceed it, the limit yields.
  final bool redFlagQuestionsExemptFromTruncation;

  final bool truncationAllowed;

  factory QuestionPathControls.fromJson(Map<String, dynamic> json) {
    return QuestionPathControls(
      maxQuestionsPerAssessment: (json['max_questions_per_assessment'] as num?)?.toInt() ?? 11,
      maxFollowupQuestions: (json['max_followup_questions'] as num?)?.toInt() ?? 5,
      // Fail safe: absence means exempt.
      redFlagQuestionsExemptFromTruncation:
          json['red_flag_questions_exempt_from_truncation'] as bool? ?? true,
      truncationAllowed: json['truncation_allowed'] as bool? ?? true,
    );
  }
}

class QuestionFlowArtifact {
  const QuestionFlowArtifact({
    required this.version,
    required this.schemaVersion,
    required this.releaseStatus,
    required this.mayPublish,
    required this.questions,
    required this.pathControls,
  });

  final String version;
  final String schemaVersion;

  /// A build must refuse anything that is not 'published'.
  final String releaseStatus;
  final bool mayPublish;

  final List<FlowQuestion> questions;
  final QuestionPathControls pathControls;

  bool get isUsableInProduction => releaseStatus == 'published' && mayPublish;

  factory QuestionFlowArtifact.fromJson(Map<String, dynamic> json) {
    final Map<String, dynamic> metadata =
        (json['_metadata'] as Map<String, dynamic>?) ?? <String, dynamic>{};
    return QuestionFlowArtifact(
      version: metadata['version'] as String? ?? '0.0',
      schemaVersion: metadata['schema_version'] as String? ?? '1.0',
      releaseStatus: metadata['release_status'] as String? ?? 'candidate_unapproved',
      mayPublish: metadata['may_publish'] as bool? ?? false,
      questions: ((json['questions'] as List<dynamic>?) ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(FlowQuestion.fromJson)
          .toList(growable: false),
      pathControls: QuestionPathControls.fromJson(
        (json['path_controls'] as Map<String, dynamic>?) ?? <String, dynamic>{},
      ),
    );
  }
}
