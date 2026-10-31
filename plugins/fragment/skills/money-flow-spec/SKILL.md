---
name: money-flow-spec
description: Writes the requirements spec for a money flow (credits, wallets, payouts, escrow, lending, spending limits) before any code — parties, states, amounts and rounding, time, failure, the invariants a ledger must enforce, and every field of every operation. Use before building a ledger-backed flow, or when the user describes how money should move in their app.
---

# Write a money-flow spec

A money flow fails in its unanswered questions: rounding, the order money is drawn from several balances,
what a late or failed payment does, which races need one winner. The spec answers them up front so the
builder never guesses and an independent judge can test the result.

1. Copy [SPEC-TEMPLATE.md](SPEC-TEMPLATE.md) and fill every section. Where it says **Choose**, write the
   choice and why. If the user hasn't decided, ask them, or write the choice as an explicit default and
   flag it; never leave it implicit.
2. Start from the closest recipe in the `money-flows` skill (`../money-flows/recipes/`): it shows the level
   of detail that works, including the fixtures and the interface table.
3. Section 7 is the heart: number each invariant so it can be attacked by posting straight to the ledger
   ("no wallet goes negative", "a reservation is captured at most once", "a capture never exceeds its
   reservation"). Then list what stays service-attested (identity, time, rail outcomes) and why.
4. Section 8: a table of every operation with its actor and **every field**, the read views with their
   fields, and the reason codes. Specs that left a field unnamed are where builds and judges disagreed.

Amounts are integers in the smallest unit; times are integer seconds passed in as `now`, never read from a
clock, so every behaviour is testable.
