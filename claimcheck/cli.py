"""Command line entry point.

    python -m claimcheck check drafts/clean.md
    python -m claimcheck check drafts/unsourced.md
    python -m claimcheck compose --ids HI-REV-2025,HI-MARKETS --title "Company facts"

`check` exits non-zero when the draft fails, so it can sit in a pre-commit
hook or a CI step and block a publish rather than merely commenting on it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .compose import compose
from .store import StoreError, load_store
from .validate import check

DEFAULT_STORE = "claims/example-store.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claimcheck",
        description="A provenance gate for AI-assisted marketing copy.",
    )
    parser.add_argument("--store", default=DEFAULT_STORE, help=f"claim store (default: {DEFAULT_STORE})")
    sub = parser.add_subparsers(dest="command", required=True)

    check_cmd = sub.add_parser("check", help="check a draft against the store")
    check_cmd.add_argument("draft", help="path to the draft, or - for stdin")
    check_cmd.add_argument(
        "--allow-soft",
        action="store_true",
        help="record a decision that this document may use SOFT claims",
    )
    check_cmd.add_argument(
        "--check-years", action="store_true", help="also check four-digit years"
    )
    check_cmd.add_argument(
        "--tolerance",
        type=float,
        default=0.01,
        help="relative rounding tolerance, default 0.01 (1%%)",
    )

    compose_cmd = sub.add_parser("compose", help="build a draft from selected claims")
    compose_cmd.add_argument("--ids", required=True, help="comma-separated claim ids")
    compose_cmd.add_argument("--title", default="Draft")
    compose_cmd.add_argument("--allow-soft", action="store_true")

    sub.add_parser("list", help="list the claims in the store")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        store = load_store(args.store)
    except (StoreError, OSError) as exc:
        print(f"Could not load store: {exc}", file=sys.stderr)
        return 2

    if args.command == "list":
        print(f"{store.subject} — {len(store.claims)} claims\n")
        for claim in store.claims:
            marker = "  BLOCKED" if claim.blocked else ("  soft" if claim.needs_decision else "")
            print(f"{claim.id:<22} {claim.sensitivity:<7}{marker}")
            print(f"  {claim.one_line()}\n")
        return 0

    if args.command == "compose":
        try:
            print(
                compose(
                    store,
                    [i.strip() for i in args.ids.split(",") if i.strip()],
                    title=args.title,
                    allow_soft=args.allow_soft,
                ),
                end="",
            )
        except StoreError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1
        return 0

    draft = sys.stdin.read() if args.draft == "-" else Path(args.draft).read_text(encoding="utf-8")
    report = check(
        draft,
        store,
        allow_soft=args.allow_soft,
        tolerance=args.tolerance,
        include_years=args.check_years,
    )
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
