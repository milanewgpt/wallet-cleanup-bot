# Wallet Cleanup Bot

A Telegram bot for safely cleaning up small EVM wallet balances through an approval-based flow.

Pipeline:

1. `scan` — collect native/ERC-20 balances across EVM chains.
2. `normalize` — convert assets into a unified structure and estimate gas, liquidity, and risk.
3. `filter` — apply protected gas chains, thresholds, and cleanup economics.
4. `route` — request a swap/bridge/swap+bridge route.
5. `proposal` — show actions to the user one by one.
6. `approve/execute` — execute only approved items and write an execution log.

## Status

Implemented components:

- Telegram bot
- encrypted wallet import form
- live native/ERC-20 scan
- LI.FI route proposals
- approval flow
- browser-side signing/execution
- direct withdraw flow

## Quick start

```bash
python3 -m py_compile src/wallet_cleanup_bot/*.py
PYTHONPATH=src python3 -m unittest discover -s tests
```

Run the Telegram bot:

```bash
set -a
. ./.env
set +a
PYTHONPATH=src python3 -m wallet_cleanup_bot.main
```

## Telegram setup

1. Create a bot via `@BotFather` and put the token in `TELEGRAM_BOT_TOKEN`.
2. Send any message to the bot.
3. Get `chat_id` through the Bot API:

```bash
curl "https://api.telegram.org/bot<token>/getUpdates"
```

4. Fill `.env` using `.env.example` as a template:

```bash
TELEGRAM_BOT_TOKEN=123:abc
TELEGRAM_CHAT_ID=123456789
TELEGRAM_ALLOWED_USER_ID=123456789
```

`.env` is included in `.gitignore`; tokens must not be committed to the repository.

5. Start the bot:

```bash
set -a
. ./.env
set +a
PYTHONPATH=src python3 -m wallet_cleanup_bot.main
```

## Runtime flags

`DEMO_DATA_ENABLED=false` by default so the bot does not show hardcoded demo balances as real wallet data.

`LIVE_NATIVE_SCANNER_ENABLED=true` enables real native balance scanning through public RPCs for Ethereum, Base, Arbitrum, Optimism, Polygon, BNB, Avalanche, Linea, and zkSync. ERC-20 scanning requires a separate indexer API.

`MORALIS_ERC20_SCANNER_ENABLED=true` enables ERC-20 balances through the Moralis Token Balances endpoint.

`LIVE_ROUTES_ENABLED=true` enables LI.FI quote proposals. After `Approve`, the bot provides an `Unlock & Execute` link: the encrypted keystore is decrypted in the browser, and approval/route transactions are signed there.

## Telegram commands

- `/add_wallet label` — create an `Import key` button; the key is encrypted in the web/Mini App before being sent to the server.
- `/remove_wallet 1` or `/remove_wallet 0x...` — remove a wallet.
- `/wallets` — show saved wallets.
- `/check_wallet label`, `/check_wallet 1`, or `/check_wallet 0x...` — check a specific wallet.
- `/check_all` — check all saved wallets.

Private keys are never typed into Telegram messages. They are entered in the web/Mini App form, encrypted locally on the device with `ethers.Wallet.encrypt(password)`, and only the encrypted keystore JSON is stored on the server.

For each detected balance, the bot shows a card with buttons:

- `Find route` — find a swap/bridge route through LI.FI.
- `Withdraw` — enter a destination address in Telegram and open `Unlock & Send` for direct ERC-20/native withdrawal.
- `Skip` — close the card.

For mobile use, `WEBAPP_BASE_URL` must be a public HTTPS URL. Local `http://127.0.0.1:8787` is suitable only for server-side testing.

Current persistent URL:

```bash
WEBAPP_BASE_URL=https://guacamole60977.hostkey.in
```

It is proxied through the existing nginx-certbot container to the local web server at `127.0.0.1:8787`.

## Filtering rules

- In protected gas chains, the native token is not touched while its value is below the threshold.
- If the native token in a protected chain is above the threshold, the bot proposes cleaning up only the excess.
- ERC-20 tokens can be processed in both protected and regular chains.
- An asset is skipped if its value is below the gas fee, there is no liquidity, or the token looks suspicious.
- Approval is always item-by-item: `approve`, `skip`, `blacklist_token`, `change_threshold`.
