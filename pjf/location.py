"""Location rule, ported from v1: remote work must be open to someone living in Spain.

OK:      Spain listed, or EU / Europe / EEA / EMEA / worldwide.
Blocked: a restriction to other countries or regions ("Remote - US", "Remote (Germany)").
Unclear: everything else. The filter turns unclear into "check", never into a drop.
"""
import re

WORLDWIDE = re.compile(
    r"\b(worldwide|world ?wide|anywhere|global(ly)?|any country|"
    r"location ?independent|remote, any)\b", re.I)

EU_WIDE = re.compile(
    r"\b(europe|european union|european economic area|eea|emea|eu[- ]based|"
    r"eu residents?|within the eu|eu|cet|cest|gmt\s*[+-]?\s*[0-3]|"
    r"utc\s*[+-]?\s*[0-3])\b", re.I)

# Case-sensitive so the English word "us" never reads as the United States.
BARE_CODES = re.compile(r"\b(?:US|USA|UK|UAE|NZ|CA)\b|\bU\.S\.(?:A\.?)?|\bU\.K\.")

SPAIN = re.compile(r"\b(spain|espa[nñ]a|iberia|galicia|coru[nñ]a|madrid|"
                   r"barcelona|valencia|sevilla|seville|bilbao|m[aá]laga|compostela|vigo|zaragoza|alicante|granada)\b", re.I)

BLOCKING_PLACES = re.compile(
    r"\b("
    r"usa|u\.s\.a|united states|us[- ]only|us[- ]based|america[ns]?|canada|canadian|"
    r"mexico|brazil|brasil|argentina|chile|colombia|peru|uruguay|costa rica|"
    r"india|pakistan|bangladesh|sri lanka|philippines|indonesia|malaysia|vietnam|"
    r"thailand|singapore|china|hong kong|taiwan|japan|korea|australia|new zealand|"
    r"nigeria|kenya|ghana|egypt|south africa|morocco|israel|"
    r"united arab emirates|uae|dubai|saudi|qatar|turkey|t[uü]rkiye|"
    r"latam|latin america|north america|south america|apac|asia[- ]pacific|"
    r"americas|anz|middle east|"
    r"united kingdom|uk[- ]only|uk[- ]based|england|scotland|wales|ireland|"
    r"germany|deutschland|france|italy|portugal|netherlands|belgium|austria|"
    r"switzerland|sweden|norway|denmark|finland|iceland|poland|czech|slovakia|"
    r"hungary|romania|bulgaria|greece|croatia|slovenia|serbia|ukraine|lithuania|"
    r"latvia|estonia|luxembourg|malta|cyprus"
    r")\b", re.I)

# Countries missing above, US states, Canadian provinces and game-industry cities
# outside Spain. A place here counts as a restriction that excludes Spain, so
# "Rome / remote" is treated like "Remote - Italy". (Not "Santiago": Compostela.)
OTHER_PLACES = re.compile(
    r"\b("
    r"afghanistan|albania|algeria|andorra|angola|armenia|azerbaijan|bahrain|belarus|bolivia|"
    r"bosnia|botswana|cambodia|cameroon|cuba|czechia|dominican republic|ecuador|el salvador|"
    r"ethiopia|georgia|guatemala|honduras|iran|iraq|jamaica|jordan|kazakhstan|kosovo|kuwait|"
    r"kyrgyzstan|laos|lebanon|libya|liechtenstein|macedonia|moldova|monaco|mongolia|montenegro|"
    r"mozambique|myanmar|namibia|nepal|nicaragua|oman|panama|paraguay|puerto rico|russia|rwanda|"
    r"san marino|senegal|sudan|syria|tanzania|tunisia|uganda|uzbekistan|venezuela|zambia|zimbabwe|"
    r"alabama|alaska|arizona|arkansas|california|colorado|connecticut|delaware|florida|hawaii|"
    r"idaho|illinois|indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|michigan|"
    r"minnesota|mississippi|missouri|montana|nebraska|nevada|new hampshire|new jersey|new mexico|"
    r"new york|north carolina|north dakota|ohio|oklahoma|oregon|pennsylvania|rhode island|"
    r"south carolina|south dakota|tennessee|texas|utah|vermont|virginia|washington|wisconsin|wyoming|"
    r"ontario|quebec|qu[eé]bec|british columbia|alberta|manitoba|saskatchewan|nova scotia|new brunswick|"
    r"london|manchester|edinburgh|glasgow|dundee|leamington|guildford|brighton|cambridge|oxford|"
    r"dublin|paris|lyon|montpellier|bordeaux|berlin|hamburg|munich|m[uü]nchen|frankfurt|cologne|"
    r"k[oö]ln|d[uü]sseldorf|rome|milan|turin|amsterdam|rotterdam|utrecht|brussels|antwerp|"
    r"stockholm|gothenburg|g[oö]teborg|malm[oö]|uppsala|helsinki|espoo|oslo|copenhagen|aarhus|"
    r"warsaw|krak[oó]w|wroc[lł]aw|katowice|prague|brno|bratislava|budapest|bucharest|belgrade|"
    r"zagreb|ljubljana|vienna|zurich|z[uü]rich|geneva|lisbon|porto|athens|kyiv|kiev|istanbul|"
    r"ankara|tallinn|riga|vilnius|reykjavik|"
    r"los angeles|san francisco|bay area|seattle|bellevue|redmond|austin|nyc|boston|chicago|"
    r"san diego|san mateo|irvine|santa monica|denver|montr[eé]al|toronto|vancouver|ottawa|"
    r"tokyo|osaka|seoul|shanghai|beijing|shenzhen|bangkok|manila|bangalore|bengaluru|hyderabad|"
    r"pune|sydney|melbourne|brisbane|auckland|tel aviv|cairo|lagos|nairobi|s[aã]o paulo|"
    r"mexico city|buenos aires|bogot[aá]"
    r")\b", re.I)

