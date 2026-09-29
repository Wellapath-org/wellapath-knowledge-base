// GENERATED CONTRACT TYPES — Adaptive Question Flow 1.1 (candidate)
//
// Source of truth: wellapath-knowledge-base
//   schema/question_flow.v1_1.schema.json
//   docs/W3_QUESTION_GROUPING_CONTRACT.md
//   candidate/question_flow.ng.v1.1.json
//
// ADDITIVE COMPANION to question_flow_v1/question_flow_types.dart. Everything
// there still applies — condition language, ordering, red-flag hooks, path
// controls. This file adds only what schema 1.1 added: grouping.
//
// STATUS: the artifact these types describe is a CANDIDATE. Not published, not
// clinically approved, NOT consumed by any build. Do not wire this into a
// shipping build. It exists so the contract is not guessed.
//
// THE FOUR RULES THAT MATTER HERE
//   1. A group presents EXACTLY ONE question. Two questions for one group_key
//      is a contract violation, not a rendering choice.
//   2. A red-flag clarifier is NEVER grouped. Each carries its own red-flag
//      token; merging two deletes a danger-sign question.
//   3. Grouping happens BEFORE truncation. Counting un-merged questions against
//      the limit of 5 drops questions the live engine asks.
//   4. `groupKey` groups. `tieBreakKey` orders. They are different fields with
//      different meanings and must never be used for each other's job.

// ---------------------------------------------------------------------------
// Merge rules — closed sets. An unknown value is a load failure, never a
// default. A consumer that silently ignores a merge rule it does not
// understand presents a different question set than the one that was reviewed.
// ---------------------------------------------------------------------------

/// How a group turns several sources into one presented question.
enum QuestionMergeStrategy {
  /// The group yields exactly one question: wording from the representative,
  /// options from the option-union rule.
  singleRepresentative,
}

const Map<String, QuestionMergeStrategy> kQuestionMergeStrategies =
    <String, QuestionMergeStrategy>{
  'single_representative': QuestionMergeStrategy.singleRepresentative,
};

/// Which triggered source supplies the wording.
enum RepresentativeSelection {
  /// The triggered source with the smallest `sourceOrderIndex`.
  ///
  /// This is the declared replacement for the live engine's first-tapped-wins.
  /// It depends only on the artifact, so the same symptom SET always produces
  /// the same wording no matter what order the user tapped.
  lowestSourceOrderIndex,
}

const Map<String, RepresentativeSelection> kRepresentativeSelections =
    <String, RepresentativeSelection>{
  'lowest_source_order_index': RepresentativeSelection.lowestSourceOrderIndex,
};

/// Which options the merged question presents.
enum OptionUnionRule {
  /// The question's own `answerOptions`, unchanged, whichever sources fired.
  /// Used where every source offers identical answers (severity, duration).
  static_,

  /// The union of the answer options of the TRIGGERED sources only,
  /// de-duplicated by `answerOptionId`, ordered by
  /// (`sourceOrderIndex`, position within that source).
  ///
  /// "Triggered only" is the part that is easy to get wrong: presenting the
  /// full union would offer the user symptoms they never selected a source for.
  unionOfTriggeredSources,
}

const Map<String, OptionUnionRule> kOptionUnionRules = <String, OptionUnionRule>{
  'static': OptionUnionRule.static_,
  'union_of_triggered_sources': OptionUnionRule.unionOfTriggeredSources,
};

/// What happens when triggered sources disagree.
class GroupConflictResolution {
  const GroupConflictResolution({
    required this.onTextConflict,
    required this.onOptionConflict,
    required this.onValueTypeConflict,
  });

  /// Always `representative_wins`: the baseline shows the first-visited wording
  /// and never the others.
  final String onTextConflict;

  /// `union_preserving_all_sources` — no triggered source's option may be lost.
  /// `reject` — a disagreement is a contract failure.
  final String onOptionConflict;

  /// Always `reject`. Merging two answer shapes would change what an answer
  /// MEANS, which no grouping rule is permitted to do.
  final String onValueTypeConflict;
}

// ---------------------------------------------------------------------------
// Sources
// ---------------------------------------------------------------------------

/// One baseline authoring site that can feed a merged question.
///
/// In the live engine these are the per-token entries of
/// `kFollowupQuestionMap`. The engine visits them in user-selection order and
/// keeps the first; here they are declared explicitly so selection is resolved
/// by a stated rule instead of by tap order.
class QuestionGroupSource {
  const QuestionGroupSource({
    required this.sourceId,
    required this.sourceToken,
    required this.sourceOrderIndex,
    required this.triggerCondition,
    required this.sourceText,
    required this.provenance,
    this.answerOptions = const <QuestionAnswerOptionRef>[],
  });

  /// Unique within a grouping block.
  final String sourceId;

  /// The canonical token whose selection makes this source contribute.
  final String sourceToken;

  /// Total order over the group's sources. Unique within a grouping block, and
  /// a property of the artifact — never of a run, a map iteration or a build.
  final int sourceOrderIndex;

  /// Must imply the owning question's trigger. A source that can fire where its
  /// question cannot would need a question that is never presented.
  final Map<String, Object?> triggerCondition;

  /// Verbatim baseline wording. Rendered ONLY if this source is the
  /// representative — never concatenated with another source's text.
  final String sourceText;

  final String provenance;

