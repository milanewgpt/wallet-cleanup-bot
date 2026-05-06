from __future__ import annotations

import tempfile
import unittest

from wallet_cleanup_bot.config import CleanupConfig
from wallet_cleanup_bot.logging_store import JsonlLogStore
from wallet_cleanup_bot.models import (
    ApprovalAction,
    ApprovalDecision,
    Asset,
    ExecutionResult,
    ExecutionStatus,
    RouteQuote,
    TokenKind,
)
from wallet_cleanup_bot.pipeline import CleanupPipeline


class Scanner:
    def __init__(self, assets: list[Asset]) -> None:
        self.assets = assets

    def scan_wallet(self, wallet: str, chains: list[str]) -> list[Asset]:
        return self.assets


class Fees:
    def estimate_fee_usd(self, asset: Asset) -> float:
        return 0.50


class Risk:
    def __init__(self, liquidity: bool = True, suspicious: bool = False) -> None:
        self.liquidity = liquidity
        self.suspicious = suspicious

    def has_liquidity(self, asset: Asset) -> bool:
        return self.liquidity

    def is_suspicious(self, asset: Asset) -> bool:
        return self.suspicious


class Router:
    def quote(self, asset: Asset, target_chain: str, target_token: str) -> RouteQuote:
        return RouteQuote(asset.chain, asset.token, target_chain, target_token, "swap", asset.value_usd - 0.50, 0.50, 0.5)


class Approvals:
    def request_approval(self, proposal):
        return ApprovalDecision(proposal.id, ApprovalAction.APPROVE)


class Executor:
    def execute(self, proposal):
        return ExecutionResult(proposal.id, ExecutionStatus.CONFIRMED, ["0xhash"])


class PipelineTest(unittest.TestCase):
    def test_protected_native_below_threshold_is_not_proposed(self) -> None:
        pipeline = make_pipeline([Asset("Base", "ETH", "0.001", 3.0, TokenKind.NATIVE)])
        self.assertEqual(pipeline.build_proposals("0xwallet"), [])

    def test_protected_native_above_threshold_is_proposed(self) -> None:
        pipeline = make_pipeline([Asset("Base", "ETH", "0.01", 20.0, TokenKind.NATIVE)])
        proposals = pipeline.build_proposals("0xwallet")
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].threshold_usd, 10.0)

    def test_erc20_on_protected_chain_is_proposed(self) -> None:
        pipeline = make_pipeline([Asset("Base", "AERO", "12", 4.5, TokenKind.ERC20, "0x-aero")])
        self.assertEqual(len(pipeline.build_proposals("0xwallet")), 1)

    def test_value_below_fee_is_skipped(self) -> None:
        pipeline = make_pipeline([Asset("Polygon", "MATIC", "0.1", 0.20, TokenKind.NATIVE)])
        self.assertEqual(pipeline.build_proposals("0xwallet"), [])

    def test_approved_proposal_executes(self) -> None:
        pipeline = make_pipeline([Asset("Polygon", "MATIC", "10", 5.0, TokenKind.NATIVE)])
        proposals = pipeline.build_proposals("0xwallet")
        results = pipeline.approve_and_execute(proposals)
        self.assertEqual(results[0].status, ExecutionStatus.CONFIRMED)
        self.assertEqual(results[0].tx_hashes, ["0xhash"])


def make_pipeline(assets: list[Asset]) -> CleanupPipeline:
    config = CleanupConfig(
        chains=["Base", "Polygon"],
        protected_gas_chains={"Base"},
        target_chain="Base",
        target_token="USDC",
        default_gas_threshold_usd=10.0,
    )
    log_file = tempfile.NamedTemporaryFile(delete=True)
    return CleanupPipeline(
        config=config,
        scanner=Scanner(assets),
        fee_estimator=Fees(),
        risk_provider=Risk(),
        router=Router(),
        approvals=Approvals(),
        executor=Executor(),
        log_store=JsonlLogStore(log_file.name),
    )


if __name__ == "__main__":
    unittest.main()

