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


# ─── Tennessee ZIP code to county mapping ───
TN_ZIP_TO_COUNTY: dict[str, str] = {}

# Maury County (Columbia, Spring Hill south, Mt Pleasant)
for z in ["38401", "38402", "38403", "38471", "38474", "38468", "38485"]:
    TN_ZIP_TO_COUNTY[z] = "Maury"
TN_ZIP_TO_COUNTY["38401"] = "Maury"  # Columbia
TN_ZIP_TO_COUNTY["38474"] = "Maury"  # Santa Fe
TN_ZIP_TO_COUNTY["38468"] = "Maury"  # Mt Pleasant

# Williamson County (Franklin, Brentwood, Spring Hill north, Nolensville, Thompson's Station)
for z in ["37064", "37065", "37067", "37068", "37069", "37027", "37174", "37135", "37179"]:
    TN_ZIP_TO_COUNTY[z] = "Williamson"
TN_ZIP_TO_COUNTY["37064"] = "Williamson"  # Franklin
TN_ZIP_TO_COUNTY["37067"] = "Williamson"  # Franklin
TN_ZIP_TO_COUNTY["37027"] = "Williamson"  # Brentwood
TN_ZIP_TO_COUNTY["37174"] = "Williamson"  # Spring Hill
TN_ZIP_TO_COUNTY["37135"] = "Williamson"  # Nolensville
TN_ZIP_TO_COUNTY["37179"] = "Williamson"  # Thompson's Station

# Hickman County (Centerville, Lyles, Bon Aqua, Nunnelly, Primm Springs)
for z in ["37033", "37098", "37025", "37137", "37060"]:
    TN_ZIP_TO_COUNTY[z] = "Hickman"
TN_ZIP_TO_COUNTY["37033"] = "Hickman"  # Centerville
TN_ZIP_TO_COUNTY["37098"] = "Hickman"  # Lyles
TN_ZIP_TO_COUNTY["37025"] = "Hickman"  # Bon Aqua
TN_ZIP_TO_COUNTY["37137"] = "Hickman"  # Nunnelly

# Marshall County (Lewisburg, Chapel Hill, Cornersville, Belfast, Petersburg)
for z in ["37091", "37034", "37047", "37019", "37144"]:
    TN_ZIP_TO_COUNTY[z] = "Marshall"
TN_ZIP_TO_COUNTY["37091"] = "Marshall"  # Lewisburg
TN_ZIP_TO_COUNTY["37034"] = "Marshall"  # Chapel Hill
TN_ZIP_TO_COUNTY["37047"] = "Marshall"  # Cornersville
TN_ZIP_TO_COUNTY["37019"] = "Marshall"  # Belfast
TN_ZIP_TO_COUNTY["37144"] = "Marshall"  # Petersburg

# Lewis County (Hohenwald, Summertown, Hampshire)
for z in ["38462", "38483", "38461"]:
    TN_ZIP_TO_COUNTY[z] = "Lewis"
TN_ZIP_TO_COUNTY["38462"] = "Lewis"  # Hohenwald
TN_ZIP_TO_COUNTY["38483"] = "Lewis"  # Summertown
TN_ZIP_TO_COUNTY["38461"] = "Lewis"  # Hampshire

# Dickson County (Dickson, Burns, Charlotte, White Bluff, Vanleer, Cumberland Furnace)
for z in ["37055", "37029", "37036", "37187", "37181", "37051"]:
    TN_ZIP_TO_COUNTY[z] = "Dickson"
TN_ZIP_TO_COUNTY["37055"] = "Dickson"  # Dickson
TN_ZIP_TO_COUNTY["37029"] = "Dickson"  # Burns
TN_ZIP_TO_COUNTY["37036"] = "Dickson"  # Charlotte
TN_ZIP_TO_COUNTY["37187"] = "Dickson"  # White Bluff
TN_ZIP_TO_COUNTY["37181"] = "Dickson"  # Vanleer

