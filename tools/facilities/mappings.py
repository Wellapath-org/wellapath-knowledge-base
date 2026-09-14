"""Explicit, reviewable mappings from source values to candidate values.

Every table is closed over the values observed in the pinned source. A value outside a table
is never defaulted: `map_value` returns `UNMAPPED`, the caller records it, and the row is
quarantined if the field is one the artifact cannot be honest without.

The two most important entries in this file are the two that are deliberately EMPTY.
"""

#: State names. The source spells Akwa Ibom with a hyphen; facilities 1.1, the Mobile
#: consumer's own tests and the standard state list do not. Everything else already matches.
#: FCT stays 'FCT' because that is what facilities 1.1 emits and what Mobile compares against.
STATE_NAMES = {
    "Abia": "Abia", "Anambra": "Anambra", "Akwa-Ibom": "Akwa Ibom", "Bauchi": "Bauchi",
    "Bayelsa": "Bayelsa", "Benue": "Benue", "Borno": "Borno", "Cross River": "Cross River",
    "Delta": "Delta", "Ebonyi": "Ebonyi", "Edo": "Edo", "Ekiti": "Ekiti", "Enugu": "Enugu",
    "FCT": "FCT", "Gombe": "Gombe", "Imo": "Imo", "Jigawa": "Jigawa", "Kaduna": "Kaduna",
    "Kano": "Kano", "Katsina": "Katsina", "Kogi": "Kogi", "Kwara": "Kwara", "Lagos": "Lagos",
    "Nasarawa": "Nasarawa", "Niger": "Niger", "Ogun": "Ogun", "Ondo": "Ondo", "Osun": "Osun",
    "Oyo": "Oyo", "Plateau": "Plateau", "Rivers": "Rivers", "Taraba": "Taraba", "Yobe": "Yobe",
    "Zamfara": "Zamfara",
}

#: The 36 states and the FCT, for coverage reporting. Not a mapping — a yardstick.
NIGERIA_STATES = (
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "Gombe", "Imo", "Jigawa",
    "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger",
    "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe", "Zamfara",
)
FCT_NAME = "FCT"

#: Approximate reference point (latitude, longitude) for each state and the FCT, accurate to
#: about half a degree. Reference geography, NOT facility data: it is a yardstick for deciding
#: whether a source coordinate pair is plausible FOR THE STATE THE ROW CLAIMS, and for nothing
#: else. No record is ever placed, moved, swapped or corrected by it; a pair that fails is
#: refused with a reason, exactly as the bounding box refuses one.
#:
#: Why it exists: the bounding box is blind to a transposed pair whenever both values happen
#: to fall inside Nigeria, which is true for most of the north (Kano is 12.0N 8.5E; written
#: the other way round it is 8.5N 12.0E, still inside the box, 500 km away in Taraba). The
#: pinned source has entire states written that way. Only a per-state yardstick can see it.
#:
#: Cross-checked, not trusted: facilities 1.1 (GRID3/OSM lineage, independent of this source)
#: has its Lagos, FCT and Kano medians 7, 5 and 20 km from these points, and every candidate
#: state the instrument leaves alone has a median within 83 km of its point. The quality
#: report tabulates both readings for every state so the calibration is auditable.
STATE_REFERENCE_POINTS = {
    "Abia": (5.5, 7.5), "Adamawa": (9.3, 12.4), "Akwa Ibom": (5.0, 7.8), "Anambra": (6.2, 7.0),
    "Bauchi": (10.5, 9.8), "Bayelsa": (4.8, 6.1), "Benue": (7.3, 8.8), "Borno": (11.8, 13.2),
    "Cross River": (5.9, 8.6), "Delta": (5.7, 6.0), "Ebonyi": (6.3, 8.1), "Edo": (6.6, 5.9),
    "Ekiti": (7.7, 5.3), "Enugu": (6.5, 7.5), "FCT": (9.0, 7.3), "Gombe": (10.3, 11.2),
    "Imo": (5.5, 7.0), "Jigawa": (12.2, 9.5), "Kaduna": (10.4, 7.7), "Kano": (11.8, 8.5),
    "Katsina": (12.5, 7.6), "Kebbi": (11.5, 4.2), "Kogi": (7.7, 6.7), "Kwara": (8.9, 4.7),
    "Lagos": (6.5, 3.4), "Nasarawa": (8.5, 8.3), "Niger": (9.9, 5.9), "Ogun": (7.0, 3.4),
    "Ondo": (7.0, 5.2), "Osun": (7.6, 4.5), "Oyo": (8.1, 3.9), "Plateau": (9.2, 9.4),
    "Rivers": (4.9, 6.9), "Sokoto": (13.1, 5.2), "Taraba": (8.0, 10.8), "Yobe": (12.3, 11.7),
    "Zamfara": (12.2, 6.2),
}

#: A pair is refused as transposed when it lies farther than this from its state's point AND
#: the transposed pair is at least SWAP_FACTOR times closer. Calibrated on the pinned source so
#: that a genuine facility at the edge of a large state is kept and a state written the wrong
#: way round is refused. Where a state's latitude and longitude are numerically close (Bauchi,
#: Gombe, Yobe, Borno, Kogi) the two readings are only ~100-250 km apart and the instrument is
#: genuinely uncertain; the quality report says so per state.
SWAP_MIN_DISTANCE_KM = 150.0
SWAP_FACTOR = 2.0

