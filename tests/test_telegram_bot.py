from __future__ import annotations

import unittest

from wallet_cleanup_bot.models import Asset, TokenKind
from wallet_cleanup_bot.scan_store import ScanItem
from wallet_cleanup_bot.telegram_bot import (
    _looks_like_private_key,
    execute_url,
    format_balance_scan,
    format_scan_item,
    format_withdraw_ready,
    import_url,
)


class TelegramBotTest(unittest.TestCase):
    def test_private_key_shape_is_detected(self) -> None:
        self.assertTrue(_looks_like_private_key("0x" + "a" * 64))
        self.assertTrue(_looks_like_private_key("b" * 64))

    def test_address_is_not_private_key_shape(self) -> None:
        self.assertFalse(_looks_like_private_key("0x" + "1" * 40))

    def test_import_url_encodes_label_and_token(self) -> None:
        url = import_url("https://example.com/", "main wallet", "secret token")
        self.assertEqual(url, "https://example.com/import?label=main+wallet&token=secret+token")

    def test_execute_url_encodes_id_and_token(self) -> None:
        url = execute_url("https://example.com/", "abc 123", "secret token")
        self.assertEqual(url, "https://example.com/execute?id=abc+123&token=secret+token")

    def test_format_balance_scan(self) -> None:
        text = format_balance_scan(
            "0xwallet",
            [Asset("BNB", "BNB", "0.1", 60.0, TokenKind.NATIVE)],
        )
        self.assertIn("BNB: <code>0.1</code> BNB ($60.00)", text)
        self.assertIn("Total value: $60.00", text)

    def test_format_scan_item(self) -> None:
        item = ScanItem("abc", "0xwallet", Asset("Base", "USDC", "2", 2.0, TokenKind.ERC20, "0xToken", 6))
        text = format_scan_item(item)
        self.assertIn("USDC (Base)", text)
        self.assertIn("ID: <code>abc</code>", text)

    def test_format_withdraw_ready(self) -> None:
        item = ScanItem("abc", "0xwallet", Asset("Base", "USDC", "2", 2.0, TokenKind.ERC20, "0xToken", 6))
        text = format_withdraw_ready(item, "0x0000000000000000000000000000000000000001")
        self.assertIn("Withdraw prepared", text)
        self.assertIn("To: <code>0x0000000000000000000000000000000000000001</code>", text)


if __name__ == "__main__":
    unittest.main()
