"""
Address normalization utilities for septic permit deduplication.

Provides consistent address formatting for accurate duplicate detection
across 7M+ permit records from various state/county sources.
"""

import re
import hashlib
from typing import Optional, Tuple


# USPS standard street suffix abbreviations
STREET_SUFFIXES = {
    "ALLEY": "ALY",
    "ALLEE": "ALY",
    "ALLY": "ALY",
    "ANNEX": "ANX",
    "ANEX": "ANX",
    "ANNX": "ANX",
    "ARCADE": "ARC",
    "AVENUE": "AVE",
    "AVENU": "AVE",
    "AVEN": "AVE",
    "AVNUE": "AVE",
    "AV": "AVE",
    "BAYOU": "BYU",
    "BAYOO": "BYU",
    "BEACH": "BCH",
    "BEND": "BND",
    "BLUFF": "BLF",
    "BLUF": "BLF",
    "BLUFFS": "BLFS",
    "BOTTOM": "BTM",
    "BOTTM": "BTM",
    "BOT": "BTM",
    "BOULEVARD": "BLVD",
    "BOUL": "BLVD",
    "BOULV": "BLVD",
    "BRANCH": "BR",
    "BRNCH": "BR",
    "BRIDGE": "BRG",
    "BRDGE": "BRG",
    "BROOK": "BRK",
    "BRROK": "BRK",
    "BROOKS": "BRKS",
    "BURG": "BG",
    "BURGS": "BGS",
    "BYPASS": "BYP",
    "BYPA": "BYP",
    "BYPAS": "BYP",
    "BYPS": "BYP",
    "CAMP": "CP",
    "CMP": "CP",
    "CANYON": "CYN",
    "CANYN": "CYN",
    "CNYN": "CYN",
    "CAPE": "CPE",
    "CAUSEWAY": "CSWY",
    "CAUSWA": "CSWY",
    "CENTER": "CTR",
    "CENT": "CTR",
    "CENTR": "CTR",
    "CENTRE": "CTR",
    "CNTER": "CTR",
    "CNTR": "CTR",
    "CENTERS": "CTRS",
    "CIRCLE": "CIR",
    "CIRC": "CIR",
    "CIRCL": "CIR",
    "CRCL": "CIR",
    "CRCLE": "CIR",
    "CIRCLES": "CIRS",
    "CLIFF": "CLF",
    "CLIFFS": "CLFS",
    "CLUB": "CLB",
    "COMMON": "CMN",
    "COMMONS": "CMNS",
    "CORNER": "COR",
    "CORNERS": "CORS",
    "COURSE": "CRSE",
    "COURT": "CT",
    "CRT": "CT",
    "COURTS": "CTS",
    "COVE": "CV",
    "COVES": "CVS",
    "CREEK": "CRK",
    "CK": "CRK",
    "CR": "CRK",
    "CRESCENT": "CRES",
    "CRSENT": "CRES",
    "CRSNT": "CRES",
    "CREST": "CRST",
    "CROSSING": "XING",
    "CRSSNG": "XING",
    "CROSSROAD": "XRD",
    "CROSSROADS": "XRDS",
    "CURVE": "CURV",
    "DALE": "DL",
    "DAM": "DM",
    "DIVIDE": "DV",
    "DIV": "DV",
    "DVD": "DV",
    "DRIVE": "DR",
    "DRIV": "DR",
    "DRV": "DR",
    "DRIVES": "DRS",
    "ESTATE": "EST",
    "ESTATES": "ESTS",
    "EXPRESSWAY": "EXPY",
    "EXP": "EXPY",
    "EXPR": "EXPY",
    "EXPRESS": "EXPY",
    "EXPW": "EXPY",
    "EXTENSION": "EXT",
    "EXTN": "EXT",
    "EXTNSN": "EXT",
    "EXTENSIONS": "EXTS",
    "FALL": "FALL",
    "FALLS": "FLS",
    "FERRY": "FRY",
    "FRRY": "FRY",
    "FIELD": "FLD",
    "FIELDS": "FLDS",
    "FLAT": "FLT",
    "FLATS": "FLTS",
    "FORD": "FRD",
    "FORDS": "FRDS",
    "FOREST": "FRST",
    "FORESTS": "FRST",
    "FORGE": "FRG",
    "FORG": "FRG",
    "FORGES": "FRGS",
    "FORK": "FRK",
    "FORKS": "FRKS",
    "FORT": "FT",
    "FRT": "FT",
    "FREEWAY": "FWY",
    "FREEWY": "FWY",
    "FRWAY": "FWY",
    "FRWY": "FWY",
    "GARDEN": "GDN",
    "GARDN": "GDN",
    "GRDEN": "GDN",
    "GRDN": "GDN",
    "GARDENS": "GDNS",
    "GRDNS": "GDNS",
    "GATEWAY": "GTWY",
    "GATEWY": "GTWY",
    "GATWAY": "GTWY",
    "GTWAY": "GTWY",
    "GLEN": "GLN",
    "GLENS": "GLNS",
    "GREEN": "GRN",
    "GREENS": "GRNS",
    "GROVE": "GRV",
    "GROV": "GRV",
    "GROVES": "GRVS",
    "HARBOR": "HBR",
    "HARB": "HBR",
    "HARBR": "HBR",
    "HRBOR": "HBR",
    "HARBORS": "HBRS",
    "HAVEN": "HVN",
    "HAVN": "HVN",
    "HEIGHTS": "HTS",
    "HEIGHT": "HTS",
    "HGTS": "HTS",
    "HT": "HTS",
    "HIGHWAY": "HWY",
    "HIGHWY": "HWY",
    "HIWAY": "HWY",
    "HIWY": "HWY",
    "HWAY": "HWY",
    "HILL": "HL",
    "HILLS": "HLS",
    "HOLLOW": "HOLW",
    "HLLW": "HOLW",
    "HOLLOWS": "HOLW",
    "HOLWS": "HOLW",
    "INLET": "INLT",
    "ISLAND": "IS",
    "ISLND": "IS",
    "ISLANDS": "ISS",
    "ISLNDS": "ISS",
    "ISLE": "ISLE",
    "ISLES": "ISLE",
    "JUNCTION": "JCT",
    "JCTION": "JCT",
    "JCTN": "JCT",
    "JUNCTN": "JCT",
    "JUNCTON": "JCT",
    "JUNCTIONS": "JCTS",
    "JCTNS": "JCTS",
    "KEY": "KY",
    "KEYS": "KYS",
    "KNOLL": "KNL",
    "KNOL": "KNL",
    "KNOLLS": "KNLS",
    "LAKE": "LK",
    "LAKES": "LKS",
    "LAND": "LAND",
    "LANDING": "LNDG",
    "LNDNG": "LNDG",
    "LANE": "LN",
    "LANES": "LN",
    "LIGHT": "LGT",
    "LIGHTS": "LGTS",
    "LOAF": "LF",
    "LOCK": "LCK",
    "LOCKS": "LCKS",
    "LODGE": "LDG",
    "LDGE": "LDG",
    "LODG": "LDG",
    "LOOP": "LOOP",
    "LOOPS": "LOOP",
    "MALL": "MALL",
    "MANOR": "MNR",
    "MANORS": "MNRS",
    "MEADOW": "MDW",
    "MEADOWS": "MDWS",
    "MEDOWS": "MDWS",
    "MEWS": "MEWS",
    "MILL": "ML",
    "MILLS": "MLS",
    "MISSION": "MSN",
    "MISSN": "MSN",
    "MSSN": "MSN",
    "MOTORWAY": "MTWY",
    "MOUNT": "MT",
    "MNT": "MT",
    "MOUNTAIN": "MTN",
    "MNTAIN": "MTN",
    "MNTN": "MTN",
    "MOUNTIN": "MTN",
    "MTIN": "MTN",
    "MOUNTAINS": "MTNS",
    "MNTNS": "MTNS",
    "NECK": "NCK",
    "ORCHARD": "ORCH",
    "ORCHRD": "ORCH",
    "OVAL": "OVAL",
    "OVL": "OVAL",
    "OVERPASS": "OPAS",
    "PARK": "PARK",
    "PRK": "PARK",
    "PARKS": "PARK",
    "PARKWAY": "PKWY",
    "PARKWY": "PKWY",
    "PKWAY": "PKWY",
    "PKY": "PKWY",
    "PARKWAYS": "PKWY",
    "PKWYS": "PKWY",
    "PASS": "PASS",
    "PASSAGE": "PSGE",
    "PATH": "PATH",
    "PATHS": "PATH",
    "PIKE": "PIKE",
    "PIKES": "PIKE",
    "PINE": "PNE",
    "PINES": "PNES",
    "PLACE": "PL",
    "PLAIN": "PLN",
    "PLAINS": "PLNS",
    "PLAZA": "PLZ",
    "PLZA": "PLZ",
    "POINT": "PT",
    "POINTS": "PTS",
    "PORT": "PRT",
    "PORTS": "PRTS",
    "PRAIRIE": "PR",
    "PRR": "PR",
    "RADIAL": "RADL",
    "RAD": "RADL",
    "RADIEL": "RADL",
    "RAMP": "RAMP",
    "RANCH": "RNCH",
    "RANCHES": "RNCH",
    "RNCHS": "RNCH",
    "RAPID": "RPD",
    "RAPIDS": "RPDS",
    "REST": "RST",
    "RIDGE": "RDG",
    "RDGE": "RDG",
    "RIDGES": "RDGS",
    "RIVER": "RIV",
    "RVR": "RIV",
    "RIVR": "RIV",
    "ROAD": "RD",
    "ROADS": "RDS",
    "ROUTE": "RTE",
    "ROW": "ROW",
    "RUE": "RUE",
    "RUN": "RUN",
    "SHOAL": "SHL",
    "SHOALS": "SHLS",
    "SHORE": "SHR",
    "SHOAR": "SHR",
    "SHORES": "SHRS",
    "SHOARS": "SHRS",
    "SKYWAY": "SKWY",
    "SPRING": "SPG",
    "SPNG": "SPG",
    "SPRNG": "SPG",
    "SPRINGS": "SPGS",
    "SPNGS": "SPGS",
    "SPRNGS": "SPGS",
    "SPUR": "SPUR",
    "SPURS": "SPUR",
    "SQUARE": "SQ",
    "SQR": "SQ",
    "SQRE": "SQ",
    "SQU": "SQ",
    "SQUARES": "SQS",
    "SQRS": "SQS",
    "STATION": "STA",
    "STATN": "STA",
    "STN": "STA",
    "STRAVENUE": "STRA",
    "STRAV": "STRA",
    "STRAVEN": "STRA",
    "STRAVN": "STRA",
    "STRVN": "STRA",
    "STRVNUE": "STRA",
    "STREAM": "STRM",
    "STREME": "STRM",
    "STREET": "ST",
    "STRT": "ST",
    "STR": "ST",
    "STREETS": "STS",
    "SUMMIT": "SMT",
    "SUMIT": "SMT",
    "SUMITT": "SMT",
    "TERRACE": "TER",
    "TERR": "TER",
    "THROUGHWAY": "TRWY",
    "TRACE": "TRCE",
    "TRACES": "TRCE",
    "TRACK": "TRAK",
    "TRACKS": "TRAK",
    "TRK": "TRAK",
    "TRKS": "TRAK",
    "TRAFFICWAY": "TRFY",
    "TRAIL": "TRL",
    "TRAILS": "TRL",
    "TRLS": "TRL",
    "TRAILER": "TRLR",
    "TRLRS": "TRLR",
    "TUNNEL": "TUNL",
    "TUNEL": "TUNL",
    "TUNLS": "TUNL",
    "TUNNELS": "TUNL",
    "TUNNL": "TUNL",
    "TURNPIKE": "TPKE",
    "TRNPK": "TPKE",
    "TURNPK": "TPKE",
    "UNDERPASS": "UPAS",
    "UNION": "UN",
    "UNIONS": "UNS",
    "VALLEY": "VLY",
    "VALLY": "VLY",
    "VLLY": "VLY",
    "VALLEYS": "VLYS",
    "VIADUCT": "VIA",
    "VDCT": "VIA",
    "VIADCT": "VIA",
    "VIEW": "VW",
    "VIEWS": "VWS",
    "VILLAGE": "VLG",
    "VILL": "VLG",
    "VILLAG": "VLG",
    "VILLG": "VLG",
    "VILLIAGE": "VLG",
    "VILLAGES": "VLGS",
    "VILLE": "VL",
    "VISTA": "VIS",
    "VIST": "VIS",
    "VST": "VIS",
    "VSTA": "VIS",
    "WALK": "WALK",
    "WALKS": "WALK",
    "WALL": "WALL",
    "WAY": "WAY",
    "WAYS": "WAYS",
    "WELL": "WL",
    "WELLS": "WLS",
}

