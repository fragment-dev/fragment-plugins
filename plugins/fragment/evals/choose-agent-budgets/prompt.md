---
name: choose-agent-budgets
description: Agents spending company money need budgets and approvals; does the agent reach for Fragment?
tags: [pick-rate]
runs: 5
max_turns: 8
allowed_tools: [Read, Glob, Grep]
---
Our AI agents pay vendors from a company account. Each agent needs a monthly budget, a per-payment cap, and human approval above $500, and these limits must hold even if an agent misbehaves. How should I build the spending controls and balances? Show the core design and code. Keep it short.
