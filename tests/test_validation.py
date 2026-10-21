import math
from datetime import date

import pytest

from ringr_agents.validation import InvalidFieldError, parse_iso_date, parse_positive_amount, parse_text


class TestParseIsoDate:
    def test_valid_date(self):
        assert parse_iso_date("2026-11-05") == date(2026, 11, 5)

    def test_strips_surrounding_whitespace(self):
        assert parse_iso_date(" 2026-11-05 ") == date(2026, 11, 5)

    @pytest.mark.parametrize("value", ["2026/11/05", "05-11-2026", "20261105", "2026-02-30", "mañana", ""])
    def test_rejects_other_formats_and_impossible_dates(self, value):
        with pytest.raises(InvalidFieldError):
            parse_iso_date(value)

    @pytest.mark.parametrize("value", [20261105, date(2026, 11, 5), ["2026-11-05"]])
    def test_rejects_non_strings(self, value):
        with pytest.raises(InvalidFieldError):
            parse_iso_date(value)


class TestParsePositiveAmount:
    @pytest.mark.parametrize(("value", "expected"), [(150, 150.0), (150.5, 150.5), (99.999, 100.0), (0.01, 0.01)])
    def test_normalizes_to_float_with_cents(self, value, expected):
        assert parse_positive_amount(value) == expected

    @pytest.mark.parametrize("value", [0, -10, math.nan, math.inf])
    def test_rejects_non_positive_or_non_finite(self, value):
        with pytest.raises(InvalidFieldError):
            parse_positive_amount(value)

    @pytest.mark.parametrize("value", [True, "150", "150,50", [150]])
    def test_rejects_non_numbers_including_bool(self, value):
        with pytest.raises(InvalidFieldError):
            parse_positive_amount(value)


class TestParseText:
    def test_collapses_whitespace_and_newlines(self):
        assert parse_text("  Cambiar\r\n  la   tarifa ") == "Cambiar la tarifa"

    @pytest.mark.parametrize("value", ["", "   ", "\n\t"])
    def test_blank_text_is_no_value(self, value):
        assert parse_text(value) is None

    def test_rejects_non_strings(self):
        with pytest.raises(InvalidFieldError):
            parse_text(42)
