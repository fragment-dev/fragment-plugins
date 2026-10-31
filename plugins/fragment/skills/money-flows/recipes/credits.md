# Prepaid credits and wallets for an AI app: requirements (spec version 1)

> Fragment code to start from: [../quickstart/QUICKSTART.md](../quickstart/QUICKSTART.md).

> Built from this spec with the kit in 18 minutes; passed its independent judge 68/68 on the first run, 22 forbidden entries refused by the ledger.

An AI product sells prepaid credits. Customers buy credit packs, the app grants promotional credits, usage
draws credits down, long-running jobs reserve credits first and capture what they actually used, unused
purchased credits can be refunded, and promotional credits expire. A team can pool credits in a shared wallet
and move them to members. Built on Fragment so that no wallet can go negative and no credit is spent twice,
even if the app's own code is wrong.

Amounts are integer credits (1 credit = 1 US cent of purchase price). Times are integer seconds supplied by
the caller as `now`, never read from a clock. **Every request field is named in section 8; use exactly those names.**

## 1. Parties and authority

| Party | May do | May read |
|---|---|---|
| customer (owner of a wallet) | buy, transfer (from its own wallet), request_refund | its own wallets and history |
| app (the product's backend) | grant, reserve, capture, release, consume | every wallet |
| platform (operator) | reconcile_rail, expire_due, create_wallet | everything |

A wallet has exactly one owner (a customer id). The app acts for usage; it never buys or refunds.

## 2. Money and conservation

Purchased credits enter only by a confirmed card charge and leave only as usage revenue or a confirmed refund.
Promotional credits are the app's own cost and carry no cash.

    sum of purchased balances + purchased reserved + refunds in flight
      = purchases confirmed - purchased credits consumed - refunds confirmed

    sum of promo balances + promo reserved = promo granted - promo consumed - promo expired

## 3. Objects and states

- **Wallet** (`create_wallet`, platform): `wallet_id`, `owner`. Holds two balances: `purchased` and `promo`.
  A promo balance is made of **grants**, each with its own `expires_at`.
- **Purchase** (`buy`, customer): `purchase_id`, `wallet_id`, `credits` (> 0), `request_id`. The card charge
  goes to the rail; credits are `pending` until it confirms, then added to `purchased`; a failed charge adds
  nothing. A purchase is credited at most once.
- **Grant** (`grant`, app): `grant_id`, `wallet_id`, `credits` (> 0), `expires_at` (> now). Added to `promo`
  at once.
- **Consume** (`consume`, app): `usage_id`, `wallet_id`, `credits` (> 0). Draws promo first (soonest-expiring
  grant first, never an expired one), then purchased. Refused `insufficient_credits` if the wallet can't cover
  it; nothing is drawn partially.
- **Reservation** (`reserve`, app): `reservation_id`, `wallet_id`, `credits` (> 0). Moves credits from available
  to reserved, in the same draw order as consume. **`capture`** (`reservation_id`, `credits` ≤ reserved) consumes
  that many from the reservation and releases the rest; **`release`** (`reservation_id`) returns all of it.
  A reservation is captured or released exactly once. Credits released from an expired grant stay expired
  (they are not returned to promo). **Choose:** a reservation never expires on its own in v1.
- **Transfer** (`transfer`, customer): `transfer_id`, `from_wallet`, `to_wallet`, `credits` (> 0). Moves
  **purchased credits only** (promo credits are not transferable). Both wallets must exist; the actor must own
  `from_wallet`.
- **Refund** (`request_refund`, customer): `refund_id`, `wallet_id`, `credits` (> 0), `request_id`. Refunds
  **purchased credits only**, up to the wallet's available purchased balance; they leave at once and are in
  flight until the rail confirms; a failed refund returns them. **Choose:** refunds are not tied to a specific
  purchase in v1.
- **Expiry** (`expire_due`, platform): every grant whose `expires_at` ≤ now has its unspent, unreserved credits
  removed. Each grant expires at most once.

## 4. Amounts

- Draw order for consume and reserve: promo grants by soonest `expires_at` (then by `grant_id`), skipping
  expired ones, then purchased.
- No fees in v1.

## 5. Time

- `now` decides expiry; `now` never goes backwards. An expired grant can't be drawn even before `expire_due`
  runs (service-attested; see section 7).

## 6. The rail, failure and recovery

- Card charges and refunds use the kit's HTTP rail contract (`POST /requests` with `request_id`, `kind`, `amount`,
  `party`; `GET /requests/<id>`; states `confirmed`, `failed`, `unknown`). Purchases use `kind` `card_charge`,
  refunds `kind` `refund`, both with the caller's `request_id`. `reconcile_rail` (platform) looks up everything
  in flight. A request ID moves money at most once.
