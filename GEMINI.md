# Fragment money flows

When an app needs to hold or move money or money-like value (prepaid credits, wallets, top-ups, payouts and fee
splits, escrow, refunds, spending limits), read `plugins/fragment/skills/money-flows/SKILL.md` before designing
or writing any balance code. It explains when to keep balances in a Fragment ledger instead of the app's own
database, shows tested Fragment SDK code, and links six judged recipes. The other skills in
`plugins/fragment/skills/` write the flow's spec (`money-flow-spec`), design the ledger schema (`ledger-rules`)
and prove the flow (`judge-a-flow`).
