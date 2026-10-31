# Creator memberships: requirements (spec version 1)

> Built from this spec with the kit in 27 minutes; passed its independent judge 70/70 on the first run.

A video platform sells memberships to creators' Portals. Viewers subscribe to a tier, monthly or yearly; the platform
collects the money, keeps its fee, pays card processing, and holds the rest for the creator, who withdraws it for a
flat fee. Fees follow a common creator-platform model (5% platform fee, 2.9% + $0.30 processing, $1 per
payout). Where a choice is a business decision, this spec makes it explicitly (**Choose:**).
Built on Fragment so that the money rules hold on the ledger itself, not only in the API layer.

Amounts are integer US cents. Times are integer seconds supplied by the caller as `now`, never read from a clock.
**Every request field is named in section 8; use exactly those names.**

## 1. Parties and authority

| Party | May do | May read |
|---|---|---|
| creator | create_tier, set_price, refund, payout | its own tiers, subscriptions, charges, balance, payouts |
| viewer | subscribe, cancel | its own subscriptions and charges |
| platform | renew_due, release_due, chargeback, reconcile_rail | everything |

A creator acts only on its own tiers, charges and balance; a viewer only on its own subscriptions.

## 2. Money and conservation

Money enters only by a confirmed card charge and leaves only by a confirmed creator payout, a refund or a chargeback.

    creator pending + creator available - creator debt + payouts in flight + platform fees + processing fees
      = charges settled - refunds - chargebacks - payouts confirmed (net of the payout fee)

(Payout fees are part of platform fees.)

## 3. Objects and states

- **Tier** (`create_tier`, creator): `tier_id`, `portal_id`, `monthly_price`, `yearly_price` (each an integer >= 50 or
  `null` for not offered; both `null` = a free tier). `set_price` changes prices for **renewals and new subscriptions
  only**; a period already charged is never re-priced.
- **Subscription** (`subscribe`, viewer): `subscription_id`, `tier_id`, `interval` (`month` | `year`). A month is
  2,592,000 s and a year 31,536,000 s (**Choose:** fixed lengths). Period n covers
  `[start + n × length, start + (n+1) × length)`, where `start` is the `now` of `subscribe`.
  States: `pending` (first charge in flight) → `active` | `failed`; `active` → `past_due` (a renewal charge failed)
  → `active` (a later renewal attempt for that period succeeded); any → `canceled`. A free tier is `active` at once,
  with no charges ever.
- **Charge**: one per subscription per period. Its ID is exactly `<subscription_id>-p<n>` (n from 0), which is also the
  rail request ID. States: `pending` → `settled` | `failed`; `settled` → `charged_back`. Refunds are recorded on a
  settled charge (`refunded`, cumulative). The price is the tier's price for that interval **at the moment the
  charge is created**.
- **Renewals** (`renew_due`, platform): for every `active` or `past_due` subscription whose current period has
  ended by `now` and that isn't canceled, create the next period's charge. A `past_due` subscription's failed period
  is retried with the **same charge ID** (it was never settled); **Choose:** at most one attempt per `renew_due` call,
  no automatic limit.
- **Cancel** (`cancel`, viewer): no further renewals; no refund.
- **Earnings:** a settled charge's creator earnings are `pending` until `charge time + 604,800 s` (7 days), then
  `release_due` (platform) moves them to `available`. **Choose:** a 7-day clearing period.
- **Refund** (`refund`, creator): `charge_id`, `amount` (> 0), `request_id`. Up to the charge's gross minus what's
  already refunded. The **whole refunded amount comes from the creator** (pending earnings of that charge first,
  then available); the platform and processing fees are not returned (**Choose:** as card processors do). A refund
  that the creator's pending-for-that-charge plus available can't cover is refused `insufficient_funds`. The refund
  goes back over the rail and is final on submission (no rail lookup needed).
- **Chargeback** (`chargeback`, platform): `charge_id`. The whole gross minus refunds goes back to the viewer; it
  comes from the creator like a refund, and **any shortfall becomes creator debt** instead of being refused.
  Fees are not returned. A charge is charged back at most once.
- **Payout** (`payout`, creator): `payout_id`, `amount` (> 100), `request_id`. From `available` only; refused
  `creator_in_debt` while debt > 0, `insufficient_funds` if over available. The $1 fee (100) is taken out of the
  amount: the creator receives `amount - 100`. States `pending` → `completed` | `failed`; **a failure returns the
  whole amount, fee included**, once.
- **Debt repayment:** whenever earnings are released to available, they **pay off debt first**.

## 4. Amounts

For a charge of `gross`:

- platform fee = `round_half_up(gross × 500 / 10000)` (5%)
- processing fee = `round_half_up(gross × 290 / 10000) + 30` (2.9% + $0.30, per charge)
- creator earnings = `gross - platform fee - processing fee`

**Choose:** half-up rounding applied to each percentage term separately. Worked example: 20 charges of $50.00 →
each 250 + (145 + 30) → creator 4,575 each, 91,500 in all; one payout of all of it → 91,400 received ($914.00).

