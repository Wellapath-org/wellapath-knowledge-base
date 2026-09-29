import '../../features/assessment/models/followup_question.dart';

const Map<String, List<FollowupQuestion>> kFollowupQuestionMap = {
  'headache': [
    FollowupQuestion(
      type: QuestionType.severity,
      questionText: 'How severe is your headache?',
    ),
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had this headache?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['fever', 'nausea', 'vomiting', 'weakness', 'dizziness'],
    ),
  ],
  'fever': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had this fever?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['chills', 'sweating', 'body_pain', 'weakness', 'nausea'],
    ),
  ],
  'cough': [
    FollowupQuestion(
      type: QuestionType.severity,
      questionText: 'How severe is your cough?',
    ),
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had this cough?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['fever', 'fast_breathing_child', 'weakness'],
    ),
  ],
  'watery_stool': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had watery stool?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['vomiting', 'nausea', 'abdominal_cramps'],
    ),
  ],
  'chills': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had chills?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['fever', 'sweating', 'weakness'],
    ),
  ],
  'body_pain': [
    FollowupQuestion(
      type: QuestionType.severity,
      questionText: 'How severe is your body pain?',
    ),
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had this body pain?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['fever', 'weakness', 'fatigue'],
    ),
  ],
  'weakness': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you felt this weakness?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['fever', 'fatigue', 'dizziness'],
    ),
  ],
  'nausea': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had nausea?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['vomiting', 'abdominal_cramps', 'fever'],
    ),
  ],
  'sweating': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had excessive sweating?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['fever', 'chills', 'weakness'],
    ),
  ],
  'vomiting': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you been vomiting?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['nausea', 'abdominal_cramps', 'fever'],
    ),
  ],
  'abdominal_cramps': [
    FollowupQuestion(
      type: QuestionType.severity,
      questionText: 'How severe are your abdominal cramps?',
    ),
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had these abdominal cramps?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['vomiting', 'nausea', 'watery_stool'],
    ),
  ],
  'dizziness': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you felt dizzy?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['weakness', 'fatigue', 'headache'],
    ),
  ],
  'fatigue': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you felt this fatigue?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['weakness', 'fever', 'body_pain'],
    ),
  ],
  'fast_breathing_child': [
    FollowupQuestion(
      type: QuestionType.severity,
      questionText: 'How severe is the fast breathing?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['fever', 'cough', 'weakness'],
    ),
  ],
  'chest_indrawing_severe': [
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['fever', 'cough', 'fast_breathing_child'],
    ),
  ],
  'dark_urine': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you noticed dark urine?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['weakness', 'fever', 'nausea'],
    ),
  ],
  'pain': [
    FollowupQuestion(
      type: QuestionType.severity,
      questionText: 'How severe is this pain?',
    ),
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had this pain?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['weakness', 'fever'],
    ),
  ],
  'swelling': [
    FollowupQuestion(
      type: QuestionType.duration,
      questionText: 'How long have you had this swelling?',
    ),
    FollowupQuestion(
      type: QuestionType.additionalSymptoms,
      questionText: 'Do you have any of these symptoms too?',
      options: ['pain', 'weakness'],
    ),
  ],
};

/// Fallback for any symptom token with no entry in [kFollowupQuestionMap].
const FollowupQuestion kDefaultFollowupQuestion = FollowupQuestion(
  type: QuestionType.duration,
  questionText: 'How long have you had this symptom?',
);
