import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NikkeiScheduleTests(unittest.TestCase):
    def test_afternoon_display_time_is_market_close(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertRegex(
            html,
            r'id:"nikkei_afternoon"[^\n]+hour:13,minute:30',
        )

    def test_afternoon_fetch_starts_at_1335_bangkok_time(self):
        workflow = (
            ROOT / ".github" / "workflows" / "scrapingant-production.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("815 <= minute <= 1080", workflow)

    def test_github_scheduler_wakes_at_1335_bangkok_time(self):
        scheduler = (
            ROOT / ".github" / "workflows" / "scrapingant-scheduler.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("cron: '35 6 * * 1-5'", scheduler)

    def test_afternoon_date_correction_waits_for_market_close(self):
        scraper = (ROOT / "scrape_with_scrapingant.py").read_text(encoding="utf-8")
        function = re.search(
            r"def correct_nikkei_afternoon_draw_date\(.*?\n\n",
            scraper,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(function)
        self.assertIn("(13, 30)", function.group(0))


if __name__ == "__main__":
    unittest.main()
