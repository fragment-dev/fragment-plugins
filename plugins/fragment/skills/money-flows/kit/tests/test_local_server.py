"""The local Fragment endpoint answers the SDK's calls as Fragment does (no network beyond 127.0.0.1)."""

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "fragment_kit"))
from ledger import load_schema          # noqa: E402
from local_server import Api, Ledgers, serve      # noqa: E402

SCHEMA = KIT.parent / "quickstart" / "credits-schema.jsonc"

# The documents the Node SDK (@fragment-dev/node-client) sends, trimmed to what the answers are checked for.
ADD = """mutation addLedgerEntry($ik: SafeString!, $ledgerIk: SafeString!, $type: String!, $typeVersion: Int,
  $parameters: JSON!) { addLedgerEntry(ik: $ik, entry: { ledger: { ik: $ledgerIk } type: $type
  typeVersion: $typeVersion parameters: $parameters }) { __typename ... on AddLedgerEntryResult { isIkReplay
  entry { ik } lines { amount account { path } } } ... on BadRequestError { code message retryable } } }"""
BALANCE = """query getLedgerAccountBalance($path: String!, $ledgerIk: SafeString!) {
  ledgerAccount(ledgerAccount: { ledger: { ik: $ledgerIk }, path: $path }) { path balance } }"""
ENTRIES = """query listLedgerEntries($ledgerIk: SafeString!) { ledger(ledger: { ik: $ledgerIk }) {
  ledgerEntries { nodes { ik lines { nodes { amount } } } } } }"""
WALLET = "liabilities/wallets/wallet:w1/purchased"


class LocalServerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        ledgers = Ledgers(Path(self.dir))
        key = ledgers.store_schema(load_schema(SCHEMA))["key"]
        ledgers.create("credits", "Credits", key)
        self.server = serve(Api(ledgers), "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def gql(self, query, variables=None):
        req = urllib.request.Request(self.url + "/graphql", json.dumps({"query": query, "variables": variables or {}}).encode(),
                                     {"Content-Type": "application/json", "Authorization": "Bearer x"})
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    def add(self, ik, type_, **params):
        return self.gql(ADD, {"ik": ik, "ledgerIk": "credits", "type": type_, "parameters": params})["data"]["addLedgerEntry"]

    def buy(self, n, credits):
        return self.add(f"purchase-{n}", "credits_purchased", purchase_id=n, wallet_id="w1", credits=str(credits))

    def spend(self, n, credits):
        return self.add(f"usage-{n}", "credits_consumed", usage_id=n, wallet_id="w1", credits=str(credits))

    def balance(self):
        return self.gql(BALANCE, {"ledgerIk": "credits", "path": WALLET})["data"]["ledgerAccount"]["balance"]

    def test_token(self):
        req = urllib.request.Request(self.url + "/oauth2/token", b"grant_type=client_credentials&scope=x",
                                     {"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req) as r:
            body = json.load(r)
        self.assertTrue(body["access_token"])
        self.assertIsInstance(body["expires_in"], int)

    def test_post_replay_and_refusal(self):
        first = self.buy("p1", 100)
        self.assertEqual((first["__typename"], first["isIkReplay"]), ("AddLedgerEntryResult", False))
        self.assertIsInstance(first["lines"], list)                       # a list here, a page when read back
        self.assertTrue(self.buy("p1", 100)["isIkReplay"])
        refused = self.spend("u1", 150)
        self.assertEqual((refused["__typename"], refused["code"], refused["retryable"]),
                         ("BadRequestError", "conditional_request_failed", False))
        self.assertEqual(self.spend("u2", 60)["__typename"], "AddLedgerEntryResult")
        self.assertEqual(self.balance(), "40")

    def test_concurrent_spends_never_overdraw(self):
        self.buy("p1", 40)
        with ThreadPoolExecutor(20) as pool:
            results = list(pool.map(lambda i: self.spend(f"c{i}", 10)["__typename"], range(20)))
        self.assertEqual(results.count("AddLedgerEntryResult"), 4)
        self.assertEqual(results.count("BadRequestError"), 16)
        self.assertEqual(self.balance(), "0")

    def test_entries_read_back_page_their_lines(self):
        self.buy("p1", 10)
        nodes = self.gql(ENTRIES, {"ledgerIk": "credits"})["data"]["ledger"]["ledgerEntries"]["nodes"]
        self.assertEqual(nodes[0]["ik"], "purchase-p1")
        self.assertIn("nodes", nodes[0]["lines"])

    def test_unknown_ledger_and_unsupported_operation(self):
        r = self.gql(ADD, {"ik": "x", "ledgerIk": "nope", "type": "credits_consumed", "parameters": {}})
        self.assertEqual(r["data"]["addLedgerEntry"]["code"], "not_found")
        r = self.gql("query getPayment($ik: SafeString!) { payment(payment: { ik: $ik }) { id } }", {"ik": "x"})
        self.assertIn("isn't supported by the local Fragment endpoint", r["errors"][0]["message"])

    def test_survives_restart(self):
        self.buy("p1", 30)
        self.tearDown()
        ledgers = Ledgers(Path(self.dir))               # same directory, new server
        self.server = serve(Api(ledgers), "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.assertEqual(self.balance(), "30")
        self.assertTrue(self.buy("p1", 30)["isIkReplay"])


if __name__ == "__main__":
    unittest.main()
