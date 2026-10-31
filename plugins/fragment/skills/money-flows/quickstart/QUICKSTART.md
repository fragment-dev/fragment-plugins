# Quickstart: prepaid credits on Fragment (TypeScript)

A minimal, working credits ledger: buy credits, spend them, and let the ledger refuse an overspend or a
double credit. Tested on a Fragment ledger: a repeated request replays, crediting a purchase twice, spending
past the balance and recording a usage twice are each refused with `conditional_request_failed`.

The full recipe (promo credits that expire, reservations for long jobs, transfers, refunds) is
[../recipes/credits.md](../recipes/credits.md); grow into it from here.

## 1. The schema

[credits-schema.jsonc](credits-schema.jsonc) defines a wallet per customer and two entry types:

- `credits_purchased`: adds credits to `liabilities/wallets/wallet:{{wallet_id}}/purchased`, and marks the
  purchase used (`liabilities/once/purchase:{{purchase_id}}` must end at exactly 1, so it credits once).
- `credits_consumed`: moves credits from the wallet to `income/usage`. Its condition, the wallet must end
  `gte 0`, is what makes overspending impossible, whatever the app's code does.

```bash
npm install -g @fragment-dev/cli
fragment login --browser                      # a person approves; new users get a workspace
fragment verify-schema -p credits-schema.jsonc
fragment store-schema -p credits-schema.jsonc
fragment create-ledger -i credits-test -n "Credits (test)" -s credits-schema.jsonc
fragment api-client create --workspace <workspace-id> --name "app" --role admin --format env --output .env.fragment
```

`.env.fragment` holds the client's API URL, auth URL, client id, secret and scope; map them to the
`FRAGMENT_*` variables below. Keep it out of version control.

## 2. Post entries from the app

```typescript
import { createFragmentClient, BadRequestError } from "@fragment-dev/node-client";

const fragment = createFragmentClient({
  params: {
    apiUrl: process.env.FRAGMENT_API_URL!,
    authUrl: process.env.FRAGMENT_AUTH_URL!,
    clientId: process.env.FRAGMENT_CLIENT_ID!,
    clientSecret: process.env.FRAGMENT_CLIENT_SECRET!,
    scope: process.env.FRAGMENT_SCOPE!,
  },
});
const ledgerIk = "credits-test";

// Stripe webhook: checkout.session.completed. The session id is the purchase id, so a
// redelivered webhook replays the same entry instead of crediting twice.
export async function creditPurchase(sessionId: string, walletId: string, credits: number) {
  await fragment.addLedgerEntry({
    ik: `purchase-${sessionId}`,
    ledgerIk,
    type: "credits_purchased",
    parameters: { purchase_id: sessionId, wallet_id: walletId, credits: String(credits) },
  });
}

// Per API call. The usage id makes retries safe; the ledger refuses an overspend.
export async function consume(usageId: string, walletId: string, credits: number): Promise<boolean> {
  try {
    await fragment.addLedgerEntry({
      ik: `usage-${usageId}`,
      ledgerIk,
      type: "credits_consumed",
      parameters: { usage_id: usageId, wallet_id: walletId, credits: String(credits) },
    });
    return true;
  } catch (e) {
    if (e instanceof BadRequestError && e.code === "conditional_request_failed") return false;  // not enough credits
    throw e;
  }
}
```

### The same post in Python, Ruby and Go

The [SDKs](https://fragment.dev/api-reference/ledger-sdks) (TypeScript, Python, Ruby, Go) take the same fields. A refused entry is an error with code
`conditional_request_failed`.

```python
# pip install fragment-python  (see its README for client setup)
await graphql_client.add_ledger_entry(
    ik=f"usage-{usage_id}",
    ledger_ik="credits-test",
    type_="credits_consumed",
    parameters=dict(usage_id=usage_id, wallet_id=wallet_id, credits=str(credits)),
)
```

```ruby
# gem install fragment-dev  (see its README for client setup)
fragment.add_ledger_entry({
  ik: "usage-#{usage_id}",
  ledgerIk: "credits-test",
  type: "credits_consumed",
  parameters: { usage_id: usage_id, wallet_id: wallet_id, credits: credits.to_s },
})
```

For Go, see the SDK page above; any language can also call the
GraphQL `addLedgerEntry` mutation directly.

Read a balance with the `ledgerAccount` query (path `liabilities/wallets/wallet:<id>/purchased`,
`balance(consistencyMode: use_account)`), or keep a mirror in your database updated after each post.

## 3. Prove it

Post the forbidden moves yourself: credit the same purchase id under a new `ik`, consume more than the
balance, reuse a usage id. Each must fail with `conditional_request_failed` and leave the balance unchanged.
For a full flow, use the `judge-a-flow` skill.
