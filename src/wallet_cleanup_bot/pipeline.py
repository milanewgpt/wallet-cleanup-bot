from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1

from .config import CleanupConfig
from .logging_store import JsonlLogStore
from .models import (
    ApprovalAction,
    ApprovalDecision,
    Asset,
    ExecutionResult,
    ExecutionStatus,
    FilterDecision,
    FilterReason,
    NormalizedAsset,
    Proposal,
    TokenKind,
)
from .providers import ApprovalGateway, ExecutionProvider, FeeEstimator, RouteProvider, ScanProvider, TokenRiskProvider


@dataclass(frozen=True)
class CleanupPipeline:
    config: CleanupConfig
    scanner: ScanProvider
    fee_estimator: FeeEstimator
    risk_provider: TokenRiskProvider
    router: RouteProvider
    approvals: ApprovalGateway
    executor: ExecutionProvider
    log_store: JsonlLogStore

    def build_proposals(self, wallet: str) -> list[Proposal]:
        assets = self.scanner.scan_wallet(wallet, self.config.chains)
        self.log_store.append("scan.completed", assets)

        normalized = [self._normalize(asset) for asset in assets]
        self.log_store.append("normalize.completed", normalized)

        decisions = [self._filter(item) for item in normalized]
        self.log_store.append("filter.completed", decisions)

        proposals: list[Proposal] = []
        for decision in decisions:
            if not decision.executable:
                continue

            asset = decision.normalized.asset
            try:
                route = self.router.quote(asset, self.config.target_chain, self.config.target_token)
            except Exception as error:
                self.log_store.append("route.failed", {"asset": asset, "error": str(error)})
                continue
            threshold = self.config.threshold_for(asset.chain) if asset.kind == TokenKind.NATIVE else None
            proposal = Proposal(
                id=_proposal_id(wallet, asset),
                wallet=wallet,
                decision=decision,
                route=route,
                threshold_usd=threshold,
            )
            proposals.append(proposal)

        self.log_store.append("proposal.created", proposals)
        return proposals

    def approve_and_execute(self, proposals: list[Proposal]) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        for proposal in proposals:
            approval = self.approvals.request_approval(proposal)
            self.log_store.append("approval.received", approval)
            result = self.execute_approval(proposal, approval)
            self.log_store.append("execute.result", result)
            results.append(result)
        return results

    def execute_approval(self, proposal: Proposal, approval: ApprovalDecision) -> ExecutionResult:
        return self._handle_approval(proposal, approval)

    def _normalize(self, asset: Asset) -> NormalizedAsset:
        return NormalizedAsset(
            asset=asset,
            estimated_fee_usd=self.fee_estimator.estimate_fee_usd(asset),
            has_liquidity=self.risk_provider.has_liquidity(asset),
            suspicious=self.risk_provider.is_suspicious(asset),
        )

    def _filter(self, item: NormalizedAsset) -> FilterDecision:
        asset = item.asset
        threshold = self.config.threshold_for(asset.chain)
        protected_native = asset.kind == TokenKind.NATIVE and asset.chain in self.config.protected_gas_chains

        if protected_native and asset.value_usd < threshold:
            return FilterDecision(item, FilterReason.PROTECTED_GAS_RESERVED, False, "native gas reserve")

        if protected_native and asset.value_usd == threshold:
            return FilterDecision(item, FilterReason.BELOW_GAS_THRESHOLD, False, "at gas threshold")

        if asset.value_usd < item.estimated_fee_usd:
            return FilterDecision(item, FilterReason.VALUE_BELOW_FEE, False, "cleanup costs more than value")

        if not item.has_liquidity:
            return FilterDecision(item, FilterReason.NO_LIQUIDITY, False, "no route liquidity")

        if item.suspicious:
            return FilterDecision(item, FilterReason.SUSPICIOUS_TOKEN, False, "token risk filter")

        note = "clean excess" if protected_native else "cleanup candidate"
        return FilterDecision(item, FilterReason.CANDIDATE, True, note)

    def _handle_approval(self, proposal: Proposal, approval: ApprovalDecision) -> ExecutionResult:
        if approval.action == ApprovalAction.APPROVE:
            return self.executor.execute(proposal)
        if approval.action == ApprovalAction.CHANGE_THRESHOLD:
            return ExecutionResult(proposal.id, ExecutionStatus.PENDING, error="threshold change requires rebuild")
        return ExecutionResult(proposal.id, ExecutionStatus.PENDING)


def _proposal_id(wallet: str, asset: Asset) -> str:
    key = f"{wallet}:{asset.chain}:{asset.token}:{asset.token_address or ''}:{asset.balance}"
    return sha1(key.encode("utf-8")).hexdigest()[:12]
