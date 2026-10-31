# Platform payouts: requirements (spec version 1)

> Built from this spec with the kit in 35 minutes; passed its independent judge 59/59 (after documented fixes to the judge's own mistakes), 17/17 forbidden entries refused.

A platform pays many recipients (creators, contractors, sellers). It funds an app wallet, moves money to each
recipient's wallet, and pays recipients out over rails, with fees that either the platform or the recipient
bears. Where a choice is a business decision, this spec makes it explicitly (**Choose:**). Built on Fragment so that the wallet
rules hold on the ledger itself, not only in the API layer.

Amounts are integer US cents. Times are integer seconds supplied by the caller as `now`.

## 1. Parties and authority

| Party | May do | May read |
|---|---|---|
| platform (the app) | fund (refill), transfer to/from users, pay out (single, fund-and-pay, batch), clear compliance holds in this sandbox | everything in its app |
| user (a recipient) | withdraw (pay out from its own wallet) | its own wallet and payouts |
| operator (the payout provider) | reconcile_rail, set fee schedule, flag/unflag a user | everything |

No user-to-user transfers. A user never touches the app wallet.

## 2. Money and conservation

Money enters only by a confirmed refill to the app wallet; it leaves only by a confirmed payout.

    app wallet + user wallets + payouts in flight + provider fees + platform fees
      = refills confirmed - payouts confirmed (at their payout amount)

## 3. Objects and states

- **Fee schedule** (operator, `set_fees`): per rail `{fixed, percent_bps, min, max}` for the provider fee, and the
  platform's own upcharge `{fixed, percent_bps}`; fixed when a payout is created. Defaults for this spec
  (typical published US rates): `ach` fixed 200; `intl_bank` 200 + 390 bps; `paypal` fixed 200; `push_to_card` 100 + 75 bps, min 150.
- **User:** `status` `verified` | `unverified` | `flagged`. Only `verified` users with no flags can be paid out.
  **Choose:** a flag holds payouts from the user's wallet; money already in the wallet stays there.
- **Transfer** (`transfer`, platform): app → user (`amount` > 0) or user → app (`amount` < 0, only up to the user's
  balance). Immediate.
- **Payout** (`payout`, platform for a user, or `withdraw`, user for itself): `user`, `amount`, `rail`, `fee_party`
  (`platform` | `user`), `fund` (bool). States: `pending` → `completed` | `failed`; `completed` → `returned`.
  - `fund: false`: paid from the user's wallet (insufficient → `insufficient_funds`).
  - `fund: true`: transfer and payout together, from the app wallet; **a failure returns the money to the app wallet**.
- **Batch** (`payout_batch`, platform): 1–500 items, each `fund: true`, each with its own `idempotency_key`.
  **Choose:** each item stands alone: an item that's refused or fails doesn't affect the others.

## 4. Amounts

- Provider fee = `max(min, min(max, fixed + round_half_up(amount × percent_bps / 10000)))` (min/max when set).
  Platform fee = `fixed + round_half_up(amount × percent_bps / 10000)`. **Choose:** half-up rounding, applied to
  each percentage term.
- `fee_party: user`: the recipient receives `amount − provider fee − platform fee` (refused `amount_too_small` if
  that's < 1); `fee_party: platform`: the recipient receives `amount` and the fees come from the app wallet on top.
  **Choose:** default `user`.
- Fees are charged when the payout is created and **returned with it** if it fails before completion; a return
  after completion refunds nothing of the fees. **Choose:** stated so.

## 5. Time

- Payouts are `pending` until the rail answers. No timing rules beyond that in v1.

## 6. The rail, failure and recovery

- Refills and payouts use the kit's HTTP rail contract (`POST /requests`, `GET /requests/<id>`, states `confirmed`,
  `failed`, `unknown`, plus `returned` after `confirmed`). `reconcile_rail` (operator) looks up everything in
  flight. A request ID moves money at most once.
- **A failure before completion** returns the money to where it came from: the app wallet for `fund: true`, the
  user's wallet otherwise. **A return after completion** credits the **user's wallet**, whatever
  the funding.
- Every operation carries `operation_id`, `now` and `actor`; replays return the first answer; the same ID with
  different content is `operation_id_reused`. Batch items are also idempotent on their `idempotency_key`.
- A crash at any point must not lose or duplicate money. Races: two payouts from one user wallet that together
  exceed it; a batch racing a transfer out of the app wallet.

## 7. Invariants the ledger itself must enforce

1. **No overdraft.** No user wallet and no app wallet ever goes negative (payouts, transfers, fees included).
2. **Exact split.** For every payout, recipient amount + provider fee + platform fee equals what left the funding wallet.
3. **Once.** A payout completes, fails or returns at most once each; a failed payout's money (and fees) come back
   exactly once; a request ID moves money once.
4. **Holds hold.** No payout posts from a flagged or unverified user's wallet.
5. **The fee is the schedule's.** The provider fee equals the schedule's formula for the amount (proved on the
   ledger, kit `proved_bps_types` or equivalent).

Service-attested and acceptable: who is the platform vs a user (authority), the rail's own timing.

**Fixtures:** `funded_user` (`user`, `wallet`), `flagged_user` (`user`, `wallet`), `pending_payout` (`payout_id`,
`user`, `amount`, `rail`, `fee`), `completed_payout` (same), `failed_payout` (same), `app_wallet` (`balance`).

## 8. Interface

HTTP JSON on `127.0.0.1:<port>`.
- `POST /op/<operation>`: `refill`, `transfer`, `payout`, `withdraw`, `payout_batch`, `set_fees`, `flag`, `unflag`,
  `verify_user`, `reconcile_rail`.
- `GET /app` → `{"wallet", "in_flight", "provider_fees", "platform_fees"}`
- `GET /user/<id>` → `{"status", "wallet", "in_flight", "held": bool}`
- `GET /payout/<id>` → `{"status", "user", "amount", "rail", "fee_party", "provider_fee", "platform_fee", "recipient_amount", "funded_from"}`
- `GET /totals` → `{"conserved": bool, ...}`

Reasons: `insufficient_funds`, `user_held`, `amount_too_small`, `invalid_state`, `unauthorized`, `operation_id_reused`.

## 9. Deliverables

As the `money-flow-spec` template, section 9; `MANIFEST.json` accounts must include `app_wallet` and `user_wallet` (`{user}`).
