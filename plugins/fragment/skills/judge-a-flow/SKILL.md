---
name: judge-a-flow
description: Proves a ledger-backed money flow works by writing an independent judge from the spec alone, fixing its fingerprint before the build is read, then testing the service over HTTP (amounts, races, crashes, retries) and posting forbidden entries straight to the ledger, each of which must be refused. Use after building a money flow, before shipping it, or when someone asks whether a flow is correct.
---

# Judge a money flow

A build's own tests share its author's assumptions. The judge doesn't: it is written from the spec alone
and attacks both the service and the ledger.

1. **Write the judge from the spec only**, on `../money-flows/kit/fragment_kit/judge_harness.py`
   (`Harness`: starts and kills the service, a scripted HTTP rail with real in-flight states, `race`,
   `balances`, and `attack_all`). Subclass it; one method per spec area; a `check(name, ok, detail)` per
   claim. Cover: every operation's effects and refusals, authority, rounding edges, failed and late rail
   outcomes, replays and `operation_id_reused`, each race the spec names, and a kill-and-restart.
2. **Pre-register it**: record `shasum -a 256` of the judge before reading the build. If the judge turns out
   wrong, fix only those mistakes in a v2, document each with evidence, and keep both scores.
3. **The build supplies `MANIFEST.json`** ([MANIFEST.md](MANIFEST.md)): how to start the service, its
   accounts, and forbidden moves per invariant. `attack_all(fixtures)` posts each forbidden entry with the
   service's own credentials and requires Fragment to refuse it with a typed code, no watched balance to
   move, and the entry type to be one the service really uses.
4. **The build supplies `TRUST-BOUNDARY.md`** ([TRUST-BOUNDARY.md](TRUST-BOUNDARY.md)): each invariant marked
   ledger-enforced (and how) or service-attested (and why). Every ledger row gets attacked.
5. **Run it on a fresh ledger** created from the stored schema: shared accounts on a reused ledger carry
   balances from the last run.

The flow passes when every check passes, every forbidden move is refused, and the service-attested rows
are honest.
