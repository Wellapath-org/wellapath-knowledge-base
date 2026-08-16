import 'package:flutter/foundation.dart';
import '../../core/telemetry/assessment_telemetry_session.dart';
import 'models/assessment_input.dart';

class AssessmentController extends ChangeNotifier {
  /// Telemetry correlation for this assessment attempt.
  ///
  /// One controller is constructed per assessment (see
  /// `HomeScreen._goToIntro`), so the session ID is created here and is never
  /// reused by a later assessment. It holds an opaque random ID and three
  /// counters; it reads nothing from this controller's clinical state, and no
  /// method on it is given access to one.
  ///
  /// Telemetry is a no-op unless explicitly enabled by configuration, so this
  /// costs one random string per assessment in every other build.
  final AssessmentTelemetrySession telemetrySession =
      AssessmentTelemetrySession();

  String? _sex;
  String? _ageToken;
  final List<String> _demographicTokens = [];
  final List<String> _symptomTokens = [];
  final List<String> _severityTokens = [];
  final List<String> _durationTokens = [];
  String? _selectedBodyArea;

  /// Feeds `EngineController(currentSeason:)`, which gates the seasonal
  /// modifiers on 21 conditions in kb.ng.v2.3.
  ///
  /// Nothing sets this yet: the knowledge base uses five distinct seasons
  /// (rainy, dry, harmattan, farming, lean) whose calendar boundaries vary by
  /// region, and picking them is a clinical/data decision rather than an
  /// engineering one. The plumbing through to the engine is complete, so a
  /// season source can be added without touching the engine. Until then the
  /// seasonal path stays inert. Flagged for engineering lead.
  String? _season;

  String? get sex => _sex;
  String? get ageToken => _ageToken;
  List<String> get demographicTokens => List.unmodifiable(_demographicTokens);
  List<String> get symptomTokens => List.unmodifiable(_symptomTokens);
  List<String> get severityTokens => List.unmodifiable(_severityTokens);
  List<String> get durationTokens => List.unmodifiable(_durationTokens);
  String? get selectedBodyArea => _selectedBodyArea;
  String? get season => _season;

  bool get shouldShowPregnancyScreen => _sex == 'female';

  static const Map<String, String> _ageTokenMap = {
    '0–12': 'children_under_5',
    '13–17': 'children_school_age',
    '18–40': 'adults',
    '41–60': 'over_40',
    '60+': 'elderly',
  };

  static const Map<String, String> _medicalConditionTokenMap = {
    'Diabetes': 'diabetes_known',
    'Smoking': 'smoker',
    'Hypertension': 'hypertension_known',
    'Allergy history': 'known_allergy',
  };

  void setSex(String sex) {
    _sex = sex;
    if (sex != 'female') {
      _demographicTokens.remove('pregnancy');
    }
    notifyListeners();
  }

  void setAgeRange(String displayLabel) {
    if (_ageToken != null) {
      _demographicTokens.remove(_ageToken);
    }
    _ageToken = _ageTokenMap[displayLabel];
    if (_ageToken != null) {
      _demographicTokens.add(_ageToken!);
    }
    notifyListeners();
  }

  void setMedicalCondition(String condition, bool isYes) {
    final token = _medicalConditionTokenMap[condition];
    if (token == null) return;
    if (isYes) {
      if (!_demographicTokens.contains(token)) {
        _demographicTokens.add(token);
      }
    } else {
      _demographicTokens.remove(token);
    }
    notifyListeners();
  }

  void setPregnancy(bool isPregnant) {
    if (isPregnant) {
      if (!_demographicTokens.contains('pregnancy')) {
        _demographicTokens.add('pregnancy');
      }
    } else {
      _demographicTokens.remove('pregnancy');
    }
    notifyListeners();
  }

  void addSymptomToken(String token) {
    if (!_symptomTokens.contains(token)) {
      _symptomTokens.add(token);
      notifyListeners();
    }
  }

  void removeSymptomToken(String token) {
    if (_symptomTokens.remove(token)) {
      notifyListeners();
    }
  }

  void setSeverityToken(String token) {
    _severityTokens
      ..clear()
      ..add(token);
    notifyListeners();
  }

  void setDurationToken(String token) {
    _durationTokens
      ..clear()
      ..add(token);
    notifyListeners();
  }

  void setBodyArea(String area) {
    _selectedBodyArea = area;
    notifyListeners();
  }

  void setSeason(String? season) {
    _season = season;
    notifyListeners();
  }

  void clearAll() {
    _sex = null;
    _ageToken = null;
    _demographicTokens.clear();
    _symptomTokens.clear();
    _severityTokens.clear();
    _durationTokens.clear();
    _selectedBodyArea = null;
    _season = null;
    notifyListeners();
  }

  AssessmentInput buildInput() {
    return AssessmentInput(
      symptomTokens: List.of(_symptomTokens),
      demographicTokens: List.of(_demographicTokens),
      severityTokens: List.of(_severityTokens),
      durationTokens: List.of(_durationTokens),
      season: _season,
    );
  }
}
