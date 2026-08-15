// GENERATED CONTRACT TYPES — Symptom Vocabulary 2.0 (candidate)
//
// Source of truth: wellapath-knowledge-base
//   schema/token_dictionary.v2.schema.json
//   schema/token_dictionary_schema_v2.0.json   (field semantics)
//   docs/VOCABULARY_NORMALIZATION_SPEC.md
//   docs/VOCABULARY_AMBIGUITY_SPEC.md
//
// Copy into the mobile repository (suggested: lib/core/vocabulary/) and adapt
// the file header to local lint rules. These are plain data classes with no
// dependencies beyond dart:core, so they can be dropped in as-is.
//
// STATUS: the artifact these types describe is a CANDIDATE. It is not published
// and not clinically approved. Do NOT wire this into a production build until
// the knowledge-base team confirms approval. It is provided now so the contract
// is not guessed.
//
// THE ONE RULE THAT MATTERS
//   Nothing in `VocabularySearch`, `VocabularyDisplay` or `VocabularyAssociations`
//   may influence scoring, red-flag evaluation, urgency or condition ranking.
//   Only `token_id` reaches the engine, and only when
//   `VocabularyMatchResult.scoringEligible` is true.

// ---------------------------------------------------------------------------
// Match model
// ---------------------------------------------------------------------------

/// The five states a query can resolve to. See VOCABULARY_AMBIGUITY_SPEC.md.
enum VocabularyMatchStatus {
  /// Query equalled a stable token ID, byte for byte.
  exactCanonical,

  /// Query equalled an authored alias owned by exactly one token.
  exactAlias,

  /// normalize(query) matched exactly one index entry.
  normalized,

  /// Two or more candidates. MUST NOT auto-resolve. MUST NOT score.
  ambiguous,

  /// Nothing matched. This means "not understood", NOT "symptom absent".
  noMatch,
}

VocabularyMatchStatus vocabularyMatchStatusFromJson(String value) {
  switch (value) {
    case 'exact_canonical':
      return VocabularyMatchStatus.exactCanonical;
    case 'exact_alias':
      return VocabularyMatchStatus.exactAlias;
    case 'normalized':
      return VocabularyMatchStatus.normalized;
    case 'ambiguous':
      return VocabularyMatchStatus.ambiguous;
    case 'no_match':
      return VocabularyMatchStatus.noMatch;
    default:
      // Unknown status from a newer artifact: fail closed, never fail open.
      // Treating an unrecognised state as "no match" is safe; treating it as a
      // resolved token would score something nobody validated.
      return VocabularyMatchStatus.noMatch;
  }
}

/// How a candidate was reached. Presentation ordering only.
enum VocabularyMatchedVia { canonicalTokenId, canonicalLabel, alias }

class VocabularyCandidate {
  const VocabularyCandidate({
    required this.tokenId,
    required this.category,
    required this.matchedVia,
    required this.safeDisplayLabel,
    required this.displaySafe,
    required this.status,
    required this.replacedBy,
  });

  /// Stable clinical identifier. The ONLY field the engine may consume.
  final String tokenId;

  /// One of the six legacy category names.
  final String category;

  final VocabularyMatchedVia matchedVia;

  /// Null unless the label has been clinically approved.
  ///
  /// When null, use the app's own approved display map. NEVER fall back to
  /// rendering [tokenId] — "csm" and "vhf_suspected" are not words a caregiver
  /// can act on.
  ///
  /// In the W2 Step 1 candidate this is null for all 295 tokens: no clinically
  /// approved label catalogue exists yet.
  final String? safeDisplayLabel;

  final bool displaySafe;

  /// 'active' or 'deprecated'.
  final String status;

  /// Successor token for a deprecated token.
  ///
  /// Do NOT auto-substitute this at runtime. It is a migration pointer for
  /// authors and for the picker, not a rewrite rule; silent substitution would
  /// change clinical meaning without review.
  final String? replacedBy;

  factory VocabularyCandidate.fromJson(Map<String, dynamic> json) {
    return VocabularyCandidate(
      tokenId: json['token_id'] as String,
      category: json['category'] as String,
      matchedVia: switch (json['matched_via']) {
        'canonical_token_id' => VocabularyMatchedVia.canonicalTokenId,
        'canonical_label' => VocabularyMatchedVia.canonicalLabel,
        _ => VocabularyMatchedVia.alias,
      },
      safeDisplayLabel: json['safe_display_label'] as String?,
      displaySafe: json['display_safe'] as bool? ?? false,
      status: json['status'] as String? ?? 'active',
      replacedBy: json['replaced_by'] as String?,
    );
  }
}

class VocabularyMatchResult {
  const VocabularyMatchResult({
    required this.query,
    required this.queryNormalized,
    required this.status,
    required this.resolvedTokenId,
    required this.scoringEligible,
    required this.candidates,
  });

