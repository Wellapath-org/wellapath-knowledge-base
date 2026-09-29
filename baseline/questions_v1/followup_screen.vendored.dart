import 'package:flutter/material.dart';
import '../../core/constants/symptom_display_map.dart';
import '../../core/telemetry/contract/telemetry_event.dart';
import 'assessment_controller.dart';
import 'loading_screen.dart';
import 'models/followup_question.dart';
import 'question_engine.dart';

class FollowupScreen extends StatefulWidget {
  final AssessmentController assessmentController;
  final VoidCallback onCancel;
  final String primarySymptomLabel;

  const FollowupScreen({
    super.key,
    required this.assessmentController,
    required this.onCancel,
    required this.primarySymptomLabel,
  });

  @override
  State<FollowupScreen> createState() => _FollowupScreenState();
}

class _FollowupScreenState extends State<FollowupScreen> {
  static const Color _primary = Color(0xFF6B4EFF);

  late final List<FollowupQuestion> _questions;
  int _currentQuestion = 0;
  final Map<int, dynamic> _answers = {};

  static const Map<String, String> _durationTokens = {
    'Less than 3 days': 'days_1_3',
    '3 to 7 days': 'days_3_7',
    '8 to 14 days': 'days_7_plus',
    'More than 14 days': 'weeks_2_plus',
  };

  @override
  void initState() {
    super.initState();
    _questions = QuestionEngine.generateQuestions(
      widget.assessmentController.symptomTokens,
    );
  }

  String _severityToken(double value) {
    if (value <= 0.25) return 'mild';
    if (value <= 0.5) return 'moderate';
    if (value <= 0.75) return 'severe';
    return 'very_severe';
  }

  String? _displayNameForToken(String token) {
    for (final entry in kSymptomDisplayMap.entries) {
      if (entry.value == token) return entry.key;
    }
    return null;
  }

  void _onBack(BuildContext context) {
    if (_currentQuestion > 0) {
      setState(() => _currentQuestion -= 1);
    } else {
      Navigator.of(context).pop();
    }
  }

