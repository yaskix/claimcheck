"""Build a document that can only say what the store can support.

The validator catches what a writer got wrong. This is the other half: a
document assembled *from* claims, so the provenance exists before the prose
does rather than being reconstructed afterwards.

It deliberately does not call a language model. What a model adds is fluency,
and fluency is exactly what makes an unsourced figure hard to spot. The
useful order is: select the claims, then let a model phrase them, then run
the result back through `check`.
"""

from __future__ import annotations

from .store import Claim, Store, StoreError
from .validate import IGNORE_END, IGNORE_START


def compose(
    store: Store,
    claim_ids: list[str],
    title: str = "Draft",
    allow_soft: bool = False,
) -> str:
    selected: list[Claim] = []
    for claim_id in claim_ids:
        claim = store.by_id(claim_id)
        if claim.blocked:
            raise StoreError(
                f"{claim.id} is tagged {claim.sensitivity} and cannot be composed into a document."
            )
        if claim.needs_decision and not allow_soft:
            raise StoreError(
                f"{claim.id} is tagged SOFT. Pass allow_soft=True to record that decision."
            )
        selected.append(claim)

    body = [f"# {title}", ""]
    body.extend(f"{claim.one_line()}" for claim in selected)

    # The appendix describes the document rather than asserting anything, so it
    # is marked as out of scope for the gate — visibly, in the document itself.
    body.extend(["", "---", "", IGNORE_START, "", "## Provenance", ""])
    for claim in selected:
        source = claim.source
        ref = source.get("ref", "unknown")
        verified = source.get("verified_on", "not recorded")
        body.append(f"- **{claim.id}** ({claim.sensitivity}) — {ref}. Verified {verified}.")
    body.extend(["", IGNORE_END])

    unit_note = _unit_warning(selected)
    if unit_note:
        body.extend(["", f"> {unit_note}"])

    return "\n".join(body) + "\n"


def _unit_warning(claims: list[Claim]) -> str:
    """Catch the mixed-unit trap: counting organisations and individuals together.

    Not a validation rule, because it is a judgement about the reader rather
    than a fact about the store. A note is the right weight for it.
    """
    notes = [c for c in claims if "individual" in c.text.lower()]
    orgs = [c for c in claims if "organisation" in c.text.lower()]
    if notes and orgs:
        return (
            "This document states a count of individuals and a count of organisations. "
            "Say which is which, or the reader will assume one unit and conclude that "
            "one of the numbers is wrong."
        )
    return ""
