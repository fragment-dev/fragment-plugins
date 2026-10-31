# MANIFEST.json: the standard format

The builder writes `MANIFEST.json` at the root of the build. The judge reads nothing else to find the
service, the ledger and the forbidden moves, so no per-build adapter is needed.

```json
{
  "flow": "milestone-escrow",
  "spec_version": 1,
  "schema": {"key": "escrow-v1-abc123", "version": 1, "file": "schema.jsonc"},
  "judge_ledger": "escrow-abc123-judge",
  "start": {"command": "python3 -m escrow_core --db {db} --ledger fragment:{ledger} --rail {rail} --port {port}",
            "cwd": "."},
  "accounts": {
    "client_wallet": "liabilities/clients/client:{client_id}/wallet",
    "milestone_escrow": "liabilities/escrow/milestone:{milestone_id}"
  },
  "forbidden": [
    {"invariant": "7.2",
     "fixture": "settled_milestone",
     "entry_type": "milestone_released", "version": 1,
     "params": {"milestone_id": "{settled_milestone.milestone_id}",
                "net": "={settled_milestone.amount} - {settled_milestone.fee}",
                "fee": "{settled_milestone.fee}"},
     "watch": [{"account": "milestone_escrow", "milestone_id": "{settled_milestone.milestone_id}"}]}
  ]
}
```

Rules:
- `start.command` placeholders: `{db}`, `{ledger}`, `{rail}` (the judge's HTTP rail URL), `{port}`. No shell
  syntax; `cwd` is relative to the manifest. The service must print nothing secret.
- `accounts`: Fragment paths with `{name}` placeholders for IDs (single braces).
- `forbidden`: at least one move per ledger-enforced invariant in the spec's section 7; more is better.
  - `fixture` names an object state the **spec** defines (section 7 lists them); the judge creates it through
    the interface and fills `{fixture.field}` from its own records (fields: the spec's IDs, `amount`, and any
    the spec names).
  - A parameter value starting with `=` is a sum: integers and `{fixture.field}` references joined by `+`/`-`.
  - Every parameter is sent as a string, so a forbidden move can't use an entry type that takes a list
    (repeated) parameter. Give each attacked rule an entry type with plain parameters.
  - An entry type with per-entry check accounts needs its own `operation_id` and `check_n` in `params`,
    unique to that move (for example `"operation_id": "atk-7-1-a", "check_n": "0"`), or the check
    accounts are already used.
  - `watch`: accounts (by name, with their placeholders) whose balances must not move when the judge posts it.
- The judge requires: Fragment refuses the entry with a typed code (`conditional_request_failed`, or a
  disabled/unknown version), no watched balance moves, and the entry type is one the service really posts.
