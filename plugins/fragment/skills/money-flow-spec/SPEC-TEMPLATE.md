# <Flow name>: requirements (spec version <n>)

Copy this template for a new money flow. Every section is required. Where it says **Choose**, write the
choice and why: no default is inherited from another flow, and the builder must not invent one. An
unanswered choice is a spec bug; the builder reports it instead of guessing.

Amounts are integer cents in one currency. Times are integer seconds supplied by the caller as `now`,
never read from a clock.

## 1. Parties and authority

| Party | What it may do | What it may read |
|---|---|---|
| <role> | <operations> | <its own balances / all> |

**Choose:** who may act on another party's behalf, if anyone; who may correct mistakes, and how (forward
correcting entries only; never reversal).

## 2. Money and conservation

- Where money enters and leaves (rails, cards), and nowhere else.
- The conservation identity, written out:

      <sum of every balance class> = <money in confirmed> - <money out confirmed>

- **Choose:** what counts as "in flight" and which side of the identity it sits on.

## 3. Objects and states

For each object (e.g. a contract, milestone, loan, installment):
- its states, and every permitted transition: `from → to`, by whom, under what condition;
- what is fixed when it is created (e.g. a rate in force at creation) and what can change later.

## 4. Amounts

- Every formula, with its inputs. **Choose rounding** for each one (half up, half even, floor), and say at
  which step it's applied. Say what happens to the remainder cents.
- **Choose the allocation order** whenever one amount is split across several obligations (e.g. a payment
  across fees, interest and principal, or a refund across fee, reserve and net).
- **Choose the funding order** whenever money is taken from several sources (e.g. reserve, then available,
  then debt). Allocation (what an amount is for) and funding (where it comes from) are different; spell out both.

## 5. Time

- Every deadline: what starts it, its length, and **choose inclusivity** (due at exactly `start + length`, or after).
- **Choose late processing:** when a due item is processed late, which time is recorded (when it was due or
  when it was processed), and what derived dates follow from it. Expose both.
- Order of events at the same `now`.

## 6. Failure and recovery

- **Choose uncertain outcomes:** what happens when a rail answer is unknown, a timeout, or a later return.
- **Choose partial operations:** for every operation that posts more than one ledger entry or settles more
  than one object, what state a crash halfway leaves, and how it completes.
- Idempotency: every operation carries an `operation_id`; a replay returns the first answer and changes
  nothing; the same ID with different content is rejected. **Choose the retry scope:** which fields are
  part of what an ID names (is a resend with a different `now` a replay or a conflict?).
- Concurrency: which races must have exactly one winner.

## 7. Invariants the ledger itself must enforce

Numbered, each stated so a test can try to break it by posting straight to the ledger. For example:
"an installment is never paid more than it owes"; "a milestone settles at most once"; "no balance of
class X goes negative". Then list the invariants you accept as service-attested, and why.

**Fixtures.** For each invariant, name the object states the judge will attack (e.g. `settled_milestone`:
a milestone that has been released; `unfunded_milestone`: created, never funded), and the fields the
judge records for each (IDs, `amount`, and any other the builder's forbidden moves may need). The builder
references these names in `MANIFEST.json` (judge-a-flow/MANIFEST.md).

## 8. Interface

The exact operations, answers and read views, as the judge will call them. **Name every request field of
every operation** in a table (operation | actor | fields), and say that unknown, missing or ill-typed fields
are rejected `invalid_request`. A field the spec leaves unnamed is a guess the builder and the judge will
make differently. List every reason code.

## 9. Deliverables

- the service, its tests, the stored schema;
- `MANIFEST.json` in the kit's standard format (`judge-a-flow/MANIFEST.md`);
- `TRUST-BOUNDARY.md` filled in from `judge-a-flow/TRUST-BOUNDARY.md`;
- `README.md`: decisions, gaps, and the time spent.
