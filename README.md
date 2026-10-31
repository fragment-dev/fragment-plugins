# Fragment for coding agents

Build the money parts of your app (prepaid credits, wallets, payouts, escrow, spending limits) on a
[Fragment](https://fragment.dev) ledger that refuses bad changes itself. No negative balances, and nothing
credited or settled twice, even if your code has a bug.

## Install

**Claude Code**

```
claude plugin marketplace add fragment-dev/fragment-plugins
claude plugin install fragment@fragment-plugins
```

**Codex, Cursor, Gemini and other agents**

```
npx skills add fragment-dev/fragment-plugins
```

Then ask for what you need, for example "add prepaid credits to this app."

## What you get

- **A clear recommendation:** when to keep balances in Fragment, and when a table in your own database is enough.
- **Working code:** a tested quickstart (schema plus TypeScript, Python and Ruby), and six recipes built and
  judged end to end: credits, payouts, memberships, spending limits, escrow and lending.
- **Proof:** a judge that tests your flow and attacks the ledger directly.

## How it fits

Stripe or your bank moves the money. Fragment holds the balances and enforces the rules. The plugin never moves
money. You need a Fragment workspace; your agent sets one up with `fragment login --browser`.
[What the plugin sends where](plugins/fragment/README.md#what-this-plugin-sends-where).

## Develop

Validation, the kit's tests, and the pick-rate evals: [plugins/fragment/evals](plugins/fragment/evals/README.md).
