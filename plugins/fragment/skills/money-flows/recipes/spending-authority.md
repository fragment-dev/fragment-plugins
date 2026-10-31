# Agent spending authority: requirements (spec version 1)

> Built from this spec with the kit in 17 minutes; passed its independent judge 42/42 (after documented fixes to the judge's own mistakes), 10/10 forbidden entries refused.

A business lets AI agents spend its money on its behalf: paying vendors for operations work. Each agent has a
budget per period, a cap per payment and an approval threshold; payments above the threshold need a person's
approval, bound to that exact payment. The point of building it on a ledger: these limits hold **even if the
agent, or the software around it, misbehaves**, because the ledger refuses a payment that breaks them.

Amounts are integer US cents. Times are integer seconds supplied by the caller as `now`, never read from a clock.

## 1. Parties and authority

| Party | May do | May read |
|---|---|---|
| owner (the business) | deposit, withdraw, set_authority, freeze, unfreeze | everything |
| approver (a person) | approve, reject | pending requests, its own decisions |
| agent | request_spend | its own authority, spend and requests |
| platform | reconcile_rail | everything |

An agent never approves, and never changes its own authority. Mistakes are corrected only by forward
operations (a vendor refund), never by reversal.

## 2. Money and conservation

Money enters only by a confirmed deposit to the business's operating account and leaves only by a confirmed
payment to a vendor or a confirmed withdrawal (rail, section 6).

    operating balance + payments in flight = deposits confirmed + refunds confirmed - payments confirmed - withdrawals confirmed

## 3. Objects and states

- **Authority** (per agent), set by the owner with `set_authority`: `period_seconds` (> 0), `period_budget`,
  `per_payment_cap`, `approval_over` (all >= 0, cents), effective from `now`. Periods are aligned: period k
  covers `[k × period_seconds, (k+1) × period_seconds)`. A change takes effect for the *current* period with
  what has already been spent in it counted against the new budget. **Choose:** a lowered budget below what's
  already spent this period leaves nothing more to spend; it never claws back.
- **Agent state:** `active` or `frozen` (`freeze`/`unfreeze`, owner). A frozen agent can't spend; requests
  already approved but not yet paid are not paid while frozen.
- **Spend request** (`request_spend`, agent): `request_id`, `vendor`, `amount` (> 0), `purpose`. States:
  `refused` → (no effect), `pending_approval`, `approved` → `paid` | `returned`, `rejected`.
  - Over the per-payment cap, over what's left of the period budget, or with the agent frozen: `refused` with a reason.
  - At or under `approval_over`: paid at once (it counts against the budget immediately, see 4).
  - Over `approval_over`: `pending_approval`; its amount is **reserved** against the period budget at once.
- **Approval** (`approve` / `reject`, approver): for one pending request. An approval pays exactly that
  request's amount to exactly its vendor, once. A rejection releases the reservation.

## 4. Amounts

- **Budget used in a period** = paid + in flight + reserved for pending approvals, for payments requested in
  that period. **Choose:** a payment counts in the period it was *requested*, even if approved or settled later.
- **A vendor refund** (`refund_received`, platform, with the bank's transaction) returns money to the
  operating account; it does **not** restore budget. **Choose:** budget measures authority used, not net cost.
- A returned payment (the rail fails it) restores both the money and the budget it used.
- No fees in this flow.

## 5. Time

- Periods as above; `now` decides the period of every request. Approving after the period ends still pays
  from the request's own period's budget (already reserved).
- Approvals don't expire in v1. **Choose:** stated so; a real deployment might add expiry.

## 6. The rail, failure and recovery

- Deposits, vendor payments and withdrawals use the kit's HTTP rail contract (`POST /requests`,
  `GET /requests/<id>`, states `confirmed`, `failed`, `unknown`). A payment leaves the operating account at once,
  is in flight until confirmed, and returns (restoring budget) if it fails. `reconcile_rail` looks up every
  request in flight. A request ID moves money at most once.
- Every operation carries `operation_id`, `now` and `actor` (`{"role", "id"}`). A replay of the identical request
  returns the first answer and changes nothing; the same ID with any different field is rejected `operation_id_reused`.
- A crash at any point must not lose or duplicate money or budget.
- Races: two requests from one agent that together exceed its budget; an approval racing a freeze; two
  approvals of one request: the outcome equals some serial order, and nothing is paid twice.

## 7. Invariants the ledger itself must enforce

1. **Budget.** An agent's budget used in a period never exceeds that period's budget (with the authority in
   force), counting paid, in flight and reserved.
2. **Cap.** No single payment exceeds the agent's per-payment cap.
3. **Approval is bound and single-use.** A payment over `approval_over` posts only by consuming an approval for
   that request, for exactly its amount and vendor, at most once; a request is paid at most once.
4. **Frozen means stopped.** No payment posts for a frozen agent.
5. **No negative money.** The operating account never goes negative.

Service-attested and acceptable: who is an approver (the ledger can't compare identities), the period
arithmetic (`now` → period index), and conservation as a whole (the judge checks it).

**Fixtures** (the judge creates these and records the fields listed):
- `agent_at_budget`: an agent whose period budget is fully used. Fields: `agent`, `period`, `budget`, `used`.
- `pending_request`: a request awaiting approval. Fields: `agent`, `request_id`, `vendor`, `amount`.
- `paid_request`: an approved request, paid. Fields: as above.
- `frozen_agent`: Fields: `agent`, `period`.
- `operating_account`: Fields: `balance` when recorded.

## 8. Interface (the judge uses exactly this)

HTTP JSON on `127.0.0.1:<port>`.
- `POST /op/<operation>` → `{"status": "accepted" | "pending_approval" | "rejected", ...}`. Operations: `deposit`,
  `withdraw`, `set_authority`, `freeze`, `unfreeze`, `request_spend`, `approve`, `reject`, `refund_received`,
  `reconcile_rail`.
- `GET /agent/<id>?now=<t>` → `{"state", "period", "period_budget", "used", "remaining", "per_payment_cap", "approval_over"}`
- `GET /request/<id>` → `{"status", "agent", "vendor", "amount", "period", "approved_by", "paid_at"}`
- `GET /account` → `{"operating_balance", "in_flight"}`
- `GET /totals` → `{"conserved": bool, ...}`

Reasons the judge expects where it tests them: `over_cap`, `over_budget`, `frozen`, `insufficient_funds`,
`unauthorized`, `operation_id_reused`, `invalid_state`.

## 9. Deliverables

As the `money-flow-spec` template, section 9: the service, tests, stored schema, `MANIFEST.json` (the `judge-a-flow` skill's MANIFEST.md, with
accounts `operating_account` and `agent_budget_used` (placeholders `{agent}`, `{period}`)), `TRUST-BOUNDARY.md`,
and `README.md` with decisions, gaps and times.
