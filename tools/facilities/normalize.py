"""Deterministic normalization: whitespace, Unicode, coordinates and Nigerian phone numbers.

Every function here is total and side-effect free, and every one of them preserves the source
value alongside the normalized one wherever the normalization could lose information. Where a
value cannot be normalized safely the answer is None plus a reason code — never a plausible
substitute.
"""

import re
import unicodedata

#: Mobile's own bounding box, copied from lib/features/locator/nigeria_coverage.dart so the
#: artifact and the consumer agree on what "in Nigeria" means. Deliberately coarse: it includes
#: a little neighbouring territory, which is the safe direction to err for a border facility.
NIGERIA_MIN_LAT, NIGERIA_MAX_LAT = 4.0, 14.0
NIGERIA_MIN_LON, NIGERIA_MAX_LON = 2.5, 15.0

#: Values that occupy a field without saying anything. Treated as absent rather than as text,
#: because "Nil" in an address field is not an address.
NULL_TOKENS = frozenset(
    ["", "nil", "nill", "null", "none", "n/a", "na", "no", "-", "--", "0", "0.0", "nan", "."]
)


def text(raw):
    """Normalize a free-text field, or return None when it says nothing.

    NFC so that visually identical strings compare equal; C0/C1 controls stripped; internal
    whitespace collapsed. Returns None for the placeholder tokens above so that 'Nil' does not
    travel onward as if it were an address.
    """
    if raw is None:
        return None
    value = unicodedata.normalize("NFC", raw)
    value = "".join(ch for ch in value if unicodedata.category(ch)[0] != "C" or ch in "\t\n")
    value = re.sub(r"\s+", " ", value).strip()
    if value.lower() in NULL_TOKENS:
        return None
    return value or None


#: Contact details that have been typed into a free-text field. One address in the pinned
#: source is a personal Gmail account; nothing marks it as a facility contact, and an address
#: field is not a documented public-contact channel. Values shaped like these are dropped from
#: free-text fields rather than carried onward.
_EMAIL_SHAPED = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_SHAPED = re.compile(r"(?i)\b(?:https?://|www\.)\S+")


def free_text(raw):
    """Normalize a free-text field, refusing values that are actually contact details.

    Returns `(value_or_None, reason_or_None)`. The distinction from `text` matters: a blank
    address is missing data, whereas an address field containing someone's personal email is a
    disclosure. Both end up null, and only one of them is worth counting separately.
    """
    value = text(raw)
    if value is None:
        return None, None
    if _EMAIL_SHAPED.search(value):
        return None, "contact_detail_in_free_text_field"
    if _URL_SHAPED.search(value):
        return None, "url_in_free_text_field"
    return value, None


def coordinate(lon_raw, lat_raw):
    """Return `(longitude, latitude, reason)`.

    `reason` is None when the pair is usable. Otherwise both values are None and `reason` says
    which gate refused them — including the one worth naming separately: a pair that is
    implausible as given but plausible with the two swapped. Those are NOT silently swapped.
    Swapping would be a guess about which of two fields the source got wrong, and a wrong guess
    moves a facility hundreds of kilometres.
    """
    lon_text, lat_text = (lon_raw or "").strip(), (lat_raw or "").strip()
    if not lon_text and not lat_text:
        return None, None, "coordinates_absent"
    try:
        lon, lat = float(lon_text), float(lat_text)
    except ValueError:
        return None, None, "coordinates_unparseable"
    if lon == 0.0 and lat == 0.0:
        return None, None, "coordinates_null_island"
    in_bounds = (
        NIGERIA_MIN_LAT <= lat <= NIGERIA_MAX_LAT and NIGERIA_MIN_LON <= lon <= NIGERIA_MAX_LON
    )
    if in_bounds:
        return lon, lat, None
    swapped_ok = (
        NIGERIA_MIN_LAT <= lon <= NIGERIA_MAX_LAT and NIGERIA_MIN_LON <= lat <= NIGERIA_MAX_LON
    )
    return None, None, "coordinates_swapped_suspected" if swapped_ok else "coordinates_out_of_bounds"


#: Nigerian mobile network codes in national format. Landline area codes are deliberately not
#: accepted: the column is overwhelmingly mobile, and admitting 2-3 digit area codes would let
#: through most of the junk this filter exists to catch.
_NG_MOBILE = re.compile(r"^0[789][01]\d{8}$")


def phone(raw):
    """Return `(e164_or_None, reason_or_None)`, never inventing a number.

    Accepts the national 0XXXXXXXXXX form, the bare 10-digit form the source mostly uses, and
    +234 international form. Everything else is refused with a reason, including numbers that
    are structurally valid but obviously placeholder (a single repeated digit, 8000000000).
    """
    if raw is None:
        return None, "phone_absent"
    value = raw.strip()
    if not value:
        return None, "phone_absent"

    digits = re.sub(r"\D", "", value)
    if not digits:
        return None, "phone_no_digits"

    if digits.startswith("00234"):
        digits = "0" + digits[5:]
    elif digits.startswith("234"):
        digits = "0" + digits[3:]
    elif len(digits) == 10 and digits[0] in "789":
        digits = "0" + digits

    if not _NG_MOBILE.match(digits):
        return None, "phone_not_a_nigerian_mobile"
    if len(set(digits[1:])) <= 2:
        return None, "phone_low_entropy_placeholder"
    if digits in ("08000000000", "07000000000", "09000000000"):
        return None, "phone_placeholder"
    return "+234" + digits[1:], None


def sort_key(record):
    """Total, stable ordering: state, LGA, name, then the source id as the tie-break.

    The source id is unique across all 31,390 rows, so the order is total and cannot depend on
    input order or dict iteration. Locale-independent: plain code-point comparison.
    """
    return (
        record["state"] or "",
        record["city_area"] or "",
        (record["name"] or "").casefold(),
        record["source_record"]["source_id"],
    )
