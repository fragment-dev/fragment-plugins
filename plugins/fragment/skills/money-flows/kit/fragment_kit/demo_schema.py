"""A small schema built only from kit.primitives: a held amount released once, with its fee proved on the
ledger. It's the worked example for the primitives, and what kit/test_primitives.py attacks.

    python3 kit/demo_schema.py <out.jsonc> [--key <schema key>]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from primitives import (acct, check_ge0, const_types, entry, exact, kit_accounts, move, nonneg, once,  # noqa: E402
                        proof_accounts, proved_bps_types, rate_accounts, rate_table_types, read, step)

RATE = "liabilities/rates/rate:{{rate_id}}"
FEE = "liabilities/fee-proofs/hold:{{hold_id}}"
WALLET = "liabilities/wallets/party:{{party_id}}"
HELD = "liabilities/held/hold:{{hold_id}}"
STATE = "liabilities/hold-state/hold:{{hold_id}}"
PAYEE = "liabilities/wallets/party:{{payee_id}}"
FEES = "income/fees"
REQ = "liabilities/requests/request:{{request_id}}"


def schema(key):
    types = const_types() + rate_table_types(RATE, "fee") + proved_bps_types("fee", RATE, FEE) + [
        entry("deposited", "Deposit {{request_id}} to {{party_id}}", once(REQ),
              ([{"key": "w", "account": {"path": WALLET}, "amount": "{{amount}}"},
                {"key": "c", "account": {"path": "assets/cash"}, "amount": "{{amount}}"}], []),
              check_ge0("amount", "{{amount}} - 1")),
        entry("held", "Hold {{hold_id}}: {{amount}} from {{party_id}}", step(STATE, 0, 1),
              move(WALLET, HELD, "{{amount}}"), nonneg(WALLET), check_ge0("amount", "{{amount}} - 1")),
        # release once, only from a held state, paying exactly the held amount: net to the payee, the
        # proved fee to income
        entry("released", "Release {{hold_id}} to {{payee_id}}", step(STATE, 1, 2),
              read(FEE + "/amount", "{{amount}}"), read(FEE + "/result", "{{fee}}"),
              ([{"key": "h", "account": {"path": HELD}, "amount": "-{{amount}}"},
                {"key": "p", "account": {"path": PAYEE}, "amount": "{{amount}} - {{fee}}"},
                {"key": "f", "account": {"path": FEES}, "amount": "{{fee}}"}], []),
              exact(HELD, 0)),
    ]
    tree = kit_accounts()
    return {"key": key, "name": "ASSISTED kit primitives demo", "chartOfAccounts": {
        "defaultCurrency": {"code": "USD"}, "defaultCurrencyMode": "single",
        # conditions use totalBalance, so the schema must say so (verify-schema rejects it otherwise)
        "defaultConsistencyConfig": {"lines": "eventual", "totalBalanceUpdates": "eventual"},
        "accounts": [
            acct("assets", type_="asset", children=[acct("cash", strong=True)] + tree["assets"]),
            acct("liabilities", type_="liability", children=[
                acct("wallets", children=[acct("party", template=True, strong=True)]),
                acct("held", children=[acct("hold", template=True, strong=True)]),
                acct("hold-state", children=[acct("hold", template=True, strong=True)]),
                acct("requests", children=[acct("request", template=True, strong=True)]),
                rate_accounts("rates"), proof_accounts("fee-proofs", "hold"),
            ] + tree["liabilities"]),
            acct("income", type_="income", children=[acct("fees", strong=True)]),
        ]},
        "ledgerEntries": {"types": types}}


if __name__ == "__main__":
    key = sys.argv[sys.argv.index("--key") + 1] if "--key" in sys.argv else "kit-demo"
    Path(sys.argv[1]).write_text(json.dumps(schema(key), indent=1))