  final String query;
  final String queryNormalized;
  final VocabularyMatchStatus status;

  /// Non-null only when exactly one candidate survived.
  final String? resolvedTokenId;

  /// True if and only if [resolvedTokenId] is non-null.
  ///
  /// This is the gate. Only feed the engine a token when this is true.
  final bool scoringEligible;

  /// Every plausible interpretation, in deterministic order.
  ///
  /// On [VocabularyMatchStatus.ambiguous], present these and let the user
  /// choose. Do not take `candidates.first` as a shortcut.
  final List<VocabularyCandidate> candidates;

  bool get isAmbiguous => status == VocabularyMatchStatus.ambiguous;

  factory VocabularyMatchResult.fromJson(Map<String, dynamic> json) {
    final String? resolved = json['resolved_token_id'] as String?;
    return VocabularyMatchResult(
      query: json['query'] as String,
      queryNormalized: json['query_normalized'] as String,
      status: vocabularyMatchStatusFromJson(json['status'] as String),
      resolvedTokenId: resolved,
      // Derived, never trusted from the wire: the invariant is what makes the
      // contract safe, so it is recomputed rather than read.
      scoringEligible: resolved != null,
      candidates: ((json['candidates'] as List<dynamic>?) ?? <dynamic>[])
          .whereType<Map<String, dynamic>>()
          .map(VocabularyCandidate.fromJson)
          .toList(growable: false),
    );
  }
}

// ---------------------------------------------------------------------------
// Artifact model
// ---------------------------------------------------------------------------

/// CLINICAL. The only block rules and scoring may depend on.
class VocabularyClinicalIdentity {
  const VocabularyClinicalIdentity({
    required this.canonicalTokenId,
    required this.status,
    required this.replacedBy,
    required this.scoringEligible,
    required this.introducedInArtifactVersion,
  });

  final String canonicalTokenId;
  final String status;
  final String? replacedBy;
  final bool scoringEligible;
  final String introducedInArtifactVersion;

  bool get isActive => status == 'active';

  factory VocabularyClinicalIdentity.fromJson(Map<String, dynamic> json) {
    return VocabularyClinicalIdentity(
      canonicalTokenId: json['canonical_token_id'] as String,
      status: json['status'] as String,
      replacedBy: json['replaced_by'] as String?,
      scoringEligible: json['scoring_eligible'] as bool? ?? false,
      introducedInArtifactVersion:
          json['introduced_in_artifact_version'] as String? ?? '1.0',
    );
  }
}

/// DISPLAY-ONLY. Never read by rules or scoring.
class VocabularyDisplay {
  const VocabularyDisplay({
    required this.canonicalLabel,
    required this.labelSource,
    required this.labelReviewStatus,
    required this.displaySafe,
    required this.locale,
  });

  final String canonicalLabel;

  /// 'derived_from_token_id' or 'clinically_approved'.
  final String labelSource;

  /// 'unreviewed' or 'approved'.
  final String labelReviewStatus;

  /// The single gate to check before putting [canonicalLabel] on screen.
  /// False for every token in the W2 Step 1 candidate.
  final bool displaySafe;

  /// BCP 47. Only 'en-NG' is defined at schema 2.0.
  final String locale;

  factory VocabularyDisplay.fromJson(Map<String, dynamic> json) {
    return VocabularyDisplay(
      canonicalLabel: json['canonical_label'] as String,
      labelSource: json['label_source'] as String,
      labelReviewStatus: json['label_review_status'] as String,
      displaySafe: json['display_safe'] as bool? ?? false,
      locale: json['locale'] as String? ?? 'en-NG',
    );
  }
}

/// SEARCH-ONLY. Never read by rules or scoring.
class VocabularySearch {
  const VocabularySearch({
    required this.normalizedForm,
    required this.aliases,
    required this.searchOnly,
  });

  final String normalizedForm;

  /// Authored search phrases. An alias is a way to FIND a token; it is never
  /// itself a token and can never be scored. Empty in the W2 Step 1 candidate.
  final List<String> aliases;

  /// Always true at schema 2.0.
  final bool searchOnly;

  factory VocabularySearch.fromJson(Map<String, dynamic> json) {
    return VocabularySearch(
      normalizedForm: json['normalized_form'] as String,
      aliases: ((json['aliases'] as List<dynamic>?) ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false),
      searchOnly: json['search_only'] as bool? ?? true,
    );
  }
}

/// SEARCH/INPUT metadata. Filtering, grouping and picker routing only.
/// No field here may affect scoring, red flags or urgency at schema 2.0.
class VocabularyAssociations {
  const VocabularyAssociations({
    required this.bodyAreas,
    required this.complaintGroups,
    required this.severityDescriptors,
    required this.durationDescriptors,
  });

  final List<String> bodyAreas;
  final List<String> complaintGroups;