# Davidson County (Nashville, Antioch, Madison, Goodlettsville, Hermitage, Joelton)
for z in [
    "37201", "37202", "37203", "37204", "37205", "37206", "37207", "37208",
    "37209", "37210", "37211", "37212", "37213", "37214", "37215", "37216",
    "37217", "37218", "37219", "37220", "37221", "37222", "37224", "37227",
    "37228", "37229", "37230", "37232", "37234", "37235", "37236", "37238",
    "37240", "37241", "37242", "37243", "37244", "37246", "37250",
    "37013",  # Antioch
    "37115",  # Madison
    "37072",  # Goodlettsville (parts)
    "37076",  # Hermitage
    "37080",  # Joelton
]:
    TN_ZIP_TO_COUNTY[z] = "Davidson"

# Rutherford County (Murfreesboro, Smyrna, La Vergne, Eagleville, Christiana, Rockvale)
for z in ["37127", "37128", "37129", "37130", "37131", "37132", "37133",
          "37167",  # Smyrna
          "37086",  # La Vergne
          "37060",  # Eagleville
          "37037",  # Christiana
          "37153",  # Rockvale
          ]:
    TN_ZIP_TO_COUNTY[z] = "Rutherford"
TN_ZIP_TO_COUNTY["37060"] = "Rutherford"  # Eagleville

# Sumner County (Gallatin, Hendersonville, Castalian Springs)
TN_ZIP_TO_COUNTY["37066"] = "Sumner"  # Gallatin
TN_ZIP_TO_COUNTY["37075"] = "Sumner"  # Hendersonville
TN_ZIP_TO_COUNTY["37031"] = "Sumner"  # Castalian Springs

# Wilson County (Lebanon, Mount Juliet)
TN_ZIP_TO_COUNTY["37087"] = "Wilson"  # Lebanon
TN_ZIP_TO_COUNTY["37088"] = "Wilson"  # Lebanon
TN_ZIP_TO_COUNTY["37122"] = "Wilson"  # Mount Juliet
TN_ZIP_TO_COUNTY["37138"] = "Wilson"  # Old Hickory (parts)

# Cheatham County (Ashland City, Kingston Springs, Pleasant View)
TN_ZIP_TO_COUNTY["37015"] = "Cheatham"  # Ashland City
TN_ZIP_TO_COUNTY["37082"] = "Cheatham"  # Kingston Springs
TN_ZIP_TO_COUNTY["37146"] = "Cheatham"  # Pleasant View

# Lawrence County (Lawrenceburg)
TN_ZIP_TO_COUNTY["38464"] = "Lawrence"  # Lawrenceburg

# Giles County (Pulaski)
TN_ZIP_TO_COUNTY["38478"] = "Giles"  # Pulaski

# Perry County (Linden)
TN_ZIP_TO_COUNTY["37096"] = "Perry"  # Linden

# Wayne County (Waynesboro)
TN_ZIP_TO_COUNTY["38485"] = "Wayne"  # Waynesboro

# Bedford County (Shelbyville)
TN_ZIP_TO_COUNTY["37160"] = "Bedford"  # Shelbyville
TN_ZIP_TO_COUNTY["37162"] = "Bedford"  # Shelbyville

# Coffee County (Tullahoma)
TN_ZIP_TO_COUNTY["37388"] = "Coffee"  # Tullahoma

# DeKalb County (Smithville)
TN_ZIP_TO_COUNTY["37166"] = "DeKalb"  # Smithville

# Cannon County (Woodbury)
TN_ZIP_TO_COUNTY["37190"] = "Cannon"  # Woodbury

# Fairview is in Williamson County
TN_ZIP_TO_COUNTY["37062"] = "Williamson"  # Fairview


