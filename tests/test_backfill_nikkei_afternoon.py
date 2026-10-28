import copy
import unittest
from decimal import Decimal

from backfill_nikkei_afternoon import (
    backfill,
    calculate_result,
    decode_official_csv,
    parse_daily_closes,
)


CSV_FIXTURE = """Date of Data,Close,Open,High,Low
2026/10/23,62693.16,62667.05,62786.89,61462.61
2026/10/26,62189.65,62449.96,62902.95,62094.34
2026/10/27,63268.37,62569.08,63684.69,62389.47
Notes: official daily values,,,,
"""


class NikkeiAfternoonBackfillTests(unittest.TestCase):
    def test_decode_official_csv_accepts_cp932_footer(self):
        raw = "Date of Data,Close\r\n2026/10/27,63268.37\r\n※注記\r\n".encode(
            "cp932"
        )
        self.assertIn("2026/10/27,63268.37", decode_official_csv(raw))

    def test_parse_daily_closes_ignores_footer_without_a_date(self):
        self.assertEqual(
            parse_daily_closes(CSV_FIXTURE),
            {
                "2026-10-23": Decimal("62693.16"),
                "2026-10-26": Decimal("62189.65"),
                "2026-10-27": Decimal("63268.37"),
            },
        )

    def test_calculate_result_handles_positive_and_negative_changes(self):
        self.assertEqual(
            calculate_result(Decimal("63268.37"), Decimal("62189.65")),
            ("83772", "837", "72"),
        )
        self.assertEqual(
            calculate_result(Decimal("62189.65"), Decimal("62693.16")),
            ("96551", "965", "51"),
        )

    def test_calculate_result_keeps_leading_zeroes(self):
        self.assertEqual(
            calculate_result(Decimal("62000.07"), Decimal("62000.00")),
            ("00707", "007", "07"),
        )

    def test_backfill_uses_previous_trading_day_and_preserves_other_data(self):
        original = {
            "nikkei_morning": [
                {"date": "2026-10-27", "main": "11111", "top3": "111", "bottom2": "11"}
            ],
            "nikkei_afternoon": [
                {
                    "date": "2026-10-27",
                    "time": "13:21",
                    "status": "out",
                    "main": "32964",
                    "top3": "329",
                    "bottom2": "64",
                },
                {
                    "date": "2026-10-26",
                    "time": "13:21",
                    "status": "out",
                    "main": "20907",
                    "top3": "209",
                    "bottom2": "07",
                },
            ],
            "government": [{"date": "2026-10-16", "main": "123456"}],
            "_meta": {"updated": ["nikkei_afternoon"]},
        }
        untouched = copy.deepcopy(original)

        updated, audit = backfill(original, parse_daily_closes(CSV_FIXTURE))

        self.assertEqual(original, untouched)
        self.assertEqual(updated["nikkei_morning"], original["nikkei_morning"])
        self.assertEqual(updated["government"], original["government"])
        self.assertEqual(updated["_meta"], original["_meta"])
        self.assertEqual(updated["nikkei_afternoon"][0], {
            "date": "2026-10-27", "time": "13:21", "status": "out",
            "main": "83772", "top3": "837", "bottom2": "72",
        })
        self.assertEqual(updated["nikkei_afternoon"][1], {
            "date": "2026-10-26", "time": "13:21", "status": "out",
            "main": "96551", "top3": "965", "bottom2": "51",
        })
        self.assertEqual(len(audit), 2)

    def test_backfill_rejects_missing_official_date_before_changing_data(self):
        original = {
            "nikkei_afternoon": [
                {"date": "2026-10-28", "main": "46427", "top3": "464", "bottom2": "27"}
            ]
        }
        untouched = copy.deepcopy(original)

        with self.assertRaisesRegex(ValueError, "2026-10-28"):
            backfill(original, parse_daily_closes(CSV_FIXTURE))

        self.assertEqual(original, untouched)

    def test_parse_daily_closes_rejects_bad_close_on_a_valid_date(self):
        bad_csv = "Date of Data,Close\n2026/10/27,not-a-number\n"
        with self.assertRaisesRegex(ValueError, "2026/10/27"):
            parse_daily_closes(bad_csv)

    def test_parse_daily_closes_rejects_conflicting_duplicate_dates(self):
        bad_csv = (
            "Date of Data,Close\n"
            "2026/10/27,63268.37\n"
            "2026/10/27,63268.38\n"
        )
        with self.assertRaisesRegex(ValueError, "duplicate.*2026-10-27"):
            parse_daily_closes(bad_csv)


if __name__ == "__main__":
    unittest.main()
