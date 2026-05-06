from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1

from .models import Asset


@dataclass(frozen=True)
class ScanItem:
    id: str
    wallet: str
    asset: Asset


class ScanStore:
    def __init__(self) -> None:
        self._items: dict[str, ScanItem] = {}

    def put_assets(self, wallet: str, assets: list[Asset]) -> list[ScanItem]:
        items = [ScanItem(asset_id(wallet, asset), wallet, asset) for asset in assets]
        for item in items:
            self._items[item.id] = item
        return items

    def get(self, item_id: str) -> ScanItem | None:
        return self._items.get(item_id)


def asset_id(wallet: str, asset: Asset) -> str:
    key = f"{wallet}:{asset.chain}:{asset.kind.value}:{asset.token}:{asset.token_address or ''}:{asset.balance}"
    return sha1(key.encode("utf-8")).hexdigest()[:10]

