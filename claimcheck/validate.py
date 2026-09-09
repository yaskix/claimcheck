"""The gate.

Given a draft — written by a person, a model, or a person editing a model —
and a claim store, decide whether the draft is allowed to ship.

Four checks, in descending order of seriousness:

1. HELD_LANGUAGE   A phrase belonging to a HOLD claim appears in the draft.
2. HELD_FIGURE     A figure only a HOLD claim licenses appears in the draft.
3. UNSOURCED       A figure appears that no claim licenses at all.
4. SOFT            A figure only a SOFT claim licenses appears, and no human
                   has said this document may use SOFT material.

The first two are the ones that matter. An unsourced figure is usually a
mistake; a held figure is a disclosure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .numbers import Quantity, extract, matches
from .store import Claim, Store

ERROR = "error"
WARNING = "warning"


@dataclass
class Finding:
    level: str
    code: str
    message: str
    line: int
    excerpt: str
    claim_id: str | None = None

    def render(self) -> str:
        tag = "ERROR  " if self.level == ERROR else "warning"
        source = f"  [{self.claim_id}]" if self.claim_id else ""
        return f"  {tag} line {self.line}: {self.message}{source}\n           …{self.excerpt}…"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    quantities: list[Quantity] = field(default_factory=list)
    used: list[Claim] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [
            f"Checked {len(self.quantities)} figure(s) against the store.",
            f"Traced to {len(self.used)} claim(s).",
        ]
        if self.findings:
            lines.append("")
            lines.extend(f.render() for f in self.findings)
        lines.append("")
        lines.append(
            "PASS — every figure traces to a sourced claim."
            if self.ok
            else f"FAIL — {len(self.errors)} error(s), {len(self.warnings)} warning(s)."
        )
        return "\n".join(lines)


IGNORE_START = "<!-- claimcheck:ignore-start -->"
IGNORE_END = "<!-- claimcheck:ignore-end -->"


def _mask_ignored(text: str) -> str:
    """Blank out regions the author has explicitly excluded, keeping offsets.

    Provenance appendices, source references and citation counts are metadata
    about the document rather than claims made by it. Rather than teach the
    gate to guess which is which, the exclusion is written into the document
    where a reader can see it.
    """
    out = text
    while True:
        start = out.find(IGNORE_START)
        if start == -1:
            return out
        end = out.find(IGNORE_END, start)
        stop = len(out) if end == -1 else end + len(IGNORE_END)
        blanked = "".join("\n" if ch == "\n" else " " for ch in out[start:stop])
        out = out[:start] + blanked + out[stop:]


def _locate(text: str, offset: int, width: int = 42) -> tuple[int, str]:
    line = text.count("\n", 0, offset) + 1
    start = max(0, offset - width // 2)
    excerpt = " ".join(text[start : offset + width].split())
    return line, excerpt


def check(
    draft: str,
    store: Store,
    allow_soft: bool = False,
    tolerance: float = 0.01,
    include_years: bool = False,
) -> Report:
    scanned = _mask_ignored(draft)
    report = Report(quantities=extract(scanned, include_years=include_years))
    used: dict[str, Claim] = {}
    lowered = scanned.lower()

    # 1. Held language. Checked against the whole draft, not per figure,
    #    because the risky part of a held claim is often the wording.
    for claim in store.held:
        hits = sorted(
            (position, keyword)
            for keyword, position in (
                (k, lowered.find(k.lower())) for k in claim.keywords
            )
            if position != -1
        )
        if not hits:
            continue

        # One finding per held claim, naming every phrase that matched. Three
        # separate errors for one restricted sentence reads as three problems
        # and is one, and a reviewer needs to see all the phrases anyway.
        position = hits[0][0]
        phrases = ", ".join(repr(keyword) for _, keyword in hits)
        line, excerpt = _locate(draft, position)
        report.findings.append(
            Finding(
                level=ERROR,
                code="HELD_LANGUAGE",
                message=f"draft uses language from a HOLD claim ({phrases})",
                line=line,
                excerpt=excerpt,
                claim_id=claim.id,
            )
        )

    permitted = store.usable(allow_soft=True)
    soft_only = {c.id for c in permitted if c.needs_decision}

    # 2-4. Every figure in the draft must trace to something.
    for quantity in report.quantities:
        line, excerpt = _locate(draft, quantity.start)

        match = next(
            (c for c in permitted if any(matches(quantity, q, tolerance) for q in c.quantities)),
            None,
        )

        # A figure is a leak only when nothing but a held claim licenses it.
        # Checking HOLD first looked safer and was wrong: a public figure that
        # happens to appear inside a restricted sentence would be flagged as a
        # disclosure, and a gate that cries wolf gets turned off.
        if match is None:
            held_match = next(
                (
                    c
                    for c in store.held
                    if any(matches(quantity, q, tolerance) for q in c.quantities)
                ),
                None,
            )
            if held_match is not None:
                report.findings.append(
                    Finding(
                        level=ERROR,
                        code="HELD_FIGURE",
                        message=(
                            f"{quantity} is licensed only by a HOLD claim "
                            "and must not be published"
                        ),
                        line=line,
                        excerpt=excerpt,
                        claim_id=held_match.id,
                    )
                )
                continue

        if match is None:
            report.findings.append(
                Finding(
                    level=ERROR,
                    code="UNSOURCED",
                    message=f"{quantity} traces to no claim in the store",
                    line=line,
                    excerpt=excerpt,
                )
            )
            continue

        used[match.id] = match

        if match.id in soft_only and not allow_soft:
            report.findings.append(
                Finding(
                    level=ERROR,
                    code="SOFT",
                    message=(
                        f"{quantity} comes from a SOFT claim; "
                        "pass --allow-soft to record that decision"
                    ),
                    line=line,
                    excerpt=excerpt,
                    claim_id=match.id,
                )
            )

    report.used = sorted(used.values(), key=lambda c: c.id)
    report.findings.sort(key=lambda f: (f.line, f.code))
    return report
