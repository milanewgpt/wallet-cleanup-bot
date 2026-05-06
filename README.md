# Wallet Cleanup Bot

Бот для аккуратной зачистки мелких EVM-балансов через Telegram approve-flow.

Пайплайн:

1. `scan` — собрать native/ERC-20 балансы по EVM-сетям.
2. `normalize` — привести активы к единой структуре, оценить gas/liquidity/risk.
3. `filter` — применить protected gas chains, threshold и экономику.
4. `route` — запросить маршрут swap/bridge/swap+bridge.
5. `proposal` — показать пользователю действия поштучно.
6. `approve/execute` — исполнить только одобренные пункты и записать лог.

## Статус

Подключены Telegram bot, encrypted wallet import form, live native/ERC-20 scan, LI.FI route proposals, approve flow, browser-side signing/execution и direct withdraw.

## Быстрый запуск

```bash
python3 -m py_compile src/wallet_cleanup_bot/*.py
PYTHONPATH=src python3 -m unittest discover -s tests
```

Запуск Telegram bot:

```bash
set -a
. ./.env
set +a
PYTHONPATH=src python3 -m wallet_cleanup_bot.main
```

## Telegram

1. Создай бота через `@BotFather` и положи токен в `TELEGRAM_BOT_TOKEN`.
2. Напиши боту любое сообщение.
3. Получи `chat_id` через Bot API:

```bash
curl "https://api.telegram.org/bot<token>/getUpdates"
```

4. Заполни `.env` по примеру `.env.example`:

```bash
TELEGRAM_BOT_TOKEN=123:abc
TELEGRAM_CHAT_ID=123456789
TELEGRAM_ALLOWED_USER_ID=123456789
```

`.env` добавлен в `.gitignore`; токены не должны попадать в репозиторий.

5. Запусти бота:

```bash
set -a
. ./.env
set +a
PYTHONPATH=src python3 -m wallet_cleanup_bot.main
```

`DEMO_DATA_ENABLED=false` по умолчанию, чтобы бот не показывал hardcoded demo balances как реальные данные кошелька.

`LIVE_NATIVE_SCANNER_ENABLED=true` включает real native balance scan через public RPC для Ethereum, Base, Arbitrum, Optimism, Polygon, BNB, Avalanche, Linea и zkSync. ERC-20 scanner требует отдельный indexer API.

`MORALIS_ERC20_SCANNER_ENABLED=true` включает ERC-20 balances через Moralis Token Balances endpoint.

`LIVE_ROUTES_ENABLED=true` включает LI.FI quote proposals. После `Approve` бот дает ссылку `Unlock & Execute`: encrypted keystore расшифровывается в браузере, там же подписываются approval/route транзакции.

## Telegram commands

- `/add_wallet label` — создать кнопку `Import key`; ключ шифруется в web/Mini App до отправки на сервер.
- `/remove_wallet 1` или `/remove_wallet 0x...` — удалить кошелек.
- `/wallets` — показать сохраненные кошельки.
- `/check_wallet label`, `/check_wallet 1` или `/check_wallet 0x...` — запустить проверку по конкретному кошельку.
- `/check_all` — проверить все сохраненные кошельки.

Приватные ключи не вводятся в Telegram-сообщение. Они вводятся в web/Mini App форму, шифруются на устройстве через `ethers.Wallet.encrypt(password)`, и на сервер сохраняется только encrypted keystore JSON.

Для каждого найденного баланса бот показывает карточку с кнопками:

- `Find route` — найти маршрут swap/bridge через LI.FI.
- `Withdraw` — указать адрес в Telegram и открыть `Unlock & Send` для прямого ERC-20/native вывода.
- `Skip` — закрыть карточку.

Для телефона нужен публичный HTTPS `WEBAPP_BASE_URL`. Локальный `http://127.0.0.1:8787` подходит только для проверки на сервере.

Текущий постоянный URL:

```bash
WEBAPP_BASE_URL=https://guacamole60977.hostkey.in
```

Он проксируется через существующий nginx-certbot контейнер на локальный web server `127.0.0.1:8787`.

## Правила фильтрации

- В protected gas chains native token не трогается, пока значение ниже threshold.
- Если native token в protected chain выше threshold, предлагается cleanup excess.
- ERC-20 можно обрабатывать и в protected, и в обычных сетях.
- Актив пропускается, если value меньше gas fee, нет ликвидности или токен подозрительный.
- Approve всегда поштучный: `approve`, `skip`, `blacklist_token`, `change_threshold`.