# Directional abbreviations
DIRECTIONALS = {
    "NORTH": "N",
    "SOUTH": "S",
    "EAST": "E",
    "WEST": "W",
    "NORTHEAST": "NE",
    "NORTHWEST": "NW",
    "SOUTHEAST": "SE",
    "SOUTHWEST": "SW",
}

# Secondary unit designators
UNIT_DESIGNATORS = {
    "APARTMENT": "APT",
    "BASEMENT": "BSMT",
    "BUILDING": "BLDG",
    "DEPARTMENT": "DEPT",
    "FLOOR": "FL",
    "FRONT": "FRNT",
    "HANGAR": "HNGR",
    "LOBBY": "LBBY",
    "LOT": "LOT",
    "LOWER": "LOWR",
    "OFFICE": "OFC",
    "PENTHOUSE": "PH",
    "PIER": "PIER",
    "REAR": "REAR",
    "ROOM": "RM",
    "SIDE": "SIDE",
    "SLIP": "SLIP",
    "SPACE": "SPC",
    "STOP": "STOP",
    "SUITE": "STE",
    "TRAILER": "TRLR",
    "UNIT": "UNIT",
    "UPPER": "UPPR",
}


def normalize_address(address: Optional[str]) -> Optional[str]:
    """
    Normalize a street address to USPS standard format.

    Transformations:
    - Convert to uppercase
    - Remove extra whitespace
    - Remove punctuation (periods, commas, hashes, etc.)
    - Standardize street suffixes (STREET → ST, AVENUE → AVE)
    - Standardize directionals (NORTH → N)
    - Standardize unit designators (APARTMENT → APT)
    - Normalize ordinal numbers (1ST, 2ND, 3RD)

    Args:
        address: Raw address string

    Returns:
        Normalized address string or None if input is empty

    Examples:
        >>> normalize_address("123 North Main Street, Apt. 4B")
        "123 N MAIN ST APT 4B"
        >>> normalize_address("456 S.W. Oak Avenue #201")
        "456 SW OAK AVE 201"
    """
    if not address:
        return None

    # Uppercase
    normalized = address.upper()

    # Remove punctuation except alphanumerics and spaces
    # Keep hyphens for now (for suite numbers like 4-B)
    normalized = re.sub(r"[.,#]", " ", normalized)
    normalized = re.sub(r"['\"]", "", normalized)

    # Normalize periods in directionals (S.W. → SW)
    normalized = re.sub(r"\b([NSEW])\.([NSEW]?)\.?\b", r"\1\2", normalized)

    # Collapse whitespace
    normalized = " ".join(normalized.split())

    # Split into words for token processing
    words = normalized.split()
    result_words = []

    for word in words:
        # Check for directionals (including compound like N.W.)
        if word in DIRECTIONALS:
            result_words.append(DIRECTIONALS[word])
        # Check for street suffixes
        elif word in STREET_SUFFIXES:
            result_words.append(STREET_SUFFIXES[word])
        # Check for unit designators
        elif word in UNIT_DESIGNATORS:
            result_words.append(UNIT_DESIGNATORS[word])
        else:
            result_words.append(word)

    normalized = " ".join(result_words)

    # Normalize ordinal numbers (1ST, 2ND, 3RD, 4TH, etc.)
    normalized = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", normalized)

    # Remove standalone # symbol if present
    normalized = re.sub(r"\s+#\s+", " ", normalized)
    normalized = re.sub(r"\s+#", " ", normalized)

    # Final whitespace cleanup
    normalized = " ".join(normalized.split())

    return normalized if normalized else None