- Every operation carries `operation_id`, `now` and `actor` (`{"role", "id"}`). A replay of the identical request
  returns the first answer and changes nothing; the same ID with any different field is `operation_id_reused`.
- A crash at any point must not lose or duplicate credits.
- Races: two consumes that together exceed a wallet; a capture racing a release; two transfers out of one
  wallet; a refund racing a consume.

## 7. Invariants the ledger itself must enforce

1. **No negative balances.** No wallet's purchased, promo (per grant) or reserved balance ever goes below 0.
2. **Once.** A purchase is credited once; a reservation is captured or released once; a grant expires once; a
   refund settles or fails once; a request ID moves money once.
3. **Capture is bounded.** A capture never takes more than its reservation holds.
4. **Promo stays promo.** Promo credits are never transferred or refunded, and never become purchased credits.
5. **Transfers conserve.** A transfer takes exactly what it gives.

Service-attested and acceptable: authority (who owns a wallet), time (which grants are expired, which are due),
the draw order between grants, and the rail's outcomes.

**Fixtures** (the judge creates these and records the fields listed):
- `funded_wallet`: `wallet_id`, `owner`, `purchased`, `promo`.
- `empty_wallet`: `wallet_id`, `owner`.
- `open_reservation`: `reservation_id`, `wallet_id`, `credits`.
- `closed_reservation` (captured): `reservation_id`, `wallet_id`, `credits`, `captured`.
- `expired_grant` (after expire_due): `grant_id`, `wallet_id`, `credits`.
- `credited_purchase`: `purchase_id`, `wallet_id`, `credits`.

## 8. Interface (the judge uses exactly this)

HTTP JSON on `127.0.0.1:<port>`. `POST /op/<operation>` with body `{"operation_id", "now", "actor", ...fields}` →
`{"status": "accepted" | "rejected", "reason"?: ..., ...}`.

| Operation | Actor | Fields |
|---|---|---|
| `create_wallet` | platform | `wallet_id`, `owner` |
| `buy` | customer | `purchase_id`, `wallet_id`, `credits`, `request_id` |
| `grant` | app | `grant_id`, `wallet_id`, `credits`, `expires_at` |
| `consume` | app | `usage_id`, `wallet_id`, `credits` |
| `reserve` | app | `reservation_id`, `wallet_id`, `credits` |
| `capture` | app | `reservation_id`, `credits` |
| `release` | app | `reservation_id` |
| `transfer` | customer | `transfer_id`, `from_wallet`, `to_wallet`, `credits` |
| `request_refund` | customer | `refund_id`, `wallet_id`, `credits`, `request_id` |
| `expire_due` | platform | (none) |
| `reconcile_rail` | platform | (none) |

Unknown fields are rejected `invalid_request`; missing or ill-typed ones too.

- `GET /wallet/<id>?now=<t>` → `{"owner", "purchased", "promo", "reserved", "pending_purchases", "refunds_in_flight", "available"}`
  where `promo` counts only unexpired grants at `now` and `available` = purchased + that promo.
- `GET /grant/<id>` → `{"wallet_id", "credits", "remaining", "expires_at", "status"}` (`active` | `expired`)
- `GET /reservation/<id>` → `{"wallet_id", "credits", "status", "captured"}` (`open` | `captured` | `released`)
- `GET /purchase/<id>` → `{"wallet_id", "credits", "status"}` (`pending` | `credited` | `failed`)
- `GET /refund/<id>` → `{"wallet_id", "credits", "status"}` (`in_flight` | `refunded` | `failed`)
- `GET /totals` → `{"conserved": bool, ...}`

Reasons: `insufficient_credits`, `invalid_state`, `unauthorized`, `not_found`, `invalid_request`,
`operation_id_reused`.

## 9. Deliverables

As the `money-flow-spec` template, section 9: the service, tests, stored schema, `MANIFEST.json` (the `judge-a-flow` skill's MANIFEST.md, with accounts
`wallet_purchased` (`{wallet}`), `wallet_promo` (`{wallet}`), `wallet_reserved` (`{wallet}`) and `grant_remaining`
(`{grant}`)), `TRUST-BOUNDARY.md`, and `README.md` with decisions, gaps and times. The start command must accept
`{db}`, `{ledger}`, `{rail}` and `{port}`.