ONSITE = re.compile(r"\b(on[- ]?site|onsite|hybrid|in[- ]office|office[- ]based|"
                    r"relocation required|must relocate)\b", re.I)

BODY_RESTRICTION = re.compile(
    r"(?:must (?:be |reside |live )(?:located |based |residing )?in|"
    r"only (?:accepting|considering) (?:candidates|applicants) (?:in|from|based in)|"
    r"candidates must be (?:located|based|residing) in|"
    r"authoriz(?:ed|ation) to work in|legally able to work in|"
    r"eligible to work in|work permit for|residents? of)\s+"
    r"(?:the\s+)?([A-Za-z .,'&/-]{3,60})", re.I)


# "Remote US", "remote (Canada)", "US-only", "remote within the United States"...
# Country codes stay case-sensitive so the word "us" never matches.
REMOTE_SCOPE = re.compile(
    r"(?i:\b(?:remote|work from home|wfh)\b)\s*[-\u2013(,:/]?\s*(?i:(?:in|within|from)\s+)?(?i:the\s+)?"
    r"(US|USA|U\.S\.A?\.?|UK|U\.K\.|(?i:united states|canada|north america|latam|latin america|apac|india))\b"
    r"|\b(?:US|USA|UK)[- ](?i:only|based)\b")


def scope_verdict(text: str) -> str:
    """blocked when the text limits the remote job to another country or region,
    unless Europe/Spain/worldwide is named right after ("Remote US or EU")."""
    for m in REMOTE_SCOPE.finditer(text or ""):
        tail = text[m.end():m.end() + 40]
        if SPAIN.search(tail) or WORLDWIDE.search(tail) or EU_WIDE.search(tail):
            continue
        return "blocked"
    return "unclear"


def classify_place(text: str) -> str:
    """ok | blocked | unclear for a short place-like string."""
    if not text or not text.strip():
        return "unclear"
    if SPAIN.search(text) or WORLDWIDE.search(text) or EU_WIDE.search(text):
        return "ok"
    if BLOCKING_PLACES.search(text) or BARE_CODES.search(text) or OTHER_PLACES.search(text):
        return "blocked"
    return "unclear"


def is_wide(text: str) -> bool:
    """A region-wide place (Europe, worldwide), as opposed to a city or a country."""
    return bool(WORLDWIDE.search(text or "") or EU_WIDE.search(text or ""))


def body_verdict(description: str) -> str:
    """Look for a hard residency requirement in the posting text."""
    for match in BODY_RESTRICTION.finditer((description or "")[:6000]):
        verdict = classify_place(match.group(1))
        if verdict != "unclear":
            return verdict
    return scope_verdict((description or "")[:6000])
