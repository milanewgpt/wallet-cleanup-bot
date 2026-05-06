from __future__ import annotations

import unittest

from wallet_cleanup_bot.models import (
    Asset,
    FilterDecision,
    FilterReason,
    NormalizedAsset,
    Proposal,
    RouteQuote,
    TokenKind,
)
from wallet_cleanup_bot.telegram_gateway import format_proposal_message, proposal_keyboard


class TelegramGatewayTest(unittest.TestCase):
    def test_keyboard_uses_per_proposal_callbacks(self) -> None:
        keyboard = proposal_keyboard("abc123")
        callbacks = [
            button["callback_data"]
            for row in keyboard["inline_keyboard"]
            for button in row
        ]
        self.assertEqual(
            callbacks,
            [
                "wc:abc123:approve",
                "wc:abc123:skip",
                "wc:abc123:blacklist_token",
                "wc:abc123:change_threshold",
            ],
        )

    def test_message_contains_route_and_threshold(self) -> None:
        proposal = Proposal(
            id="p1",
            wallet="0xwallet",
            decision=FilterDecision(
                normalized=NormalizedAsset(
                    asset=Asset("Linea", "ETH", "0.004", 12.40, TokenKind.NATIVE),
                    estimated_fee_usd=0.15,
                    has_liquidity=True,
                    suspicious=False,
                ),
                reason=FilterReason.CANDIDATE,
                executable=True,
                note="clean excess",
            ),
            route=RouteQuote("Linea", "ETH", "Base", "USDC", "swap+bridge", 12.25, 0.15, 0.5),
            threshold_usd=10,
        )

        message = format_proposal_message(proposal)
        self.assertIn("Linea", message)
        self.assertIn("ETH (Linea) -> USDC (Base)", message)
        self.assertIn("Threshold: $10.00", message)


if __name__ == "__main__":
    unittest.main()
