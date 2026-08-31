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

#: ---------------------------------------------------------------------------------------
#: DELIBERATELY EMPTY. Both need a Product decision, and neither is evidenced by the source.
#: ---------------------------------------------------------------------------------------

#: Mobile filters non-emergency results by `type` against {hospital, clinic, health_centre,
#: pharmacy}. The source has no such column. What it has is facility_level (Primary /
#: Secondary / Tertiary), which is a tier of care, not a facility kind: a Primary facility may
#: be a health centre, a clinic or a dispensary, and the source does not say which. Mapping
#: tier to kind would be an interpretation with clinical consequences — it decides which
#: facilities a user is shown for self-care versus urgent care — so it is left to Product.
#: `reports/facilities_mobile_compat_v1.json` quantifies the impact both ways.
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
