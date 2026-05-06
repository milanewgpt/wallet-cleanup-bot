from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CleanupConfig:
    chains: list[str]
    protected_gas_chains: set[str]
    target_chain: str = "Base"
    target_token: str = "USDC"
    default_gas_threshold_usd: float = 10.0
    chain_thresholds_usd: dict[str, float] = field(default_factory=dict)
    log_path: str = "wallet-cleanup-log.jsonl"
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_allowed_user_id: int | None = None
    wallet_store_path: str = "wallets.json"
    webapp_host: str = "127.0.0.1"
    webapp_port: int = 8787
    webapp_base_url: str = "http://127.0.0.1:8787"
    webapp_import_token: str = "dev-import-token"
    demo_data_enabled: bool = False
    live_native_scanner_enabled: bool = True
    live_routes_enabled: bool = True
    moralis_api_key: str | None = None
    moralis_erc20_scanner_enabled: bool = False
    lifi_api_key: str | None = None
    lifi_slippage: float = 0.03

    def threshold_for(self, chain: str) -> float:
        return self.chain_thresholds_usd.get(chain, self.default_gas_threshold_usd)


def load_config_from_env() -> CleanupConfig:
    chains = _csv_env(
        "CHAINS",
        "Ethereum,Base,Arbitrum,Optimism,Polygon,BNB,Avalanche,Linea,zkSync",
    )
    protected = set(_csv_env("PROTECTED_GAS_CHAINS", "Ethereum,Base,Arbitrum,Optimism,Linea,zkSync"))
    return CleanupConfig(
        chains=chains,
        protected_gas_chains=protected,
        target_chain=os.getenv("TARGET_CHAIN", "Base"),
        target_token=os.getenv("TARGET_TOKEN", "USDC"),
        default_gas_threshold_usd=float(os.getenv("DEFAULT_GAS_THRESHOLD_USD", "10")),
        log_path=os.getenv("LOG_PATH", "wallet-cleanup-log.jsonl"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        telegram_allowed_user_id=_optional_int(os.getenv("TELEGRAM_ALLOWED_USER_ID")),
        wallet_store_path=os.getenv("WALLET_STORE_PATH", "wallets.json"),
        webapp_host=os.getenv("WEBAPP_HOST", "127.0.0.1"),
        webapp_port=int(os.getenv("WEBAPP_PORT", "8787")),
        webapp_base_url=os.getenv("WEBAPP_BASE_URL", "http://127.0.0.1:8787").rstrip("/"),
        webapp_import_token=os.getenv("WEBAPP_IMPORT_TOKEN", "dev-import-token"),
        demo_data_enabled=_bool_env(os.getenv("DEMO_DATA_ENABLED", "false")),
        live_native_scanner_enabled=_bool_env(os.getenv("LIVE_NATIVE_SCANNER_ENABLED", "true")),
        live_routes_enabled=_bool_env(os.getenv("LIVE_ROUTES_ENABLED", "true")),
        moralis_api_key=os.getenv("MORALIS_API_KEY"),
        moralis_erc20_scanner_enabled=_bool_env(os.getenv("MORALIS_ERC20_SCANNER_ENABLED", "false")),
        lifi_api_key=os.getenv("LIFI_API_KEY"),
        lifi_slippage=float(os.getenv("LIFI_SLIPPAGE", "0.03")),
    )


def _csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [part.strip() for part in value.split(",") if part.strip()]


def _optional_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _bool_env(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
