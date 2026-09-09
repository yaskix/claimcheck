# claimcheck

A provenance gate for the numbers in AI-assisted marketing copy. Every figure in a document has to trace back to a claim a human sourced, or the document does not ship.

**Status: prototype.** It checks provenance rather than truth, and quantities rather than meaning. It is not a substitute for legal, regulatory or editorial review, and it is not trying to be.

## The problem this is built against

A language model rarely produces an obviously false number. It produces a plausible one, in a sentence that reads exactly like the true sentences around it. Nobody reviews copy by re-deriving every figure. They read for sense, and a wrong figure makes perfect sense.

In a regulated category that is expensive, which is why marketing at an asset manager, a medical device company or an industrial manufacturer already moves through legal review. Generative tools raise the volume going into that review without widening it. The question worth working on is what can be automated so the human review is spent on judgement rather than on checking whether a number is real.

## What it does

You keep a store of claims. One claim is one statement of fact, written once, with a source, a date and a sensitivity tag. Then two things become possible.

`check` reads a draft — written by a person, a model, or a person editing a model — and refuses it if any figure in it cannot be traced to a claim. It exits non-zero, so it can sit in a pre-commit hook or a publishing pipeline and block rather than comment.

`compose` builds a draft from claims you select, so the provenance exists before the prose does instead of being reconstructed afterwards.

```
$ python -m claimcheck check drafts/unsourced.md

Checked 5 figure(s) against the store.
Traced to 2 claim(s).

  ERROR   line 3: '7%' (7 %) comes from a SOFT claim; pass --allow-soft to record that decision  [TC-GROWTH-DACH]
           …ean markets and grew 7% in the DACH region last year. The TR-4…
  ERROR   line 6: draft uses language from a HOLD claim ('gross margin', 'margin on the TR-40')  [TC-MARGIN]
           …lling crankset line. Gross margin on the TR-40 held firm at 41.…
  ERROR   line 7: '41.3%' (41.3 %) is licensed only by a HOLD claim and must not be published  [TC-MARGIN]
           …e TR-40 held firm at 41.3%, comfortably ahead of the category.…
  ERROR   line 9: '6,000' (6000 count) traces to no claim in the store
           …certified more than 6,000 mechanics, and enquiries rose 23% in…
  ERROR   line 10: '23%' (23 %) traces to no claim in the store
           …, and enquiries rose 23% in the quarter following launch.…

FAIL — 5 error(s), 0 warning(s).
```

Four kinds of failure in one plausible paragraph. Two invented figures, one internal figure that should never have left the building, and one real figure whose use was a judgement nobody had made.

## Running it

```bash
pip install -r requirements.txt
python -m claimcheck list
python -m claimcheck check drafts/clean.md
python -m claimcheck check drafts/unsourced.md
python -m claimcheck compose --ids TC-REV-2025,TC-MARKETS --title "Company facts"
python -m unittest discover -s tests -t .
```

The example store describes Tallvik Components, a fictional Swedish maker of bicycle drivetrain components. The company does not exist and every figure in it is invented. It is there to show the shape of a claim.

## What a claim looks like

```yaml
- id: TC-GROWTH-DACH
  text: >
    Net sales in the DACH region grew 7% in 2025, on a regional base of
    SEK 210 million.
  sensitivity: SOFT
  themes: [financial, growth]
  source:
    kind: internal
    ref: Regional performance pack Q4 2025
    verified_on: 2026-01-22
  note: >
    The base is stated deliberately. A growth rate without a base is a claim
    rather than a result and gets discounted on sight.
```

Five sensitivity tags, and they are the part that carries the most weight:

| Tag | Meaning |
|---|---|
| `PUBLIC` | Externally verifiable. Annual report, certification register, press. |
| `OWN` | The author's own scope and work. Theirs to state. |
| `RESULT` | A performance number, self-reported, with no surviving document behind it. |
| `SOFT` | Real but internally sourced. State rounded, or judge per document. |
| `HOLD` | Never leaves the store. |

`HOLD` is the reason the store holds things it will not let you publish. A model asked to write a confident product page will reach for a margin figure if it can see one. Deleting the figure is not the answer, because a human reasoning about positioning needs it. Holding it where a person can read it and a document cannot is.

## Three decisions worth arguing about

