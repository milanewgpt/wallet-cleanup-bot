from __future__ import annotations

from .config import load_config_from_env
from .logging_store import JsonlLogStore
from .demo_providers import DemoApprovals, DemoExecutor, DemoFees, DemoRisk, DemoRouter, DemoScanner, EmptyScanner
from .execution_store import PendingExecutionStore
from .live_scanner import LiveNativeScanner
from .lifi_router import DisabledExecutionProvider, LifiRouteProvider
from .moralis_scanner import CompositeScanner, MoralisErc20Scanner
from .pipeline import CleanupPipeline
from .scan_store import ScanStore
from .telegram_bot import TelegramBotApp
from .telegram_gateway import TelegramApiClient, TelegramSettings
from .wallet_store import WalletStore
from .webapp_server import WalletImportServer


def main() -> int:
    config = load_config_from_env()
    if not config.telegram_bot_token or not config.telegram_chat_id:
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env or environment.")
        return 2

    settings = TelegramSettings(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
        allowed_user_id=config.telegram_allowed_user_id,
    )

    def pipeline_factory(wallet: str) -> CleanupPipeline:
        scanners = []
        if config.live_native_scanner_enabled:
            scanners.append(LiveNativeScanner())
        if config.moralis_erc20_scanner_enabled and config.moralis_api_key:
            scanners.append(MoralisErc20Scanner(config.moralis_api_key))
        scanner = CompositeScanner(scanners) if scanners else EmptyScanner()
        if config.demo_data_enabled:
            scanner = DemoScanner()
        router = DemoRouter()
        executor = DemoExecutor()
        if config.live_routes_enabled and not config.demo_data_enabled:
            router = LifiRouteProvider(
                from_address=wallet,
                api_key=config.lifi_api_key,
                slippage=config.lifi_slippage,
            )
            executor = DisabledExecutionProvider()
        return CleanupPipeline(
            config=config,
            scanner=scanner,
            fee_estimator=DemoFees(),
            risk_provider=DemoRisk(),
            router=router,
            approvals=DemoApprovals(),
            executor=executor,
            log_store=JsonlLogStore(config.log_path),
        )

    wallet_store = WalletStore(config.wallet_store_path)
    telegram_client = TelegramApiClient(settings.bot_token)
    pending_executions = PendingExecutionStore()
    scan_store = ScanStore()
    WalletImportServer(
        config.webapp_host,
        config.webapp_port,
        wallet_store,
        config.webapp_import_token,
        pending_executions=pending_executions,
        on_wallet_imported=lambda address, label: telegram_client.send_message(
            settings.chat_id,
            f"Wallet imported: <code>{address}</code> - {label}",
        ),
        on_execution_opened=lambda execution: telegram_client.delete_message(
            execution.message_chat_id or settings.chat_id,
            execution.message_id,
        )
        if execution.message_id is not None
        else None,
        on_execution_completed=lambda execution_id, hashes: telegram_client.send_message(
            settings.chat_id,
            f"Execution completed <code>{execution_id}</code>: <code>{', '.join(hashes)}</code>",
        ),
    ).start_background()

    app = TelegramBotApp(
        settings=settings,
        config=config,
        wallet_store=wallet_store,
        pipeline_factory=pipeline_factory,
        client=telegram_client,
        pending_executions=pending_executions,
        scan_store=scan_store,
    )
    app.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
