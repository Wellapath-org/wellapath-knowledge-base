// GENERATED CONTRACT TYPES — Facilities 2.0 (candidate)
//
// Source of truth: wellapath-knowledge-base
//   schema/facilities.v2.schema.json
//   mobile_handoff/facilities_v2/README.md   (field semantics, keying rules)
//
// Copy into the mobile repository (suggested: lib/features/locator/) and adapt
// the file header to local lint rules. Plain data classes, dart:core only.
//
// STATUS: the artifact these types describe is a CANDIDATE. It is not published,
// not approved, and its source is not licensed for redistribution. Do NOT wire
// this into a production build. It is provided so the contract is not guessed.
//
// THE RULES THAT MATTER
//   * `type` and `emergencyCapable` are null on every record of this candidate.
//     Never derive either on-device from name, level or services.
//   * A null service flag means "the source did not say". It is not `false`.
//   * An LGA is identified by (state, cityArea). Never by lgaId alone.
//   * Every parse below fails closed: an unrecognised enum string becomes
//     `null` (or `other` where the schema defines it), never a guess.

/// The closed vocabulary a future Product decision would map INTO. Declared in
/// `_metadata.unresolved_fields.type_vocabulary`; not applied to any record yet.
enum FacilityType { hospital, clinic, healthCentre, pharmacy, laboratory, other }

FacilityType? facilityTypeFromJson(Object? value) {
  switch (value) {
    case 'hospital':
      return FacilityType.hospital;
    case 'clinic':
      return FacilityType.clinic;
    case 'health_centre':
      return FacilityType.healthCentre;
    case 'pharmacy':
      return FacilityType.pharmacy;
    case 'laboratory':
      return FacilityType.laboratory;
    case 'other':
      return FacilityType.other;
    default:
      // null in this candidate; an unknown string from a later artifact is
      // treated as "not stated", never as a type the filter would act on.
      return null;
  }
}

enum OpeningHours { hours24, hours12, hours8, other }

OpeningHours? openingHoursFromJson(Object? value) {
  switch (value) {
    case '24_hours':
      return OpeningHours.hours24;
    case '12_hours':
      return OpeningHours.hours12;
    case '8_hours':
      return OpeningHours.hours8;
    case 'other':
      return OpeningHours.other;
    case null:
      return null;
    default:
      // The schema's tail value. An unknown string is at most "other".
      return OpeningHours.other;
  }
}

enum FacilityLevel { primary, secondary, tertiary }

FacilityLevel? facilityLevelFromJson(Object? value) {
  switch (value) {
    case 'Primary':
      return FacilityLevel.primary;
    case 'Secondary':
      return FacilityLevel.secondary;
    case 'Tertiary':
      return FacilityLevel.tertiary;
    default:
      return null;
  }
}

/// Five flags, each read from exactly one source column. Null is tri-state.
class FacilityServices {
  const FacilityServices({
    required this.onsiteLaboratory,
    required this.onsiteImaging,
    required this.onsitePharmacy,
    required this.mortuary,
    required this.ambulance,
  });

  final bool? onsiteLaboratory;
  final bool? onsiteImaging;
  final bool? onsitePharmacy;
  final bool? mortuary;

  /// NOT emergency capability. Do not treat it as such.
  final bool? ambulance;

  factory FacilityServices.fromJson(Map<String, dynamic> json) => FacilityServices(
        onsiteLaboratory: json['onsite_laboratory'] as bool?,
        onsiteImaging: json['onsite_imaging'] as bool?,
        onsitePharmacy: json['onsite_pharmacy'] as bool?,
        mortuary: json['mortuary'] as bool?,
        ambulance: json['ambulance'] as bool?,
      );
}

/// Identity and provenance only. Every original value is recoverable by joining
/// `sourceId` against the hash-pinned source CSV in the knowledge-base repo.
class FacilitySourceRecord {
  const FacilitySourceRecord({
    required this.sourceId,
    required this.sourceUniqueId,
    required this.stateId,
    required this.lgaId,
    required this.wardId,
    required this.sourceUpdatedAt,
  });

  final String sourceId;
  final String sourceUniqueId;
  final String stateId;

  /// Scoped to the LGA NAME, not the state. Six names carry one id in two
  /// states each. Use (state, cityArea) as the LGA key.
  final String lgaId;
  final String? wardId;

  /// `YYYY-MM-DDTHH:MM:SS` with no zone — the source declares none.
  final String? sourceUpdatedAt;

  factory FacilitySourceRecord.fromJson(Map<String, dynamic> json) => FacilitySourceRecord(
        sourceId: json['source_id'] as String,
        sourceUniqueId: json['source_unique_id'] as String,
        stateId: json['state_id'] as String,
        lgaId: json['lga_id'] as String,
        wardId: json['ward_id'] as String?,
        sourceUpdatedAt: json['source_updated_at'] as String?,
      );
}

