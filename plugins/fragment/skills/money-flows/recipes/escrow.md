# Milestone escrow: requirements

> Built from this spec in 15 minutes; passed its independent judge 52/52 (after documented fixes to the judge's own mistakes), every forbidden entry refused by the ledger.

A client hires a contractor for work paid in milestones. The client funds milestones into escrow; the
contractor is paid a milestone when the client approves it (or doesn't object in time); disputes go to the
platform, which can release, refund or split. The platform takes a fee on what the contractor is paid.

Build it on Fragment with a service in front. Amounts are integer
US cents. Times are integer seconds, supplied by the caller as `now` (never read from a clock).

## 1. Parties and money

- **client**: deposits into a wallet from their bank, funds milestones from the wallet, approves or
  disputes, and may withdraw unused wallet money.
- **contractor**: submits milestones, receives released money as available balance, and withdraws it.
- **platform**: sets the fee rule, resolves disputes, and processes due items.

Money enters only by a confirmed bank deposit and leaves only by a confirmed bank withdrawal, both over the
rail described in 5. Conservation must hold at all times:

    client wallets + escrowed milestones + contractor available + money in flight out + platform fees
      = deposits confirmed - withdrawals confirmed

## 2. Contracts and milestones

- `create_contract` (client): `contract_id`, `contractor`, `review_period` (seconds, >= 0), and
  `milestones`: a list of `{milestone_id, amount}` (amount > 0, IDs unique across the system). The
  platform's fee in force at creation is fixed on the contract.
- A milestone moves through: `unfunded` → `funded` → `submitted` → `released`, or `refunded`, or `split`.
- `fund_milestone` (client): moves the milestone's whole amount from the client's wallet into escrow.
  Rejected if the wallet doesn't hold it (`insufficient_funds`). A milestone is funded once.
- `submit_milestone` (contractor): only a funded milestone. Starts the review period at `now`.
- `approve_milestone` (client): only a submitted milestone. Releases it at once (3).
- Auto-approval: a submitted milestone that is neither approved nor disputed is released by
  `process_due` once `now >= submitted_at + review_period` (inclusive). Its release time is
  `submitted_at + review_period` even if processed later.
- `cancel_contract` (client): every funded but not submitted milestone is refunded to the client's wallet;
  unfunded milestones are closed. Submitted or disputed milestones are untouched and run their course.

## 3. Release, fee, refund, split

- On release, the contractor's available balance increases by `amount - fee` and the platform's fee
  revenue by `fee`, where `fee = round_half_up(amount * fee_bps / 10000)`.
- A refund returns the milestone's whole escrowed amount to the client's wallet. No fee.
- A split pays the contractor `x` (0 < x < amount) as a release of `x` (fee on `x` only) and refunds
  `amount - x` to the client.
- Every escrowed cent ends in exactly one place: released + refunded = funded, per milestone.

## 4. Disputes

- `open_dispute` (client or contractor): only a funded or submitted milestone, at most one open dispute
  per milestone. An open dispute stops approval and auto-approval.
- `resolve_dispute` (platform): `result` is `release`, `refund` or `split` (with `contractor_amount`).
  It settles the milestone accordingly and closes the dispute.

## 5. The rail

Deposits and withdrawals go through a rail with the kit's rail contract
(`../kit/fragment_kit/rail.py`: `submit`, `lookup`, terminal states `confirmed` and `failed`).

- `deposit` (client): `request_id`, `amount`. Money is in flight until the rail confirms; only then does
  it reach the wallet. A failed deposit adds nothing.
- `withdraw` (client from wallet, or contractor from available): `request_id`, `amount`. The amount
  leaves the spendable balance at once and is in flight; confirmed, it's gone; failed, it returns.
- `reconcile_rail` (platform): looks up every request in flight and applies the rail's answer. A
  request ID moves money at most once, whatever happens.

## 6. Rules

- `set_fee` (platform): `fee_bps` (0..10000), effective at `effective_at` (default `now`). A contract
  uses the fee in force when it was created.

## 7. Correctness the ledger itself must enforce

These must hold even if the service is buggy: Fragment must refuse an entry that would break them, not
only the service. The judge will post entries straight to your ledger, with the service's credentials,
using the entry types you declare in the manifest, and expects them to be refused.

1. A milestone never pays out (released + refunded) more than was escrowed for it.
2. A milestone settles at most once: no second release, refund or split.
3. No wallet, escrow or available balance goes negative.
4. A milestone can't be released or refunded before it is funded.

## 8. Operations and service behaviour

- Every operation carries `operation_id`, `now` and `actor` (`{"role": ..., "id": ...}`), and is
  idempotent on `operation_id`: a replay returns the first answer and changes nothing; the same ID
  with different content is rejected (`operation_id_reused`).
- Who may call what is listed in 2–6; anything else is rejected `unauthorized` with no effect.
- Rejections have a `reason` and no effect on any balance.
- Concurrent requests: when two requests race to settle the same milestone (approve, resolve, process
  due, cancel), exactly one takes effect and the rest are rejected.
- A service crash at any point must not lose or duplicate money; on restart, `reconcile_rail` and
  `process_due` complete what was in progress.

## 9. Interface (the judge uses exactly this)

HTTP JSON on `127.0.0.1:<port>`:

- `POST /op/<operation>` with the operation as a JSON object. Answer: `{"status": "accepted", ...}` or
  `{"status": "rejected", "reason": "..."}`.
  Operations: `set_fee`, `deposit`, `withdraw`, `reconcile_rail`, `create_contract`, `fund_milestone`,
  `submit_milestone`, `approve_milestone`, `cancel_contract`, `open_dispute`, `resolve_dispute`,
  `process_due`.
- `GET /account/client/<id>` → `{"wallet", "deposits_in_flight", "withdrawals_in_flight"}`
- `GET /account/contractor/<id>` → `{"available", "withdrawals_in_flight"}`
- `GET /milestone/<id>` → `{"status", "amount", "fee", "released", "refunded", "submitted_at", "released_at"}`
- `GET /totals` → `{"conserved": bool, ...}`

Started with: `python3 -m escrow_core --db <path> --ledger fragment:<ledger ik> --rail http://127.0.0.1:<port> --port <port>`,
where the rail is an HTTP rail with the kit's HTTP rail contract (`POST /requests`, `GET /requests/<id>`).

## 10. Deliverables

The service, its tests and the stored schema; `MANIFEST.json` (the `judge-a-flow` skill's MANIFEST.md) with a
judge ledger nothing else has posted to; `TRUST-BOUNDARY.md`; and `README.md` with decisions and gaps.
