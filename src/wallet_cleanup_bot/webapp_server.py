from __future__ import annotations

import html
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .execution_store import PendingExecutionStore
from .lifi_router import CHAIN_ID_BY_NAME, RPC_URL_BY_CHAIN_ID, amount_to_units
from .models import TokenKind
from .wallet_store import WalletStore


class WalletImportServer:
    def __init__(
        self,
        host: str,
        port: int,
        wallet_store: WalletStore,
        import_token: str,
        pending_executions: PendingExecutionStore | None = None,
        on_wallet_imported: Callable[[str, str], None] | None = None,
        on_execution_opened: Callable[[Any], None] | None = None,
        on_execution_completed: Callable[[str, list[str]], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.wallet_store = wallet_store
        self.import_token = import_token
        self.pending_executions = pending_executions
        self.on_wallet_imported = on_wallet_imported
        self.on_execution_opened = on_execution_opened
        self.on_execution_completed = on_execution_completed
        self.httpd = ThreadingHTTPServer((host, port), self._handler_class())

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        return thread

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        wallet_store = self.wallet_store
        import_token = self.import_token
        pending_executions = self.pending_executions
        on_wallet_imported = self.on_wallet_imported
        on_execution_opened = self.on_execution_opened
        on_execution_completed = self.on_execution_completed

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/import":
                    query = parse_qs(parsed.query)
                    label = query.get("label", [""])[0]
                    token = query.get("token", [""])[0]
                    self._send_html(import_page(label, token))
                    return
                if parsed.path == "/execute":
                    query = parse_qs(parsed.query)
                    execution_id = query.get("id", [""])[0]
                    token = query.get("token", [""])[0]
                    self._send_html(execute_page(execution_id, token))
                    return
                if parsed.path.startswith("/api/executions/"):
                    self._handle_get_execution(parsed.path, parse_qs(parsed.query))
                    return
                self._send_json(404, {"error": "not_found"})
                return

            def _handle_get_execution(self, path: str, query: dict[str, list[str]]) -> None:
                if pending_executions is None:
                    self._send_json(404, {"error": "not_found"})
                    return
                token = query.get("token", [""])[0]
                if token != import_token:
                    self._send_json(403, {"error": "forbidden"})
                    return
                execution_id = path.rsplit("/", 1)[-1]
                execution = pending_executions.get(execution_id)
                if execution is None:
                    self._send_json(404, {"error": "execution_not_found"})
                    return
                if on_execution_opened is not None:
                    on_execution_opened(execution)
                self._send_json(200, execution_payload(execution))

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == "/api/wallets":
                    self._handle_post_wallet()
                    return
                if parsed.path.startswith("/api/executions/") and parsed.path.endswith("/complete"):
                    self._handle_execution_complete(parsed.path)
                    return
                self._send_json(404, {"error": "not_found"})

            def _read_payload(self) -> dict[str, Any] | None:
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    return json.loads(self.rfile.read(length).decode("utf-8"))
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "invalid_json"})
                    return None

            def _handle_post_wallet(self) -> None:
                payload = self._read_payload()
                if payload is None:
                    return
                if payload.get("token") != import_token:
                    self._send_json(403, {"error": "forbidden"})
                    return
                label = str(payload.get("label", "")).strip()
                address = str(payload.get("address", "")).strip()
                keystore = payload.get("encrypted_keystore")
                if not label or not address or not isinstance(keystore, str):
                    self._send_json(400, {"error": "missing_fields"})
                    return
                try:
                    wallet = wallet_store.add_encrypted_wallet(address, label, keystore)
                except ValueError:
                    self._send_json(400, {"error": "invalid_address"})
                    return
                if on_wallet_imported is not None:
                    on_wallet_imported(wallet.address, wallet.label or "")
                self._send_json(200, {"ok": True, "address": wallet.address, "label": wallet.label})

            def _handle_execution_complete(self, path: str) -> None:
                payload = self._read_payload()
                if payload is None:
                    return
                if payload.get("token") != import_token:
                    self._send_json(403, {"error": "forbidden"})
                    return
                execution_id = path.split("/")[-2]
                hashes = payload.get("tx_hashes")
                if not isinstance(hashes, list):
                    self._send_json(400, {"error": "missing_hashes"})
                    return
                if pending_executions is not None:
                    pending_executions.remove(execution_id)
                if on_execution_completed is not None:
                    on_execution_completed(execution_id, [str(item) for item in hashes])
                self._send_json(200, {"ok": True})

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_html(self, body: str) -> None:
                data = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _send_json(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        return Handler


def execution_payload(execution: Any) -> dict[str, Any]:
    if execution.withdraw is not None:
        return withdraw_execution_payload(execution)
    if execution.proposal is None:
        raise ValueError("execution has no action")
    route = execution.proposal.route.raw
    tx = route.get("transactionRequest", {})
    action = route.get("action", {})
    estimate = route.get("estimate", {})
    from_token = action.get("fromToken", {})
    approval_address = estimate.get("approvalAddress")
    chain_id = int(action.get("fromChainId") or tx.get("chainId") or 0)
    approval = None
    if approval_address and from_token.get("address") and str(from_token.get("address")).lower() != "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee":
        approval = {
            "token": from_token.get("address"),
            "spender": approval_address,
            "amount": action.get("fromAmount"),
        }
    return {
        "id": execution.id,
        "wallet": execution.wallet,
        "label": execution.label,
        "encrypted_keystore": execution.encrypted_keystore,
        "chain_id": chain_id,
        "rpc_url": RPC_URL_BY_CHAIN_ID.get(chain_id),
        "approval": approval,
        "transaction": {
            "to": tx.get("to"),
            "data": tx.get("data"),
            "value": tx.get("value", "0x0"),
            "chainId": chain_id,
            "gasLimit": tx.get("gasLimit"),
            "gasPrice": tx.get("gasPrice"),
        },
    }


def withdraw_execution_payload(execution: Any) -> dict[str, Any]:
    withdraw = execution.withdraw
    asset = withdraw.asset
    chain_id = CHAIN_ID_BY_NAME.get(asset.chain, 0)
    amount = amount_to_units(asset.balance, asset.decimals)
    if asset.kind == TokenKind.ERC20:
        if not asset.token_address:
            raise ValueError("erc20 token address missing")
        to = asset.token_address
        data = erc20_transfer_data(withdraw.destination, amount)
        value = "0x0"
    else:
        to = withdraw.destination
        data = "0x"
        value = hex(int(amount))
    return {
        "id": execution.id,
        "type": "withdraw",
        "wallet": execution.wallet,
        "label": execution.label,
        "encrypted_keystore": execution.encrypted_keystore,
        "chain_id": chain_id,
        "rpc_url": RPC_URL_BY_CHAIN_ID.get(chain_id),
        "approval": None,
        "withdraw": {
            "token": asset.token,
            "chain": asset.chain,
            "amount": asset.balance,
            "destination": withdraw.destination,
        },
        "transaction": {
            "to": to,
            "data": data,
            "value": value,
            "chainId": chain_id,
            "gasLimit": None,
            "gasPrice": None,
        },
    }


def erc20_transfer_data(destination: str, amount: str) -> str:
    address = destination.removeprefix("0x").lower().rjust(64, "0")
    value = hex(int(amount)).removeprefix("0x").rjust(64, "0")
    return f"0xa9059cbb{address}{value}"


def import_page(label: str, token: str) -> str:
    safe_label = html.escape(label, quote=True)
    safe_token = html.escape(token, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Import Wallet</title>
  <script src="https://cdn.jsdelivr.net/npm/ethers@6.13.5/dist/ethers.umd.min.js"></script>
  <style>
    body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f7f7f2; color: #151515; }}
    main {{ max-width: 520px; margin: 0 auto; padding: 24px 18px; }}
    h1 {{ font-size: 24px; margin: 0 0 18px; }}
    label {{ display: block; font-size: 13px; margin: 14px 0 6px; color: #444; }}
    input, textarea {{ width: 100%; box-sizing: border-box; border: 1px solid #b8b8ad; border-radius: 6px; padding: 12px; font: inherit; background: white; }}
    textarea {{ min-height: 96px; resize: vertical; }}
    button {{ width: 100%; margin-top: 18px; border: 0; border-radius: 6px; padding: 13px; font: inherit; font-weight: 700; background: #176b5b; color: white; }}
    .note {{ font-size: 13px; line-height: 1.4; color: #555; margin-top: 12px; }}
    .status {{ margin-top: 14px; font-size: 14px; }}
  </style>
</head>
<body>
  <main>
    <h1>Import Wallet</h1>
    <form id="form">
      <label>Label</label>
      <input id="label" value="{safe_label}" required>
      <label>Private key</label>
      <textarea id="privateKey" autocomplete="off" autocapitalize="none" spellcheck="false" required></textarea>
      <label>Encryption password</label>
      <input id="password" type="password" autocomplete="new-password" required>
      <button type="submit">Encrypt and Save</button>
    </form>
    <p class="note">The private key is encrypted in this browser with ethers.js before upload. The server receives an encrypted keystore JSON.</p>
    <div id="status" class="status"></div>
  </main>
  <script>
    const token = "{safe_token}";
    const status = document.getElementById("status");
    document.getElementById("form").addEventListener("submit", async (event) => {{
      event.preventDefault();
      status.textContent = "Encrypting...";
      try {{
        const label = document.getElementById("label").value.trim();
        const privateKey = document.getElementById("privateKey").value.trim();
        const password = document.getElementById("password").value;
        const wallet = new ethers.Wallet(privateKey);
        const encrypted = await wallet.encrypt(password);
        status.textContent = "Saving...";
        const response = await fetch("/api/wallets", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            token,
            label,
            address: wallet.address,
            encrypted_keystore: encrypted
          }})
        }});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "save_failed");
        status.textContent = `Saved ${{result.address}}`;
        document.getElementById("privateKey").value = "";
        document.getElementById("password").value = "";
      }} catch (error) {{
        status.textContent = `Error: ${{error.message}}`;
      }}
    }});
  </script>
</body>
</html>"""


def execute_page(execution_id: str, token: str) -> str:
    safe_id = html.escape(execution_id, quote=True)
    safe_token = html.escape(token, quote=True)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Execute Transaction</title>
  <script src="https://cdn.jsdelivr.net/npm/ethers@6.13.5/dist/ethers.umd.min.js"></script>
  <style>
    body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f7f7f2; color: #151515; }}
    main {{ max-width: 520px; margin: 0 auto; padding: 24px 18px; }}
    h1 {{ font-size: 24px; margin: 0 0 18px; }}
    label {{ display: block; font-size: 13px; margin: 14px 0 6px; color: #444; }}
    input {{ width: 100%; box-sizing: border-box; border: 1px solid #b8b8ad; border-radius: 6px; padding: 12px; font: inherit; background: white; }}
    button {{ width: 100%; margin-top: 18px; border: 0; border-radius: 6px; padding: 13px; font: inherit; font-weight: 700; background: #176b5b; color: white; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #fff; border: 1px solid #d8d8ce; border-radius: 6px; padding: 12px; font-size: 12px; }}
    .status {{ margin-top: 14px; font-size: 14px; line-height: 1.4; }}
  </style>
</head>
<body>
  <main>
    <h1>Unlock & Execute</h1>
    <pre id="summary">Loading...</pre>
    <form id="form">
      <label>Encryption password</label>
      <input id="password" type="password" autocomplete="current-password" required>
      <button type="submit">Sign and Send</button>
    </form>
    <div id="status" class="status"></div>
  </main>
  <script>
    const executionId = "{safe_id}";
    const token = "{safe_token}";
    const status = document.getElementById("status");
    const summary = document.getElementById("summary");
    let payload = null;

    async function loadExecution() {{
      const response = await fetch(`/api/executions/${{executionId}}?token=${{encodeURIComponent(token)}}`);
      payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "load_failed");
      summary.textContent = JSON.stringify({{
        type: payload.type || "route",
        wallet: payload.wallet,
        chain_id: payload.chain_id,
        tx_to: payload.transaction.to,
        withdraw: payload.withdraw || null,
        approval: payload.approval ? {{ token: payload.approval.token, spender: payload.approval.spender }} : null
      }}, null, 2);
    }}

    document.getElementById("form").addEventListener("submit", async (event) => {{
      event.preventDefault();
      const txHashes = [];
      let provider = null;
      try {{
        status.textContent = "Decrypting keystore...";
        const password = document.getElementById("password").value;
        const wallet = await ethers.Wallet.fromEncryptedJson(payload.encrypted_keystore, password);
        if (wallet.address.toLowerCase() !== payload.wallet.toLowerCase()) {{
          throw new Error("wrong wallet password");
        }}
        if (!payload.rpc_url) {{
          throw new Error("rpc url not configured for chain");
        }}
        provider = new ethers.JsonRpcProvider(payload.rpc_url, payload.chain_id);
        const signer = wallet.connect(provider);
        if (payload.approval) {{
          status.textContent = "Checking allowance...";
          const abi = [
            "function allowance(address owner,address spender) view returns (uint256)",
            "function approve(address spender,uint256 amount) returns (bool)"
          ];
          const tokenContract = new ethers.Contract(payload.approval.token, abi, signer);
          const allowance = await tokenContract.allowance(payload.wallet, payload.approval.spender);
          const amount = BigInt(payload.approval.amount);
          if (allowance < amount) {{
            status.textContent = "Sending approval transaction...";
            const approveTx = await tokenContract.approve(payload.approval.spender, amount);
            txHashes.push(approveTx.hash);
            status.textContent = `Waiting approval: ${{approveTx.hash}}`;
            await approveTx.wait();
          }}
        }}
        status.textContent = payload.type === "withdraw" ? "Sending withdraw transaction..." : "Sending LI.FI transaction...";
        const tx = {{
          to: payload.transaction.to,
          data: payload.transaction.data,
          value: BigInt(payload.transaction.value || "0x0")
        }};
        if (payload.transaction.gasLimit) tx.gasLimit = BigInt(payload.transaction.gasLimit);
        if (payload.transaction.gasPrice) tx.gasPrice = BigInt(payload.transaction.gasPrice);
        const sent = await signer.sendTransaction(tx);
        txHashes.push(sent.hash);
        status.textContent = `Waiting transaction: ${{sent.hash}}`;
        await sent.wait();
        await completeExecution(txHashes);
        status.textContent = `Done: ${{txHashes.join(", ")}}`;
        document.getElementById("password").value = "";
      }} catch (error) {{
        const knownHash = await handleAlreadyKnown(error, provider, txHashes);
        if (knownHash) {{
          document.getElementById("password").value = "";
          return;
        }}
        status.textContent = `Error: ${{error.message}}`;
      }}
    }});

    async function completeExecution(txHashes) {{
      await fetch(`/api/executions/${{executionId}}/complete`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ token, tx_hashes: txHashes }})
      }});
    }}

    async function handleAlreadyKnown(error, provider, txHashes) {{
      const message = `${{error && (error.message || error)}}`;
      const raw = error?.payload?.params?.[0] || error?.error?.payload?.params?.[0];
      if (!message.includes("already known") || !raw || !provider) return null;
      const hash = ethers.keccak256(raw);
      if (!txHashes.includes(hash)) txHashes.push(hash);
      status.textContent = `Already submitted, waiting: ${{hash}}`;
      await provider.waitForTransaction(hash);
      await completeExecution(txHashes);
      status.textContent = `Done: ${{txHashes.join(", ")}}`;
      return hash;
    }}

    loadExecution().catch((error) => {{
      status.textContent = `Error: ${{error.message}}`;
    }});
  </script>
</body>
</html>"""
