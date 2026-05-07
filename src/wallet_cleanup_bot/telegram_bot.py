from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import CleanupConfig
from .execution_store import PendingExecution, PendingExecutionStore, PendingWithdraw
from .models import ApprovalAction, ApprovalDecision, ExecutionStatus, Proposal
from .pipeline import CleanupPipeline
from .scan_store import ScanStore
from .telegram_gateway import TelegramApiClient, TelegramSettings, format_proposal_message, proposal_keyboard
from .wallet_store import WalletStore, normalize_wallet


HELP_TEXT = """<b>Wallet Cleanup Bot</b>

/add_wallet label - добавить кошелёк (пришли приватник, удалится мгновенно)
/remove_wallet 1 или 0x... - удалить кошелёк
/wallets - список кошельков
/check_wallet label, 1 или 0x... - проверить конкретный кошелёк
/check_all - проверить все сохранённые кошельки
/cancel - отменить ожидание ключа
/help - команды
"""


@dataclass(frozen=True)
class TelegramBotApp:
    settings: TelegramSettings
    config: CleanupConfig
    wallet_store: WalletStore
    pipeline_factory: Callable[[str], CleanupPipeline]
    client: TelegramApiClient
    pending_executions: PendingExecutionStore | None = None
    scan_store: ScanStore | None = None
    pending_withdraw_items: dict[str, Any] = field(default_factory=dict)
    pending_proposals: dict[str, Proposal] = field(default_factory=dict)
    pending_key_imports: dict[str, str] = field(default_factory=dict)
    pending_key_executes: dict[str, Any] = field(default_factory=dict)
    offset: int | None = None

    def run_forever(self) -> None:
        offset = self.offset
        self.client.send_message(self.settings.chat_id, "Bot started. Use /help.")
        while True:
            updates = self.client.get_updates(offset, self.settings.poll_timeout_s)
            for update in updates:
                offset = int(update["update_id"]) + 1
                offset = self._handle_update(update, offset)

    def _handle_update(self, update: dict[str, Any], offset: int) -> int:
        message = update.get("message")
        if not message:
            callback = update.get("callback_query")
            if callback:
                self._handle_callback(callback)
            return offset
        if not self._message_allowed(message):
            return offset

        text = str(message.get("text", "")).strip()
        if not text:
            return offset
        message_id = message.get("message_id")
        if not text.startswith("/") and self._handle_pending_key(text, message_id):
            return offset
        if not text.startswith("/") and self._handle_pending_withdraw_address(text):
            return offset

        command, args = _split_command(text)
        if command in {"/start", "/help"}:
            self.client.send_message(self.settings.chat_id, HELP_TEXT)
        elif command == "/add_wallet":
            self._add_wallet(args)
        elif command == "/remove_wallet":
            self._remove_wallet(args)
        elif command == "/wallets":
            self._list_wallets()
        elif command == "/check_wallet":
            offset = self._check_wallet(args, offset)
        elif command == "/check_all":
            offset = self._check_all(offset)
        elif command == "/cancel":
            self._cancel_pending_key()
        else:
            self.client.send_message(self.settings.chat_id, "Unknown command. Use /help.")
        return offset

    def _message_allowed(self, message: dict[str, Any]) -> bool:
        if str(message.get("chat", {}).get("id")) != str(self.settings.chat_id):
            return False
        if self.settings.allowed_user_id is None:
            return True
        return int(message.get("from", {}).get("id", 0)) == self.settings.allowed_user_id

    def _add_wallet(self, args: str) -> None:
        label = args.strip()
        if not label:
            self.client.send_message(self.settings.chat_id, "Usage: /add_wallet label")
            return
        self.pending_key_imports[str(self.settings.chat_id)] = label
        self.client.send_message(
            self.settings.chat_id,
            f"Пришли приватный ключ для кошелька <b>{label}</b>.\nСообщение будет удалено мгновенно. /cancel для отмены.",
        )

    def _remove_wallet(self, args: str) -> None:
        if not args:
            self.client.send_message(self.settings.chat_id, "Usage: /remove_wallet 1 or /remove_wallet 0x...")
            return
        wallet = self.wallet_store.remove_wallet(args.strip())
        if wallet is None:
            self.client.send_message(self.settings.chat_id, "Wallet not found.")
            return
        self.client.send_message(self.settings.chat_id, f"Removed: <code>{wallet.address}</code>")

    def _list_wallets(self) -> None:
        wallets = self.wallet_store.list_wallets()
        if not wallets:
            self.client.send_message(self.settings.chat_id, "No wallets saved.")
            return
        lines = ["<b>Wallets</b>"]
        for index, wallet in enumerate(wallets, start=1):
            label = f" - {wallet.label}" if wallet.label else ""
            signer = " encrypted" if wallet.encrypted_keystore else " watch-only"
            lines.append(f"{index}. <code>{wallet.address}</code>{label} ({signer})")
        self.client.send_message(self.settings.chat_id, "\n".join(lines))

    def _check_wallet(self, args: str, offset: int) -> int:
        if not args:
            self.client.send_message(self.settings.chat_id, "Usage: /check_wallet label, 1 or 0x...")
            return offset
        wallet = self.wallet_store.resolve_wallet(args.strip())
        if wallet is None:
            self.client.send_message(self.settings.chat_id, "Wallet not found or invalid address.")
            return offset
        return self._run_check(wallet.address, offset)

    def _check_all(self, offset: int) -> int:
        wallets = self.wallet_store.list_wallets()
        if not wallets:
            self.client.send_message(self.settings.chat_id, "No wallets saved.")
            return offset
        for wallet in wallets:
            offset = self._run_check(wallet.address, offset)
        return offset

    def _run_check(self, wallet: str, offset: int) -> int:
        pipeline = self.pipeline_factory(wallet)
        self.client.send_message(self.settings.chat_id, f"Checking <code>{wallet}</code>...")
        assets = pipeline.scanner.scan_wallet(wallet, self.config.chains)
        pipeline.log_store.append("scan.completed", assets)
        if not assets:
            self.client.send_message(self.settings.chat_id, "No balances found on configured chains.")
            return offset
        items = self.scan_store.put_assets(wallet, assets) if self.scan_store else []
        self._send_scan_items(wallet, items)
        return offset

    def _send_scan_items(self, wallet: str, items: list[Any]) -> None:
        self.client.send_message(self.settings.chat_id, format_balance_scan(wallet, [item.asset for item in items]))
        for item in items:
            asset = item.asset
            self.client.send_message(
                self.settings.chat_id,
                format_scan_item(item),
                reply_markup={
                    "inline_keyboard": [
                        [
                            {"text": "Find route", "callback_data": f"asset:{item.id}:route"},
                            {"text": "Withdraw", "callback_data": f"asset:{item.id}:withdraw"},
                            {"text": "Skip", "callback_data": f"asset:{item.id}:skip"},
                        ]
                    ]
                },
            )

    def _handle_callback(self, callback: dict[str, Any]) -> None:
        if self.settings.allowed_user_id is not None and int(callback.get("from", {}).get("id", 0)) != self.settings.allowed_user_id:
            self.client.answer_callback_query(str(callback["id"]), "Not allowed")
            return
        data = str(callback.get("data", ""))
        message = callback.get("message", {})
        message_id = message.get("message_id")
        if message_id is not None:
            self.client.delete_message(self.settings.chat_id, int(message_id))
        if data.startswith("wc:"):
            self._handle_proposal_callback(callback, data)
            return
        if not data.startswith("asset:"):
            return
        parts = data.split(":")
        if len(parts) != 3 or not self.scan_store:
            return
        item = self.scan_store.get(parts[1])
        if item is None:
            self.client.answer_callback_query(str(callback["id"]), "Scan item expired")
            return
        self.client.answer_callback_query(str(callback["id"]), "Working...")
        if parts[2] == "skip":
            self.client.answer_callback_query(str(callback["id"]), "Skipped")
            return
        if parts[2] == "withdraw":
            self.pending_withdraw_items[str(self.settings.chat_id)] = item
            self.client.send_message(self.settings.chat_id, f"Send destination address for <code>{item.id}</code>.")
            return
        if parts[2] == "route":
            self._build_single_route(item)

    def _build_single_route(self, item: Any) -> None:
        pipeline = self.pipeline_factory(item.wallet)
        normalized = pipeline._normalize(item.asset)
        decision = pipeline._filter(normalized)
        if not decision.executable:
            self.client.send_message(self.settings.chat_id, f"No route: {decision.note or decision.reason.value}")
            return
        try:
            route = pipeline.router.quote(item.asset, self.config.target_chain, self.config.target_token)
        except Exception as error:
            self.client.send_message(self.settings.chat_id, f"No route found: {error}")
            return
        proposal = Proposal(
            id=item.id,
            wallet=item.wallet,
            decision=decision,
            route=route,
            threshold_usd=self.config.threshold_for(item.asset.chain) if item.asset.kind.value == "native" else None,
        )
        self.client.send_message(
            self.settings.chat_id,
            format_proposal_message(proposal),
            reply_markup=proposal_keyboard(proposal.id),
        )
        self.pending_proposals[proposal.id] = proposal

    def _handle_proposal_callback(self, callback: dict[str, Any], data: str) -> None:
        parts = data.split(":")
        if len(parts) != 3:
            return
        proposal_id = parts[1]
        action = parts[2]
        proposal = self.pending_proposals.pop(proposal_id, None)
        if proposal is None:
            self.client.answer_callback_query(str(callback["id"]), "Proposal expired")
            return
        if action == ApprovalAction.SKIP.value:
            self.client.answer_callback_query(str(callback["id"]), "Skipped")
            return
        if action == ApprovalAction.APPROVE.value:
            self.client.answer_callback_query(str(callback["id"]), "Approved")
            self._send_execute_link(proposal.wallet, proposal)
            return
        if action == ApprovalAction.BLACKLIST_TOKEN.value:
            self.client.answer_callback_query(str(callback["id"]), "Blacklisted")
            self.client.send_message(self.settings.chat_id, f"Blacklist saved for <code>{proposal.decision.normalized.asset.token}</code> is not connected yet.")
            return
        if action == ApprovalAction.CHANGE_THRESHOLD.value:
            self.client.answer_callback_query(str(callback["id"]), "Threshold")
            self.client.send_message(self.settings.chat_id, "Threshold change flow is not connected yet.")

    def _handle_pending_key(self, text: str, message_id: int | None) -> bool:
        chat_id = str(self.settings.chat_id)
        in_import = chat_id in self.pending_key_imports
        in_execute = chat_id in self.pending_key_executes
        is_pk = _looks_like_private_key(text)

        if in_import or in_execute:
            if not is_pk:
                self.client.send_message(chat_id, "Ожидаю приватный ключ (64 hex-символа, 0x опционально). /cancel для отмены.")
                return True
            if message_id is not None:
                self.client.delete_message(chat_id, message_id)
            if in_import:
                label = self.pending_key_imports.pop(chat_id)
                self._handle_key_for_import(text, label)
            else:
                payload = self.pending_key_executes.pop(chat_id)
                self._handle_key_for_execute(text, payload)
            return True

        if is_pk:
            if message_id is not None:
                self.client.delete_message(chat_id, message_id)
            self.client.send_message(chat_id, "Приватный ключ удалён для безопасности. Используй /add_wallet для добавления кошелька.")
            return True

        return False

    def _handle_key_for_import(self, private_key: str, label: str) -> None:
        from .signer import address_from_key
        try:
            address = address_from_key(private_key)
        except Exception as err:
            self.client.send_message(self.settings.chat_id, f"Неверный приватный ключ: {err}")
            return
        self.wallet_store.add_wallet(address, label)
        self.client.send_message(self.settings.chat_id, f"Кошелёк добавлен: <code>{address}</code> — {label}")

    def _handle_key_for_execute(self, private_key: str, payload: dict[str, Any]) -> None:
        from .signer import execute_with_key
        self.client.send_message(self.settings.chat_id, "Подписываю и отправляю транзакцию...")
        try:
            tx_hashes = execute_with_key(private_key, payload)
            self.client.send_message(
                self.settings.chat_id,
                "Готово: " + ", ".join(f"<code>{h}</code>" for h in tx_hashes),
            )
        except Exception as err:
            self.client.send_message(self.settings.chat_id, f"Ошибка исполнения: {err}")

    def _cancel_pending_key(self) -> None:
        chat_id = str(self.settings.chat_id)
        had = chat_id in self.pending_key_imports or chat_id in self.pending_key_executes
        self.pending_key_imports.pop(chat_id, None)
        self.pending_key_executes.pop(chat_id, None)
        self.client.send_message(self.settings.chat_id, "Отменено." if had else "Нечего отменять.")

    def _handle_pending_withdraw_address(self, text: str) -> bool:
        item = self.pending_withdraw_items.get(str(self.settings.chat_id))
        if item is None:
            return False
        try:
            destination = normalize_wallet(text)
        except ValueError:
            self.client.send_message(self.settings.chat_id, "Invalid EVM address. Send destination as 0x...")
            return True
        self.pending_withdraw_items.pop(str(self.settings.chat_id), None)
        self._send_withdraw_execute_link(item, destination)
        return True

    def _send_execute_link(self, wallet: str, proposal: Proposal) -> None:
        from .webapp_server import execution_payload
        stored = self.wallet_store.resolve_wallet(wallet)
        if stored is None:
            self.client.send_message(self.settings.chat_id, "Wallet not found.")
            return
        execution = PendingExecution(
            id=proposal.id,
            wallet=stored.address,
            label=stored.label or "",
            encrypted_keystore="",
            proposal=proposal,
        )
        try:
            payload = execution_payload(execution)
        except Exception as err:
            self.client.send_message(self.settings.chat_id, f"Failed to build tx: {err}")
            return
        self.pending_key_executes[str(self.settings.chat_id)] = payload
        self.client.send_message(
            self.settings.chat_id,
            f"Готово к исполнению <code>{proposal.id}</code>.\nПришли приватный ключ для <code>{stored.address}</code> — сообщение удалится мгновенно. /cancel для отмены.",
        )

    def _send_withdraw_execute_link(self, item: Any, destination: str) -> None:
        from .webapp_server import withdraw_execution_payload
        stored = self.wallet_store.resolve_wallet(item.wallet)
        if stored is None:
            self.client.send_message(self.settings.chat_id, "Wallet not found.")
            return
        execution = PendingExecution(
            id=f"{item.id}:withdraw",
            wallet=stored.address,
            label=stored.label or "",
            encrypted_keystore="",
            withdraw=PendingWithdraw(asset=item.asset, destination=destination),
        )
        try:
            payload = withdraw_execution_payload(execution)
        except Exception as err:
            self.client.send_message(self.settings.chat_id, f"Failed to build tx: {err}")
            return
        self.pending_key_executes[str(self.settings.chat_id)] = payload
        self.client.send_message(
            self.settings.chat_id,
            format_withdraw_ready(item, destination) + "\n\nПришли приватный ключ — сообщение удалится мгновенно. /cancel для отмены.",
        )

    def _request_approval(self, proposal: Proposal, offset: int) -> tuple[ApprovalDecision, int]:
        message = self.client.send_message(
            self.settings.chat_id,
            format_proposal_message(proposal),
            reply_markup=proposal_keyboard(proposal.id),
        )
        message_id = int(message["result"]["message_id"])
        deadline = time.monotonic() + self.settings.approval_timeout_s
        while time.monotonic() < deadline:
            updates = self.client.get_updates(offset, self.settings.poll_timeout_s)
            for update in updates:
                offset = int(update["update_id"]) + 1
                callback = update.get("callback_query")
                if not callback:
                    continue
                action = self._parse_proposal_action(callback, proposal.id)
                if action is None:
                    continue
                self.client.answer_callback_query(str(callback["id"]), f"Decision: {action.value}")
                self.client.edit_reply_markup(self.settings.chat_id, message_id)
                return ApprovalDecision(proposal.id, action), offset

        self.client.edit_reply_markup(self.settings.chat_id, message_id)
        return ApprovalDecision(proposal.id, ApprovalAction.SKIP), offset

    def _parse_proposal_action(self, callback: dict[str, Any], proposal_id: str) -> ApprovalAction | None:
        if self.settings.allowed_user_id is not None and int(callback.get("from", {}).get("id", 0)) != self.settings.allowed_user_id:
            self.client.answer_callback_query(str(callback["id"]), "Not allowed")
            return None
        data = str(callback.get("data", ""))
        prefix = f"wc:{proposal_id}:"
        if not data.startswith(prefix):
            return None
        try:
            return ApprovalAction(data.removeprefix(prefix))
        except ValueError:
            return None


