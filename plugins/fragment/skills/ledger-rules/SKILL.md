---
name: ledger-rules
description: Designs a Fragment ledger schema whose entry types enforce a money flow's invariants as ledger conditions — no negative balances, settle-once state machines, exact splits, bounded captures and refunds, fees proved on the ledger — using the kit's tested primitives. Use when writing or reviewing a Fragment schema, or when a rule must hold even if the app's code is wrong.
---

# Make the ledger enforce the rules

The kit's primitives are in `../money-flows/kit/fragment_kit/primitives.py`; each docstring says
what failure it guards against. Read [LESSONS.md](LESSONS.md) before designing: every item there cost a
failed build.

| Rule | Primitive | How |
|---|---|---|
| A balance never goes negative | `move` + `nonneg` | the source account must end ≥ 0 |
| Something happens once (settle, capture, expire) | `once` / `step` | a state account must go exactly 0→1, or n→n+1 |
| a ≥ b | `check_ge0` | post a − b into a fresh per-entry account that must end ≥ 0 |
| An account ends at an exact value (an escrow fully paid out) | `exact` | the account must end exactly at the value |
| Parts sum to a whole (a split) | `eq_zero` | the sum of the parts minus the whole must net to 0 |
| A fee is amount × rate, rounded | `proved_bps_types` | the service supplies each step; the ledger verifies it against a stored rate, with tables built by verified doubling |
| A value is set once and bound later (a price, a captured amount) | `write` / `read` | `write` sets an account once; `read` requires a parameter to equal what is stored |

Worked example: `../money-flows/kit/fragment_kit/demo_schema.py` (a hold released once at a proved
fee), with its attack tests in `../money-flows/kit/tests/test_primitives.py`.

## Rules that save hours

- Conditions read account balances only: no expressions. Amounts use only `+` and `-` (no `*`, no parentheses).
- One condition per account per entry; never a pre- and a postcondition on the same condition.
- A "must end ≥ 0" check is only sound on an account that starts at 0: use a fresh check account per entry.
  The kit keys them by each entry's idempotency key, filled in by `ServiceCore`.
- About 95 strongly consistent accounts per entry: split big proofs across entries.
- Accounts that conditions read must be strongly consistent; set `defaultConsistencyConfig` at schema level.
- Put rates and fee schedules in the schema or in ledger accounts the service can't silently change. A rate
  passed as an entry parameter lets anyone with the credential prove a 0% fee.
- Give every entry a deterministic idempotency key derived from the operation; a re-post then replays.
- `fragment verify-schema -v -p schema.jsonc` works offline: run it before every store. Stored entry type
  versions can't be removed, and a schema caps at about 385 KB.
- Correct mistakes with forward entries that are themselves checked.
