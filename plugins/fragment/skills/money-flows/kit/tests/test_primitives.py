"""Attacks every primitive in the demo schema. Local by default; KIT_FRAGMENT=<ledger ik> runs the same
attacks on a Fragment dev ledger created from the demo schema.

    python3 -m unittest discover -s tests   (from skills/money-flows/kit)
"""

import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "fragment_kit"))
from ledger import FragmentLedger, LocalLedger      # noqa: E402
from demo_schema import schema                                  # noqa: E402
from primitives import bps_params, doubling_params              # noqa: E402

ON = os.environ.get("KIT_FRAGMENT")


class Primitives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = Path(tempfile.mkdtemp())
        (d / "demo.jsonc").write_text(json.dumps(schema("kit-demo")))
        cls.L = FragmentLedger(ON) if ON else LocalLedger(d / "demo.jsonc", d / "ledger.db")
        cls.rid = uuid.uuid4().hex[:6]
        cls.n = 0
        if not cls.L.balances(["liabilities/kit-consts/pow:39"])["liabilities/kit-consts/pow:39"]:
            assert cls.post_("kit_consts_based", {}).ok
            for chunk in doubling_params(1):
                assert cls.post_("kit_consts_doubled", chunk).ok
            for chunk in doubling_params(10000):
                assert cls.post_("kit_consts10k_doubled", chunk).ok
        cls.rate = f"r{cls.rid}"
        assert cls.post_("fee_rate_set", {"rate_id": cls.rate, "value": "250", **cls.op()}).ok
        for chunk in doubling_params(250):
            assert cls.post_("fee_rate_doubled", {"rate_id": cls.rate, **chunk}).ok

    @classmethod
    def op(cls, n=0):
        cls.n += 1
        return {"operation_id": f"op{cls.rid}-{cls.n}", "check_n": str(n)}

    @classmethod
    def post_(cls, type_, params):
        cls.n += 1
        return cls.L.post(f"k{cls.rid}-{cls.n}", type_, params)

    def ok(self, type_, params):
        r = self.post_(type_, params)
        self.assertTrue(r.ok, f"{type_} refused: {r.code} {r.message}")

    def refused(self, type_, params):
        r = self.post_(type_, params)
        self.assertFalse(r.ok, f"{type_} was accepted")
        self.assertEqual(r.code, "conditional_request_failed", r.message)

    def bal(self, path):
        return self.L.balances([path])[path]

    def prove_fee(self, hold, amount, tamper=None):
        p, r, fee = bps_params(amount, 250)
        p |= {"rate_id": self.rate, "hold_id": hold, **self.op()}
        r |= {"hold_id": hold, **self.op()}
        if tamper:
            tamper(p, r)
        return p, r, fee

    # -------------------------------------------------------------- proved arithmetic

    def test_fee_proved_half_up(self):
        for amount, want in ((12_345, 309), (10_000, 250), (1, 0), (2, 0), (20, 1), (99_999_999, 2_500_000)):
            h = f"h{self.rid}-{amount}"
            p, r, fee = self.prove_fee(h, amount)
            self.assertEqual(fee, want)
            self.ok("fee_product", p)
            self.ok("fee_rounded", r)
            self.assertEqual(self.bal(f"liabilities/fee-proofs/hold:{h}/result"), want)

    def test_wrong_rounding_refused(self):
        h = f"h{self.rid}-round"
        p, r, fee = self.prove_fee(h, 12_345)
        self.ok("fee_product", p)
        for wrong in (fee - 1, fee + 1):
            _, r2, _ = bps_params(wrong * 10000 // 250 if wrong else 0, 250)
            bad = dict(r, result=str(wrong), scaled=str(wrong * 10000),
                       items=[{"j": str(j), "qa": str(1 << j), "qb": str(10000 << j)} for j in range(40) if wrong >> j & 1],
                       **self.op())
            self.refused("fee_rounded", bad)

    def test_wrong_product_refused(self):
        h = f"h{self.rid}-prod"
        self.refused("fee_product", self.prove_fee(h, 12_345, lambda p, r: p.update(product=str(12_345 * 250 + 1)))[0])
        # a table value that isn't the stored one
        self.refused("fee_product", self.prove_fee(h, 12_345, lambda p, r: p["items"][0].update(qb=str(int(p["items"][0]["qb"]) + 1)))[0])
        # a rate that isn't the stored one
        self.refused("fee_product", self.prove_fee(h, 12_345, lambda p, r: p.update(rate="300"))[0])

    def test_forged_table_refused(self):
        r = f"rf{self.rid}"
        self.ok("fee_rate_set", {"rate_id": r, "value": "100", **self.op()})
        params = doubling_params(100)[0]
        params["items"][3]["v"] = str(int(params["items"][3]["v"]) + 1)      # not 2 x half
        self.refused("fee_rate_doubled", {"rate_id": r, **params})
        params = doubling_params(100)[0]
        params["items"][5]["half"] = str(int(params["items"][5]["half"]) * 2)   # half isn't the value at h
        params["items"][5]["v"] = str(int(params["items"][5]["half"]) * 2)
        self.refused("fee_rate_doubled", {"rate_id": r, **params})
        later = doubling_params(100)[1]                                     # a chunk that skips its predecessor
        self.refused("fee_rate_doubled", {"rate_id": r, **later})
        self.refused("fee_rate_set", {"rate_id": f"rx{self.rid}", "value": "10001", **self.op()})   # above 100%

    # -------------------------------------------------------------- guards

    def test_hold_and_release(self):
        a, b, h = f"a{self.rid}", f"b{self.rid}", f"hr{self.rid}"
        self.ok("deposited", {"request_id": f"d{self.rid}", "party_id": a, "amount": "20000", **self.op()})
        self.refused("deposited", {"request_id": f"d{self.rid}", "party_id": a, "amount": "5", **self.op()})   # request once
        self.refused("held", {"hold_id": h, "party_id": a, "amount": "20001", **self.op()})                     # wallet >= 0
        self.refused("released", {"hold_id": h, "party_id": a, "payee_id": b, "amount": "0", "fee": "0", **self.op()})  # before hold
        self.ok("held", {"hold_id": h, "party_id": a, "amount": "12345", **self.op()})
        self.refused("held", {"hold_id": h, "party_id": a, "amount": "1", **self.op()})                         # hold once
        p, r, fee = self.prove_fee(h, 12_345)
        self.ok("fee_product", p)
        self.ok("fee_rounded", r)
        rel = {"hold_id": h, "party_id": a, "payee_id": b, "amount": "12345", "fee": str(fee), **self.op()}
        self.refused("released", dict(rel, fee=str(fee - 1), **self.op()))        # not the proved fee
        self.refused("released", dict(rel, amount="12344", **self.op()))          # not the held amount
        self.ok("released", rel)
        self.assertEqual(self.bal(f"liabilities/wallets/party:{b}"), 12_345 - 309)
        self.refused("released", dict(rel, **self.op()))                         # release once

    def test_shared_check_account_cant_hide_a_negative(self):
        """Two entries of one operation, the second with a negative check: refused despite the first's slack."""
        op = {"operation_id": f"shared{self.rid}"}
        self.ok("deposited", {"request_id": f"s1{self.rid}", "party_id": "x", "amount": "100", **op, "check_n": "0"})
        self.refused("deposited", {"request_id": f"s2{self.rid}", "party_id": "x", "amount": "0", **op, "check_n": "1"})
        self.refused("deposited", {"request_id": f"s3{self.rid}", "party_id": "x", "amount": "50", **op, "check_n": "0"})  # check_n reused


if __name__ == "__main__":
    unittest.main()