  /// Descriptors this token may be qualified by. Descriptive only — attaching
  /// one does not change any weight, rule or urgency tier.
  final List<String> severityDescriptors;
  final List<String> durationDescriptors;

  static List<String> _strings(dynamic value) =>
      ((value as List<dynamic>?) ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false);

  factory VocabularyAssociations.fromJson(Map<String, dynamic> json) {
    return VocabularyAssociations(
      bodyAreas: _strings(json['body_areas']),
      complaintGroups: _strings(json['complaint_groups']),
      severityDescriptors: _strings(json['severity_descriptors']),
      durationDescriptors: _strings(json['duration_descriptors']),
    );
  }
}

class VocabularyToken {
  const VocabularyToken({
    required this.tokenId,
    required this.category,
    required this.clinicalIdentity,
    required this.display,
    required this.search,
    required this.associations,
  });

  final String tokenId;
  final String category;
  final VocabularyClinicalIdentity clinicalIdentity;
  final VocabularyDisplay display;
  final VocabularySearch search;
  final VocabularyAssociations associations;

  factory VocabularyToken.fromJson(Map<String, dynamic> json) {
    return VocabularyToken(
      tokenId: json['token_id'] as String,
      category: json['category'] as String,
      clinicalIdentity: VocabularyClinicalIdentity.fromJson(
        json['clinical_identity'] as Map<String, dynamic>,
      ),
      display: VocabularyDisplay.fromJson(json['display'] as Map<String, dynamic>),
      search: VocabularySearch.fromJson(json['search'] as Map<String, dynamic>),
      associations: VocabularyAssociations.fromJson(
        json['associations'] as Map<String, dynamic>,
      ),
    );
  }
}

class VocabularyArtifact {
  const VocabularyArtifact({
    required this.version,
    required this.schemaVersion,
    required this.releaseStatus,
    required this.tokens,
    required this.normalizedForms,
    required this.legacySymptomTokens,
    required this.legacyRedFlagTokens,
  });

  final String version;
  final String schemaVersion;

  /// 'candidate_unapproved', 'approved_unpublished' or 'published'.
  /// A build must refuse anything that is not 'published'.
  final String releaseStatus;

  final List<VocabularyToken> tokens;

  /// Shipped inverted index: normalized form -> candidate token IDs.
  /// More than one ID means the form is ambiguous and must not auto-resolve.
  final Map<String, List<String>> normalizedForms;

  /// Schema 1.0 compatibility surface. These are the two keys the current
  /// engine reads, and they are byte identical to token_dictionary 1.1.
  final List<String> legacySymptomTokens;
  final List<String> legacyRedFlagTokens;

  /// True when the artifact is schema 2.0 or later.
  bool get hasVocabularyMetadata => tokens.isNotEmpty;

  static List<String> _strings(dynamic value) =>
      ((value as List<dynamic>?) ?? <dynamic>[])
          .whereType<String>()
          .toList(growable: false);

  /// Parses either a schema 1.0 or a schema 2.0 artifact.
  ///
  /// Detection is STRUCTURAL — the presence of the `tokens` key — not a parsed
  /// version string. A structural check cannot be defeated by a version string
  /// that is missing, malformed, or newer than this build understands. When
  /// `tokens` is absent the artifact is schema 1.0 (a rollback, or a stale
  /// cached config); [tokens] is empty, [hasVocabularyMetadata] is false, and
  /// the legacy arrays still populate. Never throw here: offline triage must
  /// keep working.
  factory VocabularyArtifact.fromJson(Map<String, dynamic> json) {
    final Map<String, dynamic> metadata =
        (json['_metadata'] as Map<String, dynamic>?) ?? <String, dynamic>{};
    final dynamic rawTokens = json['tokens'];
    final dynamic rawIndex =
        (json['search_index'] as Map<String, dynamic>?)?['normalized_forms'];

    return VocabularyArtifact(
      version: metadata['version'] as String? ?? '1.1',
      schemaVersion: metadata['schema_version'] as String? ?? '1.0',
      releaseStatus: metadata['release_status'] as String? ?? 'published',
      tokens: rawTokens is List
          ? rawTokens
              .whereType<Map<String, dynamic>>()
              .map(VocabularyToken.fromJson)
              .toList(growable: false)
          : const <VocabularyToken>[],
      normalizedForms: rawIndex is Map<String, dynamic>
          ? rawIndex.map(
              (String key, dynamic value) =>
                  MapEntry<String, List<String>>(key, _strings(value)),
            )
          : const <String, List<String>>{},
      legacySymptomTokens: _strings(json['symptom_tokens']),
      legacyRedFlagTokens: _strings(json['red_flag_tokens']),
    );
  }

  /// The valid-input token set the red-flag evaluator already builds.
  /// Identical for schema 1.0 and schema 2.0 artifacts.
  Set<String> get validInputTokens =>
      <String>{...legacySymptomTokens, ...legacyRedFlagTokens};
}