**The claim's own sentence is the source of truth for its numbers.** Figures are extracted from the prose rather than declared in a parallel field, so a claim's wording and its arithmetic cannot drift apart. `also_expressed_as` covers alternate renderings of the same fact, and nothing else.

**Rounding is allowed, and the tolerance is a policy.** "Approximately SEK 0.81 billion" and "SEK 812 million" are one fact at two precisions. A gate that rejected the rounded form would push writers toward false precision, which is the opposite of the point. The default is one percent. Set it loose enough and you will launder drift; that dial belongs to whoever owns the risk, not to the tool.

**Exclusions are written into the document, where a reader can see them.** A provenance appendix cites page numbers and sample sizes that assert nothing. Rather than teaching the gate to guess which numbers are metadata, a region can be marked `<!-- claimcheck:ignore-start -->`. Anyone reviewing the file can see what was excluded and argue with it.

## What this does not do

The limits are the honest part, and several of them came from tests that failed while it was being built.

It has no idea whether a claim is true. It knows whether a human sourced one. A store full of confident nonsense passes every check, cheerfully.

It only checks quantities. "Market-leading", "trusted by professionals" and "best-in-class" go straight through. Qualitative claims are frequently the ones that attract regulatory attention, and this catches none of them.

Held language is matched as substrings. Paraphrase a restricted claim and it passes. The keyword list is a speed bump for a careless writer, not a control against a determined one.

It matches figures, not the subjects attached to them. If the store says customer satisfaction reached 84%, a draft claiming employee retention reached 84% passes. The gate answers "is this number licensed", not "is this number being used for what it was sourced for". That second question needs a human, and it is the one worth the human's time.

It reads numbers, not meaning. "Grew by roughly a third" is invisible to it. So is a bare number that follows an abbreviation: the guard that keeps `ISO 4210` and `TR-40` out of the results also drops `EU 27`. A figure carrying a unit is safe — `VAT 25%` is read correctly — and there is a test recording that trade-off so it stays deliberate.

Years are skipped unless you ask for them, because dates generate more false positives than any other quantity, and a wrong year is a different class of error from a wrong result.

Number formats are English. A German decimal comma will be read as a thousands separator and produce confident nonsense of its own.

None of these are hard to improve. They are listed because a gate whose limits are undocumented gets trusted past the point where it is trustworthy, and that is worse than no gate.

## Repo structure

```
claimcheck/
  numbers.py       finds quantities in text and compares them
  store.py         loads and validates a claim store
  validate.py      the gate: four checks, in order of seriousness
  compose.py       builds a document from selected claims
  cli.py           check / compose / list
claims/
  example-store.yaml   a fictional company, invented figures
drafts/
  clean.md         passes
  unsourced.md     fails, four ways
tests/             30 tests, run on every push
```

## Prior art

The idea is not new, and it is worth being precise about what is.

Pharmaceutical marketing has used claims libraries for years: a store of approved claims, each linked to its reference, from which promotional copy is assembled. Veeva sells this inside [PromoMats](https://www.veeva.com/products/veeva-promomats/claims-management/), and it exists because medical, legal and regulatory review had become the constraint on how fast a launch could move. If you work in pharma, none of this repository will surprise you.

Separately, there is a growing category of guardrail libraries for language models — NVIDIA's [NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails), [Guardrails AI](https://github.com/guardrails-ai/guardrails) — which sit around a model and constrain what it may output. They are more capable than this and solve a broader problem.

What I have not found between those two is a small, readable, boring thing: a claims-library discipline applied to AI-assisted copy, in categories that are regulated enough to need it and not large enough to buy a suite. Industrial manufacturing, asset and wealth management, medical devices, food and cosmetics all sit in that gap. This is an argument for the pattern, in a form small enough to read in an afternoon.

## Where this came from

I keep a sourced fact bank for my own writing — every claim tagged, nothing stated that I cannot point at. It started as a discipline and turned into a habit, and the habit turned out to generalise. This repository is the generalisation, with the private material stripped out and a fictional company put in its place.

I am a marketing operator rather than an engineer, and I have spent the last several years in industrial B2B rather than in AI. The vantage is deliberate. The people writing about what generative tools do to a marketing function are mostly not the people who have sat in the approval meeting.

`private/` is in `.gitignore` for the obvious reason.

## License

MIT. See [LICENSE](LICENSE).
