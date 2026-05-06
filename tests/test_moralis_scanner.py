from __future__ import annotations

import unittest

from wallet_cleanup_bot.models import Asset, TokenKind
from wallet_cleanup_bot.moralis_scanner import CompositeScanner


class Scanner:
    def __init__(self, assets: list[Asset]) -> None:
        self.assets = assets

    def scan_wallet(self, wallet: str, chains: list[str]) -> list[Asset]:
        return self.assets


class MoralisScannerTest(unittest.TestCase):
    def test_composite_scanner_deduplicates_assets(self) -> None:
        asset = Asset("BNB", "USDT", "1", 1.0, TokenKind.ERC20, "0xToken")
        scanner = CompositeScanner([Scanner([asset]), Scanner([asset])])
        self.assertEqual(scanner.scan_wallet("0xwallet", ["BNB"]), [asset])


if __name__ == "__main__":
    unittest.main()

