from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TokenKind(str, Enum):
    NATIVE = "native"
    ERC20 = "erc20"


class FilterReason(str, Enum):
    CANDIDATE = "candidate"
    PROTECTED_GAS_RESERVED = "protected_gas_reserved"
    BELOW_GAS_THRESHOLD = "below_gas_threshold"
    VALUE_BELOW_FEE = "value_below_fee"
    NO_LIQUIDITY = "no_liquidity"
    SUSPICIOUS_TOKEN = "suspicious_token"


class ApprovalAction(str, Enum):
    APPROVE = "approve"
    SKIP = "skip"
    BLACKLIST_TOKEN = "blacklist_token"
    CHANGE_THRESHOLD = "change_threshold"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    CONFIRMED = "confirmed"
    FAILED = "failed"


@dataclass(frozen=True)
class Asset:
    chain: str
    token: str
    balance: str
    value_usd: float
    kind: TokenKind
    token_address: str | None = None
    decimals: int = 18


@dataclass(frozen=True)
class NormalizedAsset:
    asset: Asset
    estimated_fee_usd: float
    has_liquidity: bool
    suspicious: bool


@dataclass(frozen=True)
class FilterDecision:
    normalized: NormalizedAsset
    reason: FilterReason
    executable: bool
    note: str = ""


@dataclass(frozen=True)
class RouteQuote:
    from_chain: str
    from_token: str
    to_chain: str
    to_token: str
    route_type: str
    expected_receive_usd: float
    gas_usd: float
    slippage_pct: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Proposal:
    id: str
    wallet: str
    decision: FilterDecision
    route: RouteQuote
    threshold_usd: float | None = None


@dataclass(frozen=True)
class ApprovalDecision:
    proposal_id: str
    action: ApprovalAction
    threshold_usd: float | None = None


@dataclass(frozen=True)
class ExecutionResult:
    proposal_id: str
    status: ExecutionStatus
    tx_hashes: list[str] = field(default_factory=list)
    error: str | None = None
