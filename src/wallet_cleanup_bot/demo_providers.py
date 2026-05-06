from __future__ import annotations

from .models import (
    ApprovalAction,
    ApprovalDecision,
    Asset,
    ExecutionResult,
    ExecutionStatus,
    Proposal,
    RouteQuote,
    TokenKind,
)


class DemoScanner:
    def scan_wallet(self, wallet: str, chains: list[str]) -> list[Asset]:
        return [
            Asset("Base", "AERO", "12.3", 4.50, TokenKind.ERC20, "0x-aero"),
            Asset("Linea", "ETH", "0.004", 12.40, TokenKind.NATIVE),
            Asset("zkSync", "ETH", "0.001", 2.80, TokenKind.NATIVE),
        ]


class EmptyScanner:
    def scan_wallet(self, wallet: str, chains: list[str]) -> list[Asset]:
        return []


class DemoFees:
    def estimate_fee_usd(self, asset: Asset) -> float:
        return 0.03 if asset.chain == "Base" else 0.15


class DemoRisk:
    def has_liquidity(self, asset: Asset) -> bool:
        return True

    def is_suspicious(self, asset: Asset) -> bool:
        return False


class DemoRouter:
    def quote(self, asset: Asset, target_chain: str, target_token: str) -> RouteQuote:
        route_type = "swap" if asset.chain == target_chain else "swap+bridge"
        fee = 0.03 if asset.chain == "Base" else 0.15
        return RouteQuote(
            from_chain=asset.chain,
            from_token=asset.token,
            to_chain=target_chain,
            to_token=target_token,
            route_type=route_type,
            expected_receive_usd=max(asset.value_usd - fee, 0),
            gas_usd=fee,
            slippage_pct=0.5,
        )


class DemoApprovals:
    def request_approval(self, proposal: Proposal) -> ApprovalDecision:
        return ApprovalDecision(proposal.id, ApprovalAction.SKIP)


class DemoExecutor:
    def execute(self, proposal: Proposal) -> ExecutionResult:
        return ExecutionResult(proposal.id, ExecutionStatus.CONFIRMED, ["0x-demo"])