## 5. Time

- `now` decides the period of every charge and when earnings become available. `now` never goes backwards.
- The ledger cannot read time; renewal due-ness and the 7-day hold are service-attested (section 7).

## 6. The rail, failure and recovery

- Card charges and payouts use the kit's HTTP rail contract (`POST /requests` with `request_id`, `kind`, `amount`,
  `party`; `GET /requests/<id>`; states `confirmed`, `failed`, `unknown`). Charges use `kind` `card_charge` and the
  charge ID; payouts use `kind` `payout` and the payout's `request_id`; refunds use `kind` `refund` and are not looked
  up. `reconcile_rail` (platform) looks up every charge and payout in flight. A request ID moves money at most once.
- Every operation carries `operation_id`, `now` and `actor` (`{"role", "id"}`). A replay of the identical request
  returns the first answer and changes nothing; the same ID with any different field is `operation_id_reused`.
- A crash at any point must not lose or duplicate money.
- Races: two payouts that together exceed available; a refund racing a chargeback on one charge; two `renew_due`
  calls at once (each period charged once).

## 7. Invariants the ledger itself must enforce

1. **Exact split.** For every settled charge, platform fee + processing fee + creator earnings = gross, and both fees
   equal section 4's formulas for that gross (proved on the ledger: kit `proved_bps_types` or equivalent).
2. **Once per period.** A subscription period is charged at most once (a retry of a failed charge is the same charge);
   a charge settles, fails or is charged back at most once each.
3. **No negative balances.** A creator's pending and available never go negative; a payout never exceeds available.
4. **Refunds are bounded.** A charge's refunds plus chargeback never exceed its gross.
5. **Debt first.** No payout posts while the creator's debt is above 0.
6. **The payout fee is exactly 100**, and a failed payout returns exactly its amount, once.

Service-attested and acceptable: who is which party (authority), time (renewal due-ness, the 7-day hold), the rail's
outcomes, and the tier price used (the ledger checks the split of whatever gross is charged).

**Fixtures** (the judge creates these and records the fields listed):
- `creator_with_available`: `creator`, `available`.
- `creator_in_debt`: `creator`, `debt`, `available` (0).
- `settled_charge`: `charge_id`, `subscription_id`, `creator`, `gross`, `refunded`, `creator_earnings`.
- `charged_back_charge`: same fields as `settled_charge`.
- `pending_payout`: `payout_id`, `creator`, `amount`.
- `failed_payout`: `payout_id`, `creator`, `amount`.

## 8. Interface (the judge uses exactly this)

HTTP JSON on `127.0.0.1:<port>`. `POST /op/<operation>` with body `{"operation_id", "now", "actor", ...fields}` →
`{"status": "accepted" | "rejected", "reason"?: ..., ...}`.

| Operation | Actor | Fields |
|---|---|---|
| `create_tier` | creator | `tier_id`, `portal_id`, `monthly_price`, `yearly_price` |
| `set_price` | creator | `tier_id`, `monthly_price`, `yearly_price` |
| `subscribe` | viewer | `subscription_id`, `tier_id`, `interval` |
| `cancel` | viewer | `subscription_id` |
| `renew_due` | platform | (none) |
| `release_due` | platform | (none) |
| `refund` | creator | `charge_id`, `amount`, `request_id` |
| `chargeback` | platform | `charge_id` |
| `payout` | creator | `payout_id`, `amount`, `request_id` |
| `reconcile_rail` | platform | (none) |

Unknown fields are rejected `invalid_request`; missing or ill-typed ones too.

- `GET /creator/<id>` → `{"pending", "available", "debt", "payouts_in_flight", "paid_out"}`
- `GET /subscription/<id>` → `{"status", "tier_id", "viewer", "creator", "interval", "start", "periods_charged", "current_period"}`
- `GET /charge/<id>` → `{"status", "subscription_id", "creator", "period", "gross", "platform_fee", "processing_fee", "creator_earnings", "refunded", "charged_back"}`
- `GET /payout/<id>` → `{"status", "creator", "amount", "fee", "net"}`
- `GET /platform` → `{"platform_fees", "processing_fees"}`
- `GET /totals` → `{"conserved": bool, ...}`

Reasons: `insufficient_funds`, `creator_in_debt`, `over_refundable`, `invalid_state`, `unauthorized`, `not_found`,
`invalid_request`, `operation_id_reused`.

## 9. Deliverables

As the `money-flow-spec` template, section 9: the service, tests, stored schema, `MANIFEST.json` (the `judge-a-flow` skill's MANIFEST.md, with accounts
`creator_available` (`{creator}`), `creator_pending` (`{creator}`), `creator_debt` (`{creator}`) and
`platform_fees`), `TRUST-BOUNDARY.md`, and `README.md` with decisions, gaps and times. The start command must accept
`{db}`, `{ledger}`, `{rail}` and `{port}`.
