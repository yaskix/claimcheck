"""Extract quantities from prose and compare them.

The whole system rests on this module. A claim is trustworthy because a
human sourced it; a *document* is trustworthy because every quantity in it
can be traced back to one of those claims. That tracing is a numeric
comparison, so the numbers have to come out of the text reliably and in a
normalised form.

Deliberately narrow. This handles the quantity shapes that actually appear
in marketing copy — currency, percentages, percentage points, counts — and
says so out loud rather than pretending to general numeric understanding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CURRENCIES = ["SEK", "NOK", "DKK", "EUR", "USD", "CHF", "GBP", "JPY", "PLN"]

SCALE_WORDS = {
    "thousand": 1e3,
    "k": 1e3,
    "million": 1e6,
    "millions": 1e6,
    "m": 1e6,
    "mn": 1e6,
    "billion": 1e9,
    "billions": 1e9,
    "bn": 1e9,
    "trillion": 1e12,
}

SCALE_PREFIX = {"K": 1e3, "M": 1e6, "B": 1e9}

# A numeral, with either comma or space as a thousands separator.
#
# The leading lookbehind matters more than it looks. Without it, the
# space-separator branch glues digits across a word boundary: "Q4 2025" parses
# as "4 202" followed by a stray 5. Requiring the numeral to start clear of a
# letter, digit or decimal point stops that, and stops a partial match on the
# tail of a decimal.
NUM = r"(?<![A-Za-z0-9.,])(?:\d{1,3}(?:[ ,]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
CUR = "|".join(CURRENCIES)
SCALE = "|".join(sorted(SCALE_WORDS, key=len, reverse=True))

# Unit classes. Two quantities can only match if their units are equal.
UNIT_PERCENT = "%"
UNIT_POINTS = "pp"
UNIT_COUNT = "count"
UNIT_YEAR = "year"

# A number bound to a word is a name, not a measurement: TR-40, IP68, ISO 4210.
# Treating product codes and standards references as quantities was the first
# thing the tests caught, and it is the kind of error that would have made the
# gate noisy enough to be switched off.
#
# \Z, not $. In Python, `$` also matches immediately before a trailing
# newline, so a figure at the start of a line inherited the last letter of the
# previous line and was silently dropped as part of an identifier. Silently is
# the problem: a gate that drops a figure fails open.
#
# The guard applies ONLY to bare numbers. An abbreviation in front of a number
# carrying a unit does not make it a name: "VAT 25%" and "CAGR 14%" are
# measurements, and an earlier version dropped both. A dropped figure is the
# worst failure this program has, because it reports a pass.
IDENTIFIER_PREFIX = re.compile(r"(?:[A-Za-z]-?|\b[A-Z]{2,5}[ \t])\Z")


@dataclass(frozen=True)
class Quantity:
    """A number found in text, normalised to a magnitude and a unit."""

    value: float
    unit: str
    raw: str
    start: int
    end: int

    def __str__(self) -> str:
        return f"{self.raw!r} ({self.value:g} {self.unit})"


def _to_number(raw: str) -> float:
    s = re.sub(r"(?<=\d)[ ,](?=\d{3}\b)", "", raw.strip())
    return float(s.replace(" ", ""))


# Ordered most specific first. Each pattern yields (value, unit) via its handler.
_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 812 MSEK, 1.1 BEUR
    (re.compile(rf"(?P<n>{NUM})\s*(?P<p>[KMB])(?P<c>{CUR})\b"), "scaled_currency"),
    # SEK 812 million, EUR 270 billion, CHF 10
    (re.compile(rf"(?P<c>{CUR})\s*(?P<n>{NUM})(?:\s*(?P<s>{SCALE})\b)?", re.I), "currency_first"),
    # 812 million SEK, 10 CHF
    (re.compile(rf"(?P<n>{NUM})(?:\s*(?P<s>{SCALE}))?\s*(?P<c>{CUR})\b", re.I), "currency_last"),
    # 2 percentage points, 2 pp
    (re.compile(rf"(?P<n>{NUM})\s*(?:pp\b|percentage\s+points?\b)", re.I), "points"),
    # 7%, 7 per cent, 7 percent
    (re.compile(rf"(?P<n>{NUM})\s*(?:%|per\s?cents?\b|percent\b)", re.I), "percent"),
    # 18 thousand, 1.2 million (no currency)
    (re.compile(rf"(?P<n>{NUM})\s*(?P<s>{SCALE})\b", re.I), "scaled_count"),
    # 18,000
    (re.compile(rf"(?P<n>{NUM})"), "count"),
]


def extract(text: str, include_years: bool = False) -> list[Quantity]:
    """Pull every quantity out of `text`.

    Years are excluded by default. Dates are the single largest source of
    false positives in real copy, and a wrong year is a different kind of
    error from a wrong performance figure. Pass include_years=True to check
    them too.
    """
    found: list[Quantity] = []
    consumed: set[int] = set()

    for pattern, kind in _PATTERNS:
        for match in pattern.finditer(text):
            span = range(match.start(), match.end())
            if any(i in consumed for i in span):
                continue

            numeral = _to_number(match.group("n"))
            groups = match.groupdict()

            if kind == "scaled_currency":
                value = numeral * SCALE_PREFIX[groups["p"].upper()]
                unit = groups["c"].upper()
            elif kind in ("currency_first", "currency_last"):
                scale = SCALE_WORDS.get((groups.get("s") or "").lower(), 1.0)
                value, unit = numeral * scale, groups["c"].upper()
            elif kind == "points":
                value, unit = numeral, UNIT_POINTS
            elif kind == "percent":
                value, unit = numeral, UNIT_PERCENT
            elif kind == "scaled_count":
                value = numeral * SCALE_WORDS[groups["s"].lower()]
                unit = UNIT_COUNT
            else:
                value, unit = numeral, UNIT_COUNT
                if numeral.is_integer() and 1900 <= numeral <= 2100 and len(match.group("n")) == 4:
                    unit = UNIT_YEAR

            # A unit is the tell. A bare number after an abbreviation is a
            # name; the same position carrying %, pp or a currency is a
            # measurement and must be checked.
            if unit in (UNIT_COUNT, UNIT_YEAR) and IDENTIFIER_PREFIX.search(text[: match.start()]):
                consumed.update(span)
                continue

            if unit == UNIT_YEAR and not include_years:
                consumed.update(span)
                continue

            consumed.update(span)
            found.append(
                Quantity(
                    value=value,
                    unit=unit,
                    raw=match.group(0).strip(),
                    start=match.start(),
                    end=match.end(),
                )
            )

    return sorted(found, key=lambda q: q.start)


def matches(a: Quantity, b: Quantity, tolerance: float = 0.01) -> bool:
    """True if two quantities can be considered the same figure.

    Tolerance exists because rounding is legitimate. "Approximately SEK 0.81
    billion" and "SEK 812 million" are the same fact stated at different
    precision, and a system that rejected the rounded form would push writers
    into false precision — the opposite of what it is for.

    Tolerance is a policy choice, not a technical detail. 1% is the default
    because it admits ordinary rounding and refuses a figure that has drifted.
    """
    if a.unit != b.unit:
        return False
    if a.value == b.value:
        return True
    if a.value == 0 or b.value == 0:
        return False
    return abs(a.value - b.value) / max(abs(a.value), abs(b.value)) <= tolerance
