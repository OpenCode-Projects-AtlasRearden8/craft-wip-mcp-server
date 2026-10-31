"""Offline unit tests for craftlib math + storage. Run: python -m unittest discover -s tests -v"""

import datetime
import tempfile
import unittest
from pathlib import Path

import craftlib
from craftlib import CraftError, days_until, lead_time_nudge, progress_pct


class TestProgress(unittest.TestCase):
    def test_simple_pct(self):
        self.assertEqual(progress_pct(0, 10), 0)
        self.assertEqual(progress_pct(5, 10), 50)
        self.assertEqual(progress_pct(10, 10), 100)

    def test_rounding(self):
        self.assertEqual(progress_pct(2, 3), 67)
        self.assertEqual(progress_pct(1, 3), 33)

    def test_total_zero_is_complete_marker(self):
        # A project with no countable units counts as finished planning work.
        self.assertEqual(progress_pct(0, 0), 100)

    def test_negative_rejected(self):
        with self.assertRaises(CraftError):
            progress_pct(-1, 10)
        with self.assertRaises(CraftError):
            progress_pct(0, -10)

    def test_type_safety(self):
        for bad in ("5", 5.0, True, None):
            with self.assertRaises(CraftError):
                progress_pct(bad, 10)

    def test_done_above_total_is_rejected(self):
        with self.assertRaises(CraftError):
            progress_pct(11, 10)

    def test_negative_rejected(self):
        with self.assertRaises(CraftError):
            progress_pct(-1, 10)
        with self.assertRaises(CraftError):
            progress_pct(0, -10)

    def test_type_safety(self):
        for bad in ("5", 5.0, True, None):
            with self.assertRaises(CraftError):
                progress_pct(bad, 10)

    def test_rank_prefers_nearly_done_unblocked(self):
        wip_a = {"id": "w-a", "name": "A", "total_units": 10, "done_units": 9, "needs": [], "deadlines": []}
        wip_b = {"id": "w-b", "name": "B", "total_units": 10, "done_units": 1, "needs": [], "deadlines": []}
        ranked = craftlib.rank_wips([wip_b, wip_a], [], datetime.date(2026, 10, 31))
        self.assertEqual(ranked[0]["name"], "A")
        self.assertEqual(ranked[0]["progress_pct"], 90)

    def test_missing_material_bumps_blocked_item_down(self):
        covered = {
            "id": "w-1", "name": "Covered",
            "total_units": 10, "done_units": 9,
            "needs": [],  # all supplies already staged at the chair
            "deadlines": [],
        }
        blocked = {
            "id": "w-2", "name": "Blocked",
            "total_units": 10, "done_units": 9,
            "needs": [{"name": "yarn", "per_unit": 5}],  # 5 units still missing
            "deadlines": [],
        }
        ranked = craftlib.rank_wips([blocked, covered], [], datetime.date(2026, 10, 31))
        self.assertEqual(ranked[0]["name"], "Covered")
        self.assertEqual(ranked[1]["name"], "Blocked")
        self.assertEqual(ranked[1]["missing_material_qty"], 5)


class TestDeadline(unittest.TestCase):
    def test_days_until_positive(self):
        self.assertEqual(
            days_until("2026-11-07", datetime.date(2026, 10, 31)), 7
        )

    def test_days_until_today(self):
        self.assertEqual(days_until("2026-10-31", datetime.date(2026, 10, 31)), 0)

    def test_days_until_negative_overdue(self):
        self.assertEqual(days_until("2026-10-20", datetime.date(2026, 10, 31)), -11)

    def test_dst_is_not_a_thing_for_dates(self):
        # Dates, not datetimes: month lengths must not trip us up.
        self.assertEqual(days_until("2026-11-30", datetime.date(2026, 10, 31)), 30)
        self.assertEqual(days_until("2027-01-01", datetime.date(2026, 12, 31)), 1)

    def test_leap_day(self):
        # Leap target via the real knower of days: date subtraction itself.
        target = datetime.date(2028, 2, 29)
        today = datetime.date(2026, 10, 31)
        self.assertEqual(days_until(target, today), (target - today).days)
        self.assertTrue((target - today).days > 0)

    def test_bad_date_rejected(self):
        for bad in ("not-a-date", "2031-13-01", "2031-02-30", "", "2026/10/31", 5, None):
            with self.assertRaises(CraftError):
                days_until(bad, datetime.date(2026, 10, 31))

    def test_nudge_bands(self):
        lead = 20
        self.assertEqual(lead_time_nudge(-1, lead), "overdue")
        self.assertEqual(lead_time_nudge(0, lead), "due today")
        self.assertEqual(lead_time_nudge(1, lead), "start now - critically close")
        self.assertIn("critically close", lead_time_nudge(5, lead))
        self.assertIn("nudge", lead_time_nudge(10, lead))
        self.assertEqual(lead_time_nudge(20, lead), "on track - reserve some time")
        self.assertEqual(lead_time_nudge(40, lead), "plenty of time")

    def test_nudge_short_lead_time_never_divides_by_zero(self):
        for days in (-3, 0, 1, 2, 7):
            out = lead_time_nudge(days, 1)
            self.assertTrue(out)

    def test_finish_first_honors_fake_today_seam(self):
        wip = {
            "id": "w-1", "name": "BDay scarf",
            "total_units": 10, "done_units": 10,
            "needs": [], "deadlines": [{"id": "d-1", "event_date": "2026-11-02", "lead_time_days": 14}],
        }
        ranked = craftlib.rank_wips([wip], [], datetime.date(2026, 11, 1))
        self.assertEqual(ranked[0]["days_to_deadline"], 1)
        self.assertEqual(ranked[0]["deadline_nudge"], "start now - critically close")


if __name__ == "__main__":
    unittest.main()