#: A pair farther than this from its state's point under either reading is refused as not in
#: the state the row claims. No Nigerian state extends 300 km from its reference point.
NOT_IN_STATE_KM = 300.0

FACILITY_LEVELS = {"Primary": "Primary", "Secondary": "Secondary", "Tertiary": "Tertiary"}

OWNERSHIP = {"Public": "Public", "Private": "Private"}

OWNERSHIP_TYPE = {
    "Local Government": "local_government",
    "State Government": "state_government",
    "Federal Government": "federal_government",
    "For Profit": "private_for_profit",
    "Not For Profit": "private_not_for_profit",
    "Military & Paramilitary formations": "military_paramilitary",
}

#: 'Unknown' is carried through as the explicit string "unknown", which is NOT the same as a
#: blank source value. Blank becomes null (not_provided). The distinction is the point.
OPERATIONAL_STATUS = {
    "Functional": "functional",
    "Non-Functional": "non_functional",
    "Closed": "closed",
    "Under Renovation": "under_renovation",
    "Unknown": "unknown",
}

REGISTRATION_STATUS = {
    "Registered": "registered",
    "Provisionally Registered": "provisionally_registered",
    "Pending Registration": "pending_registration",
    "Registration Suspended": "registration_suspended",
    "Registration Cancelled": "registration_cancelled",
    "Unknown": "unknown",
}

LICENSE_STATUS = {
    "Licensed": "licensed",
    "Not Licensed": "not_licensed",
    "License Cancelled": "license_cancelled",
    "Unknown": "unknown",
}

#: Opening hours. The source column is mostly a clean enum with a long tail of free text and
#: typos ('124_Hours', '24  Hours', 'Registered'). Only the clean values are mapped; the tail
#: becomes null and is reported, because inventing '24 hours' from '124_Hours' is a guess about
#: when a clinic is open, and a wrong one sends someone to a closed building.
OPENING_HOURS = {
    "24_Hours": "24_hours",
    "12_Hours": "12_hours",
    "8_Hours": "8_hours",
    "Other": "other",
}

#: The boolean service flags the candidate carries, each bound to the ONE source column it is
#: read from. This table is the whole of the evidence for `services`: a key that is not here
#: has no source column and therefore cannot be emitted. The validator checks the emitted key
#: set against this table, which is what "no invented service-capability field" means in code.
#: (The source spells the pharmacy column 'onsite_pharmarcy'; the candidate does not.)
SERVICES_SOURCE_COLUMNS = {
    "onsite_laboratory": "onsite_laboratory",
    "onsite_imaging": "onsite_imaging",
    "onsite_pharmacy": "onsite_pharmarcy",
    "mortuary": "mortuary_services",
    "ambulance": "ambulance_services",
}

#: ---------------------------------------------------------------------------------------
#: DELIBERATELY EMPTY. Both need a Product decision, and neither is evidenced by the source.
#: ---------------------------------------------------------------------------------------

#: The closed facility-type vocabulary a future decision would map INTO. The first four are
#: the values the Mobile consumer filters on today (facilities 1.1 emits them); `laboratory`
#: and `other` are reserved so a later mapping has somewhere honest to put a facility that is
#: neither. Documented here so the enum exists to validate against; NOT applied — see the
#: empty table below. Every emitted `type` is null, and the validator checks both facts.
FACILITY_TYPES = ("hospital", "clinic", "health_centre", "pharmacy", "laboratory", "other")

#: Mobile filters non-emergency results by `type` against {hospital, clinic, health_centre,
#: pharmacy}. The source has no such column. What it has is facility_level (Primary /
#: Secondary / Tertiary), which is a tier of care, not a facility kind: a Primary facility may
#: be a health centre, a clinic or a dispensary, and the source does not say which. Mapping
#: tier to kind would be an interpretation with clinical consequences — it decides which
#: facilities a user is shown for self-care versus urgent care — so it is left to Product.
#: `reports/facilities_mobile_compat_v1.json` quantifies the impact both ways.
#:
#: The source also carries `facility_type_id` (1, 2, 3) with no name column. Cross-tabulated
#: against facility_level in the quality report it is a near-copy of the level (1≈Primary,
#: 2≈Secondary, 3≈Tertiary, 157 rows disagree), which is evidence that it is not a facility
#: kind either. It is reported, not interpreted.
FACILITY_TYPE_FROM_LEVEL = {}

#: facilities 1.1 set emergency_capable = (type == 'hospital'), a derivation this source cannot
#: support because it has no type. Nothing in the 90 columns records emergency capability:
#: ambulance_services and inpatient are adjacent but not the same claim, and treating either as
#: emergency capability would put a facility at the top of an emergency list on a guess.
EMERGENCY_CAPABLE_RULE = None

UNMAPPED = object()


def map_value(table, raw):
    """Map a source value, or return `UNMAPPED`. Blank returns None (not_provided)."""
    if raw is None:
        return None
    value = raw.strip()
    if value == "":
        return None
    return table.get(value, UNMAPPED)
