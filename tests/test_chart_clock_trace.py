import unittest

from tools.analyze_chart_clock_trace import read_trace, summarize


class ChartClockTraceTests(unittest.TestCase):
    def test_only_post_start_updates_count(self):
        rows = read_trace("host=0 phase=2 object=ABC clock=900 started=0\n"
                          "host=1 phase=0 object=ABC clock=0 started=0\n"
                          "host=2 phase=1 object=ABC clock=0 started=1\n"
                          "host=3 phase=2 object=ABC clock=1 started=1\n"
                          "host=13 phase=2 object=ABC clock=11 started=1\n")
        report, = summarize(rows)
        self.assertEqual(report["status"], "advancing")
        self.assertEqual(report["updates"], 2)
        self.assertEqual(report["clock_advance"], 10)

    def test_stall_and_short_capture_are_distinct(self):
        rows = read_trace("host=0 phase=2 object=A clock=4 started=1\n"
                          "host=10 phase=2 object=A clock=4 started=1\n"
                          "host=10 phase=2 object=B clock=4 started=1\n")
        first, second = summarize(rows)
        self.assertEqual(first["status"], "stalled")
        self.assertEqual(second["status"], "insufficient_observation")

    def test_missing_clock_rejected(self):
        with self.assertRaises(ValueError):
            read_trace("host=0 phase=2 object=A started=1")


if __name__ == "__main__":
    unittest.main()