class Facility {
  const Facility({
    required this.facilityId,
    required this.name,
    required this.type,
    required this.state,
    required this.cityArea,
    required this.latitude,
    required this.longitude,
    required this.phone,
    required this.openingHours,
    required this.emergencyCapable,
    required this.lga,
    required this.ward,
    required this.address,
    required this.facilityLevel,
    required this.ownership,
    required this.ownershipType,
    required this.operationalStatus,
    required this.registrationStatus,
    required this.licenseStatus,
    required this.beds,
    required this.services,
    required this.sourceRecord,
  });

  // --- the ten fields facilities 1.1 also carries -------------------------
  final String facilityId;
  final String name;

  /// Always null in this candidate. Never infer it on-device.
  final FacilityType? type;
  final String state;
  final String cityArea;

  /// Nullable in the type so a 1.1 artifact (which is also non-null) and any
  /// future artifact parse through the same class; non-null on every 2.0 record.
  final double? latitude;
  final double? longitude;

  /// E.164 or null. No `tel:` action until Product records a public-use basis.
  final String? phone;
  final OpeningHours? openingHours;

  /// Always null in this candidate. `== true` remains the only safe test.
  final bool? emergencyCapable;

  // --- added in 2.0 ----------------------------------------------------------
  final String lga;
  final String? ward;
  final String? address;
  final FacilityLevel? facilityLevel;
  final String? ownership;
  final String? ownershipType;
  final String? operationalStatus;
  final String? registrationStatus;
  final String? licenseStatus;
  final int? beds;
  final FacilityServices? services;
  final FacilitySourceRecord? sourceRecord;

  /// True when this record came from a schema-2.0 artifact. Branch on this,
  /// not on a parsed version string, and never throw on a 1.0 record.
  bool get hasSchema2Fields => services != null;

  factory Facility.fromJson(Map<String, dynamic> json) => Facility(
        facilityId: json['facility_id'] as String,
        name: json['name'] as String,
        type: facilityTypeFromJson(json['type']),
        state: json['state'] as String,
        cityArea: (json['city_area'] as String?) ?? '',
        latitude: (json['latitude'] as num?)?.toDouble(),
        longitude: (json['longitude'] as num?)?.toDouble(),
        phone: json['phone'] as String?,
        openingHours: openingHoursFromJson(json['opening_hours']),
        emergencyCapable: json['emergency_capable'] as bool?,
        lga: (json['lga'] as String?) ?? (json['city_area'] as String?) ?? '',
        ward: json['ward'] as String?,
        address: json['address'] as String?,
        facilityLevel: facilityLevelFromJson(json['facility_level']),
        ownership: json['ownership'] as String?,
        ownershipType: json['ownership_type'] as String?,
        operationalStatus: json['operational_status'] as String?,
        registrationStatus: json['registration_status'] as String?,
        licenseStatus: json['license_status'] as String?,
        beds: json['beds'] as int?,
        services: json['services'] is Map<String, dynamic>
            ? FacilityServices.fromJson(json['services'] as Map<String, dynamic>)
            : null,
        sourceRecord: json['source_record'] is Map<String, dynamic>
            ? FacilitySourceRecord.fromJson(json['source_record'] as Map<String, dynamic>)
            : null,
      );
}

class FacilitiesArtifactMetadata {
  const FacilitiesArtifactMetadata({
    required this.version,
    required this.schemaVersion,
    required this.releaseStatus,
    required this.mayPublish,
    required this.totalFacilities,
    required this.statesCovered,
    required this.statesAbsent,
  });

  final String version;
  final String schemaVersion;
  final String releaseStatus;
  final bool mayPublish;
  final int totalFacilities;
  final List<String> statesCovered;

  /// Empty for 1.1. For the 2.0 candidate: Adamawa, Kebbi, Sokoto.
  final List<String> statesAbsent;

  factory FacilitiesArtifactMetadata.fromJson(Map<String, dynamic> json) =>
      FacilitiesArtifactMetadata(
        version: json['version'] as String,
        schemaVersion: json['schema_version'] as String,
        releaseStatus: (json['release_status'] as String?) ?? 'published',
        mayPublish: (json['may_publish'] as bool?) ?? true,
        totalFacilities: json['total_facilities'] as int,
        statesCovered: List<String>.from(json['states_covered'] as List),
        statesAbsent: List<String>.from((json['states_absent'] as List?) ?? const []),
      );

  bool get isSchema2 => schemaVersion == '2.0';
}
