"""Schema files are JSONC, as the Fragment CLI accepts them: comments anywhere and trailing commas."""

import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "fragment_kit"))
from ledger import LocalLedger, parse_jsonc     # noqa: E402
import service_core                            # noqa: E402

QUICKSTART = KIT.parent / "quickstart" / "credits-schema.jsonc"


class ParseJsoncTest(unittest.TestCase):
    def test_comments_anywhere(self):
        self.assertEqual(parse_jsonc('// title\n{"a": 1, // one\n "b": /* two */ 2}'), {"a": 1, "b": 2})

    def test_trailing_commas(self):
        self.assertEqual(parse_jsonc('{"a": [1, 2,], "b": {"c": 3,}, // last\n}'), {"a": [1, 2], "b": {"c": 3}})

    def test_strings_untouched(self):
        text = '{"url": "https://fragment.dev/x", "p": "a/*b*/c", "q": "say \\"//hi\\"", "r": "x,]"}'
        self.assertEqual(parse_jsonc(text), {"url": "https://fragment.dev/x", "p": "a/*b*/c", "q": 'say "//hi"',
                                             "r": "x,]"})

    def test_unterminated_block_comment(self):
        with self.assertRaises(ValueError):
            parse_jsonc('{"a": 1 /* open')


class CommentedSchemaTest(unittest.TestCase):
    """The quickstart schema with comments and a trailing comma added where an agent would write them."""

    def setUp(self):
        text = QUICKSTART.read_text()
        text = text.replace('"name": "Prepaid credits",', '"name": "Prepaid credits", // shown in the dashboard\n'
                            '  /* accounts: assets, income, liabilities */', 1)
        text = text.replace('"credits_consumed",', '"credits_consumed", // spends credits; refused below zero', 1)
        text = text.replace('"eq": "1" } } }\n        ]', '"eq": "1" } } }, // settles once\n        ]', 1)
        self.dir = Path(tempfile.mkdtemp())
        self.schema = self.dir / "schema.jsonc"
        self.schema.write_text(text)
        self.assertNotEqual(text, QUICKSTART.read_text())

    def test_local_ledger_enforces_a_commented_schema(self):
        led = LocalLedger(self.schema, self.dir / "ledger.db")
        self.assertTrue(led.post("p1", "credits_purchased", {"purchase_id": "p1", "wallet_id": "w1", "credits": "100"}).ok)
        r = led.post("u1", "credits_consumed", {"usage_id": "u1", "wallet_id": "w1", "credits": "150"})
        self.assertEqual((r.ok, r.code), (False, "conditional_request_failed"))

    def test_service_core_reads_a_commented_schema(self):
        self.assertIn("ledgerEntries", service_core.load_schema(self.schema))


class PreAndPostConditionTest(unittest.TestCase):
    """Fragment's verify-schema refuses a condition with both checks; the local ledger and endpoint do too."""

    def setUp(self):
        text = QUICKSTART.read_text().replace(
            '"postcondition": { "totalBalance": { "gte": "0" } }',
            '"precondition": { "totalBalance": { "gte": "0" } }, "postcondition": { "totalBalance": { "gte": "0" } }', 1)
        self.dir = Path(tempfile.mkdtemp())
        self.schema = self.dir / "schema.jsonc"
        self.schema.write_text(text)

    def test_local_ledger_refuses(self):
        with self.assertRaisesRegex(ValueError, "both precondition and postcondition"):
            LocalLedger(self.schema, self.dir / "ledger.db")

    def test_endpoint_refuses_store_schema(self):
        from local_server import BadRequest, Ledgers
        from ledger import load_schema
        with self.assertRaises(BadRequest) as e:
            Ledgers(self.dir / "local").store_schema(load_schema(self.schema))
        self.assertIn("both precondition and postcondition", e.exception.message)


if __name__ == "__main__":
    unittest.main()
