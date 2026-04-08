"""
Texas ZIP code to county lookup service.

Maps ZIP codes to counties for the MAC Septic service area
(Travis, Hays, Bexar, Comal, Guadalupe) and other Texas counties.
"""

# Service area counties with their specific septic rules
COUNTY_RULES = {
    "Travis": {
        "enforcement": "Aggressive",
        "self_maintenance": False,
        "reporting": "Every 4 months",
        "phone": "512-854-9383",
        "department": "Transportation & Natural Resources (TNR)",
        "key_rules": [
            "Licensed provider required at all times",
            "Reports submitted via county online portal every 4 months",
            "Recorded affidavit filed with county for maintenance obligation",
            "LCRA lake zone: properties within 2,000 ft of Lake Travis fall under LCRA (512-578-3216)",
            "Daily inspection fees accrue until violations corrected",
        ],
    },
    "Hays": {
        "enforcement": "Aggressive",
        "self_maintenance": False,
        "reporting": "Every 4 months",
        "phone": "512-393-2150",
        "department": "Development Services",
        "key_rules": [
            "Licensed provider required for all aerobic/advanced systems",
            "Edwards Aquifer Recharge Zone may require protection plan",
            "Permit required for ALL OSSF regardless of lot size",
            "County has pursued fines against homeowners with failed systems",
        ],
    },
    "Bexar": {
        "enforcement": "Strict",
        "self_maintenance": False,
        "reporting": "Every 4 months",
        "phone": "210-335-6700",
        "department": "Environmental Services",
        "key_rules": [
            "Continuous service contract required — mandatory, not optional",
            "SARA-certified provider required",
            "Lapse over 1 year requires renewal permit with engineer certification",
            "Conventional systems must renew every 5 years ($30 fee)",
            "Seven violation categories including illegal discharge",
        ],
    },
    "Comal": {
        "enforcement": "Active",
        "self_maintenance": True,
        "reporting": "Every 4 months",
        "phone": "830-608-2090",
        "department": "Environmental Health",
        "key_rules": [
            "Homeowner self-maintenance allowed for single-family dwellings",
            "Two-strike rule: 2 violations in 3 years = mandatory licensed contract",
            "10-day cure period after violation notice",
            "Property transfer requires $150 reinspection fee if system fails",
        ],
    },
    "Guadalupe": {
        "enforcement": "Standard",
        "self_maintenance": True,
        "reporting": "Every 4 months (TCEQ baseline)",
        "phone": "830-303-8858",
        "department": "Environmental Health",
        "key_rules": [
            "Follows TCEQ baseline — no extra prohibition on self-maintenance",
            "1-acre minimum lot size for new OSSF installations",
            "County-issued License to Operate required",
            "Permit required even to connect into existing OSSF",
            "County must approve/deny within 30 days",
        ],
    },
}

# Comprehensive Texas ZIP code to county mapping
# Focus on the 5 service area counties + surrounding area
TX_ZIP_TO_COUNTY: dict[str, str] = {}

# Travis County ZIP codes
for z in [
    "73301", "73344",
    "78617", "78652", "78653", "78660", "78664", "78681",
    "78701", "78702", "78703", "78704", "78705", "78708", "78709",
    "78710", "78711", "78712", "78713", "78714", "78715", "78716",
    "78717", "78718", "78719", "78720", "78721", "78722", "78723",
    "78724", "78725", "78726", "78727", "78728", "78729", "78730",
    "78731", "78732", "78733", "78734", "78735", "78736", "78737",
    "78738", "78739", "78741", "78742", "78744", "78745", "78746",
    "78747", "78748", "78749", "78750", "78751", "78752", "78753",
    "78754", "78755", "78756", "78757", "78758", "78759", "78760",
    "78761", "78762", "78763", "78764", "78765", "78766", "78767",
    "78768", "78769", "78772", "78773", "78774", "78778", "78779",
    "78783", "78799",
]:
    TX_ZIP_TO_COUNTY[z] = "Travis"