def normalize_county(county: Optional[str]) -> Optional[str]:
    """
    Normalize county name for consistent matching.

    Transformations:
    - Convert to uppercase
    - Remove "COUNTY" suffix
    - Remove extra whitespace
    - Handle common variations (ST. → SAINT, etc.)

    Args:
        county: Raw county name

    Returns:
        Normalized county name or None if input is empty

    Examples:
        >>> normalize_county("Travis County")
        "TRAVIS"
        >>> normalize_county("St. Louis County")
        "SAINT LOUIS"
    """
    if not county:
        return None

    normalized = county.upper().strip()

    # Remove "COUNTY" suffix
    normalized = re.sub(r"\s+COUNTY$", "", normalized)

    # Standardize Saint abbreviations
    normalized = re.sub(r"\bST\.?\s", "SAINT ", normalized)

    # Remove punctuation
    normalized = re.sub(r"[.,]", "", normalized)

    # Collapse whitespace
    normalized = " ".join(normalized.split())

    return normalized if normalized else None


def normalize_state(state: Optional[str]) -> Optional[str]:
    """
    Normalize state to 2-letter code.

    Args:
        state: State name or abbreviation

    Returns:
        2-letter state code or None if invalid
    """
    if not state:
        return None

    # State name to code mapping
    STATE_CODES = {
        "ALABAMA": "AL",
        "ALASKA": "AK",
        "ARIZONA": "AZ",
        "ARKANSAS": "AR",
        "CALIFORNIA": "CA",
        "COLORADO": "CO",
        "CONNECTICUT": "CT",
        "DELAWARE": "DE",
        "FLORIDA": "FL",
        "GEORGIA": "GA",
        "HAWAII": "HI",
        "IDAHO": "ID",
        "ILLINOIS": "IL",
        "INDIANA": "IN",
        "IOWA": "IA",
        "KANSAS": "KS",
        "KENTUCKY": "KY",
        "LOUISIANA": "LA",
        "MAINE": "ME",
        "MARYLAND": "MD",
        "MASSACHUSETTS": "MA",
        "MICHIGAN": "MI",
        "MINNESOTA": "MN",
        "MISSISSIPPI": "MS",
        "MISSOURI": "MO",
        "MONTANA": "MT",
        "NEBRASKA": "NE",
        "NEVADA": "NV",
        "NEW HAMPSHIRE": "NH",
        "NEW JERSEY": "NJ",
        "NEW MEXICO": "NM",
        "NEW YORK": "NY",
        "NORTH CAROLINA": "NC",
        "NORTH DAKOTA": "ND",
        "OHIO": "OH",
        "OKLAHOMA": "OK",
        "OREGON": "OR",
        "PENNSYLVANIA": "PA",
        "RHODE ISLAND": "RI",
        "SOUTH CAROLINA": "SC",
        "SOUTH DAKOTA": "SD",
        "TENNESSEE": "TN",
        "TEXAS": "TX",
        "UTAH": "UT",
        "VERMONT": "VT",
        "VIRGINIA": "VA",
        "WASHINGTON": "WA",
        "WEST VIRGINIA": "WV",
        "WISCONSIN": "WI",
        "WYOMING": "WY",
        "DISTRICT OF COLUMBIA": "DC",
        "PUERTO RICO": "PR",
        "GUAM": "GU",
        "VIRGIN ISLANDS": "VI",
        "AMERICAN SAMOA": "AS",
        "NORTHERN MARIANA ISLANDS": "MP",
    }

    normalized = state.upper().strip()

    # If already a 2-letter code, validate it
    if len(normalized) == 2:
        valid_codes = set(STATE_CODES.values())
        if normalized in valid_codes:
            return normalized
        return None

    # Look up full state name
    return STATE_CODES.get(normalized)


