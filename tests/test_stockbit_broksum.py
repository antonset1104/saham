import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import Mock, patch

import update_data


class StockbitBrokerSummaryTest(unittest.TestCase):
    def test_running_update_keeps_existing_lock(self) -> None:
        with TemporaryDirectory() as directory:
            lock = Path(directory) / "sedang_update.lock"
            lock.write_text("already running", encoding="utf-8")
            with (
                patch.object(update_data, "LOCK_FILE", str(lock)),
                patch.object(update_data, "parse_args", return_value=None),
            ):
                update_data.main()
            self.assertEqual(lock.read_text(encoding="utf-8"), "already running")

    def test_unauthorized_response_stops_later_requests(self) -> None:
        response = Mock(status_code=401)
        with (
            patch.object(update_data, "TOKEN_CURIAN", "test-token"),
            patch.object(update_data, "_stockbit_unauthorized", Event()),
            patch.object(update_data.requests, "get", return_value=response) as get,
        ):
            self.assertIn("HTTP 401", update_data.get_broksum_aman("BBCA"))
            self.assertIn("HTTP 401", update_data.get_broksum_aman("BBRI"))
            get.assert_called_once()

    def test_forbidden_response_does_not_stop_other_tickers(self) -> None:
        response = Mock(status_code=403)
        with (
            patch.object(update_data, "TOKEN_CURIAN", "test-token"),
            patch.object(update_data, "_stockbit_unauthorized", Event()),
            patch.object(update_data.requests, "get", return_value=response) as get,
        ):
            self.assertIn("HTTP 403", update_data.get_broksum_aman("BBCA"))
            self.assertIn("HTTP 403", update_data.get_broksum_aman("BBRI"))
            self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
