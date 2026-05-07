from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .models import ApprovalAction, ApprovalDecision, Proposal, TokenKind


CallbackData = tuple[str, ApprovalAction]


@dataclass(frozen=True)
class TelegramSettings:
    bot_token: str
    chat_id: str
    allowed_user_id: int | None = None
    poll_timeout_s: int = 10
    approval_timeout_s: int = 900


class TelegramApiClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return self._post("sendMessage", payload)

    def edit_reply_markup(self, chat_id: str, message_id: int) -> dict[str, Any]:
        try:
            return self._post("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id, "reply_markup": None})
        except urllib.error.HTTPError:
            return {"ok": False}

    def delete_message(self, chat_id: str, message_id: int) -> dict[str, Any]:
        try:
            return self._post("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
        except urllib.error.HTTPError:
            return {"ok": False}

    def answer_callback_query(self, callback_query_id: str, text: str) -> dict[str, Any]:
        return self._post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})

    def get_updates(self, offset: int | None, timeout_s: int) -> list[dict[str, Any]]:
        query = {"timeout": timeout_s}
        if offset is not None:
            query["offset"] = offset
        response = self._get("getUpdates", query)
        return response.get("result", [])

    def _get(self, method: str, query: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{method}?{urllib.parse.urlencode(query)}"
        with urllib.request.urlopen(url, timeout=max(int(query.get("timeout", 30)) + 5, 10)) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))


class TelegramApprovalGateway:
    def __init__(self, settings: TelegramSettings, client: TelegramApiClient | None = None) -> None:
        self.settings = settings
        self.client = client or TelegramApiClient(settings.bot_token)
        self._offset: int | None = None

    def request_approval(self, proposal: Proposal) -> ApprovalDecision:
        message = self.client.send_message(
            self.settings.chat_id,
            format_proposal_message(proposal),
            reply_markup=proposal_keyboard(proposal.id),
        )
        message_id = int(message["result"]["message_id"])

        deadline = time.monotonic() + self.settings.approval_timeout_s
        while time.monotonic() < deadline:
            updates = self.client.get_updates(self._offset, self.settings.poll_timeout_s)
            for update in updates:
                self._offset = int(update["update_id"]) + 1
                callback = self._parse_callback(update, proposal.id)
                if callback is None:
                    continue

                callback_id, action = callback
                self.client.answer_callback_query(callback_id, f"Decision: {action.value}")
                self.client.edit_reply_markup(self.settings.chat_id, message_id)
                return ApprovalDecision(proposal.id, action)

        self.client.edit_reply_markup(self.settings.chat_id, message_id)
        return ApprovalDecision(proposal.id, ApprovalAction.SKIP)

    def _parse_callback(self, update: dict[str, Any], proposal_id: str) -> CallbackData | None:
        callback = update.get("callback_query")
        if not callback:
            return None

        user = callback.get("from", {})
        if self.settings.allowed_user_id is not None and int(user.get("id", 0)) != self.settings.allowed_user_id:
            callback_id = str(callback["id"])
            self.client.answer_callback_query(callback_id, "Not allowed")
            return None

        data = str(callback.get("data", ""))
        expected_prefix = f"wc:{proposal_id}:"
        if not data.startswith(expected_prefix):
            return None

        action_value = data.removeprefix(expected_prefix)
        try:
            action = ApprovalAction(action_value)
        except ValueError:
            return None

        return str(callback["id"]), action


def proposal_keyboard(proposal_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": _callback(proposal_id, ApprovalAction.APPROVE)},
                {"text": "Skip", "callback_data": _callback(proposal_id, ApprovalAction.SKIP)},
            ],
            [
                {"text": "Blacklist token", "callback_data": _callback(proposal_id, ApprovalAction.BLACKLIST_TOKEN)},
                {"text": "Change threshold", "callback_data": _callback(proposal_id, ApprovalAction.CHANGE_THRESHOLD)},
            ],
        ]
    }


def format_proposal_message(proposal: Proposal) -> str:
    asset = proposal.decision.normalized.asset
    lines = [
        f"<b>Wallet cleanup proposal</b>",
        f"<b>ID:</b> <code>{proposal.id}</code>",
        f"<b>Wallet:</b> <code>{proposal.wallet}</code>",
        "",
        f"<b>{asset.chain}</b>",
        f"{asset.token} ({asset.chain}) -> {proposal.route.to_token} ({proposal.route.to_chain})",
        f"Balance: <code>{asset.balance}</code>",
        f"Value: ${asset.value_usd:.2f}",
        f"Receive: ${proposal.route.expected_receive_usd:.2f}",
        f"Gas: ${proposal.route.gas_usd:.2f}",
        f"Slippage: {proposal.route.slippage_pct:.2f}%",
        f"Route: {proposal.route.route_type}",
    ]
    if asset.kind == TokenKind.NATIVE and proposal.threshold_usd is not None:
        lines.extend([f"Threshold: ${proposal.threshold_usd:.2f}", "Proposed: clean excess"])
    return "\n".join(lines)


def _callback(proposal_id: str, action: ApprovalAction) -> str:
    return f"wc:{proposal_id}:{action.value}"
