"""
deVeres Auction — Reconciliation · Normalization module
=========================================================

Pure, dependency-free normalization utilities used by the matching engine to
compare records for *meaning* rather than surface form. Every function is total
(never raises on bad input) and deterministic.

The golden rule for reconciliation (from the 1-Jul-2026 meeting): trivial
differences — capitalisation, spacing, punctuation, accents, international
dialing codes, address abbreviations — must NOT count as changes. These helpers
collapse those differences so the classifier only flags *substantive* changes.
"""
from __future__ import annotations

import re
import unicodedata

# ─────────────────────────────────────────────────────────────────────────────
# Generic helpers
# ─────────────────────────────────────────────────────────────────────────────

def strip_accents(s: str) -> str:
    """Fold accented characters to ASCII (é→e, ü→u)."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _alnum_lower(s: str) -> str:
    """Lowercase, strip accents, drop punctuation, collapse whitespace."""
    s = strip_accents(s or "").lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return collapse_ws(s)


# ─────────────────────────────────────────────────────────────────────────────
# Names
# ─────────────────────────────────────────────────────────────────────────────

# Titles/suffixes we ignore when comparing names.
_NAME_NOISE = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "madam",
               "jr", "sr", "phd", "esq"}

def normalize_name(*parts: str) -> str:
    """Normalize a (first, last, …) name to a canonical comparable string:
    lowercase, accent-folded, punctuation-free, title/suffix-stripped, sorted?
    We keep natural order but drop noise tokens. 'Mrs  Aisling  Toth' → 'aisling toth'."""
    joined = _alnum_lower(" ".join(p for p in parts if p))
    toks = [t for t in joined.split() if t not in _NAME_NOISE]
    return " ".join(toks)


def name_key(*parts: str) -> str:
    """Order-independent blocking key for names: sorted tokens.
    'John Smith' and 'Smith John' → 'john smith'."""
    toks = normalize_name(*parts).split()
    return " ".join(sorted(toks))


# ─────────────────────────────────────────────────────────────────────────────
# Emails
# ─────────────────────────────────────────────────────────────────────────────

def normalize_email(s: str) -> str:
    """Lowercase + trim. (We intentionally do NOT strip Gmail dots/plus-tags —
    that could merge distinct addresses; equivalence is exact-normalised only.)"""
    return collapse_ws((s or "").lower()).replace(" ", "")


# ─────────────────────────────────────────────────────────────────────────────
# Phone numbers
# ─────────────────────────────────────────────────────────────────────────────

# Default country calling code for bare national numbers (De Veres = Ireland).
_DEFAULT_CC = "353"
_CC_TRUNK = {  # country code -> national trunk prefix that is dropped after the CC
    "353": "0",   # Ireland
    "44":  "0",   # UK
    "1":   "",    # NANP
    "33":  "0",   # France
    "49":  "0",   # Germany
    "39":  "",    # Italy (keep leading 0)
    "34":  "",    # Spain
    "31":  "0",   # Netherlands
}

def normalize_phone(s: str, default_cc: str = _DEFAULT_CC) -> str:
    """Return a canonical E.164-style digit string, e.g. '+353871234567'.

    Handles the equivalences called out in the meeting:
      087 1234567  ·  +353 87 1234567  ·  00353 87 1234567  →  +353871234567
    Strips spaces, brackets, dashes, dots. Returns '' if no usable digits.
    """
    if not s:
        return ""
    raw = str(s).strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    # 00 international prefix → treat as leading '+'
    if digits.startswith("00"):
        digits = digits[2:]
        has_plus = True
    if has_plus:
        return "+" + digits
    # Already starts with a known country code (and isn't a national 0-number)?
    for cc in ("353", "44", "34", "39", "49", "33", "31", "1"):
        if digits.startswith(cc) and not digits.startswith("0"):
            # Heuristic: if the remainder length is plausible, accept as CC-prefixed.
            if len(digits) - len(cc) >= 6:
                return "+" + digits
            break
    # National number: drop trunk prefix, prepend default country code.
    trunk = _CC_TRUNK.get(default_cc, "0")
    if trunk and digits.startswith(trunk):
        digits = digits[len(trunk):]
    return "+" + default_cc + digits


def phone_key(s: str, default_cc: str = _DEFAULT_CC) -> str:
    """A tolerant comparison key: the last 7 digits of the *national significant
    number* (country code stripped). Robust to CC/trunk/format variations.
    Returns '' if the number is too short to be reliable — which is how we detect
    the De Veres export's TRUNCATED phones (e.g. '35387' → national '35387' → '')
    so they never falsely match, nor count as a real change."""
    norm = normalize_phone(s, default_cc)
    digits = re.sub(r"\D", "", norm)
    for cc in ("353", "44", "1", "33", "49", "39", "34", "31"):
        if digits.startswith(cc):
            digits = digits[len(cc):]      # drop country code → national significant number
            break
    if len(digits) < 7:
        return ""                          # truncated / partial / unusable
    return digits[-7:]


# ─────────────────────────────────────────────────────────────────────────────
# Addresses
# ─────────────────────────────────────────────────────────────────────────────

# Map common address words to a single canonical token so 'Street'=='St',
# 'Road'=='Rd', 'Apartment'=='Apt' etc. Both sides normalise to the SAME token.
_ADDR_SYNONYMS = {
    "street": "st", "st": "st",
    "road": "rd", "rd": "rd",
    "avenue": "ave", "ave": "ave", "av": "ave",
    "apartment": "apt", "apt": "apt", "apartments": "apt",
    "drive": "dr", "dr": "dr",
    "lane": "ln", "ln": "ln",
    "court": "ct", "ct": "ct",
    "place": "pl", "pl": "pl",
    "square": "sq", "sq": "sq",
    "terrace": "ter", "ter": "ter",
    "crescent": "cres", "cres": "cres",
    "boulevard": "blvd", "blvd": "blvd",
    "park": "pk", "pk": "pk",
    "close": "cl", "cl": "cl",
    "number": "no", "no": "no", "num": "no",
    "saint": "st", "sainte": "st",
    "flat": "apt",
    "floor": "fl", "fl": "fl",
    "suite": "ste", "ste": "ste",
}

def normalize_address(*parts: str) -> str:
    """Normalize address component(s) to a canonical comparable string:
    lowercase, accent-folded, punctuation removed, whitespace collapsed, and
    common street-type words mapped to a single abbreviation token."""
    base = _alnum_lower(" ".join(p for p in parts if p))
    toks = [_ADDR_SYNONYMS.get(t, t) for t in base.split()]
    return " ".join(toks)


# ─────────────────────────────────────────────────────────────────────────────
# Postcode
# ─────────────────────────────────────────────────────────────────────────────

_EIRCODE_RE = re.compile(r"^[A-Z]\d{2}[0-9A-Z]{4}$")

def is_eircode(s: str) -> bool:
    """True if the value looks like an Irish Eircode (e.g. 'D02 P283', 'A63DC64').
    Used to detect De Veres master rows where an Eircode was mis-entered into the
    town field while postalCode was left blank."""
    return bool(_EIRCODE_RE.match(normalize_postcode(s)))


def normalize_postcode(s: str) -> str:
    """Upper-case, remove all whitespace/punctuation. Handles Irish Eircode
    variants ('D18 XY53' == 'D18XY53' == 'd18xy53') and generic postcodes."""
    return re.sub(r"[^\w]", "", strip_accents(s or "").upper())


# ─────────────────────────────────────────────────────────────────────────────
# Country (ISO mapping)
# ─────────────────────────────────────────────────────────────────────────────

_COUNTRY_ISO = {
    "ireland": "IE", "eire": "IE", "republic of ireland": "IE", "roi": "IE", "ie": "IE",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB", "northern ireland": "GB", "gb": "GB",
    "united states": "US", "usa": "US", "us": "US", "america": "US",
    "france": "FR", "fr": "FR", "germany": "DE", "de": "DE", "deutschland": "DE",
    "italy": "IT", "it": "IT", "spain": "ES", "es": "ES", "espana": "ES",
    "netherlands": "NL", "nl": "NL", "holland": "NL", "belgium": "BE", "be": "BE",
    "switzerland": "CH", "ch": "CH", "austria": "AT", "at": "AT",
    "canada": "CA", "ca": "CA", "australia": "AU", "au": "AU",
}

def normalize_country(s: str) -> str:
    """Map a free-text country to an ISO-3166 alpha-2 code where recognised;
    otherwise return the accent-folded lowercase name."""
    key = _alnum_lower(s)
    return _COUNTRY_ISO.get(key, key.upper() if len(key) == 2 else key)
