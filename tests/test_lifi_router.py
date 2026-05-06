from __future__ import annotations

import unittest

from wallet_cleanup_bot.lifi_router import amount_to_units, route_targets_for, token_for_lifi
from wallet_cleanup_bot.models import Asset, TokenKind


class LifiRouterTest(unittest.TestCase):
    def test_amount_to_units(self) -> None:
        self.assertEqual(amount_to_units("2.939694", 6), "2939694")
        self.assertEqual(amount_to_units("0.001", 18), "1000000000000000")

    def test_token_for_lifi_uses_erc20_address(self) -> None:
        asset = Asset("Base", "USDC", "1", 1.0, TokenKind.ERC20, "0xToken", 6)
        self.assertEqual(token_for_lifi(asset), "0xToken")

    def test_basic_chain_routes_inside_same_chain(self) -> None:
        asset = Asset("BNB", "BWLD", "1", 1.0, TokenKind.ERC20, "0xToken", 18)
        self.assertEqual(
            route_targets_for(asset, "Base", "USDC"),
            [("BNB", "USDC"), ("BNB", "USDT"), ("BNB", "BNB")],
        )

    def test_non_basic_chain_routes_to_base_usdc(self) -> None:
        asset = Asset("Linea", "TOKEN", "1", 1.0, TokenKind.ERC20, "0xToken", 18)
        self.assertEqual(route_targets_for(asset, "Base", "USDC"), [("Base", "USDC")])


if __name__ == "__main__":
    unittest.main()