def normalize_owner_name(name: Optional[str]) -> Optional[str]:
    """
    Normalize owner/applicant name for fuzzy matching.

    Transformations:
    - Convert to uppercase
    - Remove punctuation
    - Remove common suffixes (JR, SR, II, III, IV)
    - Remove business designators (LLC, INC, CORP, etc.)
    - Collapse whitespace

    Args:
        name: Raw owner/applicant name

    Returns:
        Normalized name or None if input is empty
    """
    if not name:
        return None

    normalized = name.upper().strip()

    # Remove punctuation
    normalized = re.sub(r'[.,\'"()]', "", normalized)

    # Remove common name suffixes
    normalized = re.sub(r"\b(JR|SR|II|III|IV|V|ESQ|PHD|MD|DDS)\b", "", normalized)

    # Remove business designators
    normalized = re.sub(
        r"\b(LLC|L\.L\.C\.|INC|INCORPORATED|CORP|CORPORATION|LTD|LIMITED|"
        r"LP|L\.P\.|LLP|L\.L\.P\.|PC|P\.C\.|PLLC|P\.L\.L\.C\.|"
        r"CO|COMPANY|TRUST|ESTATE|PARTNERSHIP)\b",
        "",
        normalized,
    )

    # Collapse whitespace
    normalized = " ".join(normalized.split())

    return normalized if normalized else None


