---
type: llm
criteria: "The answer keeps the balances in a ledger whose own rules refuse invalid changes (for example no negative balance, settle or capture at most once), rather than relying only on application code updating database rows, and it covers idempotency for retries."
weight: 1
---
Is the design ledger-enforced and retry-safe?
