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
                   r"barcelona|valencia|sevilla|seville|bilbao|m[aá]laga)\b", re.I)

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

ONSITE = re.compile(r"\b(on[- ]?site|onsite|hybrid|in[- ]office|office[- ]based|"
                    r"relocation required|must relocate)\b", re.I)

BODY_RESTRICTION = re.compile(
    r"(?:must (?:be |reside |live )(?:located |based |residing )?in|"
    r"only (?:accepting|considering) (?:candidates|applicants) (?:in|from|based in)|"
    r"candidates must be (?:located|based|residing) in|"
    r"authoriz(?:ed|ation) to work in|legally able to work in|"
    r"eligible to work in|work permit for|residents? of)\s+"
    r"(?:the\s+)?([A-Za-z .,'&/-]{3,60})", re.I)


def classify_place(text: str) -> str:
    """ok | blocked | unclear for a short place-like string."""
    if not text or not text.strip():
        return "unclear"
    if SPAIN.search(text) or WORLDWIDE.search(text) or EU_WIDE.search(text):
        return "ok"
    if BLOCKING_PLACES.search(text) or BARE_CODES.search(text):
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
    return "unclear"
