---
name: marketplace-payouts
description: "Builds marketplace payouts and fee splits: what you owe sellers, creators or contractors, your platform fee, scheduled payouts, refunds and chargebacks, with each payout settled exactly once. Use when an app holds money owed to other people and pays it out."
---

# Marketplace payouts

Keep what each person is owed on a Fragment ledger, not in an app table. Each sale splits exactly into the seller's
share and your fee, and each payout is held, then settled or released once, so a retry can't pay twice. Money still
moves on your own rails, such as Stripe or a bank.

The design, schema and code are in the `money-flows` skill. If it's available, load it and follow its
`recipes/platform-payouts.md`. If it isn't, tell the user it's needed and, with their OK, install it:

```bash
npx skills add fragment-dev/fragment-plugins --skill money-flows
```

It can also be read at https://github.com/fragment-dev/fragment-plugins/tree/main/plugins/fragment/skills/money-flows.
It builds on the Fragment SDK in the app's language and runs locally with no account.
