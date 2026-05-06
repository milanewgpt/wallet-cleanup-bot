from __future__ import annotations

import unittest
from decimal import Decimal

from wallet_cleanup_bot.live_scanner import format_decimal


class LiveScannerTest(unittest.TestCase):
    def test_format_decimal_trims_noise(self) -> None:
        self.assertEqual(format_decimal(Decimal("1.230000")), "1.23")
        self.assertEqual(format_decimal(Decimal("1.000000")), "1")
        self.assertEqual(format_decimal(Decimal("0")), "0")


if __name__ == "__main__":
    unittest.main()