  /// Populated only under [OptionUnionRule.unionOfTriggeredSources]. Every
  /// entry also appears in the owning question's `answerOptions`; the union can
  /// never introduce an option the question does not declare.
  final List<QuestionAnswerOptionRef> answerOptions;
}

/// An answer option as referenced by a source. Identity is the option id; the
/// label, value and produced tokens must match the question's declaration
/// exactly, so which source triggered can never change what an answer means.
class QuestionAnswerOptionRef {
  const QuestionAnswerOptionRef({
    required this.answerOptionId,
    required this.label,
    required this.producesTokens,
  });

  final String answerOptionId;
  final String label;
  final List<String> producesTokens;
}

// ---------------------------------------------------------------------------
// The grouping block
// ---------------------------------------------------------------------------

/// Declares that several baseline sites collapse into ONE presented question.
///
/// Absent from a question means that question never merges. That is the correct
/// reading of every question schema 1.0 could express, which is why the field is
/// optional rather than required.
class QuestionGrouping {
  const QuestionGrouping({
    required this.groupKey,
    required this.mergeStrategy,
    required this.representativeSelection,
    required this.optionUnionRule,
    required this.sources,
    this.optionOrder,
    this.conflictResolution,
  });

  /// Identity of the merged question. At most one question may be presented per
  /// `groupKey` on any path.
  ///
  /// NOT `tieBreakKey`. `tieBreakKey` is an ordering key; two questions sharing
  /// one is an unresolved order tie, never an implied merge.
  final String groupKey;

  final QuestionMergeStrategy mergeStrategy;
  final RepresentativeSelection representativeSelection;
  final OptionUnionRule optionUnionRule;

  /// `source_order_then_declared_order` when present. Stated so two consumers
  /// cannot present the same option set in a different order.
  final String? optionOrder;

  final GroupConflictResolution? conflictResolution;

  final List<QuestionGroupSource> sources;

  /// The sources whose trigger holds for [selectedTokens], lowest order first.
  ///
  /// Takes a Set, deliberately. The live defect this contract corrects is a
  /// dependence on selection ORDER; accepting a List here would leave the door
  /// open to reintroducing it.
  List<QuestionGroupSource> triggeredSources(
    Set<String> selectedTokens,
    bool Function(Map<String, Object?> condition, Set<String> tokens) evaluate,
  ) {
    final List<QuestionGroupSource> triggered = <QuestionGroupSource>[
      for (final QuestionGroupSource source in sources)
        if (evaluate(source.triggerCondition, selectedTokens)) source,
    ];
    triggered.sort(
      (QuestionGroupSource a, QuestionGroupSource b) =>
          a.sourceOrderIndex.compareTo(b.sourceOrderIndex),
    );
    return triggered;
  }

  /// The wording to render, or null when nothing triggered.
  String? representativeText(List<QuestionGroupSource> triggered) =>
      triggered.isEmpty ? null : triggered.first.sourceText;

  /// The option ids to present, in contract order.
  ///
  /// Under [OptionUnionRule.static_] the caller supplies the question's own
  /// option ids; under the union rule this walks the triggered sources only.
  List<String> presentedOptionIds(
    List<QuestionGroupSource> triggered,
    List<String> questionOptionIds,
  ) {
    if (optionUnionRule == OptionUnionRule.static_) {
      return List<String>.unmodifiable(questionOptionIds);
    }
    final List<String> ordered = <String>[];
    final Set<String> seen = <String>{};
    for (final QuestionGroupSource source in triggered) {
      for (final QuestionAnswerOptionRef option in source.answerOptions) {
        if (seen.add(option.answerOptionId)) {
          ordered.add(option.answerOptionId);
        }
      }
    }
    return List<String>.unmodifiable(ordered);
  }
}

// ---------------------------------------------------------------------------
// Artifact-level declaration
// ---------------------------------------------------------------------------

/// `_metadata.grouping_semantics`. A consumer that cannot honour this must
/// REFUSE the artifact — ignoring it silently changes the question set.
class QuestionGroupingSemantics {
  const QuestionGroupingSemantics({
    required this.enabled,
    required this.groupableRoles,
    required this.nonGroupableRoles,
    required this.groupingPhase,
    required this.oneQuestionPerGroupKey,
  });

  final bool enabled;
  final List<String> groupableRoles;

  /// Always contains `red_flag_clarifier`. If it does not, refuse the artifact:
  /// the one declaration standing between a merge rule and a deleted
  /// danger-sign question has gone missing.
  final List<String> nonGroupableRoles;

  /// Always `before_truncation`.
  final String groupingPhase;

  /// Always true.
  final bool oneQuestionPerGroupKey;
}

// ---------------------------------------------------------------------------
// Version negotiation
// ---------------------------------------------------------------------------

/// Schema versions this consumer implements.
///
/// A 1.0-only consumer MUST refuse 1.1. It would parse a 1.1 artifact without
/// error — the grouping block is simply an unknown field to it — and then
/// present the full option union instead of the triggered union, offering the
/// user symptoms no selected token contributed. Silent partial understanding is
/// the failure mode this constant exists to prevent.
const Set<String> kSupportedQuestionFlowSchemaVersions = <String>{'1.1'};

/// Refuses anything this build cannot fully apply.
bool isSupportedQuestionFlowSchema(String schemaVersion) =>
    kSupportedQuestionFlowSchemaVersions.contains(schemaVersion);
