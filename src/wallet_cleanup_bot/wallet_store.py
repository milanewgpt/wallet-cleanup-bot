from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


@dataclass(frozen=True)
class StoredWallet:
    address: str
    label: str | None = None
    encrypted_keystore: str | None = None


class WalletStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def list_wallets(self) -> list[StoredWallet]:
        if not self.path.exists():
            return []
        raw = self.path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        data = json.loads(raw)
        return [StoredWallet(**item) for item in data.get("wallets", [])]

    def add_wallet(self, address: str, label: str | None = None) -> StoredWallet:
        normalized = normalize_wallet(address)
        wallets = [wallet for wallet in self.list_wallets() if wallet.address.lower() != normalized.lower()]
        wallet = StoredWallet(normalized, label)
        wallets.append(wallet)
        self._write(wallets)
        return wallet

    def add_encrypted_wallet(self, address: str, label: str, encrypted_keystore: str) -> StoredWallet:
        normalized = normalize_wallet(address)
        wallets = [wallet for wallet in self.list_wallets() if wallet.address.lower() != normalized.lower()]
        wallet = StoredWallet(normalized, label, encrypted_keystore)
        wallets.append(wallet)
        self._write(wallets)
        return wallet

    def remove_wallet(self, address_or_index: str) -> StoredWallet | None:
        wallets = self.list_wallets()
        wallet = self.resolve_wallet(address_or_index)
        if wallet is None:
            return None
        wallets = [item for item in wallets if item.address.lower() != wallet.address.lower()]
        self._write(wallets)
        return wallet

    def resolve_wallet(self, address_or_index: str) -> StoredWallet | None:
        wallets = self.list_wallets()
        if address_or_index.isdigit():
            index = int(address_or_index) - 1
            if 0 <= index < len(wallets):
                return wallets[index]
            return None
        for wallet in wallets:
            if wallet.label and wallet.label.lower() == address_or_index.lower():
                return wallet
        try:
            normalized = normalize_wallet(address_or_index)
        except ValueError:
            return None
        for wallet in wallets:
            if wallet.address.lower() == normalized.lower():
                return wallet
        return StoredWallet(normalized)

    def _write(self, wallets: list[StoredWallet]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"wallets": [asdict(wallet) for wallet in wallets]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_wallet(address: str) -> str:
    value = address.strip()
    if not WALLET_RE.match(value):
        raise ValueError("invalid EVM wallet address")
    return value
