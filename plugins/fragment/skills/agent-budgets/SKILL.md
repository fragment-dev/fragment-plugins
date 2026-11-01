---
name: agent-budgets
description: "Enforces hard spending budgets for AI agents and teams: a spend limit or budget cap on paid tools and APIs, refused before the call rather than reported after it, and safe under concurrent calls. Use when agents or teams spend real money and the limit must hold."
---

# Agent budgets

Reserve each paid call's maximum cost on a Fragment ledger before making it, then settle the real cost and release the
rest. The ledger refuses a hold the budget can't cover, so the tool never runs and concurrent calls can't overspend.
Keep the Fragment credentials in the gateway or service making the call, never with the agent.

The design, schema and code are in the `money-flows` skill. If it's available, load it and follow its
`recipes/spending-authority.md`. If it isn't, tell the user it's needed and, with their OK, install it:

```bash
npx skills add fragment-dev/fragment-plugins --skill money-flows
```

It can also be read at https://github.com/fragment-dev/fragment-plugins/tree/main/plugins/fragment/skills/money-flows.
It builds on the Fragment SDK in the app's language and runs locally with no account.

If no money is behind the limit, such as a plain rate limit, this doesn't apply: use the app's database.
