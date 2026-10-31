# Fragment lessons

Each one was learned building real flows on Fragment (a marketplace, escrow, lending, payouts, memberships,
credits). They're why ../money-flows/kit/fragment_kit/primitives.py looks the way it does.

- **Conditions are on account balances only**, not on expressions. To check "a ≥ b" on the ledger, post
  `a - b` into an account and require its balance to end ≥ 0.
- **One condition per account per entry.** And no precondition and postcondition on the same condition
  (`verify-schema` rejects it).
- **A "must end ≥ 0" check is only sound on an account that starts at 0.** Shared check accounts let one
  entry's slack hide another's negative. Use a fresh account per entry, e.g.
  `checks/op:{{operation_id}}/e:{{n}}/...`, with a `used` marker the entry adds 1 to and requires to end at 1.
- **Exactly-once on the ledger**: an account that must go 0 → 1 (post eq 1) makes a second attempt fail.
  That's how a milestone can settle only once even if the service is wrong.
- **Entry idempotency key**: the same `ik` with the same content replays; with different content it is
  refused. Use deterministic iks derived from the operation.
- **Schema size cap is about 385 KB**, and a stored entry type version can never be removed. Keep the
  schema small; store new versions under a new key if you must.
- **Entry listing is eventually consistent**; balances read with `consistencyMode: use_account` on
  strongly consistent accounts are not. Make the accounts you check `ownBalanceUpdates: strong`.
- **`fragment verify-schema -v -p <file>` works offline**: use it before every store.

- **The CLI token**: set `NO_COLOR=1` (or unset `FORCE_COLOR`) when calling `fragment token`, or the token
  comes back wrapped in colour codes and the API answers a bare 403.
- **Only `+` and `-` in amounts and conditions**: no `*`, not even by a constant, and no parentheses
  (`verify-schema`: "Only + and - are allowed in expressions"). Multiplication is proved with tables
  (../money-flows/kit/fragment_kit/primitives.py `proved_bps_types`).
- **About 95 strongly consistent accounts per entry.** Big proofs are split across entries (the doubling
  tables are built 10 items per entry).
- **`totalBalance` conditions need `defaultConsistencyConfig`** with `totalBalanceUpdates` at schema level,
  or verify-schema rejects every account's `consistencyConfig`.
- **The audit needs a settle window**: Fragment's entry listing is eventually consistent, so an audit can
  certify it only by re-reading until two listings some seconds apart agree.
