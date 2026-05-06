from __future__ import annotations

from typing import Protocol

from .models import Asset, ApprovalDecision, ExecutionResult, Proposal, RouteQuote


class ScanProvider(Protocol):
    def scan_wallet(self, wallet: str, chains: list[str]) -> list[Asset]:
        """Return native and ERC-20 balances with USD value."""


class FeeEstimator(Protocol):
    def estimate_fee_usd(self, asset: Asset) -> float:
        """Estimate total gas cost for cleaning this asset."""


class TokenRiskProvider(Protocol):
    def has_liquidity(self, asset: Asset) -> bool:
        """Return whether the asset has enough liquidity for routing."""

    def is_suspicious(self, asset: Asset) -> bool:
        """Return whether the asset should not be touched."""


class RouteProvider(Protocol):
    def quote(self, asset: Asset, target_chain: str, target_token: str) -> RouteQuote:
        """Return swap/bridge/swap+bridge quote."""


class ApprovalGateway(Protocol):
    def request_approval(self, proposal: Proposal) -> ApprovalDecision:
        """Ask the user to approve, skip, blacklist, or change threshold."""


class ExecutionProvider(Protocol):
    def execute(self, proposal: Proposal) -> ExecutionResult:
        """Sign, send, and wait for confirmation for one approved proposal."""

