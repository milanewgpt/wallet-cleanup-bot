from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .models import Asset, TokenKind


MORALIS_CHAIN_BY_NAME = {
    "Ethereum": "eth",
    "Base": "base",
    "Arbitrum": "arbitrum",
    "Optimism": "optimism",
    "Polygon": "polygon",
    "BNB": "bsc",
    "Avalanche": "avalanche",
    "Linea": "linea",
}


class MoralisErc20Scanner:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def scan_wallet(self, wallet: str, chains: list[str]) -> list[Asset]:
        assets: list[Asset] = []
        for chain in chains:
            moralis_chain = MORALIS_CHAIN_BY_NAME.get(chain)
            if moralis_chain is None:
                continue
            try:
                assets.extend(self._scan_chain(wallet, chain, moralis_chain))
            except Exception:
                continue
        return assets

    def _scan_chain(self, wallet: str, chain_name: str, moralis_chain: str) -> list[Asset]:
        cursor: str | None = None
        assets: list[Asset] = []
        while True:
            payload = self._fetch_page(wallet, moralis_chain, cursor)
            for item in payload.get("result", []):
                if item.get("native_token") is True or item.get("possible_spam") is True:
                    continue
                balance = str(item.get("balance_formatted") or "")
                if not balance or balance == "0":
                    continue
                assets.append(
                    Asset(
                        chain=chain_name,
                        token=str(item.get("symbol") or "UNKNOWN"),
                        balance=balance,
                        value_usd=float(item.get("usd_value") or 0.0),
                        kind=TokenKind.ERC20,
                        token_address=str(item.get("token_address") or ""),
                        decimals=int(item.get("decimals") or 18),
                    )
                )
            cursor = payload.get("cursor")
            if not cursor:
                return assets

    def _fetch_page(self, wallet: str, chain: str, cursor: str | None) -> dict[str, Any]:
        query = {
            "chain": chain,
            "exclude_spam": "true",
            "exclude_unverified_contracts": "false",
        }
        if cursor:
            query["cursor"] = cursor
        url = f"https://deep-index.moralis.io/api/v2.2/wallets/{wallet}/tokens?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "X-API-Key": self.api_key,
                "User-Agent": "wallet-cleanup-bot/0.1",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


class CompositeScanner:
    def __init__(self, scanners: list[Any]) -> None:
        self.scanners = scanners

    def scan_wallet(self, wallet: str, chains: list[str]) -> list[Asset]:
        assets: list[Asset] = []
        seen: set[tuple[str, str, str]] = set()
        for scanner in self.scanners:
            for asset in scanner.scan_wallet(wallet, chains):
                key = (asset.chain, asset.kind.value, (asset.token_address or asset.token).lower())
                if key in seen:
                    continue
                seen.add(key)
                assets.append(asset)
        return assets