# ─── Tennessee city-to-county mapping (fallback when ZIP is missing) ───
TN_CITY_TO_COUNTY: dict[str, str] = {
    # Maury County
    "columbia": "Maury", "mt pleasant": "Maury", "mt. pleasant": "Maury",
    "mount pleasant": "Maury", "culleoka": "Maury", "santa fe": "Maury",
    "williamsport": "Maury", "duck river": "Maury",
    # Williamson County
    "franklin": "Williamson", "brentwood": "Williamson", "nolensville": "Williamson",
    "fairview": "Williamson", "fariview": "Williamson",
    "thompson station": "Williamson", "thompson's station": "Williamson",
    "thomson station": "Williamson", "arrington": "Williamson",
    "college grove": "Williamson",
    # Spring Hill spans Maury/Williamson — default to Williamson (more populated side)
    "spring hill": "Williamson",
    # Hickman County
    "centerville": "Hickman", "lyles": "Hickman", "bon aqua": "Hickman",
    "nunnelly": "Hickman", "primm springs": "Hickman", "pleasantville": "Hickman",
    "only": "Hickman",
    # Marshall County
    "lewisburg": "Marshall", "chapel hill": "Marshall", "chaple hill": "Marshall",
    "chappell hill": "Marshall", "cornersville": "Marshall", "belfast": "Marshall",
    "petersburg": "Marshall",
    # Lewis County
    "hohenwald": "Lewis", "hohenwlad": "Lewis", "summertown": "Lewis",
    "hampshire": "Lewis", "hamphire": "Lewis", "hanpshire": "Lewis",
    # Dickson County
    "dickson": "Dickson", "burns": "Dickson", "bums": "Dickson",
    "charlotte": "Dickson", "white bluff": "Dickson", "vanleer": "Dickson",
    "cumberland furnace": "Dickson",
    # Davidson County
    "nashville": "Davidson", "antioch": "Davidson", "madison": "Davidson",
    "goodlettsville": "Davidson", "hermitage": "Davidson", "joelton": "Davidson",
    # Rutherford County
    "murfreesboro": "Rutherford", "mufreesboro": "Rutherford",
    "murfressboro": "Rutherford", "smyrna": "Rutherford",
    "la vergne": "Rutherford", "lavergne": "Rutherford",
    "eagleville": "Rutherford", "eaglevill": "Rutherford",
    "christiana": "Rutherford", "rockvale": "Rutherford",
    "lascassas": "Rutherford",
    # Sumner County
    "gallatin": "Sumner", "hendersonville": "Sumner",
    "castalian springs": "Sumner",
    # Wilson County
    "lebanon": "Wilson", "mount juliet": "Wilson", "mt juliet": "Wilson",
    # Cheatham County
    "ashland city": "Cheatham", "kingston springs": "Cheatham",
    # Lawrence County
    "lawrenceburg": "Lawrence",
    # Giles County
    "pulaski": "Giles", "lynnville": "Giles",
    # Wayne County
    "waynesboro": "Wayne",
    # Bedford County
    "shelbyville": "Bedford", "bell buckle": "Bedford",
    # Coffee County
    "tullahoma": "Coffee",
    # DeKalb County
    "smithville": "DeKalb",
    # Cannon County
    "woodbury": "Cannon",
    # Perry County
    "linden": "Perry",
}


def lookup_county(postal_code: str | None, state: str | None, city: str | None = None) -> str | None:
    """Look up county from ZIP code and/or city. Works for TX and TN."""
    if not state:
        return None

    state_upper = state.strip().upper()

    # Texas lookup (ZIP-based)
    if state_upper in ("TX", "TEXAS"):
        if not postal_code:
            return None
        zip5 = postal_code.strip()[:5]
        if not zip5.isdigit() or len(zip5) != 5:
            return None
        return TX_ZIP_TO_COUNTY.get(zip5)

    # Tennessee lookup (ZIP first, then city fallback)
    if state_upper in ("TN", "TENNESSEE"):
        # Try ZIP first
        if postal_code:
            zip5 = postal_code.strip()[:5]
            if zip5.isdigit() and len(zip5) == 5:
                county = TN_ZIP_TO_COUNTY.get(zip5)
                if county:
                    return county
        # Fall back to city name
        if city:
            return TN_CITY_TO_COUNTY.get(city.strip().lower())
        return None

    return None


def get_county_rules(county_name: str | None) -> dict | None:
    """Get septic rules for a county. Returns None if not a service area county."""
    if not county_name:
        return None
    return COUNTY_RULES.get(county_name)


def is_service_area_county(county_name: str | None) -> bool:
    """Check if a county is in the MAC Septic service area."""
    return county_name in COUNTY_RULES
