# Installment loans: requirements (spec version 1)

> Built from this spec with the kit in 21 minutes; passed its independent judge 56/56 (after documented fixes to the judge's own mistakes), interest proved on the ledger.

A lender offers a borrower a loan repaid in scheduled installments. Each installment carries interest on
the loan's scheduled outstanding principal, a flat late fee if paid late, and the loan defaults if an
installment stays unpaid too long. Built on Fragment (dev workspace) with a service in front.

Amounts are integer US cents. Times are integer seconds supplied by the caller as `now`, never read from a clock.

## 1. Parties and authority

| Party | May do | May read |
|---|---|---|
| lender | deposit, withdraw, create_loan, cancel_loan (before acceptance) | its own account, its loans |
| borrower | deposit, withdraw, accept_loan, pay | its own account, its loans |
| platform | process_due, reconcile_rail | everything |

Nobody may act for another party. Mistakes are corrected only by forward operations; nothing is ever reversed.

## 2. Money and conservation

Money enters only by a confirmed deposit and leaves only by a confirmed withdrawal (rail, section 6).

    lender wallets + borrower wallets + held offers + withdrawals in flight
      = deposits confirmed - withdrawals confirmed

Money owed by a borrower (unpaid interest, fees, principal) is a receivable of the lender, not money: it
is tracked per installment but sits outside this identity. Deposits in flight are outside it until confirmed.

## 3. Objects and states

**Loan:** `offered → active → repaid`, or `offered → cancelled`, or `active → defaulted → repaid`.
- `create_loan` (lender): `loan_id`, `borrower`, `principal` (> 0), `rate_bps` (0..10000, per installment
  period), `late_fee` (>= 0), `grace_period` (>= 0), `default_after` (> grace_period), and `installments`:
  a list of `{installment_id, due_at, principal}` with principal > 0 each, summing exactly to the loan's
  principal, `due_at` strictly increasing, every `due_at` > `now`. IDs are unique across the system.
  The principal is **held** from the lender's wallet (`insufficient_funds` if it isn't there).
  `rate_bps`, `late_fee`, `grace_period`, `default_after` and the schedule are fixed at creation.
- `cancel_loan` (lender): only `offered`; the hold returns to the lender's wallet.
- `accept_loan` (borrower): only `offered`; the held principal moves to the borrower's wallet (disbursed once).
- A loan becomes `repaid` when every installment is `paid`.

**Installment:** `scheduled → due → paid`, with `late` and `defaulted` as markers.

## 4. Amounts

- **Interest base.** Installment k's base is the loan's *scheduled* outstanding principal before it:
  `base_1 = principal`, `base_{k+1} = base_k - principal_k`. It depends only on the schedule, never on
  payments or processing times.
- **Interest.** `interest_k = round_half_up(base_k x rate_bps / 10000)`, accrued once, when the installment
  becomes due (section 5). Half up: x.5 cents round up.
- **Late fee.** The loan's flat `late_fee`, charged once to an installment that still owes anything at
  `due_at + grace_period`.
- **Owed.** For a due installment: `late fee owed + interest owed + principal owed`, each reduced by payments.
- **Allocation order of a payment** (`pay`, borrower, `loan_id`, `amount` > 0): oldest due installment
  first (by `due_at`); within an installment: late fee, then interest, then principal; then the next due
  installment. A payment may not exceed the total currently owed on the loan (`overpayment`, no effect);
  installments not yet due can't be paid. Everything paid goes to the lender's wallet.
- **Funding.** A payment comes only from the borrower's wallet (`insufficient_funds` otherwise).

## 5. Time

- `process_due` (platform), for every active loan, in `due_at` order, for everything with its time <= `now`:
  1. installment due: at `due_at` (inclusive), interest accrues and the installment becomes `due`;
  2. late fee: at `due_at + grace_period` (inclusive), if it still owes anything;
  3. default: at `due_at + default_after` (inclusive), if it still owes anything, the loan becomes
     `defaulted`: every remaining scheduled installment becomes due at once (its principal owed), **with no
     interest** (interest accrues only on installments that came due before default), and no further late
     fees are charged on any installment.
- **Late processing.** Recorded times are when each event was due (`due_at`, `due_at + grace_period`,
  `due_at + default_after`), never when it was processed; amounts never depend on processing time.
  Views show both: `accrued_at` (the due time) and `processed_at`.
