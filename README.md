# Wallet Cleanup Bot

Wallet cleanup assistant bot for checking wallets, listing tracked wallets, and running cleanup/status checks across configured addresses. It helps identify wallets that need attention or cleanup actions.

## Features

- Tracks configured wallets and wallet status.
- Provides commands to add, remove, list, check one wallet, or check all wallets.
- Documents wallet/API configuration without committing sensitive data.

## Architecture

- **Repository:** `MilaArtyNew/wallet-cleanup-bot`
- **Primary stack:** Python, Docker, systemd, Railway

## Configuration

Configure the service with environment variables. Do not commit real secrets to the repository.

- `ALCHEMY_API_KEY` — required or optional runtime configuration. See deployment environment for the actual value.
- `DEFAULT_GAS_THRESHOLD_USD` — required or optional runtime configuration. See deployment environment for the actual value.
- `DEMO_DATA_ENABLED` — required or optional runtime configuration. See deployment environment for the actual value.
- `LIFI_API_KEY` — required or optional runtime configuration. See deployment environment for the actual value.
- `LIFI_SLIPPAGE` — required or optional runtime configuration. See deployment environment for the actual value.
- `LIVE_NATIVE_SCANNER_ENABLED` — required or optional runtime configuration. See deployment environment for the actual value.
- `LIVE_ROUTES_ENABLED` — required or optional runtime configuration. See deployment environment for the actual value.
- `LOG_PATH` — required or optional runtime configuration. See deployment environment for the actual value.
- `MORALIS_API_KEY` — required or optional runtime configuration. See deployment environment for the actual value.
- `MORALIS_ERC20_SCANNER_ENABLED` — required or optional runtime configuration. See deployment environment for the actual value.
- `TARGET_CHAIN` — required or optional runtime configuration. See deployment environment for the actual value.
- `TARGET_TOKEN` — required or optional runtime configuration. See deployment environment for the actual value.
- `TELEGRAM_ALLOWED_USER_ID` — required or optional runtime configuration. See deployment environment for the actual value.
- `TELEGRAM_BOT_TOKEN` — required or optional runtime configuration. See deployment environment for the actual value.
- `TELEGRAM_CHAT_ID` — required or optional runtime configuration. See deployment environment for the actual value.
- `WALLET_STORE_PATH` — required or optional runtime configuration. See deployment environment for the actual value.
- `WEBAPP_BASE_URL` — required or optional runtime configuration. See deployment environment for the actual value.
- `WEBAPP_HOST` — required or optional runtime configuration. See deployment environment for the actual value.
- `WEBAPP_IMPORT_TOKEN` — required or optional runtime configuration. See deployment environment for the actual value.
- `WEBAPP_PORT` — required or optional runtime configuration. See deployment environment for the actual value.

## Setup

```bash
git clone https://github.com/MilaArtyNew/wallet-cleanup-bot
cd wallet-cleanup-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
```

## Running Locally

```bash
python main.py
```

## Bot Commands

No interactive Telegram commands were detected automatically. If this service sends alerts only, document the operational controls here when they are added.

If a command requires extra input and the argument is missing, the bot should ask a follow-up question instead of failing silently.

## Deployment Notes

- Keep secrets in the deployment platform environment variables, not in Git.
- Use the default branch as the source of truth for deployments.
- Check logs after every deployment and verify the `/status` or health endpoint when available.
- If the project uses a scheduler, verify timezone assumptions and idempotency before enabling it in production.

## Operational Notes

- Review logs after startup for missing environment variables or API authentication errors.
- Keep command names in English and document every user-facing command in this README.
- For Telegram bots, `/help` should list the same commands documented here.
- Inline buttons should edit the original message with the final status rather than sending duplicate messages.

## Troubleshooting

- **Bot does not respond:** verify the bot token, webhook/polling mode, and chat permissions.
- **Missing data:** check API keys, rate limits, and upstream service status.
- **Deployment starts but exits:** inspect platform logs for missing environment variables or import errors.
- **Commands differ from README:** update the command list here and in the bot command menu at the same time.

## Security

- Never commit `.env` files, API keys, private keys, Telegram tokens, or session strings.
- Use `.env.example` for placeholders only.
- Rotate any credential that was accidentally committed.
