from __future__ import annotations

import tempfile
import unittest

from wallet_cleanup_bot.wallet_store import WalletStore, normalize_wallet


ADDRESS = "0x0000000000000000000000000000000000000001"


class WalletStoreTest(unittest.TestCase):
    def test_add_list_remove_wallet(self) -> None:
        with tempfile.NamedTemporaryFile() as handle:
            store = WalletStore(handle.name)
            store.add_wallet(ADDRESS, "main")

            wallets = store.list_wallets()
            self.assertEqual(len(wallets), 1)
            self.assertEqual(wallets[0].label, "main")

            removed = store.remove_wallet("1")
            self.assertIsNotNone(removed)
            self.assertEqual(store.list_wallets(), [])

    def test_invalid_wallet_rejected(self) -> None:
        with self.assertRaises(ValueError):
            normalize_wallet("0x123")

    def test_add_encrypted_wallet(self) -> None:
        with tempfile.NamedTemporaryFile() as handle:
            store = WalletStore(handle.name)
            store.add_encrypted_wallet(ADDRESS, "main", '{"crypto":{}}')

            wallets = store.list_wallets()
            self.assertEqual(wallets[0].address, ADDRESS)
            self.assertEqual(wallets[0].encrypted_keystore, '{"crypto":{}}')

    def test_resolve_wallet_by_label(self) -> None:
        with tempfile.NamedTemporaryFile() as handle:
            store = WalletStore(handle.name)
            store.add_encrypted_wallet(ADDRESS, "Game", '{"crypto":{}}')

            wallet = store.resolve_wallet("game")
            self.assertIsNotNone(wallet)
            self.assertEqual(wallet.address, ADDRESS)


if __name__ == "__main__":
    unittest.main()
