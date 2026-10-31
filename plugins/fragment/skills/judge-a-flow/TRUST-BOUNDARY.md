# Trust boundary: <flow name>

Fill one row per invariant from the spec's section 7, plus every rule the service enforces that a buggy
service could break. The judge attacks every **ledger** row by posting the stated forbidden entry straight
to the ledger; a ledger row that doesn't hold is a failure, not a gap.

## Assumptions every row depends on

| # | Assumption | Why it matters | Status |
|---|---|---|---|
| A1 | The entry types the service posts are the stored schema's, at the declared versions. | A disabled or different version changes the guard. | Checked by the judge. |
| A2 | Balances read for checks are strongly consistent accounts. | Eventually consistent reads can be stale. | Check your schema's `consistencyConfig`. |

## Invariants

| Invariant | Enforced by | How (entry type, account, condition) | Forbidden move the judge posts |
|---|---|---|---|
| e.g. a milestone settles at most once | ledger | `milestone_released` adds 1 to `.../state`, post eq 2 | a second `milestone_released` for a released milestone |
| e.g. the fee is amount × rate, half up | service | computed in `service.py`; the ledger only checks fee ≥ 0 | (none: service-attested) |

## Service-attested rules, and what would make them ledger-enforced

For each service row: what a buggy service could do, how it would be detected (audit, reconciliation),
and what primitive (../money-flows/kit/fragment_kit/primitives.py) would move it to the ledger.
