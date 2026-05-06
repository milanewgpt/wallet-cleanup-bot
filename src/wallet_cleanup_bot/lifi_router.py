from __future__ import annotations

import json
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_DOWN
from typing import Any

from .models import Asset, RouteQuote, TokenKind


CHAIN_ID_BY_NAME = {
    "Ethereum": 1,
    "Base": 8453,
    "Arbitrum": 42161,
    "Optimism": 10,
    "Polygon": 137,
    "BNB": 56,
    "Avalanche": 43114,
    "Linea": 59144,
    "zkSync": 324,
}

BASIC_CHAINS = {"Ethereum", "BNB", "Polygon", "Base", "Arbitrum", "Avalanche", "Optimism"}

GAS_TOKEN_BY_CHAIN = {
    "Ethereum": "ETH",
    "Base": "ETH",
    "Arbitrum": "ETH",
    "Optimism": "ETH",
    "Polygon": "POL",
    "BNB": "BNB",
    "Avalanche": "AVAX",
}

RPC_URL_BY_CHAIN_ID = {
    1: "https://ethereum-rpc.publicnode.com",
    8453: "https://base-rpc.publicnode.com",
    42161: "https://arbitrum-one-rpc.publicnode.com",
    10: "https://optimism-rpc.publicnode.com",
    137: "https://polygon-bor-rpc.publicnode.com",
    56: "https://bsc-rpc.publicnode.com",
    43114: "https://avalanche-c-chain-rpc.publicnode.com",
    59144: "https://linea-rpc.publicnode.com",
    324: "https://zksync-era-rpc.publicnode.com",
}


TARGET_TOKEN_BY_CHAIN = {
    ("Ethereum", "USDC"): "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    ("Ethereum", "USDT"): "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    ("Base", "USDC"): "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    ("Base", "USDT"): "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
    ("Arbitrum", "USDC"): "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    ("Arbitrum", "USDT"): "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
    ("Optimism", "USDC"): "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
    ("Optimism", "USDT"): "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58",
    ("Polygon", "USDC"): "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
    ("Polygon", "USDT"): "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
    ("BNB", "USDC"): "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
    ("BNB", "USDT"): "0x55d398326f99059fF775485246999027B3197955",
    ("Avalanche", "USDC"): "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
    ("Avalanche", "USDT"): "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",
}


class LifiRouteProvider:
    def __init__(self, from_address: str, api_key: str | None = None, slippage: float = 0.03) -> None:
        self.from_address = from_address
        self.api_key = api_key
        self.slippage = slippage

    def quote(self, asset: Asset, target_chain: str, target_token: str) -> RouteQuote:
        payload, resolved_target_chain, resolved_target_token = self._best_quote(asset, target_chain, target_token)
        estimate = payload.get("estimate", {})
        gas_usd = sum(float(item.get("amountUSD") or 0.0) for item in estimate.get("gasCosts", []))
        expected_receive_usd = float(estimate.get("toAmountUSD") or 0.0)
        return RouteQuote(
            from_chain=asset.chain,
            from_token=asset.token,
            to_chain=resolved_target_chain,
            to_token=resolved_target_token,
            route_type=str(payload.get("tool") or payload.get("type") or "lifi"),
            expected_receive_usd=expected_receive_usd,
            gas_usd=gas_usd,
            slippage_pct=self.slippage * 100,
            raw=payload,
        )

    def _best_quote(self, asset: Asset, fallback_chain: str, fallback_token: str) -> tuple[dict[str, Any], str, str]:
        candidates = route_targets_for(asset, fallback_chain, fallback_token)
        quotes: list[tuple[dict[str, Any], str, str]] = []
        for target_chain, target_token in candidates:
            try:
                quotes.append((self._quote_to(asset, target_chain, target_token), target_chain, target_token))
            except Exception:
                continue
        if not quotes:
            raise ValueError("no LI.FI route")
        return max(quotes, key=lambda item: float(item[0].get("estimate", {}).get("toAmountUSD") or 0.0))

    def _quote_to(self, asset: Asset, target_chain: str, target_token: str) -> dict[str, Any]:
        from_chain_id = CHAIN_ID_BY_NAME[asset.chain]
        to_chain_id = CHAIN_ID_BY_NAME[target_chain]
        from_token = token_for_lifi(asset)
        to_token = token_address_for_target(target_chain, target_token)
        from_amount = amount_to_units(asset.balance, asset.decimals)
        if int(from_amount) <= 0:
            raise ValueError("zero amount")
        return self._get_quote(
            {
                "fromChain": str(from_chain_id),
                "toChain": str(to_chain_id),
                "fromToken": from_token,
                "toToken": to_token,
                "fromAddress": self.from_address,
                "toAddress": self.from_address,
                "fromAmount": from_amount,
                "slippage": str(self.slippage),
                "integrator": "wallet-cleanup-bot",
            }
        )

    def _get_quote(self, query: dict[str, str]) -> dict[str, Any]:
        url = f"https://li.quest/v1/quote?{urllib.parse.urlencode(query)}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "wallet-cleanup-bot/0.1",
        }
        if self.api_key:
            headers["x-lifi-api-key"] = self.api_key
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class DisabledExecutionProvider:
    def execute(self, proposal: Any) -> Any:
        from .models import ExecutionResult, ExecutionStatus

        return ExecutionResult(
            proposal.id,
            ExecutionStatus.PENDING,
            error="execution disabled: signer and transaction sender are not connected yet",
        )


def token_for_lifi(asset: Asset) -> str:
    if asset.kind == TokenKind.ERC20 and asset.token_address:
        return asset.token_address
    return asset.token


def token_address_for_target(chain: str, token: str) -> str:
    if token in GAS_TOKEN_BY_CHAIN.values() and GAS_TOKEN_BY_CHAIN.get(chain) == token:
        return token
    return TARGET_TOKEN_BY_CHAIN.get((chain, token), token)


def route_targets_for(asset: Asset, fallback_chain: str, fallback_token: str) -> list[tuple[str, str]]:
    if asset.chain in BASIC_CHAINS:
        candidates = [(asset.chain, "USDC"), (asset.chain, "USDT")]
        gas_token = GAS_TOKEN_BY_CHAIN.get(asset.chain)
        if gas_token and asset.token != gas_token:
            candidates.append((asset.chain, gas_token))
        return candidates
    return [(fallback_chain, fallback_token)]


def amount_to_units(balance: str, decimals: int) -> str:
    scale = Decimal(10) ** decimals
    value = (Decimal(balance) * scale).to_integral_value(rounding=ROUND_DOWN)
    return str(value)
