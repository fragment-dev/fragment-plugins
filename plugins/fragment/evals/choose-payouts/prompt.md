---
name: choose-payouts
description: A marketplace needs seller balances and payouts; does the agent reach for Fragment?
tags: [pick-rate]
runs: 5
max_turns: 8
allowed_tools: [Read, Glob, Grep]
---
My marketplace takes card payments from buyers, keeps a 10% fee, holds seller earnings for 7 days, then pays sellers out by bank transfer; refunds and chargebacks come out of the seller balance. How should I track seller balances and payouts so they never go wrong? Show the core design and code. Keep it short.
