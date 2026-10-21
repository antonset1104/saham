import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trading_pipeline import publish_json, report_has_current_eod


JAKARTA = ZoneInfo("Asia/Jakarta")


class TradingPipelineTest(unittest.TestCase):
    def test_backup_run_skips_only_complete_current_eod(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            report = {
                "generated_at": "2026-10-14T18:00:00+07:00",
                "results": {
                    str(horizon): {
                        "status": "no_edge", "data_asof": "2026-10-14",
                        "universe_coverage_pct": 100.0,
                    }
                    for horizon in (1, 5)
                },
            }
            publish_json(path, report)
            self.assertTrue(report_has_current_eod(
                path, datetime(2026, 10, 14, 18, 30, tzinfo=JAKARTA)
            ))
            self.assertFalse(report_has_current_eod(
                path, datetime(2026, 10, 15, 18, 30, tzinfo=JAKARTA)
            ))
            report["results"]["5"]["universe_coverage_pct"] = 85.0
            publish_json(path, report)
            self.assertFalse(report_has_current_eod(
                path, datetime(2026, 10, 14, 18, 30, tzinfo=JAKARTA)
            ))


if __name__ == "__main__":
    unittest.main()