# Hays County ZIP codes
for z in [
    "78610", "78618", "78619", "78620", "78640", "78656", "78666",
    "78676", "78737",  # shared with Travis in some areas
]:
    TX_ZIP_TO_COUNTY[z] = TX_ZIP_TO_COUNTY.get(z) or "Hays"

# Kyle, Buda, San Marcos, Wimberley, Dripping Springs
TX_ZIP_TO_COUNTY["78610"] = "Hays"  # Buda
TX_ZIP_TO_COUNTY["78640"] = "Hays"  # Kyle
TX_ZIP_TO_COUNTY["78666"] = "Hays"  # San Marcos
TX_ZIP_TO_COUNTY["78676"] = "Hays"  # Wimberley
TX_ZIP_TO_COUNTY["78620"] = "Hays"  # Dripping Springs
TX_ZIP_TO_COUNTY["78619"] = "Hays"  # Driftwood

# Bexar County ZIP codes (San Antonio metro)
for z in [
    "78006", "78015", "78023", "78039", "78056", "78073", "78101",
    "78109", "78112", "78148", "78150", "78152", "78154", "78163",
    "78201", "78202", "78203", "78204", "78205", "78206", "78207",
    "78208", "78209", "78210", "78211", "78212", "78213", "78214",
    "78215", "78216", "78217", "78218", "78219", "78220", "78221",
    "78222", "78223", "78224", "78225", "78226", "78227", "78228",
    "78229", "78230", "78231", "78232", "78233", "78234", "78235",
    "78236", "78237", "78238", "78239", "78240", "78241", "78242",
    "78243", "78244", "78245", "78246", "78247", "78248", "78249",
    "78250", "78251", "78252", "78253", "78254", "78255", "78256",
    "78257", "78258", "78259", "78260", "78261", "78263", "78264",
    "78265", "78266", "78268", "78269", "78270", "78275", "78278",
    "78279", "78280", "78283", "78284", "78285", "78286", "78287",
    "78288", "78289", "78291", "78292", "78293", "78294", "78295",
    "78296", "78297", "78298", "78299",
]:
    TX_ZIP_TO_COUNTY[z] = "Bexar"

# Comal County ZIP codes (New Braunfels, Canyon Lake, etc.)
for z in [
    "78070",  # Spring Branch
    "78130", "78131", "78132", "78133", "78135",  # New Braunfels
    "78163",  # shared - Bulverde
    "78606",  # Blanco area (some Comal)
    "78623",  # Fischer
    "78666",  # San Marcos (parts in Comal)
]:
    TX_ZIP_TO_COUNTY[z] = TX_ZIP_TO_COUNTY.get(z) or "Comal"

# Force Comal for core areas
TX_ZIP_TO_COUNTY["78070"] = "Comal"  # Spring Branch
TX_ZIP_TO_COUNTY["78130"] = "Comal"  # New Braunfels
TX_ZIP_TO_COUNTY["78131"] = "Comal"  # New Braunfels
TX_ZIP_TO_COUNTY["78132"] = "Comal"  # New Braunfels
TX_ZIP_TO_COUNTY["78133"] = "Comal"  # Canyon Lake
TX_ZIP_TO_COUNTY["78135"] = "Comal"  # New Braunfels

# Guadalupe County ZIP codes (Seguin, Schertz, etc.)
for z in [
    "78108",  # Cibolo
    "78115",  # Geronimo
    "78121",  # La Vernia (parts)
    "78123",  # McQueeney
    "78140",  # Nixon
    "78148",  # Universal City (parts)
    "78150",  # Randolph AFB area
    "78154",  # Schertz (parts)
    "78155", "78156",  # Seguin
    "78160",  # Stockdale
]:
    TX_ZIP_TO_COUNTY[z] = TX_ZIP_TO_COUNTY.get(z) or "Guadalupe"

