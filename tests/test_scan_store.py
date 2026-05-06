from __future__ import annotations

import unittest

from wallet_cleanup_bot.models import Asset, TokenKind
from wallet_cleanup_bot.scan_store import ScanStore


class ScanStoreTest(unittest.TestCase):
    def test_put_and_get_assets(self) -> None:
        store = ScanStore()
        asset = Asset("Base", "USDC", "2", 2.0, TokenKind.ERC20, "0xToken", 6)
        items = store.put_assets("0xwallet", [asset])

        self.assertEqual(store.get(items[0].id), items[0])


if __name__ == "__main__":
    unittest.main()

