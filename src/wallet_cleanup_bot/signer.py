from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


# Fallback RPCs per chain_id — tried in order if the primary node returns an error
_FALLBACK_RPCS: dict[int, list[str]] = {
    1: [
        "https://ethereum-rpc.publicnode.com",
        "https://eth.llamarpc.com",
        "https://rpc.ankr.com/eth",
        "https://cloudflare-eth.com",
    ],
    56: [
        "https://bsc-dataseed.binance.org",
        "https://bsc-dataseed1.binance.org",
        "https://bsc-dataseed2.binance.org",
        "https://bsc-dataseed3.binance.org",
        "https://bsc-rpc.publicnode.com",
    ],
    8453: [
        "https://mainnet.base.org",
        "https://base-rpc.publicnode.com",
        "https://base.llamarpc.com",
    ],
    42161: [
        "https://arb1.arbitrum.io/rpc",
        "https://arbitrum-one-rpc.publicnode.com",
        "https://rpc.ankr.com/arbitrum",
    ],
    10: [
        "https://mainnet.optimism.io",
        "https://optimism-rpc.publicnode.com",
        "https://rpc.ankr.com/optimism",
    ],
    137: [
        "https://polygon-rpc.com",
        "https://polygon-bor-rpc.publicnode.com",
        "https://rpc.ankr.com/polygon",
    ],
    43114: [
        "https://api.avax.network/ext/bc/C/rpc",
        "https://avalanche-c-chain-rpc.publicnode.com",
    ],
    59144: [
        "https://rpc.linea.build",
        "https://linea-rpc.publicnode.com",
    ],
    324: [
        "https://mainnet.era.zksync.io",
        "https://zksync-era-rpc.publicnode.com",
    ],
}


def address_from_key(private_key: str) -> str:
    from eth_account import Account
    return Account.from_key(_normalize_key(private_key)).address


def execute_with_key(private_key: str, payload: dict[str, Any]) -> list[str]:
    from eth_account import Account
    key = _normalize_key(private_key)
    account = Account.from_key(key)

    primary_rpc = payload.get("rpc_url")
    chain_id = int(payload["chain_id"])

    rpc_candidates = _rpc_list(primary_rpc, chain_id)
    if not rpc_candidates:
        raise ValueError("RPC URL not configured for this chain")

    rpc_url = _pick_working_rpc(rpc_candidates)

    wallet = payload.get("wallet", "")
    if wallet and account.address.lower() != wallet.lower():
        raise ValueError("Private key does not match wallet address")

    tx_hashes: list[str] = []

    approval = payload.get("approval")
    if approval:
        allowance = _erc20_allowance(rpc_url, approval["token"], account.address, approval["spender"])
        if allowance < int(approval["amount"]):
            approve_hash = _sign_and_send(
                account, rpc_url, chain_id,
                to=_checksum(approval["token"]),
                value=0,
                data=_approve_calldata(approval["spender"], int(approval["amount"])),
                gas_limit=None,
                gas_price=None,
            )
            tx_hashes.append(approve_hash)
            _wait_for_receipt(rpc_url, approve_hash)

    tx = payload["transaction"]
    value_raw = tx.get("value", "0x0")
    if isinstance(value_raw, str) and value_raw.startswith("0x"):
        value = int(value_raw, 16)
    else:
        value = int(value_raw or 0)

    main_hash = _sign_and_send(
        account, rpc_url, chain_id,
        to=tx["to"],
        value=value,
        data=tx.get("data") or "0x",
        gas_limit=tx.get("gasLimit"),
        gas_price=tx.get("gasPrice"),
    )
    tx_hashes.append(main_hash)
    return tx_hashes


def _rpc_list(primary: str | None, chain_id: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for url in ([primary] if primary else []) + _FALLBACK_RPCS.get(chain_id, []):
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _pick_working_rpc(candidates: list[str]) -> str:
    last_err: Exception = RuntimeError("no RPC candidates")
    for url in candidates:
        try:
            _rpc(url, "eth_blockNumber", [])
            return url
        except Exception as err:
            last_err = err
    raise ValueError(f"All RPC endpoints failed. Last error: {last_err}")


def _normalize_key(key: str) -> str:
    key = key.strip()
    if not key.startswith("0x"):
        key = "0x" + key
    return key


def _checksum(address: str) -> str:
    from eth_utils import to_checksum_address
    return to_checksum_address(address)


def _sign_and_send(
    account: Any,
    rpc_url: str,
    chain_id: int,
    to: str,
    value: int,
    data: str,
    gas_limit: str | int | None,
    gas_price: str | int | None,
) -> str:
    nonce = int(_rpc(rpc_url, "eth_getTransactionCount", [account.address, "latest"]), 16)
    gp = int(_rpc(rpc_url, "eth_gasPrice", []), 16)
    if gas_price:
        gp = int(gas_price, 16) if isinstance(gas_price, str) and gas_price.startswith("0x") else int(gas_price)

    to_addr = _checksum(to)
    tx: dict[str, Any] = {
        "to": to_addr,
        "value": value,
        "data": data,
        "nonce": nonce,
        "gasPrice": gp,
        "chainId": chain_id,
    }

    if gas_limit:
        tx["gas"] = int(gas_limit, 16) if isinstance(gas_limit, str) and gas_limit.startswith("0x") else int(gas_limit)
    else:
        estimated = _rpc(rpc_url, "eth_estimateGas", [{"to": to_addr, "data": data, "value": hex(value), "from": account.address}])
        tx["gas"] = int(estimated, 16) + 5000

    signed = account.sign_transaction(tx)
    raw = "0x" + signed.rawTransaction.hex()
    return _rpc(rpc_url, "eth_sendRawTransaction", [raw])


def _erc20_allowance(rpc_url: str, token: str, owner: str, spender: str) -> int:
    owner_hex = owner.removeprefix("0x").lower().rjust(64, "0")
    spender_hex = spender.removeprefix("0x").lower().rjust(64, "0")
    data = f"0xdd62ed3e{owner_hex}{spender_hex}"
    result = _rpc(rpc_url, "eth_call", [{"to": token, "data": data}, "latest"])
    return int(result, 16)


def _approve_calldata(spender: str, amount: int) -> str:
    spender_hex = spender.removeprefix("0x").lower().rjust(64, "0")
    amount_hex = hex(amount).removeprefix("0x").rjust(64, "0")
    return f"0x095ea7b3{spender_hex}{amount_hex}"


def _wait_for_receipt(rpc_url: str, tx_hash: str, timeout_s: int = 180) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            receipt = _rpc(rpc_url, "eth_getTransactionReceipt", [tx_hash])
            if receipt is not None:
                return
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f"tx {tx_hash} not mined after {timeout_s}s")


def _rpc(rpc_url: str, method: str, params: list[Any]) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        rpc_url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
    if "error" in result:
        raise ValueError(f"RPC {method}: {result['error']}")
    return result["result"]
