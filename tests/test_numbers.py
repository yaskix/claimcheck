import unittest

from claimcheck.numbers import UNIT_COUNT, UNIT_PERCENT, UNIT_POINTS, Quantity, extract, matches


def one(text):
    found = extract(text)
    assert len(found) == 1, f"expected one quantity in {text!r}, got {found}"
    return found[0]


class TestExtraction(unittest.TestCase):
    def test_currency_forms_normalise_to_the_same_magnitude(self):
        for text in ("SEK 812 million", "812 MSEK", "812 million SEK"):
            with self.subTest(text=text):
                q = one(text)
                self.assertEqual(q.unit, "SEK")
                self.assertEqual(q.value, 812_000_000)

    def test_thousands_separators(self):
        self.assertEqual(one("4,200 mechanics").value, 4200)
        self.assertEqual(one("18 000 plumbers").value, 18000)

    def test_percent_and_points_are_different_units(self):
        self.assertEqual(one("7%").unit, UNIT_PERCENT)
        self.assertEqual(one("2 percentage points").unit, UNIT_POINTS)
        self.assertEqual(one("7 per cent").unit, UNIT_PERCENT)

    def test_years_are_skipped_by_default(self):
        self.assertEqual(extract("in 2025"), [])
        self.assertEqual(len(extract("in 2025", include_years=True)), 1)

    def test_bare_counts(self):
        q = one("14 European markets")
        self.assertEqual((q.value, q.unit), (14, UNIT_COUNT))

    def test_scaled_count_without_currency(self):
        self.assertEqual(one("1.2 million users").value, 1_200_000)


class TestIdentifiers(unittest.TestCase):
    """A number bound to a name is not a measurement. A unit says it is."""

    def test_product_codes_and_standards_are_not_quantities(self):
        for text in ("the TR-40 crankset", "IP68 rated", "ISO 4210", "EN 14781"):
            with self.subTest(text=text):
                self.assertEqual(extract(text), [])

    def test_a_unit_beats_the_identifier_guard(self):
        # Dropping these was a fail-open bug: the gate reported a pass on a
        # document it had not fully read.
        self.assertEqual(one("VAT 25%").value, 25)
        self.assertEqual(one("CAGR 14% over the period").value, 14)
        self.assertEqual(one("VAT SEK 40 million").unit, "SEK")

    def test_a_quarter_label_does_not_glue_onto_the_year(self):
        # "Q4 2025" once parsed as "4 202" plus a stray 5.
        found = extract("Q4 2025 revenue of SEK 12 million")
        self.assertEqual([(q.value, q.unit) for q in found], [(12_000_000, "SEK")])

    def test_a_decimal_is_not_matched_twice(self):
        self.assertEqual(len(extract("margin of 41.3%")), 1)

    def test_known_limitation_bare_count_after_an_abbreviation(self):
        # Documented, not fixed: keeping "ISO 4210" out costs us "EU 27".
        # The test exists so the trade-off is visible and deliberate.
        self.assertEqual(extract("EU 27 markets"), [])


class TestMatching(unittest.TestCase):
    def test_rounding_within_tolerance_matches(self):
        precise = one("SEK 812 million")
        rounded = one("SEK 0.81 billion")
        self.assertTrue(matches(precise, rounded))

    def test_drift_outside_tolerance_does_not_match(self):
        self.assertFalse(matches(one("SEK 812 million"), one("SEK 900 million")))

    def test_units_must_agree(self):
        self.assertFalse(matches(one("7%"), one("7 percentage points")))
        self.assertFalse(matches(one("812 MSEK"), one("812 MEUR")))

    def test_bare_count_does_not_satisfy_a_percentage(self):
        self.assertFalse(matches(Quantity(84, UNIT_COUNT, "84", 0, 2), one("84%")))


if __name__ == "__main__":
    unittest.main()
