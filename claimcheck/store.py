"""Loading and validating a claim store.

A claim is a single statement of fact that a human has sourced and tagged.
The store is the only thing a document is allowed to draw on.

Design decision worth naming: **the claim's own text is the source of truth
for its numbers.** They are extracted from the sentence rather than declared
in a separate field, so a claim's prose and its figures cannot drift apart.
`also_expressed_as` exists for alternate renderings of the same fact — "812
MSEK" for "SEK 812 million" — not for new facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .numbers import Quantity, extract

SENSITIVITIES = ("PUBLIC", "OWN", "RESULT", "SOFT", "HOLD")

#: Tags that may never appear in a generated or reviewed document.
BLOCKED = ("HOLD",)

#: Tags that require an explicit human decision per document.
NEEDS_DECISION = ("SOFT",)


class StoreError(ValueError):
    """The store itself is malformed. Fail loudly; never fall back."""


@dataclass
class Claim:
    id: str
    text: str
    sensitivity: str
    source: dict
    themes: list[str] = field(default_factory=list)
    also_expressed_as: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def quantities(self) -> list[Quantity]:
        """Every figure this claim licenses, from its text and its variants."""
        out = list(extract(self.text))
        for variant in self.also_expressed_as:
            out.extend(extract(variant))
        return out

    @property
    def blocked(self) -> bool:
        return self.sensitivity in BLOCKED

    @property
    def needs_decision(self) -> bool:
        return self.sensitivity in NEEDS_DECISION

    def one_line(self) -> str:
        return " ".join(self.text.split())


@dataclass
class Store:
    subject: str
    claims: list[Claim]
    description: str = ""

    def by_id(self, claim_id: str) -> Claim:
        for claim in self.claims:
            if claim.id == claim_id:
                return claim
        raise StoreError(f"No claim with id {claim_id!r}")

    def usable(self, allow_soft: bool = False) -> list[Claim]:
        """Claims a document may draw on."""
        return [
            c
            for c in self.claims
            if not c.blocked and (allow_soft or not c.needs_decision)
        ]

    @property
    def held(self) -> list[Claim]:
        return [c for c in self.claims if c.blocked]


def load_store(path: str | Path) -> Store:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise StoreError(f"{path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict) or "claims" not in raw:
        raise StoreError(f"{path} has no 'claims' list")

    claims: list[Claim] = []
    seen: set[str] = set()

    for index, entry in enumerate(raw["claims"] or []):
        where = f"{path} claim #{index + 1}"
        for required in ("id", "text", "sensitivity"):
            if not entry.get(required):
                raise StoreError(f"{where} is missing '{required}'")

        claim_id = str(entry["id"])
        if claim_id in seen:
            raise StoreError(f"{where}: duplicate id {claim_id!r}")
        seen.add(claim_id)

        sensitivity = str(entry["sensitivity"]).upper()
        if sensitivity not in SENSITIVITIES:
            raise StoreError(
                f"{where}: sensitivity {sensitivity!r} is not one of {', '.join(SENSITIVITIES)}"
            )

        source = entry.get("source") or {}
        if not source.get("ref"):
            raise StoreError(
                f"{where} ({claim_id}) has no source.ref. "
                "A claim without a source is not a claim."
            )

        claims.append(
            Claim(
                id=claim_id,
                text=str(entry["text"]).strip(),
                sensitivity=sensitivity,
                source=source,
                themes=list(entry.get("themes") or []),
                also_expressed_as=[str(v) for v in (entry.get("also_expressed_as") or [])],
                keywords=[str(k) for k in (entry.get("keywords") or [])],
                note=str(entry.get("note") or "").strip(),
            )
        )

    if not claims:
        raise StoreError(f"{path} contains no claims")

    return Store(
        subject=str(raw.get("subject") or path.stem),
        description=str(raw.get("description") or "").strip(),
        claims=claims,
    )