def _split_command(text: str) -> tuple[str, str]:
    parts = text.split(maxsplit=1)
    command = parts[0].split("@", 1)[0]
    args = parts[1] if len(parts) > 1 else ""
    return command, args


def _looks_like_private_key(value: str) -> bool:
    raw = value.removeprefix("0x")
    return len(raw) == 64 and all(char in "0123456789abcdefABCDEF" for char in raw)


def import_url(base_url: str, label: str, token: str) -> str:
    from urllib.parse import urlencode

    return f"{base_url.rstrip('/')}/import?{urlencode({'label': label, 'token': token})}"


def execute_url(base_url: str, execution_id: str, token: str) -> str:
    from urllib.parse import urlencode

    return f"{base_url.rstrip('/')}/execute?{urlencode({'id': execution_id, 'token': token})}"


def format_balance_scan(wallet: str, assets: list[Any]) -> str:
    lines = [f"<b>Live balances</b>", f"<code>{wallet}</code>", ""]
    total = 0.0
    for asset in sorted(assets, key=lambda item: (item.chain, item.kind.value, -item.value_usd)):
        total += asset.value_usd
        lines.append(f"{asset.chain}: <code>{asset.balance}</code> {asset.token} (${asset.value_usd:.2f})")
    lines.append("")
    lines.append(f"Total value: ${total:.2f}")
    return "\n".join(lines)


def format_scan_item(item: Any) -> str:
    asset = item.asset
    return (
        f"<b>{asset.token} ({asset.chain})</b>\n"
        f"ID: <code>{item.id}</code>\n"
        f"Balance: <code>{asset.balance}</code>\n"
        f"Value: ${asset.value_usd:.2f}"
    )


def format_withdraw_ready(item: Any, destination: str) -> str:
    asset = item.asset
    return (
        "<b>Withdraw prepared</b>\n"
        f"{asset.token} ({asset.chain})\n"
        f"Amount: <code>{asset.balance}</code>\n"
        f"From: <code>{item.wallet}</code>\n"
        f"To: <code>{destination}</code>\n\n"
        "Open unlock page to sign and send."
    )
