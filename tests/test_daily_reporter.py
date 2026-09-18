import unittest
from unittest.mock import Mock, patch

from app.tasks.daily_reporter import DailyReporter


class DailyReporterCardTests(unittest.TestCase):
    def setUp(self):
        self.notifier = Mock()
        self.config = {
            "indices": [
                {"name": "上证指数", "symbol_ref": "sh000001", "flag": "🇨🇳"},
            ],
            "holdings": [
                {"name": "南方中证A500ETF", "symbol_ref": "sz159352"},
                {"name": "黄金ETF", "symbol_ref": "sh518880"},
            ],
        }
        self.reporter = DailyReporter(self.config, self.notifier)

    @patch("app.tasks.daily_reporter.time.strftime", return_value="2026-09-18 17:07")
    @patch.object(DailyReporter, "_is_trading_day", return_value=True)
    def test_card_uses_dashboard_layout_and_sorted_rows(self, _is_trading_day, _strftime):
        prices = {
            "sh000001": (3911.87, 0.94),
            "sz159352": (1.25, 2.85),
            "sh518880": (4.2, 1.73),
        }
        history = {
            "sz159352": [-0.32, 2.72],
            "sh518880": [-0.21, 0.92],
        }
        self.reporter._get_price = Mock(side_effect=lambda symbol: prices[symbol])
        self.reporter._get_historical_changes = Mock(
            side_effect=lambda symbol: history[symbol]
        )

        self.reporter.run()

        self.notifier.send_card.assert_called_once()
        call = self.notifier.send_card.call_args.kwargs
        self.assertEqual(call["template"], "indigo")
        self.assertEqual(call["title"], "📊 收盘日报 (2026-09-18 17:07)")

        elements = call["elements"]
        self.assertEqual(elements[0]["tag"], "column_set")
        self.assertEqual(elements[0]["background_style"], "grey")
        self.assertIn("+0.94%", elements[0]["columns"][0]["elements"][0]["content"])
        self.assertEqual(elements[1], {"tag": "hr"})
        self.assertEqual(elements[2]["background_style"], "grey")

        # 排序后，涨幅更高的 A500 应排在黄金 ETF 前面。
        first_row = elements[4]
        second_row = elements[6]
        self.assertEqual(len(elements[2]["columns"]), 4)
        self.assertEqual(len(first_row["columns"]), 4)
        self.assertIn("南方中证A500ETF", first_row["columns"][0]["elements"][0]["content"])
        self.assertIn("黄金ETF", second_row["columns"][0]["elements"][0]["content"])
        current_change = first_row["columns"][1]["elements"][0]
        self.assertIn("+2.85%", current_change["content"])
        self.assertIn("**", current_change["content"])
        self.assertEqual(current_change["text_size"], "medium")
        self.assertEqual(
            first_row["columns"][2]["elements"][0]["text_size"], "normal"
        )
        self.assertEqual(first_row["columns"][0]["weight"], 5)
        self.assertEqual(first_row["columns"][0]["elements"][0]["text_size"], "small")
        self.assertIn("-0.32%", first_row["columns"][2]["elements"][0]["content"])
        self.assertIn("+2.72%", first_row["columns"][3]["elements"][0]["content"])

    def test_change_format_is_consistent(self):
        self.assertEqual(DailyReporter._format_change(2.8), "<font color='red'>+2.80%</font>")
        self.assertEqual(
            DailyReporter._format_change(-0.4),
            "<font color='green'>-0.40%</font>",
        )
        self.assertEqual(
            DailyReporter._format_change(None),
            "<font color='grey'>—</font>",
        )


if __name__ == "__main__":
    unittest.main()