  void _onNext(BuildContext context) {
    if (_currentQuestion < _questions.length - 1) {
      // Each follow-up question is a step. The question itself is never
      // recorded — no question ID, no category, no answer. `_questions.length`
      // is derived from the selected symptom tokens, which is exactly why the
      // step-view event carries no `step_count`.
      widget.assessmentController.telemetrySession.recordStepView();
      setState(() => _currentQuestion += 1);
    } else {
      _commitAnswers();
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => LoadingScreen(
            assessmentController: widget.assessmentController,
            onCancel: widget.onCancel,
          ),
        ),
      );
    }
  }

  void _commitAnswers() {
    for (final entry in _answers.entries) {
      final question = _questions[entry.key];
      switch (question.type) {
        case QuestionType.severity:
          widget.assessmentController.setSeverityToken(
            _severityToken(entry.value as double),
          );
        case QuestionType.duration:
          widget.assessmentController.setDurationToken(entry.value as String);
        case QuestionType.additionalSymptoms:
          for (final token in entry.value as Set<String>) {
            widget.assessmentController.addSymptomToken(token);
          }
        case QuestionType.redFlagClarifier:
          // Only an explicit yes raises the red flag. "No" leaves the milder
          // near-miss token as the user reported it.
          if (entry.value == 'Yes' && question.redFlagToken != null) {
            widget.assessmentController.addSymptomToken(question.redFlagToken!);
          }
      }
    }
  }

  void _showCancelDialog(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Cancel Assessment'),
        content: const Text(
          'Are you sure you want to cancel your symptom assessment?',
        ),
        actions: [
          OutlinedButton(
            onPressed: () {
              Navigator.of(dialogContext).pop();
              // Recorded before `clearAll()`, so the session still exists.
              // `abandoned` says the user stopped; it says nothing about what
              // had been entered, and nothing was computed at this point.
              widget.assessmentController.telemetrySession.recordComplete(
                CompletionStatus.abandoned,
              );
              widget.assessmentController.clearAll();
              widget.onCancel();
            },
            style: OutlinedButton.styleFrom(
              foregroundColor: _primary,
              side: const BorderSide(color: _primary),
            ),
            child: const Text('Yes, cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            style: ElevatedButton.styleFrom(
              backgroundColor: _primary,
              foregroundColor: Colors.white,
            ),
            child: const Text('No, continue'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final question = _questions[_currentQuestion];
    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(context),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 28, 24, 16),
                child: _buildQuestion(question),
              ),
            ),
            _buildBottomButtons(context),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final progress = (_currentQuestion + 1) / _questions.length;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 16, 8, 8),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 5,
                ),
                decoration: BoxDecoration(
                  color: _primary,
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  'Question ${_currentQuestion + 1} of ${_questions.length}',
                  style: const TextStyle(
                    fontSize: 12,
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.close, size: 22),
                onPressed: () => _showCancelDialog(context),
              ),
            ],
          ),
        ),
        LinearProgressIndicator(
          value: progress,
          backgroundColor: const Color(0xFFEEEEEE),
          color: _primary,
          minHeight: 3,
        ),
      ],
    );
  }

  Widget _buildQuestion(FollowupQuestion question) {
    switch (question.type) {
      case QuestionType.severity:
        return _buildSeveritySection(question);
      case QuestionType.duration:
        return _buildDurationSection(question);
      case QuestionType.additionalSymptoms:
        return _buildAdditionalSymptomsSection(question);
      case QuestionType.redFlagClarifier:
        return _buildRedFlagClarifierSection(question);
    }
  }

  Widget _buildRedFlagClarifierSection(FollowupQuestion question) {
    final selected = _answers[_currentQuestion] as String?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          question.questionText,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Colors.black87,
          ),
        ),
        const SizedBox(height: 20),
        ...question.options.map((option) {
          final isSelected = selected == option;
          return Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: InkWell(
              onTap: () => setState(() => _answers[_currentQuestion] = option),
              borderRadius: BorderRadius.circular(12),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 18,
                ),
                decoration: BoxDecoration(
                  border: Border.all(
                    color: isSelected ? _primary : const Color(0xFFE0E0E0),
                    width: isSelected ? 2 : 1,
                  ),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 22,
                      height: 22,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: isSelected
                              ? _primary
                              : const Color(0xFFBDBDBD),
                          width: 2,
                        ),
                      ),
                      child: isSelected
                          ? Center(
                              child: Container(
                                width: 10,
                                height: 10,
                                decoration: const BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: _primary,
                                ),
                              ),
                            )
                          : null,
                    ),
                    const SizedBox(width: 14),
                    Text(
                      option,
                      style: const TextStyle(
                        fontSize: 16,
                        color: Colors.black87,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildSeveritySection(FollowupQuestion question) {
    final value = (_answers[_currentQuestion] as double?) ?? 0.0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          question.questionText,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Colors.black87,
          ),
        ),
        const SizedBox(height: 20),
        _SegmentedSeveritySlider(
          value: value,
          onChanged: (v) => setState(() => _answers[_currentQuestion] = v),
        ),
        const SizedBox(height: 8),
        const Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Mild', style: TextStyle(fontSize: 12, color: Colors.black54)),
            Text(
              'Moderate',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
            Text(
              'Severe',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
            Text(
              'Unbearable',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildDurationSection(FollowupQuestion question) {
    final selection = _answers[_currentQuestion] as String?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          question.questionText,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Colors.black87,
          ),
        ),
        const SizedBox(height: 16),
        ..._durationTokens.entries.map((entry) {
          final isSelected = selection == entry.value;
          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            clipBehavior: Clip.antiAlias,
            decoration: BoxDecoration(
              border: Border.all(
                color: isSelected ? _primary : const Color(0xFFE0E0E0),
                width: isSelected ? 2 : 1,
              ),
              borderRadius: BorderRadius.circular(12),
            ),
            child: InkWell(
              onTap: () =>
                  setState(() => _answers[_currentQuestion] = entry.value),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 14,
                ),
                child: Row(
                  children: [
                    _buildRadioCircle(isSelected),
                    const SizedBox(width: 14),
                    Text(
                      entry.key,
                      style: const TextStyle(
                        fontWeight: FontWeight.w500,
                        fontSize: 15,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        }),
      ],
    );
  }

  Widget _buildRadioCircle(bool isSelected) {
    return Container(
      width: 20,
      height: 20,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: isSelected ? _primary : const Color(0xFFBDBDBD),
          width: 2,
        ),
      ),
      alignment: Alignment.center,
      child: isSelected
          ? Container(
              width: 10,
              height: 10,
              decoration: const BoxDecoration(
                shape: BoxShape.circle,
                color: _primary,
              ),
            )
          : null,
    );
  }

  Widget _buildAdditionalSymptomsSection(FollowupQuestion question) {
    final selected = (_answers[_currentQuestion] as Set<String>?) ?? <String>{};
    final availableTokens = question.options
        .where((token) => _displayNameForToken(token) != null)
        .toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          question.questionText,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Colors.black87,
          ),
        ),
        const SizedBox(height: 12),
        ...availableTokens.map((token) {
          final displayName = _displayNameForToken(token)!;
          return CheckboxListTile(
            title: Text(displayName, style: const TextStyle(fontSize: 15)),
            value: selected.contains(token),
            onChanged: (checked) {
              setState(() {
                final updated = Set<String>.of(selected);
                if (checked == true) {
                  updated.add(token);
                } else {
                  updated.remove(token);
                }
                _answers[_currentQuestion] = updated;
              });
            },
            activeColor: _primary,
            controlAffinity: ListTileControlAffinity.leading,
            contentPadding: EdgeInsets.zero,
            visualDensity: const VisualDensity(vertical: -2),
          );
        }),
      ],
    );
  }

  Widget _buildBottomButtons(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Row(
        children: [
          Expanded(
            child: OutlinedButton(
              onPressed: () => _onBack(context),
              style: OutlinedButton.styleFrom(
                foregroundColor: _primary,
                side: const BorderSide(color: _primary),
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              child: const Text(
                'Back',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: ElevatedButton(
              onPressed: () => _onNext(context),
              style: ElevatedButton.styleFrom(
                backgroundColor: _primary,
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              child: const Text(
                'Next',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── Segmented severity slider ────────────────────────────────────────────────

class _SegmentedSeveritySlider extends StatelessWidget {
  final double value;
  final ValueChanged<double> onChanged;

  const _SegmentedSeveritySlider({
    required this.value,
    required this.onChanged,
  });

  static const List<Color> _segmentColors = [
    Color(0xFF4ADE80),
    Color(0xFF86EFAC),
    Color(0xFFFDE68A),
    Color(0xFFFBBF24),
    Color(0xFFF97316),
    Color(0xFFEF4444),
    Color(0xFFDC2626),
  ];

  @override
  Widget build(BuildContext context) {
    final activeCount = (value * 7).ceil().clamp(0, 7);
    return Row(
      children: List.generate(7, (i) {
        final isActive = i < activeCount;
        return Expanded(
          child: GestureDetector(
            onTap: () => onChanged((i + 1) / 7),
            child: Container(
              height: 36,
              margin: const EdgeInsets.symmetric(horizontal: 2),
              decoration: BoxDecoration(
                color: isActive ? _segmentColors[i] : const Color(0xFFE5E7EB),
                borderRadius: BorderRadius.circular(6),
              ),
            ),
          ),
        );
      }),
    );
  }
}
