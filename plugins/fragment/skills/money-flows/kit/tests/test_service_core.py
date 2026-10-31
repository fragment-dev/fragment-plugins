"""The scaffold's guarantees, on a tiny service over the demo schema (local ledger).

    python3 -m unittest discover -s tests   (from skills/money-flows/kit)
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "fragment_kit")]
from ledger import LocalLedger                     # noqa: E402
from demo_schema import WALLET, schema                          # noqa: E402
from primitives import doubling_params                          # noqa: E402
from service_core import Plan, Rejected, ServiceCore, lid      # noqa: E402


class Crash(Exception):
    pass


class Demo(ServiceCore):
    ROLES = ("party", "platform")
    DB_SCHEMA = "CREATE TABLE IF NOT EXISTS holds (hold_id TEXT PRIMARY KEY, party TEXT, amount INTEGER, status TEXT);"

    def deposit(self, op):
        def plan(op, now, actor):
            if not isinstance(op.get("amount"), int) or op["amount"] < 1:
                raise Rejected("invalid_amount")
            p = Plan(result={"request_id": op["request_id"]})
            p.entry(f"dep-{lid(op['request_id'])}", "deposited",
                    {"request_id": lid(op["request_id"]), "party_id": lid(actor["id"]), "amount": op["amount"]})
            return p
        return self.run(op, "deposit", plan, roles=("party",))

    def hold(self, op):
        def plan(op, now, actor):
            if self.bal(WALLET.replace("{{party_id}}", lid(actor["id"]))) < op["amount"]:
                raise Rejected("insufficient_funds")
            if self.one("SELECT 1 FROM holds WHERE hold_id = ?", op["hold_id"]):
                raise Rejected("hold_id_in_use")
            p = Plan(result={"hold_id": op["hold_id"]})
            p.entry(f"hold-{lid(op['hold_id'])}", "held",
                    {"hold_id": lid(op["hold_id"]), "party_id": lid(actor["id"]), "amount": op["amount"]})
            p.write("INSERT INTO holds VALUES (?, ?, ?, 'held')", op["hold_id"], actor["id"], op["amount"])
            return p
        return self.run(op, "hold", plan, roles=("party",))


class Scaffold(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.schema = d / "demo.jsonc"
        self.schema.write_text(json.dumps(schema("kit-demo")))
        self.L = LocalLedger(self.schema, d / "ledger.db")
        self.db = d / "svc.db"
        self.crash_at = None
        self.svc = self.start()
        self.n = 0

    def start(self):
        def failpoint(name):
            if self.crash_at and name.startswith(self.crash_at):
                self.crash_at = None
                raise Crash(name)
        return Demo(self.db, self.L, self.schema, failpoint=failpoint)

    def op(self, name, actor="alice", op_id=None, now=1000, **kw):
        """A retry resends the identical request, `now` included: it's part of what the ID names."""
        self.n += 1
        return getattr(self.svc, name)({"operation_id": op_id or f"o{self.n}", "now": now,
                                        "actor": {"role": "party", "id": actor}, **kw})

    def wallet(self, who):
        p = WALLET.replace("{{party_id}}", who)
        return self.L.balances([p])[p], self.svc.bal(p)

    def test_replay_and_reuse(self):
        first = self.op("deposit", op_id="d1", request_id="r1", amount=500)
        self.assertEqual(first["status"], "accepted")
        self.assertEqual(self.op("deposit", op_id="d1", request_id="r1", amount=500), first)
        self.assertEqual(self.op("deposit", op_id="d1", request_id="r1", amount=501)["reason"], "operation_id_reused")
        self.assertEqual(self.op("deposit", op_id="d1", now=1001, request_id="r1", amount=500)["reason"], "operation_id_reused")
        self.assertEqual(self.wallet("alice"), (500, 500))

    def test_rejection_has_no_effect(self):
        self.op("deposit", request_id="r2", amount=100)
        self.assertEqual(self.op("hold", hold_id="h1", amount=101)["reason"], "insufficient_funds")
        self.assertEqual(self.op("hold", actor="bob", op_id="x", hold_id="h1", amount=1)["reason"], "insufficient_funds")
        self.assertEqual(self.wallet("alice"), (100, 100))

    def test_ledger_refusal_is_a_rejection_with_no_effect(self):
        """The service's own check is skipped here (a bug): the ledger still refuses, and nothing changes."""
        self.op("deposit", request_id="r3", amount=100)
        self.svc.bal = lambda path: 10 ** 9                               # a buggy balance check
        out = self.op("hold", hold_id="h2", amount=500)
        self.assertEqual((out["status"], out["reason"]), ("rejected", "ledger_rejected"))
        self.assertEqual(self.L.balances([WALLET.replace("{{party_id}}", "alice")])[WALLET.replace("{{party_id}}", "alice")], 100)
        self.assertIsNone(self.svc.one("SELECT * FROM holds WHERE hold_id = 'h2'"))

    def test_crash_after_post_and_before_commit_recovers_once(self):
        self.op("deposit", request_id="r4", amount=1000)
        for point in ("after_post", "before_commit"):
            self.crash_at = point
            with self.assertRaises(Crash):
                self.op("hold", op_id=f"hold-{point}", hold_id=f"h-{point}", amount=100)
            self.svc = self.start()                                     # restart: recovery finishes it
            self.assertEqual(self.svc.one("SELECT status FROM holds WHERE hold_id = ?", f"h-{point}")["status"], "held")
            again = self.op("hold", op_id=f"hold-{point}", hold_id=f"h-{point}", amount=100)
            self.assertEqual(again["status"], "accepted")               # the replay answers, doesn't repeat
        self.assertEqual(self.wallet("alice"), (800, 800))


if __name__ == "__main__":
    unittest.main()
