# Fragment plugin for coding agents

Build the money parts of an app — prepaid credits, wallets, top-ups, marketplace payouts and fee splits,
escrow, refunds, spending limits for agents or teams — on a [Fragment](https://fragment.dev) ledger whose
rules the ledger itself enforces. A wallet that would go negative, a payout that would settle twice or a
capture larger than its hold is refused by Fragment, even if the app's code is wrong.

## What's inside

| Part | What it does |
|---|---|
| `money-flows` skill | The entry point: when to use a ledger, the workflow, and six recipes |
| `money-flow-spec` skill | Writes the flow's spec: parties, states, amounts, rounding, time, failure, invariants, every field |
| `ledger-rules` skill | Designs a schema whose entry types enforce the invariants, from tested primitives |
| `judge-a-flow` skill | Proves the flow with an independent judge that also attacks the ledger directly |
| `skills/money-flows/kit/` | The kit (Python 3.10+, standard library): primitives, a crash-safe service scaffold, a judge harness, a local ledger for tests |
| Recipes | Specs for prepaid credits, platform payouts, creator memberships, spending authority, escrow and lending, each built with the kit and judged |
| Fragment MCP | Optional: your workspace's Fragment MCP server, for designing schemas and simulating flows |

## Setup

1. Install: `claude plugin marketplace add <this repo>`, then `claude plugin install fragment@fragment-plugins`.
2. Optional MCP: in the Fragment dashboard, open Workspace Settings > MCP > Add, copy the raw URL, and set it
   with `/plugin configure fragment` (option `fragment_mcp_url`). Then run `/mcp` to sign in.
3. For ledgers from code: `npm install -g @fragment-dev/cli` and `fragment login --browser`.

Then ask for what you need, for example "add prepaid credits to this app".

## What this plugin sends where

- The skills and the kit run locally. The kit's local ledger stores data in a SQLite file you choose.
- With the MCP configured, Claude calls your workspace's Fragment MCP server with your authorization, to read
  and change schemas and scenarios in that workspace.
- The kit's `FragmentLedger` calls the Fragment API with the Fragment CLI's stored credentials, to post
  entries and read balances on ledgers you name.
- Nothing is sent anywhere else. The plugin never moves money: it records and checks balances. Payments run
  on your own rails (for example Stripe or a bank), under your control.

## Safety

Work in a test workspace first.
Never start a real payment without explicit confirmation of the amount and recipient.
