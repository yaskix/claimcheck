import tempfile
import unittest
from pathlib import Path

import yaml

from claimcheck.compose import compose
from claimcheck.store import StoreError, load_store
from claimcheck.validate import check

ROOT = Path(__file__).resolve().parents[1]
STORE = load_store(ROOT / "claims" / "example-store.yaml")


def codes(report):
    return {f.code for f in report.findings}


class TestCleanDraft(unittest.TestCase):
    def test_a_fully_sourced_draft_passes(self):
        draft = (ROOT / "drafts" / "clean.md").read_text()
        report = check(draft, STORE)
        self.assertTrue(report.ok, report.render())
        self.assertEqual(report.warnings, [])

    def test_it_records_which_claims_were_relied_on(self):
        draft = (ROOT / "drafts" / "clean.md").read_text()
        report = check(draft, STORE)
        self.assertIn("TC-REV-2025", {c.id for c in report.used})
        self.assertIn("TC-CSAT", {c.id for c in report.used})


class TestFailingDraft(unittest.TestCase):
    """This is the demonstration. A plausible draft, refused for four reasons."""

    def setUp(self):
        self.draft = (ROOT / "drafts" / "unsourced.md").read_text()
        self.report = check(self.draft, STORE)

    def test_the_draft_is_refused(self):
        self.assertFalse(self.report.ok)

    def test_an_invented_figure_is_caught(self):
        unsourced = [f for f in self.report.findings if f.code == "UNSOURCED"]
        found = {f.excerpt for f in unsourced}
        self.assertTrue(any("6,000" in e for e in found), found)
        self.assertTrue(any("23%" in e for e in found), found)

    def test_a_held_figure_cannot_leave_the_store(self):
        held = [f for f in self.report.findings if f.code == "HELD_FIGURE"]
        self.assertTrue(held)
        self.assertEqual(held[0].claim_id, "TC-MARGIN")

    def test_held_language_is_caught_even_without_the_number(self):
        text = "Gross margin held up well across the year."
        report = check(text, STORE)
        self.assertIn("HELD_LANGUAGE", codes(report))

    def test_one_held_claim_produces_one_finding_not_one_per_phrase(self):
        # The draft trips both keywords on TC-MARGIN. That is one problem.
        language = [f for f in self.report.findings if f.code == "HELD_LANGUAGE"]
        self.assertEqual(len(language), 1)
        self.assertEqual(language[0].claim_id, "TC-MARGIN")
        self.assertIn("gross margin", language[0].message)
        self.assertIn("margin on the TR-40", language[0].message)

    def test_soft_material_needs_an_explicit_decision(self):
        self.assertIn("SOFT", codes(self.report))
        permitted = check(self.draft, STORE, allow_soft=True)
        self.assertNotIn("SOFT", codes(permitted))
        # Allowing SOFT must not also unblock a HOLD claim.
        self.assertIn("HELD_FIGURE", codes(permitted))


class TestStoreIntegrity(unittest.TestCase):
    def _load(self, claims):
        # Not TestCase.enterContext — that arrived in Python 3.11, and this
        # package supports 3.10.
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "store.yaml"
        path.write_text(yaml.safe_dump({"subject": "T", "claims": claims}))
        return load_store(path)

    def test_a_claim_without_a_source_is_rejected(self):
        with self.assertRaises(StoreError):
            self._load([{"id": "A", "text": "Revenue was SEK 1 million.", "sensitivity": "PUBLIC"}])

    def test_duplicate_ids_are_rejected(self):
        entry = {
            "id": "A",
            "text": "Revenue was SEK 1 million.",
            "sensitivity": "PUBLIC",
            "source": {"ref": "x"},
        }
        with self.assertRaises(StoreError):
            self._load([entry, dict(entry)])

    def test_an_unknown_sensitivity_is_rejected(self):
        with self.assertRaises(StoreError):
            self._load(
                [
                    {
                        "id": "A",
                        "text": "Revenue was SEK 1 million.",
                        "sensitivity": "PROBABLY_FINE",
                        "source": {"ref": "x"},
                    }
                ]
            )


class TestCompose(unittest.TestCase):
    def test_it_refuses_to_compose_a_held_claim(self):
        with self.assertRaises(StoreError):
            compose(STORE, ["TC-MARGIN"])

    def test_it_refuses_soft_material_without_a_decision(self):
        with self.assertRaises(StoreError):
            compose(STORE, ["TC-GROWTH-DACH"])
        self.assertIn("7%", compose(STORE, ["TC-GROWTH-DACH"], allow_soft=True))

    def test_composed_output_passes_its_own_gate(self):
        text = compose(STORE, ["TC-REV-2025", "TC-MARKETS", "TC-CSAT"], title="Facts")
        self.assertTrue(check(text, STORE).ok, text)

    def test_it_warns_when_units_are_mixed(self):
        text = compose(STORE, ["TC-MECHANICS-2025", "TC-PARTNERS"])
        self.assertIn("assume one unit", text)


if __name__ == "__main__":
    unittest.main()
