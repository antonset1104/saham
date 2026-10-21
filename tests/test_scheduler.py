import os
import unittest
from datetime import datetime
from unittest.mock import patch

import scheduler_per_jam


class SchedulerTest(unittest.TestCase):
    def test_status_probe_does_not_terminate_process(self):
        self.assertTrue(scheduler_per_jam._process_alive(os.getpid()))
        self.assertFalse(scheduler_per_jam._process_alive(99_999_999))

    def test_market_hours_use_jakarta_clock(self):
        with patch.object(scheduler_per_jam, "_now_wib", return_value=datetime(2026, 10, 14, 9, 5)):
            self.assertTrue(scheduler_per_jam.is_market_hours())
        with patch.object(scheduler_per_jam, "_now_wib", return_value=datetime(2026, 10, 14, 17, 45)):
            self.assertFalse(scheduler_per_jam.is_market_hours())

    def test_regular_market_session_boundaries(self):
        for clock, expected in [
            ((8, 59), False), ((9, 0), True), ((12, 0), True),
            ((12, 1), False), ((13, 29), False), ((13, 30), True),
            ((15, 49), True), ((15, 50), False), ((16, 5), False),
        ]:
            with self.subTest(clock=clock):
                self.assertEqual(scheduler_per_jam.is_market_hours(datetime(2026, 10, 14, *clock)), expected)
        for clock, expected in [
            ((11, 30), True), ((11, 31), False), ((13, 59), False),
            ((14, 0), True), ((15, 49), True), ((15, 50), False),
        ]:
            with self.subTest(friday=clock):
                self.assertEqual(scheduler_per_jam.is_market_hours(datetime(2026, 10, 16, *clock)), expected)

    def test_eod_trigger_runs_once_after_1745_wib(self):
        self.assertFalse(scheduler_per_jam._research_due(datetime(2026, 10, 14, 17, 44), None))
        self.assertTrue(scheduler_per_jam._research_due(datetime(2026, 10, 14, 17, 45), None))
        self.assertFalse(scheduler_per_jam._research_due(
            datetime(2026, 10, 14, 18, 0), datetime(2026, 10, 14, 17, 45)
        ))
        self.assertFalse(scheduler_per_jam._research_due(datetime(2026, 10, 17, 18, 0), None))


if __name__ == "__main__":
    unittest.main()
