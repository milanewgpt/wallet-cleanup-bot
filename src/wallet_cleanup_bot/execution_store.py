from __future__ import annotations

from dataclasses import dataclass

from .models import Asset, Proposal


@dataclass(frozen=True)
class PendingWithdraw:
    asset: Asset
    destination: str


@dataclass(frozen=True)
class PendingExecution:
    id: str
    wallet: str
    label: str
    encrypted_keystore: str
    proposal: Proposal | None = None
    withdraw: PendingWithdraw | None = None
    message_chat_id: str | None = None
    message_id: int | None = None


class PendingExecutionStore:
    def __init__(self) -> None:
        self._items: dict[str, PendingExecution] = {}

    def put(self, execution: PendingExecution) -> None:
        self._items[execution.id] = execution

    def get(self, execution_id: str) -> PendingExecution | None:
        return self._items.get(execution_id)

    def remove(self, execution_id: str) -> PendingExecution | None:
        return self._items.pop(execution_id, None)