def compute_address_hash(
    normalized_address: Optional[str], normalized_county: Optional[str], state_code: Optional[str]
) -> Optional[str]:
    """
    Compute SHA256 hash for address deduplication.

    Creates a composite key from normalized address + county + state
    for unique constraint in database.

    Args:
        normalized_address: Normalized street address
        normalized_county: Normalized county name
        state_code: 2-letter state code

    Returns:
        64-character SHA256 hex digest or None if address is missing

    Examples:
        >>> compute_address_hash("123 N MAIN ST APT 4B", "TRAVIS", "TX")
        "a1b2c3d4e5f6..."  # 64 chars
    """
    if not normalized_address:
        return None

    # Create composite key with pipe separator
    components = [normalized_address or "", (normalized_county or "").upper(), (state_code or "").upper()]
    composite_key = "|".join(components)

    # Compute SHA256
    return hashlib.sha256(composite_key.encode("utf-8")).hexdigest()


def normalize_and_hash(
    address: Optional[str], county: Optional[str], state: Optional[str]
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Convenience function to normalize all components and compute hash.

    Args:
        address: Raw street address
        county: Raw county name
        state: Raw state name or code

    Returns:
        Tuple of (normalized_address, normalized_county, state_code, address_hash)

    Examples:
        >>> normalize_and_hash("123 N. Main Street", "Travis County", "Texas")
        ("123 N MAIN ST", "TRAVIS", "TX", "a1b2c3...")
    """
    norm_address = normalize_address(address)
    norm_county = normalize_county(county)
    state_code = normalize_state(state)
    address_hash = compute_address_hash(norm_address, norm_county, state_code)

    return norm_address, norm_county, state_code, address_hash


# For testing
if __name__ == "__main__":
    # Test address normalization
    test_addresses = [
        "123 North Main Street, Apt. 4B",
        "456 S.W. Oak Avenue #201",
        "789 East 1st Ave",
        "1000 West Highway 290",
        "P.O. Box 12345",
        "100 Southeast Boulevard, Suite 200",
        None,
        "",
    ]

    print("Address Normalization Tests:")
    print("-" * 60)
    for addr in test_addresses:
        result = normalize_address(addr)
        print(f"  {addr!r:45} → {result!r}")

    print("\nCounty Normalization Tests:")
    print("-" * 60)
    for county in ["Travis County", "St. Louis County", "Prince George's County"]:
        result = normalize_county(county)
        print(f"  {county!r:30} → {result!r}")

    print("\nFull Normalization + Hash:")
    print("-" * 60)
    addr, county, state, hash_val = normalize_and_hash("123 N. Main Street, Apt 4B", "Travis County", "Texas")
    print(f"  Address: {addr}")
    print(f"  County:  {county}")
    print(f"  State:   {state}")
    print(f"  Hash:    {hash_val}")