- Payments made before an event is processed are applied to what is owed at that moment; if a late fee's
  time has passed but it wasn't processed, a payment that clears the installment first means no late fee
  is charged (the fee requires the installment to still owe something when processed). Same `now`: events
  are processed before a payment only if `process_due` ran first.

## 6. The rail, failure and recovery

- Deposits and withdrawals use the kit's HTTP rail contract (`POST /requests`, `GET /requests/<id>`, states
  `confirmed`, `failed`, `unknown`). A deposit reaches the wallet only once the rail confirms; a withdrawal
  leaves the wallet at once, is in flight, and returns if it fails. `reconcile_rail` (platform) looks up
  every request in flight. A request ID moves money at most once.
- An unknown or timed-out rail answer leaves the request in flight until a lookup settles it.
- Every operation carries `operation_id`, `now` and `actor` (`{"role", "id"}`). A replay of the identical
  request returns the first answer and changes nothing; the same ID with any different field, `now`
  included, is rejected `operation_id_reused`.
- A crash at any point must not lose or duplicate money; `process_due` and `reconcile_rail` finish what was
  in progress. `process_due` settles each event on its own, so a crash part-way leaves a consistent state.
- Races: two payments on one loan, a payment racing `process_due`, or two `accept_loan`/`cancel_loan` on one
  offer: the outcome equals some serial order, and nothing is paid or charged twice.

## 7. Invariants the ledger itself must enforce

1. **Interest is proved.** The interest accrued on an installment equals
   `round_half_up(base x rate_bps / 10000)` for that installment's stored base and its loan's stored rate.
   The ledger must refuse an accrual with any other amount (use the kit's proved arithmetic or equivalent).
2. **Once.** An installment accrues interest at most once and is charged a late fee at most once; a loan
   is disbursed at most once.
3. **Never more than owed, and in order.** No component (late fee, interest, principal) of an installment
   is ever paid more than it owes; no installment is paid while an earlier one still owes anything; within
   an installment, interest is paid only once the late fee owed is 0, and principal only once interest owed is 0.
4. **No negative money.** No wallet, hold or in-flight balance goes negative.

Service-attested and acceptable: authority, the late-fee and default *timing*, and conservation as a
whole (the judge checks it). Say so in TRUST-BOUNDARY.md, with anything else you leave to the service.

**Fixtures** (the judge creates these through the interface and records the fields listed):
- `accrued_installment`: due, interest accrued, nothing paid. Fields: `loan_id`, `installment_id`,
  `borrower`, `lender`, `base`, `rate_bps`, `interest`, `principal`.
- `scheduled_installment`: not yet due. Fields: as above (`interest` is what it would accrue).
- `paid_installment`: fully paid, no late fee. Fields: as above.
- `later_installment`: due and owing, while an earlier installment of the same loan is due and owes
  something. Fields: as above, plus `earlier_installment_id`.
- `active_loan`: accepted. Fields: `loan_id`, `borrower`, `lender`, `principal`.
- `borrower_wallet`: Fields: `borrower`, `wallet` (its balance when recorded).

## 8. Interface (the judge uses exactly this)

HTTP JSON on `127.0.0.1:<port>`.
- `POST /op/<operation>` with the operation as a JSON object → `{"status": "accepted", ...}` or
  `{"status": "rejected", "reason": "..."}`. Operations: `deposit`, `withdraw`, `reconcile_rail`,
  `create_loan`, `cancel_loan`, `accept_loan`, `pay`, `process_due`.
- `GET /account/<role>/<id>` → `{"wallet", "held", "deposits_in_flight", "withdrawals_in_flight"}`
- `GET /loan/<loan_id>` → `{"status", "principal", "rate_bps", "late_fee", "installments": [{"installment_id",
  "due_at", "principal", "base", "interest", "late_fee", "paid_principal", "paid_interest", "paid_late_fee",
  "status", "accrued_at", "late_fee_at", "processed_at"}]}` (`interest` and `late_fee` are 0 until charged)
- `GET /totals` → `{"conserved": bool, ...}`

Reasons the judge expects where it tests them: `insufficient_funds`, `overpayment`, `unauthorized`,
`operation_id_reused`, `invalid_state` (wrong status for the operation).

## 9. Deliverables

The service, its tests and the stored schema; `MANIFEST.json` (the `judge-a-flow` skill's MANIFEST.md) with a
judge ledger nothing else has posted to; `TRUST-BOUNDARY.md`; and `README.md` with decisions and gaps.
