from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .models import Asset, TokenKind


@dataclass(frozen=True)
class ChainInfo:
    name: str
    native_symbol: str
    rpc_urls: tuple[str, ...]
    coingecko_id: str
    decimals: int = 18


DEFAULT_CHAINS: dict[str, ChainInfo] = {
    "Ethereum": ChainInfo("Ethereum", "ETH", ("https://ethereum-rpc.publicnode.com", "https://rpc.ankr.com/eth"), "ethereum"),
    "Base": ChainInfo("Base", "ETH", ("https://base-rpc.publicnode.com", "https://mainnet.base.org"), "ethereum"),
    "Arbitrum": ChainInfo("Arbitrum", "ETH", ("https://arbitrum-one-rpc.publicnode.com", "https://arb1.arbitrum.io/rpc"), "ethereum"),
    "Optimism": ChainInfo("Optimism", "ETH", ("https://optimism-rpc.publicnode.com", "https://mainnet.optimism.io"), "ethereum"),
    "Polygon": ChainInfo("Polygon", "POL", ("https://polygon-bor-rpc.publicnode.com", "https://polygon-rpc.com"), "polygon-ecosystem-token"),
    "BNB": ChainInfo("BNB", "BNB", ("https://bsc-rpc.publicnode.com", "https://bsc-dataseed.binance.org"), "binancecoin"),
    "Avalanche": ChainInfo("Avalanche", "AVAX", ("https://avalanche-c-chain-rpc.publicnode.com", "https://api.avax.network/ext/bc/C/rpc"), "avalanche-2"),
    "Linea": ChainInfo("Linea", "ETH", ("https://linea-rpc.publicnode.com", "https://rpc.linea.build"), "ethereum"),
    "zkSync": ChainInfo("zkSync", "ETH", ("https://zksync-era-rpc.publicnode.com", "https://mainnet.era.zksync.io"), "ethereum"),
}


class LiveNativeScanner:
    def __init__(self, chain_info: dict[str, ChainInfo] | None = None) -> None:
        self.chain_info = chain_info or DEFAULT_CHAINS

    def scan_wallet(self, wallet: str, chains: list[str]) -> list[Asset]:
        infos = [self.chain_info[chain] for chain in chains if chain in self.chain_info]
        prices = fetch_prices_usd({info.coingecko_id for info in infos})
        assets: list[Asset] = []
        for info in infos:
            try:
                balance = fetch_native_balance_with_fallback(info.rpc_urls, wallet, info.decimals)
            except Exception:
                continue
            if balance <= 0:
                continue
            price = prices.get(info.coingecko_id, 0.0)
            assets.append(
                Asset(
                    chain=info.name,
                    token=info.native_symbol,
                    balance=format_decimal(balance),
                    value_usd=float(balance * Decimal(str(price))),
                    kind=TokenKind.NATIVE,
                    decimals=info.decimals,
                )
            )
        return assets


def fetch_native_balance(rpc_url: str, wallet: str, decimals: int) -> Decimal:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getBalance",
        "params": [wallet, "latest"],
    }
    response = post_json(rpc_url, payload)
    raw = str(response.get("result", "0x0"))
    wei = int(raw, 16)
    return Decimal(wei) / (Decimal(10) ** decimals)


def fetch_native_balance_with_fallback(rpc_urls: tuple[str, ...], wallet: str, decimals: int) -> Decimal:
    last_error: Exception | None = None
    for rpc_url in rpc_urls:
        try:
            return fetch_native_balance(rpc_url, wallet, decimals)
        except Exception as error:
            last_error = error
    if last_error is not None:
        raise last_error
    return Decimal(0)


def fetch_prices_usd(coingecko_ids: set[str]) -> dict[str, float]:
    if not coingecko_ids:
        return {}
    query = urllib.parse.urlencode(
        {
            "ids": ",".join(sorted(coingecko_ids)),
            "vs_currencies": "usd",
        }
    )
    url = f"https://api.coingecko.com/api/v3/simple/price?{query}"
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}
    return {
        token_id: float(value.get("usd", 0.0))
        for token_id, value in data.items()
        if isinstance(value, dict)
    }


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "wallet-cleanup-bot/0.1",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def format_decimal(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text