# Force Guadalupe for core areas
TX_ZIP_TO_COUNTY["78155"] = "Guadalupe"  # Seguin
TX_ZIP_TO_COUNTY["78156"] = "Guadalupe"  # Seguin
TX_ZIP_TO_COUNTY["78108"] = "Guadalupe"  # Cibolo
TX_ZIP_TO_COUNTY["78123"] = "Guadalupe"  # McQueeney

# Williamson County (north of Travis)
for z in [
    "76527", "76530", "76537", "76573", "76574", "76578",
    "78613", "78615", "78626", "78628", "78630", "78633", "78634",
    "78641", "78642", "78646", "78660", "78664", "78665", "78673",
    "78674", "78680", "78681", "78682", "78683", "78691",
]:
    TX_ZIP_TO_COUNTY[z] = TX_ZIP_TO_COUNTY.get(z) or "Williamson"

# Force Williamson for core areas
TX_ZIP_TO_COUNTY["78613"] = "Williamson"  # Cedar Park
TX_ZIP_TO_COUNTY["78626"] = "Williamson"  # Georgetown
TX_ZIP_TO_COUNTY["78628"] = "Williamson"  # Georgetown
TX_ZIP_TO_COUNTY["78634"] = "Williamson"  # Hutto
TX_ZIP_TO_COUNTY["78641"] = "Williamson"  # Leander (parts)
TX_ZIP_TO_COUNTY["78642"] = "Williamson"  # Liberty Hill
TX_ZIP_TO_COUNTY["78665"] = "Williamson"  # Round Rock

# Bastrop County
for z in ["78602", "78612", "78621", "78650", "78653", "78659", "78661", "78662"]:
    TX_ZIP_TO_COUNTY[z] = TX_ZIP_TO_COUNTY.get(z) or "Bastrop"

TX_ZIP_TO_COUNTY["78602"] = "Bastrop"  # Bastrop
TX_ZIP_TO_COUNTY["78612"] = "Bastrop"  # Cedar Creek
TX_ZIP_TO_COUNTY["78621"] = "Bastrop"  # Elgin (parts)
TX_ZIP_TO_COUNTY["78659"] = "Bastrop"  # Paige

# Caldwell County
TX_ZIP_TO_COUNTY["78644"] = "Caldwell"  # Lockhart
TX_ZIP_TO_COUNTY["78616"] = "Caldwell"  # Dale
TX_ZIP_TO_COUNTY["78638"] = "Caldwell"  # Kingsbury (parts)
TX_ZIP_TO_COUNTY["78648"] = "Caldwell"  # Luling (parts)

# Blanco County
TX_ZIP_TO_COUNTY["78606"] = TX_ZIP_TO_COUNTY.get("78606") or "Blanco"  # Blanco
TX_ZIP_TO_COUNTY["78636"] = "Blanco"  # Johnson City

# Burnet County
TX_ZIP_TO_COUNTY["78611"] = "Burnet"  # Burnet
TX_ZIP_TO_COUNTY["78639"] = "Burnet"  # Kingsland
TX_ZIP_TO_COUNTY["78654"] = "Burnet"  # Marble Falls
TX_ZIP_TO_COUNTY["78657"] = "Burnet"  # Meadowlakes


def lookup_county(postal_code: str | None, state: str | None) -> str | None:
    """Look up county from ZIP code. Only works for Texas addresses."""
    if not postal_code or not state:
        return None

    # Only look up Texas addresses
    state_upper = state.strip().upper()
    if state_upper not in ("TX", "TEXAS"):
        return None

    # Normalize ZIP (take first 5 digits)
    zip5 = postal_code.strip()[:5]
    if not zip5.isdigit() or len(zip5) != 5:
        return None

    return TX_ZIP_TO_COUNTY.get(zip5)


def get_county_rules(county_name: str | None) -> dict | None:
    """Get septic rules for a county. Returns None if not a service area county."""
    if not county_name:
        return None
    return COUNTY_RULES.get(county_name)


def is_service_area_county(county_name: str | None) -> bool:
    """Check if a county is in the MAC Septic service area."""
    return county_name in COUNTY_RULES
