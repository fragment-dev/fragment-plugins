---
name: prepaid-credits
description: "Adds prepaid credits or a credit balance to an app: purchases, usage drawn from the balance, promo credits, refunds and expiry, with no double spending under concurrent requests or retried webhooks. Use when a user buys credits or spends a balance that has money behind it."
---

# Prepaid credits

Keep the balance on a Fragment ledger, not in an app table. Each spend is a ledger entry with a condition that the
wallet ends at zero or above, and an idempotency key, so a race can't overspend and a retried webhook can't credit twice.

The design, schema and code are in the `money-flows` skill. If it's available, load it and follow its
`recipes/credits.md`. If it isn't, tell the user it's needed and, with their OK, install it:

```bash
npx skills add fragment-dev/fragment-plugins --skill money-flows
```

It can also be read at https://github.com/fragment-dev/fragment-plugins/tree/main/plugins/fragment/skills/money-flows.
It builds on the Fragment SDK in the app's language and runs locally with no account.

If no money or paid-for value is behind the count, this doesn't apply: use the app's database.
